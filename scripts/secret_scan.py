from __future__ import annotations

import re
import subprocess
import sys
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
SKIP_DIRS = {
    ".git",
    ".venv",
    ".profiles",
    ".state",
    ".local",
    "__pycache__",
    "build",
    "dist",
    "output",
    "playwright-report",
    "test-results",
    "tmp",
}
PATTERNS = {
    "openai_project_key": re.compile(r"sk-proj-[A-Za-z0-9_-]{20,}"),
    "openai_secret_key": re.compile(r"sk-[A-Za-z0-9_-]{20,}"),
    "github_token": re.compile(r"(?:gh[pousr]_|github_pat_)[A-Za-z0-9_]{20,}"),
    "discord_token_like": re.compile(r"[MN][A-Za-z\d]{23}\.[\w-]{6}\.[\w-]{27}"),
    "discord_webhook": re.compile(r"https://(?:canary\.|ptb\.)?discord(?:app)?\.com/api/webhooks/\d+/[A-Za-z0-9_-]+"),
    "private_key": re.compile(r"-----BEGIN (?:RSA |EC |OPENSSH )?PRIVATE KEY-----"),
    "aws_access_key": re.compile(r"\b(?:AKIA|ASIA)[A-Z0-9]{16}\b"),
    "machine_user_path": re.compile(r"(?i)\b[A-Z]:[\\/]+Users[\\/]+(?!example\b|username\b|your-name\b)[^\\/\s]+"),
}
DISCORD_SNOWFLAKE = re.compile(r"(?<!\d)\d{17,20}(?!\d)")
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
    ".svg",
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
        relative = path.relative_to(ROOT).as_posix()
        lowered = relative.lower()
        if (
            lowered in {".env", "settings.env", "config/servers.json"}
            or lowered.startswith((".local/", ".profiles/", ".state/", "character_cards/"))
        ):
            findings.append(f"{relative}: forbidden private/runtime path")
            continue
        if not is_text_candidate(path):
            continue
        text = path.read_text(encoding="utf-8", errors="ignore")
        for name, pattern in PATTERNS.items():
            if pattern.search(text):
                findings.append(f"{relative}: matched {name}")
        if path.suffix.lower() == ".json" and DISCORD_SNOWFLAKE.search(text):
            findings.append(f"{relative}: real-looking Discord snowflake in publishable JSON")

    if findings:
        print("Potential secrets found:")
        for finding in findings:
            print(f"- {finding}")
        return 1

    print("No secret patterns found in tracked or unignored text candidates.")
    return 0


def candidate_files() -> list[Path]:
    try:
        result = subprocess.run(
            ["git", "ls-files", "--cached", "--others", "--exclude-standard", "-z"],
            cwd=ROOT,
            check=False,
            capture_output=True,
            timeout=20,
        )
    except OSError:
        result = None

    if result and result.returncode == 0 and result.stdout.strip():
        names = result.stdout.decode("utf-8", errors="surrogateescape").split("\0")
        return [ROOT / name for name in names if name]

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
