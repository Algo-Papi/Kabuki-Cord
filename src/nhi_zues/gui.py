from __future__ import annotations

import asyncio
import hashlib
import json
import mimetypes
import os
import re
import secrets as token_secrets
import subprocess
import sys
import threading
import time
import urllib.error
import urllib.request
from dataclasses import asdict
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from importlib.metadata import PackageNotFoundError, version
from pathlib import Path
from urllib.parse import unquote, urlparse

from dotenv import load_dotenv

from .approvals import ApprovalQueue
from .browser import DiscordWebSession
from .budget import BudgetManager
from .character import CharacterCardStore
from .character_memory import CharacterMemoryStore
from .config import AppConfig, load_config
from .events import EventLog
from .llm import ReplyPlanner
from .memory import ConversationMemory
from .runner import NhiZuesRunner
from .secrets import discord_credential_status, get_discord_credentials, set_discord_credentials
from .user_instructions import UserInstructionStore


ROOT = Path.cwd()
WEB_ROOT = ROOT / "web"
SESSION_TOKEN = token_secrets.token_urlsafe(32)
DISCORD_SESSION_LOCK = threading.Lock()
OPENAI_MODEL_FALLBACKS = [
    {
        "id": "gpt-5.4-nano",
        "label": "GPT-5.4 nano - lowest-cost default",
        "source": "fallback",
    },
    {
        "id": "gpt-5.4-mini",
        "label": "GPT-5.4 mini - balanced low-cost drafting",
        "source": "fallback",
    },
    {
        "id": "gpt-5.4",
        "label": "GPT-5.4 - stronger reasoning",
        "source": "fallback",
    },
    {
        "id": "gpt-5.5",
        "label": "GPT-5.5 - strongest, higher cost",
        "source": "fallback",
    },
]


class GuiHandler(BaseHTTPRequestHandler):
    server_version = "KabukiCord/0.1"

    def do_GET(self) -> None:
        parsed = urlparse(self.path)
        if parsed.path == "/api/session":
            if not self._host_allowed():
                self._json({"ok": False, "error": "Forbidden."}, status=403)
                return
            self._json({"ok": True, "token": SESSION_TOKEN})
            return
        if parsed.path.startswith("/api/server-icons/"):
            if not self._host_allowed():
                self._json({"ok": False, "error": "Forbidden."}, status=403)
                return
            self._file(_server_icon_path(parsed.path.removeprefix("/api/server-icons/")))
            return
        if parsed.path.startswith("/api/") and not self._authorized_api(require_json=False):
            self._json({"ok": False, "error": "Forbidden."}, status=403)
            return
        if parsed.path == "/api/state":
            self._json(app_state())
            return
        if parsed.path == "/api/usage":
            self._json(usage_state())
            return
        if parsed.path == "/":
            self._file(WEB_ROOT / "index.html")
            return
        self._file(self._static_path(parsed.path))

    def do_POST(self) -> None:
        parsed = urlparse(self.path)
        if not self._authorized_api(require_json=True):
            self._json({"ok": False, "error": "Forbidden."}, status=403)
            return
        body = self._read_json()
        if parsed.path == "/api/servers":
            config = load_config()
            _write_json(config.servers_file, body)
            self._json({"ok": True, "state": app_state()})
            return
        if parsed.path == "/api/discord-sync-servers":
            try:
                self._json(sync_discord_servers())
            except RuntimeError as exc:
                self._json({"ok": False, "error": str(exc)}, status=400)
            return
        if parsed.path == "/api/settings":
            update_env(body)
            self._json({"ok": True, "state": app_state()})
            return
        if parsed.path == "/api/openai-models":
            self._json(fetch_openai_models())
            return
        if parsed.path == "/api/discord-credentials":
            try:
                set_discord_credentials(
                    email=str(body.get("email") or "").strip() or None,
                    password=str(body.get("password") or "") or None,
                )
            except RuntimeError as exc:
                self._json({"ok": False, "error": str(exc)}, status=500)
                return
            self._json({"ok": True, "state": app_state()})
            return
        if parsed.path == "/api/discord-login":
            start_discord_login()
            self._json({"ok": True, "message": "Discord sign-in window launched."})
            return
        if parsed.path == "/api/open-discord-channel":
            try:
                start_discord_channel(body)
            except RuntimeError as exc:
                self._json({"ok": False, "error": str(exc)}, status=400)
                return
            self._json({"ok": True, "state": app_state(), "message": "Discord channel window launched."})
            return
        if parsed.path == "/api/runtime-start":
            RUNTIME.start()
            self._json({"ok": True, "state": app_state()})
            return
        if parsed.path == "/api/runtime-pause":
            RUNTIME.pause()
            self._json({"ok": True, "state": app_state()})
            return
        if parsed.path == "/api/approval-update":
            try:
                update_approval(body)
            except (KeyError, ValueError) as exc:
                self._json({"ok": False, "error": str(exc)}, status=400)
                return
            self._json({"ok": True, "state": app_state()})
            return
        if parsed.path == "/api/approval-discard":
            discard_approval(body)
            self._json({"ok": True, "state": app_state()})
            return
        if parsed.path == "/api/approval-send":
            try:
                send_approval(body)
            except RuntimeError as exc:
                self._json({"ok": False, "error": str(exc)}, status=400)
                return
            self._json({"ok": True, "state": app_state()})
            return
        if parsed.path == "/api/approval-regenerate":
            try:
                regenerate_approval(body)
            except RuntimeError as exc:
                self._json({"ok": False, "error": str(exc)}, status=400)
                return
            self._json({"ok": True, "state": app_state()})
            return
        if parsed.path == "/api/approval-create":
            try:
                create_manual_approval(body)
            except RuntimeError as exc:
                self._json({"ok": False, "error": str(exc)}, status=400)
                return
            self._json({"ok": True, "state": app_state()})
            return
        if parsed.path == "/api/update-check":
            self._json(check_update(apply_update=False))
            return
        if parsed.path == "/api/update":
            self._json(check_update(apply_update=True))
            return
        if parsed.path == "/api/character":
            card_path = str(body.get("path") or "")
            payload = body.get("card")
            if not card_path or not isinstance(payload, dict):
                self._json({"ok": False, "error": "Missing character card payload."}, status=400)
                return
            target = _safe_character_path(card_path)
            target.parent.mkdir(parents=True, exist_ok=True)
            target.write_text(json.dumps(payload, indent=2), encoding="utf-8")
            self._json({"ok": True, "state": app_state()})
            return
        if parsed.path == "/api/character-memory":
            config = load_config()
            store = CharacterMemoryStore(config.state_dir / "character_memory")
            card_id = str(body.get("card_id") or config.character_card)
            note = str(body.get("note") or "")
            note_type = str(body.get("type") or "story")
            if note_type == "behavior":
                store.add_behavior_note(card_id, note)
            else:
                store.add_story_claim(card_id, note)
            self._json({"ok": True, "state": app_state()})
            return
        if parsed.path == "/api/user-instruction":
            config = load_config()
            user_key = str(body.get("user_key") or "")
            note = str(body.get("note") or "")
            server_id = str(body.get("server_id") or "") or None
            channel_id = str(body.get("channel_id") or "") or None
            if not user_key or not note:
                self._json({"ok": False, "error": "Missing user key or note."}, status=400)
                return
            UserInstructionStore(config.state_dir / "user_instructions.json").add(
                user_key,
                note,
                server_id=server_id,
                channel_id=channel_id,
            )
            self._json({"ok": True, "state": app_state()})
            return
        self._json({"ok": False, "error": "Unknown endpoint."}, status=404)

    def log_message(self, format: str, *args) -> None:
        return

    def _read_json(self) -> dict:
        length = int(self.headers.get("Content-Length", "0"))
        if length == 0:
            return {}
        return json.loads(self.rfile.read(length).decode("utf-8"))

    def _json(self, payload: dict, *, status: int = 200) -> None:
        data = json.dumps(payload).encode("utf-8")
        self.send_response(status)
        self.send_header("Content-Type", "application/json; charset=utf-8")
        self.send_header("Content-Length", str(len(data)))
        self.end_headers()
        self.wfile.write(data)

    def _file(self, path: Path | None) -> None:
        if path is None:
            self.send_response(403)
            self.end_headers()
            return
        if not path.exists() or not path.is_file():
            self.send_response(404)
            self.end_headers()
            return
        content_type = mimetypes.guess_type(str(path))[0] or "application/octet-stream"
        data = path.read_bytes()
        self.send_response(200)
        self.send_header("Content-Type", content_type)
        self.send_header("Content-Length", str(len(data)))
        self.end_headers()
        self.wfile.write(data)

    def _static_path(self, raw_path: str) -> Path | None:
        relative = unquote(raw_path.lstrip("/"))
        target = (WEB_ROOT / relative).resolve()
        base = WEB_ROOT.resolve()
        if target != base and base not in target.parents:
            return None
        return target

    def _authorized_api(self, *, require_json: bool) -> bool:
        if not self._host_allowed():
            return False
        if self.headers.get("X-Kabuki-Token") != SESSION_TOKEN:
            return False
        if require_json and "application/json" not in self.headers.get("Content-Type", ""):
            return False
        origin = self.headers.get("Origin") or self.headers.get("Referer")
        if origin and not self._same_origin(origin):
            return False
        return True

    def _host_allowed(self) -> bool:
        host = (self.headers.get("Host") or "").split(":", 1)[0].strip("[]").lower()
        return host in {"127.0.0.1", "localhost", "::1"}

    def _same_origin(self, value: str) -> bool:
        parsed = urlparse(value)
        host = (parsed.hostname or "").lower()
        return host in {"127.0.0.1", "localhost", "::1"}


class RuntimeController:
    def __init__(self) -> None:
        self._lock = threading.Lock()
        self._thread: threading.Thread | None = None
        self._stop = threading.Event()
        self._running = False
        self._last_started_at: float | None = None
        self._last_run_at: float | None = None
        self._last_error: str = ""

    def start(self) -> None:
        with self._lock:
            self._stop.clear()
            if self._thread and self._thread.is_alive():
                self._running = True
                return
            self._running = True
            self._last_started_at = time.time()
            self._thread = threading.Thread(target=self._loop, name="kabuki-runtime", daemon=True)
            self._thread.start()

    def pause(self) -> None:
        with self._lock:
            self._running = False
            self._stop.set()

    def state(self) -> dict:
        thread_alive = bool(self._thread and self._thread.is_alive())
        return {
            "running": self._running and thread_alive,
            "paused": not (self._running and thread_alive),
            "last_started_at": self._last_started_at,
            "last_run_at": self._last_run_at,
            "last_error": self._last_error,
        }

    def _loop(self) -> None:
        while not self._stop.is_set():
            with self._lock:
                active = self._running
            if not active:
                break

            try:
                config = load_config()
                if not config.channels:
                    self._last_error = "No channels are enabled for Observe."
                    self._stop.wait(5)
                    continue
                if not DISCORD_SESSION_LOCK.acquire(blocking=False):
                    self._last_error = "Discord browser profile is busy."
                    self._stop.wait(5)
                    continue
                try:
                    asyncio.run(NhiZuesRunner(config).run_once())
                    self._last_run_at = time.time()
                    self._last_error = ""
                finally:
                    DISCORD_SESSION_LOCK.release()
                interval = max(config.poll_seconds, 5)
            except Exception as exc:
                self._last_error = str(exc)
                interval = 10

            if self._stop.wait(interval):
                break

        with self._lock:
            self._running = False


RUNTIME = RuntimeController()


def app_state() -> dict:
    load_dotenv(override=True)
    config = load_config()
    env = read_env()
    model_catalog = model_catalog_state(config)
    return {
        "app": {
            "name": "Kabuki-Cord",
            "version": package_version(),
            "profile_dir": str(config.profile_dir),
            "state_dir": str(config.state_dir),
            "servers_file": str(config.servers_file),
            "active_character_card": config.character_card,
            "llm_enabled": config.llm_enabled,
            "draft_in_dry_run": config.draft_in_dry_run,
            "dry_run": config.dry_run,
            "proactive_approval_required": config.proactive_approval_required,
            "openai_model": config.openai_model,
            "api_key_set": bool(os.getenv("OPENAI_API_KEY")),
            "max_daily_usd": config.max_daily_usd,
            "max_session_usd": config.max_session_usd,
            "max_llm_calls_per_run": config.max_llm_calls_per_run,
            "writing_mistake_rate": config.writing_mistake_rate,
            "writing_quirk": config.writing_quirk,
            "writing_misspellings": config.writing_misspellings,
            "typing_indicator_enabled": config.typing_indicator_enabled,
            "typing_min_seconds": config.typing_min_seconds,
            "typing_max_seconds": config.typing_max_seconds,
            "typing_chars_per_second": config.typing_chars_per_second,
        },
        "discord": discord_credential_status(),
        "runtime": RUNTIME.state(),
        "updates": update_state(),
        "model_catalog": {
            "live": model_catalog["live"],
            "source": model_catalog["source"],
            "message": model_catalog["message"],
            "fetched_at": model_catalog.get("fetched_at", ""),
        },
        "model_options": model_catalog["models"],
        "env": {
            "OPENAI_MODEL": env.get("OPENAI_MODEL", ""),
            "NHI_ZUES_LLM_ENABLED": env.get("NHI_ZUES_LLM_ENABLED", "false"),
            "NHI_ZUES_DRAFT_IN_DRY_RUN": env.get("NHI_ZUES_DRAFT_IN_DRY_RUN", "false"),
            "NHI_ZUES_DRY_RUN": env.get("NHI_ZUES_DRY_RUN", "true"),
            "NHI_ZUES_PROACTIVE_APPROVAL_REQUIRED": env.get(
                "NHI_ZUES_PROACTIVE_APPROVAL_REQUIRED", "true"
            ),
            "NHI_ZUES_CHARACTER_CARD": env.get("NHI_ZUES_CHARACTER_CARD", ""),
            "NHI_ZUES_MAX_DAILY_USD": env.get("NHI_ZUES_MAX_DAILY_USD", "0.25"),
            "NHI_ZUES_MAX_SESSION_USD": env.get("NHI_ZUES_MAX_SESSION_USD", "0.05"),
            "NHI_ZUES_MAX_LLM_CALLS_PER_RUN": env.get("NHI_ZUES_MAX_LLM_CALLS_PER_RUN", "3"),
            "NHI_ZUES_WRITING_MISTAKE_RATE": env.get("NHI_ZUES_WRITING_MISTAKE_RATE", "0.06"),
            "NHI_ZUES_WRITING_QUIRK": env.get("NHI_ZUES_WRITING_QUIRK", "lowercase_no_commas"),
            "NHI_ZUES_WRITING_MISSPELLINGS": env.get(
                "NHI_ZUES_WRITING_MISSPELLINGS",
                "definitely:definately,because:becuase,probably:prolly",
            ),
            "NHI_ZUES_TYPING_INDICATOR_ENABLED": env.get("NHI_ZUES_TYPING_INDICATOR_ENABLED", "true"),
            "NHI_ZUES_TYPING_MIN_SECONDS": env.get("NHI_ZUES_TYPING_MIN_SECONDS", "2.5"),
            "NHI_ZUES_TYPING_MAX_SECONDS": env.get("NHI_ZUES_TYPING_MAX_SECONDS", "18.0"),
            "NHI_ZUES_TYPING_CHARS_PER_SECOND": env.get("NHI_ZUES_TYPING_CHARS_PER_SECOND", "10.0"),
        },
        "servers": _read_json(config.servers_file, default={"servers": []}),
        "characters": character_cards(config.character_dir),
        "active_character": read_character(config.character_dir, config.character_card),
        "character_memory": character_memory_state(config.state_dir, config.character_card),
        "user_instructions": user_instruction_state(config.state_dir),
        "usage": usage_state(),
        "approvals": [asdict(item) for item in ApprovalQueue(config.state_dir / "approvals.json").list()],
        "recent_posters": recent_posters_state(config.state_dir / "memory.json"),
        "observed": observed_conversation_state(config.state_dir / "memory.json"),
        "history": conversation_history_state(
            config.state_dir / "memory.json",
            config.state_dir / "events.json",
        ),
        "memory": memory_state(config.state_dir / "memory.json"),
    }


def usage_state() -> dict:
    config = load_config()
    budget = BudgetManager(
        config.state_dir / "usage.json",
        model=config.openai_model,
        max_daily_usd=config.max_daily_usd,
        max_session_usd=config.max_session_usd,
        max_calls_per_run=config.max_llm_calls_per_run,
    )
    return budget.summary()


def model_catalog_state(config: AppConfig) -> dict:
    cache = _read_json(config.state_dir / "openai_models.json", default={})
    cached_models = cache.get("models") if isinstance(cache, dict) else None
    live = bool(cached_models)
    models = _merge_model_options(
        config.openai_model,
        cached_models if isinstance(cached_models, list) else OPENAI_MODEL_FALLBACKS,
        include_fallbacks=not live,
    )
    source = "OpenAI /v1/models" if live else "fallback"
    message = (
        f"{len(models)} account model options cached from OpenAI."
        if live
        else "Fallback model suggestions shown. Add an API key and refresh models for this project."
    )
    return {
        "live": live,
        "source": source,
        "message": message,
        "fetched_at": str(cache.get("fetched_at") or "") if isinstance(cache, dict) else "",
        "models": models,
    }


def fetch_openai_models() -> dict:
    load_dotenv(override=True)
    config = load_config()
    fallback = model_catalog_state(config)
    if not config.openai_api_key:
        return {
            "ok": False,
            "live": False,
            "source": fallback["source"],
            "message": "OpenAI API key is missing. Save a key first, then refresh models.",
            "models": fallback["models"],
        }

    request = urllib.request.Request(
        "https://api.openai.com/v1/models",
        headers={
            "Authorization": f"Bearer {config.openai_api_key}",
            "Content-Type": "application/json",
        },
        method="GET",
    )
    try:
        with urllib.request.urlopen(request, timeout=20) as response:
            payload = json.loads(response.read().decode("utf-8"))
    except urllib.error.HTTPError as exc:
        return {
            "ok": False,
            "live": False,
            "source": fallback["source"],
            "message": _safe_openai_error(exc),
            "models": fallback["models"],
        }
    except Exception as exc:
        return {
            "ok": False,
            "live": False,
            "source": fallback["source"],
            "message": f"Could not fetch OpenAI models: {_redact_secret_text(str(exc))}",
            "models": fallback["models"],
        }

    raw_models = payload.get("data", [])
    fetched_options = []
    if isinstance(raw_models, list):
        for item in raw_models:
            if not isinstance(item, dict):
                continue
            model_id = str(item.get("id") or "").strip()
            if not _looks_like_text_model(model_id):
                continue
            fetched_options.append(
                {
                    "id": model_id,
                    "label": model_id,
                    "source": "openai",
                    "owned_by": str(item.get("owned_by") or ""),
                    "created": item.get("created"),
                }
            )

    if not fetched_options:
        models = _merge_model_options(
            config.openai_model,
            OPENAI_MODEL_FALLBACKS,
            include_fallbacks=True,
        )
        message = "OpenAI returned models, but none matched Kabuki-Cord's text/reasoning filter."
        return {
            "ok": False,
            "live": False,
            "source": "fallback",
            "message": message,
            "models": models,
            "total_models": len(raw_models) if isinstance(raw_models, list) else 0,
        }

    models = _merge_model_options(config.openai_model, fetched_options)
    fetched_at = time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime())
    cache_payload = {
        "live": True,
        "source": "OpenAI /v1/models",
        "fetched_at": fetched_at,
        "models": models,
        "total_models": len(raw_models) if isinstance(raw_models, list) else len(models),
    }
    cache_path = config.state_dir / "openai_models.json"
    _write_json(cache_path, cache_payload)
    return {
        "ok": True,
        **cache_payload,
        "message": f"Loaded {len(models)} OpenAI text/reasoning model options for this key.",
    }


def _merge_model_options(
    current_model: str,
    model_options: list | tuple,
    *,
    include_fallbacks: bool = False,
) -> list[dict]:
    by_id: dict[str, dict] = {}
    if include_fallbacks:
        for option in OPENAI_MODEL_FALLBACKS:
            by_id[option["id"]] = dict(option)
    for option in model_options:
        if isinstance(option, str):
            model_id = option.strip()
            payload = {"id": model_id, "label": model_id, "source": "openai"}
        elif isinstance(option, dict):
            model_id = str(option.get("id") or "").strip()
            payload = dict(option)
            payload["id"] = model_id
            payload["label"] = str(payload.get("label") or model_id)
        else:
            continue
        if model_id:
            by_id[model_id] = payload
    if current_model and current_model not in by_id:
        by_id[current_model] = {
            "id": current_model,
            "label": f"{current_model} - current setting",
            "source": "current",
        }
    return sorted(by_id.values(), key=_model_option_sort_key)


def _model_option_sort_key(option: dict) -> tuple[int, str]:
    model_id = str(option.get("id") or "")
    preferred_order = {
        "gpt-5.4-nano": 0,
        "gpt-5.4-mini": 1,
        "gpt-5.4": 2,
        "gpt-5.5": 3,
    }
    return (preferred_order.get(model_id, 20), model_id)


def _looks_like_text_model(model_id: str) -> bool:
    if not model_id:
        return False
    lowered = model_id.lower()
    excluded = (
        "embedding",
        "moderation",
        "realtime",
        "whisper",
        "tts",
        "transcribe",
        "image",
        "dall-e",
        "audio",
        "search",
    )
    if any(part in lowered for part in excluded):
        return False
    modern_gpt_prefixes = (
        "gpt-5",
        "gpt-4.5",
        "gpt-4.1",
        "gpt-4o",
        "chatgpt-4o",
    )
    return lowered.startswith(modern_gpt_prefixes) or (
        lowered.startswith("o") and len(lowered) > 1 and lowered[1].isdigit()
    )


def _safe_openai_error(exc: urllib.error.HTTPError) -> str:
    detail = ""
    try:
        raw = exc.read().decode("utf-8", errors="replace")
        payload = json.loads(raw)
        detail = str(payload.get("error", {}).get("message") or raw)
    except Exception:
        detail = str(exc)
    detail = _redact_secret_text(detail)
    return f"OpenAI model fetch failed ({exc.code}): {detail}"


def _redact_secret_text(value: str) -> str:
    return re.sub(r"sk-[A-Za-z0-9_\-]{8,}", "sk-...redacted", value)


def sync_discord_servers() -> dict:
    config = load_config()
    if not DISCORD_SESSION_LOCK.acquire(blocking=False):
        raise RuntimeError("Discord browser profile is busy. Pause scanning or close the sign-in window, then try again.")
    try:
        try:
            discovered = asyncio.run(_discover_discord_workspace(config))
        except RuntimeError:
            raise
        except Exception as exc:
            raise RuntimeError(
                "Discord sync failed. Close any open Kabuki Discord sign-in windows and try again."
            ) from exc
    finally:
        DISCORD_SESSION_LOCK.release()
    payload = _read_json(config.servers_file, default={"servers": []})
    server_list = payload.get("servers")
    if not isinstance(server_list, list):
        server_list = []

    by_id: dict[str, dict] = {}
    for item in server_list:
        if isinstance(item, dict) and item.get("server_id"):
            by_id[str(item["server_id"])] = item

    added = 0
    updated = 0
    channels_discovered = 0
    channels_added = 0
    channels_updated = 0
    next_server_list: list[dict] = []
    for server in discovered:
        server_id = str(server["server_id"])
        label = str(server.get("label") or "")
        existing = by_id.get(server_id)
        if existing is None:
            existing = {
                "server_id": server_id,
                "label": label,
                "character_card": None,
                "poll_seconds": 120,
                "channels": [],
            }
            server_list.append(existing)
            by_id[server_id] = existing
            added += 1
        if label and str(existing.get("label") or "").strip() != label:
            existing["label"] = label
            updated += 1
        icon_url = str(server.get("icon_url") or "")
        icon_path = _cache_server_icon(config.state_dir, server_id, icon_url)
        if icon_path:
            existing["icon_path"] = icon_path
        channel_stats = _merge_channels(existing, server.get("channels", []))
        channels_discovered += channel_stats["discovered"]
        channels_added += channel_stats["added"]
        channels_updated += channel_stats["updated"]
        next_server_list.append(existing)

    discovered_ids = {str(server["server_id"]) for server in discovered}
    next_server_list.extend(
        server
        for server in server_list
        if isinstance(server, dict) and str(server.get("server_id") or "") not in discovered_ids
    )

    next_payload = {**payload, "servers": next_server_list}
    _write_json(config.servers_file, next_payload)
    return {
        "ok": True,
        "discovered": len(discovered),
        "added": added,
        "updated": updated,
        "channels_discovered": channels_discovered,
        "channels_added": channels_added,
        "channels_updated": channels_updated,
        "state": app_state(),
    }


def _merge_channels(server: dict, discovered_channels: list[dict]) -> dict[str, int]:
    existing_channels = server.get("channels")
    if not isinstance(existing_channels, list):
        existing_channels = []

    by_id: dict[str, dict] = {}
    for item in existing_channels:
        if isinstance(item, dict) and item.get("channel_id"):
            by_id[str(item["channel_id"])] = item

    updated = 0
    added = 0
    next_channels: list[dict] = []
    for channel in discovered_channels:
        channel_id = str(channel.get("channel_id") or "")
        if not channel_id:
            continue
        existing = by_id.get(channel_id)
        if existing is None:
            existing = {
                "channel_id": channel_id,
                "label": str(channel.get("label") or ""),
                "channel_type": str(channel.get("channel_type") or "text"),
                "category": str(channel.get("category") or ""),
                "scan_enabled": False,
                "engage_enabled": False,
                "auto_respond_enabled": False,
            }
            added += 1
        else:
            for key in ("label", "channel_type", "category"):
                value = str(channel.get(key) or "")
                if value and str(existing.get(key) or "") != value:
                    existing[key] = value
                    updated += 1
        next_channels.append(existing)

    discovered_ids = {str(channel.get("channel_id") or "") for channel in discovered_channels}
    next_channels.extend(
        channel
        for channel in existing_channels
        if (
            isinstance(channel, dict)
            and str(channel.get("channel_id") or "") not in discovered_ids
            and str(channel.get("label") or "").strip()
        )
    )
    server["channels"] = next_channels
    return {"discovered": len(discovered_channels), "added": added, "updated": updated}


async def _discover_discord_workspace(config: AppConfig) -> list[dict]:
    credentials = get_discord_credentials()
    async with DiscordWebSession(
        config.profile_dir,
        browser_channel=config.browser_channel,
        headless=config.headless,
    ) as session:
        logged_in = await session.login_if_needed(
            email=credentials.email,
            password=credentials.password,
            timeout_seconds=120,
        )
        if not logged_in:
            raise RuntimeError("Discord is not signed in. Use Sign In first, then Sync Servers.")
        servers = await session.discover_servers()
        for server in servers:
            server["channels"] = await session.discover_channels(server["server_id"])
    if not servers:
        raise RuntimeError("No Discord servers were found in the signed-in browser profile.")
    return servers


def character_cards(card_dir: Path) -> list[dict]:
    base = card_dir.resolve()
    cards: list[dict] = []
    for path in [base / "default.json", *sorted((base / "cards").glob("*.json"))]:
        if path.exists():
            rel = path.relative_to(base).as_posix()
            payload = json.loads(path.read_text(encoding="utf-8"))
            cards.append({"path": rel, "name": payload.get("name", rel), "card": payload})
    return cards


def read_character(card_dir: Path, card_path: str) -> dict:
    base = card_dir.resolve()
    path = _safe_character_path(card_path, card_dir=base)
    if not path.exists():
        path = base / "default.json"
    return {"path": path.relative_to(base).as_posix(), "card": json.loads(path.read_text(encoding="utf-8"))}


def memory_state(path: Path) -> dict:
    payload = _read_json(path, default={"channels": {}, "users": {}})
    users = payload.get("users", {})
    return {
        "channel_count": len(payload.get("channels", {})),
        "seen_ids": len(payload.get("seen_ids", [])),
        "user_count": len(users),
        "users": [
            {"user_key": key, **value}
            for key, value in sorted(users.items(), key=lambda item: item[1].get("display_name", ""))
        ][:80],
    }


def observed_conversation_state(path: Path) -> dict:
    payload = _read_json(path, default={"channels": {}, "users": {}})
    result: dict[str, dict] = {}
    for channel_id, rows in payload.get("channels", {}).items():
        recent = rows[-16:]
        poster_summaries = []
        seen: set[str] = set()
        for row in reversed(recent):
            key = _message_user_key(row)
            if key in seen:
                continue
            seen.add(key)
            user_messages = [
                item for item in reversed(rows) if _message_user_key(item) == key and str(item.get("text") or "").strip()
            ][:4]
            texts = [str(item.get("text") or "").strip() for item in reversed(user_messages)]
            poster_summaries.append(
                {
                    "user_key": key,
                    "display_name": str(row.get("author") or "unknown"),
                    "message_count": len(user_messages),
                    "summary": _summarize_messages(texts),
                    "recent_text": texts[-1] if texts else "",
                }
            )
            if len(poster_summaries) >= 6:
                break
        result[str(channel_id)] = {
            "recent_messages": [_message_preview(row) for row in recent[-12:]],
            "poster_summaries": poster_summaries,
        }
    return result


def conversation_history_state(memory_path: Path, event_path: Path) -> dict:
    memory_payload = _read_json(memory_path, default={"channels": {}})
    event_payload = _read_json(event_path, default={"items": []})
    events_by_channel: dict[str, list[dict]] = {}
    for event in event_payload.get("items", []):
        channel_id = str(event.get("channel_id") or "")
        events_by_channel.setdefault(channel_id, []).append(event)
    return {
        str(channel_id): {
            "messages": [_message_preview(row) for row in rows[-60:]],
            "events": events_by_channel.get(str(channel_id), [])[-60:],
        }
        for channel_id, rows in memory_payload.get("channels", {}).items()
    }


def recent_posters_state(path: Path) -> dict:
    payload = _read_json(path, default={"channels": {}})
    result: dict[str, list[dict]] = {}
    for channel_id, rows in payload.get("channels", {}).items():
        posters: list[dict] = []
        seen: set[str] = set()
        for row in reversed(rows):
            author = str(row.get("author") or "").strip()
            if not author:
                continue
            author_id = row.get("author_id")
            key = _message_user_key(row)
            if key in seen:
                continue
            seen.add(key)
            posters.append(
                {
                    "user_key": key,
                    "display_name": author,
                    "author_id": author_id,
                    "reply_prefix": f"@{author}",
                }
            )
            if len(posters) >= 6:
                break
        result[str(channel_id)] = posters
    return result


def character_memory_state(state_dir: Path, card_id: str) -> dict:
    memory = CharacterMemoryStore(state_dir / "character_memory").load(card_id)
    return asdict(memory)


def user_instruction_state(state_dir: Path) -> dict:
    path = state_dir / "user_instructions.json"
    return _read_json(path, default={"items": []})


def update_approval(body: dict) -> None:
    approval_id = str(body.get("approval_id") or "")
    draft = str(body.get("draft") or "").strip()
    if not approval_id or not draft:
        raise ValueError("Missing approval id or draft text.")
    config = load_config()
    item = ApprovalQueue(config.state_dir / "approvals.json").update_draft(approval_id, draft)
    EventLog(config.state_dir / "events.json").add(
        event_type="approval_updated",
        server_id=item.server_id,
        channel_id=item.channel_id,
        summary="Approval draft edited by operator.",
        draft=draft,
    )


def discard_approval(body: dict) -> None:
    approval_id = str(body.get("approval_id") or "")
    if not approval_id:
        return
    config = load_config()
    queue = ApprovalQueue(config.state_dir / "approvals.json")
    item = queue.get(approval_id)
    if queue.remove(approval_id) and item:
        EventLog(config.state_dir / "events.json").add(
            event_type="approval_discarded",
            server_id=item.server_id,
            channel_id=item.channel_id,
            summary="Approval draft discarded by operator.",
            draft=item.draft,
        )


def send_approval(body: dict) -> None:
    approval_id = str(body.get("approval_id") or "")
    draft = str(body.get("draft") or "").strip()
    if not approval_id or not draft:
        raise RuntimeError("Missing approval id or draft text.")

    config = load_config()
    if config.dry_run:
        raise RuntimeError("Dry-run is enabled. Turn off Dry-run mode in API & Runtime before sending.")
    if not DISCORD_SESSION_LOCK.acquire(blocking=False):
        raise RuntimeError("Discord browser profile is busy. Pause scanning or close the sign-in window, then try again.")
    try:
        queue = ApprovalQueue(config.state_dir / "approvals.json")
        item = queue.update_draft(approval_id, draft)
        asyncio.run(_send_approval_message(config, item.server_id, item.channel_id, draft))
        queue.remove(approval_id)
        EventLog(config.state_dir / "events.json").add(
            event_type="approval_sent",
            server_id=item.server_id,
            channel_id=item.channel_id,
            summary="Approved draft sent by operator.",
            draft=draft,
        )
    finally:
        DISCORD_SESSION_LOCK.release()


def regenerate_approval(body: dict) -> None:
    approval_id = str(body.get("approval_id") or "")
    operator_instruction = str(body.get("instruction") or "").strip()
    target_user_key = str(body.get("target_user_key") or "")
    current_draft = str(body.get("draft") or "").strip()
    if not approval_id:
        raise RuntimeError("Missing approval id.")
    config = load_config()
    queue = ApprovalQueue(config.state_dir / "approvals.json")
    item = queue.get(approval_id)
    if item is None:
        raise RuntimeError("Unknown approval.")
    decision = asyncio.run(
        _generate_manual_decision(
            config,
            server_id=item.server_id,
            channel_id=item.channel_id,
            target_user_key=target_user_key,
            current_draft=current_draft or item.draft,
            operator_instruction=operator_instruction,
        )
    )
    if not decision.draft:
        raise RuntimeError(decision.reason)
    queue.update_draft(approval_id, decision.draft)
    EventLog(config.state_dir / "events.json").add(
        event_type="approval_regenerated",
        server_id=item.server_id,
        channel_id=item.channel_id,
        summary=operator_instruction or decision.reason,
        draft=decision.draft,
        user_key=target_user_key,
    )


def create_manual_approval(body: dict) -> None:
    server_id = str(body.get("server_id") or "")
    channel_id = str(body.get("channel_id") or "")
    target_user_key = str(body.get("target_user_key") or "")
    operator_instruction = str(body.get("instruction") or "").strip()
    if not server_id or not channel_id:
        raise RuntimeError("Missing server or channel.")
    config = load_config()
    decision = asyncio.run(
        _generate_manual_decision(
            config,
            server_id=server_id,
            channel_id=channel_id,
            target_user_key=target_user_key,
            current_draft="",
            operator_instruction=operator_instruction,
        )
    )
    if not decision.draft:
        raise RuntimeError(decision.reason)
    context = _memory_context(config.state_dir / "memory.json", channel_id)
    character = CharacterCardStore(config.character_dir, config.character_card).for_server(
        server_id,
        _server_character_card(config, server_id),
    )
    item = ApprovalQueue(config.state_dir / "approvals.json").add(
        server_id=server_id,
        channel_id=channel_id,
        character_name=character.name,
        engagement_type="manual",
        reason=operator_instruction or decision.reason,
        draft=decision.draft,
        source_messages=context[-8:],
    )
    EventLog(config.state_dir / "events.json").add(
        event_type="manual_approval_created",
        server_id=server_id,
        channel_id=channel_id,
        summary=operator_instruction or decision.reason,
        draft=item.draft,
        user_key=target_user_key,
    )


def _message_preview(row: dict) -> dict:
    return {
        "server_id": str(row.get("server_id") or ""),
        "channel_id": str(row.get("channel_id") or ""),
        "message_id": str(row.get("message_id") or ""),
        "author": str(row.get("author") or "unknown"),
        "author_id": row.get("author_id"),
        "user_key": _message_user_key(row),
        "text": str(row.get("text") or ""),
        "observed_at": str(row.get("observed_at") or ""),
    }


def _message_user_key(row: dict) -> str:
    author_id = row.get("author_id")
    if author_id:
        return f"discord:{author_id}"
    author = " ".join(str(row.get("author") or "unknown").lower().strip().split())
    return f"name:{author or 'unknown'}"


def _summarize_messages(texts: list[str]) -> str:
    if not texts:
        return "No recent readable message text."
    terms: list[str] = []
    ignored = {
        "that",
        "this",
        "with",
        "from",
        "they",
        "have",
        "just",
        "like",
        "what",
        "your",
        "about",
        "there",
        "would",
        "could",
        "really",
    }
    for text in texts:
        for raw in text.split():
            term = raw.strip(".,!?;:()[]{}\"'").lower()
            if len(term) >= 5 and term not in ignored and term not in terms:
                terms.append(term)
            if len(terms) >= 5:
                break
        if len(terms) >= 5:
            break
    topic_text = ", ".join(terms) if terms else "the current thread"
    latest = texts[-1]
    if len(latest) > 130:
        latest = latest[:127].rstrip() + "..."
    return f"Talking about {topic_text}. Latest: {latest}"


def _memory_context(memory_path: Path, channel_id: str):
    memory = ConversationMemory(memory_path)
    memory.load()
    return memory.context(channel_id, limit=24)


def _server_character_card(config: AppConfig, server_id: str) -> str | None:
    payload = _read_json(config.servers_file, default={"servers": []})
    for server in payload.get("servers", []):
        if str(server.get("server_id") or "") == server_id:
            return server.get("character_card") or None
    return None


async def _generate_manual_decision(
    config: AppConfig,
    *,
    server_id: str,
    channel_id: str,
    target_user_key: str,
    current_draft: str,
    operator_instruction: str,
):
    memory = ConversationMemory(config.state_dir / "memory.json")
    memory.load()
    context = memory.context(channel_id, limit=24)
    user_memories = memory.user_context_for(context, limit=10)
    user_notes = UserInstructionStore(config.state_dir / "user_instructions.json").for_users(
        [user.user_key for user in user_memories],
        server_id=server_id,
        channel_id=channel_id,
    )
    card_id = _server_character_card(config, server_id) or config.character_card
    character = CharacterCardStore(config.character_dir, config.character_card).for_server(server_id, card_id)
    character_memory = CharacterMemoryStore(config.state_dir / "character_memory").load(card_id)
    planner = ReplyPlanner(
        api_key=config.openai_api_key,
        model=config.openai_model,
        enabled=config.llm_enabled,
        generate_drafts=True,
        budget=BudgetManager(
            config.state_dir / "usage.json",
            model=config.openai_model,
            max_daily_usd=config.max_daily_usd,
            max_session_usd=config.max_session_usd,
            max_calls_per_run=config.max_llm_calls_per_run,
        ),
        max_output_tokens=config.max_output_tokens,
        max_input_chars=config.max_input_chars,
        proactive_approval_required=True,
        writing_mistake_rate=config.writing_mistake_rate,
        writing_quirk=config.writing_quirk,
        writing_misspellings=config.writing_misspellings,
    )
    return await planner.regenerate(
        channel_id=channel_id,
        character=character,
        character_memory=character_memory,
        context=context,
        user_memories=user_memories,
        user_instructions=user_notes,
        current_draft=current_draft,
        operator_instruction=operator_instruction,
        target_user_key=target_user_key,
    )


async def _send_approval_message(config: AppConfig, server_id: str, channel_id: str, draft: str) -> None:
    credentials = get_discord_credentials()
    async with DiscordWebSession(
        config.profile_dir,
        browser_channel=config.browser_channel,
        headless=config.headless,
    ) as session:
        logged_in = await session.login_if_needed(
            email=credentials.email,
            password=credentials.password,
            timeout_seconds=120,
        )
        if not logged_in:
            raise RuntimeError("Discord is not signed in. Use Sign In first.")
        current_url = await session.navigate_channel(server_id, channel_id)
        if channel_id not in current_url:
            raise RuntimeError("Discord redirected away from the approval channel.")
        await session.send_message(
            draft,
            typing_enabled=config.typing_indicator_enabled,
            typing_min_seconds=config.typing_min_seconds,
            typing_max_seconds=config.typing_max_seconds,
            typing_chars_per_second=config.typing_chars_per_second,
        )


def start_discord_channel(body: dict) -> None:
    server_id = str(body.get("server_id") or "")
    channel_id = str(body.get("channel_id") or "")
    if not server_id or not channel_id:
        raise RuntimeError("Missing server or channel.")
    if not DISCORD_SESSION_LOCK.acquire(blocking=False):
        raise RuntimeError("Discord browser profile is busy. Pause scanning or close the sign-in window, then try again.")
    DISCORD_SESSION_LOCK.release()
    RUNTIME.pause()
    kwargs = {}
    if sys.platform == "win32":
        kwargs["creationflags"] = subprocess.CREATE_NO_WINDOW
    subprocess.Popen(
        [sys.executable, "-m", "nhi_zues.cli", "--open-channel", server_id, channel_id],
        cwd=ROOT,
        close_fds=True,
        **kwargs,
    )


def read_env() -> dict[str, str]:
    env_path = ROOT / ".env"
    values: dict[str, str] = {}
    if not env_path.exists():
        return values
    for line in env_path.read_text(encoding="utf-8").splitlines():
        if "=" not in line or line.strip().startswith("#"):
            continue
        key, value = line.split("=", 1)
        values[key.strip()] = value.strip()
    return values


def update_env(values: dict) -> None:
    env_path = ROOT / ".env"
    existing = read_env()
    allowed = {
        "OPENAI_API_KEY",
        "OPENAI_MODEL",
        "NHI_ZUES_LLM_ENABLED",
        "NHI_ZUES_DRAFT_IN_DRY_RUN",
        "NHI_ZUES_DRY_RUN",
        "NHI_ZUES_PROACTIVE_APPROVAL_REQUIRED",
        "NHI_ZUES_CHARACTER_CARD",
        "NHI_ZUES_MAX_DAILY_USD",
        "NHI_ZUES_MAX_SESSION_USD",
        "NHI_ZUES_MAX_LLM_CALLS_PER_RUN",
        "NHI_ZUES_WRITING_MISTAKE_RATE",
        "NHI_ZUES_WRITING_QUIRK",
        "NHI_ZUES_WRITING_MISSPELLINGS",
        "NHI_ZUES_TYPING_INDICATOR_ENABLED",
        "NHI_ZUES_TYPING_MIN_SECONDS",
        "NHI_ZUES_TYPING_MAX_SECONDS",
        "NHI_ZUES_TYPING_CHARS_PER_SECOND",
    }
    for key, value in values.items():
        if key not in allowed:
            continue
        if key == "OPENAI_API_KEY" and not str(value).strip():
            continue
        existing[key] = str(value).strip()
    env_path.write_text("\n".join(f"{key}={value}" for key, value in existing.items()) + "\n", encoding="utf-8")


def start_discord_login() -> None:
    kwargs = {}
    if sys.platform == "win32":
        kwargs["creationflags"] = subprocess.CREATE_NO_WINDOW
    subprocess.Popen(
        [sys.executable, "-m", "nhi_zues.cli", "--login"],
        cwd=ROOT,
        close_fds=True,
        **kwargs,
    )


def update_state() -> dict:
    remote = _git(["remote", "get-url", "origin"], check=False).stdout.strip()
    return {
        "remote": remote,
        "remote_allowed": _remote_allowed(remote) if remote else False,
    }


def check_update(*, apply_update: bool) -> dict:
    inside = _git(["rev-parse", "--is-inside-work-tree"], check=False)
    if inside.returncode != 0:
        return {"ok": False, "error": "This install is not running from a Git checkout."}

    remote = _git(["remote", "get-url", "origin"], check=False).stdout.strip()
    if not _remote_allowed(remote):
        return {"ok": False, "error": "Origin remote is not Algo-Papi/Kabuki-Cord."}

    fetched = _git(["fetch", "origin", "main"], check=False)
    if fetched.returncode != 0:
        return {"ok": False, "error": fetched.stderr.strip() or "Git fetch failed."}

    local_result = _git(["rev-parse", "HEAD"], check=False)
    remote_result = _git(["rev-parse", "origin/main"], check=False)
    if local_result.returncode != 0 or remote_result.returncode != 0:
        return {"ok": False, "error": "Could not compare local checkout with origin/main."}

    local = local_result.stdout.strip()
    remote_head = remote_result.stdout.strip()
    behind_result = _git(["rev-list", "--count", "HEAD..origin/main"], check=False)
    ahead_result = _git(["rev-list", "--count", "origin/main..HEAD"], check=False)
    if behind_result.returncode != 0 or ahead_result.returncode != 0:
        return {"ok": False, "error": "Could not calculate Git update distance."}
    behind = int(behind_result.stdout.strip() or "0")
    ahead = int(ahead_result.stdout.strip() or "0")
    payload = {
        "ok": True,
        "local": local,
        "remote": remote_head,
        "behind": behind,
        "ahead": ahead,
        "update_available": behind > 0,
    }
    if not apply_update:
        return payload

    dirty = _git(["status", "--porcelain"]).stdout.strip()
    if dirty:
        return {
            **payload,
            "ok": False,
            "error": "Working tree has local changes; update refused to avoid overwriting work.",
        }
    if behind == 0:
        return {**payload, "updated": False, "message": "Already up to date."}

    pulled = _git(["pull", "--ff-only", "origin", "main"], check=False)
    if pulled.returncode != 0:
        return {"ok": False, "error": pulled.stderr.strip() or "Git pull failed."}
    return {**payload, "updated": True, "message": pulled.stdout.strip()}


def _remote_allowed(remote: str) -> bool:
    normalized = remote.strip().removesuffix(".git")
    if normalized.startswith("git@github.com:"):
        owner_repo = normalized.removeprefix("git@github.com:")
        return owner_repo.lower() == "algo-papi/kabuki-cord"

    parsed = urlparse(normalized)
    host = (parsed.hostname or "").lower()
    owner_repo = parsed.path.strip("/")
    return host == "github.com" and owner_repo.lower() == "algo-papi/kabuki-cord"


def _git(args: list[str], *, check: bool = True) -> subprocess.CompletedProcess:
    return subprocess.run(
        ["git", *args],
        cwd=ROOT,
        check=check,
        capture_output=True,
        text=True,
        timeout=60,
    )


def package_version() -> str:
    try:
        return version("kabuki-cord")
    except PackageNotFoundError:
        return "0.0.0"


def _safe_character_path(card_path: str, *, card_dir: Path | None = None) -> Path:
    base = card_dir or ROOT / "character_cards"
    target = (base / card_path).resolve()
    if base.resolve() not in target.parents and target != base.resolve():
        raise ValueError("Character card path escapes card directory.")
    return target


def _cache_server_icon(state_dir: Path, server_id: str, icon_url: str) -> str:
    if not icon_url.startswith(("https://", "http://")):
        return ""
    suffix = Path(urlparse(icon_url).path).suffix.lower()
    if suffix not in {".png", ".jpg", ".jpeg", ".webp", ".gif"}:
        suffix = ".webp"
    filename = f"{server_id}-{hashlib.sha256(icon_url.encode('utf-8')).hexdigest()[:12]}{suffix}"
    target_dir = state_dir / "server_icons"
    target = target_dir / filename
    if not target.exists():
        target_dir.mkdir(parents=True, exist_ok=True)
        request = urllib.request.Request(icon_url, headers={"User-Agent": "Kabuki-Cord"})
        with urllib.request.urlopen(request, timeout=20) as response:
            target.write_bytes(response.read())
    return f"/api/server-icons/{filename}"


def _server_icon_path(filename: str) -> Path | None:
    if not filename or "/" in filename or "\\" in filename:
        return None
    target = (load_config().state_dir / "server_icons" / filename).resolve()
    base = (load_config().state_dir / "server_icons").resolve()
    if target != base and base not in target.parents:
        return None
    return target


def _read_json(path: Path, *, default: dict) -> dict:
    if not path.exists():
        return default
    return json.loads(path.read_text(encoding="utf-8"))


def _write_json(path: Path, payload: dict) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload, indent=2), encoding="utf-8")


def main() -> None:
    host = os.getenv("KABUKI_CORD_HOST", "127.0.0.1")
    port = int(os.getenv("KABUKI_CORD_PORT", "8765"))
    server = ThreadingHTTPServer((host, port), GuiHandler)
    print(f"Kabuki-Cord GUI: http://{host}:{port}")
    server.serve_forever()


if __name__ == "__main__":
    main()
