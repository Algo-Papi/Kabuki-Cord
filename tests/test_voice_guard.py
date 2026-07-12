from __future__ import annotations

import sys
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))

from nhi_zues.voice_guard import DEFAULT_RESPONSE_MOVES, draft_quality_issues


class VoiceGuardTests(unittest.TestCase):
    def test_flags_formulaic_recap_opener(self) -> None:
        issues = draft_quality_issues(
            "that part about the government hiding it sounds like the whole point is control"
        )

        self.assertTrue(any("recap" in issue for issue in issues))

    def test_flags_direct_quote_block(self) -> None:
        issues = draft_quality_issues(
            'the line "this proves the whole thing was planned" is too clean to trust'
        )

        self.assertTrue(any("quotation" in issue for issue in issues))

    def test_allows_short_opinionated_side_comment(self) -> None:
        issues = draft_quality_issues(
            "i dont buy the clean debunk. pilots misread stuff, sure, but not every weird radar hit is a balloon"
        )

        self.assertEqual([], issues)

    def test_default_moves_are_domain_neutral(self) -> None:
        defaults = " ".join(DEFAULT_RESPONSE_MOVES).lower()

        for residue in ("uap", "ufo", "foia", "raw log", "clean debunk", "spiritual angle"):
            with self.subTest(residue=residue):
                self.assertNotIn(residue, defaults)


if __name__ == "__main__":
    unittest.main()
