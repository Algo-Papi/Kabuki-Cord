from __future__ import annotations

import re
from difflib import SequenceMatcher
from typing import Iterable

from .discord_text import clean_discord_display_name, sanitize_outgoing_draft
from .models import MessageRecord


LEADING_MENTION_RE = re.compile(r"^(?:<@!?\d+>|@\S+)\s+")
WORD_RE = re.compile(r"\b[a-z0-9']+\b")
POINT_STOPWORDS = {
    "about",
    "after",
    "again",
    "also",
    "because",
    "been",
    "being",
    "could",
    "does",
    "dont",
    "even",
    "from",
    "have",
    "just",
    "like",
    "make",
    "more",
    "much",
    "that",
    "thats",
    "their",
    "them",
    "then",
    "there",
    "they",
    "this",
    "what",
    "when",
    "where",
    "with",
    "would",
    "your",
}


def normalize_author(value: str) -> str:
    return " ".join(clean_discord_display_name(str(value or "")).lower().split())


def normalize_message_text(value: str) -> str:
    text = " ".join(sanitize_outgoing_draft(str(value or "")).lower().split())
    previous = None
    while text and text != previous:
        previous = text
        text = LEADING_MENTION_RE.sub("", text).strip()
    text = re.sub(r"[^\w\s']", " ", text)
    return " ".join(text.split())


def is_character_author(author: str, character_names: tuple[str, ...]) -> bool:
    cleaned_author = normalize_author(author)
    if not cleaned_author:
        return False
    exact_names = {normalize_author(name) for name in character_names if name}
    if cleaned_author in exact_names:
        return True
    prefix_names = {name for name in exact_names if len(name.replace(" ", "")) >= 5}
    if any(cleaned_author.startswith(f"{name} ") for name in prefix_names if name):
        return True
    compact_author = cleaned_author.replace(" ", "")
    compact_names = {name.replace(" ", "") for name in prefix_names}
    return bool(
        compact_author
        and (
            compact_author in compact_names
            or any(compact_author.startswith(name) for name in compact_names)
        )
    )


def is_own_message(
    message: MessageRecord,
    *,
    character_names: tuple[str, ...],
    own_author_ids: set[str] | None = None,
    own_message_ids: set[str] | None = None,
    own_texts: Iterable[str] | None = None,
) -> bool:
    author_id = str(getattr(message, "author_id", "") or "").strip()
    if author_id and author_id in (own_author_ids or set()):
        return True
    message_id = str(getattr(message, "message_id", "") or "").strip()
    if message_id and message_id in (own_message_ids or set()):
        return True
    if is_character_author(getattr(message, "author", ""), character_names):
        return True
    return message_text_matches_own(getattr(message, "text", ""), own_texts or ())


def own_author_ids_from_messages(
    messages: Iterable[MessageRecord],
    *,
    character_names: tuple[str, ...],
    own_texts: Iterable[str] | None = None,
) -> set[str]:
    own_ids: set[str] = set()
    for message in messages or []:
        if not (
            is_character_author(getattr(message, "author", ""), character_names)
            or message_text_matches_own(getattr(message, "text", ""), own_texts or ())
        ):
            continue
        author_id = str(getattr(message, "author_id", "") or "").strip()
        if author_id:
            own_ids.add(author_id)
    return own_ids


def without_own_messages(
    messages: Iterable[MessageRecord],
    *,
    character_names: tuple[str, ...],
    own_author_ids: set[str] | None = None,
    own_message_ids: set[str] | None = None,
    own_texts: Iterable[str] | None = None,
) -> list[MessageRecord]:
    return [
        message
        for message in messages
        if not is_own_message(
            message,
            character_names=character_names,
            own_author_ids=own_author_ids,
            own_message_ids=own_message_ids,
            own_texts=own_texts,
        )
    ]


def recent_own_messages(
    messages: Iterable[MessageRecord],
    *,
    character_names: tuple[str, ...],
    own_author_ids: set[str] | None = None,
    own_message_ids: set[str] | None = None,
    own_texts: Iterable[str] | None = None,
    limit: int = 8,
) -> list[MessageRecord]:
    matched = [
        message
        for message in messages
        if is_own_message(
            message,
            character_names=character_names,
            own_author_ids=own_author_ids,
            own_message_ids=own_message_ids,
            own_texts=own_texts,
        )
        and str(getattr(message, "text", "") or "").strip()
    ]
    return matched[-limit:]


def normalized_own_texts(texts: Iterable[str]) -> set[str]:
    return {text for text in (normalize_message_text(value) for value in texts or []) if text}


def message_text_matches_own(text: str, own_texts: Iterable[str]) -> bool:
    current = normalize_message_text(text)
    if not current:
        return False
    known = normalized_own_texts(own_texts)
    if current in known:
        return True
    for own in known:
        if not own:
            continue
        shorter = min(len(current), len(own))
        if shorter < 36:
            continue
        if current.endswith(own) or own.endswith(current):
            return True
        if SequenceMatcher(None, current, own).ratio() >= 0.9:
            return True
    return False


def repeated_own_point_issue(draft: str, recent_own_lines: Iterable[str]) -> str:
    current = _point_terms(draft)
    if len(current) < 5:
        return ""
    for line in recent_own_lines:
        previous = _point_terms(line)
        if len(previous) < 5:
            continue
        overlap = len(current.intersection(previous))
        if overlap >= 5 and overlap / max(1, min(len(current), len(previous))) >= 0.72:
            return "repeats the same point the character already made in this channel"
    return ""


def _point_terms(value: str) -> set[str]:
    normalized = normalize_message_text(value)
    return {
        token
        for token in WORD_RE.findall(normalized)
        if len(token) >= 4 and token not in POINT_STOPWORDS
    }
