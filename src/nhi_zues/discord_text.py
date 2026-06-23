from __future__ import annotations

import re


SERVER_TAG_RE = re.compile(
    r"\b(?:Server|Guild)\s+Tag:\s*[^\s,\n\r]+(?:\s*\([^)]{1,80}\))?",
    flags=re.IGNORECASE,
)
ROLE_TAG_RE = re.compile(r"\s*\[[A-Z0-9][A-Z0-9 _-]{1,24}\]\s*,?", flags=re.IGNORECASE)
LEADING_METADATA_MENTION_RE = re.compile(
    r"^@\s*.*?\b(?:Server|Guild)\s+Tag:\s*[^\s,\n\r]+(?:\s*\([^)]{1,80}\))?"
    r"(?:\s+\b(?:Server|Guild)\s+Tag:\s*[^\s,\n\r]+(?:\s*\([^)]{1,80}\))?)*\s+",
    flags=re.IGNORECASE,
)


def contains_discord_metadata(value: str) -> bool:
    return bool(SERVER_TAG_RE.search(_normalize_spacing(value)))


def strip_discord_metadata(value: str) -> str:
    text = _normalize_spacing(value)
    text = SERVER_TAG_RE.sub("", text)
    text = re.sub(r"\s+,", ",", text)
    text = re.sub(r",\s*,", ",", text)
    text = re.sub(r"\s{2,}", " ", text)
    return text.strip(" ,")


def clean_discord_display_name(value: str) -> str:
    text = strip_discord_metadata(value)
    text = ROLE_TAG_RE.sub(" ", text)
    cleaned = []
    for char in text:
        if char.isalnum() or char in " ._-'":
            cleaned.append(char)
        elif char.isspace():
            cleaned.append(" ")
    text = re.sub(r"\s{2,}", " ", "".join(cleaned)).strip(" ._-'")
    return text[:48].strip() or "unknown"


def sanitize_outgoing_draft(value: str) -> str:
    text = _normalize_spacing(value).strip()
    text = LEADING_METADATA_MENTION_RE.sub("", text)
    text = strip_discord_metadata(text)
    text = ROLE_TAG_RE.sub(" ", text)
    text = re.sub(r"\s{2,}", " ", text)
    return text.strip()


def _normalize_spacing(value: str) -> str:
    return str(value or "").replace("\xa0", " ").replace("\u200b", "").strip()
