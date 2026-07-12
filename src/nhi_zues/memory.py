from __future__ import annotations

from collections import defaultdict, deque
from collections.abc import Iterable
from dataclasses import asdict, dataclass
from datetime import datetime, timedelta, timezone
from pathlib import Path

from .discord_text import clean_discord_display_name
from .models import MessageRecord, UserMemory
from .state_io import mutate_json_file, read_json_file


DEFAULT_CANDIDATE_TTL_SECONDS = 30 * 60
DEFAULT_MAX_CANDIDATES_PER_CHANNEL = 12
DEFAULT_CANDIDATE_BATCH_SIZE = 8
_REPLY_CANDIDATES_KEY = "reply_candidates"


@dataclass(frozen=True)
class ReplyCandidateBatch:
    channel_id: str
    message_ids: tuple[str, ...]
    generation: int
    revision: int
    status: str = "pending"
    reason: str = ""


class ConversationMemory:
    def __init__(
        self,
        state_file: Path,
        *,
        max_messages_per_channel: int = 500,
        candidate_ttl_seconds: float = DEFAULT_CANDIDATE_TTL_SECONDS,
        max_candidates_per_channel: int = DEFAULT_MAX_CANDIDATES_PER_CHANNEL,
        candidate_batch_size: int = DEFAULT_CANDIDATE_BATCH_SIZE,
    ) -> None:
        self.state_file = state_file
        self.max_messages_per_channel = max_messages_per_channel
        self.candidate_ttl_seconds = max(0.0, float(candidate_ttl_seconds))
        self.max_candidates_per_channel = max(1, int(max_candidates_per_channel))
        self.candidate_batch_size = max(
            1,
            min(int(candidate_batch_size), self.max_candidates_per_channel),
        )
        self._messages: dict[str, deque[MessageRecord]] = defaultdict(
            lambda: deque(maxlen=max_messages_per_channel)
        )
        self._seen_ids: set[str] = set()
        self._users: dict[str, UserMemory] = {}
        self._candidate_channels: dict[str, dict] = {}

    def load(self) -> None:
        payload = read_json_file(
            self.state_file,
            default=_memory_default_payload(),
        )
        self._seen_ids = set(payload.get("seen_ids", []))
        self._candidate_channels = _candidate_channels_from_payload(payload)
        for channel_id, rows in payload.get("channels", {}).items():
            bucket: deque[MessageRecord] = deque(maxlen=self.max_messages_per_channel)
            for row in rows:
                bucket.append(
                    MessageRecord(
                        server_id=row.get("server_id", ""),
                        channel_id=row["channel_id"],
                        message_id=row["message_id"],
                        author=clean_discord_display_name(row["author"]),
                        author_id=row.get("author_id"),
                        text=row["text"],
                        observed_at=datetime.fromisoformat(row["observed_at"]),
                    )
                )
            self._messages[channel_id] = bucket
        for user_key, row in payload.get("users", {}).items():
            self._users[user_key] = UserMemory(
                user_key=user_key,
                display_name=clean_discord_display_name(row["display_name"]),
                stable_user_id=row.get("stable_user_id"),
                message_count=int(row.get("message_count", 0)),
                recent_topics=tuple(row.get("recent_topics", [])),
                last_seen_at=datetime.fromisoformat(row["last_seen_at"]),
                summary=row.get("summary", ""),
            )
        if not self._users:
            for messages in self._messages.values():
                for message in messages:
                    self._update_user_memory(message)

    def save(self) -> None:
        self._rebuild_user_index()
        self.state_file.parent.mkdir(parents=True, exist_ok=True)
        payload = {
            "seen_ids": sorted(self._seen_ids),
            "channels": {
                channel_id: [
                    self._serialize_message(message)
                    for message in sorted(messages, key=_message_order_key)
                ]
                for channel_id, messages in self._messages.items()
            },
            "users": {
                user_key: self._serialize_user(user)
                for user_key, user in sorted(self._users.items())
            },
        }
        mutate_json_file(
            self.state_file,
            default=_memory_default_payload(),
            mutator=lambda latest: _merge_memory_payload(
                latest,
                payload,
                max_messages_per_channel=self.max_messages_per_channel,
            ),
        )

    def ingest(self, channel_id: str, messages: list[MessageRecord]) -> list[MessageRecord]:
        fresh: list[MessageRecord] = []
        touched_channels: set[str] = set()
        for message in messages:
            if message.message_id in self._seen_ids:
                if self._merge_seen_message(message):
                    touched_channels.add(message.channel_id)
                    continue
                # A message can be present in seen_ids but missing from the retained
                # channel bucket after older low-cap history runs. Rehydrate it so
                # deeper backfills actually improve the visible conversation log.
                self._messages[channel_id].append(message)
                touched_channels.add(channel_id)
                continue
            self._seen_ids.add(message.message_id)
            self._messages[channel_id].append(message)
            self._update_user_memory(message)
            fresh.append(message)
            touched_channels.add(channel_id)
        for touched_channel in touched_channels:
            self._sort_channel(touched_channel)
        return fresh

    def observe_reply_candidates(
        self,
        channel_id: str,
        messages: Iterable[MessageRecord],
        *,
        now: datetime | None = None,
    ) -> ReplyCandidateBatch | None:
        """Persist newly eligible message IDs without duplicating message content."""
        channel_id = str(channel_id or "").strip()
        if not channel_id:
            return None
        observed_at = _as_utc(now)
        message_ids = _candidate_message_ids(channel_id, messages)

        def observe(payload: dict) -> None:
            if self.candidate_ttl_seconds <= 0:
                payload[_REPLY_CANDIDATES_KEY] = {}
                return
            _prune_reply_candidate_payload(
                payload,
                now=observed_at,
                max_candidates_per_channel=self.max_candidates_per_channel,
            )
            if not message_ids:
                return
            channels = payload.setdefault(_REPLY_CANDIDATES_KEY, {})
            row = _normalize_candidate_channel(channels.get(channel_id, {}))
            existing_ids = {str(item["message_id"]) for item in row["items"]}
            added_ids = [message_id for message_id in message_ids if message_id not in existing_ids]
            if not added_ids:
                return

            generation = int(row["generation"]) + 1
            expires_at = observed_at + timedelta(seconds=self.candidate_ttl_seconds)
            row["items"].extend(
                {
                    "message_id": message_id,
                    "queued_at": observed_at.isoformat(),
                    "expires_at": expires_at.isoformat(),
                    "generation": generation,
                }
                for message_id in added_ids
            )
            row["items"] = row["items"][-self.max_candidates_per_channel :]
            row["generation"] = generation
            row["revision"] = int(row["revision"]) + 1
            row["status"] = "pending"
            row["reason"] = ""
            channels[channel_id] = row

        payload, _ = mutate_json_file(
            self.state_file,
            default=_memory_default_payload(),
            mutator=observe,
        )
        self._sync_candidate_channels(payload)
        return _candidate_batch_from_payload(
            payload,
            channel_id,
            batch_size=self.candidate_batch_size,
            mode="any",
        )

    def ready_reply_candidates(
        self,
        channel_id: str,
        *,
        now: datetime | None = None,
    ) -> ReplyCandidateBatch | None:
        """Return a batch only when it has never run or its generation advanced."""
        payload = self._pruned_candidate_payload(now=now)
        return _candidate_batch_from_payload(
            payload,
            str(channel_id or "").strip(),
            batch_size=self.candidate_batch_size,
            mode="ready",
        )

    def active_reply_candidates(
        self,
        channel_id: str,
        *,
        now: datetime | None = None,
    ) -> ReplyCandidateBatch | None:
        """Return the active bounded batch regardless of lifecycle status."""
        payload = self._pruned_candidate_payload(now=now)
        return _candidate_batch_from_payload(
            payload,
            str(channel_id or "").strip(),
            batch_size=self.max_candidates_per_channel,
            mode="any",
        )

    def eligible_reply_candidates(
        self,
        channel_id: str,
        *,
        now: datetime | None = None,
    ) -> ReplyCandidateBatch | None:
        payload = self._pruned_candidate_payload(now=now)
        return _candidate_batch_from_payload(
            payload,
            str(channel_id or "").strip(),
            batch_size=self.candidate_batch_size,
            mode="eligible",
        )

    def pending_reply_candidates(
        self,
        channel_id: str,
        *,
        now: datetime | None = None,
    ) -> ReplyCandidateBatch | None:
        """Return the newest active batch even when it is currently deferred."""
        payload = self._pruned_candidate_payload(now=now)
        return _candidate_batch_from_payload(
            payload,
            str(channel_id or "").strip(),
            batch_size=self.candidate_batch_size,
            mode="pending",
        )

    def reply_candidate_counts(
        self,
        channel_id: str | None = None,
        *,
        now: datetime | None = None,
    ) -> dict[str, int]:
        """Return content-free lifecycle counts for one channel or all channels."""
        payload = self._pruned_candidate_payload(now=now)
        counts = {"pending": 0, "deferred": 0, "eligible": 0}
        channels = _candidate_channels_from_payload(payload)
        requested_channel = str(channel_id or "").strip()
        for current_channel, row in channels.items():
            if requested_channel and current_channel != requested_channel:
                continue
            status = str(row["status"])
            counts[status] += len(row["items"])
        return counts

    def defer_reply_candidates(
        self,
        batch: ReplyCandidateBatch,
        *,
        reason: str,
        now: datetime | None = None,
    ) -> bool:
        """Defer a snapshot unless a newer observation has already advanced it."""
        return self._mark_reply_candidate_status(
            batch,
            status="deferred",
            reason=reason,
            now=now,
        )

    def mark_reply_candidates_eligible(
        self,
        batch: ReplyCandidateBatch,
        *,
        reason: str,
        now: datetime | None = None,
    ) -> bool:
        """Mark an evaluated generation eligible unless newer context superseded it."""
        return self._mark_reply_candidate_status(
            batch,
            status="eligible",
            reason=reason,
            now=now,
        )

    def _mark_reply_candidate_status(
        self,
        batch: ReplyCandidateBatch,
        *,
        status: str,
        reason: str,
        now: datetime | None,
    ) -> bool:
        evaluated_at = _as_utc(now)
        changed = False

        def mark(payload: dict) -> None:
            nonlocal changed
            if self.candidate_ttl_seconds <= 0:
                payload[_REPLY_CANDIDATES_KEY] = {}
                return
            _prune_reply_candidate_payload(
                payload,
                now=evaluated_at,
                max_candidates_per_channel=self.max_candidates_per_channel,
            )
            channels = payload.setdefault(_REPLY_CANDIDATES_KEY, {})
            row = _normalize_candidate_channel(channels.get(batch.channel_id, {}))
            if not row["items"] or int(row["generation"]) != int(batch.generation):
                return
            active_ids = {str(item["message_id"]) for item in row["items"]}
            if not active_ids.intersection(batch.message_ids):
                return
            row["evaluated_generation"] = int(batch.generation)
            row["last_evaluated_at"] = evaluated_at.isoformat()
            row["status"] = status
            row["reason"] = str(reason or "").strip()
            row["revision"] = int(row["revision"]) + 1
            channels[batch.channel_id] = row
            changed = True

        payload, _ = mutate_json_file(
            self.state_file,
            default=_memory_default_payload(),
            mutator=mark,
        )
        self._sync_candidate_channels(payload)
        return changed

    def resolve_reply_candidates(
        self,
        channel_id: str,
        candidates: ReplyCandidateBatch | Iterable[str],
        *,
        now: datetime | None = None,
    ) -> int:
        """Resolve an evaluated generation while preserving candidates observed later."""
        channel_id = str(channel_id or "").strip()
        if isinstance(candidates, ReplyCandidateBatch):
            if candidates.channel_id != channel_id:
                raise ValueError("Candidate batch belongs to a different channel.")
            through_generation: int | None = int(candidates.generation)
            requested_ids: set[str] = set(candidates.message_ids)
        else:
            through_generation = None
            requested_ids = {
                str(message_id or "").strip()
                for message_id in candidates
                if str(message_id or "").strip()
            }
        resolved = 0
        current_time = _as_utc(now)

        def resolve(payload: dict) -> None:
            nonlocal resolved
            _prune_reply_candidate_payload(
                payload,
                now=current_time,
                max_candidates_per_channel=self.max_candidates_per_channel,
            )
            channels = payload.setdefault(_REPLY_CANDIDATES_KEY, {})
            row = _normalize_candidate_channel(channels.get(channel_id, {}))
            if not row["items"]:
                return
            if through_generation is None:
                keep = [
                    item for item in row["items"] if str(item["message_id"]) not in requested_ids
                ]
            else:
                keep = [
                    item
                    for item in row["items"]
                    if int(item["generation"]) > through_generation
                ]
            resolved = len(row["items"]) - len(keep)
            if not resolved:
                return
            if not keep:
                channels.pop(channel_id, None)
                return
            row["items"] = keep
            row["generation"] = max(int(item["generation"]) for item in keep)
            row["evaluated_generation"] = min(
                int(row["evaluated_generation"]),
                int(row["generation"]),
            )
            row["revision"] = int(row["revision"]) + 1
            row["status"] = "pending"
            row["reason"] = ""
            channels[channel_id] = row

        payload, _ = mutate_json_file(
            self.state_file,
            default=_memory_default_payload(),
            mutator=resolve,
        )
        self._sync_candidate_channels(payload)
        return resolved

    def prune_reply_candidates(self, *, now: datetime | None = None) -> int:
        current_time = _as_utc(now)
        removed = 0

        def prune(payload: dict) -> None:
            nonlocal removed
            if self.candidate_ttl_seconds <= 0:
                removed = _clear_reply_candidate_payload(payload)
            else:
                removed = _prune_reply_candidate_payload(
                    payload,
                    now=current_time,
                    max_candidates_per_channel=self.max_candidates_per_channel,
                )

        payload, _ = mutate_json_file(
            self.state_file,
            default=_memory_default_payload(),
            mutator=prune,
        )
        self._sync_candidate_channels(payload)
        return removed

    def messages_by_ids(
        self,
        channel_id: str,
        message_ids: Iterable[str],
    ) -> list[MessageRecord]:
        by_id = {
            message.message_id: message
            for message in self._messages.get(str(channel_id or "").strip(), ())
        }
        ordered_ids = _unique_strings(message_ids)
        return [by_id[message_id] for message_id in ordered_ids if message_id in by_id]

    def _pruned_candidate_payload(self, *, now: datetime | None = None) -> dict:
        current_time = _as_utc(now)

        def prune(payload: dict) -> None:
            if self.candidate_ttl_seconds <= 0:
                _clear_reply_candidate_payload(payload)
            else:
                _prune_reply_candidate_payload(
                    payload,
                    now=current_time,
                    max_candidates_per_channel=self.max_candidates_per_channel,
                )

        payload, _ = mutate_json_file(
            self.state_file,
            default=_memory_default_payload(),
            mutator=prune,
        )
        self._sync_candidate_channels(payload)
        return payload

    def _sync_candidate_channels(self, payload: dict) -> None:
        self._candidate_channels = _candidate_channels_from_payload(payload)

    def context(self, channel_id: str, *, limit: int = 20) -> list[MessageRecord]:
        self._sort_channel(channel_id)
        return list(self._messages[channel_id])[-limit:]

    def user_context_for(self, messages: list[MessageRecord], *, limit: int = 8) -> list[UserMemory]:
        users: list[UserMemory] = []
        seen: set[str] = set()
        for message in reversed(messages):
            user_key = _user_key(message.author, message.author_id)
            if user_key in seen:
                continue
            seen.add(user_key)
            user = self._users.get(user_key)
            if user is not None:
                users.append(user)
            if len(users) >= limit:
                break
        return list(reversed(users))

    def _update_user_memory(self, message: MessageRecord) -> None:
        user_key = _user_key(message.author, message.author_id)
        existing = self._users.get(user_key)
        topics = _extract_lightweight_topics(message.text)
        if existing is None:
            self._users[user_key] = UserMemory(
                user_key=user_key,
                display_name=message.author,
                stable_user_id=message.author_id,
                message_count=1,
                recent_topics=tuple(topics[:12]),
                last_seen_at=message.observed_at,
            )
            return

        merged_topics = list(existing.recent_topics)
        for topic in topics:
            if topic not in merged_topics:
                merged_topics.append(topic)
        self._users[user_key] = UserMemory(
            user_key=user_key,
            display_name=message.author or existing.display_name,
            stable_user_id=message.author_id or existing.stable_user_id,
            message_count=existing.message_count + 1,
            recent_topics=tuple(merged_topics[-12:]),
            last_seen_at=message.observed_at,
            summary=existing.summary,
        )

    def _merge_seen_message(self, message: MessageRecord) -> bool:
        bucket = self._messages.get(message.channel_id)
        if not bucket:
            return False

        for index, existing in enumerate(bucket):
            if existing.message_id != message.message_id:
                continue
            merged = _best_message_record(existing, message)
            if merged == existing:
                return True
            bucket[index] = merged
            return True
        return False

    def _sort_channel(self, channel_id: str) -> None:
        messages = self._messages.get(channel_id)
        if not messages:
            return
        self._messages[channel_id] = deque(
            sorted(messages, key=_message_order_key),
            maxlen=self.max_messages_per_channel,
        )

    def _rebuild_user_index(self) -> None:
        summaries_by_key = {key: user.summary for key, user in self._users.items() if user.summary}
        summaries_by_name = {
            _normalize_name(user.display_name): user.summary
            for user in self._users.values()
            if user.summary
        }
        messages = [message for bucket in self._messages.values() for message in bucket]
        self._users = {}
        for message in sorted(messages, key=lambda item: item.observed_at):
            self._update_user_memory(message)
        for key, user in list(self._users.items()):
            summary = summaries_by_key.get(key) or summaries_by_name.get(_normalize_name(user.display_name)) or ""
            if not summary:
                continue
            self._users[key] = UserMemory(
                user_key=user.user_key,
                display_name=user.display_name,
                stable_user_id=user.stable_user_id,
                message_count=user.message_count,
                recent_topics=user.recent_topics,
                last_seen_at=user.last_seen_at,
                summary=summary,
            )

    @staticmethod
    def _serialize_message(message: MessageRecord) -> dict[str, str]:
        payload = asdict(message)
        payload["observed_at"] = message.observed_at.isoformat()
        return payload

    @staticmethod
    def _serialize_user(user: UserMemory) -> dict:
        return {
            "display_name": user.display_name,
            "stable_user_id": user.stable_user_id,
            "message_count": user.message_count,
            "recent_topics": list(user.recent_topics),
            "last_seen_at": user.last_seen_at.isoformat(),
            "summary": user.summary,
        }


def _memory_default_payload() -> dict:
    return {
        "seen_ids": [],
        "channels": {},
        "users": {},
        _REPLY_CANDIDATES_KEY: {},
    }


def _candidate_message_ids(
    channel_id: str,
    messages: Iterable[MessageRecord],
) -> tuple[str, ...]:
    message_ids: list[str] = []
    seen: set[str] = set()
    for message in messages:
        message_channel = str(getattr(message, "channel_id", "") or "").strip()
        message_id = str(getattr(message, "message_id", "") or "").strip()
        if message_channel != channel_id or not message_id or message_id in seen:
            continue
        seen.add(message_id)
        message_ids.append(message_id)
    return tuple(message_ids)


def _candidate_channels_from_payload(payload: dict) -> dict[str, dict]:
    raw_channels = payload.get(_REPLY_CANDIDATES_KEY, {})
    if not isinstance(raw_channels, dict):
        return {}
    channels: dict[str, dict] = {}
    for raw_channel_id, raw_row in raw_channels.items():
        channel_id = str(raw_channel_id or "").strip()
        if not channel_id:
            continue
        row = _normalize_candidate_channel(raw_row)
        if row["items"]:
            channels[channel_id] = row
    return channels


def _normalize_candidate_channel(value) -> dict:
    raw = value if isinstance(value, dict) else {}
    items: list[dict] = []
    seen: set[str] = set()
    raw_items = raw.get("items", [])
    if not isinstance(raw_items, list):
        raw_items = []
    for item in raw_items:
        if not isinstance(item, dict):
            continue
        message_id = str(item.get("message_id") or "").strip()
        queued_at = _parse_candidate_datetime(item.get("queued_at"))
        expires_at = _parse_candidate_datetime(item.get("expires_at"))
        if not message_id or message_id in seen or expires_at is None:
            continue
        seen.add(message_id)
        queued_at = queued_at or expires_at
        items.append(
            {
                "message_id": message_id,
                "queued_at": queued_at.isoformat(),
                "expires_at": expires_at.isoformat(),
                "generation": max(1, _safe_int(item.get("generation"), 1)),
            }
        )

    generation = max(
        max(0, _safe_int(raw.get("generation"), 0)),
        max((int(item["generation"]) for item in items), default=0),
    )
    evaluated_generation = min(
        generation,
        max(0, _safe_int(raw.get("evaluated_generation"), 0)),
    )
    status = str(raw.get("status") or "pending").strip().lower()
    if status not in {"deferred", "eligible"} or generation > evaluated_generation:
        status = "pending"
    evaluated_at = _parse_candidate_datetime(raw.get("last_evaluated_at"))
    return {
        "generation": generation,
        "evaluated_generation": evaluated_generation,
        "revision": max(0, _safe_int(raw.get("revision"), 0)),
        "status": status,
        "reason": (
            str(raw.get("reason") or "").strip()
            if status in {"deferred", "eligible"}
            else ""
        ),
        "last_evaluated_at": evaluated_at.isoformat() if evaluated_at is not None else "",
        "items": items,
    }


def _prune_reply_candidate_payload(
    payload: dict,
    *,
    now: datetime,
    max_candidates_per_channel: int,
) -> int:
    raw_channels = payload.get(_REPLY_CANDIDATES_KEY, {})
    if not isinstance(raw_channels, dict):
        raw_channels = {}
    channels: dict[str, dict] = {}
    removed = 0
    for raw_channel_id, raw_row in raw_channels.items():
        channel_id = str(raw_channel_id or "").strip()
        raw_item_count = (
            len(raw_row.get("items", []))
            if isinstance(raw_row, dict) and isinstance(raw_row.get("items", []), list)
            else 0
        )
        if not channel_id:
            removed += raw_item_count
            continue
        row = _normalize_candidate_channel(raw_row)
        active = [
            item
            for item in row["items"]
            if (_parse_candidate_datetime(item["expires_at"]) or now) > now
        ]
        active = active[-max(1, int(max_candidates_per_channel)) :]
        removed += max(0, raw_item_count - len(active))
        if not active:
            continue
        row["items"] = active
        row["generation"] = max(int(item["generation"]) for item in active)
        row["evaluated_generation"] = min(
            int(row["evaluated_generation"]),
            int(row["generation"]),
        )
        if int(row["generation"]) > int(row["evaluated_generation"]):
            row["status"] = "pending"
            row["reason"] = ""
        normalized_previous = _normalize_candidate_channel(raw_row)
        if row != normalized_previous or raw_item_count != len(active):
            row["revision"] = max(
                int(row["revision"]),
                int(normalized_previous["revision"]),
            ) + 1
        channels[channel_id] = row
    payload[_REPLY_CANDIDATES_KEY] = channels
    return removed


def _clear_reply_candidate_payload(payload: dict) -> int:
    channels = _candidate_channels_from_payload(payload)
    removed = sum(len(row["items"]) for row in channels.values())
    payload[_REPLY_CANDIDATES_KEY] = {}
    return removed


def _candidate_batch_from_payload(
    payload: dict,
    channel_id: str,
    *,
    batch_size: int,
    mode: str,
) -> ReplyCandidateBatch | None:
    row = _normalize_candidate_channel(
        payload.get(_REPLY_CANDIDATES_KEY, {}).get(channel_id, {})
        if isinstance(payload.get(_REPLY_CANDIDATES_KEY, {}), dict)
        else {}
    )
    if not row["items"]:
        return None
    status = str(row["status"])
    generation_advanced = int(row["generation"]) > int(row["evaluated_generation"])
    if mode == "ready" and status != "pending" and not generation_advanced:
        return None
    if mode == "eligible" and (status != "eligible" or generation_advanced):
        return None
    if mode == "pending" and status != "pending":
        return None
    items = row["items"][-max(1, int(batch_size)) :]
    return ReplyCandidateBatch(
        channel_id=channel_id,
        message_ids=tuple(str(item["message_id"]) for item in items),
        generation=int(row["generation"]),
        revision=int(row["revision"]),
        status=str(row["status"]),
        reason=str(row["reason"]),
    )


def _unique_strings(values: Iterable[str]) -> tuple[str, ...]:
    if isinstance(values, str):
        values = (values,)
    items: list[str] = []
    seen: set[str] = set()
    for value in values:
        item = str(value or "").strip()
        if not item or item in seen:
            continue
        seen.add(item)
        items.append(item)
    return tuple(items)


def _as_utc(value: datetime | None) -> datetime:
    current = value or datetime.now(timezone.utc)
    if current.tzinfo is None:
        return current.replace(tzinfo=timezone.utc)
    return current.astimezone(timezone.utc)


def _parse_candidate_datetime(value) -> datetime | None:
    try:
        parsed = datetime.fromisoformat(str(value or "").replace("Z", "+00:00"))
    except ValueError:
        return None
    return _as_utc(parsed)


def _safe_int(value, default: int) -> int:
    try:
        return int(value)
    except (TypeError, ValueError):
        return int(default)


def _user_key(author: str, author_id: str | None = None) -> str:
    if author_id:
        return f"discord:{author_id}"
    normalized = _normalize_name(clean_discord_display_name(author))
    return f"name:{normalized or 'unknown'}"


def _normalize_name(author: str) -> str:
    return " ".join(author.lower().strip().split())


def _best_message_record(existing: MessageRecord, incoming: MessageRecord) -> MessageRecord:
    server_id = incoming.server_id or existing.server_id
    author = clean_discord_display_name(existing.author)
    author_id = existing.author_id
    text = incoming.text or existing.text

    incoming_author = str(incoming.author or "").strip()
    existing_author = str(existing.author or "").strip()
    incoming_author = clean_discord_display_name(incoming_author)
    existing_author = clean_discord_display_name(existing_author)
    incoming_author_known = bool(incoming_author) and incoming_author.lower() != "unknown"
    existing_author_known = bool(existing_author) and existing_author.lower() != "unknown"

    if incoming.author_id:
        if incoming.author_id != existing.author_id:
            author_id = incoming.author_id
            if incoming_author_known:
                author = incoming_author
        elif incoming_author_known and (not existing_author_known or incoming_author != existing_author):
            author = incoming_author
    elif not existing.author_id and incoming_author_known and (
        not existing_author_known or incoming_author != existing_author
    ):
        author = incoming_author

    return MessageRecord(
        server_id=server_id,
        channel_id=existing.channel_id,
        message_id=existing.message_id,
        author=author,
        author_id=author_id,
        text=text,
        observed_at=existing.observed_at,
    )


def _message_order_key(message: MessageRecord) -> tuple[int, str]:
    try:
        return (int(str(message.message_id).rsplit("-", 1)[-1]), message.message_id)
    except ValueError:
        return (0, message.message_id)


def _extract_lightweight_topics(text: str) -> list[str]:
    terms = [
        term.strip(".,!?;:()[]{}\"'").lower()
        for term in text.split()
        if len(term.strip(".,!?;:()[]{}\"'")) >= 4
    ]
    ignored = {"that", "this", "with", "from", "they", "have", "just", "like", "what", "your"}
    return [term for term in terms if term not in ignored][:8]


def _merge_memory_payload(
    latest: dict,
    incoming: dict,
    *,
    max_messages_per_channel: int,
) -> None:
    latest["seen_ids"] = sorted(
        set(latest.get("seen_ids", [])).union(incoming.get("seen_ids", []))
    )
    channels = latest.setdefault("channels", {})
    for channel_id, rows in incoming.get("channels", {}).items():
        by_id = {
            str(row.get("message_id") or ""): row
            for row in channels.get(channel_id, [])
            if str(row.get("message_id") or "")
        }
        by_id.update(
            {
                str(row.get("message_id") or ""): row
                for row in rows
                if str(row.get("message_id") or "")
            }
        )
        channels[channel_id] = sorted(
            by_id.values(),
            key=lambda row: (str(row.get("observed_at") or ""), str(row.get("message_id") or "")),
        )[-max_messages_per_channel:]

    users = latest.setdefault("users", {})
    for user_key, row in incoming.get("users", {}).items():
        existing = users.get(user_key, {})
        topics = list(existing.get("recent_topics", []))
        for topic in row.get("recent_topics", []):
            if topic not in topics:
                topics.append(topic)
        newest = row if str(row.get("last_seen_at") or "") >= str(existing.get("last_seen_at") or "") else existing
        users[user_key] = {
            **existing,
            **newest,
            "message_count": max(
                int(existing.get("message_count", 0)),
                int(row.get("message_count", 0)),
            ),
            "recent_topics": topics[-12:],
            "summary": str(row.get("summary") or existing.get("summary") or ""),
        }
