from __future__ import annotations
"""
Hydraulic Filter Platform — Email Utilities
========================================
SMTP email sending for verification, follow-up notifications,
and knowledge base update alerts.

Configuration via environment variables:
    SMTP_HOST       — SMTP server hostname (default: smtp.gmail.com)
    SMTP_PORT       — SMTP server port (default: 587)
    SMTP_USER       — SMTP username / email
    SMTP_PASSWORD   — SMTP password or app password
    SMTP_FROM_ADDRESS — "From" address (defaults to SMTP_USER)
    BASE_URL        — Public base URL for verification links
"""

import logging
import os
import smtplib
from email.mime.multipart import MIMEMultipart
from email.mime.text import MIMEText

logger = logging.getLogger(__name__)

# ---------------------------------------------------------------------------
# Configuration
# ---------------------------------------------------------------------------

SMTP_HOST = os.getenv("SMTP_HOST", "smtp.gmail.com")
SMTP_PORT = int(os.getenv("SMTP_PORT", "587"))
SMTP_USER = os.getenv("SMTP_USER", "")
SMTP_PASSWORD = os.getenv("SMTP_PASSWORD", "")
SMTP_FROM_ADDRESS = os.getenv("SMTP_FROM_ADDRESS", "") or SMTP_USER
BASE_URL = os.getenv("BASE_URL", "http://localhost:8000")


def is_email_configured() -> bool:
    """Check if SMTP credentials are configured."""
    return bool(SMTP_USER and SMTP_PASSWORD)


# ---------------------------------------------------------------------------
# Low-level send
# ---------------------------------------------------------------------------

def _send_email(to: str, subject: str, html_body: str, text_body: str = "") -> bool:
    """Send an email via SMTP. Returns True on success, False on failure."""
    if not is_email_configured():
        logger.warning("[email] SMTP not configured — skipping email send")
        return False

    msg = MIMEMultipart("alternative")
    msg["From"] = SMTP_FROM_ADDRESS
    msg["To"] = to
    msg["Subject"] = subject

    if text_body:
        msg.attach(MIMEText(text_body, "plain"))
    msg.attach(MIMEText(html_body, "html"))

    try:
        with smtplib.SMTP(SMTP_HOST, SMTP_PORT, timeout=30) as server:
            server.starttls()
            server.login(SMTP_USER, SMTP_PASSWORD)
            server.sendmail(SMTP_FROM_ADDRESS, to, msg.as_string())
        logger.info(f"[email] Sent to {to}: {subject}")
        return True
    except Exception as e:
        logger.error(f"[email] Failed to send to {to}: {e}")
        return False


# ---------------------------------------------------------------------------
# Email templates
# ---------------------------------------------------------------------------

def send_auth_code(email: str, code: str) -> bool:
    """Send a 6-digit verification code for passwordless login."""
    subject = "Your FilterOracle verification code"

    html_body = f"""
    <div style="font-family: -apple-system, BlinkMacSystemFont, 'Segoe UI', Roboto, sans-serif; max-width: 500px; margin: 0 auto; padding: 20px;">
        <p style="color: #555; font-size: 14px;">Your FilterOracle verification code is:</p>
        <div style="text-align: center; margin: 24px 0;">
            <span style="font-size: 32px; font-weight: bold; letter-spacing: 8px; color: #1e3a5f;
                         background: #f1f5f9; padding: 16px 32px; border-radius: 8px; display: inline-block;">
                {code}
            </span>
        </div>
        <p style="color: #555; font-size: 14px;">This code expires in 10 minutes.</p>
        <p style="color: #888; font-size: 12px; margin-top: 24px;">
            If you didn't request this code, you can safely ignore this email.
        </p>
        <p style="color: #aaa; font-size: 11px;">&mdash; FilterOracle</p>
    </div>
    """

    text_body = f"""Your FilterOracle verification code is: {code}

This code expires in 10 minutes.

If you didn't request this code, you can safely ignore this email.

-- FilterOracle
"""

    return _send_email(email, subject, html_body, text_body)


def send_verification_email(
    email: str,
    verification_token: str,
    session_title: str,
    unsubscribe_token: str,
) -> bool:
    """Send a verification email to a new subscriber."""
    verify_url = f"{BASE_URL}/api/consult/subscribe/verify?token={verification_token}"
    unsubscribe_url = f"{BASE_URL}/api/consult/subscribe/unsubscribe?token={unsubscribe_token}"

    subject = f"Verify your subscription — {session_title}"

    html_body = f"""
    <div style="font-family: -apple-system, BlinkMacSystemFont, 'Segoe UI', Roboto, sans-serif; max-width: 600px; margin: 0 auto; padding: 20px;">
        <h2 style="color: #1e3a5f; margin-bottom: 8px;">Hydraulic Filter Expert Platform</h2>
        <p style="color: #555; font-size: 14px;">
            Thanks for subscribing to updates for your consultation: <strong>{session_title}</strong>
        </p>
        <p style="color: #555; font-size: 14px;">
            Please verify your email address by clicking the button below:
        </p>
        <div style="text-align: center; margin: 30px 0;">
            <a href="{verify_url}"
               style="background-color: #2563eb; color: white; padding: 12px 32px;
                      text-decoration: none; border-radius: 6px; font-weight: 600;
                      font-size: 14px; display: inline-block;">
                Verify Email Address
            </a>
        </div>
        <p style="color: #888; font-size: 12px;">
            Once verified, we'll notify you when:
        </p>
        <ul style="color: #888; font-size: 12px; padding-left: 20px;">
            <li>New technical data is added to the knowledge base that's relevant to your consultation</li>
            <li>It's time for a follow-up on your implementation results</li>
        </ul>
        <hr style="border: none; border-top: 1px solid #eee; margin: 24px 0;" />
        <p style="color: #aaa; font-size: 11px;">
            If you didn't request this, you can safely ignore this email.
            <br/>
            <a href="{unsubscribe_url}" style="color: #aaa;">Unsubscribe</a>
        </p>
    </div>
    """

    text_body = f"""Hydraulic Filter Expert Platform

Thanks for subscribing to updates for: {session_title}

Verify your email: {verify_url}

Once verified, we'll notify you when relevant technical data is added
or when it's time for a follow-up on your implementation.

Unsubscribe: {unsubscribe_url}
"""

    return _send_email(email, subject, html_body, text_body)


def send_followup_reminder(
    email: str,
    session_title: str,
    followup_stage: str,
    session_id: str,
    unsubscribe_token: str,
) -> bool:
    """Send a follow-up outcome reminder to a subscriber."""
    outcome_url = f"{BASE_URL}/consult?session={session_id}"
    unsubscribe_url = f"{BASE_URL}/api/consult/subscribe/unsubscribe?token={unsubscribe_token}"

    stage_label = followup_stage.replace("_", " ").title()
    subject = f"{stage_label} Follow-up — {session_title}"

    html_body = f"""
    <div style="font-family: -apple-system, BlinkMacSystemFont, 'Segoe UI', Roboto, sans-serif; max-width: 600px; margin: 0 auto; padding: 20px;">
        <h2 style="color: #1e3a5f; margin-bottom: 8px;">Hydraulic Filter Expert Platform</h2>
        <p style="color: #555; font-size: 14px;">
            It's time for your <strong>{stage_label.lower()}</strong> follow-up on: <strong>{session_title}</strong>
        </p>
        <p style="color: #555; font-size: 14px;">
            How did the recommendation work out? Your feedback helps us improve
            future recommendations for all engineers.
        </p>
        <div style="text-align: center; margin: 30px 0;">
            <a href="{outcome_url}"
               style="background-color: #2563eb; color: white; padding: 12px 32px;
                      text-decoration: none; border-radius: 6px; font-weight: 600;
                      font-size: 14px; display: inline-block;">
                Report Your Results
            </a>
        </div>
        <hr style="border: none; border-top: 1px solid #eee; margin: 24px 0;" />
        <p style="color: #aaa; font-size: 11px;">
            <a href="{unsubscribe_url}" style="color: #aaa;">Unsubscribe from future emails</a>
        </p>
    </div>
    """

    text_body = f"""Hydraulic Filter Expert Platform

{stage_label} Follow-up: {session_title}

How did the recommendation work out? Report your results:
{outcome_url}

Unsubscribe: {unsubscribe_url}
"""

    return _send_email(email, subject, html_body, text_body)


def send_knowledge_update_notification(
    email: str,
    update_title: str,
    update_description: str,
    session_title: str,
    unsubscribe_token: str,
) -> bool:
    """Notify a subscriber about a relevant knowledge base update."""
    unsubscribe_url = f"{BASE_URL}/api/consult/subscribe/unsubscribe?token={unsubscribe_token}"

    subject = f"New data available — {update_title}"

    html_body = f"""
    <div style="font-family: -apple-system, BlinkMacSystemFont, 'Segoe UI', Roboto, sans-serif; max-width: 600px; margin: 0 auto; padding: 20px;">
        <h2 style="color: #1e3a5f; margin-bottom: 8px;">Hydraulic Filter Expert Platform</h2>
        <p style="color: #555; font-size: 14px;">
            New technical data has been added to the knowledge base that may be relevant
            to your consultation: <strong>{session_title}</strong>
        </p>
        <div style="background: #f8fafc; border: 1px solid #e2e8f0; border-radius: 8px; padding: 16px; margin: 16px 0;">
            <h3 style="color: #1e3a5f; margin: 0 0 8px 0; font-size: 15px;">{update_title}</h3>
            <p style="color: #555; font-size: 13px; margin: 0;">{update_description}</p>
        </div>
        <p style="color: #555; font-size: 14px;">
            You may want to start a new consultation to get updated recommendations
            based on the latest data.
        </p>
        <hr style="border: none; border-top: 1px solid #eee; margin: 24px 0;" />
        <p style="color: #aaa; font-size: 11px;">
            You received this because you subscribed after your consultation on "{session_title}".
            <br/>
            <a href="{unsubscribe_url}" style="color: #aaa;">Unsubscribe</a>
        </p>
    </div>
    """

    text_body = f"""Hydraulic Filter Expert Platform

New data available: {update_title}

{update_description}

This may be relevant to your consultation: {session_title}

Unsubscribe: {unsubscribe_url}
"""

    return _send_email(email, subject, html_body, text_body)
