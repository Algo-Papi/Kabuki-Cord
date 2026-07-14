from __future__ import annotations

import os
import json
from pathlib import Path

from dotenv import dotenv_values

from .app_paths import legacy_root, settings_path
from .state_io import write_text_file


SECRET_KEYS = {
    "OPENAI_API_KEY",
    "KABUKI_CORD_DISCORD_EMAIL",
    "KABUKI_CORD_DISCORD_PASSWORD",
}


def read_settings(path: Path | None = None) -> dict[str, str]:
    target = path or settings_path()
    if not target.exists():
        return {}
    return {
        str(key): str(value or "")
        for key, value in dotenv_values(target, encoding="utf-8-sig").items()
        if key
    }


def load_settings_environment(*, override: bool = False) -> dict[str, str]:
    values = read_settings()
    for key, value in values.items():
        if key in SECRET_KEYS:
            continue
        if override or key not in os.environ:
            os.environ[key] = value
    return values


def update_settings(values: dict[str, str], *, allowed: set[str]) -> dict[str, str]:
    target = settings_path()
    existing = {
        key: value
        for key, value in read_settings(target).items()
        if key not in SECRET_KEYS
    }
    for key, value in values.items():
        if key not in allowed or key in SECRET_KEYS:
            continue
        existing[key] = str(value)
        os.environ[key] = str(value)
    payload = "\n".join(
        f"{key}={json.dumps(value, ensure_ascii=False)}"
        for key, value in sorted(existing.items())
    )
    write_text_file(target, payload + ("\n" if payload else ""), encoding="utf-8")
    return existing


def migrate_legacy_settings() -> bool:
    """Move legacy repo-local settings to app data and secrets to the OS keyring."""
    target = settings_path()
    first_migration = not target.exists()
    legacy = read_legacy_settings()
    nonsecret = {key: value for key, value in legacy.items() if key not in SECRET_KEYS}
    legacy_path_defaults = {
        "NHI_ZUES_PROFILE_DIR": {".profiles/nhi-zues", ".profiles\\nhi-zues"},
        "NHI_ZUES_STATE_DIR": {".state"},
    }
    replacements = {
        "NHI_ZUES_PROFILE_DIR": "profiles/discord",
        "NHI_ZUES_STATE_DIR": "state",
    }
    for key, old_values in legacy_path_defaults.items():
        if str(nonsecret.get(key) or "").strip() in old_values:
            nonsecret[key] = replacements[key]
    if first_migration:
        update_settings(nonsecret, allowed=set(nonsecret))

    # Import lazily to avoid a settings/secrets import cycle at module load time.
    from .secrets import (
        get_discord_credentials,
        get_openai_api_key,
        set_discord_credentials,
        set_openai_api_key,
    )

    openai_key = str(legacy.get("OPENAI_API_KEY") or "").strip()
    discord_email = str(legacy.get("KABUKI_CORD_DISCORD_EMAIL") or "").strip()
    discord_password = str(legacy.get("KABUKI_CORD_DISCORD_PASSWORD") or "")
    try:
        if openai_key and not get_openai_api_key():
            set_openai_api_key(openai_key)
        current_discord = get_discord_credentials()
        if (discord_email and not current_discord.email) or (
            discord_password and not current_discord.password
        ):
            set_discord_credentials(email=discord_email or None, password=discord_password or None)
    except RuntimeError:
        # Preserve one-run continuity on systems where a keyring is unavailable.
        if openai_key:
            os.environ.setdefault("OPENAI_API_KEY", openai_key)
        if discord_email:
            os.environ.setdefault("KABUKI_CORD_DISCORD_EMAIL", discord_email)
        if discord_password:
            os.environ.setdefault("KABUKI_CORD_DISCORD_PASSWORD", discord_password)
    return first_migration and bool(legacy)


def legacy_settings_path() -> Path:
    return legacy_root() / ".env"


def read_legacy_settings() -> dict[str, str]:
    return read_settings(legacy_settings_path())
