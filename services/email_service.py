"""services/email_service.py — SMTP email helpers using stdlib only."""

from __future__ import annotations

import html as _html_mod
import logging
import re
import smtplib
from email.mime.multipart import MIMEMultipart
from email.mime.text import MIMEText

from app.config import settings
from app.i18n import t as _t

logger = logging.getLogger(__name__)

# ---------------------------------------------------------------------------
# Core send function
# ---------------------------------------------------------------------------


# ---------------------------------------------------------------------------
# Template rendering
# ---------------------------------------------------------------------------


def _strip_html(html: str) -> str:
    """Convert an HTML string to plain text by stripping tags."""
    # Remove <head>...</head> so <title> doesn't duplicate the header text
    html = re.sub(r"<head\b[^>]*>.*?</head>", "", html, flags=re.IGNORECASE | re.DOTALL)
    html = re.sub(r"<br\s*/?>", "\n", html, flags=re.IGNORECASE)
    html = re.sub(r"</(p|div|tr|li)>", "\n", html, flags=re.IGNORECASE)
    html = re.sub(r"<[^>]+>", "", html)
    html = _html_mod.unescape(html)
    lines = [line.strip() for line in html.splitlines()]
    lines = [line for line in lines if line]
    return "\n".join(lines)


def render_email_template(
    name: str,
    context: dict,
    locale: str = "en",
) -> str:
    """Render templates/email/{name}.html via the shared Jinja2 environment.

    Always injects: app_name, t (i18n callable), magic_link (default None).
    Returns the rendered HTML string.
    """
    from app.i18n import t as _t
    from app.templates import templates

    full_context = {
        "app_name": settings.APP_NAME,
        "magic_link": None,
        "t": lambda key, **kw: _t(key, locale, **kw),
        **context,
    }
    template = templates.env.get_template(f"email/{name}.html")
    return template.render(**full_context)


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
    magic_link: str | None = None,
) -> bool:
    """Send an event reminder to a player."""
    time_str = event_time.strftime("%H:%M") if event_time else ""
    date_str = event_date.strftime("%Y-%m-%d") if event_date else str(event_date)
    when = f"{date_str} {time_str}".strip()

    subject = _t("email.reminder_subject", locale, event_name=event_title, date=date_str)
    body_html = render_email_template("reminder", {
        "name": player_name,
        "event_title": event_title,
        "when": when,
        "location": event_location or "TBD",
        "magic_link": magic_link,
    }, locale=locale)
    body_text = _strip_html(body_html)
    return send_email(player_email, subject, body_html, body_text)


def send_attendance_request(
    player_email: str,
    player_name: str,
    event_title: str,
    event_date,
    attendance_url: str,
    locale: str = "en",
    magic_link: str | None = None,
) -> bool:
    """Send an attendance request (RSVP) to a player."""
    date_str = event_date.strftime("%Y-%m-%d") if event_date else str(event_date)

    subject = _t("email.attendance_subject", locale, event_name=event_title, date=date_str)
    body_html = render_email_template("attendance", {
        "name": player_name,
        "event_title": event_title,
        "date": date_str,
        "attendance_url": attendance_url,
        "magic_link": magic_link,
    }, locale=locale)
    body_text = _strip_html(body_html)
    return send_email(player_email, subject, body_html, body_text)


def send_welcome_email(
    to: str,
    username: str,
    password: str,
    locale: str = "en",
    magic_link: str | None = None,
) -> bool:
    """Send a welcome email with login credentials to a new user."""
    subject = _t("email.welcome_subject", locale, app_name=settings.APP_NAME)
    body_html = render_email_template("welcome", {
        "username": username,
        "password": password,
        "magic_link": magic_link,
        "telegram_bot_username": settings.TELEGRAM_BOT_USERNAME or None,
    }, locale=locale)
    body_text = _strip_html(body_html)
    return send_email(to, subject, body_html, body_text)


def send_reset_email(
    to: str,
    username: str,
    password: str,
    locale: str = "en",
    magic_link: str | None = None,
) -> bool:
    """Send a password-reset email with new credentials."""
    subject = _t("email.reset_subject", locale, app_name=settings.APP_NAME)
    body_html = render_email_template("reset", {
        "username": username,
        "password": password,
        "magic_link": magic_link,
    }, locale=locale)
    body_text = _strip_html(body_html)
    return send_email(to, subject, body_html, body_text)


def send_notification_email(
    to: str,
    title: str,
    body: str,
    locale: str = "en",
    magic_link: str | None = None,
) -> bool:
    """Send a generic notification email."""
    subject = _t("email.notification_subject", locale, title=title)
    body_html = render_email_template("notification", {
        "title": title,
        "body": body,
        "magic_link": magic_link,
    }, locale=locale)
    body_text = _strip_html(body_html)
    return send_email(to, subject, body_html, body_text)


def send_forgot_password_email(
    to: str,
    username: str,
    password: str,
    locale: str = "en",
) -> bool:
    """Send a forgot-password email with new temporary credentials."""
    subject = _t("email.forgot_password_subject", locale, app_name=settings.APP_NAME)
    body_html = render_email_template("forgot_password", {
        "username": username,
        "password": password,
    }, locale=locale)
    body_text = _strip_html(body_html)
    return send_email(to, subject, body_html, body_text)
