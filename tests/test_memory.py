from __future__ import annotations

import sys
import unittest
from datetime import datetime, timezone
from pathlib import Path
from tempfile import TemporaryDirectory

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))

from nhi_zues.memory import ConversationMemory
from nhi_zues.models import MessageRecord


def record(message_id: int, author: str, author_id: str | None, text: str) -> MessageRecord:
    return MessageRecord(
        server_id="server",
        channel_id="channel",
        message_id=f"chat-messages-123-{message_id}",
        author=author,
        author_id=author_id,
        text=text,
        observed_at=datetime(2026, 6, 23, tzinfo=timezone.utc),
    )


class ConversationMemoryTests(unittest.TestCase):
    def test_seen_message_reconciles_corrected_author_and_text(self) -> None:
        with TemporaryDirectory() as tmp:
            memory = ConversationMemory(Path(tmp) / "memory.json", max_messages_per_channel=10)
            memory.ingest("channel", [record(100, "Wrong User", "111", "quoted reply text")])
            memory.ingest("channel", [record(100, "Right User", "222", "actual message text")])

            [message] = memory.context("channel", limit=1)
            self.assertEqual(message.author, "Right User")
            self.assertEqual(message.author_id, "222")
            self.assertEqual(message.text, "actual message text")

    def test_seen_but_evicted_message_is_rehydrated_by_backfill(self) -> None:
        with TemporaryDirectory() as tmp:
            memory = ConversationMemory(Path(tmp) / "memory.json", max_messages_per_channel=2)
            memory.ingest("channel", [record(100, "A", "1", "first")])
            memory.ingest("channel", [record(101, "B", "2", "second")])
            memory.ingest("channel", [record(102, "C", "3", "third")])

            self.assertNotIn("first", [message.text for message in memory.context("channel", limit=3)])
            memory.ingest("channel", [record(100, "A", "1", "first")])

            self.assertIn("first", [message.text for message in memory.context("channel", limit=3)])


if __name__ == "__main__":
    unittest.main()
