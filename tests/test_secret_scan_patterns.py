from __future__ import annotations

import unittest

from scripts import secret_scan, verify_release_archive


class SecretScanPatternTests(unittest.TestCase):
    def test_asset_slugs_do_not_look_like_openai_keys(self) -> None:
        samples = (
            "update-mask-workshop-checking-v2-sheet.png",
            "update-mask-workshop-updated-v2-sheet.png",
            "update-mask-workshop-current-v2-sheet.png",
        )
        patterns = (
            secret_scan.PATTERNS["openai_project_key"],
            secret_scan.PATTERNS["openai_secret_key"],
            verify_release_archive.PATTERNS["openai_key"],
        )

        for sample in samples:
            for pattern in patterns:
                with self.subTest(sample=sample, pattern=pattern.pattern):
                    self.assertIsNone(pattern.search(sample))

    def test_openai_key_patterns_still_match_token_boundaries(self) -> None:
        secret = "s" + "k-" + ("x" * 24)
        project_secret = "s" + "k-proj-" + ("y" * 24)

        self.assertIsNotNone(secret_scan.PATTERNS["openai_secret_key"].search(secret))
        self.assertIsNotNone(secret_scan.PATTERNS["openai_project_key"].search(project_secret))
        self.assertIsNotNone(verify_release_archive.PATTERNS["openai_key"].search(secret))
        self.assertIsNotNone(verify_release_archive.PATTERNS["openai_key"].search(project_secret))

        self.assertIsNotNone(secret_scan.PATTERNS["openai_secret_key"].search(f"OPENAI_KEY_{secret}"))
        self.assertIsNotNone(secret_scan.PATTERNS["openai_project_key"].search(f"prefix-{project_secret}"))
        self.assertIsNotNone(verify_release_archive.PATTERNS["openai_key"].search(f"OPENAI_KEY_{secret}"))


if __name__ == "__main__":
    unittest.main()
