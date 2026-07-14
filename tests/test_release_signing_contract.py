from __future__ import annotations

import unittest
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]


class ReleaseSigningContractTests(unittest.TestCase):
    def test_release_version_is_final(self) -> None:
        pyproject = (ROOT / "pyproject.toml").read_text(encoding="utf-8")
        package = (ROOT / "src" / "nhi_zues" / "__init__.py").read_text(encoding="utf-8")
        self.assertIn('version = "2.5.0"', pyproject)
        self.assertIn('__version__ = "2.5.0"', package)
        self.assertNotIn("2.5.0.dev", pyproject + package)

    def test_release_workflow_supports_optional_signing(self) -> None:
        workflow = (ROOT / ".github" / "workflows" / "release.yml").read_text(encoding="utf-8")
        self.assertIn("WINDOWS_CODE_SIGNING_PFX_BASE64", workflow)
        self.assertIn("WINDOWS_CODE_SIGNING_PFX_PASSWORD", workflow)
        self.assertIn("Publishing an unsigned Windows installer", workflow)
        self.assertIn("KABUKI_CORD_REQUIRE_SIGNATURE", workflow)
        self.assertIn("-RequireSignature", workflow)

    def test_release_builder_verifies_authenticode(self) -> None:
        builder = (ROOT / "installer" / "windows" / "Build-ReleaseZip.ps1").read_text(encoding="utf-8")
        self.assertIn("[switch]$RequireSignature", builder)
        self.assertIn("Get-AuthenticodeSignature", builder)
        self.assertIn('Status -ne "Valid"', builder)
        self.assertIn("1.3.6.1.5.5.7.3.3", builder)


if __name__ == "__main__":
    unittest.main()
