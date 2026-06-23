from __future__ import annotations

import sys
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))

from nhi_zues.gui import _suggest_emoji_reaction


class ReactionSuggestionTests(unittest.TestCase):
    def test_joke_gets_laugh_reaction(self) -> None:
        emoji, reason = _suggest_emoji_reaction("that is such a dumb bit lmao")

        self.assertEqual("😂", emoji)
        self.assertIn("joke", reason)

    def test_agreement_gets_thumbs_up(self) -> None:
        emoji, reason = _suggest_emoji_reaction("exactly, that is a fair point")

        self.assertEqual("👍", emoji)
        self.assertIn("agreement", reason)

    def test_weird_claim_gets_eyes(self) -> None:
        emoji, reason = _suggest_emoji_reaction("that is a bizarre detail and honestly wild")

        self.assertEqual("👀", emoji)
        self.assertIn("weird", reason)


if __name__ == "__main__":
    unittest.main()
