#!/usr/bin/env python
"""Test script for sending Telegram notifications."""
import asyncio
import sys
import os
from pathlib import Path

# Add parent directory to path
sys.path.insert(0, str(Path(__file__).parent.parent))

import app.database as db_module
from models.user import User
from models.player import Player
from models.event import Event
from services.telegram_notifications import notify_coaches_via_telegram


async def send_test_notification(user_id: int, event_id: int, player_id: int, status: str) -> None:
    """Send a test Telegram notification."""
    db = db_module.SessionLocal()
    try:
        user = db.get(User, user_id)
        if not user:
            print(f"User {user_id} not found")
            return

        player = db.get(Player, player_id)
        if not player:
            print(f"Player {player_id} not found")
            return

        event = db.get(Event, event_id)
        if not event:
            print(f"Event {event_id} not found")
            return

        # Initialize bot if needed
        import bot as _bot
        if _bot.telegram_app is None:
            token = os.getenv("TELEGRAM_BOT_TOKEN")
            if not token:
                print("TELEGRAM_BOT_TOKEN not set")
                return
            print("Initializing Telegram app...")
            await _bot.init_application(token)

        print(f"Sending notification: {player.full_name} → {status} for {event.title}")
        await notify_coaches_via_telegram(event_id, player_id, status)
        print("Notification sent!")

    finally:
        db.close()


if __name__ == "__main__":
    if len(sys.argv) != 5:
        print("Usage: python test_telegram.py <user_id> <event_id> <player_id> <status>")
        print("Example: python test_telegram.py 1 5 10 present")
        sys.exit(1)

    user_id = int(sys.argv[1])
    event_id = int(sys.argv[2])
    player_id = int(sys.argv[3])
    status = sys.argv[4]

    asyncio.run(send_test_notification(user_id, event_id, player_id, status))
