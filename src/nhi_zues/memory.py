from __future__ import annotations

from collections import defaultdict, deque
from dataclasses import asdict
from datetime import datetime
from pathlib import Path

from .discord_text import clean_discord_display_name
from .models import MessageRecord, UserMemory
from .state_io import mutate_json_file, read_json_file


class ConversationMemory:
    def __init__(self, state_file: Path, *, max_messages_per_channel: int = 500) -> None:
        self.state_file = state_file
        self.max_messages_per_channel = max_messages_per_channel
        self._messages: dict[str, deque[MessageRecord]] = defaultdict(
            lambda: deque(maxlen=max_messages_per_channel)
        )
        self._seen_ids: set[str] = set()
        self._users: dict[str, UserMemory] = {}

    def load(self) -> None:
        payload = read_json_file(
            self.state_file,
            default={"seen_ids": [], "channels": {}, "users": {}},
        )
        self._seen_ids = set(payload.get("seen_ids", []))
        for channel_id, rows in payload.get("channels", {}).items():
            bucket = deque(maxlen=self.max_messages_per_channel)
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
            default={"seen_ids": [], "channels": {}, "users": {}},
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
