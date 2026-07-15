"""
core/utils.py
=============
Small, reusable helpers shared across services. Email validation and
filename sanitization are carried over verbatim in behaviour from the
original project's ``utils.py`` so existing data keeps working exactly as
before.
"""

from __future__ import annotations

import re
from typing import Tuple

# A pragmatic, widely used regex for validating "good enough" email syntax.
_EMAIL_REGEX = re.compile(
    r"^[a-zA-Z0-9.!#$%&'*+/=?^_`{|}~-]+"
    r"@[a-zA-Z0-9](?:[a-zA-Z0-9-]{0,61}[a-zA-Z0-9])?"
    r"(?:\.[a-zA-Z0-9](?:[a-zA-Z0-9-]{0,61}[a-zA-Z0-9])?)+$"
)


def is_valid_email(email: str) -> bool:
    """Return True if ``email`` looks like a syntactically valid address."""
    if not isinstance(email, str):
        return False
    return bool(_EMAIL_REGEX.match(email.strip()))


def sanitize_filename(name: str) -> str:
    """
    Convert a participant's name into a filesystem-safe filename fragment.
    Removes characters that are illegal on common filesystems and collapses
    whitespace.
    """
    cleaned = re.sub(r'[\\/*?:"<>|]', "", str(name)).strip()
    cleaned = re.sub(r"\s+", " ", cleaned)
    return cleaned or "participant"


def hex_to_rgb(value: str) -> Tuple[int, int, int]:
    """Convert a ``#RRGGBB`` (or ``#RGB``) hex string to an (r, g, b) tuple."""
    value = (value or "").strip().lstrip("#")
    if len(value) == 3:
        value = "".join(c * 2 for c in value)
    if len(value) != 6:
        return (20, 20, 20)
    try:
        return tuple(int(value[i : i + 2], 16) for i in (0, 2, 4))  # type: ignore[return-value]
    except ValueError:
        return (20, 20, 20)


def human_duration(seconds: float) -> str:
    """Format a number of seconds as a compact ``1h 2m 3s`` string."""
    seconds = int(max(0, seconds))
    hours, rem = divmod(seconds, 3600)
    minutes, secs = divmod(rem, 60)
    parts = []
    if hours:
        parts.append(f"{hours}h")
    if minutes or hours:
        parts.append(f"{minutes}m")
    parts.append(f"{secs}s")
    return " ".join(parts)
