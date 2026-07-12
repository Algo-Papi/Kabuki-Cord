from __future__ import annotations

import os
from pathlib import Path
from typing import BinaryIO


class RuntimeInstanceLock:
    """Cross-process singleton lock for one Kabuki state directory."""

    def __init__(self, path: Path) -> None:
        self.path = path
        self._handle: BinaryIO | None = None

    def acquire(self) -> None:
        if self._handle is not None:
            return
        self.path.parent.mkdir(parents=True, exist_ok=True)
        handle = self.path.open("a+b")
        if handle.seek(0, os.SEEK_END) == 0:
            handle.write(b"\0")
            handle.flush()
        handle.seek(0)
        try:
            _lock_handle(handle)
        except OSError as exc:
            handle.close()
            raise RuntimeError(
                "Another Kabuki-Cord scanner is already using this local state directory. "
                "Pause or close that runtime before starting another one."
            ) from exc
        self._handle = handle

    def release(self) -> None:
        handle = self._handle
        if handle is None:
            return
        self._handle = None
        try:
            handle.seek(0)
            _unlock_handle(handle)
        finally:
            handle.close()

    def __enter__(self) -> RuntimeInstanceLock:
        self.acquire()
        return self

    def __exit__(self, exc_type, exc, traceback) -> None:
        self.release()


def _lock_handle(handle: BinaryIO) -> None:
    if os.name == "nt":
        import msvcrt

        msvcrt.locking(handle.fileno(), msvcrt.LK_NBLCK, 1)
        return

    import fcntl

    flock = getattr(fcntl, "flock")
    flock(handle.fileno(), getattr(fcntl, "LOCK_EX") | getattr(fcntl, "LOCK_NB"))


def _unlock_handle(handle: BinaryIO) -> None:
    if os.name == "nt":
        import msvcrt

        msvcrt.locking(handle.fileno(), msvcrt.LK_UNLCK, 1)
        return

    import fcntl

    getattr(fcntl, "flock")(handle.fileno(), getattr(fcntl, "LOCK_UN"))
