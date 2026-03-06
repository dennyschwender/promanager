"""services/email_service.py — SMTP email helpers using stdlib only."""

from __future__ import annotations

import logging
import smtplib
from email.mime.multipart import MIMEMultipart
from email.mime.text import MIMEText

from app.config import settings

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
) -> bool:
    """Send an event reminder to a player."""
    time_str = event_time.strftime("%H:%M") if event_time else ""
    date_str = event_date.strftime("%Y-%m-%d") if event_date else str(event_date)
    when = f"{date_str} {time_str}".strip()

    subject = f"Reminder: {event_title} on {date_str}"
    body_text = (
        f"Hi {player_name},\n\n"
        f"This is a reminder for the upcoming event:\n\n"
        f"  Event:    {event_title}\n"
        f"  When:     {when}\n"
        f"  Location: {event_location or 'TBD'}\n\n"
        f"Please make sure to update your attendance status.\n\n"
        f"Best regards,\n{settings.APP_NAME}"
    )
    body_html = (
        f"<p>Hi <strong>{player_name}</strong>,</p>"
        f"<p>This is a reminder for the upcoming event:</p>"
        f"<table>"
        f"<tr><td><strong>Event</strong></td><td>{event_title}</td></tr>"
        f"<tr><td><strong>When</strong></td><td>{when}</td></tr>"
        f"<tr><td><strong>Location</strong></td><td>{event_location or 'TBD'}</td></tr>"
        f"</table>"
        f"<p>Please update your attendance status.</p>"
        f"<p>Best regards,<br>{settings.APP_NAME}</p>"
    )
    return send_email(player_email, subject, body_html, body_text)


def send_attendance_request(
    player_email: str,
    player_name: str,
    event_title: str,
    event_date,
    attendance_url: str,
) -> bool:
    """Send an attendance request (RSVP) to a player."""
    date_str = event_date.strftime("%Y-%m-%d") if event_date else str(event_date)
    subject = f"Please confirm attendance: {event_title} on {date_str}"
    body_text = (
        f"Hi {player_name},\n\n"
        f"Please confirm your attendance for:\n\n"
        f"  Event: {event_title}\n"
        f"  Date:  {date_str}\n\n"
        f"Update your status here: {attendance_url}\n\n"
        f"Best regards,\n{settings.APP_NAME}"
    )
    body_html = (
        f"<p>Hi <strong>{player_name}</strong>,</p>"
        f"<p>Please confirm your attendance for <strong>{event_title}</strong> on {date_str}.</p>"
        f"<p><a href=\"{attendance_url}\">Click here to update your attendance status</a></p>"
        f"<p>Best regards,<br>{settings.APP_NAME}</p>"
    )
    return send_email(player_email, subject, body_html, body_text)
