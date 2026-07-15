"""
services/email_sender.py
========================
Sends personalized certificate emails via the Brevo (Sendinblue)
Transactional Email API, with automatic retries and configurable throttling.

Refactored from the original project. The network call, retry loop, dry-run
behaviour and throttling are preserved. What's new: the email body is now
assembled from the user-editable, section-based template with ``{{Placeholder}}``
substitution, and all sender/subject/retry values are passed in explicitly
instead of being read from module-level globals — so the UI fully controls
them and a running job is never affected by later edits.
"""

from __future__ import annotations

import base64
import logging
import re
import time
from dataclasses import dataclass, field
from datetime import date
from pathlib import Path
from typing import Dict, Optional

import requests
from services.placeholder_service import replace_placeholders

logger = logging.getLogger(__name__)

BREVO_API_URL = "https://api.brevo.com/v3/smtp/email"





class EmailSendError(Exception):
    """Raised when an email ultimately fails to send after all retries."""


@dataclass
class EmailResult:
    """Outcome of an attempt to send one participant's email."""

    success: bool
    retries: int
    error_message: str = ""


# ---------------------------------------------------------------------------
# Template rendering
# ---------------------------------------------------------------------------
def build_context(
    name: str,
    email: str,
    organization: str,
    certificate_name: str,
    extras: Optional[Dict[str, str]] = None,
) -> Dict[str, str]:
    """Assemble the placeholder-substitution context for one participant."""
    context = {
        "{{Name}}": name,
        "{{Organization}}": organization,
        "{{Email}}": email,
        "{{CertificateName}}": certificate_name,
        "{{Date}}": date.today().strftime("%B %d, %Y"),
    }
    if extras:
        context.update(extras)
    return context


def render_email_text(template: Dict[str, str], context: Dict[str, str]) -> str:
    """Produce the plain-text body of the email."""
    body = template.get("body", "")
    return replace_placeholders(body, context)


def render_email_html(template: Dict[str, str], context: Dict[str, str]) -> str:
    """Produce a lightly styled HTML body of the email."""
    body = template.get("body", "")
    content = replace_placeholders(body, context).strip()

    def esc(text: str) -> str:
        return (
            text.replace("&", "&amp;")
            .replace("<", "&lt;")
            .replace(">", "&gt;")
            .replace("\n", "<br>")
        )

    parts = ['<div style="font-family:Arial,Helvetica,sans-serif;font-size:15px;'
             'line-height:1.6;color:#1f2937;">']
    
    if content:
        parts.append(f'<p style="margin:0 0 14px 0;">{esc(content)}</p>')
        
    parts.append("</div>")
    return "".join(parts)


# ---------------------------------------------------------------------------
# Sending
# ---------------------------------------------------------------------------
def _build_payload(
    name: str,
    email: str,
    pdf_path: Path,
    email_settings: Dict[str, str],
    subject: str,
    html_body: str,
    text_body: str,
) -> dict:
    """Construct the JSON payload for the Brevo /smtp/email endpoint."""
    with open(pdf_path, "rb") as f:
        encoded_pdf = base64.b64encode(f.read()).decode("utf-8")

    payload = {
        "sender": {
            "name": email_settings.get("sender_name", ""),
            "email": email_settings.get("sender_email", ""),
        },
        "to": [{"email": email, "name": name}],
        "subject": subject,
        "htmlContent": html_body,
        "textContent": text_body,
        "attachment": [{"content": encoded_pdf, "name": Path(pdf_path).name}],
    }

    reply_to = (email_settings.get("reply_to_email") or "").strip()
    if reply_to:
        payload["replyTo"] = {"email": reply_to}

    campaign = (email_settings.get("campaign_name") or "").strip()
    if campaign:
        payload["tags"] = [campaign]

    return payload


def _send_once(payload: dict, api_key: str) -> None:
    """Attempt a single send via the Brevo API. Raises on failure."""
    if not api_key:
        raise EmailSendError("Brevo API key is not set. Add it under Settings.")

    headers = {
        "accept": "application/json",
        "api-key": api_key,
        "content-type": "application/json",
    }
    response = requests.post(BREVO_API_URL, json=payload, headers=headers, timeout=30)
    if response.status_code not in (200, 201):
        raise EmailSendError(f"Brevo API returned {response.status_code}: {response.text}")


def send_certificate_email(
    name: str,
    email: str,
    pdf_path: Path,
    email_settings: Dict[str, str],
    template: Dict[str, str],
    context: Dict[str, str],
    subject: str,
    max_retries: int,
    retry_backoff: list,
    dry_run: bool = False,
) -> EmailResult:
    """
    Send the certificate email, retrying on failure. Always returns an
    ``EmailResult`` (never raises) so the caller can keep processing the
    remaining participants regardless of outcome.
    """
    if dry_run:
        logger.info("[DRY RUN] Simulated send to %s <%s>.", name, email)
        return EmailResult(success=True, retries=0)

    subject_rendered = replace_placeholders(subject, context)
    html_body = render_email_html(template, context)
    text_body = render_email_text(template, context)
    payload = _build_payload(
        name, email, pdf_path, email_settings, subject_rendered, html_body, text_body
    )
    api_key = email_settings.get("brevo_api_key", "")

    last_error: Optional[str] = None
    for attempt in range(max_retries + 1):
        try:
            _send_once(payload, api_key)
            return EmailResult(success=True, retries=attempt)
        except Exception as exc:  # noqa: BLE001 - catch & retry everything
            last_error = str(exc)
            logger.error(
                "Attempt %d/%d failed for %s <%s>: %s",
                attempt + 1,
                max_retries + 1,
                name,
                email,
                last_error,
            )
            if attempt < max_retries:
                wait = retry_backoff[min(attempt, len(retry_backoff) - 1)]
                time.sleep(wait)

    return EmailResult(
        success=False, retries=max_retries, error_message=last_error or "Unknown error"
    )
