from collections.abc import Callable
from dataclasses import dataclass
from typing import Any, Literal


AgentActivityKind = Literal["main", "subagent", "summarizer", "decider"]
EventEmitter = Callable[[dict[str, Any]], None]


@dataclass(frozen=True)
class AgentIdentity:
    agent_id: str
    name: str
    kind: AgentActivityKind


class AgentActivityEmitter:
    def __init__(self, *, identity: AgentIdentity, emit: EventEmitter) -> None:
        self._identity = identity
        self._emit = emit

    def emit_started(self) -> None:
        self._emit(
            {
                "type": "agent.activity.started",
                "agentId": self._identity.agent_id,
                "agentName": self._identity.name,
                "agentKind": self._identity.kind,
            }
        )

    def emit_event(self, event: dict[str, Any]) -> None:
        if "agentId" in event:
            raise ValueError("activity event 不能自行指定 agentId")
        self._emit({**event, "agentId": self._identity.agent_id})

    def emit_completed(self) -> None:
        self._emit(
            {
                "type": "agent.activity.completed",
                "agentId": self._identity.agent_id,
            }
        )
