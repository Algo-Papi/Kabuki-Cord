from __future__ import annotations

import os
from dataclasses import dataclass

import keyring
from keyring.errors import KeyringError


SERVICE = "Kabuki-Cord"
DISCORD_EMAIL_KEY = "discord_email"
DISCORD_PASSWORD_KEY = "discord_password"


@dataclass(frozen=True)
class DiscordCredentials:
    email: str | None
    password: str | None

    @property
    def complete(self) -> bool:
        return bool(self.email and self.password)


def get_discord_credentials() -> DiscordCredentials:
    return DiscordCredentials(
        email=_get_secret(DISCORD_EMAIL_KEY) or os.getenv("KABUKI_CORD_DISCORD_EMAIL") or None,
        password=_get_secret(DISCORD_PASSWORD_KEY) or os.getenv("KABUKI_CORD_DISCORD_PASSWORD") or None,
    )


def set_discord_credentials(*, email: str | None = None, password: str | None = None) -> None:
    if email is not None and email.strip():
        _set_secret(DISCORD_EMAIL_KEY, email.strip())
    if password is not None and password.strip():
        _set_secret(DISCORD_PASSWORD_KEY, password)


def discord_credential_status() -> dict:
    credentials = get_discord_credentials()
    return {
        "email_set": bool(credentials.email),
        "password_set": bool(credentials.password),
        "complete": credentials.complete,
    }


def _get_secret(name: str) -> str | None:
    try:
        value = keyring.get_password(SERVICE, name)
    except KeyringError:
        return None
    return value or None


def _set_secret(name: str, value: str) -> None:
    try:
        keyring.set_password(SERVICE, name, value)
    except KeyringError as exc:
        raise RuntimeError("Could not save secret to the operating system keyring.") from exc
