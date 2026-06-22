from __future__ import annotations

import re
import subprocess
import sys
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
SKIP_DIRS = {".git", ".venv", ".profiles", ".state", ".local", "__pycache__", "playwright-report", "test-results"}
PATTERNS = {
    "openai_project_key": re.compile(r"sk-proj-[A-Za-z0-9_-]{20,}"),
    "openai_secret_key": re.compile(r"sk-[A-Za-z0-9_-]{20,}"),
    "github_token": re.compile(r"gh[pousr]_[A-Za-z0-9_]{30,}"),
    "discord_token_like": re.compile(r"[MN][A-Za-z\d]{23}\.[\w-]{6}\.[\w-]{27}"),
}
TEXT_SUFFIXES = {
    ".css",
    ".cmd",
    ".cs",
    ".html",
    ".ini",
    ".js",
    ".json",
    ".md",
    ".ps1",
    ".py",
    ".toml",
    ".txt",
    ".yaml",
    ".yml",
}


def main() -> int:
    findings: list[str] = []
    for path in candidate_files():
        if not path.is_file() or any(part in SKIP_DIRS for part in path.parts):
            continue
        if not is_text_candidate(path):
            continue
        text = path.read_text(encoding="utf-8", errors="ignore")
        for name, pattern in PATTERNS.items():
            if pattern.search(text):
                findings.append(f"{path.relative_to(ROOT)}: matched {name}")

    if findings:
        print("Potential secrets found:")
        for finding in findings:
            print(f"- {finding}")
        return 1

    print("No secret patterns found in tracked-text candidates.")
    return 0


def candidate_files() -> list[Path]:
    try:
        result = subprocess.run(
            ["git", "ls-files"],
            cwd=ROOT,
            check=False,
            capture_output=True,
            text=True,
            timeout=20,
        )
    except OSError:
        result = None

    if result and result.returncode == 0 and result.stdout.strip():
        return [ROOT / line for line in result.stdout.splitlines() if line.strip()]

    return [path for path in ROOT.rglob("*") if path.is_file()]


def is_text_candidate(path: Path) -> bool:
    name = path.name.lower()
    if name in {".gitignore", ".env"} or name.startswith(".env."):
        return True
    if path.suffix.lower() in TEXT_SUFFIXES:
        return True
    return path.suffix == ""


if __name__ == "__main__":
    sys.exit(main())
