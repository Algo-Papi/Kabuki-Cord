from __future__ import annotations

import unittest
from datetime import datetime, timezone

from nhi_zues.character import CharacterCard
from nhi_zues.models import MessageRecord
from nhi_zues.relevance import assess_reply_candidate, term_in_text


def card(*, triggers: tuple[str, ...] = ("coffee",)) -> CharacterCard:
    return CharacterCard(
        name="Test Character",
        system_prompt="",
        style_rules=(),
        engagement_rules=(),
        response_moves=(),
        voice_examples=(),
        avoid_examples=(),
        aliases=("zyn",),
        trigger_keywords=triggers,
    )


def message(
    message_id: int,
    text: str,
    *,
    author: str = "Rook",
    author_id: str | None = "1",
) -> MessageRecord:
    return MessageRecord(
        server_id="server",
        channel_id="channel",
        message_id=f"chat-messages-123-{message_id}",
        author=author,
        author_id=author_id,
        text=text,
        observed_at=datetime(2026, 7, 12, tzinfo=timezone.utc),
    )


def assess(
    messages: list[MessageRecord],
    *,
    context: list[MessageRecord] | None = None,
    character: CharacterCard | None = None,
    conversation: bool = True,
):
    return assess_reply_candidate(
        new_messages=messages,
        context=context if context is not None else messages,
        character=character or card(),
        conversation_reply_enabled=conversation,
    )


class RelevanceAssessmentTests(unittest.TestCase):
    def test_compact_opinions_are_reply_worthy(self) -> None:
        for text in (
            "that album is painfully overrated",
            "the remaster sounds worse actually",
            "this episode needed fewer guests",
        ):
            with self.subTest(text=text):
                result = assess([message(1, text)])
                self.assertEqual("reply", result.outcome)
                self.assertEqual("compact_opinion", result.reason_code)
                self.assertGreaterEqual(result.total_score, 6)

    def test_plain_declaration_and_low_signal_chatter_stay_blocked(self) -> None:
        for text in (
            "Canadian Jesus wears cargo socks",
            "my favorite soda",
            "I give up",
            "cute",
            "..... what",
        ):
            with self.subTest(text=text):
                result = assess([message(1, text)])
                self.assertEqual("skip", result.outcome)

    def test_question_without_question_mark_is_reply_worthy(self) -> None:
        result = assess([message(1, "why cant we have conclusive answers")])

        self.assertEqual("reply", result.outcome)
        self.assertEqual("specific_question", result.reason_code)

    def test_direct_question_passes_but_alias_only_defers(self) -> None:
        direct = assess([message(1, "zyn thoughts?")])
        alias_only = assess([message(2, "zyn")])

        self.assertEqual("reply", direct.outcome)
        self.assertEqual("direct", direct.engagement_type)
        self.assertEqual("direct_cue_with_substance", direct.reason_code)
        self.assertEqual("defer", alias_only.outcome)
        self.assertEqual("awaiting_more_detail", alias_only.reason_code)

    def test_trigger_establishes_relevance_but_does_not_force_reply(self) -> None:
        trigger_only = assess([message(1, "coffee")])
        substantive = assess([message(2, "coffee culture is painfully overrated")])

        self.assertEqual("defer", trigger_only.outcome)
        self.assertEqual("proactive", trigger_only.engagement_type)
        self.assertEqual("reply", substantive.outcome)
        self.assertEqual("card_trigger_with_substance", substantive.reason_code)

    def test_card_terms_are_exact_and_card_specific(self) -> None:
        coffee = assess(
            [message(1, "coffee culture is painfully overrated")],
            character=card(triggers=("coffee",)),
            conversation=False,
        )
        football = assess(
            [message(1, "coffee culture is painfully overrated")],
            character=card(triggers=("football",)),
            conversation=False,
        )

        self.assertEqual("reply", coffee.outcome)
        self.assertEqual("skip", football.outcome)
        self.assertFalse(term_in_text("ai", "Canadian Jesus wears cargo socks"))

    def test_anaphoric_opinion_needs_and_uses_adjacent_context(self) -> None:
        prior = message(1, "The audio was remastered in 2024", author="Mara", author_id="2")
        fresh = message(2, "it still sounds worse though")

        unresolved = assess([fresh], context=[fresh])
        resolved = assess([fresh], context=[prior, fresh])

        self.assertEqual("defer", unresolved.outcome)
        self.assertEqual("awaiting_context", unresolved.reason_code)
        self.assertEqual("reply", resolved.outcome)
        self.assertEqual("thread_continuation", resolved.reason_code)
        self.assertEqual((fresh.message_id,), resolved.target_message_ids)
        self.assertEqual((prior.message_id,), resolved.support_message_ids)

    def test_same_author_fragments_form_one_target_group(self) -> None:
        messages = [
            message(1, "the edit is cleaner"),
            message(2, "but it sounds way worse"),
        ]

        result = assess(messages)

        self.assertEqual("reply", result.outcome)
        self.assertEqual(tuple(item.message_id for item in messages), result.target_message_ids)

    def test_app_feed_and_meta_suspicion_are_skipped(self) -> None:
        app = message(
            1,
            "Doggo and Bear were playing",
            author="WordleVerified AppAPP",
            author_id="app",
        )
        meta = message(2, "your posting behavior sounds like a bot")

        self.assertEqual("system_feed", assess([app]).reason_code)
        self.assertEqual("meta_suspicion", assess([meta]).reason_code)

    def test_domain_nouns_do_not_receive_hidden_priority(self) -> None:
        result = assess(
            [message(1, "sensor camera foia physics government")],
            character=card(triggers=()),
        )

        self.assertEqual("skip", result.outcome)
        self.assertEqual("insufficient_substance", result.reason_code)


if __name__ == "__main__":
    unittest.main()
