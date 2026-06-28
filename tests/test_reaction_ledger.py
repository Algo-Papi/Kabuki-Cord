from __future__ import annotations

import json
import unittest
from datetime import datetime, timezone
from pathlib import Path
from tempfile import TemporaryDirectory

from nhi_zues.models import MessageRecord
from nhi_zues.reaction_ledger import ReactionLedger


def message() -> MessageRecord:
    return MessageRecord(
        server_id="server-1",
        channel_id="channel-1",
        message_id="message-1",
        author="Rook",
        author_id="user-1",
        text="that is cursed lmao",
    )


class ReactionLedgerTests(unittest.TestCase):
    def test_unverified_rows_do_not_count_as_verified_reactions(self) -> None:
        with TemporaryDirectory() as tmp:
            ledger_file = Path(tmp) / "reactions.json"
            ledger_file.write_text(
                json.dumps(
                    {
                        "items": [
                            {
                                "created_at": "2026-06-24T12:00:00+00:00",
                                "server_id": "server-1",
                                "channel_id": "channel-1",
                                "message_id": "message-1",
                                "emoji": "😂",
                                "reason": "old optimistic click",
                                "author": "Rook",
                            }
                        ]
                    }
                ),
                encoding="utf-8",
            )

            ledger = ReactionLedger(ledger_file)

            self.assertFalse(
                ledger.has_reacted_to_message(channel_id="channel-1", message_id="message-1")
            )
            self.assertFalse(
                ledger.has_reacted(channel_id="channel-1", message_id="message-1", emoji="😂")
            )
            self.assertTrue(
                ledger.has_attempted_to_message(channel_id="channel-1", message_id="message-1")
            )

    def test_verified_record_upgrades_legacy_row(self) -> None:
        with TemporaryDirectory() as tmp:
            ledger_file = Path(tmp) / "reactions.json"
            ledger_file.write_text(
                json.dumps(
                    {
                        "items": [
                            {
                                "created_at": "2026-06-24T12:00:00+00:00",
                                "server_id": "server-1",
                                "channel_id": "channel-1",
                                "message_id": "message-1",
                                "emoji": "😂",
                                "reason": "old optimistic click",
                                "author": "Rook",
                            }
                        ]
                    }
                ),
                encoding="utf-8",
            )
            ledger = ReactionLedger(ledger_file)

            ledger.record(
                server_id="server-1",
                message=message(),
                emoji="😂",
                reason="verified in Discord UI",
            )

            reloaded = ReactionLedger(ledger_file)
            self.assertTrue(
                reloaded.has_reacted_to_message(channel_id="channel-1", message_id="message-1")
            )
            self.assertTrue(
                reloaded.has_reacted(channel_id="channel-1", message_id="message-1", emoji="😂")
            )

    def test_last_reaction_at_uses_latest_verified_channel_record(self) -> None:
        with TemporaryDirectory() as tmp:
            ledger_file = Path(tmp) / "reactions.json"
            ledger_file.write_text(
                json.dumps(
                    {
                        "items": [
                            {
                                "created_at": "2026-06-24T12:00:00+00:00",
                                "server_id": "server-1",
                                "channel_id": "channel-1",
                                "message_id": "old",
                                "emoji": "\U0001f602",
                                "reason": "old",
                                "author": "Rook",
                                "verified": True,
                            },
                            {
                                "created_at": "2026-06-24T12:10:00+00:00",
                                "server_id": "server-1",
                                "channel_id": "channel-1",
                                "message_id": "new",
                                "emoji": "\U0001f602",
                                "reason": "new",
                                "author": "Rook",
                                "verified": True,
                            },
                            {
                                "created_at": "2026-06-24T12:30:00+00:00",
                                "server_id": "server-1",
                                "channel_id": "channel-2",
                                "message_id": "other",
                                "emoji": "\U0001f602",
                                "reason": "other channel",
                                "author": "Rook",
                                "verified": True,
                            },
                        ]
                    }
                ),
                encoding="utf-8",
            )

            latest = ReactionLedger(ledger_file).last_reaction_at(channel_id="channel-1")

            self.assertEqual(datetime(2026, 6, 24, 12, 10, tzinfo=timezone.utc), latest)

    def test_last_attempt_at_uses_unverified_records(self) -> None:
        with TemporaryDirectory() as tmp:
            ledger_file = Path(tmp) / "reactions.json"
            ledger_file.write_text(
                json.dumps(
                    {
                        "items": [
                            {
                                "created_at": "2026-06-24T12:30:00+00:00",
                                "server_id": "server-1",
                                "channel_id": "channel-1",
                                "message_id": "failed",
                                "emoji": "\U0001f44d",
                                "reason": "unverified",
                                "author": "Rook",
                                "verified": False,
                            }
                        ]
                    }
                ),
                encoding="utf-8",
            )

            ledger = ReactionLedger(ledger_file)

            self.assertIsNone(ledger.last_reaction_at(channel_id="channel-1"))
            self.assertEqual(
                datetime(2026, 6, 24, 12, 30, tzinfo=timezone.utc),
                ledger.last_attempt_at(channel_id="channel-1"),
            )


if __name__ == "__main__":
    unittest.main()
