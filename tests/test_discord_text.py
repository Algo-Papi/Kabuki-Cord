from __future__ import annotations

import sys
import unittest
from datetime import datetime, timezone
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))

from nhi_zues.discord_text import clean_discord_display_name, sanitize_outgoing_draft
from nhi_zues.gui import _draft_with_reply_mention, _reply_mention_prefix
from nhi_zues.llm import _format_message_lines
from nhi_zues.models import MessageRecord
from nhi_zues.voice_guard import draft_quality_issues


BAD_AUTHOR = "< Obvs.TheVillain >\xa0[EVIL],\xa0Server Tag: EVILEVILUntouchables (boosters)"
BAD_DRAFT = (
    "@< Obvs.TheVillain >\xa0[EVIL],\xa0Server Tag: EVILEVILUntouchables (boosters) "
    "Server Tag: EVILEVILUntouchables (boosters) i push back a bit on fruit first."
)


class DiscordTextTests(unittest.TestCase):
    def test_display_name_drops_role_and_server_tag_metadata(self) -> None:
        self.assertEqual("Obvs.TheVillain", clean_discord_display_name(BAD_AUTHOR))

    def test_outgoing_draft_strips_metadata_mention_prefix(self) -> None:
        self.assertEqual(
            "i push back a bit on fruit first.",
            sanitize_outgoing_draft(BAD_DRAFT),
        )

    def test_textual_fallback_mentions_are_disabled_without_author_id(self) -> None:
        self.assertEqual("", _reply_mention_prefix(BAD_AUTHOR, None))

    def test_real_discord_ids_still_create_actual_mentions(self) -> None:
        self.assertEqual("<@12345>", _reply_mention_prefix(BAD_AUTHOR, "12345"))

    def test_draft_with_reply_mention_never_prepends_scraped_metadata(self) -> None:
        source = MessageRecord(
            server_id="server",
            channel_id="channel",
            message_id="chat-messages-1-1",
            author=BAD_AUTHOR,
            author_id=None,
            text="I'll usually start with fruit",
            observed_at=datetime(2026, 6, 23, tzinfo=timezone.utc),
        )

        self.assertEqual("i push back a bit on fruit first.", _draft_with_reply_mention(BAD_DRAFT, [source]))

    def test_draft_with_reply_mention_replaces_clean_textual_prefix_with_real_mention(self) -> None:
        source = MessageRecord(
            server_id="server",
            channel_id="channel",
            message_id="chat-messages-1-1",
            author=BAD_AUTHOR,
            author_id="12345",
            text="I'll usually start with fruit",
            observed_at=datetime(2026, 6, 23, tzinfo=timezone.utc),
        )

        self.assertEqual(
            "<@12345> i push back a bit on fruit first.",
            _draft_with_reply_mention("@Obvs.TheVillain i push back a bit on fruit first.", [source]),
        )

    def test_draft_with_reply_mention_does_not_double_prefix_existing_discord_mention(self) -> None:
        source = MessageRecord(
            server_id="server",
            channel_id="channel",
            message_id="chat-messages-1-1",
            author="Rook",
            author_id="12345",
            text="I'll usually start with fruit",
            observed_at=datetime(2026, 6, 23, tzinfo=timezone.utc),
        )

        self.assertEqual(
            "<@!12345> i push back a bit on fruit first.",
            _draft_with_reply_mention("<@!12345> i push back a bit on fruit first.", [source]),
        )

    def test_prompt_message_lines_hide_scraped_metadata(self) -> None:
        line = _format_message_lines(
            [
                MessageRecord(
                    server_id="server",
                    channel_id="channel",
                    message_id="chat-messages-1-1",
                    author=BAD_AUTHOR,
                    author_id=None,
                    text=BAD_DRAFT,
                    observed_at=datetime(2026, 6, 23, tzinfo=timezone.utc),
                )
            ]
        )

        self.assertEqual("- Obvs.TheVillain: i push back a bit on fruit first.", line)

    def test_quality_gate_flags_raw_server_tag_metadata(self) -> None:
        issues = draft_quality_issues(BAD_DRAFT)

        self.assertTrue(any("metadata" in issue for issue in issues))


if __name__ == "__main__":
    unittest.main()
