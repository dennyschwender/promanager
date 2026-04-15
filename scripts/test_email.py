#!/usr/bin/env python
"""Send a test email using any ProManager email template.

Usage examples:
    # Reminder email with fake player data
    python scripts/test_email.py --to you@example.com --type reminder

    # Attendance request email
    python scripts/test_email.py --to you@example.com --type attendance

    # Use a real player from the DB as the fake user
    python scripts/test_email.py --to you@example.com --type reminder --player-id 3

    # Use a real event from the DB
    python scripts/test_email.py --to you@example.com --type reminder --event-id 7

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
from services.email_service import send_attendance_request, send_event_reminder

# ---------------------------------------------------------------------------
# Fake defaults used when no real DB objects are specified
# ---------------------------------------------------------------------------

FAKE_PLAYER_NAME = "Test Player"
FAKE_EVENT_TITLE = "Test Match"
FAKE_EVENT_DATE = date.today()
FAKE_EVENT_TIME = time(19, 30)
FAKE_EVENT_LOCATION = "Test Arena"
FAKE_ATTENDANCE_URL = "http://localhost:7000/events/1"


def main() -> None:
    parser = argparse.ArgumentParser(description="Send a test ProManager email.")
    parser.add_argument("--to", required=True, help="Recipient email address")
    parser.add_argument(
        "--type",
        choices=["reminder", "attendance"],
        default="reminder",
        help="Email template to send (default: reminder)",
    )
    parser.add_argument("--player-id", type=int, help="Use a real player from the DB")
    parser.add_argument("--event-id", type=int, help="Use a real event from the DB")
    parser.add_argument("--locale", default="en", help="Locale for the email (default: en)")
    args = parser.parse_args()

    init_db()

    player_name = FAKE_PLAYER_NAME
    event_title = FAKE_EVENT_TITLE
    event_date = FAKE_EVENT_DATE
    event_time = FAKE_EVENT_TIME
    event_location = FAKE_EVENT_LOCATION
    attendance_url = FAKE_ATTENDANCE_URL

    if args.player_id or args.event_id:
        from models.event import Event
        from models.player import Player

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

    print(f"Sending '{args.type}' email to {args.to} (locale={args.locale}) ...")

    if args.type == "reminder":
        ok = send_event_reminder(
            player_email=args.to,
            player_name=player_name,
            event_title=event_title,
            event_date=event_date,
            event_time=event_time,
            event_location=event_location,
            locale=args.locale,
        )
    else:  # attendance
        ok = send_attendance_request(
            player_email=args.to,
            player_name=player_name,
            event_title=event_title,
            event_date=event_date,
            attendance_url=attendance_url,
            locale=args.locale,
        )

    if ok:
        print("Done.")
    else:
        print("Failed — check SMTP settings and logs.", file=sys.stderr)
        sys.exit(1)


if __name__ == "__main__":
    main()
