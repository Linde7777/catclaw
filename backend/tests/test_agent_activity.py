import unittest

from src.core.agent_activity import AgentActivityEmitter, AgentIdentity


class AgentActivityEmitterTests(unittest.TestCase):
    def test_emits_identity_then_scoped_events(self) -> None:
        events: list[dict[str, object]] = []
        activity = AgentActivityEmitter(
            identity=AgentIdentity(
                agent_id="summarizer:main.json:1",
                name="summarizer / 1",
                kind="summarizer",
            ),
            emit=events.append,
        )

        activity.emit_started()
        activity.emit_event({"type": "assistant.message.started", "messageId": "message-1"})
        activity.emit_completed()

        self.assertEqual(
            events,
            [
                {
                    "type": "agent.activity.started",
                    "agentId": "summarizer:main.json:1",
                    "agentName": "summarizer / 1",
                    "agentKind": "summarizer",
                },
                {
                    "type": "assistant.message.started",
                    "messageId": "message-1",
                    "agentId": "summarizer:main.json:1",
                },
                {
                    "type": "agent.activity.completed",
                    "agentId": "summarizer:main.json:1",
                },
            ],
        )

    def test_rejects_event_with_a_different_identity_source(self) -> None:
        activity = AgentActivityEmitter(
            identity=AgentIdentity(agent_id="main", name="main", kind="main"),
            emit=lambda event: None,
        )

        with self.assertRaisesRegex(ValueError, "不能自行指定 agentId"):
            activity.emit_event({"type": "agent.became.busy", "agentId": "other"})


if __name__ == "__main__":
    unittest.main()
