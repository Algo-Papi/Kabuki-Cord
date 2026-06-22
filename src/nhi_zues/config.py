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
    dry_run: bool
    headless: bool
    poll_seconds: float
    channels: tuple[ChannelTarget, ...]
    openai_api_key: str | None
    openai_model: str
    llm_enabled: bool
    draft_in_dry_run: bool
    max_daily_usd: float
    max_session_usd: float
    max_llm_calls_per_run: int
    max_output_tokens: int
    max_input_chars: int
    proactive_approval_required: bool


def load_config() -> AppConfig:
    load_dotenv()

    return AppConfig(
        profile_dir=Path(_env("NHI_ZUES_PROFILE_DIR", ".profiles/nhi-zues")),
        browser_channel=os.getenv("NHI_ZUES_BROWSER_CHANNEL") or None,
        state_dir=Path(_env("NHI_ZUES_STATE_DIR", ".state")),
        servers_file=Path(_env("NHI_ZUES_SERVERS_FILE", "config/servers.json")),
        character_dir=Path(_env("NHI_ZUES_CHARACTER_DIR", "character_cards")),
        character_card=_env("NHI_ZUES_CHARACTER_CARD", "default.json"),
        dry_run=_env_bool("NHI_ZUES_DRY_RUN", default=True),
        headless=_env_bool("NHI_ZUES_HEADLESS", default=False),
        poll_seconds=float(_env("NHI_ZUES_POLL_SECONDS", "20")),
        channels=_load_channels(
            Path(_env("NHI_ZUES_SERVERS_FILE", "config/servers.json")),
            _env("NHI_ZUES_CHANNELS", ""),
        ),
        openai_api_key=os.getenv("OPENAI_API_KEY") or None,
        openai_model=_env("OPENAI_MODEL", "gpt-5.4-nano"),
        llm_enabled=_env_bool("NHI_ZUES_LLM_ENABLED", default=False),
        draft_in_dry_run=_env_bool("NHI_ZUES_DRAFT_IN_DRY_RUN", default=False),
        max_daily_usd=float(_env("NHI_ZUES_MAX_DAILY_USD", "0.25")),
        max_session_usd=float(_env("NHI_ZUES_MAX_SESSION_USD", "0.05")),
        max_llm_calls_per_run=int(_env("NHI_ZUES_MAX_LLM_CALLS_PER_RUN", "3")),
        max_output_tokens=int(_env("NHI_ZUES_MAX_OUTPUT_TOKENS", "120")),
        max_input_chars=int(_env("NHI_ZUES_MAX_INPUT_CHARS", "6000")),
        proactive_approval_required=_env_bool("NHI_ZUES_PROACTIVE_APPROVAL_REQUIRED", default=True),
    )


def _env(name: str, default: str) -> str:
    value = os.getenv(name)
    return default if value is None or value.strip() == "" else value.strip()


def _env_bool(name: str, default: bool) -> bool:
    value = os.getenv(name)
    if value is None or value.strip() == "":
        return default
    return value.strip().lower() in {"1", "true", "yes", "y", "on"}


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
                        auto_respond_enabled=bool(channel.get("auto_respond_enabled", False)),
                        poll_seconds=float(poll_seconds) if poll_seconds else None,
                    )
                )
        if targets:
            return tuple(targets)
    return _parse_channels(fallback_raw)
