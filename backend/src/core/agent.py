import asyncio
import json
import logging
from collections import deque
from typing import Any, Protocol
from dataclasses import dataclass
from math import ceil

from src.commons import get_model_context_window_tokens, noop
from src.conversation_repository import ConversationRepository
from src.conversation_state import ConversationState
from src.core.agent_base import AgentBase, DriveDecision, DriveReason
from src.core.agent_turn import (
    stream,
    execute_tool_calls,
    TurnResult,
    TurnUsage,
    OnAiContentDelta,
    OnAiReasoningDelta,
    OnAiToolCallStarted,
    OnAiToolCallArgumentsDelta,
    OnAiToolCallFinished,
    OnToolResult,
)
from src.tools.tool import Tool
from src.core.memory_manager import (
    DeciderRunner,
    SummarizerRunner,
)
from src.core.model_config import ModelConfig
from src.toolkits import build_summarizer_tools

MEMORY_MANAGER_CONTEXT_USED_THRESHOLD_STEP_PERCENT = 3

logger = logging.getLogger(__name__)


@dataclass(frozen=True)
class QueuedUserMessage:
    frontend_msg_id: str  # 前端渲染要用到，这个id是前端生成并维护的
    content: str


class OnUserMsgEnqueued(Protocol):
    def __call__(self, *, frontend_msg_id: str) -> None: ...


class OnQueuedUserMsgCommitted(Protocol):
    def __call__(self, *, frontend_msg_id: str) -> None: ...


class OnSwitchConversation(Protocol):
    def __call__(self, *, visible_messages: list[dict[str, Any]]) -> None: ...


class OnPauseRequested(Protocol):
    def __call__(self) -> None: ...


class OnPaused(Protocol):
    def __call__(self) -> None: ...


class OnResumed(Protocol):
    def __call__(self) -> None: ...


class Agent(AgentBase):

    def __init__(self, *, name: str, model_config: ModelConfig,
                 init_messages: list[dict[str, Any]],
                 tools: list[Tool],
                 on_ai_content_delta: OnAiContentDelta | None = None,
                 on_ai_reasoning_delta: OnAiReasoningDelta | None = None,
                 on_ai_tool_call_started: OnAiToolCallStarted | None = None,
                 on_ai_tool_call_arguments_delta: OnAiToolCallArgumentsDelta | None = None,
                 on_ai_tool_call_finished: OnAiToolCallFinished | None = None,
                 on_tool_result: OnToolResult | None = None,
                 on_user_msg_enqueued: OnUserMsgEnqueued | None = None,
                 on_queued_user_msg_committed: OnQueuedUserMsgCommitted | None = None,
                 on_switch_conversation: OnSwitchConversation | None = None,
                 on_pause_requested: OnPauseRequested | None = None,
                 on_paused: OnPaused | None = None,
                 on_resumed: OnResumed | None = None,
                 conversation_repository: ConversationRepository | None = None,
                 ) -> None:
        self.name = name
        self._model_config = model_config
        self._conversation = ConversationState(init_messages=[message.copy() for message in init_messages])
        self._conversation_repository = conversation_repository or ConversationRepository()
        self._tools = tools
        if len({tool.name for tool in tools}) != len(tools):
            raise ValueError("tools 里存在重复的 name")
        self._on_ai_content_delta = on_ai_content_delta or noop
        self._on_ai_reasoning_delta = on_ai_reasoning_delta or noop

        # started 不一定表示是函数的名字出来了，有些供应商是先给 ID 什么的
        self._on_ai_tool_call_started = on_ai_tool_call_started or noop
        self._on_ai_tool_call_arguments_delta = on_ai_tool_call_arguments_delta or noop
        self._on_ai_tool_call_finished = on_ai_tool_call_finished or noop
        self._on_tool_result = on_tool_result or noop

        self._user_msg_queue: deque[QueuedUserMessage] = deque()

        self._on_user_msg_enqueued = on_user_msg_enqueued or noop
        self._on_queued_user_msg_committed = on_queued_user_msg_committed or noop
        self._on_switch_conversation = on_switch_conversation or noop
        self._on_pause_requested = on_pause_requested or noop
        self._on_paused = on_paused or noop
        self._on_resumed = on_resumed or noop

        self._summarizer_runner = SummarizerRunner()
        self._decider_runner = DeciderRunner()
        self._summarizer_task: asyncio.Task[None] | None = None
        self._decider_task: asyncio.Task[bool] | None = None
        self._run_in_progress = False
        self._memory_manager_reset_task: asyncio.Task[None] | None = None

    def start_conversation(self) -> None:
        conversation = self._conversation_repository.load_latest()
        if conversation is None:
            logger.info("Agent[%s].start_conversation：创建新会话", self.name)
            self._conversation = ConversationState(
                init_messages=[message.copy() for message in self._conversation.init_messages],
            )
            self._notify_switch_conversation()
            self._on_resumed()
            return

        logger.info("Agent[%s].start_conversation：恢复历史会话（file=%s）", self.name, conversation.file_name)
        if self._user_msg_queue:
            raise RuntimeError("加载 conversation 文件之前不能有排队中的 user message")

        self._conversation = conversation
        self._notify_switch_conversation()
        self._notify_pause_state_for_new_connection()

    def _persist_if_started(self) -> None:
        if self._conversation.file_name is not None:
            self._conversation_repository.persist(self._conversation)

    def _notify_switch_conversation(self) -> None:
        self._on_switch_conversation(
            visible_messages=[dict(message) for message in self._conversation.messages]
        )

    def _notify_pause_state_for_new_connection(self) -> None:
        # 新连接恢复 conversation 时，需要把 pause 状态补发给前端，
        # 否则 UI 会默认展示“未暂停”，与后端实际状态不一致。
        if self._conversation.paused:
            self._on_paused()
            return
        if self._conversation.pause_requested:
            self._on_pause_requested()

    def enqueue_user_message(self, *, frontend_msg_id: str, user_message: str) -> None:
        if self._conversation.paused or self._conversation.pause_requested:
            logger.info(
                "Agent[%s].enqueue_user_message：暂停中自动恢复（paused=%s pause_requested=%s）",
                self.name,
                self._conversation.paused,
                self._conversation.pause_requested,
            )
            self.clear_pause()
        self._user_msg_queue.append(QueuedUserMessage(frontend_msg_id, user_message))
        logger.info(
            "Agent[%s].enqueue_user_message：已入队（frontend_msg_id=%s queue=%s user_len=%s）",
            self.name,
            frontend_msg_id,
            len(self._user_msg_queue),
            len(user_message),
        )
        self._on_user_msg_enqueued(frontend_msg_id=frontend_msg_id)

    def request_pause(self) -> None:
        if self._conversation.paused:
            return
        self._conversation.pause_requested = True
        self._persist_if_started()
        logger.info("Agent[%s].request_pause：pause_requested=true", self.name)
        self._on_pause_requested()

    def clear_pause(self) -> None:
        """解除 pause gate；是否继续运行由 AgentRunner 决定。"""
        was_paused = self._conversation.paused
        was_pause_requested = self._conversation.pause_requested
        self._conversation.pause_requested = False
        self._conversation.paused = False
        self._persist_if_started()
        if was_paused or was_pause_requested:
            logger.info("Agent[%s].clear_pause：已解除暂停（was_paused=%s was_pause_requested=%s）", self.name, was_paused,
                        was_pause_requested)
            self._on_resumed()

    def is_paused(self) -> bool:
        return self._conversation.paused

    def is_pause_requested(self) -> bool:
        return self._conversation.pause_requested

    def drive_decision(self) -> DriveDecision:
        backlog_reason = self._backlog_reason()

        # paused 是一个硬边界：一旦进入 paused，runner 必须停下，等待显式解除暂停。
        if self._conversation.paused:
            if backlog_reason is None:
                return DriveDecision(should_drive=False, reason=DriveReason.paused_no_backlog)
            return DriveDecision(should_drive=False, reason=DriveReason.paused_with_backlog)

        if backlog_reason is not None:
            return DriveDecision(should_drive=True, reason=backlog_reason)

        # 无 backlog，但也要区分“未开始”与“正常 idle”，方便上层做更可读的判断/埋点。
        if self._conversation.file_name is None:
            return DriveDecision(should_drive=False, reason=DriveReason.not_started)

        return DriveDecision(should_drive=False, reason=DriveReason.no_backlog)

    def _backlog_reason(self) -> DriveReason | None:
        if self._user_msg_queue:
            return DriveReason.backlog_user_msg

        if self._conversation.file_name is None:
            return None

        if not self._conversation.messages:
            return None

        last = self._conversation.messages[-1]
        role = last.get("role")

        # 1) assistant(tool_calls) 说明工具还没真正执行完（可能是中断后续跑）。
        if role == "assistant" and last.get("tool_calls"):
            return DriveReason.backlog_tool_execution

        # 2) tool message 说明还欠一轮“工具结果后的 follow-up assistant”。
        # （可能是被中断了导致的）
        if role == "tool":
            return DriveReason.backlog_tool_followup

        return None

    def _safe_drain_user_message_queue(self) -> None:
        while self._user_msg_queue:
            item = self._user_msg_queue.popleft()
            user_message = {"role": "user", "content": item.content}
            self._conversation.messages.append(user_message)
            logger.info(
                "Agent[%s]._safe_drain_user_message_queue：出队并持久化（frontend_msg_id=%s remaining=%s user_len=%s）",
                self.name,
                item.frontend_msg_id,
                len(self._user_msg_queue),
                len(item.content),
            )
            # 只有等到用户发送了一个消息 之后，才创建对话文件。
            # 不然用户创建了一个会话，但是没有说任何内容，然后这个对话文件就被持久化下来了，
            # 然后用户 resume conversation ，结果发现这玩意是空的，这就很不合理。
            first_persist = self._conversation.file_name is None
            self._conversation_repository.persist(self._conversation)
            if first_persist:
                logger.info(
                    "Agent[%s] 会话已持久化（file=%s）",
                    self.name,
                    self._conversation.file_name,
                )
            self._on_queued_user_msg_committed(frontend_msg_id=item.frontend_msg_id)

    @staticmethod
    def _attach_background_task_exception_logger(*, task: asyncio.Task[Any], task_name: str, agent_name: str) -> None:
        """
        目的：确保后台 task 的异常一定会被观察到，否则 asyncio 会报：
        "Task exception was never retrieved"

        这里用 done callback 主动调用 task.exception() 完成“异常领取”，并打日志。
        """

        def _on_done(done_task: asyncio.Task[Any]) -> None:
            try:
                exc = done_task.exception()
            except asyncio.CancelledError:
                logger.info("Agent[%s] 后台任务 %s 被取消", agent_name, task_name)
                return
            except Exception as exc:
                # 这里是 done callback，任何异常都不应继续向外冒泡，否则会污染事件循环日志。
                logger.exception(
                    "Agent[%s] 读取后台任务 %s 的异常时失败：%s: %s",
                    agent_name,
                    task_name,
                    type(exc).__name__,
                    exc,
                )
                return

            if exc is not None:
                logger.error("Agent[%s] 后台任务 %s 异常退出", agent_name, task_name, exc_info=exc)

        task.add_done_callback(_on_done)

    def _attach_summarizer_task_callbacks(self, *, task: asyncio.Task[None]) -> None:
        self._attach_background_task_exception_logger(
            task=task,
            task_name="summarizer_task",
            agent_name=self.name,
        )

    def _attach_decider_result_handler(self, *, task: asyncio.Task[bool]) -> None:
        self._attach_background_task_exception_logger(
            task=task,
            task_name="decider_task",
            agent_name=self.name,
        )

        def _on_done(done_task: asyncio.Task[bool]) -> None:
            try:
                loop = asyncio.get_running_loop()
            except RuntimeError:
                logger.warning("Agent[%s] decider task 完成时事件循环不可用，跳过结果处理", self.name)
                return
            loop.create_task(self._sync_decider_result(done_task))

        task.add_done_callback(_on_done)

    async def _sync_decider_result(self, decider_task: asyncio.Task[bool]) -> None:
        try:
            should_reset_context = await decider_task
        except asyncio.CancelledError:
            raise
        except Exception:
            # 异常已经在回调里打过日志，这里只负责阻断后续 reset 流程。
            return

        logger.info("Agent[%s] memory manager decider 结果（should_reset_context=%s）", self.name, should_reset_context)
        if not should_reset_context:
            return

        reset_task = self._memory_manager_reset_task
        if reset_task is not None and not reset_task.done():
            logger.info("Agent[%s] memory manager reset 流程已在进行中，跳过重复启动", self.name)
            return

        self._memory_manager_reset_task = asyncio.create_task(self._handle_memory_manager_reset_request())
        self._attach_background_task_exception_logger(
            task=self._memory_manager_reset_task,
            task_name="memory_manager_reset_task",
            agent_name=self.name,
        )

    async def _wait_until_worker_paused_for_reset(self) -> None:
        while not self._conversation.paused:
            if not self._run_in_progress and self._conversation.pause_requested:
                self._enter_paused_state(log_reason="decider 结果返回时 worker 已空闲，直接进入 paused")
                return
            await asyncio.sleep(0.05)

    async def _wait_for_summarizer_before_reset(self) -> None:
        summarizer_task = self._summarizer_task
        if summarizer_task is None or summarizer_task.done():
            return

        logger.info("Agent[%s] reset_context 前等待 summarizer_task 完成", self.name)
        try:
            await summarizer_task
        except asyncio.CancelledError:
            raise
        except Exception:
            # summarizer 的异常会由后台任务回调统一记录；这里不阻断 reset，
            # 否则 decider 已经决定需要重置时，会因为摘要失败而卡住上下文回收。
            logger.warning("Agent[%s] summarizer_task 失败，reset_context 继续执行", self.name)

    def _enter_paused_state(self, *, log_reason: str) -> None:
        self._conversation.pause_requested = False
        self._conversation.paused = True
        self._persist_if_started()
        logger.info("Agent[%s].run：%s", self.name, log_reason)
        self._on_paused()

    def _build_reset_carryover_messages(self) -> list[dict[str, Any]]:
        new_messages = self._conversation.messages
        last_summarized_msg_idx = self._conversation.last_summarized_msg_idx
        if last_summarized_msg_idx is None:
            logger.error(
                "Agent[%s] reset_context 缺少 last_summarized_msg_idx（new_messages=%s）",
                self.name,
                len(new_messages),
            )
            raise RuntimeError("reset_context 缺少 last_summarized_msg_idx")

        carryover_messages = new_messages[last_summarized_msg_idx + 1:]
        return [dict(message) for message in carryover_messages]

    def _build_last_summarized_boundary(self) -> tuple[int, str] | None:
        new_messages = self._conversation.messages
        if not new_messages:
            return None

        last_msg_idx = len(new_messages) - 1
        rendered_messages: list[str] = []
        for message in new_messages:
            content = message.get("content")
            if isinstance(content, str):
                rendered_messages.append(content)
            else:
                rendered_messages.append(json.dumps(content, ensure_ascii=False, separators=(",", ":")))

        last_message_content = rendered_messages[last_msg_idx]
        signature = last_message_content
        max_window = min(60, len(last_message_content))
        for window in range(10, max_window + 1):
            if len(last_message_content) <= window * 2:
                candidate = last_message_content
            else:
                candidate = f"{last_message_content[:window]}......{last_message_content[-window:]}"

            matched_count = sum(1 for content in rendered_messages if content == last_message_content or (
                    len(content) <= window * 2 and candidate == content
            ) or (
                                        len(content) > window * 2 and candidate == f"{content[:window]}......{content[-window:]}"
                                ))
            signature = candidate
            if matched_count == 1:
                break

        return last_msg_idx, signature

    async def _handle_memory_manager_reset_request(self) -> None:
        self.request_pause()
        await self._wait_until_worker_paused_for_reset()
        await self._wait_for_summarizer_before_reset()
        carryover_messages = self._build_reset_carryover_messages()
        self._conversation.reset_carryover_messages = [dict(message) for message in carryover_messages]
        self._conversation_repository.persist(self._conversation)
        self._reset_context(carryover_messages=carryover_messages)

    @staticmethod
    def _estimate_prompt_tokens_from_messages(messages: list[dict[str, Any]]) -> int:
        packed = json.dumps(messages, ensure_ascii=False, separators=(",", ":"))
        return ceil(len(packed.encode("utf-8")) / 4)

    def _resolve_prompt_tokens(self, *, usage: TurnUsage) -> int:
        prompt_tokens = usage.prompt_tokens
        if prompt_tokens is not None:
            return prompt_tokens

        estimated_tokens = self._estimate_prompt_tokens_from_messages(self._conversation.build_model_messages())
        logger.info(
            "Agent[%s] 本轮缺少 usage.prompt_tokens，回退为本地估算（estimated_tokens=%s）",
            self.name,
            estimated_tokens,
        )
        return estimated_tokens

    async def _maybe_wake_memory_manager(self, *, prompt_tokens: int) -> None:
        context_limit = get_model_context_window_tokens(model=self._model_config.model)
        current_tokens = prompt_tokens
        last_triggered_threshold = self._conversation.last_triggered_threshold

        used_percent = int(current_tokens * 100 / context_limit)
        current_threshold = (
                                    used_percent // MEMORY_MANAGER_CONTEXT_USED_THRESHOLD_STEP_PERCENT) * MEMORY_MANAGER_CONTEXT_USED_THRESHOLD_STEP_PERCENT
        if current_threshold <= last_triggered_threshold:
            return

        logger.info(
            "Agent[%s] 唤醒 memory manager（file=%s tokens=%s used_percent=%s last_threshold=%s current_threshold=%s step=%s）",
            self.name,
            self._conversation.file_name,
            current_tokens,
            used_percent,
            last_triggered_threshold,
            current_threshold,
            MEMORY_MANAGER_CONTEXT_USED_THRESHOLD_STEP_PERCENT,
        )
        self._conversation.last_triggered_threshold = current_threshold

        summarizer_task = self._summarizer_task
        if summarizer_task is None or summarizer_task.done():
            summarizer_round = self._conversation.summarizer_awaken_count + 1
            previous_last_summarized_signature = self._conversation.last_summarized_signature
            last_summarized_boundary = self._build_last_summarized_boundary()
            if last_summarized_boundary is not None:
                self._conversation.last_summarized_msg_idx = last_summarized_boundary[0]
                self._conversation.last_summarized_signature = last_summarized_boundary[1]
            worker_messages_snapshot = self._conversation.build_model_messages()
            summarizer_tools = build_summarizer_tools(provider=self._model_config.provider)
            logger.info(
                "Agent[%s] 启动 summarizer_task（round=%s messages=%s）",
                self.name,
                summarizer_round,
                len(worker_messages_snapshot),
            )
            summarizer_task = asyncio.create_task(
                self._summarizer_runner.run(
                    worker_messages=worker_messages_snapshot,
                    model_config=self._model_config,
                    tools=summarizer_tools,
                    is_first_time_awaken=self._conversation.summarizer_awaken_count == 0,
                    last_summarized_signature=previous_last_summarized_signature,
                    conversation_file_name=self._conversation.file_name,
                    awaken_round=summarizer_round,
                )
            )
            self._attach_summarizer_task_callbacks(task=summarizer_task)
            self._summarizer_task = summarizer_task
            self._conversation.summarizer_awaken_count = summarizer_round

        decider_task = self._decider_task
        if decider_task is None or decider_task.done():
            decider_round = self._conversation.decider_awaken_count + 1
            worker_messages_snapshot = self._conversation.build_model_messages()
            decider_tools = build_summarizer_tools(provider=self._model_config.provider)
            logger.info(
                "Agent[%s] 启动 decider_task（round=%s messages=%s）",
                self.name,
                decider_round,
                len(worker_messages_snapshot),
            )
            self._decider_task = asyncio.create_task(
                self._decider_runner.run(
                    worker_messages=worker_messages_snapshot,
                    model_config=self._model_config,
                    tools=decider_tools,
                    conversation_file_name=self._conversation.file_name,
                    awaken_round=decider_round,
                )
            )
            self._attach_decider_result_handler(task=self._decider_task)
            decider_task = self._decider_task
            self._conversation.decider_awaken_count = decider_round
        if decider_task is None:
            logger.warning("memory manager decider task 未初始化，本次跳过 decider")
        self._conversation_repository.persist(self._conversation)

    def _append_runtime_message(self, message: dict[str, Any]) -> None:
        # 这个函数被用的地方都是在 run 函数的后方，
        # run开头就drain user message，这函数出来之后一定是已经有持久化文件了。
        if self._conversation.file_name is None:
            raise RuntimeError("conversation 尚未开始，不能追加运行时消息")
        self._conversation.messages.append(message)
        self._conversation_repository.persist(self._conversation)

    def _reset_context(self, *, carryover_messages: list[dict[str, Any]]) -> None:
        from src.core.init_prompts import (
            build_init_messages,
        )

        self._conversation = ConversationState(
            init_messages=build_init_messages(provider=self._model_config.provider),
            messages=[dict(message) for message in carryover_messages],
        )
        self._conversation_repository.persist(self._conversation)
        self._notify_switch_conversation()
        self._on_resumed()

    async def run(self) -> dict[str, Any]:
        self._safe_drain_user_message_queue()
        if self._conversation.file_name is None:
            # 显式校验：如果没有待处理的 user message，就不应该进入模型生成路径。
            # 否则会进入 assistant message 的持久化路径，最终抛出更隐晦的异常。
            raise RuntimeError("conversation 尚未开始：没有待处理的 user message，请先 enqueue_user_message()")

        self._run_in_progress = True
        try:
            while True:
                model_messages = self._conversation.build_model_messages()
                last_message = self._conversation.messages[-1]
                if last_message.get("role") == "assistant" and last_message.get("tool_calls"):
                    # assistant tool call 已经持久化，说明上次运行在执行工具前中断了。
                    # 直接从工具阶段继续，避免再次调用模型或重复追加 assistant 消息。
                    logger.info("Agent[%s].run：恢复未执行的 tool_calls", self.name)
                    turn_result = TurnResult(assistant_message=last_message, usage=TurnUsage())
                else:
                    logger.info(
                        "Agent[%s].run：开始模型调用（messages=%s tools=%s paused=%s pause_requested=%s）",
                        self.name,
                        len(model_messages),
                        len(self._tools),
                        self._conversation.paused,
                        self._conversation.pause_requested,
                    )
                    turn_result = await stream(
                        model_config=self._model_config,
                        messages=model_messages,
                        tools=self._tools,
                        on_ai_content_delta=self._on_ai_content_delta,
                        on_ai_reasoning_delta=self._on_ai_reasoning_delta,
                        on_ai_tool_call_started=self._on_ai_tool_call_started,
                        on_ai_tool_call_arguments_delta=self._on_ai_tool_call_arguments_delta,
                        on_ai_tool_call_finished=self._on_ai_tool_call_finished,
                    )
                    self._append_runtime_message(turn_result.assistant_message)
                    
                ai_msg_dict = turn_result.assistant_message
                if not ai_msg_dict.get("tool_calls"):
                    # 即使本轮没有工具调用，也需要按上下文阈值唤醒 memory manager，
                    # 否则“纯聊天”场景永远不会触发摘要/重置判断。
                    await self._maybe_wake_memory_manager(
                        prompt_tokens=self._resolve_prompt_tokens(usage=turn_result.usage)
                    )
                    if self._conversation.pause_requested:
                        # 为了让“暂停”在有pending user message的场景下也可靠生效：
                        # 即使本轮没有 tool_calls，只要本轮模型调用已经结束，
                        # 我们也要在回合边界暂停，阻止 runner 立刻进入下一轮模型调用。
                        self._enter_paused_state(log_reason="在回合边界进入 paused")
                    return ai_msg_dict

                logger.info("Agent[%s].run：收到 tool_calls（n=%s）", self.name, len(ai_msg_dict.get("tool_calls") or []))
                tool_messages = await execute_tool_calls(ai_msg_dict=ai_msg_dict, tools=self._tools,
                                                         on_tool_result=self._on_tool_result)
                for tool_message in tool_messages:
                    self._append_runtime_message(tool_message)

                # 在这里maybe wake memory manager，最后一条msg是tool result msg
                # 这个格式是合法的，可以在这个基础上跑 summarizer、decider 任务
                await self._maybe_wake_memory_manager(
                    prompt_tokens=self._resolve_prompt_tokens(usage=turn_result.usage)
                )
                if self._conversation.pause_requested:
                    # 用户点击暂停，可能是想看一会，然后恢复运行之前，还要输入一些内容，
                    # 所以暂停检查点应该在 drain user msg 之前。
                    # 同时必须在 tool_messages 已经 append/persist 且 memory manager 唤醒结束之后，
                    # 否则会造成“用户看到了工具结果，但 memory manager 状态没有同步”的错觉。
                    self._enter_paused_state(log_reason="在工具执行后进入 paused")
                    return ai_msg_dict

                # steer message 注入点。在执行完toolcall后注入最符合直觉
                # 另外注意，我们是在 memory manager reset-context 之后才注入，
                # 因为上下文越精简，ai表现越好，reset context的优先级应高于steer conversation
                self._safe_drain_user_message_queue()
                continue
        finally:
            self._run_in_progress = False
