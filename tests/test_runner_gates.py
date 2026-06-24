from datetime import datetime, timedelta, timezone
from types import SimpleNamespace
import unittest

from nhi_zues.models import MessageRecord
from nhi_zues.reply_ledger import SentReply
from nhi_zues.runner import _approval_gate_reason, _auto_reply_guard_reason, _requires_approval


class ReplyLedgerStub:
    def __init__(self, items=None):
        self.items = list(items or [])

    def latest_for_channel(self, *, channel_id: str):
        for item in reversed(self.items):
            if item.channel_id == channel_id:
                return item
        return None

    def recent_for_channel(self, *, channel_id: str, window_seconds: float, now: datetime):
        return [
            item
            for item in self.items
            if item.channel_id == channel_id
            and (now - datetime.fromisoformat(item.created_at)).total_seconds() <= window_seconds
        ]


def guard_config(**overrides):
    values = {
        "reply_cooldown_seconds": 900.0,
        "reply_window_seconds": 3600.0,
        "reply_max_per_window": 3,
        "reply_require_intervening_user": True,
    }
    values.update(overrides)
    return SimpleNamespace(**values)


def sent_reply(created_at: datetime, *, channel_id: str = "channel-1") -> SentReply:
    return SentReply(
        reply_id=f"reply-{created_at.timestamp()}",
        created_at=created_at.isoformat(),
        server_id="server-1",
        channel_id=channel_id,
        mode="auto",
        draft_hash="abc",
        source_message_ids=("source-1",),
    )


def message(message_id: str, author: str) -> MessageRecord:
    return MessageRecord(
        server_id="server-1",
        channel_id="channel-1",
        message_id=message_id,
        author=author,
        author_id=None,
        text="hello",
        observed_at=datetime.now(timezone.utc),
    )


class RunnerGateTests(unittest.TestCase):
    def test_full_auto_still_requires_approval_when_channel_auto_is_off(self):
        self.assertTrue(_requires_approval("full_auto", "conversation", auto_respond_enabled=False))
        self.assertEqual(
            "Auto is off for this channel",
            _approval_gate_reason("full_auto", "conversation", auto_respond_enabled=False),
        )

    def test_full_auto_allows_conversation_when_channel_auto_is_on(self):
        self.assertFalse(_requires_approval("full_auto", "conversation", auto_respond_enabled=True))
        self.assertEqual(
            "",
            _approval_gate_reason("full_auto", "conversation", auto_respond_enabled=True),
        )

    def test_live_fire_explains_universal_review_gate(self):
        self.assertTrue(_requires_approval("live_fire", "direct", auto_respond_enabled=True))
        self.assertEqual(
            "Live Fire requires review for every draft",
            _approval_gate_reason("live_fire", "direct", auto_respond_enabled=True),
        )

    def test_auto_reply_guard_blocks_channel_cooldown(self):
        now = datetime(2026, 6, 23, 12, 0, tzinfo=timezone.utc)
        ledger = ReplyLedgerStub([sent_reply(now - timedelta(minutes=2))])

        reason = _auto_reply_guard_reason(
            guard_config(),
            ledger,
            channel_id="channel-1",
            visible_messages=[message("1", "Rook")],
            character_names=("NHI Zues",),
            now=now,
        )

        self.assertIn("channel cooldown", reason)

    def test_auto_reply_guard_blocks_channel_rate_limit(self):
        now = datetime(2026, 6, 23, 12, 0, tzinfo=timezone.utc)
        ledger = ReplyLedgerStub(
            [
                sent_reply(now - timedelta(minutes=50)),
                sent_reply(now - timedelta(minutes=35)),
                sent_reply(now - timedelta(minutes=20)),
            ]
        )

        reason = _auto_reply_guard_reason(
            guard_config(reply_cooldown_seconds=0),
            ledger,
            channel_id="channel-1",
            visible_messages=[message("1", "Rook")],
            character_names=("NHI Zues",),
            now=now,
        )

        self.assertIn("rate limit", reason)

    def test_auto_reply_guard_blocks_when_character_is_last_visible_author(self):
        reason = _auto_reply_guard_reason(
            guard_config(reply_cooldown_seconds=0, reply_max_per_window=0),
            ReplyLedgerStub(),
            channel_id="channel-1",
            visible_messages=[message("1", "Rook"), message("2", "NHI Zues")],
            character_names=("NHI Zues", "zues"),
            now=datetime(2026, 6, 23, 12, 0, tzinfo=timezone.utc),
        )

        self.assertIn("last visible message", reason)

    def test_auto_reply_guard_allows_when_another_user_spoke_after_character(self):
        reason = _auto_reply_guard_reason(
            guard_config(reply_cooldown_seconds=0, reply_max_per_window=0),
            ReplyLedgerStub(),
            channel_id="channel-1",
            visible_messages=[
                message("1", "NHI Zues"),
                message("2", "Rook"),
            ],
            character_names=("NHI Zues",),
            now=datetime(2026, 6, 23, 12, 0, tzinfo=timezone.utc),
        )

        self.assertEqual("", reason)


if __name__ == "__main__":
    unittest.main()
