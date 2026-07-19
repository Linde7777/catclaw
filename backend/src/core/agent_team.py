from typing import Protocol

from src.core.agent_activity import AgentActivityEmitter, AgentIdentity, EventEmitter
from src.core.agent_runner import AgentRunner


MAIN_AGENT_NAME = "main"


class SubagentRunner(Protocol):
    def start(self, *, first_message: str) -> None: ...

    def submit_agent_message(self, *, sender_name: str, content: str) -> None: ...


class SubagentFactory(Protocol):
    def __call__(self, *, name: str) -> SubagentRunner: ...


class AgentTeam:
    """
    WebSocket / Agent 工具
              │
              ▼
          AgentTeam
          ├── main AgentRunner
          ├── lightweight SubagentRunner
          └── memory manager activity
                    │
                    ▼
           AgentActivityEmitter
    """

    def __init__(self, *, main_runner: AgentRunner, emit_activity_event: EventEmitter) -> None:
        self._main_runner = main_runner
        self._emit_activity_event = emit_activity_event

    def start(self) -> None:
        self._main_runner.start()

    def submit_main_user_message(self, *, message_id: str, content: str) -> None:
        self._main_runner.submit_user_message(frontend_msg_id=message_id, user_message=content)

    def request_main_pause(self) -> None:
        self._main_runner.request_pause()

    def resume_main(self) -> None:
        self._main_runner.resume()

    def create_subagent(self, *, name: str, first_message: str) -> AgentIdentity:
        raise NotImplementedError

    def send_message(self, *, sender_name: str, recipient_name: str, content: str) -> None:
        raise NotImplementedError

    def open_activity(self, *, identity: AgentIdentity) -> AgentActivityEmitter:
        return AgentActivityEmitter(identity=identity, emit=self._emit_activity_event)
