"""
core/state.py
=============
Bridges Streamlit's per-session state with the on-disk configuration and the
process-level singletons (log manager, campaign runner).

Streamlit re-runs the whole script on every interaction, so this module
centralises "load once, keep in session_state" bootstrapping and provides
tiny typed accessors the UI can use without repeating boilerplate.
"""

from __future__ import annotations

from typing import Dict, List

import streamlit as st

from services.config_manager import load_config, save_config
from services.excel_reader import Participant


def init_session() -> None:
    """Initialise session state on first load of a session."""
    if "config" not in st.session_state:
        st.session_state.config = load_config()
    if "page" not in st.session_state:
        st.session_state.page = "Dashboard"
    if "participants" not in st.session_state:
        st.session_state.participants: List[Participant] = []
    if "participants_source" not in st.session_state:
        st.session_state.participants_source = ""
    if "excel_df" not in st.session_state:
        st.session_state.excel_df = None
    if "active_preset" not in st.session_state:
        st.session_state.active_preset = "Default Template"
    if "toast" not in st.session_state:
        st.session_state.toast = None
    if "detected_placeholders" not in st.session_state:
        st.session_state.detected_placeholders = []


def cfg() -> Dict:
    """Return the live, editable session configuration dictionary."""
    return st.session_state.config


def persist_config() -> None:
    """Write the current session config to disk (last-used config)."""
    save_config(st.session_state.config)


def set_config(new_config: Dict) -> None:
    """Replace the whole session config (e.g. after loading a preset)."""
    st.session_state.config = new_config


def participants() -> List[Participant]:
    return st.session_state.get("participants", [])


def set_participants(items: List[Participant], source: str = "") -> None:
    st.session_state.participants = items
    st.session_state.participants_source = source


def queue_toast(message: str, icon: str = "✅") -> None:
    """Stash a toast to show after the next rerun."""
    st.session_state.toast = (message, icon)


def flush_toast() -> None:
    """Render any queued toast, then clear it."""
    toast = st.session_state.get("toast")
    if toast:
        st.toast(toast[0], icon=toast[1])
        st.session_state.toast = None
