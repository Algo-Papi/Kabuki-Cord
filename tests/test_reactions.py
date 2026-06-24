from __future__ import annotations

import sys
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))

from nhi_zues.reactions import (
    APPRECIATION_EMOJI,
    EYES_EMOJI,
    LAUGH_EMOJI,
    THINKING_EMOJI,
    THUMBS_UP_EMOJI,
    should_auto_laugh_react,
    should_auto_react,
    suggest_emoji_reaction,
)


class ReactionSuggestionTests(unittest.TestCase):
    def test_joke_gets_laugh_reaction(self) -> None:
        emoji, reason = suggest_emoji_reaction("that is such a dumb bit lmao")

        self.assertEqual(LAUGH_EMOJI, emoji)
        self.assertIn("joke", reason)

    def test_agreement_gets_thumbs_up(self) -> None:
        emoji, reason = suggest_emoji_reaction("exactly, that is a fair point")

        self.assertEqual(THUMBS_UP_EMOJI, emoji)
        self.assertIn("agreement", reason)

    def test_weird_claim_gets_eyes(self) -> None:
        emoji, reason = suggest_emoji_reaction("that is a bizarre detail and honestly wild")

        self.assertEqual(EYES_EMOJI, emoji)
        self.assertIn("weird", reason)

    def test_question_gets_thinking_reaction(self) -> None:
        emoji, reason = suggest_emoji_reaction("Anyone following the World Cup?")

        self.assertEqual(THINKING_EMOJI, emoji)
        self.assertIn("question", reason)

    def test_auto_laugh_requires_strong_joke_marker(self) -> None:
        should_react, _reason = should_auto_laugh_react("this is such a cursed meme lmao")
        self.assertTrue(should_react)

    def test_auto_laugh_ignores_plain_agreement(self) -> None:
        should_react, _reason = should_auto_laugh_react("exactly, that is a fair point")
        self.assertFalse(should_react)

    def test_auto_react_handles_agreement(self) -> None:
        should_react, emoji, reason = should_auto_react("exactly, that is a fair point")

        self.assertTrue(should_react)
        self.assertEqual(THUMBS_UP_EMOJI, emoji)
        self.assertIn("agreement", reason)

    def test_auto_react_handles_appreciation(self) -> None:
        should_react, emoji, reason = should_auto_react("thanks, that was actually helpful")

        self.assertTrue(should_react)
        self.assertEqual(APPRECIATION_EMOJI, emoji)
        self.assertIn("helpful", reason)

    def test_auto_react_handles_weird_claim(self) -> None:
        should_react, emoji, reason = should_auto_react("that whole account is bizarre and honestly wild")

        self.assertTrue(should_react)
        self.assertEqual(EYES_EMOJI, emoji)
        self.assertIn("weird", reason)

    def test_auto_react_ignores_low_signal_text(self) -> None:
        should_react, emoji, reason = should_auto_react("ok")

        self.assertFalse(should_react)
        self.assertEqual("", emoji)
        self.assertIn("low-signal", reason)

    def test_auto_react_normal_ignores_safe_light_acknowledgement(self) -> None:
        should_react, emoji, reason = should_auto_react("I saw the update from earlier and will check it later")

        self.assertFalse(should_react)
        self.assertEqual("", emoji)
        self.assertIn("no configured", reason)

    def test_auto_react_loose_accepts_safe_light_acknowledgement(self) -> None:
        should_react, emoji, reason = should_auto_react(
            "I saw the update from earlier and will check it later",
            threshold="loose",
        )

        self.assertTrue(should_react)
        self.assertEqual(THUMBS_UP_EMOJI, emoji)
        self.assertIn("loose threshold", reason)

    def test_auto_react_can_sample_with_override(self) -> None:
        should_react, emoji, reason = should_auto_react(
            "I saw the update from earlier and will check it later",
            sample_percent=10,
            emoji_override=LAUGH_EMOJI,
            sample_roll=0.05,
        )

        self.assertTrue(should_react)
        self.assertEqual(LAUGH_EMOJI, emoji)
        self.assertIn("10%", reason)

    def test_force_reaction_does_not_laugh_at_plain_text(self) -> None:
        should_react, emoji, reason = should_auto_react(
            "I saw the update from earlier and will check it later",
            force_laugh_percent=100,
            force_laugh_roll=0.0,
        )

        self.assertTrue(should_react)
        self.assertEqual(THUMBS_UP_EMOJI, emoji)
        self.assertIn("force reaction", reason)

    def test_force_reaction_keeps_laugh_for_obvious_joke(self) -> None:
        should_react, emoji, reason = should_auto_react(
            "that is such a dumb bit lmao",
            force_laugh_percent=100,
            force_laugh_roll=0.0,
        )

        self.assertTrue(should_react)
        self.assertEqual(LAUGH_EMOJI, emoji)
        self.assertIn("joke", reason)

    def test_auto_react_sample_respects_roll(self) -> None:
        should_react, emoji, reason = should_auto_react(
            "I saw the update from earlier and will check it later",
            sample_percent=10,
            sample_roll=0.5,
        )

        self.assertFalse(should_react)
        self.assertEqual("", emoji)
        self.assertIn("no configured", reason)

    def test_auto_react_override_applies_to_smart_match(self) -> None:
        should_react, emoji, reason = should_auto_react(
            "exactly, that is a fair point",
            emoji_override=LAUGH_EMOJI,
        )

        self.assertTrue(should_react)
        self.assertEqual(LAUGH_EMOJI, emoji)
        self.assertIn("override", reason)


if __name__ == "__main__":
    unittest.main()
