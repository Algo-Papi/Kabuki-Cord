from __future__ import annotations

import asyncio
import json
import mimetypes
import os
import secrets as token_secrets
import subprocess
import sys
from dataclasses import asdict
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from importlib.metadata import PackageNotFoundError, version
from pathlib import Path
from urllib.parse import unquote, urlparse

from dotenv import load_dotenv

from .approvals import ApprovalQueue
from .browser import DiscordWebSession
from .budget import BudgetManager
from .character_memory import CharacterMemoryStore
from .config import AppConfig, load_config
from .secrets import discord_credential_status, get_discord_credentials, set_discord_credentials
from .user_instructions import UserInstructionStore


ROOT = Path.cwd()
WEB_ROOT = ROOT / "web"
SESSION_TOKEN = token_secrets.token_urlsafe(32)


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
            if not user_key or not note:
                self._json({"ok": False, "error": "Missing user key or note."}, status=400)
                return
            UserInstructionStore(config.state_dir / "user_instructions.json").add(user_key, note)
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


def app_state() -> dict:
    load_dotenv(override=True)
    config = load_config()
    env = read_env()
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
        },
        "discord": discord_credential_status(),
        "updates": update_state(),
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
        },
        "servers": _read_json(config.servers_file, default={"servers": []}),
        "characters": character_cards(config.character_dir),
        "active_character": read_character(config.character_dir, config.character_card),
        "character_memory": character_memory_state(config.state_dir, config.character_card),
        "user_instructions": user_instruction_state(config.state_dir),
        "usage": usage_state(),
        "approvals": [asdict(item) for item in ApprovalQueue(config.state_dir / "approvals.json").list()],
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


def sync_discord_servers() -> dict:
    config = load_config()
    try:
        discovered = asyncio.run(_discover_discord_servers(config))
    except RuntimeError:
        raise
    except Exception as exc:
        raise RuntimeError(
            "Discord sync failed. Close any open Kabuki Discord sign-in windows and try again."
        ) from exc
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
            continue
        if label and not str(existing.get("label") or "").strip():
            existing["label"] = label
            updated += 1

    next_payload = {**payload, "servers": server_list}
    _write_json(config.servers_file, next_payload)
    return {
        "ok": True,
        "discovered": len(discovered),
        "added": added,
        "updated": updated,
        "state": app_state(),
    }


async def _discover_discord_servers(config: AppConfig) -> list[dict[str, str]]:
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


def character_memory_state(state_dir: Path, card_id: str) -> dict:
    memory = CharacterMemoryStore(state_dir / "character_memory").load(card_id)
    return asdict(memory)


def user_instruction_state(state_dir: Path) -> dict:
    path = state_dir / "user_instructions.json"
    return _read_json(path, default={"items": []})


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
