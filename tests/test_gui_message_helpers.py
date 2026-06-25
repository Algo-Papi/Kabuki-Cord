from __future__ import annotations

import sys
import unittest
from datetime import datetime, timezone
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))

from nhi_zues.gui import (
    _manual_source_messages,
    _message_preview,
    _message_record_user_key,
    _message_row_sort_key,
    _message_user_key,
    _sorted_message_rows,
)
from nhi_zues.models import MessageRecord


BAD_AUTHOR = "< Obvs.TheVillain >\xa0[EVIL],\xa0Server Tag: EVILEVILUntouchables (boosters)"


def record(message_id: str, author: str, author_id: str | None, text: str = "hello") -> MessageRecord:
    return MessageRecord(
        server_id="server-1",
        channel_id="channel-1",
        message_id=message_id,
        author=author,
        author_id=author_id,
        text=text,
        observed_at=datetime(2026, 6, 23, tzinfo=timezone.utc),
    )


class GuiMessageHelperTests(unittest.TestCase):
    def test_message_rows_sort_by_numeric_discord_tail_then_full_id(self) -> None:
        rows = [
            {"message_id": "chat-messages-1-10"},
            {"message_id": "manual-alpha"},
            {"message_id": "chat-messages-1-2"},
            {"message_id": "chat-messages-1-1"},
        ]

        self.assertEqual(
            ["manual-alpha", "chat-messages-1-1", "chat-messages-1-2", "chat-messages-1-10"],
            [row["message_id"] for row in _sorted_message_rows(rows)],
        )
        self.assertEqual((10, "chat-messages-1-10"), _message_row_sort_key(rows[0]))

    def test_message_preview_cleans_metadata_and_prefers_discord_user_key(self) -> None:
        preview = _message_preview(
            {
                "server_id": "server-1",
                "channel_id": "channel-1",
                "message_id": "chat-messages-1-2",
                "author": BAD_AUTHOR,
                "author_id": "12345",
                "text": "Server Tag: EVILEVILUntouchables (boosters) i push back a bit.",
                "observed_at": "2026-06-23T12:00:00+00:00",
            }
        )

        self.assertEqual("Obvs.TheVillain", preview["author"])
        self.assertEqual("discord:12345", preview["user_key"])
        self.assertEqual("i push back a bit.", preview["text"])

    def test_message_user_key_falls_back_to_clean_normalized_display_name(self) -> None:
        row = {
            "author": "  < Obvs.TheVillain >\xa0[EVIL],\xa0Server Tag: EVILEVILUntouchables (boosters)  ",
            "author_id": None,
        }

        self.assertEqual("name:obvs.thevillain", _message_user_key(row))
        self.assertEqual("discord:12345", _message_user_key({**row, "author_id": "12345"}))

    def test_message_record_user_key_matches_row_user_key_rules(self) -> None:
        self.assertEqual("name:obvs.thevillain", _message_record_user_key(record("1", BAD_AUTHOR, None)))
        self.assertEqual("discord:12345", _message_record_user_key(record("1", BAD_AUTHOR, "12345")))

    def test_manual_source_messages_selects_last_two_target_user_messages_chronologically(self) -> None:
        context = [
            record("1", "Rook", "user-1", "oldest"),
            record("2", "Muse", "user-2", "other user"),
            record("3", "Rook", "user-1", "middle"),
            record("4", "Rook", "user-1", "newest"),
        ]

        selected = _manual_source_messages(context, "discord:user-1")

        self.assertEqual(["3", "4"], [message.message_id for message in selected])

    def test_manual_source_messages_selected_message_id_overrides_target_user(self) -> None:
        context = [
            record("1", "Rook", "user-1"),
            record("2", "Muse", "user-2"),
        ]

        selected = _manual_source_messages(context, "discord:user-1", target_message_id="2")

        self.assertEqual(["2"], [message.message_id for message in selected])


if __name__ == "__main__":
    unittest.main()
