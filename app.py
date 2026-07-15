"""
app.py
======
Entry point for the Certificate Studio Streamlit application.

Run with:

    streamlit run app.py

This file wires together the modular UI (``ui/*``) and services
(``services/*``). All business logic — certificate generation, Brevo
sending, retries, throttling, Excel loading, CSV logging — is reused and
refactored from the original command-line project; nothing here needs to be
edited to run a campaign.
"""

from __future__ import annotations

import streamlit as st

from core.state import cfg, flush_toast, init_session
from core.theme import BRASS_DEEP, INK, inject_theme, status_badge
from services.campaign_runner import campaign_runner
from ui import (
    dashboard,
    email_editor,
    logging_panel,
    presets_panel,
    scheduler,
    settings,
    template_manager,
)

st.set_page_config(
    page_title="Certificate Studio",
    page_icon="🎓",
    layout="wide",
    initial_sidebar_state="expanded",
)

inject_theme()
init_session()

PAGES = {
    "Dashboard": ("🏠", dashboard.render),
    "Data & Template": ("🗂️", template_manager.render),
    "Email Template": ("✉️", email_editor.render),
    "Settings": ("⚙️", settings.render),
    "Presets": ("📌", presets_panel.render),
    "Send & Monitor": ("🚀", scheduler.render),
    "Logs": ("📜", logging_panel.render),
}


def _sidebar() -> str:
    with st.sidebar:
        st.markdown(
            f"""
            <div style="display:flex;align-items:center;gap:12px;padding:6px 2px 14px 2px;">
              <div class="cm-seal">✦</div>
              <div>
                <div style="font-family:'Fraunces',serif;font-weight:700;font-size:20px;color:{INK};">Certificate Studio</div>
                <div style="font-size:11px;letter-spacing:.14em;text-transform:uppercase;color:{BRASS_DEEP};">Generate · Send · Track</div>
              </div>
            </div>
            """,
            unsafe_allow_html=True,
        )

        labels = [f"{icon}  {name}" for name, (icon, _) in PAGES.items()]
        names = list(PAGES.keys())
        default_idx = names.index(st.session_state.get("page", "Dashboard"))
        choice = st.radio(
            "Navigation", labels, index=default_idx, label_visibility="collapsed"
        )
        selected = names[labels.index(choice)]
        st.session_state.page = selected

        st.divider()

        # Live status + mode at a glance
        state = campaign_runner.state.snapshot()
        kind = {
            "idle": "info",
            "scheduled": "warning",
            "running": "info",
            "completed": "success",
            "cancelled": "warning",
            "error": "error",
        }.get(state.status, "info")
        st.markdown("**Campaign status**")
        st.markdown(status_badge(state.status.capitalize(), kind), unsafe_allow_html=True)
        if state.is_active:
            st.progress(state.percent / 100.0, text=f"{state.percent:.0f}%")

        mode = "Dry run" if cfg().get("dry_run", False) else "Live send"
        st.caption(f"Mode: **{mode}**")
        st.caption(f"Active preset: **{st.session_state.get('active_preset','Default Template')}**")

        st.divider()
        st.caption("A workflow, not a script — no code required.")

    return selected


def main() -> None:
    flush_toast()
    selected = _sidebar()
    _, render_fn = PAGES[selected]
    render_fn()


if __name__ == "__main__":
    main()
