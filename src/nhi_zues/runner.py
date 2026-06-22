from __future__ import annotations

import asyncio
import logging
import time

from .approvals import ApprovalQueue
from .browser import DiscordWebSession
from .budget import BudgetManager
from .character import CharacterCardStore
from .character_memory import CharacterMemoryStore
from .config import AppConfig
from .events import EventLog
from .llm import ReplyPlanner
from .memory import ConversationMemory
from .secrets import get_discord_credentials
from .topics import TopicTracker
from .user_instructions import UserInstructionStore


log = logging.getLogger(__name__)


class NhiZuesRunner:
    def __init__(self, config: AppConfig) -> None:
        self.config = config
        self.memory = ConversationMemory(config.state_dir / "memory.json")
        self.topics = TopicTracker()
        self.budget = BudgetManager(
            config.state_dir / "usage.json",
            model=config.openai_model,
            max_daily_usd=config.max_daily_usd,
            max_session_usd=config.max_session_usd,
            max_calls_per_run=config.max_llm_calls_per_run,
        )
        self.planner = ReplyPlanner(
            api_key=config.openai_api_key,
            model=config.openai_model,
            enabled=config.llm_enabled,
            generate_drafts=(not config.dry_run) or config.draft_in_dry_run,
            budget=self.budget,
            max_output_tokens=config.max_output_tokens,
            max_input_chars=config.max_input_chars,
            proactive_approval_required=config.proactive_approval_required,
            writing_mistake_rate=config.writing_mistake_rate,
            writing_quirk=config.writing_quirk,
            writing_misspellings=config.writing_misspellings,
        )
        self.characters = CharacterCardStore(config.character_dir, config.character_card)
        self.character_memory = CharacterMemoryStore(config.state_dir / "character_memory")
        self.approvals = ApprovalQueue(config.state_dir / "approvals.json")
        self.user_instructions = UserInstructionStore(config.state_dir / "user_instructions.json")
        self.events = EventLog(config.state_dir / "events.json")

    async def run_once(self) -> None:
        await self._run(loop=False)

    async def run_forever(self) -> None:
        await self._run(loop=True)

    async def _run(self, *, loop: bool) -> None:
        if not self.config.channels:
            raise ValueError("Configure at least one channel in NHI_ZUES_CHANNELS.")

        self.config.state_dir.mkdir(parents=True, exist_ok=True)
        self.memory.load()

        async with DiscordWebSession(
            self.config.profile_dir,
            browser_channel=self.config.browser_channel,
            headless=self.config.headless,
        ) as session:
            credentials = get_discord_credentials()
            await session.login_if_needed(email=credentials.email, password=credentials.password)
            last_checked: dict[tuple[str, str], float] = {}
            while True:
                targets = self._due_targets(last_checked) if loop else list(self.config.channels)
                if targets:
                    await self._process_channels(session, targets)
                    now = time.monotonic()
                    for target in targets:
                        last_checked[(target.server_id, target.channel_id)] = now
                if not loop:
                    return

                await asyncio.sleep(min(self.config.poll_seconds, 10))

    def _due_targets(self, last_checked: dict[tuple[str, str], float]):
        now = time.monotonic()
        due = []
        for target in self.config.channels:
            key = (target.server_id, target.channel_id)
            interval = target.poll_seconds or self.config.poll_seconds
            if key not in last_checked or now - last_checked[key] >= interval:
                due.append(target)
        return due

    async def _process_channels(self, session: DiscordWebSession, targets) -> None:
        for target in targets:
            current_url = await session.navigate_channel(target.server_id, target.channel_id)
            if f"/{target.channel_id}" not in current_url:
                log.warning(
                    "channel=%s redirected to %s; account may not have access",
                    target.channel_id,
                    current_url,
                )
                continue

            visible_messages = await session.read_visible_messages(target.server_id, target.channel_id)
            fresh = self.memory.ingest(target.channel_id, visible_messages)
            snapshot = self.topics.update(target.channel_id, fresh)
            context = self.memory.context(target.channel_id)
            user_memories = self.memory.user_context_for(context)
            user_notes = self.user_instructions.for_users(
                [user.user_key for user in user_memories],
                server_id=target.server_id,
                channel_id=target.channel_id,
            )
            character = self.characters.for_server(target.server_id, target.character_card)
            card_id = target.character_card or self.config.character_card
            character_memory = self.character_memory.load(card_id)
            if not target.engage_enabled:
                log.info(
                    "server=%s channel=%s visible=%s fresh=%s engage=false",
                    target.server_id,
                    target.channel_id,
                    len(visible_messages),
                    len(fresh),
                )
                self.memory.save()
                continue

            decision = await self.planner.plan(
                channel_id=target.channel_id,
                character=character,
                character_memory=character_memory,
                new_messages=fresh,
                context=context,
                topics=snapshot,
                user_memories=user_memories,
                user_instructions=user_notes,
            )

            log.info(
                "server=%s character=%s channel=%s visible=%s fresh=%s users=%s topics=%s decision=%s",
                target.server_id,
                character.name,
                target.channel_id,
                len(visible_messages),
                len(fresh),
                len(user_memories),
                snapshot.top_topics,
                decision.reason,
            )
            if decision.should_reply and decision.draft:
                if decision.requires_approval and not target.auto_respond_enabled:
                    item = self.approvals.add(
                        server_id=target.server_id,
                        channel_id=target.channel_id,
                        character_name=character.name,
                        engagement_type=decision.engagement_type,
                        reason=decision.reason,
                        draft=decision.draft,
                        source_messages=fresh,
                    )
                    log.info("queued approval=%s channel=%s", item.approval_id, target.channel_id)
                    self.events.add(
                        event_type="approval_queued",
                        server_id=target.server_id,
                        channel_id=target.channel_id,
                        summary=decision.reason,
                        draft=decision.draft,
                    )
                elif self.config.dry_run:
                    mode = "auto_respond_dry_run" if target.auto_respond_enabled else "dry_run"
                    log.info("%s draft for %s: %s", mode, target.channel_id, decision.draft)
                    self.events.add(
                        event_type=mode,
                        server_id=target.server_id,
                        channel_id=target.channel_id,
                        summary=decision.reason,
                        draft=decision.draft,
                    )
                else:
                    await session.send_message(
                        decision.draft,
                        typing_enabled=self.config.typing_indicator_enabled,
                        typing_min_seconds=self.config.typing_min_seconds,
                        typing_max_seconds=self.config.typing_max_seconds,
                        typing_chars_per_second=self.config.typing_chars_per_second,
                    )
                    self.events.add(
                        event_type="message_sent",
                        server_id=target.server_id,
                        channel_id=target.channel_id,
                        summary=decision.reason,
                        draft=decision.draft,
                    )

            self.memory.save()
