import json
from pathlib import Path

from src.conversation_repository import ConversationRepository
from src.conversation_state import ConversationState


def test_load_latest_returns_none_without_history(tmp_path: Path) -> None:
    repository = ConversationRepository(originals_dir=tmp_path)

    assert repository.load_latest() is None


def test_persist_and_load_latest_roundtrip(tmp_path: Path) -> None:
    repository = ConversationRepository(originals_dir=tmp_path)
    conversation = ConversationState(
        init_messages=[{"role": "system", "content": "instruction"}],
        messages=[{"role": "user", "content": "hello"}],
    )
    conversation.last_triggered_threshold = 12
    conversation.pause_requested = True

    repository.persist(conversation)
    loaded = repository.load_latest()

    assert loaded == conversation
    assert conversation.file_name is not None
    payload = json.loads((tmp_path / conversation.file_name).read_text(encoding="utf-8"))
    assert "file_name" not in payload
    assert payload["messages"] == [{"role": "user", "content": "hello"}]


def test_persist_reuses_assigned_file_name(tmp_path: Path) -> None:
    repository = ConversationRepository(originals_dir=tmp_path)
    conversation = ConversationState(init_messages=[{"role": "user", "content": "instruction"}])

    repository.persist(conversation)
    first_file_name = conversation.file_name
    conversation.messages.append({"role": "user", "content": "hello"})
    repository.persist(conversation)

    assert conversation.file_name == first_file_name
    assert len(list(tmp_path.glob("*.json"))) == 1
