from __future__ import annotations

import unittest
from unittest.mock import patch

from nhi_zues.desktop import DesktopBridge, configure_webview2_runtime


class FakeWindow:
    def __init__(self, *, closed: bool = False) -> None:
        self.closed = closed
        self.calls: list[str] = []

    def evaluate_js(self, _script: str) -> str:
        if self.closed:
            raise RuntimeError("window closed")
        return "complete"

    def show(self) -> None:
        self.calls.append("show")

    def restore(self) -> None:
        self.calls.append("restore")

    def bring_to_front(self) -> None:
        self.calls.append("bring_to_front")


class DesktopBridgeTests(unittest.TestCase):
    def test_webview_runtime_flags_bound_renderers_and_preserve_existing_flags(self) -> None:
        with patch.dict(
            "os.environ",
            {"WEBVIEW2_ADDITIONAL_BROWSER_ARGUMENTS": "--existing-flag"},
            clear=False,
        ):
            configure_webview2_runtime()
            value = __import__("os").environ["WEBVIEW2_ADDITIONAL_BROWSER_ARGUMENTS"]

        self.assertIn("--existing-flag", value)
        self.assertIn("--renderer-process-limit=2", value)
        self.assertEqual(1, value.count("--renderer-process-limit=2"))

    def test_focus_monitor_window_reuses_live_window(self) -> None:
        bridge = DesktopBridge("http://127.0.0.1:8765")
        window = FakeWindow()
        bridge.monitor_window = window

        self.assertTrue(bridge._focus_monitor_window())
        self.assertIs(bridge.monitor_window, window)
        self.assertEqual(window.calls, ["show", "restore", "bring_to_front"])

    def test_focus_monitor_window_clears_closed_window(self) -> None:
        bridge = DesktopBridge("http://127.0.0.1:8765")
        bridge.monitor_window = FakeWindow(closed=True)

        self.assertFalse(bridge._focus_monitor_window())
        self.assertIsNone(bridge.monitor_window)


if __name__ == "__main__":
    unittest.main()
