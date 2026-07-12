from __future__ import annotations

import unittest
from tempfile import TemporaryDirectory
from pathlib import Path

from nhi_zues.runtime_lock import RuntimeInstanceLock


class RuntimeInstanceLockTests(unittest.TestCase):
    def test_only_one_runtime_can_hold_a_state_directory_lock(self) -> None:
        with TemporaryDirectory() as tmp:
            path = Path(tmp) / "runtime.lock"
            first = RuntimeInstanceLock(path)
            second = RuntimeInstanceLock(path)

            first.acquire()
            with self.assertRaisesRegex(RuntimeError, "already using this local state"):
                second.acquire()

            first.release()
            second.acquire()
            second.release()

    def test_context_manager_releases_after_an_error(self) -> None:
        with TemporaryDirectory() as tmp:
            path = Path(tmp) / "runtime.lock"
            with self.assertRaisesRegex(ValueError, "boom"):
                with RuntimeInstanceLock(path):
                    raise ValueError("boom")

            with RuntimeInstanceLock(path):
                pass


if __name__ == "__main__":
    unittest.main()
