"""
ui/settings.py
==============
The Settings workspace, covering requirements 2 (email settings),
7 (delay/retry), 8 (campaign) and 15 (configuration).

Every value here is editable from the UI and persisted to
``config/config.json`` — users never touch ``.env`` or Python files.
"""

from __future__ import annotations

import json

import streamlit as st

from core import theme
from core.state import cfg, persist_config
from core.utils import is_valid_email
from services.config_manager import default_config


def _email_settings() -> None:
    theme.section("Sender & email settings", "2", "No .env editing required")
    s = cfg()["email_settings"]

    c1, c2 = st.columns(2)
    with c1:
        s["sender_name"] = st.text_input("Sender name", value=s.get("sender_name", ""))
        s["sender_email"] = st.text_input("Sender email", value=s.get("sender_email", ""))
        if s["sender_email"] and not is_valid_email(s["sender_email"]):
            st.warning("That sender email doesn't look valid.")
        s["organization_name"] = st.text_input(
            "Organization name", value=s.get("organization_name", "")
        )
        s["reply_to_email"] = st.text_input(
            "Reply-to email (optional)", value=s.get("reply_to_email", "")
        )
    with c2:
        s["brevo_api_key"] = st.text_input(
            "Brevo API key", value=s.get("brevo_api_key", ""), type="password",
            help="Settings → SMTP & API → API Keys in your Brevo dashboard.",
        )
        s["email_subject"] = st.text_input(
            "Email subject", value=s.get("email_subject", "")
        )
        s["campaign_name"] = st.text_input(
            "Campaign name (Brevo tag)", value=s.get("campaign_name", "")
        )

    if not s.get("brevo_api_key"):
        st.markdown(
            theme.status_badge("No API key — enable Dry run to test safely", "warning"),
            unsafe_allow_html=True,
        )


def _delay_settings() -> None:
    theme.section("Delay & retry", "7", "Respect Brevo rate limits")
    d = cfg()["delay_settings"]
    c1, c2, c3 = st.columns(3)
    with c1:
        d["delay_between_emails"] = st.number_input(
            "Delay between emails", 0.0, 3600.0,
            float(d.get("delay_between_emails", 2.0)), step=0.5,
        )
        units = ["seconds", "minutes"]
        d["delay_unit"] = st.selectbox(
            "Delay unit", units, index=units.index(d.get("delay_unit", "seconds"))
        )
    with c2:
        d["retry_count"] = st.number_input(
            "Retry count", 0, 10, int(d.get("retry_count", 3))
        )
        d["max_retry_attempts"] = st.number_input(
            "Maximum retry attempts", 0, 10, int(d.get("max_retry_attempts", 3))
        )
    with c3:
        d["retry_delay"] = st.number_input(
            "Retry delay (seconds)", 0, 600, int(d.get("retry_delay", 5))
        )


def _campaign_settings() -> None:
    theme.section("Campaign", "8", "Name your run and set batching")
    c = cfg()["campaign_settings"]
    c1, c2 = st.columns(2)
    with c1:
        c["campaign_name"] = st.text_input("Campaign name", value=c.get("campaign_name", ""))
        c["event_name"] = st.text_input("Event name", value=c.get("event_name", ""))
        c["certificate_name"] = st.text_input(
            "Certificate name", value=c.get("certificate_name", "Certificate of Participation")
        )
    with c2:
        c["batch_size"] = st.number_input(
            "Email batch size", 1, 10000, int(c.get("batch_size", 50))
        )
        modes = ["immediate", "scheduled"]
        c["sending_mode"] = st.selectbox(
            "Email sending mode", modes, index=modes.index(c.get("sending_mode", "immediate"))
        )


def _configuration() -> None:
    theme.section("Configuration", "15", "Everything lives in one JSON file")

    dry = st.toggle(
        "Dry run — generate certificates but simulate sending (no real emails)",
        value=bool(cfg().get("dry_run", True)),
    )
    cfg()["dry_run"] = dry

    c1, c2, c3 = st.columns(3)
    with c1:
        if st.button("Save configuration", type="primary", width='stretch'):
            persist_config()
            st.session_state.toast = ("Configuration saved.", "✅")
    with c2:
        st.download_button(
            "Export config (JSON)",
            data=json.dumps(cfg(), indent=2, ensure_ascii=False).encode("utf-8"),
            file_name="certificate_config.json",
            mime="application/json",
            width='stretch',
        )
    with c3:
        if st.button("Reset to defaults", width='stretch'):
            st.session_state.config = default_config()
            persist_config()
            st.session_state.toast = ("Reset to default configuration.", "↺")
            st.rerun()

    with st.expander("View raw configuration"):
        st.json(cfg())


def render() -> None:
    theme.hero("Settings", "Sender, throttling, retries and campaign — all editable")
    _email_settings()
    st.divider()
    _delay_settings()
    st.divider()
    _campaign_settings()
    st.divider()
    _configuration()
