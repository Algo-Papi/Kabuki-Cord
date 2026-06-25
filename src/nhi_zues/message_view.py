from __future__ import annotations

import re

from .discord_text import clean_discord_display_name, sanitize_outgoing_draft
from .models import MessageRecord


def message_preview(row: dict) -> dict:
    return {
        "server_id": str(row.get("server_id") or ""),
        "channel_id": str(row.get("channel_id") or ""),
        "message_id": str(row.get("message_id") or ""),
        "author": clean_discord_display_name(str(row.get("author") or "unknown")),
        "author_id": row.get("author_id"),
        "user_key": message_user_key(row),
        "text": sanitize_outgoing_draft(str(row.get("text") or "")),
        "observed_at": str(row.get("observed_at") or ""),
    }


def reply_mention_prefix(author: str, author_id) -> str:
    clean_id = str(author_id or "").strip()
    if clean_id:
        return f"<@{clean_id}>"
    return ""


def draft_with_reply_mention(draft: str, source_messages: list[MessageRecord]) -> str:
    draft = sanitize_outgoing_draft(str(draft or "").strip())
    if not draft or not source_messages:
        return draft
    source = source_messages[-1]
    prefix = reply_mention_prefix(source.author, source.author_id)
    if not prefix:
        return draft
    if draft.startswith(prefix) or re.match(r"^<@!?\d+>\s+", draft):
        return draft
    if source.author:
        plain_prefix = f"@{clean_discord_display_name(source.author)}"
        if draft.startswith(plain_prefix):
            return f"{prefix}{draft[len(plain_prefix):]}"
    return f"{prefix} {draft}"


def sorted_message_rows(rows: list[dict]) -> list[dict]:
    return sorted(rows or [], key=message_row_sort_key)


def message_row_sort_key(row: dict) -> tuple[int, str]:
    message_id = str(row.get("message_id") or "")
    try:
        return (int(message_id.rsplit("-", 1)[-1]), message_id)
    except ValueError:
        return (0, message_id)


def message_user_key(row: dict) -> str:
    author_id = row.get("author_id")
    if author_id:
        return f"discord:{author_id}"
    author = normalize_display_author(row.get("author") or "unknown")
    return f"name:{author or 'unknown'}"


def manual_source_messages(
    context: list[MessageRecord],
    target_user_key: str,
    target_message_id: str = "",
) -> list[MessageRecord]:
    if not context:
        return []
    if target_message_id:
        selected = [message for message in context if message.message_id == target_message_id]
        return selected[-1:] if selected else []
    if target_user_key:
        targeted = [
            message
            for message in reversed(context)
            if message_record_user_key(message) == target_user_key
        ]
        return list(reversed(targeted[:2]))
    return [context[-1]]


def message_record_user_key(message: MessageRecord) -> str:
    if message.author_id:
        return f"discord:{message.author_id}"
    return f"name:{normalize_display_author(message.author or 'unknown') or 'unknown'}"


def summarize_messages(texts: list[str]) -> str:
    if not texts:
        return "No recent readable message text."
    terms: list[str] = []
    ignored = {
        "that",
        "this",
        "with",
        "from",
        "they",
        "have",
        "just",
        "like",
        "what",
        "your",
        "about",
        "there",
        "would",
        "could",
        "really",
    }
    for text in texts:
        for raw in text.split():
            term = raw.strip(".,!?;:()[]{}\"'").lower()
            if len(term) >= 5 and term not in ignored and term not in terms:
                terms.append(term)
            if len(terms) >= 5:
                break
        if len(terms) >= 5:
            break
    topic_text = ", ".join(terms) if terms else "the current thread"
    latest = texts[-1]
    if len(latest) > 130:
        latest = latest[:127].rstrip() + "..."
    return f"Talking about {topic_text}. Latest: {latest}"


def normalize_display_author(value: object) -> str:
    return " ".join(
        clean_discord_display_name(str(value or "unknown")).lower().strip().split()
    )
