from __future__ import annotations

import json
import unittest
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
    def test_legacy_unverified_rows_do_not_block_retry(self) -> None:
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


if __name__ == "__main__":
    unittest.main()
