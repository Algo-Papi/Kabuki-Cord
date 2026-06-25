from __future__ import annotations

import re


def redact_secret_text(value: str) -> str:
    return re.sub(r"sk-[A-Za-z0-9_\-]{8,}", "sk-...redacted", str(value or ""))
