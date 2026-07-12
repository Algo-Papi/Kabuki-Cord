from __future__ import annotations

import json
import unittest
from pathlib import Path


WEB_ROOT = Path(__file__).resolve().parents[1] / "src" / "nhi_zues" / "web"


class WebContractTests(unittest.TestCase):
    def test_frontend_has_no_remote_runtime_dependencies(self) -> None:
        index = (WEB_ROOT / "index.html").read_text(encoding="utf-8")
        self.assertNotIn("https://fonts.", index)
        self.assertNotIn("cdn.jsdelivr.net", index)

    def test_switch_inputs_remain_keyboard_accessible(self) -> None:
        styles = (WEB_ROOT / "styles.css").read_text(encoding="utf-8")
        switch_rule = styles.split(".switch input {", 1)[1].split("}", 1)[0]
        self.assertNotIn("display: none", switch_rule)
        self.assertIn("opacity: 0", switch_rule)
        self.assertIn(".switch input:focus-visible + span", styles)

    def test_monitor_uses_compact_state_endpoint(self) -> None:
        script = (WEB_ROOT / "monitor.js").read_text(encoding="utf-8")
        self.assertIn('api("/api/monitor-state")', script)
        self.assertNotIn('api("/api/state")', script)

    def test_monitor_renders_content_free_engagement_funnel_and_freshness(self) -> None:
        markup = (WEB_ROOT / "monitor.html").read_text(encoding="utf-8")
        script = (WEB_ROOT / "monitor.js").read_text(encoding="utf-8")
        styles = (WEB_ROOT / "monitor.css").read_text(encoding="utf-8")

        for element_id in (
            "engagementFunnel",
            "funnelFreshObserved",
            "funnelOwnFiltered",
            "funnelPending",
            "funnelDeferred",
            "funnelEligible",
            "funnelModelCalled",
            "funnelDraftQueued",
            "funnelSent",
            "funnelRejected",
            "decisionReasons",
            "channelFreshness",
        ):
            self.assertIn(f'id="{element_id}"', markup)
        self.assertIn("renderEngagement(state.engagement || {})", script)
        self.assertIn('available && Number.isFinite(value) ? String', script)
        self.assertIn(': "--"', script)
        self.assertIn("channel.server_label", script)
        self.assertIn("channel.channel_label", script)
        self.assertIn(".funnel-grid", styles)
        self.assertIn(".freshness-row", styles)

    def test_scanner_monitor_uses_direct_v2_frames(self) -> None:
        from PIL import Image

        script = (WEB_ROOT / "monitor.js").read_text(encoding="utf-8")
        styles = (WEB_ROOT / "monitor.css").read_text(encoding="utf-8")
        frame_dir = WEB_ROOT / "assets" / "monitor_spy_v2_frames"
        manifest = json.loads((frame_dir / "manifest.json").read_text(encoding="utf-8"))
        frames = sorted(frame_dir.glob("frame_*.webp"))

        self.assertIn('"/assets/monitor_spy_v2_frames"', script)
        self.assertNotIn('"/assets/monitor_spy_frames"', script)
        self.assertIn("showSceneFrame((spyFrameIndex + 1) % spyFrames.length, { transition: false })", script)
        self.assertEqual(8, manifest["frame_count"])
        self.assertEqual(350, manifest["frame_ms"])
        self.assertEqual("webp", manifest["extension"])
        self.assertEqual(8, len(frames))
        spy_rule = styles.split(".spy-frame {", 1)[1].split("}", 1)[0]
        self.assertIn("image-rendering: auto", spy_rule)
        self.assertIn("transition: none", spy_rule)
        for frame in frames:
            with self.subTest(frame=frame.name):
                with Image.open(frame) as image:
                    self.assertEqual((640, 480), image.size)
                    self.assertEqual("RGB", image.mode)

    def test_channel_autonomy_is_explicit_and_persisted(self) -> None:
        index = (WEB_ROOT / "index.html").read_text(encoding="utf-8")
        script = (WEB_ROOT / "app.js").read_text(encoding="utf-8")
        self.assertIn('id="channelAutoRespond" type="checkbox"', index)
        self.assertNotIn('id="channelAutoRespond" type="checkbox" disabled', index)
        self.assertIn('button.dataset.toggle === "auto"', script)
        self.assertIn("persistServersSoon();", script)

    def test_discord_account_switch_is_explicit(self) -> None:
        index = (WEB_ROOT / "index.html").read_text(encoding="utf-8")
        script = (WEB_ROOT / "app.js").read_text(encoding="utf-8")
        self.assertIn('id="switchDiscordAccount"', index)
        self.assertIn('api("/api/discord-session-reset"', script)
        self.assertIn('confirmation: "SWITCH_DISCORD_ACCOUNT"', script)

    def test_discord_blocked_animation_uses_v2_eight_frame_sheet(self) -> None:
        styles = (WEB_ROOT / "styles.css").read_text(encoding="utf-8")
        self.assertIn('url("/assets/scanner-kabuki-discord-blocked-v2-sheet.png")', styles)
        self.assertIn("animation: scanner-discord-blocked 3.6s steps(8, end) infinite", styles)
        self.assertIn("background-position: -624px 0", styles)

    def test_posting_animation_uses_v2_eight_frame_sheet(self) -> None:
        styles = (WEB_ROOT / "styles.css").read_text(encoding="utf-8")
        self.assertIn('url("/assets/scanner-kabuki-posting-v2-sheet.png")', styles)
        self.assertIn("animation: scanner-posting-delivery 3.2s steps(8, end) infinite", styles)

    def test_default_scanner_uses_v2_eight_frame_sheet(self) -> None:
        styles = (WEB_ROOT / "styles.css").read_text(encoding="utf-8")
        self.assertIn('url("/assets/scanner-kabuki-v2-sheet.png")', styles)
        self.assertIn("animation: scanner-scout 3.2s steps(8, end) infinite", styles)
        self.assertIn("animation: scanner-scout 4s steps(8, end) infinite", styles)
        self.assertIn("background-position: -408px 0", styles)

    def test_discord_sync_uses_v2_eight_frame_sheet(self) -> None:
        styles = (WEB_ROOT / "styles.css").read_text(encoding="utf-8")
        self.assertIn('url("/assets/scanner-kabuki-sync-v2-sheet.png")', styles)
        self.assertIn("animation: scanner-sync-network 3.6s steps(8, end) infinite", styles)

    def test_server_repair_uses_v2_eight_frame_sheet(self) -> None:
        styles = (WEB_ROOT / "styles.css").read_text(encoding="utf-8")
        self.assertIn('url("/assets/scanner-kabuki-repair-v2-sheet.png")', styles)
        self.assertIn("animation: scanner-repair-fix 4s steps(8, end) infinite", styles)

    def test_history_backfill_uses_v2_eight_frame_sheet(self) -> None:
        styles = (WEB_ROOT / "styles.css").read_text(encoding="utf-8")
        self.assertIn('url("/assets/scanner-kabuki-backfill-v2-sheet.png")', styles)
        self.assertIn("animation: scanner-backfill-archive 4.4s steps(8, end) infinite", styles)

    def test_refresh_latest_uses_v2_eight_frame_sheet(self) -> None:
        styles = (WEB_ROOT / "styles.css").read_text(encoding="utf-8")
        self.assertIn('url("/assets/scanner-kabuki-latest-v2-sheet.png")', styles)
        self.assertIn("animation: scanner-latest-scroll 4s steps(8, end) infinite", styles)

    def test_refresh_local_state_uses_v2_eight_frame_sheet(self) -> None:
        styles = (WEB_ROOT / "styles.css").read_text(encoding="utf-8")
        self.assertIn('url("/assets/scanner-kabuki-refresh-v2-sheet.png")', styles)
        self.assertIn("animation: scanner-refresh-state 4s steps(8, end) infinite", styles)

    def test_dry_mode_uses_v2_eight_frame_sheet(self) -> None:
        styles = (WEB_ROOT / "styles.css").read_text(encoding="utf-8")
        self.assertIn('url("/assets/mode-kabuki-dry-v2-sheet.png")', styles)
        self.assertIn("animation: mode-dry-dust-run 2.08s steps(8, end) forwards", styles)
        self.assertIn("background-position: -1664px 0", styles)

    def test_semi_auto_mode_uses_v2_eight_frame_sheet(self) -> None:
        styles = (WEB_ROOT / "styles.css").read_text(encoding="utf-8")
        self.assertIn('url("/assets/mode-kabuki-semi-auto-v2-sheet.png")', styles)
        self.assertIn("animation: mode-semi-auto-check-run 2.16s steps(8, end) forwards", styles)

    def test_full_auto_mode_uses_v2_eight_frame_sheet(self) -> None:
        styles = (WEB_ROOT / "styles.css").read_text(encoding="utf-8")
        self.assertIn('url("/assets/mode-kabuki-full-auto-v2-sheet.png")', styles)
        self.assertIn("animation: mode-full-auto-run 2.25s steps(8, end) forwards", styles)

    def test_live_fire_mode_uses_v2_eight_frame_sheet(self) -> None:
        styles = (WEB_ROOT / "styles.css").read_text(encoding="utf-8")
        self.assertIn('url("/assets/mode-kabuki-live-fire-v2-sheet.png")', styles)
        self.assertIn("animation: mode-live-fire-run 2.25s steps(8, end) forwards", styles)

    def test_delivery_celebration_uses_v2_eight_frame_sheet(self) -> None:
        script = (WEB_ROOT / "monitor.js").read_text(encoding="utf-8")
        styles = (WEB_ROOT / "monitor.css").read_text(encoding="utf-8")
        self.assertIn('class="delivery-character delivery-character-toast"', script)
        self.assertIn('class="delivery-character delivery-character-burst"', script)
        self.assertNotIn('src="/assets/monitor-arigato-sprite.png"', script)
        self.assertIn('url("/assets/monitor-arigato-v2-sheet.png")', styles)
        self.assertIn("delivery-character-run 2400ms steps(7, end) forwards", styles)
        reduced_motion = styles.split("@media (prefers-reduced-motion: reduce) {", 1)[1]
        self.assertIn(".delivery-character-burst", reduced_motion)
        self.assertIn("background-position: 100% 0", reduced_motion)

    def test_dojo_sweep_monitor_uses_direct_v2_frames(self) -> None:
        from PIL import Image

        script = (WEB_ROOT / "monitor.js").read_text(encoding="utf-8")
        styles = (WEB_ROOT / "monitor.css").read_text(encoding="utf-8")
        frame_dir = WEB_ROOT / "assets" / "monitor_dojo_sweep_v2_frames"
        manifest = json.loads((frame_dir / "manifest.json").read_text(encoding="utf-8"))
        frames = sorted(frame_dir.glob("frame_*.webp"))

        self.assertIn('"/assets/monitor_dojo_sweep_v2_frames"', script)
        self.assertNotIn('"/assets/monitor_dojo_sweep_frames"', script)
        self.assertEqual(8, manifest["frame_count"])
        self.assertEqual(300, manifest["frame_ms"])
        self.assertEqual("webp", manifest["extension"])
        self.assertEqual(8, len(frames))
        dojo_rule = styles.split(".spy-scene.dojo-sweep .spy-frame {", 1)[1].split("}", 1)[0]
        self.assertIn("image-rendering: auto", dojo_rule)
        self.assertIn("transition: none", dojo_rule)
        for frame in frames:
            with self.subTest(frame=frame.name):
                with Image.open(frame) as image:
                    self.assertEqual((640, 480), image.size)
                    self.assertEqual("RGB", image.mode)

    def test_v2_sprite_sheets_match_their_css_contract(self) -> None:
        from PIL import Image

        for filename in (
            "scanner-kabuki-discord-blocked-v2-sheet.png",
            "scanner-kabuki-posting-v2-sheet.png",
            "scanner-kabuki-v2-sheet.png",
            "scanner-kabuki-sync-v2-sheet.png",
            "scanner-kabuki-repair-v2-sheet.png",
            "scanner-kabuki-backfill-v2-sheet.png",
            "scanner-kabuki-latest-v2-sheet.png",
            "scanner-kabuki-refresh-v2-sheet.png",
            "mode-kabuki-dry-v2-sheet.png",
            "mode-kabuki-semi-auto-v2-sheet.png",
            "mode-kabuki-full-auto-v2-sheet.png",
            "mode-kabuki-live-fire-v2-sheet.png",
            "monitor-arigato-v2-sheet.png",
        ):
            with self.subTest(filename=filename):
                with Image.open(WEB_ROOT / "assets" / filename) as sheet:
                    self.assertEqual((2048, 256), sheet.size)
                    self.assertEqual("RGBA", sheet.mode)


if __name__ == "__main__":
    unittest.main()
