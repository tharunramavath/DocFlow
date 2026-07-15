"""
services/preset_manager.py
==========================
Manages reusable presets. A preset is a complete, self-contained snapshot of
a configuration — certificate template reference, email template, sender
settings, organization, text positions, delay settings, column mapping,
retry settings and campaign settings — saved as a JSON file in ``presets/``.

Supports the full lifecycle the UI needs: create, duplicate, rename, delete,
import and export, plus a built-in read-only "Default Template" derived from
the application defaults.
"""

from __future__ import annotations

import json
import re
from datetime import datetime
from pathlib import Path
from typing import Dict, List

from services.config_manager import PRESETS_DIR, default_config, deep_merge, DEFAULT_CONFIG, migrate_config

DEFAULT_PRESET_NAME = "Default Template"


class PresetError(Exception):
    """Raised when a preset operation fails."""


def _slugify(name: str) -> str:
    slug = re.sub(r"[^a-zA-Z0-9_-]+", "_", name.strip()).strip("_")
    return slug or "preset"


def _preset_path(name: str) -> Path:
    return PRESETS_DIR / f"{_slugify(name)}.json"


def list_presets() -> List[str]:
    """Return preset display names (built-in default first, then user presets)."""
    names = []
    for path in sorted(PRESETS_DIR.glob("*.json")):
        try:
            with open(path, "r", encoding="utf-8") as f:
                data = json.load(f)
            names.append(data.get("name", path.stem))
        except (json.JSONDecodeError, OSError):
            continue
    names = sorted(names, key=str.lower)
    return [DEFAULT_PRESET_NAME] + [n for n in names if n != DEFAULT_PRESET_NAME]


def preset_exists(name: str) -> bool:
    if name == DEFAULT_PRESET_NAME:
        return True
    return _preset_path(name).exists()


def load_preset(name: str) -> Dict:
    """Return the config dict stored in a preset (deep-merged over defaults)."""
    if name == DEFAULT_PRESET_NAME:
        return default_config()

    path = _preset_path(name)
    if not path.exists():
        raise PresetError(f"Preset '{name}' not found.")
    with open(path, "r", encoding="utf-8") as f:
        data = json.load(f)
    data = migrate_config(data.get("config", {}))
    return deep_merge(DEFAULT_CONFIG, data)


def save_preset(name: str, config: Dict, overwrite: bool = True) -> str:
    """Create or update a preset with the given name and config."""
    name = (name or "").strip()
    if not name:
        raise PresetError("Preset name cannot be empty.")
    if name == DEFAULT_PRESET_NAME:
        raise PresetError("The built-in 'Default Template' cannot be overwritten.")

    path = _preset_path(name)
    if path.exists() and not overwrite:
        raise PresetError(f"A preset named '{name}' already exists.")

    payload = {
        "name": name,
        "saved_at": datetime.now().isoformat(timespec="seconds"),
        "config": config,
    }
    with open(path, "w", encoding="utf-8") as f:
        json.dump(payload, f, indent=2, ensure_ascii=False)
    return name


def duplicate_preset(source: str, new_name: str) -> str:
    """Copy an existing preset (including the built-in default) to a new name."""
    config = load_preset(source)
    return save_preset(new_name, config, overwrite=False)


def rename_preset(old_name: str, new_name: str) -> str:
    """Rename a user preset. The built-in default cannot be renamed."""
    if old_name == DEFAULT_PRESET_NAME:
        raise PresetError("The built-in 'Default Template' cannot be renamed.")
    config = load_preset(old_name)
    saved = save_preset(new_name, config, overwrite=False)
    delete_preset(old_name)
    return saved


def delete_preset(name: str) -> None:
    """Delete a user preset. The built-in default cannot be deleted."""
    if name == DEFAULT_PRESET_NAME:
        raise PresetError("The built-in 'Default Template' cannot be deleted.")
    path = _preset_path(name)
    if path.exists():
        path.unlink()


def export_preset(name: str) -> bytes:
    """Return the preset as pretty-printed JSON bytes for download."""
    config = load_preset(name)
    payload = {
        "name": name,
        "exported_at": datetime.now().isoformat(timespec="seconds"),
        "config": config,
    }
    return json.dumps(payload, indent=2, ensure_ascii=False).encode("utf-8")


def import_preset(raw: bytes, fallback_name: str = "Imported Preset") -> str:
    """Import a preset from uploaded JSON bytes and return the stored name."""
    try:
        data = json.loads(raw.decode("utf-8"))
    except (json.JSONDecodeError, UnicodeDecodeError) as exc:
        raise PresetError(f"Not a valid preset file: {exc}") from exc

    config = data.get("config")
    if not isinstance(config, dict):
        raise PresetError("The file does not contain a 'config' section.")

    name = data.get("name") or fallback_name
    # Avoid clobbering an existing preset on import.
    candidate = name
    counter = 2
    while preset_exists(candidate):
        candidate = f"{name} ({counter})"
        counter += 1

    merged = deep_merge(DEFAULT_CONFIG, config)
    return save_preset(candidate, merged, overwrite=False)
