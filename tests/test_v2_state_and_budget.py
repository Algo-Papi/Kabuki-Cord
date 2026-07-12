from __future__ import annotations

import tempfile
import unittest
import json
from types import SimpleNamespace
from unittest.mock import patch
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path

from nhi_zues.budget import BudgetManager
from nhi_zues.app_paths import migrate_legacy_data, resolve_data_path
from nhi_zues.state_io import mutate_json_file, read_json_file
from nhi_zues.gui import reset_discord_session


class V2StateTests(unittest.TestCase):
    def test_legacy_layout_migrates_to_isolated_app_data(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            legacy = root / "legacy"
            app_data = root / "app-data"
            (legacy / ".state").mkdir(parents=True)
            (legacy / ".state" / "events.json").write_text('{"items": []}', encoding="utf-8")
            (legacy / "character_cards").mkdir()
            (legacy / "character_cards" / "default.json").write_text("{}", encoding="utf-8")
            with patch.dict(
                "os.environ",
                {
                    "KABUKI_CORD_DATA_DIR": str(app_data),
                    "KABUKI_CORD_LEGACY_ROOT": str(legacy),
                },
                clear=False,
            ):
                migrated = migrate_legacy_data(include_browser_profile=False)
                self.assertTrue(migrated["state"])
                self.assertTrue((app_data / "state" / "events.json").is_file())
                self.assertTrue((app_data / "character_cards" / "default.json").is_file())

    def test_relative_data_path_cannot_escape_app_root(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            with patch.dict("os.environ", {"KABUKI_CORD_DATA_DIR": directory}, clear=False):
                with self.assertRaises(ValueError):
                    resolve_data_path("../../outside", "state")

    def test_concurrent_mutations_do_not_lose_updates(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "state" / "counter.json"

            def increment(_: int) -> None:
                mutate_json_file(
                    path,
                    default={"count": 0},
                    mutator=lambda payload: payload.update(count=int(payload["count"]) + 1),
                )

            with ThreadPoolExecutor(max_workers=8) as executor:
                list(executor.map(increment, range(100)))

            self.assertEqual(100, read_json_file(path, default={"count": 0})["count"])
            self.assertTrue((path.parent / "state.db").exists())

    def test_session_budget_is_shared_across_manager_instances(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            usage_file = Path(directory) / "state" / "usage.json"
            first = BudgetManager(
                usage_file,
                model="gpt-5.4-nano",
                max_daily_usd=10,
                max_session_usd=10,
                max_calls_per_run=1,
            )
            first.record(input_tokens=10, output_tokens=10)
            second = BudgetManager(
                usage_file,
                model="gpt-5.4-nano",
                max_daily_usd=10,
                max_session_usd=10,
                max_calls_per_run=1,
            )
            check = second.check(estimated_input_tokens=1, max_output_tokens=1)
            self.assertFalse(check.allowed)
            self.assertIn("max LLM calls", check.reason)

    def test_unknown_model_pricing_fails_closed(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            manager = BudgetManager(
                Path(directory) / "state" / "usage.json",
                model="unpriced-future-model",
                max_daily_usd=10,
                max_session_usd=10,
                max_calls_per_run=3,
            )
            check = manager.check(estimated_input_tokens=100, max_output_tokens=100)
            self.assertFalse(check.allowed)
            self.assertIn("No verified pricing", check.reason)

    def test_discord_session_reset_clears_profile_and_disables_old_targets(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            profile_dir = root / "profiles" / "discord"
            profile_dir.mkdir(parents=True)
            (profile_dir / "Cookies").write_text("old session", encoding="utf-8")
            servers_file = root / "config" / "servers.json"
            servers_file.parent.mkdir(parents=True)
            servers_file.write_text(
                json.dumps(
                    {
                        "servers": [
                            {
                                "server_id": "server-1",
                                "channels": [
                                    {
                                        "channel_id": "channel-1",
                                        "scan_enabled": True,
                                        "engage_enabled": True,
                                        "react_enabled": True,
                                        "auto_respond_enabled": True,
                                    }
                                ],
                            }
                        ]
                    }
                ),
                encoding="utf-8",
            )
            config = SimpleNamespace(
                profile_dir=profile_dir,
                servers_file=servers_file,
                state_dir=root / "state",
            )
            with (
                patch.dict("os.environ", {"KABUKI_CORD_DATA_DIR": str(root)}, clear=False),
                patch("nhi_zues.gui.load_config", return_value=config),
                patch("nhi_zues.gui.RUNTIME.pause") as pause,
                patch("nhi_zues.browser._close_profile_browsers") as close_browsers,
                patch("nhi_zues.gui.clear_discord_credentials") as clear_credentials,
            ):
                reset_discord_session()

            self.assertTrue(profile_dir.is_dir())
            self.assertEqual([], list(profile_dir.iterdir()))
            pause.assert_called_once_with(wait=True, timeout=15.0)
            close_browsers.assert_called_once_with(profile_dir.resolve())
            clear_credentials.assert_called_once_with()
            payload = json.loads(servers_file.read_text(encoding="utf-8"))
            channel = payload["servers"][0]["channels"][0]
            self.assertFalse(channel["scan_enabled"])
            self.assertFalse(channel["engage_enabled"])
            self.assertFalse(channel["react_enabled"])
            self.assertFalse(channel["auto_respond_enabled"])


if __name__ == "__main__":
    unittest.main()
