from __future__ import annotations

import json
import re
import sys
import zipfile
from pathlib import Path, PurePosixPath


ROOT = Path(__file__).resolve().parents[1]
TEXT_SUFFIXES = {
    ".cmd",
    ".css",
    ".env",
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
FORBIDDEN_PARTS = {".git", ".local", ".profiles", ".state", "__pycache__"}
FORBIDDEN_SUFFIXES = {".db", ".har", ".jsonl", ".log", ".sqlite", ".sqlite3"}
PATTERNS = {
    "openai_key": re.compile(r"sk-(?:proj-)?[A-Za-z0-9_-]{20,}"),
    "github_token": re.compile(r"(?:gh[pousr]_|github_pat_)[A-Za-z0-9_]{20,}"),
    "discord_token": re.compile(r"[MN][A-Za-z\d]{23}\.[\w-]{6}\.[\w-]{27}"),
    "discord_webhook": re.compile(
        r"https://(?:canary\.|ptb\.)?discord(?:app)?\.com/api/webhooks/\d+/[A-Za-z0-9_-]+"
    ),
    "private_key": re.compile(r"-----BEGIN (?:RSA |EC |OPENSSH )?PRIVATE KEY-----"),
    "machine_user_path": re.compile(
        r"(?i)\b[A-Z]:[\\/]+Users[\\/]+(?!example\b|username\b|your-name\b)[^\\/\s]+"
    ),
    "private_persona": re.compile(
        r"(?i)st\.? augustine|cigar-shaped craft|call-center job|zyn\.bad|joe rogan"
    ),
}
DEFAULT_CARD_SUFFIX = "src/nhi_zues/defaults/character_cards/default.json"


def main() -> int:
    archive = _archive_path()
    findings: list[str] = []
    default_card: dict | None = None

    with zipfile.ZipFile(archive) as bundle:
        for item in bundle.infolist():
            if item.is_dir():
                continue
            name = item.filename.replace("\\", "/")
            path = PurePosixPath(name)
            lowered_parts = {part.lower() for part in path.parts}
            lowered_name = name.lower()
            if lowered_parts & FORBIDDEN_PARTS:
                findings.append(f"{name}: forbidden private/runtime directory")
            if path.suffix.lower() in FORBIDDEN_SUFFIXES:
                findings.append(f"{name}: forbidden runtime-data suffix")
            if path.name.lower() in {".env", "settings.env"}:
                findings.append(f"{name}: forbidden settings file")
            if lowered_name.endswith("/config/servers.json"):
                findings.append(f"{name}: mutable server configuration")
            if "/character_cards/cards/" in f"/{lowered_name}" or "/character_cards/servers/" in f"/{lowered_name}":
                findings.append(f"{name}: operator-owned character card")

            if name.endswith(DEFAULT_CARD_SUFFIX):
                default_card = json.loads(bundle.read(item).decode("utf-8"))
            if path.suffix.lower() not in TEXT_SUFFIXES:
                continue
            text = bundle.read(item).decode("utf-8", errors="ignore")
            for label, pattern in PATTERNS.items():
                if pattern.search(text):
                    findings.append(f"{name}: matched {label}")

    if default_card is None:
        findings.append(f"missing {DEFAULT_CARD_SUFFIX}")
    elif (
        default_card.get("name") != "Default Character"
        or default_card.get("aliases")
        or default_card.get("trigger_keywords")
    ):
        findings.append(f"{DEFAULT_CARD_SUFFIX}: packaged fallback is not neutral")

    if findings:
        print(f"Release archive verification failed for {archive.name}:")
        for finding in findings:
            print(f"- {finding}")
        return 1
    print(f"Verified release privacy boundary: {archive.name}")
    return 0


def _archive_path() -> Path:
    if len(sys.argv) > 1:
        return Path(sys.argv[1]).expanduser().resolve()
    matches = sorted((ROOT / "dist").glob("Kabuki-Cord-*-windows.zip"))
    if not matches:
        raise SystemExit("No Kabuki-Cord Windows release archive found under dist/.")
    return max(matches, key=lambda path: path.stat().st_mtime)


if __name__ == "__main__":
    raise SystemExit(main())
