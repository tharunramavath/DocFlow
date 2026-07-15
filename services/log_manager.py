"""
services/log_manager.py
=======================
A small, thread-safe, in-memory log store that the background campaign
worker writes to and the Streamlit UI reads from.

Every entry carries a severity level so the UI can colour-code it:

    success  -> green
    warning  -> yellow
    error    -> red
    info     -> blue

The store is a process-level singleton (``log_manager``) so that the
background sending thread and the Streamlit script — which re-runs on every
interaction — always see the same buffer.
"""

from __future__ import annotations

import threading
from dataclasses import dataclass, field
from datetime import datetime
from typing import List

LEVEL_SUCCESS = "success"
LEVEL_WARNING = "warning"
LEVEL_ERROR = "error"
LEVEL_INFO = "info"

_VALID_LEVELS = {LEVEL_SUCCESS, LEVEL_WARNING, LEVEL_ERROR, LEVEL_INFO}


@dataclass
class LogEntry:
    """One line in the live log panel."""

    timestamp: datetime
    level: str
    message: str
    participant: str = ""

    @property
    def time_str(self) -> str:
        return self.timestamp.strftime("%H:%M:%S")

    def as_text(self) -> str:
        who = f" | {self.participant}" if self.participant else ""
        return f"[{self.timestamp:%Y-%m-%d %H:%M:%S}] {self.level.upper():7}{who} | {self.message}"


class LogManager:
    """Thread-safe append-only log buffer with search/export helpers."""

    def __init__(self, max_entries: int = 5000) -> None:
        self._entries: List[LogEntry] = []
        self._lock = threading.Lock()
        self._max_entries = max_entries

    # -- writing -------------------------------------------------------
    def add(self, level: str, message: str, participant: str = "") -> None:
        level = level if level in _VALID_LEVELS else LEVEL_INFO
        entry = LogEntry(
            timestamp=datetime.now(),
            level=level,
            message=message,
            participant=participant,
        )
        with self._lock:
            self._entries.append(entry)
            # Keep memory bounded on very large runs.
            if len(self._entries) > self._max_entries:
                self._entries = self._entries[-self._max_entries :]

    def info(self, message: str, participant: str = "") -> None:
        self.add(LEVEL_INFO, message, participant)

    def success(self, message: str, participant: str = "") -> None:
        self.add(LEVEL_SUCCESS, message, participant)

    def warning(self, message: str, participant: str = "") -> None:
        self.add(LEVEL_WARNING, message, participant)

    def error(self, message: str, participant: str = "") -> None:
        self.add(LEVEL_ERROR, message, participant)

    # -- reading -------------------------------------------------------
    def get_all(self) -> List[LogEntry]:
        with self._lock:
            return list(self._entries)

    def get_filtered(self, query: str = "", level: str = "all") -> List[LogEntry]:
        query = (query or "").strip().lower()
        entries = self.get_all()
        if level and level != "all":
            entries = [e for e in entries if e.level == level]
        if query:
            entries = [
                e
                for e in entries
                if query in e.message.lower() or query in e.participant.lower()
            ]
        return entries

    def count(self) -> int:
        with self._lock:
            return len(self._entries)

    def to_text(self) -> str:
        return "\n".join(e.as_text() for e in self.get_all())

    def clear(self) -> None:
        with self._lock:
            self._entries.clear()


# Process-level singleton shared across Streamlit re-runs and the worker thread.
log_manager = LogManager()
