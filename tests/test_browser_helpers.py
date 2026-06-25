from __future__ import annotations

import sys
import unittest
from datetime import datetime, timezone
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))

from nhi_zues.browser import (
    _discord_message_token,
    _draft_still_in_composer,
    _emoji_search_query,
    _message_sort_value,
    _normalized_message_text,
    _typing_duration,
    discord_login_blocker_message,
)
from nhi_zues.models import MessageRecord


def record(message_id: str) -> MessageRecord:
    return MessageRecord(
        server_id="server-1",
        channel_id="channel-1",
        message_id=message_id,
        author="Rook",
        author_id="user-1",
        text="hello",
        observed_at=datetime(2026, 6, 25, tzinfo=timezone.utc),
    )


class BrowserHelperTests(unittest.TestCase):
    def test_typing_duration_clamps_estimate_between_bounds(self) -> None:
        self.assertEqual(
            1.5,
            _typing_duration("hi", min_seconds=1.5, max_seconds=10.0, chars_per_second=10.0),
        )
        self.assertEqual(
            2.0,
            _typing_duration("x" * 100, min_seconds=0.0, max_seconds=2.0, chars_per_second=10.0),
        )
        self.assertEqual(
            0.1,
            _typing_duration("   ", min_seconds=0.0, max_seconds=5.0, chars_per_second=10.0),
        )

    def test_typing_duration_normalizes_invalidish_bounds_and_speed(self) -> None:
        self.assertEqual(
            0.0,
            _typing_duration("", min_seconds=-1.0, max_seconds=-5.0, chars_per_second=0.0),
        )
        self.assertEqual(
            3.0,
            _typing_duration("abc", min_seconds=0.0, max_seconds=10.0, chars_per_second=-4.0),
        )

    def test_normalized_message_text_removes_invisible_markers_and_collapses_whitespace(self) -> None:
        self.assertEqual(
            "alpha beta gamma",
            _normalized_message_text("\ufeff alpha \u200b beta\n\tgamma  "),
        )
        self.assertEqual("", _normalized_message_text(None))  # type: ignore[arg-type]

    def test_draft_still_in_composer_matches_normalized_text_in_either_direction(self) -> None:
        self.assertTrue(_draft_still_in_composer("alpha beta", "\ufeff alpha \u200b beta gamma"))
        self.assertTrue(_draft_still_in_composer("alpha beta gamma", "alpha\nbeta"))
        self.assertFalse(_draft_still_in_composer("", "alpha"))
        self.assertFalse(_draft_still_in_composer("alpha", ""))
        self.assertFalse(_draft_still_in_composer("alpha", "beta"))

    def test_message_sort_value_uses_trailing_numeric_token(self) -> None:
        self.assertEqual(42, _message_sort_value(record("chat-messages-111-42")))
        self.assertEqual(98765, _message_sort_value(record("98765")))
        self.assertEqual(0, _message_sort_value(record("chat-messages-111-alpha")))
        self.assertEqual(0, _message_sort_value(record("manual-alpha")))

    def test_discord_message_token_strips_chat_message_prefix_only(self) -> None:
        self.assertEqual("42", _discord_message_token(" chat-messages-111-42 "))
        self.assertEqual("message-42", _discord_message_token(" message-42 "))
        self.assertEqual("", _discord_message_token(""))
        self.assertEqual("", _discord_message_token(None))  # type: ignore[arg-type]

    def test_emoji_search_query_maps_common_reaction_emoji(self) -> None:
        self.assertEqual("joy", _emoji_search_query("\U0001f602"))
        self.assertEqual("rofl", _emoji_search_query("\U0001f923"))
        self.assertEqual("thumbsup", _emoji_search_query("\U0001f44d"))
        self.assertEqual("pray", _emoji_search_query("\U0001f64f"))
        self.assertEqual("eyes", _emoji_search_query("\U0001f440"))
        self.assertEqual("heart", _emoji_search_query("\u2764\ufe0f"))
        self.assertEqual("heart", _emoji_search_query("\u2764"))

    def test_emoji_search_query_falls_back_to_trimmed_value_or_joy(self) -> None:
        self.assertEqual("sparkles", _emoji_search_query("  sparkles  "))
        self.assertEqual("joy", _emoji_search_query(""))
        self.assertEqual("joy", _emoji_search_query(None))  # type: ignore[arg-type]

    def test_discord_login_blocker_message_uses_highest_priority_state(self) -> None:
        message = discord_login_blocker_message(
            {
                "password_reset": True,
                "account_action_required": True,
                "human_verification": True,
                "two_factor": True,
                "login_form_visible": True,
            }
        )

        self.assertIn("password reset", message)
        self.assertIn("No message was sent.", message)

    def test_discord_login_blocker_message_describes_each_login_blocker(self) -> None:
        cases = [
            ({"account_action_required": True}, "account verification"),
            ({"human_verification": True}, "human verification"),
            ({"two_factor": True}, "authentication code"),
            ({"login_form_visible": True}, "login screen"),
            ({}, "not signed in"),
        ]

        for state, expected_text in cases:
            with self.subTest(state=state):
                message = discord_login_blocker_message(state)
                self.assertIn(expected_text, message)
                self.assertIn("No message was sent.", message)


if __name__ == "__main__":
    unittest.main()
