"""
ui/email_editor.py
==================
Rich, section-based email editor with a live preview (requirement 3).

The user edits each part of the email separately (greeting, body, thank-you,
future invitation, regards, signature, footer) and can drop placeholders like
``{{Name}}`` anywhere. The preview renders exactly what a real recipient would
receive, using the first loaded participant (or sample data) as context.
"""

from __future__ import annotations

import streamlit as st

from core import theme
from core.state import cfg, participants, persist_config
from services import excel_reader
from services.email_sender import build_context, render_email_html
from services.placeholder_service import extract_placeholders, auto_map_placeholders, replace_placeholders


def _preview_context() -> dict:
    email_settings = cfg()["email_settings"]
    campaign = cfg()["campaign_settings"]
    people = participants()
    if people:
        p = people[0]
        name, email, extras = p.name, p.email, p.extras
    else:
        # Dummy data for preview if no Excel loaded
        name = "John Doe"
        email = "john@example.com"
        extras = {
            "{{Name}}": "John Doe",
            "{{Email}}": "john@example.com",
            "{{Organization}}": email_settings.get("organization_name", "ABC Pvt Ltd"),
            "{{CertificateName}}": campaign.get("certificate_name", "Certificate of Participation"),
            "{{College}}": "XYZ University",
            "{{Department}}": "Computer Science",
            "{{Phone}}": "+1 234 567 890",
        }
    return build_context(
        name=name,
        email=email,
        organization=email_settings.get("organization_name", "Our Team"),
        certificate_name=campaign.get("certificate_name", "Certificate of Participation"),
        extras=extras,
    )


def render() -> None:
    theme.hero("Email Template", "Craft the message that carries each certificate")

    template = cfg()["email_template"]
    email_settings = cfg()["email_settings"]

    editor, preview = st.columns([1, 1], gap="large")

    with editor:
        theme.section("Compose", "", "")
        
        subject_val = st.text_input(
            "Subject line", 
            value=email_settings.get("email_subject", "")
        )
        
        body_val = st.text_area(
            "Email body",
            value=template.get("body", ""),
            height=300
        )

        if subject_val != email_settings.get("email_subject", "") or body_val != template.get("body", ""):
            cfg()["email_settings"]["email_subject"] = subject_val
            cfg()["email_template"]["body"] = body_val
            persist_config()

        # Placeholders and mapping logic
        detected_vars = extract_placeholders(subject_val, body_val)
        st.session_state.detected_placeholders = detected_vars
        
        df = st.session_state.get("excel_df")
        columns = excel_reader.get_columns(df) if df is not None else []
        
        mapping = cfg()["column_mapping"]
        ph_mapping = mapping.get("extra_fields", {})
        
        # We process ALL detected variables.
        auto_mapped = auto_map_placeholders(detected_vars, columns)
        
        updated_mapping = {}
        for p in detected_vars:
            if p in ph_mapping and ph_mapping[p]:
                updated_mapping[p] = ph_mapping[p]
            elif p in auto_mapped:
                updated_mapping[p] = auto_mapped[p]
            else:
                updated_mapping[p] = ""
                
        mapping["extra_fields"] = updated_mapping
        
        # Check if anything changed in mapping that requires save
        if updated_mapping != ph_mapping:
            persist_config()
            
        st.divider()
        
        if df is not None:
            st.markdown("**Detected columns**")
            st.caption(", ".join(columns))
            st.write("")
        
        st.markdown("**Detected placeholders**")
        if detected_vars:
            st.caption(", ".join(detected_vars))
        else:
            st.caption("None")
        st.write("")
            
        mapped_vars = [p for p in detected_vars if updated_mapping[p]]
        missing_vars = [p for p in detected_vars if not updated_mapping[p]]
        
        if mapped_vars:
            st.markdown("**Auto mapped**")
            for p in mapped_vars:
                st.markdown(f'<span style="color: green;">✓ {p} → {updated_mapping[p]}</span>', unsafe_allow_html=True)
            st.write("")
            
        if missing_vars:
            st.markdown("**Missing**")
            for p in missing_vars:
                st.markdown(f'<span style="color: red;">⚠ {p}</span>', unsafe_allow_html=True)
                
                opts = [""] + columns
                idx = 0
                new_col = st.selectbox(
                    f"Select Excel Column for {p}",
                    opts,
                    index=idx,
                    key=f"map_{p}",
                    label_visibility="collapsed"
                )
                if new_col:
                    mapping["extra_fields"][p] = new_col
                    persist_config()
                    st.rerun()

    with preview:
        theme.section("Live preview", "", "As the recipient sees it")
        context = _preview_context()
        
        # If previewing mock data, fill any unmapped missing vars with mock data to avoid raw placeholders
        for p in missing_vars:
            if p not in context:
                context[p] = f"[Mock {p.strip('{} ')}]"

        subject = replace_placeholders(subject_val, context)
        html_body = render_email_html({"body": body_val}, context)

        who = context.get("{{Name}}", context.get("Name", "John Doe"))
        who_email = context.get("{{Email}}", context.get("Email", "john@example.com"))
        sender = email_settings.get("sender_name") or "Your Organization"
        sender_email = email_settings.get("sender_email") or "sender@example.com"
        
        card = f"""
        <div style="border:1px solid #e0e0e0;border-radius:8px;overflow:hidden;
                    font-family:'Segoe UI',Roboto,Helvetica,Arial,sans-serif;background:#fff;
                    box-shadow: 0 1px 3px rgba(0,0,0,0.1);">
          <div style="background:#f9f9f9;border-bottom:1px solid #e0e0e0;padding:16px 20px;">
            <div style="font-size:14px;color:#222;margin-bottom:4px;">
                <strong>From:</strong> {sender} &lt;{sender_email}&gt;
            </div>
            <div style="font-size:14px;color:#222;margin-bottom:8px;">
                <strong>To:</strong> {who} &lt;{who_email}&gt;
            </div>
            <div style="font-size:18px;font-weight:600;color:#111;margin-top:12px;">
                <strong>Subject:</strong> {subject or "(no subject)"}
            </div>
          </div>
          <div style="padding:24px 20px;color:#333;font-size:15px;line-height:1.6;">
            {html_body}
          </div>
          <div style="background:#f1f3f4;border-top:1px solid #e0e0e0;padding:12px 20px;font-size:13px;color:#5f6368;display:flex;align-items:center;">
            <span style="background:#e8eaed;padding:6px 12px;border-radius:16px;border:1px solid #dadce0;">
                📎 {cfg()["campaign_settings"].get("certificate_name","Certificate")}.pdf
            </span>
          </div>
        </div>
        """
        st.html(card)
