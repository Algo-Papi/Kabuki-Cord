from __future__ import annotations

import hashlib
import re
from dataclasses import asdict, dataclass, field
from datetime import datetime, timezone
from functools import lru_cache
from pathlib import Path

from .models import MessageRecord
from .state_io import mutate_json_file, read_json_file, try_write_json_file


@dataclass(frozen=True)
class SafetyReviewFinding:
    message: MessageRecord
    category: str
    severity: str
    reason: str
    matched_cues: tuple[str, ...] = field(default_factory=tuple)


@dataclass(frozen=True)
class SafetyReviewItem:
    review_id: str
    created_at: str
    status: str
    server_id: str
    server_label: str
    channel_id: str
    channel_label: str
    message_id: str
    message_link: str
    author: str
    author_id: str
    text: str
    category: str
    severity: str
    reason: str
    matched_cues: tuple[str, ...] = field(default_factory=tuple)
    dismissed_at: str = ""


class SafetyReviewQueue:
    def __init__(
        self,
        queue_file: Path,
        *,
        max_items: int = 10,
        max_history_items: int = 1000,
    ) -> None:
        self.queue_file = queue_file
        self.max_items = max(1, max_items)
        self.max_history_items = max(self.max_items, max_history_items)
        self._items = self._load()
        if self._prune():
            self._save()

    def add_findings(
        self,
        *,
        server_id: str,
        server_label: str,
        channel_id: str,
        channel_label: str,
        findings: list[SafetyReviewFinding],
    ) -> list[SafetyReviewItem]:
        def add_rows(payload: dict) -> list[SafetyReviewItem]:
            items = _items_from_payload(payload)
            added: list[SafetyReviewItem] = []
            existing_ids = {item.review_id for item in items}
            for finding in findings:
                if sum(1 for item in items if item.status == "open") >= self.max_items:
                    break
                message = finding.message
                review_id = _review_id(
                    server_id=server_id,
                    channel_id=channel_id,
                    message_id=message.message_id,
                    category=finding.category,
                )
                if review_id in existing_ids:
                    continue
                item = SafetyReviewItem(
                    review_id=review_id,
                    created_at=datetime.now(timezone.utc).isoformat(),
                    status="open",
                    server_id=str(server_id),
                    server_label=str(server_label or ""),
                    channel_id=str(channel_id),
                    channel_label=str(channel_label or ""),
                    message_id=str(message.message_id or ""),
                    message_link=_discord_message_link(server_id, channel_id, message.message_id),
                    author=str(message.author or ""),
                    author_id=str(message.author_id or ""),
                    text=str(message.text or ""),
                    category=finding.category,
                    severity=finding.severity,
                    reason=finding.reason,
                    matched_cues=finding.matched_cues,
                )
                items.append(item)
                existing_ids.add(review_id)
                added.append(item)
            items = _pruned_items(items, self.max_items, self.max_history_items)
            payload["items"] = [_serialize_item(item) for item in items]
            return added

        _, added = mutate_json_file(
            self.queue_file,
            default={"items": []},
            mutator=add_rows,
        )
        self._items = self._load()
        return added

    def list(self, *, include_dismissed: bool = False) -> list[SafetyReviewItem]:
        self._items = self._load()
        items = self._items if include_dismissed else [item for item in self._items if item.status == "open"]
        return sorted(items, key=lambda item: item.created_at, reverse=True)

    def dismiss(self, review_ids: list[str], *, all_open: bool = False) -> int:
        requested = {str(value).strip() for value in review_ids if str(value or "").strip()}
        def dismiss_rows(payload: dict) -> int:
            dismissed = 0
            now = datetime.now(timezone.utc).isoformat()
            updated: list[SafetyReviewItem] = []
            for item in _items_from_payload(payload):
                should_dismiss = item.status == "open" and (all_open or item.review_id in requested)
                if not should_dismiss:
                    updated.append(item)
                    continue
                dismissed += 1
                updated.append(
                    SafetyReviewItem(
                        **{**asdict(item), "status": "dismissed", "dismissed_at": now}
                    )
                )
            payload["items"] = [_serialize_item(item) for item in updated]
            return dismissed

        _, dismissed = mutate_json_file(
            self.queue_file,
            default={"items": []},
            mutator=dismiss_rows,
        )
        self._items = self._load()
        return dismissed

    def state(self) -> dict:
        open_items = self.list()
        return {
            "items": [_serialize_item(item) for item in open_items],
            "open_count": len(open_items),
            "max_open_count": self.max_items,
        }

    def _load(self) -> list[SafetyReviewItem]:
        payload = read_json_file(self.queue_file, default={"items": []})
        return _items_from_payload(payload)

    def _save(self) -> None:
        self.queue_file.parent.mkdir(parents=True, exist_ok=True)
        try_write_json_file(
            self.queue_file,
            {"items": [_serialize_item(item) for item in self._items]},
        )

    def _prune(self) -> bool:
        if len(self._items) <= self.max_history_items and self._open_count() <= self.max_items:
            return False
        open_items = [item for item in self._items if item.status == "open"][-self.max_items :]
        closed_items = [item for item in self._items if item.status != "open"]
        keep_closed_count = max(0, self.max_history_items - len(open_items))
        kept_closed = closed_items[-keep_closed_count:] if keep_closed_count else []
        self._items = [*kept_closed, *open_items]
        return True

    def _open_count(self) -> int:
        return sum(1 for item in self._items if item.status == "open")


def detect_safety_review_findings(
    messages: list[MessageRecord],
    *,
    per_cue_limit: int = 5,
) -> list[SafetyReviewFinding]:
    findings: list[SafetyReviewFinding] = []
    cue_counts: dict[str, int] = {}
    for message in messages:
        text = str(message.text or "")
        if not text.strip():
            continue
        normalized = _normalize_text(text)
        matched: list[_SafetyPattern] = []
        for pattern in SAFETY_PATTERNS:
            if pattern.matches(normalized):
                matched.append(pattern)
        if not matched:
            continue
        strongest = _strongest_pattern(matched)
        cue_count = cue_counts.get(strongest.label, 0)
        if cue_count >= per_cue_limit:
            continue
        cue_counts[strongest.label] = cue_count + 1
        findings.append(
            SafetyReviewFinding(
                message=message,
                category=strongest.category,
                severity=strongest.severity,
                reason=strongest.reason,
                matched_cues=tuple(pattern.label for pattern in matched[:5]),
            )
        )
    return findings


@dataclass(frozen=True)
class _SafetyPattern:
    label: str
    category: str
    severity: str
    reason: str
    regex: re.Pattern[str] | None = None
    compact_terms: tuple[str, ...] = ()

    def matches(self, normalized: str) -> bool:
        if self.regex is not None and self.regex.search(normalized):
            return True
        # Match punctuation/spacing-obfuscated terms while preserving alphabetic
        # boundaries.  Searching the fully compacted message made a term such as
        # "spic" match the middle of the ordinary word "suspicious".
        return any(_obfuscated_term_pattern(term).search(normalized) for term in self.compact_terms)


SAFETY_PATTERNS: tuple[_SafetyPattern, ...] = (
    _SafetyPattern(
        label="direct self-harm abuse",
        category="Harassment / self-harm abuse",
        severity="high",
        reason="Message appears to tell a person to harm or kill themselves.",
        regex=re.compile(r"\b(kys|kill\s+yourself|go\s+die)\b", re.IGNORECASE),
    ),
    _SafetyPattern(
        label="violent threat",
        category="Violent threat",
        severity="high",
        reason="Message appears to advocate or threaten violence toward a person or group.",
        regex=re.compile(
            r"\b(kill|hang|gas|shoot|exterminate|wipe\s+out)\s+(all\s+)?(you|them|those|these|people|"
            r"jews|muslims|christians|immigrants|gays|trans|women|men|black|white|asian|mexicans)\b",
            re.IGNORECASE,
        ),
    ),
    _SafetyPattern(
        label="protected-class expulsion or extermination",
        category="Hateful conduct",
        severity="high",
        reason="Message appears to target a protected class with expulsion, elimination, or violence.",
        regex=re.compile(
            r"\b(all|every|the)\s+(jews|muslims|christians|immigrants|gays|trans|women|men|black\s+people|"
            r"white\s+people|asian\s+people|mexicans)\s+(should|must|need\s+to|deserve\s+to)\s+"
            r"(die|be\s+killed|be\s+removed|be\s+deported|leave|get\s+out)\b",
            re.IGNORECASE,
        ),
    ),
    _SafetyPattern(
        label="sexual content involving minors",
        category="Sexual content involving minors",
        severity="critical",
        reason="Message appears to request, offer, or normalize sexual content involving minors.",
        regex=re.compile(
            r"\b(child\s+porn|minor\s+nudes|underage\s+(sex|nudes)|send\s+cp|watch\s+cp|cp\s+collection)\b",
            re.IGNORECASE,
        ),
    ),
    _SafetyPattern(
        label="protected-class slur cue",
        category="Hateful conduct",
        severity="high",
        reason="Message contains a high-risk slur or demeaning protected-class cue.",
        compact_terms=(
            "nigger",
            "faggot",
            "kike",
            "spic",
            "chink",
            "tranny",
            "wetback",
            "sandnigger",
            "raghead",
        ),
    ),
)


def _strongest_pattern(patterns: list[_SafetyPattern]) -> _SafetyPattern:
    rank = {"critical": 0, "high": 1, "medium": 2, "low": 3}
    return sorted(patterns, key=lambda pattern: rank.get(pattern.severity, 9))[0]


def _normalize_text(text: str) -> str:
    lowered = text.lower()
    replacements = str.maketrans(
        {
            "0": "o",
            "1": "i",
            "3": "e",
            "4": "a",
            "5": "s",
            "7": "t",
            "@": "a",
            "$": "s",
            "!": "i",
        }
    )
    return lowered.translate(replacements)


@lru_cache(maxsize=128)
def _obfuscated_term_pattern(term: str) -> re.Pattern[str]:
    letters = [re.escape(letter) for letter in str(term or "").lower() if "a" <= letter <= "z"]
    if not letters:
        return re.compile(r"(?!x)x")
    separated = r"[^a-z]*".join(letters)
    return re.compile(rf"(?<![a-z]){separated}(?![a-z])", re.IGNORECASE)


def _review_id(*, server_id: str, channel_id: str, message_id: str, category: str) -> str:
    raw = "\n".join((str(server_id), str(channel_id), str(message_id), str(category)))
    return hashlib.sha256(raw.encode("utf-8")).hexdigest()[:18]


def _discord_message_link(server_id: str, channel_id: str, message_id: str) -> str:
    if not server_id or not channel_id or not message_id:
        return ""
    return f"https://discord.com/channels/{server_id}/{channel_id}/{message_id}"


def _serialize_item(item: SafetyReviewItem) -> dict:
    payload = asdict(item)
    payload["matched_cues"] = list(item.matched_cues)
    return payload


def _items_from_payload(payload: dict) -> list[SafetyReviewItem]:
    items = [
        SafetyReviewItem(
            review_id=str(row.get("review_id") or ""),
            created_at=str(row.get("created_at") or ""),
            status=str(row.get("status") or "open"),
            server_id=str(row.get("server_id") or ""),
            server_label=str(row.get("server_label") or ""),
            channel_id=str(row.get("channel_id") or ""),
            channel_label=str(row.get("channel_label") or ""),
            message_id=str(row.get("message_id") or ""),
            message_link=str(row.get("message_link") or ""),
            author=str(row.get("author") or ""),
            author_id=str(row.get("author_id") or ""),
            text=str(row.get("text") or ""),
            category=str(row.get("category") or ""),
            severity=str(row.get("severity") or "medium"),
            reason=str(row.get("reason") or ""),
            matched_cues=tuple(row.get("matched_cues", [])),
            dismissed_at=str(row.get("dismissed_at") or ""),
        )
        for row in payload.get("items", [])
    ]
    return [item for item in items if item.review_id]


def _pruned_items(
    items: list[SafetyReviewItem],
    max_items: int,
    max_history_items: int,
) -> list[SafetyReviewItem]:
    open_items = [item for item in items if item.status == "open"][-max_items:]
    closed_items = [item for item in items if item.status != "open"]
    keep_closed_count = max(0, max_history_items - len(open_items))
    kept_closed = closed_items[-keep_closed_count:] if keep_closed_count else []
    return [*kept_closed, *open_items]
