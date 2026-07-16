"""
services/config_manager.py
==========================
Single source of truth for every user-editable setting in the application.

The whole app is driven by one nested configuration dictionary. This module
owns its default shape, and knows how to persist it to ``config/config.json``
and load it back (deep-merged over the defaults, so new keys added in future
versions never break an old saved file).

Nothing else in the codebase should hardcode a default value that belongs
here.
"""

from __future__ import annotations

import copy
import json
import uuid
from pathlib import Path
from typing import Any, Dict

# ---------------------------------------------------------------------------
# Project directories (created on import so every service can rely on them)
# ---------------------------------------------------------------------------
BASE_DIR = Path(__file__).resolve().parent.parent

ASSETS_DIR = BASE_DIR / "assets"
FONTS_DIR = ASSETS_DIR / "fonts"
TEMPLATES_DIR = BASE_DIR / "templates"
PRESETS_DIR = BASE_DIR / "presets"
GENERATED_DIR = BASE_DIR / "generated_certificates"
LOGS_DIR = BASE_DIR / "logs"
CONFIG_DIR = BASE_DIR / "config"

CONFIG_FILE = CONFIG_DIR / "config.json"

UPLOADS_DIR = ASSETS_DIR / "uploads"
MEDIA_DIR = ASSETS_DIR / "media"
MEDIA_CATEGORY_DIRS = {
    "image": MEDIA_DIR / "images",
    "video": MEDIA_DIR / "videos",
    "audio": MEDIA_DIR / "audio",
    "spreadsheet": MEDIA_DIR / "spreadsheets",
    "document": MEDIA_DIR / "documents",
    "other": MEDIA_DIR / "other",
}

for _d in (
    ASSETS_DIR,
    FONTS_DIR,
    TEMPLATES_DIR,
    PRESETS_DIR,
    GENERATED_DIR,
    LOGS_DIR,
    CONFIG_DIR,
    UPLOADS_DIR,
    MEDIA_DIR,
    *MEDIA_CATEGORY_DIRS.values(),
):
    _d.mkdir(parents=True, exist_ok=True)


# ---------------------------------------------------------------------------
# Default configuration — the canonical shape of a config / preset
# ---------------------------------------------------------------------------
DEFAULT_CONFIG: Dict[str, Any] = {
    # 2. Email / sender settings ------------------------------------------
    "email_settings": {
        "sender_name": "",
        "sender_email": "",
        "brevo_api_key": "",
        "organization_name": "Our Team",
        "reply_to_email": "",
        "email_subject": "\U0001f389 Your Certificate of Participation",
        "campaign_name": "",
    },
    # 3. Email template ---------------------------------------------------
    "email_template": {
        "body": (
            "Dear {{Name}},\n\n"
            "Thank you for being a part of {{Organization}}'s event. "
            "We sincerely appreciate your time, enthusiasm, and participation.\n\n"
            "Please find your {{CertificateName}} attached to this email. "
            "We hope it serves as a reminder of your achievement.\n\n"
            "We look forward to welcoming you again at our future events.\n\n"
            "Warm Regards,\n"
            "{{Organization}}\n\n"
            "This is an automated message sent on {{Date}}."
        ),
    },
    # 6. Certificate elements (multi-element support) --------------------
    "certificate_elements": [
        {
            "id": "name_element",
            "type": "text",
            "label": "Participant Name",
            "content_source": "{{Name}}",
            "x": 995,
            "y": 680,
            "font_size": 90,
            "min_font_size": 40,
            "font_size_step": 2,
            "max_text_width": 1350,
            "font_color": "#141414",
            "font_family": "DejaVuSerif",
            "bold": True,
            "italic": False,
            "alignment": "center",
        },
    ],
    "dpi": 300,
    # 7. Delay / retry behaviour ------------------------------------------
    "delay_settings": {
        "delay_between_emails": 2.0,
        "delay_unit": "seconds",  # "seconds" | "minutes"
        "retry_count": 3,
        "retry_delay": 5,
        "max_retry_attempts": 3,
    },
    # 8. Campaign settings ------------------------------------------------
    "campaign_settings": {
        "campaign_name": "",
        "event_name": "",
        "certificate_name": "Certificate of Participation",
        "batch_size": 50,
        "sending_mode": "immediate",  # "immediate" | "scheduled"
    },
    # 9. Scheduler --------------------------------------------------------
    "scheduler": {
        "date": "",  # ISO date string, empty = today
        "time": "09:00",
        "timezone": "UTC",
    },
    # 4. Column mapping ---------------------------------------------------
    "column_mapping": {
        "name_column": "Name",
        "email_column": "Email",
        "certificate_id_column": "",
        "extra_fields": {},  # { "{{Placeholder}}": "Excel Column" }
    },
    # 5. Certificate template (path, relative to project or absolute) -----
    "certificate_template": "templates/certificate.png",
    # Global -------------------------------------------------------------
    "dry_run": True,
}


# ---------------------------------------------------------------------------
# Deep-merge helper
# ---------------------------------------------------------------------------
def deep_merge(base: Dict[str, Any], override: Dict[str, Any]) -> Dict[str, Any]:
    """
    Return a new dict where ``override`` is layered on top of ``base``.

    Nested dictionaries are merged recursively so that a saved config that
    predates a newly added default key still receives that key.
    """
    result = copy.deepcopy(base)
    for key, value in (override or {}).items():
        if key in result and isinstance(result[key], dict) and isinstance(value, dict):
            result[key] = deep_merge(result[key], value)
        else:
            result[key] = copy.deepcopy(value)
    return result


def default_config() -> Dict[str, Any]:
    """Return a fresh deep copy of the default configuration."""
    return copy.deepcopy(DEFAULT_CONFIG)


# ---------------------------------------------------------------------------
# Persistence
# ---------------------------------------------------------------------------
def migrate_config(saved: Dict[str, Any]) -> Dict[str, Any]:
    """Apply backward compatibility migrations to older configs."""
    # Backward compatibility for email template body
    if "email_template" in saved:
        tmpl = saved["email_template"]
        if "greeting" in tmpl or "thank_you" in tmpl or "regards" in tmpl:
            parts = []
            for sec in [
                "greeting",
                "body",
                "thank_you",
                "future_invitation",
                "regards",
                "signature",
                "footer",
            ]:
                if sec in tmpl and tmpl[sec].strip():
                    parts.append(tmpl[sec].strip())
            saved["email_template"] = {"body": "\n\n".join(parts)}

    # Migrate old text_position -> certificate_elements
    if "text_position" in saved and "certificate_elements" not in saved:
        old = saved["text_position"]
        dpi = old.pop("dpi", 300)
        saved["dpi"] = dpi
        saved["certificate_elements"] = [
            {
                "id": "element_" + uuid.uuid4().hex[:8],
                "type": "text",
                "label": "Participant Name",
                "content_source": "{{Name}}",
                "x": old.get("x", 995),
                "y": old.get("y", 680),
                "font_size": old.get("font_size", 90),
                "min_font_size": old.get("min_font_size", 40),
                "font_size_step": old.get("font_size_step", 2),
                "max_text_width": old.get("max_text_width", 1350),
                "font_color": old.get("font_color", "#141414"),
                "font_family": old.get("font_family", "DejaVuSerif"),
                "bold": old.get("bold", True),
                "italic": old.get("italic", False),
                "alignment": old.get("alignment", "center"),
            }
        ]
        del saved["text_position"]

    return saved


def load_config() -> Dict[str, Any]:
    """
    Load the last-used configuration from disk, deep-merged over the
    defaults. If no config file exists yet, the defaults are returned.
    """
    if not CONFIG_FILE.exists():
        return default_config()
    try:
        with open(CONFIG_FILE, "r", encoding="utf-8") as f:
            saved = json.load(f)

        saved = migrate_config(saved)

        return deep_merge(DEFAULT_CONFIG, saved)
    except (json.JSONDecodeError, OSError):
        # A corrupt config should never brick the app — fall back to defaults.
        return default_config()


def save_config(config: Dict[str, Any]) -> None:
    """Persist ``config`` to ``config/config.json`` (pretty-printed)."""
    CONFIG_DIR.mkdir(parents=True, exist_ok=True)
    with open(CONFIG_FILE, "w", encoding="utf-8") as f:
        json.dump(config, f, indent=2, ensure_ascii=False)


# ---------------------------------------------------------------------------
# Path resolution helper
# ---------------------------------------------------------------------------
def resolve_path(path_str: str) -> Path:
    """
    Resolve a stored path string to an absolute Path. Relative paths are
    interpreted relative to the project base directory.
    """
    if not path_str:
        return Path()
    p = Path(path_str)
    return p if p.is_absolute() else (BASE_DIR / p)


def to_relative(path: Path) -> str:
    """Store paths relative to the project root when possible."""
    try:
        return str(Path(path).resolve().relative_to(BASE_DIR))
    except ValueError:
        return str(path)
