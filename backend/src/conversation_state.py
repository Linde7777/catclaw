from dataclasses import dataclass, field
from typing import Any


@dataclass
class ConversationState:
    init_messages: list[dict[str, Any]]
    messages: list[dict[str, Any]] = field(default_factory=list)
    file_name: str | None = None
    summarizer_awaken_count: int = 0
    decider_awaken_count: int = 0
    last_triggered_threshold: int = 0
    reset_carryover_messages: list[dict[str, Any]] = field(default_factory=list)
    last_summarized_msg_idx: int | None = None
    last_summarized_signature: str = ""
    pause_requested: bool = False
    paused: bool = False

    def build_model_messages(self) -> list[dict[str, Any]]:
        return [
            *[dict(message) for message in self.init_messages],
            *[dict(message) for message in self.messages],
        ]
