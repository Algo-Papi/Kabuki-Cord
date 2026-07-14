from __future__ import annotations

import json
import logging
import sys
import unittest
import zipfile
from pathlib import Path
from tempfile import TemporaryDirectory
from types import SimpleNamespace
from unittest.mock import patch

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))

from nhi_zues.diagnostics import collect_diagnostics, redact_diagnostic_text


class DiagnosticTests(unittest.TestCase):
    def test_redacts_credentials_email_and_discord_urls(self) -> None:
        value = (
            "api_key=sk-secret123 user@example.com "
            "https://discord.com/channels/123456789012345678/987654321098765432/111222333444555666"
        )

        redacted = redact_diagnostic_text(value)

        self.assertNotIn("secretvalue", redacted)
        self.assertNotIn("user@example.com", redacted)
        self.assertNotIn("123456789012345678", redacted)
        self.assertIn("redacted", redacted)

    def test_bundle_is_local_redacted_and_excludes_content_state(self) -> None:
        with TemporaryDirectory() as tmp:
            root = Path(tmp)
            state_dir = root / "state"
            state_dir.mkdir(parents=True)
            (state_dir / "logs").mkdir()
            (state_dir / "app.log").write_text("scan metrics={\"eligible\": 2}\n", encoding="utf-8")
            (state_dir / "logs" / "kabuki-cord.log").write_text(
                "login user@example.com api_key=sk-secret123\n",
                encoding="utf-8",
            )
            (state_dir / "events.json").write_text(
                json.dumps({"items": [{"draft": "private chat text"}]}),
                encoding="utf-8",
            )
            servers_file = root / "config" / "servers.json"
            servers_file.parent.mkdir(parents=True)
            servers_file.write_text(
                json.dumps({"servers": [{"channels": [{"scan_enabled": True, "react_enabled": True}]}]}),
                encoding="utf-8",
            )
            config = SimpleNamespace(
                state_dir=state_dir,
                servers_file=servers_file,
                runtime_mode="dry",
                headless=True,
                llm_enabled=False,
                openai_api_key="sk-hidden456",
            )

            with (
                patch("nhi_zues.diagnostics.load_config", return_value=config),
                patch("nhi_zues.diagnostics.app_data_root", return_value=root),
                patch(
                    "nhi_zues.diagnostics.discord_credential_status",
                    return_value={"email_set": True, "password_set": True},
                ),
            ):
                result = collect_diagnostics(open_folder=False)
            for handler in list(logging.getLogger().handlers):
                if getattr(handler, "kabuki_cord_diagnostic_handler", False):
                    logging.getLogger().removeHandler(handler)
                    handler.close()

            archive = root / "diagnostics" / str(result["filename"])
            self.assertTrue(archive.is_file())
            with zipfile.ZipFile(archive) as bundle:
                names = set(bundle.namelist())
                combined = "\n".join(
                    bundle.read(name).decode("utf-8", errors="replace") for name in names
                )
            self.assertIn("README.txt", names)
            self.assertIn("diagnostics.json", names)
            self.assertNotIn("events.json", names)
            self.assertNotIn("private chat text", combined)
            self.assertNotIn("user@example.com", combined)
            self.assertNotIn("secret123", combined)
            self.assertNotIn("hidden456", combined)
            self.assertIn("Nothing was uploaded", str(result["message"]))


if __name__ == "__main__":
    unittest.main()
