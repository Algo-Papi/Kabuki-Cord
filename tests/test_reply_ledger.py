from __future__ import annotations

from datetime import datetime, timedelta, timezone
from tempfile import TemporaryDirectory
from pathlib import Path
import unittest

from nhi_zues.reply_ledger import ReplyLedger, SentReply


class ReplyLedgerTests(unittest.TestCase):
    def test_latest_and_recent_for_channel(self) -> None:
        now = datetime(2026, 6, 23, 12, 0, tzinfo=timezone.utc)
        with TemporaryDirectory() as temp_dir:
            ledger = ReplyLedger(Path(temp_dir) / "sent_replies.json")
            ledger._items = [
                _reply("old", "channel-1", now - timedelta(hours=2)),
                _reply("other", "channel-2", now - timedelta(minutes=5)),
                _reply("new", "channel-1", now - timedelta(minutes=10)),
            ]

            latest = ledger.latest_for_channel(channel_id="channel-1")
            recent = ledger.recent_for_channel(
                channel_id="channel-1",
                window_seconds=3600,
                now=now,
            )

        self.assertIsNotNone(latest)
        self.assertEqual("new", latest.reply_id)
        self.assertEqual(["new"], [item.reply_id for item in recent])

    def test_record_tracks_own_message_id_and_text(self) -> None:
        with TemporaryDirectory() as temp_dir:
            ledger = ReplyLedger(Path(temp_dir) / "sent_replies.json")

            ledger.record(
                server_id="server-1",
                channel_id="channel-1",
                mode="auto",
                draft="<@123> I already said the archive chain is the weak part.",
                source_message_ids=("source-1",),
                message_id="posted-1",
            )
            reloaded = ReplyLedger(Path(temp_dir) / "sent_replies.json")

            self.assertEqual({"posted-1"}, reloaded.own_message_ids_for_channel(channel_id="channel-1"))
            self.assertEqual(
                {"i already said the archive chain is the weak part"},
                reloaded.own_texts_for_channel(channel_id="channel-1"),
            )


def _reply(reply_id: str, channel_id: str, created_at: datetime) -> SentReply:
    return SentReply(
        reply_id=reply_id,
        created_at=created_at.isoformat(),
        server_id="server-1",
        channel_id=channel_id,
        mode="auto",
        draft_hash="draft",
        source_message_ids=("source",),
    )


if __name__ == "__main__":
    unittest.main()
