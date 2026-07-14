from __future__ import annotations

import sys
import unittest
from datetime import datetime, timezone
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))

from nhi_zues.character import CharacterCard
from nhi_zues.llm import (
    _draft_quality_issues,
    _focus_issue,
    _focus_messages_for_reply,
    _format_own_post_strategy,
    _format_user_recent_arcs,
)
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


def character() -> CharacterCard:
    return CharacterCard(
        name="NHI Zues",
        system_prompt="",
        style_rules=(),
        engagement_rules=(),
        response_moves=(),
        voice_examples=(),
        avoid_examples=(),
        aliases=("nhi zues", "zues"),
        trigger_keywords=("ufo", "uap", "alien", "disclosure", "ai"),
    )


class LlmContextTests(unittest.TestCase):
    def test_user_recent_arc_tracks_source_user_without_character_echo(self) -> None:
        card = character()
        context = [
            record(100, "EB3", "42", "first claim about witness timing"),
            record(101, "NHI Zues", "self", "old reply that should not become EB3 continuity"),
            record(102, "Other", "77", "side chatter"),
            record(103, "EB3", "42", "newer claim about the same footage"),
        ]

        arc = _format_user_recent_arcs(context, [context[-1]], card)

        self.assertIn("EB3:", arc)
        self.assertIn("first claim about witness timing", arc)
        self.assertIn("newer claim about the same footage", arc)
        self.assertNotIn("old reply that should not become EB3 continuity", arc)
        self.assertNotIn("Other:", arc)

    def test_own_post_strategy_tracks_character_direction_without_reply_targeting(self) -> None:
        card = character()
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

        strategy = _format_own_post_strategy(context, card)
        issues = _draft_quality_issues(
            "the original source file timestamp matters more than the edited story here",
            [
                "i already said the original source file timestamp matters more than the edited story",
            ],
        )

        self.assertIn("own recent posts", strategy)
        self.assertIn("original source file timestamp", strategy)
        self.assertIn("repeats the same point", " ".join(issues))

    def test_conversation_focus_blocks_short_banter_batches(self) -> None:
        card = character()
        messages = [
            record(1, "Doggo", "1", "Ill try that tmr"),
            record(2, "WordleVerified AppAPP", "app", "Doggo and Bear were playing"),
            record(3, "Bear", "2", "I give up"),
            record(4, "srin", "3", "cute"),
            record(5, "Bear", "2", "Hm"),
            record(6, "Bear", "2", "Yes thanks a banana bunch"),
        ]

        focus = _focus_messages_for_reply(
            messages,
            messages,
            card,
            engagement_type="conversation",
        )

        self.assertNotIn("WordleVerified", [message.author for message in focus])
        self.assertIn("too thin", _focus_issue(focus, card, engagement_type="conversation"))

    def test_conversation_focus_allows_clear_recent_claim(self) -> None:
        card = character()
        messages = [
            record(1, "TestSubject", "1", "We are not required to have front license plates where I am."),
            record(2, "TestSubject", "1", "This would be interesting to find out with a FOIA request."),
        ]

        focus = _focus_messages_for_reply(
            messages,
            messages,
            card,
            engagement_type="conversation",
        )

        self.assertEqual(
            ["chat-messages-123-1", "chat-messages-123-2"],
            [message.message_id for message in focus],
        )
        self.assertEqual("", _focus_issue(focus, card, engagement_type="conversation"))

    def test_conversation_focus_blocks_joke_banter_as_reply_target(self) -> None:
        card = character()
        messages = [
            record(1, "QuietRound", "1", "Hes the french canadian jesus"),
            record(2, "QuietRound", "1", "And he eat"),
            record(3, "Kaiser", "2", "Canadian Jesus wears cargo socks"),
            record(4, "QuietRound", "1", "Ur hair looks kim"),
        ]

        focus = _focus_messages_for_reply(
            messages,
            messages,
            card,
            engagement_type="conversation",
        )

        self.assertIn("too thin", _focus_issue(focus, card, engagement_type="conversation"))

    def test_short_trigger_keyword_does_not_match_inside_words(self) -> None:
        card = character()
        messages = [
            record(1, "Kaiser", "2", "Canadian Jesus wears cargo socks"),
        ]

        focus = _focus_messages_for_reply(
            messages,
            messages,
            card,
            engagement_type="conversation",
        )

        self.assertIn("too thin", _focus_issue(focus, card, engagement_type="conversation"))

    def test_one_word_question_fragment_is_not_reply_worthy(self) -> None:
        card = character()
        messages = [
            record(1, "Rook", "1", "..... what"),
        ]

        focus = _focus_messages_for_reply(
            messages,
            messages,
            card,
            engagement_type="conversation",
        )

        self.assertIn("too thin", _focus_issue(focus, card, engagement_type="conversation"))

    def test_ai_bot_suspicion_thread_is_not_auto_reply_target(self) -> None:
        card = character()
        messages = [
            record(1, "Rook", "1", "if you think it might be ai, look at posting behavior not grammar"),
        ]

        focus = _focus_messages_for_reply(
            messages,
            messages,
            card,
            engagement_type="conversation",
        )

        self.assertIn("AI/bot-suspicion", _focus_issue(focus, card, engagement_type="conversation"))

    def test_conversation_focus_blocks_casual_chatter_as_reply_target(self) -> None:
        card = character()
        messages = [
            record(1, "Leviathan", "1", "My favorite soda"),
            record(2, "Morded", "2", "brother"),
            record(3, "Leviathan", "1", "My lil cousin was watching that on his iPad"),
            record(4, "Leviathan", "1", "Thats facts"),
        ]

        focus = _focus_messages_for_reply(
            messages,
            messages,
            card,
            engagement_type="conversation",
        )

        self.assertIn("too thin", _focus_issue(focus, card, engagement_type="conversation"))

    def test_conversation_focus_allows_question_without_question_mark(self) -> None:
        card = character()
        messages = [
            record(1, "Variable", "1", "I hate physics"),
            record(2, "Variable", "1", "why cant we have conclusive answers"),
            record(3, "Variable", "1", "(without real life empirical tests)"),
        ]

        focus = _focus_messages_for_reply(
            messages,
            messages,
            card,
            engagement_type="conversation",
        )

        self.assertEqual("", _focus_issue(focus, card, engagement_type="conversation"))

    def test_quality_gate_rejects_unrelated_persona_detail(self) -> None:
        issues = _draft_quality_issues(
            "i work overnight shifts so i know how that goes",
            [],
            [record(1, "Rook", "42", "What do you think about that old footage?")],
        )

        self.assertIn("unrelated personal biography", " ".join(issues))


if __name__ == "__main__":
    unittest.main()
