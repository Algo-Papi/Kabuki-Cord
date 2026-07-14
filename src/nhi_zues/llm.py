from __future__ import annotations

import re

from openai import AsyncOpenAI

from .budget import BudgetManager
from .character import CharacterCard
from .character_memory import CharacterMemory
from .discord_text import clean_discord_display_name, sanitize_outgoing_draft
from .models import DraftDecision, MessageRecord, UserMemory
from . import own_identity
from .relevance import (
    assess_reply_candidate,
    contains_card_alias,
    contains_card_trigger,
    detect_text_signals,
    is_conversation_worthy_text,
    looks_like_app_feed,
    looks_like_meta_suspicion,
    term_in_text,
)
from .topics import TopicSnapshot
from .user_instructions import UserInstruction
from .voice_guard import (
    apply_voice_guard,
    draft_quality_issues,
    select_response_move,
    should_avoid_question,
    voice_guard_prompt,
)
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
            return DraftDecision(False, "no new messages", reason_code="no_new_messages")

        assessment = assess_reply_candidate(
            new_messages=new_messages,
            context=context,
            character=character,
            conversation_reply_enabled=self.conversation_reply_enabled,
        )
        engagement_type = assessment.engagement_type
        source_message_ids = assessment.target_message_ids
        source_id_set = set(source_message_ids)
        focus_messages = [
            message for message in new_messages if message.message_id in source_id_set
        ]
        if assessment.outcome != "reply":
            return DraftDecision(
                False,
                assessment.reason,
                engagement_type=engagement_type,
                source_message_ids=source_message_ids,
                reason_code=assessment.reason_code,
                eligible_source_count=0,
            )
        requires_approval = engagement_type == "proactive" and self.proactive_approval_required
        reason = _engagement_reason(engagement_type)

        if not self.enabled:
            return DraftDecision(
                True,
                f"would reply; {reason}; LLM disabled by NHI_ZUES_LLM_ENABLED",
                draft=None,
                engagement_type=engagement_type,
                requires_approval=requires_approval,
                source_message_ids=source_message_ids,
                reason_code=assessment.reason_code,
                eligible_source_count=len(source_message_ids),
            )
        if not self.generate_drafts:
            return DraftDecision(
                True,
                f"would reply; {reason}; draft generation disabled for this run",
                draft=None,
                engagement_type=engagement_type,
                requires_approval=requires_approval,
                source_message_ids=source_message_ids,
                reason_code=assessment.reason_code,
                eligible_source_count=len(source_message_ids),
            )
        if self.client is None:
            return DraftDecision(
                True,
                f"would reply; {reason}; no OPENAI_API_KEY configured",
                draft=None,
                engagement_type=engagement_type,
                requires_approval=requires_approval,
                source_message_ids=source_message_ids,
                reason_code=assessment.reason_code,
                eligible_source_count=len(source_message_ids),
            )

        transcript = _fit_text(_format_message_lines(context[-32:], max_chars=320), self.max_input_chars)
        newest_messages = _format_message_lines(new_messages[-5:])
        focused_messages = _format_message_lines(focus_messages, max_chars=320)
        topic_summary = ", ".join(topic for topic, _ in topics.top_topics) or "none"
        user_memory = _format_user_memories(user_memories, user_instructions)
        user_arc = _fit_text(_format_user_recent_arcs(context, focus_messages, character), 1600)
        seed = f"{channel_id}:{','.join(message.message_id for message in focus_messages)}"
        recent_character_lines = _recent_character_lines(context, character)
        own_strategy = _fit_text(_format_own_post_strategy(context, character), 1600)
        avoid_question = should_avoid_question(
            recent_character_lines=recent_character_lines,
            seed=seed,
        )
        response_move = select_response_move(
            seed=seed,
            avoid_question=avoid_question,
            card_moves=character.response_moves,
        )
        user_prompt = (
            f"Channel: {channel_id}\n"
            f"Character: {character.name}\n"
            f"Tracked topics: {topic_summary}\n\n"
            f"Known user context:\n{user_memory}\n\n"
            f"Recent user arc to use privately:\n{user_arc}\n\n"
            f"Recent account direction to use privately:\n{own_strategy}\n\n"
            f"Recent conversation:\n{transcript}\n\n"
            f"Newest message(s) to react to:\n{newest_messages or '(none)'}\n\n"
            f"Specific reply target(s):\n{focused_messages or '(none)'}\n\n"
            f"{grounding_prompt(engagement_type=engagement_type)}\n\n"
            f"{conversation_intelligence_prompt(mode=engagement_type)}\n\n"
            f"{voice_guard_prompt(avoid_question=avoid_question, recent_character_lines=recent_character_lines, response_move=response_move)}\n\n"
            "Draft one reply for approval. Aim for 12-35 words and never exceed 45 words. Prefer one sentence. Two sentences only if the second adds a real detail. "
            "No polished mini-essay, no recap, no default opener."
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
                source_message_ids=source_message_ids,
                reason_code=assessment.reason_code,
                eligible_source_count=len(source_message_ids),
            )

        draft, records, issues = await self._generate_with_quality_retry(
            instructions=instructions,
            user_prompt=user_prompt,
            seed=seed,
            avoid_question=avoid_question,
            recent_character_lines=recent_character_lines,
            focus_messages=focus_messages,
        )
        if _is_no_reply(draft):
            return DraftDecision(
                False,
                f"{reason}; model declined weak or unclear target",
                engagement_type=engagement_type,
                requires_approval=requires_approval,
                source_message_ids=source_message_ids,
                reason_code="model_declined",
                eligible_source_count=len(source_message_ids),
                model_call_count=len(records),
            )
        cost = sum(record.cost_usd for record in records)
        retry_count = max(0, len(records) - 1)
        quality_note = f"; style_retry={retry_count}" if retry_count else ""
        return DraftDecision(
            True,
            f"{reason}; api_cost=${cost:.6f}{quality_note}",
            draft=draft.strip(),
            engagement_type=engagement_type,
            requires_approval=requires_approval,
            source_message_ids=source_message_ids,
            reason_code=assessment.reason_code,
            eligible_source_count=len(source_message_ids),
            model_call_count=len(records),
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
        original_draft: str = "",
        target_user_key: str = "",
        targeted_context: str = "",
    ) -> DraftDecision:
        if not self.enabled:
            return DraftDecision(True, "would regenerate; LLM disabled by NHI_ZUES_LLM_ENABLED")
        if self.client is None:
            return DraftDecision(True, "would regenerate; no OPENAI_API_KEY configured")

        transcript = _fit_text(_format_message_lines(context[-36:], max_chars=320), self.max_input_chars)
        target = _target_user_line(target_user_key, user_memories)
        user_memory = _format_user_memories(user_memories, user_instructions)
        target_messages = [message for message in context if _message_user_key(message) == target_user_key]
        focus_messages = _focus_messages_for_manual(context, target_user_key=target_user_key)
        user_arc = _fit_text(_format_user_recent_arcs(context, target_messages[-1:], character), 1600)
        seed = f"{channel_id}:{target_user_key}:{operator_instruction}"
        recent_character_lines = _recent_character_lines(context, character)
        own_strategy = _fit_text(_format_own_post_strategy(context, character), 1600)
        avoid_question = should_avoid_question(
            recent_character_lines=recent_character_lines,
            seed=seed,
        )
        response_move = select_response_move(
            seed=seed,
            avoid_question=avoid_question,
            card_moves=character.response_moves,
        )
        user_prompt = (
            f"Channel: {channel_id}\n"
            f"Character: {character.name}\n"
            f"Target user: {target}\n\n"
            f"Known user context:\n{user_memory}\n\n"
            f"Recent user arc to use privately:\n{user_arc}\n\n"
            f"Recent account direction to use privately:\n{own_strategy}\n\n"
            f"Recent conversation:\n{transcript}\n\n"
            f"Original queued draft:\n{sanitize_outgoing_draft(original_draft) or '(none)'}\n\n"
            f"Current editor draft:\n{sanitize_outgoing_draft(current_draft) or '(none)'}\n\n"
            f"Operator direction:\n{operator_instruction or 'Make a better natural response for the selected context.'}\n\n"
            f"Targeted regeneration context:\n{targeted_context or '(none)'}\n\n"
            f"{grounding_prompt(engagement_type='manual')}\n\n"
            f"{conversation_intelligence_prompt(mode='manual')}\n\n"
            f"{voice_guard_prompt(avoid_question=avoid_question, recent_character_lines=recent_character_lines, response_move=response_move)}\n\n"
            "Generate one revised Discord reply for approval. Aim for 12-35 words and never exceed 45 words. Prefer one sentence. Two sentences only if the second adds a real detail. "
            "Use the original queued draft and current editor draft as reference material, especially when the operator says things like 'instead of that' or 'make that more specific.' "
            "Keep any useful conversational hook from the earlier draft, but rewrite the parts the operator is correcting. Do not preserve the draft's structure if it sounds synthetic."
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

        draft, records, issues = await self._generate_with_quality_retry(
            instructions=instructions,
            user_prompt=user_prompt,
            seed=seed,
            avoid_question=avoid_question,
            recent_character_lines=recent_character_lines,
            focus_messages=focus_messages,
        )
        cost = sum(record.cost_usd for record in records)
        retry_count = max(0, len(records) - 1)
        quality_note = f"; style_retry={retry_count}" if retry_count else ""
        return DraftDecision(
            True,
            f"manual approval draft generated; api_cost=${cost:.6f}{quality_note}",
            draft=draft.strip(),
            engagement_type="manual",
            requires_approval=True,
            source_message_ids=tuple(message.message_id for message in focus_messages),
        )

    async def _generate_with_quality_retry(
        self,
        *,
        instructions: str,
        user_prompt: str,
        seed: str,
        avoid_question: bool,
        recent_character_lines: list[str],
        focus_messages: list[MessageRecord] | None = None,
    ):
        draft, record = await self._request_draft(
            instructions=instructions,
            user_prompt=user_prompt,
            seed=seed,
            avoid_question=avoid_question,
        )
        records = [record]
        issues = _draft_quality_issues(draft, recent_character_lines, focus_messages or [])
        if not issues:
            return draft, records, issues

        best_draft = draft
        best_issues = issues
        current_draft = draft
        current_issues = issues
        for attempt in range(1, 3):
            retry_prompt = _quality_retry_prompt(user_prompt, current_draft, current_issues)
            estimated_input_tokens = BudgetManager.approx_tokens(instructions + "\n" + retry_prompt)
            retry_budget = self.budget.check(
                estimated_input_tokens=estimated_input_tokens,
                max_output_tokens=self.max_output_tokens,
            )
            if not retry_budget.allowed:
                break

            retry_draft, retry_record = await self._request_draft(
                instructions=instructions,
                user_prompt=retry_prompt,
                seed=f"{seed}:style-retry:{attempt}",
                avoid_question=avoid_question,
            )
            records.append(retry_record)
            retry_issues = _draft_quality_issues(retry_draft, recent_character_lines, focus_messages or [])
            if not retry_issues:
                return retry_draft, records, issues
            if len(retry_issues) < len(best_issues):
                best_draft = retry_draft
                best_issues = retry_issues
            current_draft = retry_draft
            current_issues = retry_issues
        return best_draft, records, best_issues

    async def _request_draft(
        self,
        *,
        instructions: str,
        user_prompt: str,
        seed: str,
        avoid_question: bool,
    ):
        response = await self.client.responses.create(
            model=self.model,
            instructions=instructions,
            input=user_prompt,
            max_output_tokens=self.max_output_tokens,
        )
        estimated_input_tokens = BudgetManager.approx_tokens(instructions + "\n" + user_prompt)
        input_tokens, output_tokens = _usage_tokens(response, estimated_input_tokens)
        record = self.budget.record(input_tokens=input_tokens, output_tokens=output_tokens)
        draft = getattr(response, "output_text", "") or ""
        draft = self._finalize_draft(draft, seed=seed, avoid_question=avoid_question)
        return draft, record

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
    del topics  # Topic summaries are prompt context, never permission to engage.
    text = "\n".join(message.text for message in messages)
    if contains_card_alias(text, character):
        return "direct"
    if contains_card_trigger(text, character):
        return "proactive"
    if conversation_reply_enabled:
        return "conversation"
    return "none"


def _engagement_reason(engagement_type: str) -> str:
    if engagement_type == "direct":
        return "direct name cue"
    if engagement_type == "conversation":
        return "conversation reply opportunity"
    if engagement_type == "proactive":
        return "tracked topic cue"
    return "reply opportunity"


def _focus_messages_for_reply(
    new_messages: list[MessageRecord],
    context: list[MessageRecord],
    character: CharacterCard,
    *,
    engagement_type: str,
) -> list[MessageRecord]:
    fresh_candidates = [
        message
        for message in new_messages
        if _is_focus_candidate(message, character)
    ]
    if engagement_type == "direct":
        direct = [
            message
            for message in fresh_candidates
            if _contains_alias(message.text, character)
        ]
        return direct[-3:] or fresh_candidates[-3:]
    if engagement_type == "proactive":
        triggered = [
            message
            for message in fresh_candidates
            if _contains_trigger(message.text, character)
        ]
        return (triggered or fresh_candidates)[-4:]
    if engagement_type == "conversation":
        return fresh_candidates[-4:]
    return [
        message
        for message in context[-4:]
        if _is_focus_candidate(message, character)
    ]


def _focus_messages_for_manual(
    context: list[MessageRecord],
    *,
    target_user_key: str = "",
) -> list[MessageRecord]:
    if target_user_key:
        targeted = [
            message
            for message in context
            if _message_user_key(message) == target_user_key and _message_has_text(message)
        ]
        if targeted:
            return targeted[-3:]
    return [message for message in context[-4:] if _message_has_text(message)]


def _focus_issue(
    focus_messages: list[MessageRecord],
    character: CharacterCard,
    *,
    engagement_type: str,
) -> str:
    if not focus_messages:
        return "no non-self source message to answer"
    if engagement_type == "manual":
        return ""
    if any(_looks_like_meta_suspicion(message.text) for message in focus_messages):
        return "AI/bot-suspicion thread skipped unless manually selected"
    if any(_is_conversation_worthy(message.text, character) for message in focus_messages):
        return ""
    if engagement_type == "proactive":
        return "tracked topic source too thin or stale for a grounded draft"
    if engagement_type in {"conversation", "direct"}:
        return "conversation source too thin or ambiguous for a grounded draft"
    return ""


def grounding_prompt(*, engagement_type: str) -> str:
    lines = [
        "Grounding gate:",
        "- The Specific reply target(s) are the only messages you are answering. The wider transcript is just context.",
        "- If there is no clear useful reply to the target, output exactly NO_REPLY.",
        "- Do not answer app/game/system feed text unless a real user is clearly discussing it.",
        "- Do not invent a subject from banter fragments, acknowledgements, or one-word reactions.",
        "- Do not import personal biography, possessions, work, family, location, or past experiences unless the target directly makes that relevant.",
        "- Do not introduce a new technical, legal, medical, or evidentiary claim unless the target/context already contains that lane.",
        "- Pick one grounded point from the target and either add one small take, ask one concrete detail, or pass.",
    ]
    if engagement_type == "conversation":
        lines.append("- Conversation mode is allowed to stay silent. A weak forced reply is worse than no draft.")
    return "\n".join(lines)


def _is_focus_candidate(message: MessageRecord, character: CharacterCard) -> bool:
    if _is_character_message(message, character):
        return False
    if not _message_has_text(message):
        return False
    if _looks_like_app_feed(message):
        return False
    return True


def _message_has_text(message: MessageRecord) -> bool:
    return bool(str(getattr(message, "text", "") or "").strip())


def _looks_like_app_feed(message: MessageRecord) -> bool:
    return looks_like_app_feed(message)


def _looks_like_meta_suspicion(text: str) -> bool:
    return looks_like_meta_suspicion(text)


def _is_conversation_worthy(text: str, character: CharacterCard) -> bool:
    return is_conversation_worthy_text(text, character)


def _reply_worthiness_score(cleaned: str, words: list[str]) -> int:
    if not words:
        return 0
    signals = detect_text_signals(cleaned)
    return min(
        5,
        (3 if signals.concrete_question else 0)
        + (3 if signals.compact_opinion else 0)
        + (2 if signals.disagreement else 0)
        + (2 if signals.reason_or_evidence else 0)
        + int(signals.specific),
    )


def _has_claim_marker(cleaned: str) -> bool:
    signals = detect_text_signals(cleaned)
    return signals.compact_opinion or signals.disagreement or signals.reason_or_evidence


def _contains_alias(text: str, character: CharacterCard) -> bool:
    return contains_card_alias(text, character)


def _contains_trigger(text: str, character: CharacterCard) -> bool:
    return contains_card_trigger(text, character)


def _term_in_text(term: str, text: str) -> bool:
    return term_in_text(term, text)


def _clean_focus_text(text: str) -> str:
    return " ".join(sanitize_outgoing_draft(str(text or "")).lower().split())


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
            f"- {clean_discord_display_name(user.display_name)}: {user.message_count} observed messages; recent topics: {topics}.{summary}{instruction_text}"
        )
    return "\n".join(lines)


def _format_message_lines(messages: list[MessageRecord], *, max_chars: int = 260) -> str:
    lines: list[str] = []
    for message in messages:
        text = " ".join(sanitize_outgoing_draft(str(message.text or "")).split())
        if not text:
            continue
        if len(text) > max_chars:
            text = text[: max_chars - 3].rstrip() + "..."
        lines.append(f"- {clean_discord_display_name(message.author)}: {text}")
    return "\n".join(lines)


def _format_user_recent_arcs(
    context: list[MessageRecord],
    source_messages: list[MessageRecord],
    character: CharacterCard,
    *,
    per_user_limit: int = 5,
    user_limit: int = 5,
) -> str:
    wanted_keys: list[str] = []
    seen: set[str] = set()
    for message in reversed(source_messages):
        if _is_character_message(message, character) or not str(message.text or "").strip():
            continue
        key = _message_user_key(message)
        if not key or key in seen:
            continue
        wanted_keys.append(key)
        seen.add(key)
        if len(wanted_keys) >= user_limit:
            break
    if not wanted_keys:
        for message in reversed(context):
            if _is_character_message(message, character) or not str(message.text or "").strip():
                continue
            key = _message_user_key(message)
            if not key or key in seen:
                continue
            wanted_keys.append(key)
            seen.add(key)
            if len(wanted_keys) >= user_limit:
                break

    if not wanted_keys:
        return "No useful per-user arc."

    sections: list[str] = []
    for key in reversed(wanted_keys):
        user_messages = [
            message
            for message in context
            if _message_user_key(message) == key
            and not _is_character_message(message, character)
            and str(message.text or "").strip()
        ][-per_user_limit:]
        if not user_messages:
            continue
        display_name = clean_discord_display_name(user_messages[-1].author)
        sections.append(f"{display_name}:")
        for message in user_messages:
            text = " ".join(sanitize_outgoing_draft(str(message.text or "")).split())
            if len(text) > 180:
                text = text[:177].rstrip() + "..."
            sections.append(f"  - {text}")
    return "\n".join(sections) if sections else "No useful per-user arc."


def conversation_intelligence_prompt(*, mode: str) -> str:
    lines = [
        "Conversation intelligence:",
        "- Treat the transcript as context, not material to summarize.",
        "- Use the per-user arc only as private continuity for tone and direction. Do not recap it or mention that you remember it.",
        "- Treat recent account-authored posts as your own prior comments, never as someone else's prompt.",
        "- If the newest live item is only your own prior message, do not invent a reply to yourself.",
        "- Do not revive an older point just because it appears in memory. If the room moved on, move with the newest live point.",
        "- Before drafting, check what the character already said recently. Do not restate the same claim, metaphor, or angle.",
        "- If the same topic continues, advance one step: narrow the claim, add a concrete objection, concede a small point, or pivot to a fresher implication.",
        "- Pick one live point, tension, or implied claim and answer that. Do not respond to every sentence.",
        "- Have an actual take: buy it, doubt it, split the difference, draw a line, or admit a rough bias.",
        "- For lore-heavy topics, choose one concrete lane at a time instead of listing every related theory or reference.",
        "- It is okay to be imperfect or half-informed, but the reply still needs a direction and a reason someone could challenge.",
        "- Do not quote the user and then interpret the quote. React as if you already heard it in the room.",
        "- Prefer a specific opinion, correction, or side comment over a broad question.",
        "- Let memory show through only as a small concrete detail. Do not announce continuity or tracking.",
        "- Output only the final Discord reply.",
    ]
    if mode == "proactive":
        lines.append("- If nobody addressed the character, use a light side comment instead of steering the whole room.")
    elif mode == "direct":
        lines.append("- If addressed directly, answer the person first before adding any tangent.")
    elif mode == "manual":
        lines.append("- Follow the operator direction, but do not preserve a synthetic structure from the earlier draft.")
    return "\n".join(lines)


def _target_user_line(target_user_key: str, user_memories: list[UserMemory]) -> str:
    if not target_user_key:
        return "none selected"
    for user in user_memories:
        if user.user_key == target_user_key:
            return f"{clean_discord_display_name(user.display_name)} ({user.user_key})"
    return target_user_key


def _recent_character_lines(context: list[MessageRecord], character: CharacterCard) -> list[str]:
    names = _character_names(character)
    return [
        sanitize_outgoing_draft(message.text)
        for message in context
        if own_identity.is_own_message(message, character_names=names) and message.text
    ][-8:]


def _is_character_message(message: MessageRecord, character: CharacterCard) -> bool:
    return own_identity.is_own_message(message, character_names=_character_names(character))


def _message_user_key(message: MessageRecord) -> str:
    if message.author_id:
        return f"discord:{message.author_id}"
    return f"name:{_normalize_author(message.author)}"


def _normalize_author(value: str) -> str:
    return own_identity.normalize_author(value)


def _character_names(character: CharacterCard) -> tuple[str, ...]:
    return (character.name, *character.aliases)


def _format_own_post_strategy(context: list[MessageRecord], character: CharacterCard) -> str:
    own_lines = _recent_character_lines(context, character)
    if not own_lines:
        return "No recent account-authored posts in this remembered channel context."
    lines = [
        "These are the account's own recent posts in this channel. Use them as private continuity and strategy, not reply targets.",
        "If they show the operator manually steering the account into playing dumb, pushing back, conceding, or changing tone, continue that direction without announcing it.",
        "Do not restate the same claim, source ask, metaphor, or punchline. If the topic continues, advance or pivot one small step.",
    ]
    for item in own_lines[-8:]:
        text = " ".join(sanitize_outgoing_draft(item).split())
        if len(text) > 220:
            text = text[:217].rstrip() + "..."
        lines.append(f"- {text}")
    return "\n".join(lines)


def _draft_quality_issues(
    text: str,
    recent_character_lines: list[str],
    focus_messages: list[MessageRecord] | None = None,
) -> list[str]:
    if _is_no_reply(text):
        return []
    issues = draft_quality_issues(text)
    repeat_issue = own_identity.repeated_own_point_issue(text, recent_character_lines)
    if repeat_issue:
        issues.append(repeat_issue)
    grounding_issue = _unsupported_personal_claim_issue(text, focus_messages or [])
    if grounding_issue:
        issues.append(grounding_issue)
    return issues


def _is_no_reply(text: str) -> bool:
    normalized = re.sub(r"[^a-z]+", "_", str(text or "").strip().lower()).strip("_")
    return normalized == "no_reply"


def _unsupported_personal_claim_issue(
    text: str,
    focus_messages: list[MessageRecord],
) -> str:
    if not focus_messages:
        return ""
    lowered = str(text or "").lower()
    focus_text = " ".join(_clean_focus_text(message.text) for message in focus_messages)
    biography_patterns = (
        re.compile(r"\bi (?:live|work|grew up|was born|went to school|own|play)\b"),
        re.compile(r"\bmy (?:age|family|hometown|job|parents|school|workplace)\b"),
        re.compile(r"\bwhen i was (?:a kid|younger|in school)\b"),
    )
    unsupported = [match.group(0) for pattern in biography_patterns if (match := pattern.search(lowered))]
    if unsupported and not any(claim in focus_text for claim in unsupported):
        return "injects unrelated personal biography"
    return ""


def _quality_retry_prompt(user_prompt: str, draft: str, issues: list[str]) -> str:
    issue_lines = "\n".join(f"- {issue}" for issue in issues)
    return (
        f"{user_prompt}\n\n"
        "The previous draft failed the voice quality gate:\n"
        f"{draft}\n\n"
        f"Problems:\n{issue_lines}\n\n"
        "Rewrite from scratch. Make it sound like a normal quick Discord reply, not a polished response. "
        "Use fewer words, fewer abstractions, no stock opener, no quote-and-interpret structure, and no more than one like-comparison. "
        "If the target is too thin or unclear to answer without inventing context, output exactly NO_REPLY."
    )


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
