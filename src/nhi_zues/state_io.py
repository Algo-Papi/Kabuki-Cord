from __future__ import annotations

import json
import os
import threading
import time
from datetime import datetime, timezone
from pathlib import Path


def write_json_file(path: Path, payload: dict, *, indent: int = 2) -> None:
    write_text_file(path, json.dumps(payload, indent=indent), encoding="utf-8")


def try_write_json_file(path: Path, payload: dict, *, indent: int = 2) -> bool:
    try:
        write_json_file(path, payload, indent=indent)
        return True
    except OSError as exc:
        append_state_log(
            path.parent / "app.log",
            event_type="state_write_failed",
            summary=f"Could not write {path.name}: {exc}",
        )
        return False


def write_text_file(
    path: Path,
    text: str,
    *,
    encoding: str = "utf-8",
    attempts: int = 8,
    base_delay_seconds: float = 0.08,
) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    last_error: OSError | None = None
    for attempt in range(max(1, attempts)):
        tmp_path = path.with_name(
            f".{path.name}.{os.getpid()}.{threading.get_ident()}.{attempt}.tmp"
        )
        try:
            tmp_path.write_text(text, encoding=encoding)
            tmp_path.replace(path)
            return
        except OSError as exc:
            last_error = exc
            try:
                tmp_path.unlink(missing_ok=True)
            except OSError:
                pass
            if attempt < attempts - 1:
                time.sleep(base_delay_seconds * (attempt + 1))
    if last_error is not None:
        raise last_error


def append_state_log(path: Path, *, event_type: str, summary: str) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    timestamp = datetime.now(timezone.utc).isoformat()
    line = (
        f"{timestamp} | {event_type} | server=\"\" | channel=\"\" | "
        f"summary={json.dumps(str(summary or ''), ensure_ascii=False)}\n"
    )
    try:
        with path.open("a", encoding="utf-8") as handle:
            handle.write(line)
    except OSError:
        return
