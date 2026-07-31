from __future__ import annotations

from collections.abc import Callable
from dataclasses import dataclass
from typing import Any, Literal, TYPE_CHECKING

if TYPE_CHECKING:
    from src.core.agent_runner import AgentRunner
    from src.core.memory_manager import DeciderRunner, SummarizerRunner


RunnerEventEmitter = Callable[[dict[str, Any]], None]
ConversationStartMode = Literal["new", "restore_latest"]


@dataclass(frozen=True)
class WorkerRunnerInput:
    agent_id: str
    name: str
    first_message: str | None
    # 根 agent 使用 restore_latest；新 subagent 使用 new，避免恢复其他 agent 的 conversation。
    conversation_start_mode: ConversationStartMode
    can_create_subagents: bool
    emit_event: RunnerEventEmitter


@dataclass(frozen=True)
class SummarizerRunnerInput:
    agent_id: str
    name: str
    worker_messages: list[dict[str, Any]]
    is_first_time_awaken: bool
    last_summarized_signature: str
    emit_event: RunnerEventEmitter


@dataclass(frozen=True)
class DeciderRunnerInput:
    agent_id: str
    name: str
    worker_messages: list[dict[str, Any]]
    emit_event: RunnerEventEmitter


class AgentRunnerFactory:
    """
    根据 AgentTeam 创建的节点生成对应 runner。

    输入包含节点、初始上下文和统一事件出口。
    输出是 AgentRunner、SummarizerRunner 或 DeciderRunner。
    """

    def create_worker_runner(
        self,
        *,
        runner_input: WorkerRunnerInput,
    ) -> AgentRunner:
        """创建包含独立 Agent、工具和持久化状态的 AgentRunner。"""
        raise NotImplementedError

    def create_summarizer_runner(
        self,
        *,
        runner_input: SummarizerRunnerInput,
    ) -> SummarizerRunner:
        """创建读取 worker 快照并维护记忆文档的 SummarizerRunner。"""
        raise NotImplementedError

    def create_decider_runner(
        self,
        *,
        runner_input: DeciderRunnerInput,
    ) -> DeciderRunner:
        """创建读取 worker 快照并返回 reset 判断的 DeciderRunner。"""
        raise NotImplementedError
