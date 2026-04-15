#!/usr/bin/env python
"""Send a test email using any ProManager email template.

Usage examples:
    # Reminder email with fake player data
    python scripts/test_email.py --to you@example.com --type reminder

    # Attendance request email
    python scripts/test_email.py --to you@example.com --type attendance

    # Welcome email (account created)
    python scripts/test_email.py --to you@example.com --type welcome

    # Password reset email
    python scripts/test_email.py --to you@example.com --type reset

    # Generic notification email
    python scripts/test_email.py --to you@example.com --type notification

    # Use a real player from the DB
    python scripts/test_email.py --to you@example.com --type reminder --player-id 3

    # Use a real event from the DB
    python scripts/test_email.py --to you@example.com --type reminder --event-id 7

    # Use a real user from the DB (for welcome/reset)
    python scripts/test_email.py --to you@example.com --type welcome --user-id 2

    # Override locale
    python scripts/test_email.py --to you@example.com --type reminder --locale it
"""

from __future__ import annotations

import os
import sys
from datetime import date, time

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

import argparse

from app.database import SessionLocal, init_db
from app.i18n import t
from services.email_service import send_attendance_request, send_email, send_event_reminder

# ---------------------------------------------------------------------------
# Fake defaults
# ---------------------------------------------------------------------------

FAKE_PLAYER_NAME = "Test Player"
FAKE_USERNAME = "testplayer"
FAKE_PASSWORD = "Abc123xyz!"
FAKE_EVENT_TITLE = "Test Match"
FAKE_EVENT_DATE = date.today()
FAKE_EVENT_TIME = time(19, 30)
FAKE_EVENT_LOCATION = "Test Arena"
FAKE_ATTENDANCE_URL = "http://localhost:7000/events/1"
FAKE_NOTIFICATION_TITLE = "Test Notification"
FAKE_NOTIFICATION_BODY = "This is a test notification sent from the test_email script."
FAKE_NOTIFICATION_TAG = "test"


def main() -> None:
    parser = argparse.ArgumentParser(description="Send a test ProManager email.")
    parser.add_argument("--to", required=True, help="Recipient email address")
    parser.add_argument(
        "--type",
        choices=["reminder", "attendance", "welcome", "reset", "notification"],
        default="reminder",
        help="Email template to send (default: reminder)",
    )
    parser.add_argument("--player-id", type=int, help="Use a real player from the DB (reminder/attendance)")
    parser.add_argument("--event-id", type=int, help="Use a real event from the DB (reminder/attendance)")
    parser.add_argument("--user-id", type=int, help="Use a real user from the DB (welcome/reset)")
    parser.add_argument("--locale", default="en", help="Locale for the email (default: en)")
    args = parser.parse_args()

    init_db()

    player_name = FAKE_PLAYER_NAME
    username = FAKE_USERNAME
    event_title = FAKE_EVENT_TITLE
    event_date = FAKE_EVENT_DATE
    event_time = FAKE_EVENT_TIME
    event_location = FAKE_EVENT_LOCATION
    attendance_url = FAKE_ATTENDANCE_URL

    if args.player_id or args.event_id or args.user_id:
        from models.event import Event
        from models.player import Player
        from models.user import User

        with SessionLocal() as db:
            if args.player_id:
                player = db.get(Player, args.player_id)
                if player is None:
                    print(f"Error: player id={args.player_id} not found.", file=sys.stderr)
                    sys.exit(1)
                player_name = player.full_name
                print(f"Using player: {player_name}")

            if args.event_id:
                event = db.get(Event, args.event_id)
                if event is None:
                    print(f"Error: event id={args.event_id} not found.", file=sys.stderr)
                    sys.exit(1)
                event_title = event.title
                event_date = event.event_date
                event_time = event.event_time
                event_location = event.location or ""
                attendance_url = f"http://localhost:7000/events/{event.id}"
                print(f"Using event: {event_title} on {event_date}")

            if args.user_id:
                user = db.get(User, args.user_id)
                if user is None:
                    print(f"Error: user id={args.user_id} not found.", file=sys.stderr)
                    sys.exit(1)
                player_name = f"{user.first_name or ''} {user.last_name or ''}".strip() or user.username
                username = user.username
                print(f"Using user: {username}")

    locale = args.locale
    print(f"Sending '{args.type}' email to {args.to} (locale={locale}) ...")

    if args.type == "reminder":
        ok = send_event_reminder(
            player_email=args.to,
            player_name=player_name,
            event_title=event_title,
            event_date=event_date,
            event_time=event_time,
            event_location=event_location,
            locale=locale,
        )

    elif args.type == "attendance":
        ok = send_attendance_request(
            player_email=args.to,
            player_name=player_name,
            event_title=event_title,
            event_date=event_date,
            attendance_url=attendance_url,
            locale=locale,
        )

    elif args.type == "welcome":
        subject = t("users.email_subject", locale)
        body_html = (
            f"<p>Your account has been created.<br>"
            f"Username: <strong>{username}</strong><br>"
            f"Password: <strong>{FAKE_PASSWORD}</strong></p>"
        )
        body_text = (
            f"Your account has been created.\n"
            f"Username: {username}\n"
            f"Password: {FAKE_PASSWORD}"
        )
        ok = send_email(args.to, subject, body_html, body_text)

    elif args.type == "reset":
        subject = t("users.email_subject", locale)
        reset_body = t("users.reset_email_body", locale)
        body_html = (
            f"<p>{reset_body}<br>"
            f"Username: <strong>{username}</strong><br>"
            f"Password: <strong>{FAKE_PASSWORD}</strong></p>"
        )
        body_text = (
            f"{reset_body}\n"
            f"Username: {username}\n"
            f"Password: {FAKE_PASSWORD}"
        )
        ok = send_email(args.to, subject, body_html, body_text)

    elif args.type == "notification":
        body_html = (
            f"<p>{FAKE_NOTIFICATION_BODY.replace(chr(10), '<br>')}</p>"
            f"<p><small>Tag: {FAKE_NOTIFICATION_TAG}</small></p>"
        )
        ok = send_email(args.to, FAKE_NOTIFICATION_TITLE, body_html, FAKE_NOTIFICATION_BODY)

    if ok:
        print("Done.")
    else:
        print("Failed — check SMTP settings and logs.", file=sys.stderr)
        sys.exit(1)


if __name__ == "__main__":
    main()
