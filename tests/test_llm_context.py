from __future__ import annotations

import sys
import unittest
from datetime import datetime, timezone
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))

from nhi_zues.character import CharacterCard
from nhi_zues.llm import _draft_quality_issues, _format_own_post_strategy, _format_user_recent_arcs
from nhi_zues.models import MessageRecord


def record(message_id: int, author: str, author_id: str | None, text: str) -> MessageRecord:
    return MessageRecord(
        server_id="server",
        channel_id="channel",
        message_id=f"chat-messages-123-{message_id}",
        author=author,
        author_id=author_id,
        text=text,
        observed_at=datetime(2026, 6, 24, tzinfo=timezone.utc),
    )


class LlmContextTests(unittest.TestCase):
    def test_user_recent_arc_tracks_source_user_without_character_echo(self) -> None:
        character = CharacterCard(
            name="NHI Zues",
            system_prompt="",
            style_rules=(),
            engagement_rules=(),
            response_moves=(),
            voice_examples=(),
            avoid_examples=(),
            aliases=("nhi zues", "zues"),
            trigger_keywords=(),
        )
        context = [
            record(100, "EB3", "42", "first claim about witness timing"),
            record(101, "NHI Zues", "self", "old reply that should not become EB3 continuity"),
            record(102, "Other", "77", "side chatter"),
            record(103, "EB3", "42", "newer claim about the same footage"),
        ]

        arc = _format_user_recent_arcs(context, [context[-1]], character)

        self.assertIn("EB3:", arc)
        self.assertIn("first claim about witness timing", arc)
        self.assertIn("newer claim about the same footage", arc)
        self.assertNotIn("old reply that should not become EB3 continuity", arc)
        self.assertNotIn("Other:", arc)

    def test_own_post_strategy_tracks_character_direction_without_reply_targeting(self) -> None:
        character = CharacterCard(
            name="NHI Zues",
            system_prompt="",
            style_rules=(),
            engagement_rules=(),
            response_moves=(),
            voice_examples=(),
            avoid_examples=(),
            aliases=("nhi zues", "zues"),
            trigger_keywords=(),
        )
        context = [
            record(100, "Rook", "42", "first outside claim"),
            record(
                101,
                "NHI ZuesOnline",
                "self",
                "i already said the original source file timestamp matters more than the edited story",
            ),
            record(102, "Other", "77", "newer side chatter"),
        ]

        strategy = _format_own_post_strategy(context, character)
        issues = _draft_quality_issues(
            "the original source file timestamp matters more than the edited story here",
            [
                "i already said the original source file timestamp matters more than the edited story",
            ],
        )

        self.assertIn("own recent posts", strategy)
        self.assertIn("original source file timestamp", strategy)
        self.assertIn("repeats the same point", " ".join(issues))


if __name__ == "__main__":
    unittest.main()
