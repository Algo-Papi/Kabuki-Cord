from __future__ import annotations

import re

from .discord_text import sanitize_outgoing_draft


HIGH_RISK_PATTERNS: tuple[tuple[re.Pattern[str], str], ...] = (
    (re.compile(r"\bmacacos?\b", re.IGNORECASE), "racial or ethnic slur"),
    (re.compile(r"\bjews?\b", re.IGNORECASE), "identity-group escalation"),
    (re.compile(r"\bantisemit(?:e|ic|ism)\b", re.IGNORECASE), "antisemitism-related escalation"),
    (re.compile(r"\bsam\s+hyde\b", re.IGNORECASE), "edgy extremist-coded reference"),
    (re.compile(r"\b(?:nazi|nazis|nazism|hitler)\b", re.IGNORECASE), "extremist reference"),
    (re.compile(r"\bretard(?:ed)?\b", re.IGNORECASE), "ableist insult"),
    (re.compile(r"\bshoot(?:ing)?\s+(?:a\s+)?baby\b", re.IGNORECASE), "graphic violence against a child"),
)


def outgoing_block_reason(text: str) -> str:
    cleaned = sanitize_outgoing_draft(text)
    if not cleaned:
        return ""
    for pattern, label in HIGH_RISK_PATTERNS:
        if pattern.search(cleaned):
            return (
                "Output guard blocked this draft because it contains a high-risk "
                f"{label}. Regenerate or edit it before sending."
            )
    return ""
