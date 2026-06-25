from __future__ import annotations

import sys
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))

from nhi_zues.server_sync import merge_discovered_servers


class ServerSyncTests(unittest.TestCase):
    def test_sync_removes_servers_missing_from_discord_discovery(self) -> None:
        payload = {
            "servers": [
                {
                    "server_id": "kept",
                    "label": "Old Label",
                    "character_card": "cards/custom.json",
                    "safety_review_enabled": True,
                    "channels": [
                        {
                            "channel_id": "general",
                            "label": "old-general",
                            "scan_enabled": True,
                            "engage_enabled": True,
                            "react_enabled": True,
                            "auto_respond_enabled": True,
                        }
                    ],
                },
                {
                    "server_id": "stale",
                    "label": "Kicked Server",
                    "channels": [{"channel_id": "gone", "label": "gone"}],
                },
            ]
        }
        discovered = [
            {
                "server_id": "kept",
                "label": "New Label",
                "icon_url": "https://cdn.discordapp.com/icons/kept/icon.png",
                "channels": [
                    {
                        "channel_id": "general",
                        "label": "general",
                        "channel_type": "text",
                    }
                ],
            }
        ]

        merged, stats = merge_discovered_servers(
            payload,
            discovered,
            icon_path_for_server=lambda server_id, icon_url: f"/icons/{server_id}.png",
        )

        self.assertEqual(["kept"], [server["server_id"] for server in merged["servers"]])
        kept = merged["servers"][0]
        self.assertEqual("New Label", kept["label"])
        self.assertEqual("cards/custom.json", kept["character_card"])
        self.assertTrue(kept["safety_review_enabled"])
        self.assertEqual("/icons/kept.png", kept["icon_path"])
        self.assertTrue(kept["channels"][0]["scan_enabled"])
        self.assertTrue(kept["channels"][0]["engage_enabled"])
        self.assertTrue(kept["channels"][0]["react_enabled"])
        self.assertTrue(kept["channels"][0]["auto_respond_enabled"])
        self.assertEqual(1, stats["removed"])
        self.assertEqual(["stale"], stats["removed_server_ids"])
        self.assertEqual(0, stats["added"])
        self.assertEqual(1, stats["updated"])

    def test_sync_adds_new_server_with_disabled_channel_defaults(self) -> None:
        merged, stats = merge_discovered_servers(
            {"servers": []},
            [
                {
                    "server_id": "new",
                    "label": "New Server",
                    "channels": [{"channel_id": "general", "label": "general"}],
                }
            ],
        )

        [server] = merged["servers"]
        [channel] = server["channels"]
        self.assertEqual("new", server["server_id"])
        self.assertEqual(["new"], stats["added_server_ids"])
        self.assertFalse(channel["scan_enabled"])
        self.assertFalse(channel["engage_enabled"])
        self.assertFalse(channel["react_enabled"])
        self.assertFalse(channel["auto_respond_enabled"])


if __name__ == "__main__":
    unittest.main()
