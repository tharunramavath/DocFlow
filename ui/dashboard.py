"""
ui/dashboard.py
==============
The dashboard (requirements 12 & 13): summary cards and progress overview,
plus a setup-readiness checklist so a non-technical user always knows what's
left before they can send.

The metric/progress renderers are shared with the monitor page so the numbers
look identical everywhere.
"""

from __future__ import annotations

import streamlit as st

from core import theme
from core.state import cfg, participants
from core.utils import human_duration
from services.campaign_runner import STATUS_RUNNING, campaign_runner
from services.config_manager import resolve_path

_STATUS_KIND = {
    "idle": "info",
    "scheduled": "warning",
    "running": "info",
    "completed": "success",
    "cancelled": "warning",
    "error": "error",
}


def render_status_badge(state) -> None:
    kind = _STATUS_KIND.get(state.status, "info")
    label = state.status.capitalize()
    if state.dry_run and state.status in (STATUS_RUNNING, "scheduled"):
        label += " · Dry run"
    st.markdown(theme.status_badge(label, kind), unsafe_allow_html=True)


def render_metrics(state) -> None:
    loaded = len(participants())
    total = state.total or loaded

    row1 = st.columns(4)
    cards1 = [
        ("Participants loaded", loaded, False),
        ("Certificates generated", state.certs_generated, False),
        ("Emails sent", state.emails_sent, True),
        ("Failed", state.failed, False),
    ]
    for col, (label, value, accent) in zip(row1, cards1):
        col.markdown(theme.stat_card(label, value, accent), unsafe_allow_html=True)

    row2 = st.columns(4)
    cards2 = [
        ("Remaining", state.remaining if state.total else max(0, loaded - state.processed), False),
        ("Elapsed", human_duration(state.elapsed_seconds), False),
        ("Est. remaining", human_duration(state.eta_seconds) if state.eta_seconds else "—", False),
        ("Success rate", f"{state.success_rate:.0f}%", True),
    ]
    for col, (label, value, accent) in zip(row2, cards2):
        col.markdown(theme.stat_card(label, value, accent), unsafe_allow_html=True)


def render_progress(state) -> None:
    pct = state.percent / 100.0
    st.progress(pct, text=f"Overall progress — {state.percent:.0f}%")
    if state.status == STATUS_RUNNING and state.current_name:
        st.caption(
            f"Now processing #{state.current_index} of {state.total} — "
            f"**{state.current_name}** ({state.current_email})"
        )


def _readiness() -> None:
    theme.section("Setup checklist", "", "What's left before you can send")
    c = cfg()
    template_ok = resolve_path(c.get("certificate_template", "")).exists()
    checks = [
        (bool(participants()), f"Participants loaded ({len(participants())})", "Upload an Excel file under Data & Template"),
        (template_ok, "Certificate template selected", "Upload a template under Data & Template"),
        (bool(c["email_settings"].get("sender_email")), "Sender email set", "Add it under Settings"),
        (bool(c["email_settings"].get("organization_name")), "Organization set", "Add it under Settings"),
        (
            bool(c["email_settings"].get("brevo_api_key")) or bool(c.get("dry_run")),
            "API key set or Dry run enabled",
            "Add a Brevo key under Settings, or enable Dry run",
        ),
    ]
    
    from services.placeholder_service import extract_placeholders
    subject_val = c["email_settings"].get("email_subject", "")
    body_val = c["email_template"].get("body", "")
    detected_vars = extract_placeholders(subject_val, body_val)
    mapping = c["column_mapping"].get("extra_fields", {})
    missing_vars = [p for p in detected_vars if not mapping.get(p)]
    
    checks.append(
        (len(missing_vars) == 0, "All placeholders mapped", f"Map missing fields ({len(missing_vars)}) in Email Template")
    )
    
    for ok, label, hint in checks:
        icon = "✅" if ok else "⬜"
        tail = "" if ok else f" — <span style='color:{theme.MUTED}'>{hint}</span>"
        st.markdown(f"{icon} {label}{tail}", unsafe_allow_html=True)


def render() -> None:
    theme.hero("Dashboard", "Your campaign at a glance")
    state = campaign_runner.state.snapshot()

    top = st.columns([3, 1])
    with top[0]:
        theme.section("Campaign summary", "12", "")
    with top[1]:
        st.write("")
        render_status_badge(state)

    render_metrics(state)
    st.write("")
    theme.section("Progress", "13", "")
    render_progress(state)

    st.divider()
    _readiness()

    if state.status == "idle":
        st.info("Head to **Send & Monitor** when you're ready to start a campaign.")
