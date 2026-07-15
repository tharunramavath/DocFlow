"""
ui/scheduler.py
==============
The "Send & Monitor" workspace — the operational heart of the app. It brings
together the scheduler (requirement 9), live progress (13), the dashboard
metrics (12) and the live log (11).

Sending always runs on a background thread (see services.campaign_runner), so
this page stays responsive. While a campaign is active, a fragment auto-
refreshes once a second to stream progress and logs; when idle it stays
still so the operator can read and search comfortably.
"""

from __future__ import annotations

import datetime as dt
import time

import pytz
import streamlit as st

from core import theme
from core.state import cfg, participants
from core.utils import human_duration
from services.campaign_runner import (
    STATUS_COMPLETED,
    STATUS_ERROR,
    STATUS_SCHEDULED,
    campaign_runner,
)
from services.config_manager import resolve_path
from ui.dashboard import render_metrics, render_progress, render_status_badge
from ui.logging_panel import render_log_panel


# --------------------------------------------------------------------------
# Pre-flight validation
# --------------------------------------------------------------------------
def _preflight():
    c = cfg()
    problems = []
    if not participants():
        problems.append("No participants loaded — go to Data & Template.")
    if not resolve_path(c.get("certificate_template", "")).exists():
        problems.append("No certificate template selected.")
    if not c.get("dry_run", False):
        if not c["email_settings"].get("brevo_api_key"):
            problems.append("Brevo API key missing (or enable Dry run).")
        if not c["email_settings"].get("sender_email"):
            problems.append("Sender email missing.")
            
    from services.placeholder_service import extract_placeholders
    subject_val = c["email_settings"].get("email_subject", "")
    body_val = c["email_template"].get("body", "")
    detected_vars = extract_placeholders(subject_val, body_val)
    mapping = c["column_mapping"].get("extra_fields", {})
    missing_vars = [p for p in detected_vars if not mapping.get(p)]
    if missing_vars:
        problems.append(f"Missing placeholder mappings: {', '.join(missing_vars)}. Fix in Email Template.")
        
    return problems


def _scheduled_epoch() -> float | None:
    sch = cfg()["scheduler"]
    try:
        tz = pytz.timezone(sch.get("timezone", "UTC"))
    except Exception:  # noqa: BLE001
        tz = pytz.UTC
    date_val = st.session_state.get("_sched_date")
    time_val = st.session_state.get("_sched_time")
    if not date_val or not time_val:
        return None
    naive = dt.datetime.combine(date_val, time_val)
    local = tz.localize(naive)
    return local.timestamp()


# --------------------------------------------------------------------------
# Launch controls (static section — only shown when not active)
# --------------------------------------------------------------------------
def _launch_controls() -> None:
    c = cfg()
    theme.section("Prepare to send", "9", "Immediate or scheduled")

    problems = _preflight()
    if problems:
        for p in problems:
            st.markdown(theme.status_badge(p, "error"), unsafe_allow_html=True)

    campaign = c["campaign_settings"]
    modes = ["immediate", "scheduled"]
    mode = st.radio(
        "Sending mode",
        modes,
        index=modes.index(campaign.get("sending_mode", "immediate")),
        horizontal=True,
    )
    campaign["sending_mode"] = mode

    scheduled_for = None
    if mode == "scheduled":
        sch = c["scheduler"]
        s1, s2, s3 = st.columns(3)
        with s1:
            st.session_state["_sched_date"] = st.date_input(
                "Date", value=dt.date.today(), min_value=dt.date.today()
            )
        with s2:
            st.session_state["_sched_time"] = st.time_input(
                "Time", value=dt.time(9, 0)
            )
        with s3:
            tzs = pytz.common_timezones
            tz_idx = tzs.index(sch.get("timezone", "UTC")) if sch.get("timezone") in tzs else tzs.index("UTC")
            sch["timezone"] = st.selectbox("Timezone", tzs, index=tz_idx)

        scheduled_for = _scheduled_epoch()
        if scheduled_for:
            when = dt.datetime.fromtimestamp(scheduled_for).strftime("%a %d %b %Y, %H:%M")
            delta = scheduled_for - time.time()
            if delta <= 0:
                st.warning("That time is in the past — pick a future time.")
            else:
                st.caption(f"Will start at **{when}** (in {human_duration(delta)}).")

    dry = c.get("dry_run", False)
    ready = not problems and (mode == "immediate" or (scheduled_for and scheduled_for > time.time()))

    label = "Schedule campaign" if mode == "scheduled" else "Start sending now"
    if dry:
        label += " (Dry run)"

    if st.button(label, type="primary", disabled=not ready, width='stretch'):
        campaign_runner.start(
            participants=participants(),
            config=c,
            scheduled_for=scheduled_for if mode == "scheduled" else None,
        )
        st.session_state.toast = ("Campaign started.", "🚀")
        st.rerun()


# --------------------------------------------------------------------------
# Live monitor (fragment — auto-refreshes only while active)
# --------------------------------------------------------------------------
def _monitor_body() -> None:
    state = campaign_runner.state.snapshot()

    head = st.columns([3, 1])
    with head[0]:
        theme.section("Live monitor", "", "")
    with head[1]:
        st.write("")
        render_status_badge(state)

    if state.status == STATUS_SCHEDULED:
        st.info(
            f"⏳ Scheduled — starting in **{human_duration(state.countdown_seconds)}**"
        )

    render_metrics(state)
    st.write("")
    render_progress(state)

    if state.is_active:
        if st.button("Cancel campaign", key="cancel_btn"):
            campaign_runner.cancel()
            st.session_state.toast = ("Cancellation requested.", "🛑")
            st.rerun()

    if state.status == STATUS_COMPLETED:
        st.success(
            f"Done — {state.emails_sent} sent, {state.failed} failed of {state.total} "
            f"in {human_duration(state.elapsed_seconds)}."
        )
        if state.csv_log_path:
            try:
                with open(state.csv_log_path, "rb") as f:
                    st.download_button(
                        "Download results (CSV)",
                        data=f.read(),
                        file_name="mail_log.csv",
                        mime="text/csv",
                    )
            except OSError:
                pass
    elif state.status == STATUS_ERROR:
        st.error(f"Campaign ended with an error: {state.error_message}")

    st.divider()
    theme.section("Live log", "11", f"{campaign_runner.state.snapshot().processed} processed")
    render_log_panel(show_controls=True, key_prefix="monitor")


def render() -> None:
    theme.hero("Send & Monitor", "Launch the campaign and watch it run")

    state = campaign_runner.state.snapshot()
    active = state.is_active

    if not active:
        _launch_controls()
        st.divider()

    # Auto-refresh the monitor only while a campaign is active.
    interval = "1s" if active else None
    fragment = st.fragment(run_every=interval)(_monitor_body)
    fragment()
