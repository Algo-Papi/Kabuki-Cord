from __future__ import annotations

import json
from pathlib import Path

from . import own_identity
from .approvals import ApprovalItem, ApprovalQueue
from .character import CharacterCardStore
from .config import AppConfig
from .discarded_approvals import DiscardedApprovalStore
from .events import EventLog
from .memory import ConversationMemory
from .message_view import message_preview, sorted_message_rows
from .models import MessageRecord
from .reply_ledger import ReplyLedger


def update_approval_draft(config: AppConfig, approval_id: str, draft: str) -> ApprovalItem:
    item = ApprovalQueue(config.state_dir / "approvals.json").update_draft(approval_id, draft)
    EventLog(config.state_dir / "events.json").add(
        event_type="approval_updated",
        server_id=item.server_id,
        channel_id=item.channel_id,
        summary="Approval draft edited by operator.",
        draft=draft,
    )
    return item


def discard_approval(config: AppConfig, approval_id: str) -> bool:
    queue = ApprovalQueue(config.state_dir / "approvals.json")
    item = queue.get(approval_id)
    if not queue.remove(approval_id) or item is None:
        return False
    DiscardedApprovalStore(config.state_dir / "discarded_approvals.json").record(
        server_id=item.server_id,
        channel_id=item.channel_id,
        source_message_ids=item.source_message_ids,
        draft=item.draft,
        reason="discarded by operator",
    )
    EventLog(config.state_dir / "events.json").add(
        event_type="approval_discarded",
        server_id=item.server_id,
        channel_id=item.channel_id,
        summary="Approval draft discarded by operator.",
        draft=item.draft,
    )
    return True


def clear_approval_queue(config: AppConfig) -> int:
    queue = ApprovalQueue(config.state_dir / "approvals.json")
    items = queue.list()
    count = queue.clear()
    if not count:
        return 0
    discarded = DiscardedApprovalStore(config.state_dir / "discarded_approvals.json")
    for item in items:
        discarded.record(
            server_id=item.server_id,
            channel_id=item.channel_id,
            source_message_ids=item.source_message_ids,
            draft=item.draft,
            reason="cleared from approval queue by operator",
        )
    EventLog(config.state_dir / "events.json").add(
        event_type="approvals_cleared",
        server_id="",
        channel_id="",
        summary=f"Cleared {count} queued approval draft(s).",
        draft="",
    )
    return count


def last_approval_source_message(config: AppConfig, item: ApprovalItem) -> dict:
    source_ids = _source_ids(item)
    if not source_ids:
        return {}
    payload = _read_json(config.state_dir / "memory.json", default={"channels": {}})
    rows = payload.get("channels", {}).get(str(getattr(item, "channel_id", "") or ""), [])
    matches = [
        row
        for row in sorted_message_rows(rows)
        if str(row.get("message_id") or "") in source_ids
    ]
    if not matches:
        return {}
    return message_preview(matches[-1])


def approval_source_messages(config: AppConfig, item: ApprovalItem) -> list[MessageRecord]:
    source_ids = _source_ids(item)
    if not source_ids:
        return []
    return [
        message
        for message in memory_context(config.state_dir / "memory.json", str(item.channel_id or ""))
        if message.message_id in source_ids
    ]


def own_source_block_message(
    config: AppConfig,
    *,
    server_id: str,
    channel_id: str,
    source_messages: list[MessageRecord],
    context: list[MessageRecord] | None = None,
) -> str:
    if not source_messages:
        return ""
    character = CharacterCardStore(config.character_dir, config.character_card).for_server(
        server_id,
        server_character_card(config, server_id),
    )
    character_names = (character.name, *character.aliases)
    ledger = ReplyLedger(config.state_dir / "sent_replies.json")
    own_texts = ledger.own_texts_for_channel(channel_id=channel_id)
    own_message_ids = ledger.own_message_ids_for_channel(channel_id=channel_id)
    own_author_ids = own_identity.own_author_ids_from_messages(
        context or source_messages,
        character_names=character_names,
        own_texts=own_texts,
    )
    for message in source_messages:
        if own_identity.is_own_message(
            message,
            character_names=character_names,
            own_author_ids=own_author_ids,
            own_message_ids=own_message_ids,
            own_texts=own_texts,
        ):
            return (
                "Reply blocked: the selected/source message appears to be from this "
                "Discord account or character. Discard the stale approval or select a "
                "message from another user."
            )
    return ""


def memory_context(memory_path: Path, channel_id: str, *, limit: int = 80) -> list[MessageRecord]:
    memory = ConversationMemory(memory_path)
    memory.load()
    return memory.context(channel_id, limit=limit)


def server_character_card(config: AppConfig, server_id: str) -> str | None:
    payload = _read_json(config.servers_file, default={"servers": []})
    for server in payload.get("servers", []):
        if str(server.get("server_id") or "") == server_id:
            return server.get("character_card") or None
    return None


def _source_ids(item: ApprovalItem) -> set[str]:
    return {
        str(value)
        for value in getattr(item, "source_message_ids", ())
        if str(value or "").strip()
    }


def _read_json(path: Path, *, default: dict) -> dict:
    if not path.exists():
        return default
    return json.loads(path.read_text(encoding="utf-8-sig"))
