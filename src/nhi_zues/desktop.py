from __future__ import annotations

import threading
import webbrowser
from http.server import ThreadingHTTPServer

from .gui import GuiHandler


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
        window = webview.create_window(
            "Kabuki-Cord",
            url,
            width=1440,
            height=980,
            min_size=(1180, 720),
        )
        webview.start()
        _ = window
    finally:
        server.shutdown()


if __name__ == "__main__":
    main()
