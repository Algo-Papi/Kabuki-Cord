from __future__ import annotations

import subprocess
import unittest
from unittest.mock import patch

from nhi_zues.gui import check_update


class UpdateCheckTests(unittest.TestCase):
    def test_diverged_checkout_is_not_advertised_as_fast_forwardable(self) -> None:
        git = FakeGit(behind=2, ahead=1)

        with patch("nhi_zues.gui._git", side_effect=git):
            result = check_update(apply_update=False)

        self.assertTrue(result["ok"])
        self.assertTrue(result["update_available"])
        self.assertFalse(result["can_fast_forward"])

    def test_apply_refuses_diverged_checkout_before_pull(self) -> None:
        git = FakeGit(behind=2, ahead=1)

        with patch("nhi_zues.gui._git", side_effect=git):
            result = check_update(apply_update=True)

        self.assertFalse(result["ok"])
        self.assertIn("diverged", result["error"])
        self.assertNotIn(("pull", "--ff-only", "origin", "main"), git.calls)


class FakeGit:
    def __init__(self, *, behind: int, ahead: int) -> None:
        self.behind = behind
        self.ahead = ahead
        self.calls: list[tuple[str, ...]] = []

    def __call__(self, args: list[str], *, check: bool = True) -> subprocess.CompletedProcess[str]:
        _ = check
        command = tuple(args)
        self.calls.append(command)
        stdout = ""
        if command == ("rev-parse", "--is-inside-work-tree"):
            stdout = "true\n"
        elif command == ("remote", "get-url", "origin"):
            stdout = "https://github.com/Algo-Papi/Kabuki-Cord.git\n"
        elif command == ("rev-parse", "HEAD"):
            stdout = "local-head\n"
        elif command == ("rev-parse", "origin/main"):
            stdout = "remote-head\n"
        elif command == ("rev-list", "--count", "HEAD..origin/main"):
            stdout = f"{self.behind}\n"
        elif command == ("rev-list", "--count", "origin/main..HEAD"):
            stdout = f"{self.ahead}\n"
        elif command == ("pull", "--ff-only", "origin", "main"):
            raise AssertionError("A diverged checkout must not reach git pull.")
        return subprocess.CompletedProcess(["git", *args], 0, stdout=stdout, stderr="")


if __name__ == "__main__":
    unittest.main()
