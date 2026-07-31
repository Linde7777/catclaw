from dataclasses import dataclass
from enum import StrEnum
from typing import Any

from src.core.init_prompts import TAG_BIONIC_BOT_INSTRUCTION
from src.commons import MEMORY_MAIN_MD, MEMORY_TODO_MD, SUMMARIES_DIR
from src.core.init_prompts import read_main_memory

from src.core.agent_turn import (
    AgentTurnCallbacks,
    execute_tool_calls,
    stream,
)
from src.tools.tool import Tool
from src.core.memory_manager_run_logger import MemoryManagerRunLogger
from src.core.model_config import ModelConfig

RESET_CONTEXT_MAGIC_WORD = "BIONIC-BOT-RESET-CONTEXT"


class MemoryManagerKind(StrEnum):
    summarizer = "summarizer"
    decider = "decider"


class MemoryManagerRunStatus(StrEnum):
    running = "running"
    finished = "finished"
    failed = "failed"
    cancelled = "cancelled"


@dataclass(frozen=True)
class MemoryManagerRunSnapshot:
    """
    表示某个 Agent 内部的一次 memory manager 运行，供 UI 展示。

    name 使用 summarizer-N 或 decider-N，N 在所属 Agent reset context 后重新计数。
    visible_messages 只包含 fork 后新增的消息，不重复所属 Agent 的既有消息。
    """

    run_id: str
    name: str
    kind: MemoryManagerKind
    status: MemoryManagerRunStatus
    visible_messages: tuple[dict[str, Any], ...]


class SummarizerRunner:
    run_id: str
    name: str
    status: MemoryManagerRunStatus
    _visible_messages: list[dict[str, Any]]

    def snapshot(self) -> MemoryManagerRunSnapshot:
        """返回本次 summarizer 运行的身份、状态和可见消息。"""
        raise NotImplementedError

    def get_visible_messages(self) -> list[dict[str, Any]]:
        """
        返回本次 summarizer 运行中供 UI 展示的消息。
        完整的 message 包含 fork 之前的 worker 的消息，展示这部分消息就很冗余
        """
        raise NotImplementedError

    async def run(
            self,
            *,
            worker_messages: list[dict[str, Any]],
            model_config: ModelConfig,
            tools: list[Tool],
            is_first_time_awaken: bool,
            last_summarized_signature: str,
            conversation_file_name: str,
            awaken_round: int,
            callbacks: AgentTurnCallbacks,
    ) -> None:
        forked_messages = [dict(message) for message in worker_messages]
        logger = MemoryManagerRunLogger(
            conversation_file_name=conversation_file_name,
            runner_kind="summarizer",
            awaken_round=awaken_round,
        )
        logger.append_event(
            {
                "worker_messages": len(worker_messages),
                "forked_messages": len(forked_messages),
                "tools": [tool.name for tool in tools],
                "provider": model_config.provider,
                "model": model_config.model,
                "is_first_time_awaken": is_first_time_awaken,
            }
        )
        user_prompt = {
            "role": "user",
            "content": build_summarizer_instruction(
                is_first_time_awaken=is_first_time_awaken,
                last_summarized_signature=last_summarized_signature,
            ),
        }
        forked_messages.append(
            {
                **user_prompt,
            }
        )
        logger.append_event(user_prompt)

        while True:
            turn_result = await stream(
                model_config=model_config,
                messages=forked_messages,
                tools=tools,
                # 在medium时，summarizer会有过度工作的问题
                reasoning_effort="low",
                on_ai_content_delta=callbacks.on_ai_content_delta,
                on_ai_reasoning_delta=callbacks.on_ai_reasoning_delta,
                on_ai_tool_call_started=callbacks.on_ai_tool_call_started,
                on_ai_tool_call_arguments_delta=callbacks.on_ai_tool_call_arguments_delta,
                on_ai_tool_call_finished=callbacks.on_ai_tool_call_finished,
            )
            assistant_message = turn_result.assistant_message
            forked_messages.append(assistant_message)
            logger.append_event(
                {
                    "role": "assistant",
                    "content": "\n".join(
                        s for s in [assistant_message.get("reasoning_content"), assistant_message.get("content")] if
                        isinstance(s, str) and s
                    ),
                    "tool_calls": assistant_message.get("tool_calls") or [],
                }
            )
            if not assistant_message.get("tool_calls"):
                break

            tool_messages = await execute_tool_calls(
                ai_msg_dict=assistant_message,
                tools=tools,
                on_tool_result=callbacks.on_tool_result,
            )
            forked_messages.extend(tool_messages)
            for tool_message in tool_messages:
                logger.append_event(tool_message)

        logger.append_event(
            {
                "hint": "runner.finished",
                "forked_messages": len(forked_messages),
            }
        )
        return None


class DeciderRunner:
    run_id: str
    name: str
    status: MemoryManagerRunStatus
    _visible_messages: list[dict[str, Any]]

    def snapshot(self) -> MemoryManagerRunSnapshot:
        """返回本次 decider 运行的身份、状态和可见消息。"""
        raise NotImplementedError

    def get_visible_messages(self) -> list[dict[str, Any]]:
        """返回本次 decider 运行中供 UI 展示的消息。"""
        raise NotImplementedError

    async def run(
            self,
            *,
            worker_messages: list[dict[str, Any]],
            model_config: ModelConfig,
            tools: list[Tool],
            conversation_file_name: str,
            awaken_round: int,
            callbacks: AgentTurnCallbacks,
    ) -> bool:
        forked_messages = [dict(message) for message in worker_messages]
        logger = MemoryManagerRunLogger(
            conversation_file_name=conversation_file_name,
            runner_kind="decider",
            awaken_round=awaken_round,
        )
        logger.append_event(
            {
                "hint": "runner.started",
                "worker_messages": len(worker_messages),
                "forked_messages": len(forked_messages),
                "tools": [tool.name for tool in tools],
                "provider": model_config.provider,
                "model": model_config.model,
            }
        )
        user_prompt = {
            "role": "user",
            "content": build_decider_instruction(),
        }
        forked_messages.append(
            {
                **user_prompt,
            }
        )
        logger.append_event(user_prompt)

        while True:
            turn_result = await stream(
                model_config=model_config,
                messages=forked_messages,
                tools=tools,
                on_ai_content_delta=callbacks.on_ai_content_delta,
                on_ai_reasoning_delta=callbacks.on_ai_reasoning_delta,
                on_ai_tool_call_started=callbacks.on_ai_tool_call_started,
                on_ai_tool_call_arguments_delta=callbacks.on_ai_tool_call_arguments_delta,
                on_ai_tool_call_finished=callbacks.on_ai_tool_call_finished,
            )
            assistant_message = turn_result.assistant_message
            forked_messages.append(assistant_message)
            logger.append_event(
                {
                    "role": "assistant",
                    "content": "\n".join(
                        s for s in [assistant_message.get("reasoning_content"), assistant_message.get("content")] if
                        isinstance(s, str) and s
                    ),
                    "tool_calls": assistant_message.get("tool_calls") or [],
                }
            )
            tool_calls = assistant_message.get("tool_calls")
            if not tool_calls:
                break

            # decider runner 只判断是否 reset-context，不允许真正执行工具。
            # 但为了不破坏 provider 的“工具缓存”，我们依然把 tools 透传给 stream，
            # 并对 tool_calls 统一回一个不可执行的 tool result，让对话继续走到结束。
            tool_messages: list[dict[str, Any]] = []
            for call in tool_calls:
                tool_call_id = call.get("id")
                if not isinstance(tool_call_id, str) or not tool_call_id:
                    continue
                tool_message = {
                    "role": "tool",
                    "tool_call_id": tool_call_id,
                    "content": "判断是否需要重置上下文不需要工具调用",
                }
                tool_messages.append(tool_message)
                logger.append_event(tool_message)
            forked_messages.extend(tool_messages)

        content = assistant_message.get("content")
        should_reset = isinstance(content, str) and RESET_CONTEXT_MAGIC_WORD in content.splitlines()
        logger.append_event(
            {
                "hint": "runner.finished",
                "forked_messages": len(forked_messages),
                "should_reset_context": should_reset,
            }
        )
        return should_reset


def build_summarizer_instruction(is_first_time_awaken: bool, last_summarized_signature: str) -> str:
    if is_first_time_awaken:
        summarizer_operation_history_prompt = (f"<summarizer_operation_history_info>"
                                           f"这是你第一次在当前会话中被唤醒，"
                                           f"“磁盘中的{MEMORY_MAIN_MD}”和“上下文中的{MEMORY_MAIN_MD}”是一致的，没有被之前的你修改过"
                                           "</summarizer_operation_history_info>")
    else:
        summarizer_operation_history_prompt = f"""
<summarizer_operation_history_info>
这不是你第一次在当前会话中被唤醒，你之前已经处理过记忆文档。

你上一次被唤醒的边界消息签名是：
<signature>
{last_summarized_signature}
</signature>
这条边界消息以及它之前的内容，都已经被之前的你摘要过了。

这是当前 {MEMORY_MAIN_MD} 的内容（你等会不需要再调用工具去读一遍了）：
<{MEMORY_MAIN_MD}>
{read_main_memory()}
</{MEMORY_MAIN_MD}>
</summarizer_operation_history_info>
"""

    return f"""
<roles_change_notice>

**先停下你手头上的事，阅读下面的消息**

**你的角色是 summarizer，你刚从 worker 的上下文中被 fork 出来。**

你现在要做的事情就是处理记忆文档，比如对当前上下文做摘要然后放到记忆文档中、整理记忆文档等等

***摘要要达成的效果是：当 worker 清空了上下文，然后再加载你之前写的摘要时，worker 能够像没清空之前那样无缝地继续工作***，当你疑惑要记录还是不记录某个信息时，想想这个目的，你就知道要怎么做了。

通常来说：
- 做摘要 = 丢弃中间过程，只保留最后的结果
- 你应该记住犯过的错误，免得以后再犯。
- 你应该记住一个文件大概是讲什么的
- 你不应该去记“一个小时前执行了ls命令”这种无关紧要的信息

你必须维护记忆文档的结构，杂乱无章的记忆会影响你的发挥和后续维护。

随着你做的事情越来越多，记忆文档的长度也会越来越多，**你要确保 AGENTS.md 只存储80%以上的情况都会用到的记忆**，比如用户偏好。不会经常用到的记忆要放到其他文档中，然后在 AGENTS.md 里面留下对这些文档的大致描述（引用）就行了。这里不是说所有的其他记忆文档都要被 AGENTS.md 直接引用，而是可以被间接引用，比如有 20 个文档都是关于某个主题的，你要把它们都放进一个文件夹里面，然后在 AGENTS.md 里面记录这个文件夹大概装了什么就行。

再次强调，***摘要要达成的效果是：当你清空了上下文，然后再加载你之前写的摘要时，你能够像没清空之前那样无缝地继续工作***

不要对上下文中<{TAG_BIONIC_BOT_INSTRUCTION}>以及这之前的指令做摘要，因为这些信息在重置后系统会自动注入

{summarizer_operation_history_prompt}

你当前的工作目录已经被改为 {SUMMARIES_DIR}

另外再次提醒，你不能修改 {MEMORY_TODO_MD} 

</roles_change_notice>
"""


def build_decider_instruction() -> str:
    return f"""
<roles_change_notice>

**先停下你手头上的事，阅读下面的消息**

**你的角色是 decider，你刚从worker的上下文中被 fork 出来**

你现在要做的事情就是判断当前是否要重置上下文

**判断是否要重置上下文的标准：如果当前上下文中有50%以上的内容都是对当前任务不重要的，那通常就要重置。（这里的50%是按token估算）**

一个例子是，当前上下文中有大量的中间过程，而我们只需要最后的结果，那通常就应该重置。

例外情况：如果预估worker还有几轮就可以完成任务，而这时刚好大约有50%的内容是不重要的，那么这个时候一般不建议重置。如果你感觉很难预估，那你就认为需要很久才能完成任务就行了。

如果判断出要重置上下文，你就输出 {RESET_CONTEXT_MAGIC_WORD} ，系统检测到后，就会重置

你会看到一些工具，但是你不能去使用它们，因为判断是否需要重置上下文并不需要工具

</roles_change_notice>
"""


def _build_context_token_detail(messages: dict[str, Any]) -> str:
    # 打印以下消息占据的上下文百分比窗口
    # - user msg
    # - AI reasoning 占据多少百分比
    # - AI content占据多少
    # - AI tool call，且其内部还会再细分各个工具的占比（大于一定比例才显示，小于一定比例的，通通归为“其他工具”）
    # - tool result 占据多少百分比，且其内部还会再细分各个工具的tool result的占比（大于一定比例才显示，小于一定比例的，通通归为“其他工具”）
    raise NotImplementedError
