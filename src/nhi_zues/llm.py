from __future__ import annotations

from openai import AsyncOpenAI

from .budget import BudgetManager
from .character import CharacterCard
from .character_memory import CharacterMemory
from .models import DraftDecision, MessageRecord, UserMemory
from .topics import TopicSnapshot
from .user_instructions import UserInstruction
from .voice_guard import apply_voice_guard, should_avoid_question, voice_guard_prompt
from .writing_style import apply_human_writing_noise, writing_style_prompt


class ReplyPlanner:
    def __init__(
        self,
        *,
        api_key: str | None,
        model: str,
        enabled: bool,
        generate_drafts: bool,
        conversation_reply_enabled: bool,
        budget: BudgetManager,
        max_output_tokens: int,
        max_input_chars: int,
        proactive_approval_required: bool,
        writing_mistake_rate: float,
        writing_quirk: str,
        writing_misspellings: str,
    ) -> None:
        self.model = model
        self.enabled = enabled
        self.generate_drafts = generate_drafts
        self.conversation_reply_enabled = conversation_reply_enabled
        self.budget = budget
        self.max_output_tokens = max_output_tokens
        self.max_input_chars = max_input_chars
        self.proactive_approval_required = proactive_approval_required
        self.writing_mistake_rate = writing_mistake_rate
        self.writing_quirk = writing_quirk
        self.writing_misspellings = writing_misspellings
        self.client = AsyncOpenAI(api_key=api_key) if api_key else None

    async def plan(
        self,
        *,
        channel_id: str,
        character: CharacterCard,
        character_memory: CharacterMemory,
        new_messages: list[MessageRecord],
        context: list[MessageRecord],
        topics: TopicSnapshot,
        user_memories: list[UserMemory],
        user_instructions: dict[str, list[UserInstruction]],
    ) -> DraftDecision:
        if not new_messages:
            return DraftDecision(False, "no new messages")

        engagement_type = _engagement_type(
            new_messages,
            topics,
            character,
            conversation_reply_enabled=self.conversation_reply_enabled,
        )
        if engagement_type == "none":
            return DraftDecision(False, "no conversation, tracked topic, or direct name cue")
        requires_approval = engagement_type == "proactive" and self.proactive_approval_required
        reason = _engagement_reason(engagement_type)

        if not self.enabled:
            return DraftDecision(
                True,
                f"would reply; {reason}; LLM disabled by NHI_ZUES_LLM_ENABLED",
                draft=None,
                engagement_type=engagement_type,
                requires_approval=requires_approval,
            )
        if not self.generate_drafts:
            return DraftDecision(
                True,
                f"would reply; {reason}; draft generation disabled for this run",
                draft=None,
                engagement_type=engagement_type,
                requires_approval=requires_approval,
            )
        if self.client is None:
            return DraftDecision(
                True,
                f"would reply; {reason}; no OPENAI_API_KEY configured",
                draft=None,
                engagement_type=engagement_type,
                requires_approval=requires_approval,
            )

        transcript = _fit_text(
            "\n".join(f"{message.author}: {message.text}" for message in context[-20:]),
            self.max_input_chars,
        )
        topic_summary = ", ".join(topic for topic, _ in topics.top_topics) or "none"
        user_memory = _format_user_memories(user_memories, user_instructions)
        seed = f"{channel_id}:{','.join(message.message_id for message in new_messages)}"
        recent_character_lines = _recent_character_lines(context, character)
        avoid_question = should_avoid_question(
            recent_character_lines=recent_character_lines,
            seed=seed,
        )
        user_prompt = (
            f"Channel: {channel_id}\n"
            f"Character: {character.name}\n"
            f"Tracked topics: {topic_summary}\n\n"
            f"Known user context:\n{user_memory}\n\n"
            f"Recent conversation:\n{transcript}\n\n"
            f"{voice_guard_prompt(avoid_question=avoid_question, recent_character_lines=recent_character_lines)}\n\n"
            "Draft one reply, 1-2 sentences max."
        )
        instructions = character.prompt_text()
        memory_prompt = character_memory.prompt_text()
        if memory_prompt:
            instructions = f"{instructions}\n\nPersistent character continuity:\n{memory_prompt}"
        instructions = f"{instructions}\n\n{writing_style_prompt(mistake_rate=self.writing_mistake_rate, quirk=self.writing_quirk, misspellings=self.writing_misspellings)}"
        estimated_input_tokens = BudgetManager.approx_tokens(instructions + "\n" + user_prompt)
        budget_check = self.budget.check(
            estimated_input_tokens=estimated_input_tokens,
            max_output_tokens=self.max_output_tokens,
        )
        if not budget_check.allowed:
            return DraftDecision(
                True,
                f"would reply; {reason}; {budget_check.reason} (${budget_check.estimated_cost_usd:.6f} est.)",
                draft=None,
                engagement_type=engagement_type,
                requires_approval=requires_approval,
            )

        response = await self.client.responses.create(
            model=self.model,
            instructions=instructions,
            input=user_prompt,
            max_output_tokens=self.max_output_tokens,
        )
        input_tokens, output_tokens = _usage_tokens(response, estimated_input_tokens)
        record = self.budget.record(input_tokens=input_tokens, output_tokens=output_tokens)
        draft = getattr(response, "output_text", "") or ""
        draft = self._finalize_draft(draft, seed=seed, avoid_question=avoid_question)
        return DraftDecision(
            True,
            f"{reason}; api_cost=${record.cost_usd:.6f}",
            draft=draft.strip(),
            engagement_type=engagement_type,
            requires_approval=requires_approval,
        )

    async def regenerate(
        self,
        *,
        channel_id: str,
        character: CharacterCard,
        character_memory: CharacterMemory,
        context: list[MessageRecord],
        user_memories: list[UserMemory],
        user_instructions: dict[str, list[UserInstruction]],
        current_draft: str,
        operator_instruction: str,
        target_user_key: str = "",
    ) -> DraftDecision:
        if not self.enabled:
            return DraftDecision(True, "would regenerate; LLM disabled by NHI_ZUES_LLM_ENABLED")
        if self.client is None:
            return DraftDecision(True, "would regenerate; no OPENAI_API_KEY configured")

        transcript = _fit_text(
            "\n".join(f"{message.author}: {message.text}" for message in context[-24:]),
            self.max_input_chars,
        )
        target = _target_user_line(target_user_key, user_memories)
        user_memory = _format_user_memories(user_memories, user_instructions)
        seed = f"{channel_id}:{target_user_key}:{operator_instruction}"
        recent_character_lines = _recent_character_lines(context, character)
        avoid_question = should_avoid_question(
            recent_character_lines=recent_character_lines,
            seed=seed,
        )
        user_prompt = (
            f"Channel: {channel_id}\n"
            f"Character: {character.name}\n"
            f"Target user: {target}\n\n"
            f"Known user context:\n{user_memory}\n\n"
            f"Recent conversation:\n{transcript}\n\n"
            f"Current draft:\n{current_draft or '(none)'}\n\n"
            f"Operator direction:\n{operator_instruction or 'Make a better natural response for the selected context.'}\n\n"
            f"{voice_guard_prompt(avoid_question=avoid_question, recent_character_lines=recent_character_lines)}\n\n"
            "Generate one revised Discord reply for approval, 1-2 sentences max."
        )
        instructions = character.prompt_text()
        memory_prompt = character_memory.prompt_text()
        if memory_prompt:
            instructions = f"{instructions}\n\nPersistent character continuity:\n{memory_prompt}"
        instructions = f"{instructions}\n\n{writing_style_prompt(mistake_rate=self.writing_mistake_rate, quirk=self.writing_quirk, misspellings=self.writing_misspellings)}"

        estimated_input_tokens = BudgetManager.approx_tokens(instructions + "\n" + user_prompt)
        budget_check = self.budget.check(
            estimated_input_tokens=estimated_input_tokens,
            max_output_tokens=self.max_output_tokens,
        )
        if not budget_check.allowed:
            return DraftDecision(
                True,
                f"would regenerate; {budget_check.reason} (${budget_check.estimated_cost_usd:.6f} est.)",
                draft=None,
                engagement_type="manual",
                requires_approval=True,
            )

        response = await self.client.responses.create(
            model=self.model,
            instructions=instructions,
            input=user_prompt,
            max_output_tokens=self.max_output_tokens,
        )
        input_tokens, output_tokens = _usage_tokens(response, estimated_input_tokens)
        record = self.budget.record(input_tokens=input_tokens, output_tokens=output_tokens)
        draft = getattr(response, "output_text", "") or ""
        draft = self._finalize_draft(draft, seed=seed, avoid_question=avoid_question)
        return DraftDecision(
            True,
            f"manual approval draft generated; api_cost=${record.cost_usd:.6f}",
            draft=draft.strip(),
            engagement_type="manual",
            requires_approval=True,
        )

    def _finalize_draft(self, draft: str, *, seed: str, avoid_question: bool = False) -> str:
        draft = apply_voice_guard(draft, avoid_question=avoid_question, seed=seed)
        return apply_human_writing_noise(
            draft,
            mistake_rate=self.writing_mistake_rate,
            quirk=self.writing_quirk,
            misspellings=self.writing_misspellings,
            seed=seed,
        )


def _engagement_type(
    messages: list[MessageRecord],
    topics: TopicSnapshot,
    character: CharacterCard,
    *,
    conversation_reply_enabled: bool = False,
) -> str:
    text = "\n".join(message.text.lower() for message in messages)
    if any(alias in text for alias in character.aliases):
        return "direct"
    if conversation_reply_enabled:
        return "conversation"
    if any(keyword in text for keyword in character.trigger_keywords):
        return "proactive"
    if topics.top_topics:
        return "proactive"
    return "none"


def _engagement_reason(engagement_type: str) -> str:
    if engagement_type == "direct":
        return "direct name cue"
    if engagement_type == "conversation":
        return "conversation reply opportunity"
    if engagement_type == "proactive":
        return "tracked topic cue"
    return "reply opportunity"


def _format_user_memories(
    user_memories: list[UserMemory],
    user_instructions: dict[str, list[UserInstruction]],
) -> str:
    if not user_memories:
        return "No prior user memory."
    lines: list[str] = []
    for user in user_memories:
        topics = ", ".join(user.recent_topics[:8]) or "none"
        summary = f" Summary: {user.summary}" if user.summary else ""
        instructions = user_instructions.get(user.user_key, [])
        instruction_text = ""
        if instructions:
            notes = "; ".join(item.note for item in instructions[-5:])
            instruction_text = f" User-specific guidance: {notes}."
        lines.append(
            f"- {user.display_name}: {user.message_count} observed messages; recent topics: {topics}.{summary}{instruction_text}"
        )
    return "\n".join(lines)


def _target_user_line(target_user_key: str, user_memories: list[UserMemory]) -> str:
    if not target_user_key:
        return "none selected"
    for user in user_memories:
        if user.user_key == target_user_key:
            return f"{user.display_name} ({user.user_key})"
    return target_user_key


def _recent_character_lines(context: list[MessageRecord], character: CharacterCard) -> list[str]:
    names = {_normalize_author(character.name)}
    names.update(_normalize_author(alias) for alias in character.aliases)
    return [
        message.text
        for message in context
        if _normalize_author(message.author) in names and message.text
    ][-8:]


def _normalize_author(value: str) -> str:
    return " ".join(str(value or "").lower().split())


def _fit_text(text: str, max_chars: int) -> str:
    if len(text) <= max_chars:
        return text
    return text[-max_chars:]


def _usage_tokens(response, estimated_input_tokens: int) -> tuple[int, int]:
    usage = getattr(response, "usage", None)
    input_tokens = getattr(usage, "input_tokens", None)
    output_tokens = getattr(usage, "output_tokens", None)
    if input_tokens is None and isinstance(usage, dict):
        input_tokens = usage.get("input_tokens")
        output_tokens = usage.get("output_tokens")
    return int(input_tokens or estimated_input_tokens), int(output_tokens or 0)
