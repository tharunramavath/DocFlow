"""
ui/logging_panel.py
==================
The live logging panel (requirement 11). Renders the shared log buffer with
colour-coded severity, search, level filtering, and download/clear controls.

``render_log_panel`` is called both as a standalone view and from inside the
auto-refreshing monitor fragment, so it must be cheap and side-effect free
apart from the explicit buttons.
"""

from __future__ import annotations

import html

import streamlit as st

from core import theme
from services.log_manager import log_manager


def _log_html(entries) -> str:
    rows = []
    for e in entries:
        color = theme.LEVEL_COLORS.get(e.level, theme.INFO)
        icon = theme.LEVEL_ICONS.get(e.level, "•")
        who = f'<span class="who">{html.escape(e.participant)}</span> ' if e.participant else ""
        msg = html.escape(e.message)
        rows.append(
            f'<div class="row"><span class="t">{e.time_str}</span>'
            f'<span style="color:{color};flex:0 0 14px;font-weight:700;">{icon}</span>'
            f'<span class="m">{who}{msg}</span></div>'
        )
    if not rows:
        rows.append('<div class="row"><span class="m" style="color:#6B7A99;">No log entries yet.</span></div>')
    return f'<div class="cm-log">{"".join(rows)}</div>'


def render_log_panel(show_controls: bool = True, key_prefix: str = "log") -> None:
    """Render the log panel. Set ``show_controls`` False for compact embeds."""
    query = ""
    level = "all"

    if show_controls:
        c1, c2, c3, c4 = st.columns([3, 2, 1, 1])
        with c1:
            query = st.text_input(
                "Search logs", key=f"{key_prefix}_search", placeholder="Filter by name or message…",
                label_visibility="collapsed",
            )
        with c2:
            level = st.selectbox(
                "Level",
                ["all", "success", "warning", "error", "info"],
                key=f"{key_prefix}_level",
                label_visibility="collapsed",
            )
        with c3:
            st.download_button(
                "Download",
                data=log_manager.to_text().encode("utf-8"),
                file_name="campaign_logs.txt",
                mime="text/plain",
                width='stretch',
                key=f"{key_prefix}_dl",
            )
        with c4:
            if st.button("Clear", width='stretch', key=f"{key_prefix}_clear"):
                log_manager.clear()
                st.rerun()

    entries = log_manager.get_filtered(query=query, level=level)
    st.markdown(_log_html(entries), unsafe_allow_html=True)


def render() -> None:
    theme.hero("Logs", "Every step of every campaign, as it happens")
    theme.section("Live activity log", "11", f"{log_manager.count()} entries")
    render_log_panel(show_controls=True, key_prefix="standalone")
