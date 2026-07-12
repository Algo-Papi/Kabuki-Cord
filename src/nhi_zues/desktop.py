from __future__ import annotations

import ctypes
import os
import threading
import webbrowser
from http.server import ThreadingHTTPServer
from ctypes import wintypes

from .app_paths import asset_root
from .gui import GuiHandler


ASSET_ROOT = asset_root()
BADGE_ICON_HANDLE = None


class DesktopBridge:
    def __init__(self, base_url: str) -> None:
        self.base_url = base_url.rstrip("/")
        self.monitor_window = None
        self._monitor_lock = threading.Lock()

    def set_badge(self, active: bool) -> bool:
        return set_taskbar_badge(bool(active))

    def open_monitor(self) -> bool:
        try:
            import webview

            with self._monitor_lock:
                if self.monitor_window is not None and self._focus_monitor_window():
                    return True
                self.monitor_window = None
                window = webview.create_window(
                    "Kabuki-Cord Scanner Monitor",
                    f"{self.base_url}/monitor.html",
                    width=860,
                    height=820,
                    min_size=(720, 620),
                )
                self.monitor_window = window
                self._watch_monitor_close(window)
            return True
        except Exception:
            return False

    def _focus_monitor_window(self) -> bool:
        window = self.monitor_window
        if window is None:
            return False
        try:
            evaluate_js = getattr(window, "evaluate_js", None)
            if callable(evaluate_js):
                evaluate_js("document.readyState")
            focused = False
            for method_name in ("show", "restore", "bring_to_front"):
                method = getattr(window, method_name, None)
                if callable(method):
                    method()
                    focused = True
            return focused or callable(evaluate_js)
        except Exception:
            self.monitor_window = None
            return False

    def _watch_monitor_close(self, window) -> None:
        events = getattr(window, "events", None)
        closed = getattr(events, "closed", None)
        if closed is None:
            return
        try:
            closed += self._clear_monitor_window
        except Exception:
            return

    def _clear_monitor_window(self, *args) -> None:
        _ = args
        with self._monitor_lock:
            self.monitor_window = None


class GUID(ctypes.Structure):
    _fields_ = [
        ("Data1", wintypes.DWORD),
        ("Data2", wintypes.WORD),
        ("Data3", wintypes.WORD),
        ("Data4", ctypes.c_ubyte * 8),
    ]

    def __init__(self, value: str) -> None:
        super().__init__()
        ctypes.windll.ole32.CLSIDFromString(str(value), ctypes.byref(self))


def set_taskbar_badge(active: bool) -> bool:
    if not hasattr(ctypes, "windll"):
        return False
    try:
        hwnd = _find_kabuki_window()
        if not hwnd:
            return False
        icon = _badge_icon_handle() if active else None
        return _set_taskbar_overlay(hwnd, icon, "Kabuki-Cord activity" if active else "")
    except Exception:
        return False


def _find_kabuki_window() -> int:
    user32 = ctypes.windll.user32
    current_pid = os.getpid()
    matches: list[int] = []

    @ctypes.WINFUNCTYPE(wintypes.BOOL, wintypes.HWND, wintypes.LPARAM)
    def enum_proc(hwnd: int, _lparam: int) -> bool:
        if not user32.IsWindowVisible(hwnd):
            return True
        pid = wintypes.DWORD()
        user32.GetWindowThreadProcessId(hwnd, ctypes.byref(pid))
        if pid.value != current_pid:
            return True
        length = user32.GetWindowTextLengthW(hwnd)
        if length <= 0:
            return True
        buffer = ctypes.create_unicode_buffer(length + 1)
        user32.GetWindowTextW(hwnd, buffer, length + 1)
        if "Kabuki-Cord" in buffer.value:
            matches.append(hwnd)
        return True

    user32.EnumWindows(enum_proc, 0)
    return matches[0] if matches else 0


def _badge_icon_handle() -> int:
    global BADGE_ICON_HANDLE
    if BADGE_ICON_HANDLE:
        return BADGE_ICON_HANDLE
    icon_path = ASSET_ROOT / "taskbar-badge.ico"
    if not icon_path.exists():
        return 0
    load_image = ctypes.windll.user32.LoadImageW
    load_image.restype = wintypes.HANDLE
    BADGE_ICON_HANDLE = load_image(None, str(icon_path), 1, 16, 16, 0x10)
    return int(BADGE_ICON_HANDLE or 0)


def _set_taskbar_overlay(hwnd: int, icon: int | None, description: str) -> bool:
    ole32 = ctypes.windll.ole32
    ole32.CoInitialize(None)
    taskbar = ctypes.c_void_p()
    clsid_taskbar = GUID("{56FDF344-FD6D-11d0-958A-006097C9A090}")
    iid_taskbar3 = GUID("{EA1AFB91-9E28-4B86-90E9-9E9F8A5EEA84}")
    hr = ole32.CoCreateInstance(
        ctypes.byref(clsid_taskbar),
        None,
        1,
        ctypes.byref(iid_taskbar3),
        ctypes.byref(taskbar),
    )
    if hr != 0 or not taskbar.value:
        return False
    vtable = ctypes.cast(taskbar, ctypes.POINTER(ctypes.POINTER(ctypes.c_void_p))).contents
    release = ctypes.WINFUNCTYPE(wintypes.ULONG, ctypes.c_void_p)(vtable[2])
    hr_init = ctypes.WINFUNCTYPE(ctypes.c_long, ctypes.c_void_p)(vtable[3])
    set_overlay_icon = ctypes.WINFUNCTYPE(
        ctypes.c_long,
        ctypes.c_void_p,
        wintypes.HWND,
        wintypes.HANDLE,
        wintypes.LPCWSTR,
    )(vtable[18])
    try:
        hr_init(taskbar)
        result = set_overlay_icon(taskbar, hwnd, icon or 0, description)
        return result == 0
    finally:
        release(taskbar)


def main() -> None:
    server = ThreadingHTTPServer(("127.0.0.1", 0), GuiHandler)
    host, port = server.server_address
    url = f"http://{host}:{port}"
    thread = threading.Thread(target=server.serve_forever, name="kabuki-cord-gui", daemon=True)
    thread.start()

    try:
        import webview
    except Exception:
        webbrowser.open(url)
        try:
            thread.join()
        except KeyboardInterrupt:
            server.shutdown()
        return

    try:
        icon_path = ASSET_ROOT / "app.ico"
        if hasattr(ctypes, "windll"):
            ctypes.windll.shell32.SetCurrentProcessExplicitAppUserModelID("KabukiCord.Desktop")
        window = webview.create_window(
            "Kabuki-Cord",
            url,
            width=1440,
            height=980,
            min_size=(1024, 720),
            js_api=DesktopBridge(url),
        )
        webview.start(icon=str(icon_path) if icon_path.exists() else None)
        _ = window
    finally:
        server.shutdown()


if __name__ == "__main__":
    main()
