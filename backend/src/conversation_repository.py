import json
from dataclasses import asdict
from datetime import datetime, timezone
from pathlib import Path
from uuid import uuid4

import coolname
from pydantic import TypeAdapter, ValidationError

from src.commons import ORIGINALS_DIR
from src.conversation_state import ConversationState


_CONVERSATION_ADAPTER = TypeAdapter(ConversationState)


def _build_file_name() -> str:
    slug = coolname.generate_slug()
    timestamp = datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%S%fZ")
    return f"{slug}-{timestamp}.json"


def _timestamp_from_file_name(file_name: str) -> str | None:
    _, separator, timestamp = Path(file_name).stem.rpartition("-")
    if not separator:
        return None
    try:
        datetime.strptime(timestamp, "%Y%m%dT%H%M%S%fZ")
    except ValueError:
        return None
    return timestamp


class ConversationRepository:
    def __init__(self, *, originals_dir: Path | None = None) -> None:
        self._originals_dir = (originals_dir or ORIGINALS_DIR).expanduser()

    def load_latest(self) -> ConversationState | None:
        if not self._originals_dir.exists():
            return None

        candidates = (
            (timestamp, path)
            for path in self._originals_dir.glob("*.json")
            if path.is_file() and (timestamp := _timestamp_from_file_name(path.name)) is not None
        )
        latest = max(candidates, default=None)
        if latest is None:
            return None

        file_path = latest[1]
        try:
            payload = json.loads(file_path.read_text(encoding="utf-8"))
            return _CONVERSATION_ADAPTER.validate_python({**payload, "file_name": file_path.name})
        except json.JSONDecodeError as exc:
            raise ValueError(f"conversation JSON 解析失败: {file_path.name}") from exc
        except ValidationError as exc:
            raise ValueError(f"conversation JSON 结构非法: {file_path.name}") from exc

    def persist(self, conversation: ConversationState) -> None:
        self._originals_dir.mkdir(parents=True, exist_ok=True)
        if conversation.file_name is None:
            conversation.file_name = _build_file_name()

        file_path = self._originals_dir / conversation.file_name
        payload = asdict(conversation)
        payload.pop("file_name")
        temp_path = file_path.with_name(f".{file_path.name}.{uuid4().hex}.tmp")
        temp_path.write_text(json.dumps(payload, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
        temp_path.replace(file_path)
