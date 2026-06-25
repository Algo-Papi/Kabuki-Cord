from __future__ import annotations

import json
import os
import socket
import subprocess
import sys
import time
import urllib.request


HOST = "127.0.0.1"
BASE_URL = ""


def main() -> int:
    global BASE_URL
    port = open_loopback_port()
    BASE_URL = f"http://{HOST}:{port}"
    env = os.environ.copy()
    env["KABUKI_CORD_HOST"] = HOST
    env["KABUKI_CORD_PORT"] = str(port)
    env["PYTHONUNBUFFERED"] = "1"
    process = subprocess.Popen(
        [sys.executable, "-m", "nhi_zues.gui"],
        env=env,
        stdout=subprocess.PIPE,
        stderr=subprocess.STDOUT,
        text=True,
    )
    try:
        token = wait_for_session_token()
        state = read_json("/api/state", token)
        assert state["app"]["name"] == "Kabuki-Cord", "unexpected app name"
        assert "runtime" in state, "state missing runtime"
        assert_text("/", "Kabuki-Cord")
        assert_text("/app.js", "KabukiUiHelpers")
        assert_text("/js/ui-helpers.js", "KabukiUiHelpers")
        print("Kabuki-Cord GUI smoke test passed.")
        return 0
    finally:
        process.terminate()
        try:
            process.wait(timeout=5)
        except subprocess.TimeoutExpired:
            process.kill()
            process.wait(timeout=5)


def open_loopback_port() -> int:
    with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as server:
        server.bind((HOST, 0))
        return int(server.getsockname()[1])


def wait_for_session_token(timeout_seconds: float = 10.0) -> str:
    deadline = time.monotonic() + timeout_seconds
    last_error: Exception | None = None
    while time.monotonic() < deadline:
        try:
            payload = read_json("/api/session", token="")
            return str(payload["token"])
        except Exception as exc:
            last_error = exc
            time.sleep(0.2)
    raise RuntimeError(f"GUI did not become ready: {last_error}")


def read_json(path: str, token: str) -> dict:
    request = urllib.request.Request(BASE_URL + path)
    if token:
        request.add_header("X-Kabuki-Token", token)
    with urllib.request.urlopen(request, timeout=5) as response:
        return json.loads(response.read().decode("utf-8"))


def assert_text(path: str, expected: str) -> None:
    with urllib.request.urlopen(BASE_URL + path, timeout=5) as response:
        body = response.read().decode("utf-8", errors="replace")
    assert expected in body, f"{path} did not contain {expected!r}"


if __name__ == "__main__":
    raise SystemExit(main())
