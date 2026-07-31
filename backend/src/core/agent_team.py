from __future__ import annotations

from collections.abc import Callable
from dataclasses import dataclass
from enum import StrEnum
from typing import Any, TYPE_CHECKING

if TYPE_CHECKING:
    from src.core.agent_runner import AgentRunner
    from src.core.memory_manager import MemoryManagerRunSnapshot


class AgentStatus(StrEnum):
    idle = "idle"
    busy = "busy"
    finished = "finished"
    failed = "failed"


@dataclass(frozen=True)
class AgentNode:
    agent_id: str
    name: str
    parent_agent_id: str | None
    status: AgentStatus
    supports_steer: bool
    supports_pause: bool
    can_create_subagents: bool


@dataclass(frozen=True)
class AgentTeamEvent:
    agent_id: str
    # None 表示 Agent 本身的事件。非 None 表示该 Agent 内部一次 memory manager 运行的事件。
    memory_manager_run_id: str | None
    payload: dict[str, Any]


@dataclass(frozen=True)
class AgentTreeSnapshot:
    """
    表示某一时刻的完整 agent 树，不包含任何聊天记录。

    WebSocket 新订阅或重连时先用它建立树，再接收后续增量事件。
    前端选择节点后，单独读取该 agent 的可见消息。
    """

    root_agent_id: str
    agents: tuple[AgentNode, ...]


AgentTeamEventSubscriber = Callable[[AgentTeamEvent], None]
Unsubscribe = Callable[[], None]


class AgentTeam:
    """
    管理一棵可交互的 agent 树，并向展示层提供统一事件。

    树中的节点只表示 Agent，不包含 Agent 内部的 memory_manager。
    每个 Agent 自己创建 memory manager，并把相关事件作为自身工作过程输出。
    """

    _root_agent_id: str
    _nodes_by_id: dict[str, AgentNode]
    _agent_ids_by_name: dict[str, str]
    _agent_runners_by_id: dict[str, AgentRunner]
    _subscribers: list[AgentTeamEventSubscriber]
    _allow_nested_subagents: bool

    def __init__(
        self,
        *,
        root_agent_name: str,
        allow_nested_subagents: bool = False,
    ) -> None:
        """保存团队依赖，并创建尚未启动的根节点。"""
        raise NotImplementedError

    def start(self) -> AgentTreeSnapshot:
        """启动根 Agent，恢复它最近的 conversation，并返回当前 AgentTree。"""
        raise NotImplementedError

    def snapshot(self) -> AgentTreeSnapshot:
        """从注册表生成不含聊天正文的团队树快照。"""
        raise NotImplementedError

    def get_visible_messages(self, *, agent_id: str) -> list[dict[str, Any]]:
        """找到指定 agent 的 runner，并向它读取可见消息。"""
        raise NotImplementedError

    def get_memory_manager_run_snapshots(
        self,
        *,
        agent_id: str,
    ) -> tuple[MemoryManagerRunSnapshot, ...]:
        """找到指定 Agent，并读取它内部的 memory manager 运行记录。"""
        raise NotImplementedError

    def submit_user_message(
        self,
        *,
        agent_id: str,
        frontend_msg_id: str,
        content: str,
    ) -> None:
        """找到指定 agent，并把前端用户消息提交给它。"""
        raise NotImplementedError

    def create_subagent(
        self,
        *,
        parent_agent_id: str,
        name: str,
        first_message: str,
    ) -> AgentNode:
        """
        创建并启动具有独立 conversation 的 subagent。

        新建 subagent 必须创建新的 conversation，不能恢复任何其他 Agent 的记录。
        """
        raise NotImplementedError

    def send_message(
        self,
        *,
        sender_agent_id: str,
        target_agent_name: str,
        content: str,
    ) -> None:
        """定位目标 agent，包装来源信息，然后提交 agent 消息。"""
        raise NotImplementedError

    def request_pause(self, *, agent_id: str) -> None:
        """检查指定 agent 的能力，并把暂停请求转发给它。"""
        raise NotImplementedError

    def resume(self, *, agent_id: str) -> None:
        """检查指定 agent 的能力，并把恢复请求转发给它。"""
        raise NotImplementedError

    def subscribe(self, *, subscriber: AgentTeamEventSubscriber) -> Unsubscribe:
        """注册事件订阅者，并返回只移除该订阅者的函数。"""
        raise NotImplementedError

    async def close(self) -> None:
        """停止团队中的运行任务，并释放应用级资源。"""
        raise NotImplementedError
