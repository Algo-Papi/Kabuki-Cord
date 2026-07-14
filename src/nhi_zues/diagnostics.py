from __future__ import annotations

import json
import logging
import os
import platform
import re
import subprocess
import sys
import zipfile
from datetime import datetime, timezone
from importlib.metadata import PackageNotFoundError, version
from logging.handlers import RotatingFileHandler
from pathlib import Path

from .app_paths import app_data_root
from .config import load_config
from .secrets import discord_credential_status
from .state_io import read_json_file


LOG_NAME = "kabuki-cord.log"
_HANDLER_MARKER = "kabuki_cord_diagnostic_handler"
_SECRET_PATTERNS = (
    (re.compile(r"sk-[A-Za-z0-9_-]{8,}"), "sk-...redacted"),
    (re.compile(r"(?i)(password|token|api[_ -]?key)(\s*[=:]\s*)[^\s,;]+"), r"\1\2[redacted]"),
    (re.compile(r"[\w.+-]+@[\w.-]+\.[A-Za-z]{2,}"), "[email redacted]"),
    (re.compile(r"https://discord\.com/channels/\d+/\d+(?:/\d+)?"), "https://discord.com/channels/[redacted]"),
    (re.compile(r"(?<!\d)\d{16,20}(?!\d)"), "[discord-id redacted]"),
)


def redact_diagnostic_text(value: str) -> str:
    cleaned = str(value or "")
    for pattern, replacement in _SECRET_PATTERNS:
        cleaned = pattern.sub(replacement, cleaned)
    return cleaned


class DiagnosticRedactionFilter(logging.Filter):
    def filter(self, record: logging.LogRecord) -> bool:
        try:
            record.msg = redact_diagnostic_text(record.getMessage())
            record.args = ()
        except Exception:
            record.msg = "[log message could not be formatted]"
            record.args = ()
        return True


def configure_diagnostic_logging(state_dir: Path | None = None) -> Path:
    directory = (state_dir or load_config().state_dir) / "logs"
    directory.mkdir(parents=True, exist_ok=True)
    path = directory / LOG_NAME
    root = logging.getLogger()
    for handler in root.handlers:
        if getattr(handler, _HANDLER_MARKER, False):
            return path
    handler = RotatingFileHandler(path, maxBytes=2_000_000, backupCount=5, encoding="utf-8")
    setattr(handler, _HANDLER_MARKER, True)
    # Activity is captured separately in the content-free app.log. The rotating
    # diagnostic log intentionally stores only warnings/errors to avoid copying
    # normal conversation-routing detail into a support bundle.
    handler.setLevel(logging.WARNING)
    handler.setFormatter(logging.Formatter("%(asctime)s %(levelname)s %(name)s: %(message)s"))
    handler.addFilter(DiagnosticRedactionFilter())
    root.addHandler(handler)
    return path


def collect_diagnostics(*, open_folder: bool = True) -> dict[str, str | bool]:
    config = load_config()
    configure_diagnostic_logging(config.state_dir)
    output_dir = app_data_root() / "diagnostics"
    output_dir.mkdir(parents=True, exist_ok=True)
    stamp = datetime.now().strftime("%Y%m%d-%H%M%S")
    archive = output_dir / f"Kabuki-Cord-Diagnostics-{stamp}.zip"

    snapshot = _diagnostic_snapshot()
    readme = (
        "Kabuki-Cord local diagnostic bundle\n"
        "===================================\n\n"
        "This bundle was created on this PC and was not uploaded anywhere.\n"
        "It contains redacted application logs and a configuration summary; it does not include\n"
        "Discord message text, character cards, stored passwords, API keys, or the browser profile.\n"
        "Review the files before sharing them manually with a support person.\n"
    )

    with zipfile.ZipFile(archive, "w", compression=zipfile.ZIP_DEFLATED) as bundle:
        bundle.writestr("README.txt", readme)
        bundle.writestr("diagnostics.json", json.dumps(snapshot, indent=2, sort_keys=True))
        candidates = [config.state_dir / "app.log"]
        log_dir = config.state_dir / "logs"
        candidates.extend(sorted(log_dir.glob(f"{LOG_NAME}*")))
        for path in candidates:
            if not path.is_file():
                continue
            try:
                content = path.read_text(encoding="utf-8", errors="replace")[-1_000_000:]
            except OSError:
                continue
            bundle.writestr(f"logs/{path.name}.txt", redact_diagnostic_text(content))

    opened = open_diagnostics_folder(select=archive) if open_folder else False
    return {
        "ok": True,
        "filename": archive.name,
        "folder": str(output_dir),
        "opened": opened,
        "message": "Logs collected locally. Nothing was uploaded.",
    }


def open_diagnostics_folder(*, select: Path | None = None) -> bool:
    folder = app_data_root() / "diagnostics"
    folder.mkdir(parents=True, exist_ok=True)
    try:
        if os.name == "nt":
            args = ["explorer.exe", str(folder)]
            if select is not None and select.exists():
                args = ["explorer.exe", f"/select,{select}"]
            subprocess.Popen(args)
        elif sys.platform == "darwin":
            subprocess.Popen(["open", str(folder)])
        else:
            subprocess.Popen(["xdg-open", str(folder)])
        return True
    except OSError:
        return False


def _diagnostic_snapshot() -> dict:
    config = load_config()
    servers_payload = read_json_file(config.servers_file, default={"servers": []})
    servers = servers_payload.get("servers", []) if isinstance(servers_payload, dict) else []
    channels = [channel for server in servers if isinstance(server, dict) for channel in server.get("channels", []) if isinstance(channel, dict)]
    credentials = discord_credential_status()
    return {
        "created_at": datetime.now(timezone.utc).isoformat(),
        "app_version": _package_version(),
        "platform": platform.platform(),
        "python": platform.python_version(),
        "configuration": {
            "response_mode": config.runtime_mode,
            "headless_browser": config.headless,
            "llm_enabled": config.llm_enabled,
            "api_key_configured": bool(config.openai_api_key),
            "discord_email_configured": bool(credentials.get("email_set")),
            "discord_password_configured": bool(credentials.get("password_set")),
            "server_count": len(servers),
            "channel_count": len(channels),
            "observe_channel_count": sum(bool(channel.get("scan_enabled")) for channel in channels),
            "react_channel_count": sum(bool(channel.get("react_enabled")) for channel in channels),
            "engage_channel_count": sum(bool(channel.get("engage_enabled")) for channel in channels),
            "auto_channel_count": sum(bool(channel.get("auto_respond_enabled")) for channel in channels),
        },
    }


def _package_version() -> str:
    try:
        return version("kabuki-cord")
    except PackageNotFoundError:
        try:
            from . import __version__

            return __version__
        except ImportError:
            return "unknown"
