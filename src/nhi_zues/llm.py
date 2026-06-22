from __future__ import annotations

from openai import AsyncOpenAI

from .budget import BudgetManager
from .character import CharacterCard
from .character_memory import CharacterMemory
from .models import DraftDecision, MessageRecord, UserMemory
from .topics import TopicSnapshot
from .user_instructions import UserInstruction


class ReplyPlanner:
    def __init__(
        self,
        *,
        api_key: str | None,
        model: str,
        enabled: bool,
        generate_drafts: bool,
        budget: BudgetManager,
        max_output_tokens: int,
        max_input_chars: int,
        proactive_approval_required: bool,
    ) -> None:
        self.model = model
        self.enabled = enabled
        self.generate_drafts = generate_drafts
        self.budget = budget
        self.max_output_tokens = max_output_tokens
        self.max_input_chars = max_input_chars
        self.proactive_approval_required = proactive_approval_required
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

        engagement_type = _engagement_type(new_messages, topics, character)
        if engagement_type == "none":
            return DraftDecision(False, "no tracked topic or direct name cue")
        requires_approval = engagement_type == "proactive" and self.proactive_approval_required

        if not self.enabled:
            return DraftDecision(
                True,
                "would reply; LLM disabled by NHI_ZUES_LLM_ENABLED",
                draft=None,
                engagement_type=engagement_type,
                requires_approval=requires_approval,
            )
        if not self.generate_drafts:
            return DraftDecision(
                True,
                "would reply; draft generation disabled for this run",
                draft=None,
                engagement_type=engagement_type,
                requires_approval=requires_approval,
            )
        if self.client is None:
            return DraftDecision(
                True,
                "would reply; no OPENAI_API_KEY configured",
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
        user_prompt = (
            f"Channel: {channel_id}\n"
            f"Character: {character.name}\n"
            f"Tracked topics: {topic_summary}\n\n"
            f"Known user context:\n{user_memory}\n\n"
            f"Recent conversation:\n{transcript}\n\n"
            "Draft one reply, 1-2 sentences max."
        )
        instructions = character.prompt_text()
        memory_prompt = character_memory.prompt_text()
        if memory_prompt:
            instructions = f"{instructions}\n\nPersistent character continuity:\n{memory_prompt}"
        estimated_input_tokens = BudgetManager.approx_tokens(instructions + "\n" + user_prompt)
        budget_check = self.budget.check(
            estimated_input_tokens=estimated_input_tokens,
            max_output_tokens=self.max_output_tokens,
        )
        if not budget_check.allowed:
            return DraftDecision(
                True,
                f"would reply; {budget_check.reason} (${budget_check.estimated_cost_usd:.6f} est.)",
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
        return DraftDecision(
            True,
            f"tracked topic or direct name cue; api_cost=${record.cost_usd:.6f}",
            draft=draft.strip(),
            engagement_type=engagement_type,
            requires_approval=requires_approval,
        )


def _engagement_type(
    messages: list[MessageRecord],
    topics: TopicSnapshot,
    character: CharacterCard,
) -> str:
    text = "\n".join(message.text.lower() for message in messages)
    if any(alias in text for alias in character.aliases):
        return "direct"
    if any(keyword in text for keyword in character.trigger_keywords):
        return "proactive"
    if topics.top_topics:
        return "proactive"
    return "none"


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
