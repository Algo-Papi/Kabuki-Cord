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
    scan_enabled: bool = True
    engage_enabled: bool = True
    react_enabled: bool = False
    auto_respond_enabled: bool = False
    poll_seconds: float | None = None


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
    poll_seconds: float
    scanner_max_channels_per_cycle: int
    scanner_cycle_sleep_seconds: float
    scanner_channel_settle_seconds: float
    scanner_min_channel_delay_seconds: float
    scanner_max_channel_delay_seconds: float
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
        poll_seconds=_env_float("NHI_ZUES_POLL_SECONDS", 180.0),
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
            poll_seconds = server.get("poll_seconds")
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
                        scan_enabled=bool(channel.get("scan_enabled", True)),
                        engage_enabled=bool(channel.get("engage_enabled", True)),
                        react_enabled=bool(channel.get("react_enabled", False)),
                        auto_respond_enabled=bool(channel.get("auto_respond_enabled", False)),
                        poll_seconds=float(poll_seconds) if poll_seconds else None,
                    )
                )
        if targets:
            return tuple(targets)
    return _parse_channels(fallback_raw)
