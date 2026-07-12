from __future__ import annotations

import unittest
from datetime import datetime, timezone

from nhi_zues.character import CharacterCard
from nhi_zues.llm import _engagement_type
from nhi_zues.models import MessageRecord
from nhi_zues.topics import TopicSnapshot, TopicTracker


def message(message_id: int, text: str) -> MessageRecord:
    return MessageRecord(
        server_id="server",
        channel_id="channel",
        message_id=f"chat-messages-123-{message_id}",
        author="Rook",
        author_id="1",
        text=text,
        observed_at=datetime(2026, 7, 12, tzinfo=timezone.utc),
    )


def character() -> CharacterCard:
    return CharacterCard(
        name="Test Character",
        system_prompt="",
        style_rules=(),
        engagement_rules=(),
        response_moves=(),
        voice_examples=(),
        avoid_examples=(),
        aliases=("zyn",),
        trigger_keywords=("cold brew",),
    )


class TopicTrackerTests(unittest.TestCase):
    def test_tracks_generic_recurring_terms(self) -> None:
        tracker = TopicTracker(decay=1.0)

        snapshot = tracker.update(
            "channel",
            [
                message(1, "The album mix sounds muddy"),
                message(2, "That album remaster still sounds muddy"),
            ],
        )

        scores = dict(snapshot.top_topics)
        self.assertEqual(2.0, scores["album"])
        self.assertEqual(2.0, scores["sounds"])
        self.assertEqual(2.0, scores["muddy"])

    def test_exact_tracked_terms_receive_card_aware_weight(self) -> None:
        tracker = TopicTracker(decay=1.0)

        snapshot = tracker.update(
            "channel",
            [message(1, "cold brew tastes better than drip")],
            tracked_terms=("cold brew", "ai"),
        )

        scores = dict(snapshot.top_topics)
        self.assertEqual(2.0, scores["cold brew"])
        self.assertNotIn("ai", scores)

    def test_topic_snapshot_never_authorizes_engagement(self) -> None:
        snapshot = TopicSnapshot(
            channel_id="channel",
            top_topics=(("uap", 99.0),),
            recent_terms=(("uap", 5),),
        )

        mode = _engagement_type(
            [message(1, "ordinary status update")],
            snapshot,
            character(),
            conversation_reply_enabled=False,
        )

        self.assertEqual("none", mode)


if __name__ == "__main__":
    unittest.main()
