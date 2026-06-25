from __future__ import annotations

import os
import json
from dataclasses import dataclass
from pathlib import Path

from dotenv import load_dotenv


@dataclass(frozen=True)
class ChannelTarget:
    server_id: str
    channel_id: str
    label: str = ""
    server_label: str = ""
    character_card: str | None = None
    safety_review_enabled: bool = False
    scan_enabled: bool = True
    engage_enabled: bool = True
    react_enabled: bool = False
    auto_respond_enabled: bool = False


@dataclass(frozen=True)
class AppConfig:
    profile_dir: Path
    browser_channel: str | None
    state_dir: Path
    servers_file: Path
    character_dir: Path
    character_card: str
    runtime_mode: str
    dry_run: bool
    headless: bool
    scanner_max_channels_per_cycle: int
    scanner_cycle_sleep_seconds: float
    scanner_channel_settle_seconds: float
    scanner_min_channel_delay_seconds: float
    scanner_max_channel_delay_seconds: float
    safety_review_exclusive: bool
    safety_review_history_limit: int
    safety_review_scroll_rounds: int
    reply_cooldown_seconds: float
    reply_window_seconds: float
    reply_max_per_window: int
    reply_require_intervening_user: bool
    channels: tuple[ChannelTarget, ...]
    openai_api_key: str | None
    openai_model: str
    llm_enabled: bool
    draft_in_dry_run: bool
    conversation_reply_enabled: bool
    max_daily_usd: float
    max_session_usd: float
    max_llm_calls_per_run: int
    max_output_tokens: int
    max_input_chars: int
    proactive_approval_required: bool
    writing_mistake_rate: float
    writing_quirk: str
    writing_misspellings: str
    reaction_max_per_channel: int
    reaction_threshold: str
    reaction_sample_percent: float
    reaction_force_laugh_percent: float
    reaction_emoji_override: str
    typing_indicator_enabled: bool
    typing_min_seconds: float
    typing_max_seconds: float
    typing_chars_per_second: float


def load_config() -> AppConfig:
    load_dotenv(encoding="utf-8-sig")

    return AppConfig(
        profile_dir=Path(_env("NHI_ZUES_PROFILE_DIR", ".profiles/nhi-zues")),
        browser_channel=os.getenv("NHI_ZUES_BROWSER_CHANNEL") or None,
        state_dir=Path(_env("NHI_ZUES_STATE_DIR", ".state")),
        servers_file=Path(_env("NHI_ZUES_SERVERS_FILE", "config/servers.json")),
        character_dir=Path(_env("NHI_ZUES_CHARACTER_DIR", "character_cards")),
        character_card=_env("NHI_ZUES_CHARACTER_CARD", "default.json"),
        runtime_mode=_runtime_mode(),
        dry_run=_env_bool("NHI_ZUES_DRY_RUN", default=True),
        headless=_env_bool("NHI_ZUES_HEADLESS", default=False),
        scanner_max_channels_per_cycle=max(1, _env_int("NHI_ZUES_SCANNER_MAX_CHANNELS_PER_CYCLE", 1)),
        scanner_cycle_sleep_seconds=max(5.0, _env_float("NHI_ZUES_SCANNER_CYCLE_SLEEP_SECONDS", 45.0)),
        scanner_channel_settle_seconds=max(
            0.0,
            _env_float("NHI_ZUES_SCANNER_CHANNEL_SETTLE_SECONDS", 12.0),
        ),
        scanner_min_channel_delay_seconds=max(
            0.0,
            _env_float("NHI_ZUES_SCANNER_MIN_CHANNEL_DELAY_SECONDS", 12.0),
        ),
        scanner_max_channel_delay_seconds=max(
            0.0,
            _env_float("NHI_ZUES_SCANNER_MAX_CHANNEL_DELAY_SECONDS", 35.0),
        ),
        safety_review_exclusive=_env_bool("NHI_ZUES_SAFETY_REVIEW_EXCLUSIVE", default=True),
        safety_review_history_limit=max(20, _env_int("NHI_ZUES_SAFETY_REVIEW_HISTORY_LIMIT", 420)),
        safety_review_scroll_rounds=max(1, _env_int("NHI_ZUES_SAFETY_REVIEW_SCROLL_ROUNDS", 45)),
        reply_cooldown_seconds=max(0.0, _env_float("NHI_ZUES_REPLY_COOLDOWN_SECONDS", 900.0)),
        reply_window_seconds=max(60.0, _env_float("NHI_ZUES_REPLY_WINDOW_SECONDS", 3600.0)),
        reply_max_per_window=max(0, _env_int("NHI_ZUES_REPLY_MAX_PER_WINDOW", 3)),
        reply_require_intervening_user=_env_bool(
            "NHI_ZUES_REPLY_REQUIRE_INTERVENING_USER",
            default=True,
        ),
        channels=_load_channels(
            Path(_env("NHI_ZUES_SERVERS_FILE", "config/servers.json")),
            _env("NHI_ZUES_CHANNELS", ""),
        ),
        openai_api_key=os.getenv("OPENAI_API_KEY") or None,
        openai_model=_env("OPENAI_MODEL", "gpt-5.4-nano"),
        llm_enabled=_env_bool("NHI_ZUES_LLM_ENABLED", default=False),
        draft_in_dry_run=_env_bool("NHI_ZUES_DRAFT_IN_DRY_RUN", default=False),
        conversation_reply_enabled=_env_bool("NHI_ZUES_CONVERSATION_REPLY_ENABLED", default=False),
        max_daily_usd=float(_env("NHI_ZUES_MAX_DAILY_USD", "0.25")),
        max_session_usd=float(_env("NHI_ZUES_MAX_SESSION_USD", "0.05")),
        max_llm_calls_per_run=int(_env("NHI_ZUES_MAX_LLM_CALLS_PER_RUN", "3")),
        max_output_tokens=int(_env("NHI_ZUES_MAX_OUTPUT_TOKENS", "120")),
        max_input_chars=int(_env("NHI_ZUES_MAX_INPUT_CHARS", "6000")),
        proactive_approval_required=_env_bool("NHI_ZUES_PROACTIVE_APPROVAL_REQUIRED", default=True),
        writing_mistake_rate=_env_float("NHI_ZUES_WRITING_MISTAKE_RATE", 0.06),
        writing_quirk=_env("NHI_ZUES_WRITING_QUIRK", "lowercase_no_commas"),
        writing_misspellings=_env(
            "NHI_ZUES_WRITING_MISSPELLINGS",
            "definitely:definately,because:becuase,probably:prolly",
        ),
        reaction_max_per_channel=max(0, _env_int("NHI_ZUES_REACTION_MAX_PER_CHANNEL", 3)),
        reaction_threshold=_reaction_threshold(),
        reaction_sample_percent=max(0.0, min(_env_float("NHI_ZUES_REACTION_SAMPLE_PERCENT", 0.0), 100.0)),
        reaction_force_laugh_percent=max(
            0.0,
            min(_env_float("NHI_ZUES_REACTION_FORCE_LAUGH_PERCENT", 20.0), 100.0),
        ),
        reaction_emoji_override=_env("NHI_ZUES_REACTION_EMOJI_OVERRIDE", ""),
        typing_indicator_enabled=_env_bool("NHI_ZUES_TYPING_INDICATOR_ENABLED", default=True),
        typing_min_seconds=_env_float("NHI_ZUES_TYPING_MIN_SECONDS", 2.5),
        typing_max_seconds=_env_float("NHI_ZUES_TYPING_MAX_SECONDS", 18.0),
        typing_chars_per_second=_env_float("NHI_ZUES_TYPING_CHARS_PER_SECOND", 10.0),
    )


def _env(name: str, default: str) -> str:
    value = os.getenv(name)
    return default if value is None or value.strip() == "" else value.strip()


def _env_bool(name: str, default: bool) -> bool:
    value = os.getenv(name)
    if value is None or value.strip() == "":
        return default
    return value.strip().lower() in {"1", "true", "yes", "y", "on"}


def _runtime_mode() -> str:
    value = os.getenv("NHI_ZUES_RUNTIME_MODE")
    if value and value.strip():
        cleaned = value.strip().lower().replace("-", "_").replace(" ", "_")
        aliases = {
            "dry": "dry",
            "dry_mode": "dry",
            "full": "full_auto",
            "full_auto": "full_auto",
            "full_auto_mode": "full_auto",
            "semi": "semi_auto",
            "semi_auto": "semi_auto",
            "semi_auto_mode": "semi_auto",
            "live": "live_fire",
            "live_fire": "live_fire",
            "live_fire_mode": "live_fire",
        }
        if cleaned in aliases:
            return aliases[cleaned]

    if _env_bool("NHI_ZUES_DRY_RUN", default=True):
        return "dry"
    if _env_bool("NHI_ZUES_PROACTIVE_APPROVAL_REQUIRED", default=True):
        return "live_fire"
    return "full_auto"


def _reaction_threshold() -> str:
    cleaned = _env("NHI_ZUES_REACTION_THRESHOLD", "normal").lower().replace("-", "_").replace(" ", "_")
    return cleaned if cleaned in {"strict", "normal", "loose"} else "normal"


def _env_float(name: str, default: float) -> float:
    value = os.getenv(name)
    if value is None or value.strip() == "":
        return default
    try:
        return float(value.strip())
    except ValueError:
        return default


def _env_int(name: str, default: int) -> int:
    value = os.getenv(name)
    if value is None or value.strip() == "":
        return default
    try:
        return int(value.strip())
    except ValueError:
        return default


def _parse_channels(raw: str) -> tuple[ChannelTarget, ...]:
    targets: list[ChannelTarget] = []
    for server_group in raw.split(";"):
        server_group = server_group.strip()
        if not server_group:
            continue

        try:
            server_id, channel_ids = server_group.split(":", 1)
        except ValueError as exc:
            raise ValueError(
                "NHI_ZUES_CHANNELS entries must use server_id:channel_id,channel_id"
            ) from exc

        for channel_id in channel_ids.split(","):
            channel_id = channel_id.strip()
            if channel_id:
                targets.append(ChannelTarget(server_id=server_id.strip(), channel_id=channel_id))

    return tuple(targets)


def _load_channels(servers_file: Path, fallback_raw: str) -> tuple[ChannelTarget, ...]:
    if servers_file.exists():
        payload = json.loads(servers_file.read_text(encoding="utf-8"))
        targets: list[ChannelTarget] = []
        for server in payload.get("servers", []):
            server_id = str(server["server_id"]).strip()
            server_label = str(server.get("label") or "")
            character_card = server.get("character_card")
            safety_review_enabled = bool(server.get("safety_review_enabled", False))
            for channel in server.get("channels", []):
                if channel.get("scan_enabled", True) is False:
                    continue
                targets.append(
                    ChannelTarget(
                        server_id=server_id,
                        channel_id=str(channel["channel_id"]).strip(),
                        label=str(channel.get("label") or ""),
                        server_label=server_label,
                        character_card=character_card,
                        safety_review_enabled=safety_review_enabled,
                        scan_enabled=bool(channel.get("scan_enabled", True)),
                        engage_enabled=bool(channel.get("engage_enabled", True)),
                        react_enabled=bool(channel.get("react_enabled", False)),
                        auto_respond_enabled=bool(channel.get("auto_respond_enabled", False)),
                    )
                )
        if targets:
            return tuple(targets)
    return _parse_channels(fallback_raw)
