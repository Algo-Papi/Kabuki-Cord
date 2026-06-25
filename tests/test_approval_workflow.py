from __future__ import annotations

import json
import sys
import unittest
from datetime import datetime, timezone
from pathlib import Path
from tempfile import TemporaryDirectory
from types import SimpleNamespace

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))

from nhi_zues.approval_workflow import (
    approval_source_messages,
    clear_approval_queue,
    discard_approval,
    last_approval_source_message,
    update_approval_draft,
)
from nhi_zues.approvals import ApprovalQueue
from nhi_zues.memory import ConversationMemory
from nhi_zues.models import MessageRecord


class ApprovalWorkflowTests(unittest.TestCase):
    def test_update_discard_and_clear_are_logged_and_persisted(self) -> None:
        with TemporaryDirectory() as tmp:
            root = Path(tmp)
            config = SimpleNamespace(state_dir=root / ".state")
            source = _message("source-1")
            queue = ApprovalQueue(config.state_dir / "approvals.json")
            first = queue.add(
                server_id="server-1",
                channel_id="channel-1",
                character_name="NHI Zues",
                engagement_type="reply",
                reason="first",
                draft="old draft",
                source_messages=[source],
            )
            second = queue.add(
                server_id="server-1",
                channel_id="channel-1",
                character_name="NHI Zues",
                engagement_type="reply",
                reason="second",
                draft="second draft",
                source_messages=[_message("source-2")],
            )

            updated = update_approval_draft(config, first.approval_id, "new draft")
            self.assertEqual("new draft", updated.draft)

            self.assertTrue(discard_approval(config, first.approval_id))
            self.assertEqual(1, clear_approval_queue(config))

            self.assertEqual([], ApprovalQueue(config.state_dir / "approvals.json").list())
            events = json.loads((config.state_dir / "events.json").read_text(encoding="utf-8"))
            event_types = [event["event_type"] for event in events["items"]]
            self.assertIn("approval_updated", event_types)
            self.assertIn("approval_discarded", event_types)
            self.assertIn("approvals_cleared", event_types)
            discarded = json.loads(
                (config.state_dir / "discarded_approvals.json").read_text(encoding="utf-8")
            )
            self.assertEqual(2, len(discarded["items"]))
            self.assertEqual(second.source_message_ids, tuple(discarded["items"][-1]["source_message_ids"]))

    def test_source_message_helpers_read_memory_snapshot(self) -> None:
        with TemporaryDirectory() as tmp:
            root = Path(tmp)
            config = SimpleNamespace(state_dir=root / ".state")
            remembered = _message("chat-messages-1-200", text="remember this line")
            missing = _message("chat-messages-1-201", text="not stored")
            memory = ConversationMemory(config.state_dir / "memory.json")
            memory.ingest("channel-1", [remembered])
            memory.save()
            item = ApprovalQueue(config.state_dir / "approvals.json").add(
                server_id="server-1",
                channel_id="channel-1",
                character_name="NHI Zues",
                engagement_type="reply",
                reason="manual response",
                draft="draft",
                source_messages=[remembered, missing],
            )

            self.assertEqual(
                ["chat-messages-1-200"],
                [message.message_id for message in approval_source_messages(config, item)],
            )
            self.assertEqual(
                "remember this line",
                last_approval_source_message(config, item)["text"],
            )


def _message(message_id: str, *, text: str = "source text") -> MessageRecord:
    return MessageRecord(
        server_id="server-1",
        channel_id="channel-1",
        message_id=message_id,
        author="Rook",
        author_id="123",
        text=text,
        observed_at=datetime(2026, 6, 23, tzinfo=timezone.utc),
    )


if __name__ == "__main__":
    unittest.main()
