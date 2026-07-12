from __future__ import annotations

import json
import os
import copy
import sqlite3
import threading
import time
from collections.abc import Callable
from contextlib import closing
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, TypeVar


T = TypeVar("T")
_DATABASE_LOCKS: dict[Path, threading.RLock] = {}
_DATABASE_LOCKS_GUARD = threading.Lock()


def read_json_file(path: Path, *, default: T) -> dict[str, Any] | T:
    """Read a state document, importing a legacy JSON file on first use."""
    database = _database_path(path)
    key = _document_key(path, database)
    with _database_lock(database), closing(_connect(database)) as connection:
        row = connection.execute(
            "SELECT payload FROM documents WHERE document_key = ?",
            (key,),
        ).fetchone()
        if row is not None:
            return json.loads(str(row[0]))
        payload = _read_legacy_json(path, default=default)
        _upsert(connection, key, payload)
        connection.commit()
        return payload


def mutate_json_file(
    path: Path,
    *,
    default: dict[str, Any],
    mutator: Callable[[dict[str, Any]], T],
    indent: int = 2,
) -> tuple[dict[str, Any], T]:
    """Mutate one state document under an immediate SQLite transaction."""
    database = _database_path(path)
    key = _document_key(path, database)
    with _database_lock(database), closing(_connect(database)) as connection:
        connection.execute("BEGIN IMMEDIATE")
        row = connection.execute(
            "SELECT payload FROM documents WHERE document_key = ?",
            (key,),
        ).fetchone()
        payload = (
            json.loads(str(row[0]))
            if row is not None
            else _read_legacy_json(path, default=default)
        )
        result = mutator(payload)
        _upsert(connection, key, payload)
        _write_json_mirror(path, payload, indent=indent)
        connection.commit()
    return payload, result


def write_json_file(path: Path, payload: dict, *, indent: int = 2) -> None:
    database = _database_path(path)
    key = _document_key(path, database)
    with _database_lock(database), closing(_connect(database)) as connection:
        connection.execute("BEGIN IMMEDIATE")
        _upsert(connection, key, payload)
        _write_json_mirror(path, payload, indent=indent)
        connection.commit()


def try_write_json_file(path: Path, payload: dict, *, indent: int = 2) -> bool:
    try:
        write_json_file(path, payload, indent=indent)
        return True
    except (OSError, sqlite3.Error) as exc:
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


def _connect(database: Path) -> sqlite3.Connection:
    database.parent.mkdir(parents=True, exist_ok=True)
    connection = sqlite3.connect(database, timeout=15.0, isolation_level=None)
    connection.execute("PRAGMA journal_mode=WAL")
    connection.execute("PRAGMA synchronous=NORMAL")
    connection.execute("PRAGMA busy_timeout=15000")
    connection.execute(
        """
        CREATE TABLE IF NOT EXISTS documents (
            document_key TEXT PRIMARY KEY,
            payload TEXT NOT NULL,
            updated_at TEXT NOT NULL
        )
        """
    )
    return connection


def _database_path(path: Path) -> Path:
    resolved = _canonical_path(path)
    for parent in (resolved.parent, *resolved.parents):
        if parent.name.lower() in {"state", ".state"}:
            return parent / "state.db"
    return resolved.parent / "state.db"


def _document_key(path: Path, database: Path) -> str:
    resolved = _canonical_path(path)
    try:
        return resolved.relative_to(database.parent).as_posix()
    except ValueError:
        return resolved.as_posix()


def _database_lock(database: Path) -> threading.RLock:
    with _DATABASE_LOCKS_GUARD:
        return _DATABASE_LOCKS.setdefault(database, threading.RLock())


def _canonical_path(path: Path) -> Path:
    resolved = str(path.expanduser().resolve())
    if resolved.startswith("\\\\?\\UNC\\"):
        resolved = "\\\\" + resolved[8:]
    elif resolved.startswith("\\\\?\\"):
        resolved = resolved[4:]
    return Path(os.path.normcase(resolved) if os.name == "nt" else resolved)


def _read_legacy_json(path: Path, *, default: T) -> dict[str, Any] | T:
    if not path.exists():
        return copy.deepcopy(default)
    return json.loads(path.read_text(encoding="utf-8-sig"))


def _upsert(connection: sqlite3.Connection, key: str, payload: Any) -> None:
    connection.execute(
        """
        INSERT INTO documents(document_key, payload, updated_at)
        VALUES (?, ?, ?)
        ON CONFLICT(document_key) DO UPDATE SET
            payload = excluded.payload,
            updated_at = excluded.updated_at
        """,
        (
            key,
            json.dumps(payload, ensure_ascii=False, separators=(",", ":")),
            datetime.now(timezone.utc).isoformat(),
        ),
    )


def _write_json_mirror(path: Path, payload: Any, *, indent: int) -> None:
    # Human-readable mirrors keep V1 tooling and recovery workflows compatible.
    write_text_file(
        path,
        json.dumps(payload, indent=indent, ensure_ascii=False),
        encoding="utf-8",
    )
