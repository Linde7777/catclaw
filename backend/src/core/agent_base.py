from abc import ABC, abstractmethod
from dataclasses import dataclass
from enum import StrEnum
from typing import Any


class DriveReason(StrEnum):
    backlog_user_msg = "backlog_user_msg"
    backlog_tool_execution = "backlog_tool_execution"
    backlog_tool_followup = "backlog_tool_followup"
    not_started = "not_started"
    no_backlog = "no_backlog"
    paused_no_backlog = "paused_no_backlog"
    paused_with_backlog = "paused_with_backlog"


@dataclass(frozen=True)
class DriveDecision:
    should_drive: bool
    reason: DriveReason


class AgentBase(ABC):
    @abstractmethod
    def start_conversation(self) -> None:
        raise NotImplementedError

    @abstractmethod
    def enqueue_user_message(self, *, frontend_msg_id: str, user_message: str) -> None:
        raise NotImplementedError

    @abstractmethod
    def enqueue_agent_message(self, *, sender_name: str, content: str) -> None:
        """接收另一个 agent 发来的消息。"""
        raise NotImplementedError

    @abstractmethod
    def get_visible_messages(self) -> list[dict[str, Any]]:
        """返回当前 conversation 中供 UI 展示的消息。"""
        raise NotImplementedError

    @abstractmethod
    def request_pause(self) -> None:
        raise NotImplementedError

    @abstractmethod
    def clear_pause(self) -> None:
        raise NotImplementedError

    @abstractmethod
    def is_paused(self) -> bool:
        raise NotImplementedError

    @abstractmethod
    def is_pause_requested(self) -> bool:
        raise NotImplementedError

    @abstractmethod
    async def run(self) -> dict[str, Any]:
        raise NotImplementedError

    @abstractmethod
    def drive_decision(self) -> DriveDecision:
        """
        runner 用它来决定“是否应该自动调用 run()”。

        说明：
        - drive_decision() 会把 pause gate / not_started 等 runner 约束编码进 reason
        - “backlog” 的判断也应该在这里完成，避免 runner 额外拼条件
        """
        raise NotImplementedError
