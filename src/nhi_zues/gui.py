from __future__ import annotations

import asyncio
import hashlib
import ipaddress
import json
import mimetypes
import os
import secrets as token_secrets
import shutil
import subprocess
import sys
import threading
import time
import urllib.request
import webbrowser
from dataclasses import asdict
from datetime import datetime, timezone
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from importlib.metadata import PackageNotFoundError, version
from pathlib import Path
from urllib.parse import unquote, urlparse

from .app_paths import app_data_root, asset_root, legacy_root, web_root
from .approval_state import (
    approval_config_indexes as _approval_config_indexes,
    approval_items_state,
)
from .approval_workflow import (
    approval_source_messages as _approval_source_messages_impl,
    clear_approval_queue as _clear_approval_queue,
    discard_approval as _discard_approval,
    last_approval_source_message as _last_approval_source_message_impl,
    memory_context as _memory_context_impl,
    own_source_block_message as _own_source_block_message_impl,
    server_character_card as _server_character_card_impl,
    update_approval_draft as _update_approval_draft,
)
from .approvals import ApprovalQueue
from .browser import DiscordWebSession, discord_login_blocker_message
from .budget import BudgetManager
from .character import CharacterCardStore
from .character_memory import CharacterMemoryStore
from .config import AppConfig, load_config
from .discord_text import clean_discord_display_name, sanitize_outgoing_draft
from .diagnostics import collect_diagnostics, configure_diagnostic_logging, open_diagnostics_folder
from .events import (
    EventLog,
    normalize_event_metrics,
    normalize_reason_code,
)
from .llm import ReplyPlanner
from .memory import ConversationMemory
from .models import MessageRecord
from .model_catalog import fetch_openai_models, model_catalog_state
from .message_view import (
    draft_with_reply_mention as _draft_with_reply_mention,
    manual_source_messages as _manual_source_messages,
    message_preview as _message_preview,
    message_record_user_key as _message_record_user_key,
    message_row_sort_key as _message_row_sort_key,
    message_user_key as _message_user_key,
    reply_mention_prefix as _reply_mention_prefix,
    sorted_message_rows as _sorted_message_rows,
    summarize_messages as _summarize_messages,
)
from .output_guard import outgoing_block_reason
from .reactions import suggest_emoji_reaction
from .redaction import redact_secret_text as _redact_secret_text
from .reply_ledger import ReplyLedger, duplicate_reply_message
from .state_io import read_json_file, write_text_file
from .runtime_controller import RuntimeController
from .safety_review import SafetyReviewQueue
from .scan_estimates import (
    estimated_channel_scan_seconds as _estimated_channel_scan_seconds,  # noqa: F401
    estimated_loop_seconds as _estimated_loop_seconds,  # noqa: F401
)
from .secrets import (
    clear_discord_credentials,
    clear_openai_api_key,
    discord_credential_status,
    get_discord_credentials,
    set_discord_credentials,
    set_openai_api_key,
)
from .server_sync import merge_channels as _merge_channels_impl
from .server_sync import merge_discovered_servers
from .settings import read_settings, update_settings
from .user_instructions import UserInstructionStore


ROOT = legacy_root()
WEB_ROOT = web_root()
ASSET_ROOT = asset_root()
SESSION_TOKEN = token_secrets.token_urlsafe(32)
DISCORD_SESSION_LOCK = threading.Lock()
DISCORD_LOCK_WAIT_SECONDS = 45.0
APPROVAL_REGENERATION_LOCKS: dict[str, threading.Lock] = {}
APPROVAL_REGENERATION_LOCKS_LOCK = threading.Lock()
APPROVAL_SEND_LOCKS: dict[str, threading.Lock] = {}
APPROVAL_SEND_LOCKS_LOCK = threading.Lock()
UPDATE_STATE_CACHE: dict[str, object] | None = None
UPDATE_STATE_CACHE_AT = 0.0
UPDATE_STATE_CACHE_LOCK = threading.Lock()
UPDATE_STATE_CACHE_SECONDS = 300.0


def _is_loopback_host(host: str) -> bool:
    normalized = host.strip("[]").lower()
    if normalized == "localhost":
        return True
    try:
        return ipaddress.ip_address(normalized).is_loopback
    except ValueError:
        return False


class GuiHandler(BaseHTTPRequestHandler):
    server_version = "KabukiCord/0.1"

    def do_GET(self) -> None:
        parsed = urlparse(self.path)
        if parsed.path == "/api/session":
            if not self._request_allowed():
                self._json({"ok": False, "error": "Forbidden."}, status=403)
                return
            self._json({"ok": True, "token": SESSION_TOKEN})
            return
        if parsed.path.startswith("/api/server-icons/"):
            if not self._request_allowed():
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
        if parsed.path == "/api/monitor-state":
            self._json(monitor_state())
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
        try:
            body = self._read_json()
        except ValueError as exc:
            self._json({"ok": False, "error": str(exc)}, status=400)
            return
        if parsed.path == "/api/servers":
            config = load_config()
            previous = _read_config_json(config.servers_file, default={"servers": []})
            _write_json(config.servers_file, body)
            _log_channel_autonomy_changes(config, previous, body)
            self._json({"ok": True, "state": app_state()})
            return
        if parsed.path == "/api/discord-sync-servers":
            try:
                self._json(sync_discord_servers())
            except RuntimeError as exc:
                self._json({"ok": False, "error": str(exc)}, status=400)
            return
        if parsed.path == "/api/discord-repair-server":
            try:
                self._json(repair_discord_server(body))
            except RuntimeError as exc:
                self._json({"ok": False, "error": str(exc)}, status=400)
            return
        if parsed.path == "/api/channel-backfill":
            try:
                self._json(backfill_channel_history(body))
            except RuntimeError as exc:
                self._json({"ok": False, "error": str(exc)}, status=400)
            return
        if parsed.path == "/api/channel-refresh":
            try:
                self._json(refresh_channel_latest(body))
            except RuntimeError as exc:
                self._json({"ok": False, "error": str(exc)}, status=400)
            return
        if parsed.path == "/api/reaction-suggest":
            try:
                self._json(suggest_reaction(body))
            except RuntimeError as exc:
                self._json({"ok": False, "error": str(exc)}, status=400)
            return
        if parsed.path == "/api/unresponded-dismiss":
            try:
                dismissed = dismiss_unresponded_replies(body)
            except (ValueError, RuntimeError) as exc:
                status = 400 if isinstance(exc, ValueError) else 500
                self._json({"ok": False, "error": str(exc)}, status=status)
                return
            self._json({"ok": True, "dismissed": dismissed, "state": app_state()})
            return
        if parsed.path == "/api/safety-review-dismiss":
            try:
                dismissed = dismiss_safety_reviews(body)
            except ValueError as exc:
                self._json({"ok": False, "error": str(exc)}, status=400)
                return
            self._json({"ok": True, "dismissed": dismissed, "state": app_state()})
            return
        if parsed.path == "/api/settings":
            previous_config = load_config()
            try:
                update_env(body)
            except (ValueError, RuntimeError) as exc:
                status = 400 if isinstance(exc, ValueError) else 500
                self._json({"ok": False, "error": str(exc)}, status=status)
                return
            _log_settings_security_changes(previous_config, load_config(), body)
            self._json({"ok": True, "state": app_state()})
            return
        if parsed.path == "/api/openai-models":
            self._json(fetch_openai_models())
            return
        if parsed.path == "/api/openai-key-clear":
            try:
                clear_openai_api_key()
            except RuntimeError as exc:
                self._json({"ok": False, "error": str(exc)}, status=500)
                return
            _record_security_event("openai_key_cleared", "Stored OpenAI API key was cleared.")
            self._json({"ok": True, "state": app_state()})
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
            _record_security_event("discord_credentials_saved", "Discord credentials were saved to the OS keyring.")
            self._json({"ok": True, "state": app_state()})
            return
        if parsed.path == "/api/discord-credentials-clear":
            try:
                clear_discord_credentials()
            except RuntimeError as exc:
                self._json({"ok": False, "error": str(exc)}, status=500)
                return
            _record_security_event("discord_credentials_cleared", "Stored Discord credentials were cleared.")
            self._json({"ok": True, "state": app_state()})
            return
        if parsed.path == "/api/discord-session-reset":
            if str(body.get("confirmation") or "") != "SWITCH_DISCORD_ACCOUNT":
                self._json({"ok": False, "error": "Confirmation phrase did not match."}, status=400)
                return
            try:
                reset_discord_session()
            except (OSError, RuntimeError) as exc:
                self._json({"ok": False, "error": str(exc)}, status=500)
                return
            self._json(
                {
                    "ok": True,
                    "state": app_state(),
                    "message": "Discord session reset. Sign in with the new account.",
                }
            )
            return
        if parsed.path == "/api/local-state-clear":
            if str(body.get("confirmation") or "") != "CLEAR_LOCAL_STATE":
                self._json({"ok": False, "error": "Confirmation phrase did not match."}, status=400)
                return
            try:
                clear_local_state()
            except (OSError, RuntimeError) as exc:
                self._json({"ok": False, "error": str(exc)}, status=500)
                return
            self._json({"ok": True, "state": app_state()})
            return
        if parsed.path == "/api/discord-login":
            try:
                start_discord_login()
            except RuntimeError as exc:
                self._json({"ok": False, "error": str(exc)}, status=400)
                return
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
        if parsed.path == "/api/runtime-start-signin":
            RUNTIME.start_with_discord_handoff()
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
        if parsed.path == "/api/approvals-clear":
            count = clear_approvals()
            self._json({"ok": True, "cleared": count, "state": app_state()})
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
                log_regeneration_failure(body, str(exc))
                self._json({"ok": False, "error": str(exc)}, status=400)
                return
            except Exception as exc:
                message = f"Could not regenerate approval draft: {_redact_secret_text(str(exc))}"
                log_regeneration_failure(body, message)
                self._json({"ok": False, "error": message}, status=500)
                return
            self._json({"ok": True, "state": app_state()})
            return
        if parsed.path == "/api/approval-create":
            try:
                create_manual_approval(body)
            except RuntimeError as exc:
                self._json({"ok": False, "error": str(exc)}, status=400)
                return
            except Exception as exc:
                self._json(
                    {
                        "ok": False,
                        "error": f"Could not create approval draft: {_redact_secret_text(str(exc))}",
                    },
                    status=500,
                )
                return
            self._json({"ok": True, "state": app_state()})
            return
        if parsed.path == "/api/update-check":
            self._json(check_update(apply_update=False))
            return
        if parsed.path == "/api/update":
            self._json(check_update(apply_update=True))
            return
        if parsed.path == "/api/diagnostics/collect":
            try:
                self._json(collect_diagnostics(open_folder=True))
            except (OSError, RuntimeError) as exc:
                self._json({"ok": False, "error": f"Could not collect logs: {_redact_secret_text(str(exc))}"}, status=500)
            return
        if parsed.path == "/api/diagnostics/open-folder":
            opened = open_diagnostics_folder()
            self._json({"ok": opened, "message": "Opened the local diagnostics folder." if opened else "Could not open the diagnostics folder."})
            return
        if parsed.path == "/api/character":
            config = load_config()
            card_path = str(body.get("path") or "")
            payload = body.get("card")
            if not card_path or not isinstance(payload, dict):
                self._json({"ok": False, "error": "Missing character card payload."}, status=400)
                return
            target = _safe_character_path(card_path, card_dir=config.character_dir)
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
        if length < 0 or length > 2_000_000:
            raise ValueError("JSON request body is too large.")
        try:
            payload = json.loads(self.rfile.read(length).decode("utf-8"))
        except (UnicodeDecodeError, json.JSONDecodeError) as exc:
            raise ValueError("Request body must be valid UTF-8 JSON.") from exc
        if not isinstance(payload, dict):
            raise ValueError("Request body must be a JSON object.")
        return payload

    def _json(self, payload: dict, *, status: int = 200) -> None:
        data = json.dumps(payload).encode("utf-8")
        self.send_response(status)
        self.send_header("Content-Type", "application/json; charset=utf-8")
        self.send_header("Content-Length", str(len(data)))
        self._security_headers(cache_control="no-store")
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
        cache_control = (
            "public, max-age=86400"
            if path.suffix.lower() in {".png", ".jpg", ".jpeg", ".svg", ".ico", ".wav", ".webp"}
            else "no-cache"
        )
        self._security_headers(cache_control=cache_control)
        self.end_headers()
        self.wfile.write(data)

    def _security_headers(self, *, cache_control: str) -> None:
        self.send_header("Cache-Control", cache_control)
        self.send_header("X-Content-Type-Options", "nosniff")
        self.send_header("X-Frame-Options", "DENY")
        self.send_header("Referrer-Policy", "no-referrer")
        self.send_header(
            "Content-Security-Policy",
            "default-src 'self'; img-src 'self' data:; style-src 'self' 'unsafe-inline'; "
            "script-src 'self'; connect-src 'self'; font-src 'self'; object-src 'none'; "
            "base-uri 'none'; frame-ancestors 'none'; form-action 'self'",
        )

    def _static_path(self, raw_path: str) -> Path | None:
        relative = unquote(raw_path.lstrip("/"))
        target = (WEB_ROOT / relative).resolve()
        base = WEB_ROOT.resolve()
        if target != base and base not in target.parents:
            return None
        return target

    def _authorized_api(self, *, require_json: bool) -> bool:
        if not self._request_allowed():
            return False
        if self.headers.get("X-Kabuki-Token") != SESSION_TOKEN:
            return False
        if require_json and "application/json" not in self.headers.get("Content-Type", ""):
            return False
        origin = self.headers.get("Origin") or self.headers.get("Referer")
        if origin and not self._same_origin(origin):
            return False
        return True

    def _request_allowed(self) -> bool:
        return self._host_allowed() and _is_loopback_host(str(self.client_address[0]))

    def _host_allowed(self) -> bool:
        raw_host = (self.headers.get("Host") or "").strip().lower()
        if raw_host.startswith("["):
            host = raw_host[1:].split("]", 1)[0]
        else:
            host = raw_host.split(":", 1)[0]
        return _is_loopback_host(host)

    def _same_origin(self, value: str) -> bool:
        parsed = urlparse(value)
        host = (parsed.hostname or "").lower()
        port = parsed.port
        server_port = int(getattr(self.server, "server_port", 0) or 0)
        return _is_loopback_host(host) and (port is None or port == server_port)


RUNTIME = RuntimeController(DISCORD_SESSION_LOCK)


def app_state() -> dict:
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
            "headless": config.headless,
            "llm_enabled": config.llm_enabled,
            "draft_in_dry_run": config.draft_in_dry_run,
            "conversation_reply_enabled": config.conversation_reply_enabled,
            "runtime_mode": config.runtime_mode,
            "dry_run": config.dry_run,
            "proactive_approval_required": config.proactive_approval_required,
            "openai_model": config.openai_model,
            "api_key_set": bool(config.openai_api_key),
            "max_daily_usd": config.max_daily_usd,
            "max_session_usd": config.max_session_usd,
            "max_llm_calls_per_run": config.max_llm_calls_per_run,
            "writing_mistake_rate": config.writing_mistake_rate,
            "writing_quirk": config.writing_quirk,
            "writing_misspellings": config.writing_misspellings,
            "reaction_max_per_channel": config.reaction_max_per_channel,
            "reaction_threshold": config.reaction_threshold,
            "reaction_sample_percent": config.reaction_sample_percent,
            "reaction_force_laugh_percent": config.reaction_force_laugh_percent,
            "reaction_cooldown_seconds": config.reaction_cooldown_seconds,
            "reaction_emoji_override": config.reaction_emoji_override,
            "typing_indicator_enabled": config.typing_indicator_enabled,
            "typing_min_seconds": config.typing_min_seconds,
            "typing_max_seconds": config.typing_max_seconds,
            "typing_chars_per_second": config.typing_chars_per_second,
            "scanner_max_channels_per_cycle": config.scanner_max_channels_per_cycle,
            "scanner_cycle_sleep_seconds": config.scanner_cycle_sleep_seconds,
            "scanner_channel_settle_seconds": config.scanner_channel_settle_seconds,
            "scanner_min_channel_delay_seconds": config.scanner_min_channel_delay_seconds,
            "scanner_max_channel_delay_seconds": config.scanner_max_channel_delay_seconds,
            "scanner_history_backfill_limit": config.scanner_history_backfill_limit,
            "scanner_history_scroll_rounds": config.scanner_history_scroll_rounds,
            "safety_review_exclusive": config.safety_review_exclusive,
            "safety_review_history_limit": config.safety_review_history_limit,
            "safety_review_scroll_rounds": config.safety_review_scroll_rounds,
            "safety_review_history_retries": config.safety_review_history_retries,
            "reply_cooldown_seconds": config.reply_cooldown_seconds,
            "reply_window_seconds": config.reply_window_seconds,
            "reply_max_per_window": config.reply_max_per_window,
            "reply_require_intervening_user": config.reply_require_intervening_user,
        },
        "discord": discord_credential_status(),
        "runtime": RUNTIME.state(),
        "updates": update_state(),
        "model_catalog": {
            "live": model_catalog["live"],
            "source": model_catalog["source"],
            "message": model_catalog["message"],
            "fetched_at": model_catalog.get("fetched_at", ""),
            "total_models": model_catalog.get("total_models", 0),
        },
        "model_options": model_catalog["models"],
        "env": {
            "OPENAI_MODEL": env.get("OPENAI_MODEL", ""),
            "NHI_ZUES_LLM_ENABLED": env.get("NHI_ZUES_LLM_ENABLED", "false"),
            "NHI_ZUES_RUNTIME_MODE": env.get("NHI_ZUES_RUNTIME_MODE", config.runtime_mode),
            "NHI_ZUES_DRAFT_IN_DRY_RUN": env.get("NHI_ZUES_DRAFT_IN_DRY_RUN", "false"),
            "NHI_ZUES_CONVERSATION_REPLY_ENABLED": env.get(
                "NHI_ZUES_CONVERSATION_REPLY_ENABLED", "false"
            ),
            "NHI_ZUES_HEADLESS": env.get("NHI_ZUES_HEADLESS", "false"),
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
            "NHI_ZUES_SCANNER_MAX_CHANNELS_PER_CYCLE": env.get("NHI_ZUES_SCANNER_MAX_CHANNELS_PER_CYCLE", "1"),
            "NHI_ZUES_SCANNER_CYCLE_SLEEP_SECONDS": env.get("NHI_ZUES_SCANNER_CYCLE_SLEEP_SECONDS", "45"),
            "NHI_ZUES_SCANNER_MIN_CHANNEL_DELAY_SECONDS": env.get("NHI_ZUES_SCANNER_MIN_CHANNEL_DELAY_SECONDS", "12"),
            "NHI_ZUES_SCANNER_MAX_CHANNEL_DELAY_SECONDS": env.get("NHI_ZUES_SCANNER_MAX_CHANNEL_DELAY_SECONDS", "35"),
            "NHI_ZUES_SCANNER_HISTORY_BACKFILL_LIMIT": env.get("NHI_ZUES_SCANNER_HISTORY_BACKFILL_LIMIT", "80"),
            "NHI_ZUES_SCANNER_HISTORY_SCROLL_ROUNDS": env.get("NHI_ZUES_SCANNER_HISTORY_SCROLL_ROUNDS", "8"),
            "NHI_ZUES_REPLY_CANDIDATE_TTL_SECONDS": env.get("NHI_ZUES_REPLY_CANDIDATE_TTL_SECONDS", "600"),
            "NHI_ZUES_SAFETY_REVIEW_EXCLUSIVE": env.get("NHI_ZUES_SAFETY_REVIEW_EXCLUSIVE", "true"),
            "NHI_ZUES_SAFETY_REVIEW_HISTORY_LIMIT": env.get("NHI_ZUES_SAFETY_REVIEW_HISTORY_LIMIT", "420"),
            "NHI_ZUES_SAFETY_REVIEW_SCROLL_ROUNDS": env.get("NHI_ZUES_SAFETY_REVIEW_SCROLL_ROUNDS", "45"),
            "NHI_ZUES_SAFETY_REVIEW_HISTORY_RETRIES": env.get("NHI_ZUES_SAFETY_REVIEW_HISTORY_RETRIES", "1"),
            "NHI_ZUES_REPLY_COOLDOWN_SECONDS": env.get("NHI_ZUES_REPLY_COOLDOWN_SECONDS", "900"),
            "NHI_ZUES_REPLY_WINDOW_SECONDS": env.get("NHI_ZUES_REPLY_WINDOW_SECONDS", "3600"),
            "NHI_ZUES_REPLY_MAX_PER_WINDOW": env.get("NHI_ZUES_REPLY_MAX_PER_WINDOW", "3"),
            "NHI_ZUES_REPLY_REQUIRE_INTERVENING_USER": env.get("NHI_ZUES_REPLY_REQUIRE_INTERVENING_USER", "true"),
            "NHI_ZUES_REACTION_MAX_PER_CHANNEL": env.get("NHI_ZUES_REACTION_MAX_PER_CHANNEL", "1"),
            "NHI_ZUES_REACTION_THRESHOLD": env.get("NHI_ZUES_REACTION_THRESHOLD", "normal"),
            "NHI_ZUES_REACTION_SAMPLE_PERCENT": env.get("NHI_ZUES_REACTION_SAMPLE_PERCENT", "0"),
            "NHI_ZUES_REACTION_FORCE_LAUGH_PERCENT": env.get("NHI_ZUES_REACTION_FORCE_LAUGH_PERCENT", "0"),
            "NHI_ZUES_REACTION_COOLDOWN_SECONDS": env.get("NHI_ZUES_REACTION_COOLDOWN_SECONDS", "900"),
            "NHI_ZUES_REACTION_EMOJI_OVERRIDE": env.get("NHI_ZUES_REACTION_EMOJI_OVERRIDE", ""),
        },
        "servers": _read_config_json(config.servers_file, default={"servers": []}),
        "characters": character_cards(config.character_dir),
        "active_character": read_character(config.character_dir, config.character_card),
        "character_memory": character_memory_state(config.state_dir, config.character_card),
        "user_instructions": user_instruction_state(config.state_dir),
        "usage": usage_state(),
        "approvals": approval_items_state(config),
        "recent_posters": recent_posters_state(config.state_dir / "memory.json"),
        "observed": observed_conversation_state(config.state_dir / "memory.json"),
        "history": conversation_history_state(
            config.state_dir / "memory.json",
            config.state_dir / "events.json",
        ),
        "events": events_state(config.state_dir / "events.json"),
        "memory": memory_state(config.state_dir / "memory.json"),
        "unresponded": unresponded_replies_state(config),
        "safety_reviews": SafetyReviewQueue(config.state_dir / "safety_review.json").state(),
        "reply_ledger": reply_ledger_state(config.state_dir / "sent_replies.json"),
    }


def monitor_state() -> dict:
    config = load_config()
    servers_payload = _read_config_json(config.servers_file, default={"servers": []})
    runtime = RUNTIME.state()
    servers = []
    for server in servers_payload.get("servers", []):
        servers.append(
            {
                "server_id": str(server.get("server_id") or ""),
                "label": str(server.get("label") or ""),
                "channels": [
                    {
                        "channel_id": str(channel.get("channel_id") or ""),
                        "label": str(channel.get("label") or ""),
                    }
                    for channel in server.get("channels", [])
                ],
            }
        )
    return {
        "app": {
            "scanner_max_channels_per_cycle": config.scanner_max_channels_per_cycle,
            "scanner_cycle_sleep_seconds": config.scanner_cycle_sleep_seconds,
            "scanner_channel_settle_seconds": config.scanner_channel_settle_seconds,
            "scanner_min_channel_delay_seconds": config.scanner_min_channel_delay_seconds,
            "scanner_max_channel_delay_seconds": config.scanner_max_channel_delay_seconds,
        },
        "runtime": runtime,
        "engagement": engagement_state(
            config.state_dir / "events.json",
            servers_payload,
            runtime,
        ),
        "events": events_state(config.state_dir / "events.json"),
        "servers": {"servers": servers},
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


def clear_local_state() -> None:
    config = load_config()
    target = config.state_dir.expanduser().resolve()
    drive_root = Path(target.anchor).resolve()
    if target in {drive_root, Path.home().resolve()} or len(target.parts) < 3:
        raise RuntimeError("Refusing to clear an unsafe state directory.")
    RUNTIME.pause(wait=True, timeout=15.0)
    if target.exists():
        for child in target.iterdir():
            if child.is_dir():
                shutil.rmtree(child)
            else:
                child.unlink(missing_ok=True)
    target.mkdir(parents=True, exist_ok=True)


def reset_discord_session() -> None:
    """Remove the app-owned Discord browser session before changing accounts."""
    config = load_config()
    target = config.profile_dir.expanduser().resolve()
    configured_root = app_data_root().resolve()
    if configured_root != target and configured_root not in target.parents:
        raise RuntimeError(
            "Refusing to reset a Discord profile outside the Kabuki-Cord app-data directory."
        )
    drive_root = Path(target.anchor).resolve()
    if target in {drive_root, Path.home().resolve(), configured_root} or len(target.parts) < 4:
        raise RuntimeError("Refusing to reset an unsafe Discord profile directory.")

    RUNTIME.pause(wait=True, timeout=15.0)
    from .browser import _close_profile_browsers

    _close_profile_browsers(target)
    if target.exists():
        shutil.rmtree(target)
    target.mkdir(parents=True, exist_ok=True)
    clear_discord_credentials()

    payload = _read_config_json(config.servers_file, default={"servers": []})
    for server in payload.get("servers", []):
        for channel in server.get("channels", []):
            for key in ("scan_enabled", "engage_enabled", "react_enabled", "auto_respond_enabled"):
                channel[key] = False
    _write_json(config.servers_file, payload)
    _record_security_event(
        "discord_session_reset",
        "Discord browser session and stored credentials were cleared for an account switch. "
        "All existing channel automation was disabled.",
    )


def _record_security_event(event_type: str, summary: str) -> None:
    config = load_config()
    EventLog(config.state_dir / "events.json").add(
        event_type=event_type,
        server_id="",
        channel_id="",
        summary=summary,
    )


def _log_settings_security_changes(before: AppConfig, after: AppConfig, values: dict) -> None:
    if str(values.get("OPENAI_API_KEY") or "").strip():
        _record_security_event("openai_key_saved", "OpenAI API key was saved to the OS keyring.")
    if before.runtime_mode != after.runtime_mode:
        _record_security_event(
            "runtime_mode_changed",
            f"Response mode changed from {before.runtime_mode} to {after.runtime_mode}.",
        )
    if before.llm_enabled != after.llm_enabled:
        _record_security_event(
            "llm_drafting_changed",
            f"AI drafting {'enabled' if after.llm_enabled else 'disabled'}.",
        )


def _log_channel_autonomy_changes(config: AppConfig, before: dict, after: dict) -> None:
    previous = _autonomous_channel_keys(before)
    current = _autonomous_channel_keys(after)
    enabled = current - previous
    disabled = previous - current
    if not enabled and not disabled:
        return
    EventLog(config.state_dir / "events.json").add(
        event_type="channel_autonomy_changed",
        server_id="",
        channel_id="",
        summary=f"Autonomous channel permission changed: {len(enabled)} enabled, {len(disabled)} disabled.",
    )


def _autonomous_channel_keys(payload: dict) -> set[tuple[str, str]]:
    return {
        (str(server.get("server_id") or ""), str(channel.get("channel_id") or ""))
        for server in payload.get("servers", [])
        for channel in server.get("channels", [])
        if bool(channel.get("auto_respond_enabled", False))
    }


def sync_discord_servers() -> dict:
    config = load_config()
    _acquire_discord_session_or_raise(pause_runtime=True)
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
    payload = _read_config_json(config.servers_file, default={"servers": []})
    next_payload, stats = merge_discovered_servers(
        payload,
        discovered,
        icon_path_for_server=lambda server_id, icon_url: _cache_server_icon(
            config.state_dir,
            server_id,
            icon_url,
        ),
    )
    _write_json(config.servers_file, next_payload)
    if stats["removed"]:
        EventLog(config.state_dir / "events.json").add(
            event_type="discord_servers_removed",
            server_id="",
            channel_id="",
            summary=(
                f"Discord sync removed {stats['removed']} server(s) no longer visible "
                f"to this account: {', '.join(stats['removed_server_ids'])}."
            ),
        )
    return {
        "ok": True,
        **stats,
        "state": app_state(),
    }


def repair_discord_server(body: dict) -> dict:
    server_id = str(body.get("server_id") or "").strip()
    if not server_id:
        raise RuntimeError("Select a server before repairing channels.")
    config = load_config()
    _acquire_discord_session_or_raise(pause_runtime=True)
    try:
        try:
            discovered_channels = asyncio.run(_discover_discord_server_channels(config, server_id))
        except RuntimeError:
            raise
        except Exception as exc:
            raise RuntimeError(
                "Discord channel repair failed. Close any open Kabuki Discord sign-in/channel windows and try again."
            ) from exc
    finally:
        DISCORD_SESSION_LOCK.release()

    payload = _read_config_json(config.servers_file, default={"servers": []})
    server_list = payload.get("servers")
    if not isinstance(server_list, list):
        server_list = []
    server = next(
        (
            item
            for item in server_list
            if isinstance(item, dict) and str(item.get("server_id") or "") == server_id
        ),
        None,
    )
    if server is None:
        server = {
            "server_id": server_id,
            "label": f"Server {server_id}",
            "character_card": None,
            "safety_review_enabled": False,
            "channels": [],
        }
        server_list.append(server)
    stats = _merge_channels(server, discovered_channels)
    _write_json(config.servers_file, {**payload, "servers": server_list})
    EventLog(config.state_dir / "events.json").add(
        event_type="discord_repair",
        server_id=server_id,
        channel_id="",
        summary=(
            f"Server channel repair found {stats['discovered']} channel/thread item(s), "
            f"added {stats['added']}, updated {stats['updated']}."
        ),
        draft="",
    )
    return {"ok": True, **stats, "state": app_state()}


def backfill_channel_history(body: dict) -> dict:
    server_id = str(body.get("server_id") or "").strip()
    channel_id = str(body.get("channel_id") or "").strip()
    try:
        limit = max(80, min(int(body.get("limit") or 320), 500))
    except (TypeError, ValueError):
        limit = 320
    if not server_id or not channel_id:
        raise RuntimeError("Select a channel before backfilling history.")

    config = load_config()
    _acquire_discord_session_or_raise(pause_runtime=True)
    try:
        try:
            messages = asyncio.run(_backfill_channel_history(config, server_id, channel_id, limit=limit))
        except RuntimeError:
            raise
        except Exception as exc:
            raise RuntimeError(
                "Channel history backfill failed. Close any open Kabuki Discord sign-in/channel windows and try again."
            ) from exc
    finally:
        DISCORD_SESSION_LOCK.release()

    memory = ConversationMemory(config.state_dir / "memory.json", max_messages_per_channel=max(limit, 500))
    memory.load()
    fresh = memory.ingest(channel_id, messages)
    memory.save()
    EventLog(config.state_dir / "events.json").add(
        event_type="channel_backfilled",
        server_id=server_id,
        channel_id=channel_id,
        summary=f"Backfilled {len(messages)} visible/history message(s), {len(fresh)} new to Kabuki memory.",
        draft="",
    )
    return {
        "ok": True,
        "messages": len(messages),
        "new": len(fresh),
        "state": app_state(),
    }


def refresh_channel_latest(body: dict) -> dict:
    server_id = str(body.get("server_id") or "").strip()
    channel_id = str(body.get("channel_id") or "").strip()
    if not server_id or not channel_id:
        raise RuntimeError("Select a channel before refreshing latest messages.")

    config = load_config()
    _acquire_discord_session_or_raise(pause_runtime=True)
    try:
        try:
            messages = asyncio.run(_read_latest_channel_messages(config, server_id, channel_id))
        except RuntimeError:
            raise
        except Exception as exc:
            raise RuntimeError(
                "Latest message refresh failed. Close any open Kabuki Discord sign-in/channel windows and try again."
            ) from exc
    finally:
        DISCORD_SESSION_LOCK.release()

    memory = ConversationMemory(config.state_dir / "memory.json")
    memory.load()
    fresh = memory.ingest(channel_id, messages)
    memory.save()
    EventLog(config.state_dir / "events.json").add(
        event_type="channel_refreshed",
        server_id=server_id,
        channel_id=channel_id,
        summary=f"Refreshed latest visible messages: {len(messages)} found, {len(fresh)} new.",
        draft="",
    )
    return {
        "ok": True,
        "messages": len(messages),
        "new": len(fresh),
        "state": app_state(),
    }


def suggest_reaction(body: dict) -> dict:
    server_id = str(body.get("server_id") or "").strip()
    channel_id = str(body.get("channel_id") or "").strip()
    message_id = str(body.get("message_id") or "").strip()
    raw_author = str(body.get("author") or "").strip()
    author = clean_discord_display_name(raw_author) if raw_author else ""
    text = sanitize_outgoing_draft(str(body.get("text") or "").strip())
    if not server_id or not channel_id or not message_id:
        raise RuntimeError("Select a remembered message before asking for a reaction suggestion.")

    config = load_config()
    if not text:
        memory = ConversationMemory(config.state_dir / "memory.json")
        memory.load()
        for message in memory.context(channel_id, limit=500):
            if message.message_id == message_id:
                author = author or clean_discord_display_name(message.author)
                text = sanitize_outgoing_draft(message.text)
                break
    if not text:
        raise RuntimeError("Kabuki could not find the selected message text in local memory.")

    emoji, reason = suggest_emoji_reaction(text)
    snippet = " ".join(text.split())
    if len(snippet) > 140:
        snippet = snippet[:137].rstrip() + "..."
    EventLog(config.state_dir / "events.json").add(
        event_type="reaction_suggested",
        server_id=server_id,
        channel_id=channel_id,
        summary=f"Suggested {emoji} reaction for {author or 'selected message'}: {reason}",
        draft=snippet,
    )
    return {
        "ok": True,
        "emoji": emoji,
        "reason": reason,
        "message_id": message_id,
        "state": app_state(),
    }


def _acquire_discord_session_or_raise(*, pause_runtime: bool = False) -> None:
    if pause_runtime:
        RUNTIME.pause(wait=True, timeout=10.0)

    deadline = time.monotonic() + DISCORD_LOCK_WAIT_SECONDS
    while time.monotonic() < deadline:
        if DISCORD_SESSION_LOCK.acquire(blocking=False):
            return
        time.sleep(0.25)

    raise RuntimeError(
        "Discord browser profile is busy. Scanner was paused, but another Kabuki Discord "
        "window is still using the profile. Close any Kabuki-opened Discord sign-in/channel "
        "windows, then try again."
    )


def _merge_channels(server: dict, discovered_channels: list[dict]) -> dict[str, int]:
    return _merge_channels_impl(server, discovered_channels)


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
            allow_human_challenge=False,
        )
        if not logged_in:
            raise RuntimeError(discord_login_blocker_message(await session.account_blocker_state()))
        servers = await session.discover_servers()
        for server in servers:
            server["channels"] = await session.discover_channels(server["server_id"])
    if not servers:
        raise RuntimeError("No Discord servers were found in the signed-in browser profile.")
    return servers


async def _discover_discord_server_channels(config: AppConfig, server_id: str) -> list[dict]:
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
            allow_human_challenge=False,
        )
        if not logged_in:
            raise RuntimeError(discord_login_blocker_message(await session.account_blocker_state()))
        return await session.discover_channels(server_id)


async def _backfill_channel_history(
    config: AppConfig,
    server_id: str,
    channel_id: str,
    *,
    limit: int,
) -> list[MessageRecord]:
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
            allow_human_challenge=False,
        )
        if not logged_in:
            raise RuntimeError(discord_login_blocker_message(await session.account_blocker_state()))
        current_url = await session.navigate_channel(server_id, channel_id)
        if channel_id not in current_url:
            raise RuntimeError("Discord redirected away from the selected channel.")
        return await session.read_channel_history(server_id, channel_id, limit=limit)


async def _read_latest_channel_messages(
    config: AppConfig,
    server_id: str,
    channel_id: str,
) -> list[MessageRecord]:
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
            allow_human_challenge=False,
        )
        if not logged_in:
            raise RuntimeError(discord_login_blocker_message(await session.account_blocker_state()))
        current_url = await session.navigate_channel(server_id, channel_id)
        if channel_id not in current_url:
            raise RuntimeError("Discord redirected away from the selected channel.")
        return await session.read_visible_messages(server_id, channel_id)


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
    user_rows = [{"user_key": key, **value} for key, value in users.items()]
    user_rows.sort(
        key=lambda item: (
            str(item.get("last_seen_at") or ""),
            int(item.get("message_count") or 0),
            str(item.get("display_name") or "").lower(),
        ),
        reverse=True,
    )
    return {
        "channel_count": len(payload.get("channels", {})),
        "seen_ids": len(payload.get("seen_ids", [])),
        "user_count": len(users),
        "users": user_rows,
    }


def reply_ledger_state(path: Path) -> dict:
    payload = _read_json(path, default={"items": []})
    items = payload.get("items", [])
    return {
        "count": len(items),
        "recent": items[-20:],
    }


def observed_conversation_state(path: Path) -> dict:
    payload = _read_json(path, default={"channels": {}, "users": {}})
    result: dict[str, dict] = {}
    for channel_id, rows in payload.get("channels", {}).items():
        rows = _sorted_message_rows(rows)
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
                    "display_name": clean_discord_display_name(str(row.get("author") or "unknown")),
                    "message_id": str(row.get("message_id") or ""),
                    "message_count": len(user_messages),
                    "summary": _summarize_messages([sanitize_outgoing_draft(text) for text in texts]),
                    "recent_text": sanitize_outgoing_draft(texts[-1]) if texts else "",
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
            "messages": [_message_preview(row) for row in _sorted_message_rows(rows)[-80:]],
            "events": events_by_channel.get(str(channel_id), [])[-60:],
        }
        for channel_id, rows in memory_payload.get("channels", {}).items()
    }


def events_state(event_path: Path) -> dict:
    payload = _read_json(event_path, default={"items": []})
    items = payload.get("items", [])
    if not isinstance(items, list):
        items = []
    tail = items[-180:]
    reaction_tail = [
        item
        for item in items
        if str(item.get("event_type") or "").startswith("reaction_")
    ][-80:]
    combined = []
    seen = set()
    for item in [*tail, *reaction_tail]:
        key = (
            item.get("created_at"),
            item.get("event_type"),
            item.get("server_id"),
            item.get("channel_id"),
            item.get("summary"),
            item.get("draft"),
        )
        if key in seen:
            continue
        seen.add(key)
        combined.append(item)
    combined.sort(key=lambda item: str(item.get("created_at") or ""))
    return {
        "items": list(reversed(combined)),
        "count": len(items),
    }


_CHANNEL_FRESHNESS_EVENT_TYPES = frozenset(
    {"channel_checked", "channel_unavailable", "safety_review_scan"}
)
_RUNTIME_START_EVENT_TYPES = frozenset(
    {"runtime_started", "runtime_signin_handoff_started"}
)


def engagement_state(
    event_path: Path,
    servers_payload: dict,
    runtime_state: dict | None = None,
) -> dict:
    payload = _read_json(event_path, default={"items": []})
    items = payload.get("items", [])
    if not isinstance(items, list):
        items = []

    scope_started_at = _engagement_scope_started_at(items, runtime_state or {})
    scope_timestamp = _event_timestamp(scope_started_at)
    scoped_items = [
        item
        for item in items
        if isinstance(item, dict)
        and (
            scope_timestamp is None
            or (
                (created_timestamp := _event_timestamp(item.get("created_at"))) is not None
                and created_timestamp >= scope_timestamp
            )
        )
    ]

    totals: dict[str, int] = {}
    reason_counts: dict[str, int] = {}
    for item in scoped_items:
        for key, value in normalize_event_metrics(item.get("metrics")).items():
            totals[key] = totals.get(key, 0) + value
        reason_code = normalize_reason_code(item.get("reason_code"))
        if reason_code:
            reason_counts[reason_code] = reason_counts.get(reason_code, 0) + 1

    latest_by_channel: dict[str, dict] = {}
    for item in items:
        if not isinstance(item, dict):
            continue
        if str(item.get("event_type") or "") not in _CHANNEL_FRESHNESS_EVENT_TYPES:
            continue
        channel_id = str(item.get("channel_id") or "").strip()
        created_at = str(item.get("created_at") or "")
        if not channel_id or _event_timestamp(created_at) is None:
            continue
        current = latest_by_channel.get(channel_id)
        if current is None or created_at > str(current.get("created_at") or ""):
            latest_by_channel[channel_id] = item

    channels = []
    for server_index, server in enumerate(servers_payload.get("servers", [])):
        if not isinstance(server, dict):
            continue
        server_label = str(server.get("label") or f"Server {server_index + 1}")
        for channel_index, channel in enumerate(server.get("channels", [])):
            if not isinstance(channel, dict) or channel.get("scan_enabled", True) is False:
                continue
            channel_id = str(channel.get("channel_id") or "").strip()
            latest = latest_by_channel.get(channel_id, {})
            event_type = str(latest.get("event_type") or "")
            metrics = normalize_event_metrics(latest.get("metrics"))
            channels.append(
                {
                    "server_label": server_label,
                    "channel_label": str(
                        channel.get("label") or f"Channel {channel_index + 1}"
                    ),
                    "last_checked_at": str(latest.get("created_at") or ""),
                    "last_reason_code": normalize_reason_code(latest.get("reason_code")),
                    "last_fresh_observed": metrics.get("fresh_observed"),
                    "status": (
                        "never"
                        if not latest
                        else "unavailable"
                        if event_type == "channel_unavailable"
                        else "checked"
                    ),
                }
            )
    channels.sort(
        key=lambda item: (
            0 if not item["last_checked_at"] else 1,
            item["last_checked_at"],
            str(item["server_label"]).lower(),
            str(item["channel_label"]).lower(),
        )
    )

    scan = (runtime_state or {}).get("scan", {})
    loop = scan.get("loop", {}) if isinstance(scan, dict) else {}
    expected_revisit_seconds = max(
        0.0,
        _finite_float(loop.get("estimated_loop_seconds")) if isinstance(loop, dict) else 0.0,
    )
    return {
        "scope": "latest_run" if scope_started_at else "retained_history",
        "scope_started_at": scope_started_at,
        "totals": totals,
        "reasons": [
            {"code": code, "count": count}
            for code, count in sorted(
                reason_counts.items(),
                key=lambda item: (-item[1], item[0]),
            )
        ],
        "channels": channels,
        "expected_revisit_seconds": expected_revisit_seconds,
    }


def _engagement_scope_started_at(items: list, runtime_state: dict) -> str:
    runtime_started_at = runtime_state.get("last_started_at")
    if isinstance(runtime_started_at, (int, float)) and not isinstance(runtime_started_at, bool):
        if runtime_started_at > 0:
            return datetime.fromtimestamp(runtime_started_at, tz=timezone.utc).isoformat()
    for item in reversed(items):
        if not isinstance(item, dict):
            continue
        if str(item.get("event_type") or "") not in _RUNTIME_START_EVENT_TYPES:
            continue
        created_at = str(item.get("created_at") or "")
        if _event_timestamp(created_at) is not None:
            return created_at
    return ""


def _event_timestamp(value) -> float | None:
    text = str(value or "").strip()
    if not text:
        return None
    try:
        parsed = datetime.fromisoformat(text.replace("Z", "+00:00"))
    except ValueError:
        return None
    if parsed.tzinfo is None:
        parsed = parsed.replace(tzinfo=timezone.utc)
    return parsed.timestamp()


def _finite_float(value) -> float:
    if isinstance(value, bool):
        return 0.0
    try:
        result = float(value or 0.0)
    except (TypeError, ValueError):
        return 0.0
    return result if result == result and result not in {float("inf"), float("-inf")} else 0.0


def recent_posters_state(path: Path) -> dict:
    payload = _read_json(path, default={"channels": {}})
    result: dict[str, list[dict]] = {}
    for channel_id, rows in payload.get("channels", {}).items():
        rows = _sorted_message_rows(rows)
        posters: list[dict] = []
        seen: set[str] = set()
        for row in reversed(rows):
            raw_author = str(row.get("author") or "").strip()
            if not raw_author:
                continue
            author = clean_discord_display_name(raw_author)
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
                    "message_id": str(row.get("message_id") or ""),
                    "reply_prefix": _reply_mention_prefix(author, author_id),
                }
            )
            if len(posters) >= 6:
                break
        result[str(channel_id)] = posters
    return result


def dismiss_unresponded_replies(body: dict) -> int:
    config = load_config()
    path = config.state_dir / "dismissed_unresponded.json"
    payload = _read_json(path, default={"message_ids": []})
    existing = {
        str(message_id)
        for message_id in payload.get("message_ids", [])
        if str(message_id).strip()
    }
    raw_message_ids = body.get("message_ids", [])
    if isinstance(raw_message_ids, str):
        raw_message_ids = [raw_message_ids]
    if not isinstance(raw_message_ids, list):
        raw_message_ids = []
    requested = {
        str(message_id)
        for message_id in raw_message_ids
        if str(message_id).strip()
    }
    single_id = str(body.get("message_id") or "").strip()
    if single_id:
        requested.add(single_id)
    if body.get("all"):
        requested.update(
            str(item.get("message_id") or "")
            for item in unresponded_replies_state(config, include_dismissed=True).get("items", [])
            if str(item.get("message_id") or "").strip()
        )
    if not requested and body.get("all"):
        return 0
    if not requested:
        raise ValueError("No unresponded reply id was provided.")

    next_ids = sorted(existing | requested)
    _write_json(
        path,
        {
            "message_ids": next_ids,
            "updated_at": datetime.now(timezone.utc).isoformat(),
        },
    )
    EventLog(config.state_dir / "events.json").add(
        event_type="unresponded_reply_dismissed",
        server_id=str(body.get("server_id") or ""),
        channel_id=str(body.get("channel_id") or ""),
        summary=f"Dismissed {len(requested)} unresponded reply notification(s).",
    )
    return len(requested)


def dismiss_safety_reviews(body: dict) -> int:
    config = load_config()
    queue = SafetyReviewQueue(config.state_dir / "safety_review.json")
    raw_review_ids = body.get("review_ids", [])
    if isinstance(raw_review_ids, str):
        raw_review_ids = [raw_review_ids]
    if not isinstance(raw_review_ids, list):
        raw_review_ids = []
    requested = {
        str(review_id).strip()
        for review_id in raw_review_ids
        if str(review_id or "").strip()
    }
    single_id = str(body.get("review_id") or "").strip()
    if single_id:
        requested.add(single_id)
    all_open = bool(body.get("all"))
    if not requested and not all_open:
        raise ValueError("No Dojo Sweep item id was provided.")

    dismissed = queue.dismiss(sorted(requested), all_open=all_open)
    EventLog(config.state_dir / "events.json").add(
        event_type="safety_review_dismissed",
        server_id=str(body.get("server_id") or ""),
        channel_id=str(body.get("channel_id") or ""),
        summary=f"Dismissed {dismissed} Dojo Sweep item(s).",
    )
    return dismissed


def unresponded_replies_state(config: AppConfig, *, include_dismissed: bool = False) -> dict:
    memory_payload = _read_json(config.state_dir / "memory.json", default={"channels": {}})
    server_labels, channel_labels = _approval_config_indexes(config.servers_file)
    store = CharacterCardStore(config.character_dir, config.character_card)
    dismissed_ids: set[str] = set()
    if not include_dismissed:
        dismissed_payload = _read_json(config.state_dir / "dismissed_unresponded.json", default={"message_ids": []})
        dismissed_ids = {
            str(message_id)
            for message_id in dismissed_payload.get("message_ids", [])
            if str(message_id).strip()
        }
    items: list[dict] = []
    by_server: dict[str, int] = {}
    by_channel: dict[str, int] = {}

    for channel_id, rows in memory_payload.get("channels", {}).items():
        sorted_rows = _sorted_message_rows(rows)
        if not sorted_rows:
            continue
        server_id = _channel_server_id(str(channel_id), sorted_rows, channel_labels)
        card = store.for_server(server_id, _server_character_card(config, server_id))
        own_names = _character_name_set(card)
        last_own_index = _last_own_message_index(sorted_rows, own_names)
        if last_own_index < 0:
            continue

        own_row = sorted_rows[last_own_index]
        own_at = _parse_iso_time(str(own_row.get("observed_at") or ""))
        for index, row in enumerate(sorted_rows[last_own_index + 1 :], start=last_own_index + 1):
            if _is_own_author(row, own_names):
                continue
            text = str(row.get("text") or "")
            explicit_mention = _text_mentions_character(text, own_names)
            adjacent_reply = index == last_own_index + 1 and _within_hours(
                own_at,
                _parse_iso_time(str(row.get("observed_at") or "")),
                hours=0.75,
            )
            if not explicit_mention and not adjacent_reply:
                continue
            message_id = str(row.get("message_id") or "")
            if message_id and message_id in dismissed_ids:
                continue
            preview = _message_preview(row)
            channel_meta = channel_labels.get(str(channel_id), {})
            reason = "mentioned/tagged the character" if explicit_mention else "posted immediately after the character"
            item = {
                **preview,
                "server_id": server_id,
                "server_label": server_labels.get(server_id) or channel_meta.get("server_label") or server_id,
                "channel_label": channel_meta.get("label") or str(channel_id),
                "channel_type": channel_meta.get("channel_type") or "",
                "reason": reason,
                "since_message_id": str(own_row.get("message_id") or ""),
                "since_text": sanitize_outgoing_draft(str(own_row.get("text") or "")),
            }
            items.append(item)
            by_server[server_id] = by_server.get(server_id, 0) + 1
            by_channel[str(channel_id)] = by_channel.get(str(channel_id), 0) + 1

    items = sorted(items, key=lambda item: _message_row_sort_key(item), reverse=True)[:80]
    return {
        "count": len(items),
        "items": items,
        "by_server": by_server,
        "by_channel": by_channel,
    }


def _channel_server_id(channel_id: str, rows: list[dict], channel_labels: dict[str, dict]) -> str:
    channel_meta = channel_labels.get(channel_id, {})
    if channel_meta.get("server_id"):
        return str(channel_meta["server_id"])
    for row in reversed(rows):
        if row.get("server_id"):
            return str(row["server_id"])
    return ""


def _character_name_set(card) -> set[str]:
    names = {card.name, *card.aliases}
    return {_normalize_character_match(name) for name in names if _normalize_character_match(name)}


def _last_own_message_index(rows: list[dict], own_names: set[str]) -> int:
    for index in range(len(rows) - 1, -1, -1):
        if _is_own_author(rows[index], own_names):
            return index
    return -1


def _is_own_author(row: dict, own_names: set[str]) -> bool:
    author = _normalize_character_match(clean_discord_display_name(str(row.get("author") or "")))
    return bool(author and author in own_names)


def _text_mentions_character(text: str, own_names: set[str]) -> bool:
    normalized = _normalize_character_match(text)
    if not normalized:
        return False
    return any(name and name in normalized for name in own_names)


def _normalize_character_match(value: str) -> str:
    return " ".join(str(value or "").lower().replace("@", " ").split())


def _parse_iso_time(value: str) -> datetime | None:
    if not value:
        return None
    try:
        parsed = datetime.fromisoformat(value.replace("Z", "+00:00"))
    except ValueError:
        return None
    if parsed.tzinfo is None:
        return parsed.replace(tzinfo=timezone.utc)
    return parsed


def _within_hours(left: datetime | None, right: datetime | None, *, hours: float) -> bool:
    if left is None or right is None:
        return False
    return 0 <= (right - left).total_seconds() <= hours * 3600


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
    _update_approval_draft(load_config(), approval_id, draft)


def discard_approval(body: dict) -> None:
    approval_id = str(body.get("approval_id") or "")
    if not approval_id:
        return
    _discard_approval(load_config(), approval_id)


def clear_approvals() -> int:
    return _clear_approval_queue(load_config())


def send_approval(body: dict) -> None:
    approval_id = str(body.get("approval_id") or "")
    draft = str(body.get("draft") or "").strip()
    reply_to_message_id = str(body.get("reply_to_message_id") or "").strip()
    if not approval_id or not draft:
        raise RuntimeError("Missing approval id or draft text.")
    lock = _approval_send_lock(approval_id)
    if not lock.acquire(blocking=False):
        raise RuntimeError("Send is already running for this approval.")
    try:
        _send_approval_locked(
            approval_id=approval_id,
            draft=draft,
            reply_to_message_id=reply_to_message_id,
        )
    finally:
        lock.release()


def _approval_send_lock(approval_id: str) -> threading.Lock:
    with APPROVAL_SEND_LOCKS_LOCK:
        lock = APPROVAL_SEND_LOCKS.get(approval_id)
        if lock is None:
            lock = threading.Lock()
            APPROVAL_SEND_LOCKS[approval_id] = lock
        return lock


def _send_approval_locked(*, approval_id: str, draft: str, reply_to_message_id: str = "") -> None:
    config = load_config()
    if config.runtime_mode == "dry":
        raise RuntimeError("Dry Mode is enabled. Switch response mode before sending approved replies.")
    draft = sanitize_outgoing_draft(draft)
    if not draft:
        raise RuntimeError("Draft became empty after removing unsafe Discord metadata.")
    queue = ApprovalQueue(config.state_dir / "approvals.json")
    try:
        item = queue.update_draft(approval_id, draft)
    except KeyError as exc:
        raise RuntimeError("That approval was already cleared. Refresh the app before sending.") from exc
    output_block = outgoing_block_reason(draft)
    if output_block:
        EventLog(config.state_dir / "events.json").add(
            event_type="output_guard_blocked",
            server_id=item.server_id,
            channel_id=item.channel_id,
            summary=output_block,
            draft=draft,
        )
        raise RuntimeError(output_block)

    source_messages = _approval_source_messages(config, item)
    own_source_message = _own_source_block_message(
        config,
        server_id=item.server_id,
        channel_id=item.channel_id,
        source_messages=source_messages,
    )
    if own_source_message:
        EventLog(config.state_dir / "events.json").add(
            event_type="own_reply_blocked",
            server_id=item.server_id,
            channel_id=item.channel_id,
            summary=own_source_message,
            draft=draft,
        )
        raise RuntimeError(own_source_message)

    ledger = ReplyLedger(config.state_dir / "sent_replies.json")
    duplicate_message = duplicate_reply_message(
        ledger.find_overlap(channel_id=item.channel_id, source_message_ids=item.source_message_ids)
    )
    if duplicate_message:
        EventLog(config.state_dir / "events.json").add(
            event_type="duplicate_reply_blocked",
            server_id=item.server_id,
            channel_id=item.channel_id,
            summary=duplicate_message,
            draft=draft,
        )
        raise RuntimeError(duplicate_message)

    event_log = EventLog(config.state_dir / "events.json")
    event_log.add(
        event_type="approval_send_started",
        server_id=item.server_id,
        channel_id=item.channel_id,
        summary="Approved draft accepted. Waiting for Discord delivery.",
        draft=draft,
    )

    lock_acquired = False
    resume_runtime = bool(RUNTIME.state().get("running"))
    start_runtime_after_send = False
    try:
        _acquire_discord_session_or_raise(pause_runtime=True)
        lock_acquired = True
        current_item = queue.get(approval_id)
        if current_item is None:
            raise RuntimeError("That approval was already sent or cleared. Refresh the app before sending.")
        item = current_item
        duplicate_message = duplicate_reply_message(
            ledger.find_overlap(channel_id=item.channel_id, source_message_ids=item.source_message_ids)
        )
        if duplicate_message:
            event_log.add(
                event_type="duplicate_reply_blocked",
                server_id=item.server_id,
                channel_id=item.channel_id,
                summary=duplicate_message,
                draft=draft,
            )
            raise RuntimeError(duplicate_message)
        source_preview = _last_approval_source_message(config, item)
        delivery = asyncio.run(
            _send_approval_message(
                config,
                item.server_id,
                item.channel_id,
                draft,
                reply_to_message_id=reply_to_message_id,
            )
        )
    except Exception as exc:
        friendly_error = _friendly_discord_send_error(str(exc))
        if not _is_non_delivery_block(friendly_error):
            event_log.add(
                event_type="approval_send_failed",
                server_id=item.server_id,
                channel_id=item.channel_id,
                summary=friendly_error,
                draft=draft,
            )
        raise RuntimeError(friendly_error) from exc
    else:
        visible_messages = delivery.get("visible_messages")
        if isinstance(visible_messages, list):
            memory = ConversationMemory(config.state_dir / "memory.json")
            memory.load()
            fresh = memory.ingest(item.channel_id, visible_messages)
            memory.save()
            event_log.add(
                event_type="channel_refreshed",
                server_id=item.server_id,
                channel_id=item.channel_id,
                summary=(
                    f"Immediate post-send refresh saw {len(visible_messages)} visible "
                    f"message(s), {len(fresh)} new."
                ),
                draft="",
            )
        ledger.record(
            server_id=item.server_id,
            channel_id=item.channel_id,
            mode=item.engagement_type,
            draft=draft,
            source_message_ids=item.source_message_ids,
            message_id=str(delivery.get("message_id") or ""),
        )
        queue.remove(approval_id)
        summary = "Approved draft posted successfully to Discord."
        if delivery.get("reply_fallback_used"):
            summary = (
                "Approved draft posted as a normal channel message because Discord "
                "did not expose the selected message Reply action."
            )
        if delivery.get("assumed_sent"):
            summary = (
                "Approved draft appears posted. Discord cleared the composer and rendered "
                "a new message, but Kabuki could not text-match the rendered copy."
            )
        event_log.add(
            event_type="approval_sent",
            server_id=item.server_id,
            channel_id=item.channel_id,
            reason_code="sent",
            metrics=(
                {"sent": 1}
                if str(item.engagement_type or "").lower() != "manual"
                else {}
            ),
            summary=summary,
            draft=draft,
            message_id=str(delivery.get("message_id") or ""),
            target_message_id=(
                reply_to_message_id
                or str(source_preview.get("message_id") or "")
                or str(item.source_message_ids[-1] if item.source_message_ids else "")
            ),
            target_author=str(source_preview.get("author") or ""),
        )
        start_runtime_after_send = True
    finally:
        if lock_acquired:
            DISCORD_SESSION_LOCK.release()
        if resume_runtime or start_runtime_after_send:
            RUNTIME.start()


def _last_approval_source_message(config: AppConfig, item) -> dict:
    return _last_approval_source_message_impl(config, item)


def _approval_source_messages(config: AppConfig, item) -> list[MessageRecord]:
    return _approval_source_messages_impl(config, item)


def _own_source_block_message(
    config: AppConfig,
    *,
    server_id: str,
    channel_id: str,
    source_messages: list[MessageRecord],
    context: list[MessageRecord] | None = None,
) -> str:
    return _own_source_block_message_impl(
        config,
        server_id=server_id,
        channel_id=channel_id,
        source_messages=source_messages,
        context=context,
    )


def _friendly_discord_send_error(raw_error: str) -> str:
    lowered = raw_error.lower()
    profile_markers = (
        "processsingleton",
        "singletonlock",
        "user data directory is already in use",
        "profile appears to be in use",
        "browser has been closed",
        "target page, context or browser has been closed",
    )
    if any(marker in lowered for marker in profile_markers):
        return (
            "Discord profile is already open in another Kabuki/Chrome window. "
            "Close any Kabuki-opened Discord channel or sign-in windows, then retry. "
            "The draft was not sent and remains queued."
        )
    channel_markers = (
        "no writable message composer",
        "blocking sends here",
        "did not finish loading a writable message composer",
        "redirected away from the target channel",
        "permission to send messages",
        "read-only",
        "selected message to reply to",
        "reply action",
        "duplicate reply blocked",
        "already sent or cleared",
        "human verification",
        "visible discord login",
        "authentication code",
        "discord is on the login screen",
        "discord is not signed in",
    )
    if any(marker in lowered for marker in channel_markers):
        return _redact_secret_text(raw_error)
    return f"Discord send failed: {_redact_secret_text(raw_error)}"


def _is_non_delivery_block(message: str) -> bool:
    lowered = message.lower()
    return "duplicate reply blocked" in lowered or "already sent or cleared" in lowered


def regenerate_approval(body: dict) -> None:
    approval_id = str(body.get("approval_id") or "")
    operator_instruction = str(body.get("instruction") or "").strip()
    target_user_key = str(body.get("target_user_key") or "")
    current_draft = str(body.get("draft") or "").strip()
    original_draft = str(body.get("original_draft") or "").strip()
    if not approval_id:
        raise RuntimeError("Missing approval id.")
    lock = _approval_regeneration_lock(approval_id)
    if not lock.acquire(blocking=False):
        raise RuntimeError("Regeneration is already running for this approval.")
    try:
        _regenerate_approval_locked(
            approval_id=approval_id,
            operator_instruction=operator_instruction,
            target_user_key=target_user_key,
            current_draft=current_draft,
            original_draft=original_draft,
        )
    finally:
        lock.release()


def log_regeneration_failure(body: dict, message: str) -> None:
    try:
        config = load_config()
        approval_id = str(body.get("approval_id") or "")
        item = ApprovalQueue(config.state_dir / "approvals.json").get(approval_id)
        EventLog(config.state_dir / "events.json").add(
            event_type="approval_regeneration_failed",
            server_id=item.server_id if item else "",
            channel_id=item.channel_id if item else "",
            summary=_redact_secret_text(message),
            draft=str(body.get("draft") or (item.draft if item else "")),
        )
    except Exception:
        return


def _approval_regeneration_lock(approval_id: str) -> threading.Lock:
    with APPROVAL_REGENERATION_LOCKS_LOCK:
        lock = APPROVAL_REGENERATION_LOCKS.get(approval_id)
        if lock is None:
            lock = threading.Lock()
            APPROVAL_REGENERATION_LOCKS[approval_id] = lock
        return lock


def _regenerate_approval_locked(
    *,
    approval_id: str,
    operator_instruction: str,
    target_user_key: str,
    current_draft: str,
    original_draft: str,
) -> None:
    config = load_config()
    queue = ApprovalQueue(config.state_dir / "approvals.json")
    item = queue.get(approval_id)
    if item is None:
        raise RuntimeError("Unknown approval.")
    source_ids = set(item.source_message_ids)
    source_messages = [
        message
        for message in _memory_context(config.state_dir / "memory.json", item.channel_id)
        if message.message_id in source_ids
    ]
    own_source_message = _own_source_block_message(
        config,
        server_id=item.server_id,
        channel_id=item.channel_id,
        source_messages=source_messages,
    )
    if own_source_message:
        raise RuntimeError(own_source_message)
    effective_target_user_key = target_user_key or _source_user_key(source_messages)
    decision = asyncio.run(
        _generate_manual_decision(
            config,
            server_id=item.server_id,
            channel_id=item.channel_id,
            target_user_key=effective_target_user_key,
            source_messages=source_messages,
            current_draft=current_draft or item.draft,
            original_draft=original_draft or item.draft,
            operator_instruction=operator_instruction,
        )
    )
    if not decision.draft:
        raise RuntimeError(decision.reason)
    draft = _draft_with_reply_mention(decision.draft, source_messages)
    output_block = outgoing_block_reason(draft)
    if output_block:
        EventLog(config.state_dir / "events.json").add(
            event_type="output_guard_blocked",
            server_id=item.server_id,
            channel_id=item.channel_id,
            summary=output_block,
            draft=draft,
            user_key=effective_target_user_key,
        )
        raise RuntimeError(output_block)
    queue.update_draft(approval_id, draft)
    EventLog(config.state_dir / "events.json").add(
        event_type="approval_regenerated",
        server_id=item.server_id,
        channel_id=item.channel_id,
        summary=operator_instruction or decision.reason,
        draft=draft,
        user_key=effective_target_user_key,
    )


def create_manual_approval(body: dict) -> None:
    server_id = str(body.get("server_id") or "")
    channel_id = str(body.get("channel_id") or "")
    target_user_key = str(body.get("target_user_key") or "")
    target_message_id = str(body.get("target_message_id") or "")
    operator_instruction = str(body.get("instruction") or "").strip()
    force_manual = bool(body.get("force_manual") or body.get("force"))
    if not server_id or not channel_id:
        raise RuntimeError("Missing server or channel.")
    config = load_config()
    context = _memory_context(config.state_dir / "memory.json", channel_id)
    source_messages = _manual_source_messages(context, target_user_key, target_message_id)
    if target_message_id and not source_messages:
        raise RuntimeError(
            "That selected message is no longer in remembered channel history. "
            "Run the scanner or reopen the channel, then try again."
        )
    own_source_message = _own_source_block_message(
        config,
        server_id=server_id,
        channel_id=channel_id,
        source_messages=source_messages,
        context=context,
    )
    if own_source_message:
        EventLog(config.state_dir / "events.json").add(
            event_type="own_reply_blocked",
            server_id=server_id,
            channel_id=channel_id,
            summary=own_source_message,
            draft="",
            user_key=target_user_key,
        )
        raise RuntimeError(own_source_message)
    source_ids = tuple(message.message_id for message in source_messages)
    ledger = ReplyLedger(config.state_dir / "sent_replies.json")
    duplicate_message = duplicate_reply_message(
        ledger.find_overlap(channel_id=channel_id, source_message_ids=source_ids)
    )
    if duplicate_message:
        EventLog(config.state_dir / "events.json").add(
            event_type="duplicate_reply_blocked",
            server_id=server_id,
            channel_id=channel_id,
            summary=duplicate_message,
            draft="",
            user_key=target_user_key,
        )
        raise RuntimeError(duplicate_message)
    existing = ApprovalQueue(config.state_dir / "approvals.json").find_source_overlap(
        channel_id=channel_id,
        source_message_ids=source_ids,
    )
    if existing:
        raise RuntimeError(
            "An approval is already queued for this recent message. "
            "Use Regenerate on the existing approval instead of creating another reply."
        )
    decision = asyncio.run(
        _generate_manual_decision(
            config,
            server_id=server_id,
            channel_id=channel_id,
            target_user_key=target_user_key,
            source_messages=source_messages,
            current_draft="",
            operator_instruction=operator_instruction,
        )
    )
    if not decision.draft:
        raise RuntimeError(decision.reason)
    draft = _draft_with_reply_mention(decision.draft, source_messages)
    output_block = outgoing_block_reason(draft)
    if output_block:
        EventLog(config.state_dir / "events.json").add(
            event_type="output_guard_blocked",
            server_id=server_id,
            channel_id=channel_id,
            summary=output_block,
            draft=draft,
            user_key=target_user_key,
        )
        raise RuntimeError(output_block)
    character = CharacterCardStore(config.character_dir, config.character_card).for_server(
        server_id,
        _server_character_card(config, server_id),
    )
    item = ApprovalQueue(config.state_dir / "approvals.json").add(
        server_id=server_id,
        channel_id=channel_id,
        character_name=character.name,
        engagement_type="manual",
        reason=_manual_approval_reason(operator_instruction or decision.reason, force_manual=force_manual),
        draft=draft,
        source_messages=source_messages,
    )
    EventLog(config.state_dir / "events.json").add(
        event_type="manual_approval_created",
        server_id=server_id,
        channel_id=channel_id,
        summary=_manual_approval_reason(operator_instruction or decision.reason, force_manual=force_manual),
        draft=item.draft,
        user_key=target_user_key,
    )


def _manual_approval_reason(reason: str, *, force_manual: bool) -> str:
    reason = str(reason or "manual approval draft").strip()
    if not force_manual:
        return reason
    return f"Manual override: {reason}"


def _memory_context(memory_path: Path, channel_id: str):
    return _memory_context_impl(memory_path, channel_id)


def _server_character_card(config: AppConfig, server_id: str) -> str | None:
    return _server_character_card_impl(config, server_id)


async def _generate_manual_decision(
    config: AppConfig,
    *,
    server_id: str,
    channel_id: str,
    target_user_key: str,
    current_draft: str,
    operator_instruction: str,
    original_draft: str = "",
    source_messages: list[MessageRecord] | None = None,
):
    memory = ConversationMemory(config.state_dir / "memory.json")
    memory.load()
    full_context = memory.context(channel_id, limit=120)
    effective_target_user_key = target_user_key or _source_user_key(source_messages or [])
    context = _manual_decision_context(
        full_context,
        source_messages or [],
        target_user_key=effective_target_user_key,
    )
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
        conversation_reply_enabled=True,
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
    selected_text = _source_message_prompt(source_messages or [])
    targeted_context = _regeneration_context_pack(
        full_context,
        target_user_key=effective_target_user_key,
        source_messages=source_messages or [],
    )
    prompt_instruction = operator_instruction
    if selected_text:
        prompt_instruction = (
            f"{operator_instruction or 'Draft a natural reply to the selected message.'}\n\n"
            f"Selected message context:\n{selected_text}"
        )
    return await planner.regenerate(
        channel_id=channel_id,
        character=character,
        character_memory=character_memory,
        context=context,
        user_memories=user_memories,
        user_instructions=user_notes,
        current_draft=current_draft,
        original_draft=original_draft,
        operator_instruction=prompt_instruction,
        target_user_key=effective_target_user_key,
        targeted_context=targeted_context,
    )


def _manual_decision_context(
    context: list[MessageRecord],
    source_messages: list[MessageRecord],
    *,
    target_user_key: str = "",
    before: int = 14,
    after: int = 8,
    recent: int = 8,
) -> list[MessageRecord]:
    if not context:
        return []
    source_ids = {message.message_id for message in source_messages}
    target_messages = _last_messages_for_user(context, target_user_key, limit=5)
    other_messages = _last_other_messages(context, target_user_key, limit=5)
    if not source_ids:
        return _merge_context_messages([*context[-24:], *target_messages, *other_messages], context)[-36:]
    selected_indexes = [
        index for index, message in enumerate(context) if message.message_id in source_ids
    ]
    if not selected_indexes:
        return _merge_context_messages([*context[-24:], *target_messages, *other_messages], context)[-36:]
    start = max(0, min(selected_indexes) - before)
    end = min(len(context), max(selected_indexes) + after + 1)
    selected_window = context[start:end]
    recent_window = context[-recent:]
    return _merge_context_messages(
        [*selected_window, *recent_window, *target_messages, *other_messages],
        context,
    )[-40:]


def _source_user_key(source_messages: list[MessageRecord]) -> str:
    if not source_messages:
        return ""
    return _message_record_user_key(source_messages[-1])


def _last_messages_for_user(
    context: list[MessageRecord],
    target_user_key: str,
    *,
    limit: int,
) -> list[MessageRecord]:
    if not target_user_key:
        return []
    matches = [
        message
        for message in reversed(context)
        if _message_record_user_key(message) == target_user_key and message.text.strip()
    ]
    return list(reversed(matches[:limit]))


def _last_other_messages(
    context: list[MessageRecord],
    target_user_key: str,
    *,
    limit: int,
) -> list[MessageRecord]:
    matches = [
        message
        for message in reversed(context)
        if (not target_user_key or _message_record_user_key(message) != target_user_key) and message.text.strip()
    ]
    return list(reversed(matches[:limit]))


def _merge_context_messages(
    messages: list[MessageRecord],
    ordered_context: list[MessageRecord],
) -> list[MessageRecord]:
    wanted = {message.message_id: message for message in messages if message.message_id}
    merged = [message for message in ordered_context if message.message_id in wanted]
    seen = {message.message_id for message in merged}
    merged.extend(message for message in messages if message.message_id not in seen)
    return merged


def _source_message_prompt(messages: list[MessageRecord]) -> str:
    lines = []
    for message in messages[-5:]:
        text = sanitize_outgoing_draft(message.text).strip()
        if len(text) > 600:
            text = text[:597].rstrip() + "..."
        lines.append(f"- {clean_discord_display_name(message.author)}: {text}")
    return "\n".join(lines)


def _regeneration_context_pack(
    context: list[MessageRecord],
    *,
    target_user_key: str,
    source_messages: list[MessageRecord],
) -> str:
    sections: list[str] = []
    target_messages = _last_messages_for_user(context, target_user_key, limit=5)
    other_messages = _last_other_messages(context, target_user_key, limit=5)
    if target_messages:
        sections.append("Last 5 messages from the target account:\n" + _source_message_prompt(target_messages))
    if other_messages:
        sections.append("5 most recent messages from other accounts:\n" + _source_message_prompt(other_messages))
    if source_messages:
        sections.append("Original selected/source messages:\n" + _source_message_prompt(source_messages))
    return "\n\n".join(sections)


async def _send_approval_message(
    config: AppConfig,
    server_id: str,
    channel_id: str,
    draft: str,
    *,
    reply_to_message_id: str = "",
) -> dict[str, object]:
    credentials = get_discord_credentials()
    async with DiscordWebSession(
        config.profile_dir,
        browser_channel=config.browser_channel,
        headless=config.headless,
    ) as session:
        logged_in = await session.login_if_needed(
            email=credentials.email,
            password=credentials.password,
            timeout_seconds=45,
            allow_human_challenge=False,
        )
        if not logged_in:
            raise RuntimeError(discord_login_blocker_message(await session.account_blocker_state()))
        current_url = await session.navigate_channel(
            server_id,
            channel_id,
            message_id=reply_to_message_id,
        )
        if channel_id not in current_url:
            raise RuntimeError("Discord redirected away from the approval channel.")
        delivery = await session.send_message(
            draft,
            reply_to_message_id=reply_to_message_id,
            reply_fallback_to_channel=True,
            typing_enabled=config.typing_indicator_enabled,
            typing_min_seconds=config.typing_min_seconds,
            typing_max_seconds=config.typing_max_seconds,
            typing_chars_per_second=config.typing_chars_per_second,
        )
        try:
            delivery["visible_messages"] = await session.read_visible_messages(server_id, channel_id)
        except Exception as exc:
            delivery["refresh_error"] = str(exc)
        return delivery


def start_discord_channel(body: dict) -> None:
    server_id = str(body.get("server_id") or "")
    channel_id = str(body.get("channel_id") or "")
    message_id = str(body.get("message_id") or "").strip()
    if not server_id or not channel_id:
        raise RuntimeError("Missing server or channel.")
    url = _discord_channel_url(server_id, channel_id, message_id)
    _open_external_discord_url(url)
    EventLog(load_config().state_dir / "events.json").add(
        event_type="conversation_opened",
        server_id=server_id,
        channel_id=channel_id,
        summary="Opened Discord conversation in the default browser so the automation profile stays undisturbed.",
    )


def read_env() -> dict[str, str]:
    return read_settings()


def update_env(values: dict) -> None:
    allowed = {
        "OPENAI_MODEL",
        "NHI_ZUES_LLM_ENABLED",
        "NHI_ZUES_RUNTIME_MODE",
        "NHI_ZUES_DRAFT_IN_DRY_RUN",
        "NHI_ZUES_CONVERSATION_REPLY_ENABLED",
        "NHI_ZUES_HEADLESS",
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
        "NHI_ZUES_SCANNER_MAX_CHANNELS_PER_CYCLE",
        "NHI_ZUES_SCANNER_CYCLE_SLEEP_SECONDS",
        "NHI_ZUES_SCANNER_MIN_CHANNEL_DELAY_SECONDS",
        "NHI_ZUES_SCANNER_MAX_CHANNEL_DELAY_SECONDS",
        "NHI_ZUES_SCANNER_HISTORY_BACKFILL_LIMIT",
        "NHI_ZUES_SCANNER_HISTORY_SCROLL_ROUNDS",
        "NHI_ZUES_REPLY_CANDIDATE_TTL_SECONDS",
        "NHI_ZUES_SAFETY_REVIEW_EXCLUSIVE",
        "NHI_ZUES_SAFETY_REVIEW_HISTORY_LIMIT",
        "NHI_ZUES_SAFETY_REVIEW_SCROLL_ROUNDS",
        "NHI_ZUES_SAFETY_REVIEW_HISTORY_RETRIES",
        "NHI_ZUES_REPLY_COOLDOWN_SECONDS",
        "NHI_ZUES_REPLY_WINDOW_SECONDS",
        "NHI_ZUES_REPLY_MAX_PER_WINDOW",
        "NHI_ZUES_REPLY_REQUIRE_INTERVENING_USER",
        "NHI_ZUES_REACTION_MAX_PER_CHANNEL",
        "NHI_ZUES_REACTION_THRESHOLD",
        "NHI_ZUES_REACTION_SAMPLE_PERCENT",
        "NHI_ZUES_REACTION_FORCE_LAUGH_PERCENT",
        "NHI_ZUES_REACTION_COOLDOWN_SECONDS",
        "NHI_ZUES_REACTION_EMOJI_OVERRIDE",
    }
    cleaned_values = {}
    for key, value in values.items():
        if key == "OPENAI_API_KEY":
            cleaned_key = _clean_env_value(key, value)
            if cleaned_key:
                set_openai_api_key(cleaned_key)
            continue
        if key not in allowed:
            continue
        cleaned = _clean_env_value(key, value)
        cleaned_values[key] = cleaned
    update_settings(cleaned_values, allowed=allowed)


def _clean_env_value(key: str, value) -> str:
    cleaned = str(value).strip()
    if "\n" in cleaned or "\r" in cleaned:
        raise ValueError(f"{key} cannot contain line breaks.")
    if key == "NHI_ZUES_RUNTIME_MODE" and cleaned not in {"dry", "full_auto", "semi_auto", "live_fire"}:
        raise ValueError("Response mode must be dry, full_auto, semi_auto, or live_fire.")
    if key == "NHI_ZUES_REACTION_THRESHOLD" and cleaned not in {"strict", "normal", "loose"}:
        raise ValueError("Reaction threshold must be strict, normal, or loose.")
    if key == "NHI_ZUES_REACTION_EMOJI_OVERRIDE":
        return cleaned[:8]
    numeric_ranges = {
        "NHI_ZUES_MAX_DAILY_USD": (0.0, 1000.0),
        "NHI_ZUES_MAX_SESSION_USD": (0.0, 1000.0),
        "NHI_ZUES_MAX_LLM_CALLS_PER_RUN": (0.0, 10000.0),
        "NHI_ZUES_WRITING_MISTAKE_RATE": (0.0, 0.35),
        "NHI_ZUES_TYPING_MIN_SECONDS": (0.0, 30.0),
        "NHI_ZUES_TYPING_MAX_SECONDS": (1.0, 60.0),
        "NHI_ZUES_TYPING_CHARS_PER_SECOND": (1.0, 40.0),
        "NHI_ZUES_SCANNER_MAX_CHANNELS_PER_CYCLE": (1.0, 10.0),
        "NHI_ZUES_SCANNER_CYCLE_SLEEP_SECONDS": (5.0, 600.0),
        "NHI_ZUES_SCANNER_MIN_CHANNEL_DELAY_SECONDS": (0.0, 300.0),
        "NHI_ZUES_SCANNER_MAX_CHANNEL_DELAY_SECONDS": (0.0, 600.0),
        "NHI_ZUES_SCANNER_HISTORY_BACKFILL_LIMIT": (0.0, 500.0),
        "NHI_ZUES_SCANNER_HISTORY_SCROLL_ROUNDS": (1.0, 45.0),
        "NHI_ZUES_REPLY_CANDIDATE_TTL_SECONDS": (0.0, 3600.0),
        "NHI_ZUES_SAFETY_REVIEW_HISTORY_LIMIT": (20.0, 5000.0),
        "NHI_ZUES_SAFETY_REVIEW_SCROLL_ROUNDS": (1.0, 150.0),
        "NHI_ZUES_SAFETY_REVIEW_HISTORY_RETRIES": (0.0, 2.0),
        "NHI_ZUES_REPLY_COOLDOWN_SECONDS": (0.0, 86400.0),
        "NHI_ZUES_REPLY_WINDOW_SECONDS": (60.0, 604800.0),
        "NHI_ZUES_REPLY_MAX_PER_WINDOW": (0.0, 1000.0),
        "NHI_ZUES_REACTION_MAX_PER_CHANNEL": (0.0, 100.0),
        "NHI_ZUES_REACTION_SAMPLE_PERCENT": (0.0, 100.0),
        "NHI_ZUES_REACTION_FORCE_LAUGH_PERCENT": (0.0, 100.0),
        "NHI_ZUES_REACTION_COOLDOWN_SECONDS": (0.0, 86400.0),
    }
    if key in numeric_ranges:
        try:
            number = float(cleaned)
        except ValueError as exc:
            raise ValueError(f"{key} must be numeric.") from exc
        minimum, maximum = numeric_ranges[key]
        if not minimum <= number <= maximum:
            raise ValueError(f"{key} must be between {minimum:g} and {maximum:g}.")
        integer_keys = {
            "NHI_ZUES_MAX_LLM_CALLS_PER_RUN",
            "NHI_ZUES_SCANNER_MAX_CHANNELS_PER_CYCLE",
            "NHI_ZUES_SCANNER_HISTORY_BACKFILL_LIMIT",
            "NHI_ZUES_SCANNER_HISTORY_SCROLL_ROUNDS",
            "NHI_ZUES_SAFETY_REVIEW_HISTORY_LIMIT",
            "NHI_ZUES_SAFETY_REVIEW_SCROLL_ROUNDS",
            "NHI_ZUES_SAFETY_REVIEW_HISTORY_RETRIES",
            "NHI_ZUES_REPLY_MAX_PER_WINDOW",
            "NHI_ZUES_REACTION_MAX_PER_CHANNEL",
        }
        if key in integer_keys:
            if not number.is_integer():
                raise ValueError(f"{key} must be a whole number.")
            return str(int(number))
    return cleaned


def start_discord_login() -> None:
    _acquire_discord_session_or_raise(pause_runtime=True)
    DISCORD_SESSION_LOCK.release()
    kwargs = {}
    if sys.platform == "win32":
        kwargs["creationflags"] = subprocess.CREATE_NO_WINDOW
    subprocess.Popen(
        [_background_python_executable(), "-m", "nhi_zues.cli", "--login"],
        cwd=ROOT,
        close_fds=True,
        **kwargs,
    )


def _background_python_executable() -> str:
    if sys.platform == "win32":
        pythonw = Path(sys.executable).with_name("pythonw.exe")
        if pythonw.exists():
            return str(pythonw)
    return sys.executable


def _discord_channel_url(server_id: str, channel_id: str, message_id: str = "") -> str:
    url = f"https://discord.com/channels/{server_id}/{channel_id}"
    token = _discord_message_token(message_id)
    return f"{url}/{token}" if token else url


def _discord_message_token(message_id: str) -> str:
    raw = str(message_id or "").strip()
    if not raw:
        return ""
    if raw.startswith("chat-messages-"):
        return raw.rsplit("-", 1)[-1]
    return raw


def _open_external_discord_url(url: str) -> None:
    if sys.platform == "win32":
        chrome = _first_existing_path(
            Path(os.environ.get("LOCALAPPDATA", "")) / "Google" / "Chrome" / "Application" / "chrome.exe",
            Path(os.environ.get("PROGRAMFILES", "")) / "Google" / "Chrome" / "Application" / "chrome.exe",
            Path(os.environ.get("PROGRAMFILES(X86)", "")) / "Google" / "Chrome" / "Application" / "chrome.exe",
        )
        edge = _first_existing_path(
            Path(os.environ.get("PROGRAMFILES(X86)", "")) / "Microsoft" / "Edge" / "Application" / "msedge.exe",
            Path(os.environ.get("PROGRAMFILES", "")) / "Microsoft" / "Edge" / "Application" / "msedge.exe",
        )
        browser = chrome or edge
        if browser:
            subprocess.Popen(
                [str(browser), "--new-window", url],
                cwd=ROOT,
                close_fds=True,
                creationflags=subprocess.CREATE_NO_WINDOW,
            )
            return
    webbrowser.open_new(url)


def _first_existing_path(*paths: Path) -> Path | None:
    for path in paths:
        if path and path.exists():
            return path
    return None


def update_state() -> dict:
    global UPDATE_STATE_CACHE, UPDATE_STATE_CACHE_AT
    now = time.time()
    with UPDATE_STATE_CACHE_LOCK:
        if UPDATE_STATE_CACHE is not None and now - UPDATE_STATE_CACHE_AT < UPDATE_STATE_CACHE_SECONDS:
            return dict(UPDATE_STATE_CACHE)

    remote = _git(["remote", "get-url", "origin"], check=False).stdout.strip()
    payload = {
        "remote": remote,
        "remote_allowed": _remote_allowed(remote) if remote else False,
    }
    with UPDATE_STATE_CACHE_LOCK:
        UPDATE_STATE_CACHE = dict(payload)
        UPDATE_STATE_CACHE_AT = now
    return payload


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
        "can_fast_forward": behind > 0 and ahead == 0,
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
    if ahead > 0:
        return {
            **payload,
            "ok": False,
            "error": (
                "This checkout has diverged from origin/main; a safe fast-forward is impossible. "
                "Reconcile the Git branches manually before updating from the app."
            ),
        }

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
    kwargs = {}
    if sys.platform == "win32":
        startupinfo = subprocess.STARTUPINFO()
        startupinfo.dwFlags |= subprocess.STARTF_USESHOWWINDOW
        startupinfo.wShowWindow = getattr(subprocess, "SW_HIDE", 0)
        kwargs["startupinfo"] = startupinfo
        kwargs["creationflags"] = subprocess.CREATE_NO_WINDOW
    return subprocess.run(
        ["git", *args],
        cwd=ROOT,
        check=check,
        capture_output=True,
        text=True,
        timeout=60,
        **kwargs,
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
    parsed = urlparse(icon_url)
    if parsed.scheme != "https" or (parsed.hostname or "").lower() not in {
        "cdn.discordapp.com",
        "media.discordapp.net",
    }:
        return ""
    suffix = Path(parsed.path).suffix.lower()
    if suffix not in {".png", ".jpg", ".jpeg", ".webp", ".gif"}:
        suffix = ".webp"
    filename = f"{server_id}-{hashlib.sha256(icon_url.encode('utf-8')).hexdigest()[:12]}{suffix}"
    target_dir = state_dir / "server_icons"
    target = target_dir / filename
    if not target.exists():
        target_dir.mkdir(parents=True, exist_ok=True)
        request = urllib.request.Request(icon_url, headers={"User-Agent": "Kabuki-Cord"})
        with urllib.request.urlopen(request, timeout=20) as response:
            content_length = int(response.headers.get("Content-Length") or "0")
            if content_length > 2_000_000:
                return ""
            data = response.read(2_000_001)
            if len(data) > 2_000_000:
                return ""
            target.write_bytes(data)
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
    return read_json_file(path, default=default)


def _read_config_json(path: Path, *, default: dict) -> dict:
    if not path.exists():
        return default
    return json.loads(path.read_text(encoding="utf-8-sig"))


def _write_json(path: Path, payload: dict) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    write_text_file(path, json.dumps(payload, indent=2, ensure_ascii=False), encoding="utf-8")


def main() -> None:
    host = os.getenv("KABUKI_CORD_HOST", "127.0.0.1")
    port = int(os.getenv("KABUKI_CORD_PORT", "8765"))
    configure_diagnostic_logging(load_config().state_dir)
    if not _is_loopback_host(host):
        raise RuntimeError("Kabuki-Cord GUI must bind to a loopback host such as 127.0.0.1 or localhost.")
    server = ThreadingHTTPServer((host, port), GuiHandler)
    print(f"Kabuki-Cord GUI: http://{host}:{port}")
    server.serve_forever()


if __name__ == "__main__":
    main()
