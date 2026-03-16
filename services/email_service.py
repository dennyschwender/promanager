"""services/email_service.py — SMTP email helpers using stdlib only."""

from __future__ import annotations

import logging
import smtplib
from email.mime.multipart import MIMEMultipart
from email.mime.text import MIMEText

from app.config import settings
from app.i18n import t as _t

logger = logging.getLogger(__name__)

# ---------------------------------------------------------------------------
# Core send function
# ---------------------------------------------------------------------------


def _is_dev_mode() -> bool:
    """Return True when SMTP is unconfigured (dev / no-op mode)."""
    host = settings.SMTP_HOST.strip()
    return not host or host in ("localhost", "127.0.0.1") and not settings.SMTP_USER


def send_email(to: str, subject: str, body_html: str, body_text: str = "") -> bool:
    """Send a single email via SMTP.

    Returns True on success (or in dev no-op mode), False on failure.
    """
    if _is_dev_mode():
        logger.debug(
            "Email (dev no-op) to=%r subject=%r body_text=%r",
            to,
            subject,
            body_text or body_html[:120],
        )
        return True

    msg = MIMEMultipart("alternative")
    msg["Subject"] = subject
    msg["From"] = settings.SMTP_FROM
    msg["To"] = to

    if body_text:
        msg.attach(MIMEText(body_text, "plain", "utf-8"))
    msg.attach(MIMEText(body_html, "html", "utf-8"))

    try:
        with smtplib.SMTP(settings.SMTP_HOST, settings.SMTP_PORT, timeout=10) as smtp:
            smtp.ehlo()
            if smtp.has_extn("STARTTLS"):
                smtp.starttls()
                smtp.ehlo()
            if settings.SMTP_USER and settings.SMTP_PASSWORD:
                smtp.login(settings.SMTP_USER, settings.SMTP_PASSWORD)
            smtp.sendmail(settings.SMTP_FROM, [to], msg.as_string())
        logger.info("Email sent to %r: %s", to, subject)
        return True
    except Exception as exc:
        logger.error("Failed to send email to %r: %s", to, exc)
        return False


# ---------------------------------------------------------------------------
# Higher-level helpers
# ---------------------------------------------------------------------------


def send_event_reminder(
    player_email: str,
    player_name: str,
    event_title: str,
    event_date,
    event_time,
    event_location: str,
    locale: str = "en",
) -> bool:
    """Send an event reminder to a player."""
    time_str = event_time.strftime("%H:%M") if event_time else ""
    date_str = event_date.strftime("%Y-%m-%d") if event_date else str(event_date)
    when = f"{date_str} {time_str}".strip()
    location = event_location or "TBD"

    subject = _t("email.reminder_subject", locale, event_name=event_title, date=date_str)
    body_text = _t(
        "email.reminder_body",
        locale,
        name=player_name,
        event_name=event_title,
        when=when,
        location=location,
        app_name=settings.APP_NAME,
    )
    body_html = _t(
        "email.reminder_body_html",
        locale,
        name=player_name,
        event_name=event_title,
        when=when,
        location=location,
        app_name=settings.APP_NAME,
    )
    return send_email(player_email, subject, body_html, body_text)


def send_attendance_request(
    player_email: str,
    player_name: str,
    event_title: str,
    event_date,
    attendance_url: str,
    locale: str = "en",
) -> bool:
    """Send an attendance request (RSVP) to a player."""
    date_str = event_date.strftime("%Y-%m-%d") if event_date else str(event_date)

    subject = _t("email.attendance_subject", locale, event_name=event_title, date=date_str)
    body_text = _t(
        "email.attendance_body",
        locale,
        name=player_name,
        event_name=event_title,
        date=date_str,
        url=attendance_url,
        app_name=settings.APP_NAME,
    )
    body_html = _t(
        "email.attendance_body_html",
        locale,
        name=player_name,
        event_name=event_title,
        date=date_str,
        url=attendance_url,
        app_name=settings.APP_NAME,
    )
    return send_email(player_email, subject, body_html, body_text)
