import json
import tempfile
import unittest
from pathlib import Path

from src.conversation_repository import ConversationRepository
from src.conversation_state import ConversationState
from src.core.agent import Agent
from src.core.model_config import ModelConfig

OLD_INIT_MESSAGES = [
    {"role": "system", "content": "system-old"},
    {"role": "user", "content": "user-old"},
]
NEW_INIT_MESSAGES = [
    {"role": "system", "content": "system-new"},
    {"role": "user", "content": "user-new"},
]


class StartConversationTests(unittest.TestCase):
    def test_start_conversation_restores_latest_messages_and_reuses_file(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            originals_dir = Path(temp_dir)
            repository = ConversationRepository(originals_dir=originals_dir)
            conversation = ConversationState(
                init_messages=OLD_INIT_MESSAGES,
                messages=[
                    {"role": "user", "content": "hello"},
                    {"role": "assistant", "content": "hi"},
                ],
            )
            repository.persist(conversation)
            switch_events: list[list[dict]] = []

            stored_files = list(originals_dir.glob("*.json"))
            self.assertEqual(len(stored_files), 1)
            file_path = stored_files[0]
            self.assertEqual(file_path.name, conversation.file_name)

            agent = Agent(
                name="demo",
                model_config=ModelConfig(model="demo", base_url="https://example.com", api_key="key"),
                init_messages=NEW_INIT_MESSAGES,
                tools=[],
                on_switch_conversation=lambda *, visible_messages: switch_events.append(visible_messages),
                conversation_repository=repository,
            )

            agent.start_conversation()

            self.assertEqual(agent._conversation.init_messages, OLD_INIT_MESSAGES)
            self.assertTrue(all("meta" not in m for m in agent._conversation.messages))
            self.assertEqual(
                switch_events,
                [[
                    {"role": "user", "content": "hello"},
                    {"role": "assistant", "content": "hi"},
                ]],
            )

            agent.enqueue_user_message(frontend_msg_id="frontend-1", user_message="next")
            agent._safe_drain_user_message_queue()

            stored_files_after = list(originals_dir.glob("*.json"))
            self.assertEqual(stored_files_after, [file_path])
            payload = json.loads(file_path.read_text(encoding="utf-8"))
            self.assertEqual(payload["messages"][-1]["role"], "user")
            self.assertEqual(payload["messages"][-1]["content"], "next")
            self.assertNotIn("meta", payload["messages"][-1])

    def test_start_conversation_rejects_invalid_latest_conversation(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            originals_dir = Path(temp_dir)
            (originals_dir / "invalid-20260429T120000000000Z.json").write_text("{}", encoding="utf-8")
            repository = ConversationRepository(originals_dir=originals_dir)
            agent = Agent(
                name="demo",
                model_config=ModelConfig(model="demo", base_url="https://example.com", api_key="key"),
                init_messages=[{"role": "user", "content": "user"}],
                tools=[],
                conversation_repository=repository,
            )

            with self.assertRaisesRegex(ValueError, "结构非法"):
                agent.start_conversation()

    def test_start_conversation_restores_memory_manager_state(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            originals_dir = Path(temp_dir)
            repository = ConversationRepository(originals_dir=originals_dir)
            conversation = ConversationState(
                init_messages=OLD_INIT_MESSAGES,
                messages=[{"role": "user", "content": "hello"}],
                summarizer_awaken_count=2,
                decider_awaken_count=3,
                last_triggered_threshold=33,
            )
            repository.persist(conversation)

            agent = Agent(
                name="demo",
                model_config=ModelConfig(model="demo", base_url="https://example.com", api_key="key"),
                init_messages=NEW_INIT_MESSAGES,
                tools=[],
                conversation_repository=repository,
            )
            agent.start_conversation()

        self.assertEqual(agent._conversation.summarizer_awaken_count, 2)
        self.assertEqual(agent._conversation.decider_awaken_count, 3)
        self.assertEqual(agent._conversation.last_triggered_threshold, 33)


if __name__ == "__main__":
    unittest.main()
