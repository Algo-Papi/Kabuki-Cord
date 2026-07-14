from __future__ import annotations

import os
import shutil
from pathlib import Path


APP_NAME = "Kabuki-Cord"
PACKAGE_ROOT = Path(__file__).resolve().parent
SOURCE_ROOT = PACKAGE_ROOT.parents[1]


def app_data_root() -> Path:
    configured = str(os.getenv("KABUKI_CORD_DATA_DIR") or "").strip()
    if configured:
        return Path(configured).expanduser().resolve()
    if os.name == "nt" and os.getenv("LOCALAPPDATA"):
        return (Path(os.environ["LOCALAPPDATA"]) / APP_NAME).resolve()
    xdg = str(os.getenv("XDG_DATA_HOME") or "").strip()
    if xdg:
        return (Path(xdg).expanduser() / "kabuki-cord").resolve()
    return (Path.home() / ".local" / "share" / "kabuki-cord").resolve()


def settings_path() -> Path:
    return app_data_root() / "settings.env"


def resolve_data_path(value: str, default: str) -> Path:
    raw = str(value or default).strip() or default
    candidate = Path(raw).expanduser()
    if candidate.is_absolute():
        return candidate.resolve()
    cleaned_parts = [part for part in candidate.parts if part not in {".", ""}]
    root = app_data_root().resolve()
    resolved = root.joinpath(*cleaned_parts).resolve()
    if resolved != root and root not in resolved.parents:
        raise ValueError("Relative app-data paths cannot escape the Kabuki-Cord data directory.")
    return resolved


def web_root() -> Path:
    configured = str(os.getenv("KABUKI_CORD_WEB_ROOT") or "").strip()
    if configured:
        return Path(configured).expanduser().resolve()
    packaged = PACKAGE_ROOT / "web"
    if packaged.exists():
        return packaged
    return SOURCE_ROOT / "web"


def asset_root() -> Path:
    packaged = PACKAGE_ROOT / "assets"
    if packaged.exists():
        return packaged
    return SOURCE_ROOT / "assets"


def legacy_root() -> Path:
    configured = str(os.getenv("KABUKI_CORD_LEGACY_ROOT") or "").strip()
    if configured:
        return Path(configured).expanduser().resolve()
    return SOURCE_ROOT


def ensure_user_data_layout() -> None:
    root = app_data_root()
    root.mkdir(parents=True, exist_ok=True)
    _copy_tree_once(_default_character_source(), root / "character_cards")
    _copy_file_once(_default_servers_source(), root / "config" / "servers.json")


def migrate_legacy_data(*, include_browser_profile: bool = True) -> dict[str, bool]:
    root = app_data_root()
    old = legacy_root()
    if root == old:
        return {}
    root.mkdir(parents=True, exist_ok=True)
    migrated = {
        "state": _copy_tree_once(old / ".state", root / "state"),
        "config": _copy_file_once(old / "config" / "servers.json", root / "config" / "servers.json"),
        "characters": _copy_tree_once(old / "character_cards", root / "character_cards"),
    }
    if include_browser_profile:
        migrated["profile"] = _copy_tree_once(old / ".profiles" / "nhi-zues", root / "profiles" / "discord")
    return migrated


def _default_character_source() -> Path:
    packaged = PACKAGE_ROOT / "defaults" / "character_cards"
    return packaged if packaged.exists() else SOURCE_ROOT / "character_cards"


def _default_servers_source() -> Path:
    packaged = PACKAGE_ROOT / "defaults" / "servers.example.json"
    if packaged.exists():
        return packaged
    example = SOURCE_ROOT / "config" / "servers.example.json"
    return example if example.exists() else SOURCE_ROOT / "config" / "servers.json"


def _copy_tree_once(source: Path, target: Path) -> bool:
    if target.exists() or not source.exists() or not source.is_dir():
        return False
    target.parent.mkdir(parents=True, exist_ok=True)
    temporary = target.with_name(f".{target.name}.migrating")
    try:
        if temporary.exists():
            shutil.rmtree(temporary)
        shutil.copytree(source, temporary)
        temporary.replace(target)
        return True
    except OSError:
        shutil.rmtree(temporary, ignore_errors=True)
        return False


def _copy_file_once(source: Path, target: Path) -> bool:
    if target.exists() or not source.exists() or not source.is_file():
        return False
    target.parent.mkdir(parents=True, exist_ok=True)
    temporary = target.with_name(f".{target.name}.migrating")
    try:
        shutil.copy2(source, temporary)
        temporary.replace(target)
        return True
    except OSError:
        temporary.unlink(missing_ok=True)
        return False
