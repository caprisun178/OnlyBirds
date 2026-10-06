"""Outbound email — raw SMTP only, no business logic.

Used for the beta "Report a problem" button (see app/services/feedback.py).
No provider SDK — one plain-text message to one inbox doesn't need one.
"""

from __future__ import annotations

import asyncio
import smtplib
from email.message import EmailMessage

from app.config import get_settings


class EmailNotConfigured(RuntimeError):
    """Raised when SMTP_HOST / SMTP_USER / SMTP_PASSWORD / REPORT_EMAIL_TO aren't set."""


class EmailSendFailed(RuntimeError):
    """Raised when the vars are set but the actual SMTP send fails (bad
    credentials, wrong host/port, the provider rejecting the login, ...).
    Wraps the real smtplib/socket exception's message so it reaches the
    router as a clean error instead of leaking out as an unhandled 500."""


def is_configured() -> bool:
    settings = get_settings()
    return bool(
        settings.smtp_host
        and settings.smtp_user
        and settings.smtp_password
        and settings.report_email_to
    )


async def send_email(subject: str, body: str) -> None:
    settings = get_settings()
    if not is_configured():
        raise EmailNotConfigured(
            "SMTP_HOST / SMTP_USER / SMTP_PASSWORD / REPORT_EMAIL_TO are not set."
        )

    message = EmailMessage()
    message["Subject"] = subject
    message["From"] = settings.smtp_user
    message["To"] = settings.report_email_to
    message.set_content(body)

    # smtplib is blocking — off the event loop so one slow send doesn't
    # stall every other request this worker is handling.
    try:
        await asyncio.to_thread(_send_sync, message)
    except (smtplib.SMTPException, OSError) as exc:
        raise EmailSendFailed(f"Could not send email via {settings.smtp_host}: {exc}") from exc


def _send_sync(message: EmailMessage) -> None:
    settings = get_settings()
    with smtplib.SMTP(settings.smtp_host, settings.smtp_port, timeout=settings.http_timeout_seconds) as smtp:
        smtp.starttls()
        smtp.login(settings.smtp_user, settings.smtp_password)
        smtp.send_message(message)
