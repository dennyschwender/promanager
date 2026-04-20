"""services/channels/telegram_channel.py — Telegram notification channel."""
from __future__ import annotations

import logging
import os

import requests

from models.notification import Notification
from models.player import Player

logger = logging.getLogger(__name__)

_EMOJI: dict[str, str] = {
    "event_new": "📅",
    "event_update": "✏️",
    "reminder": "⏰",
    "announcement": "📅",
}


class TelegramChannel:
    """Sends a notification to a player's linked Telegram chat via the Bot HTTP API."""

    def send(self, player: Player, notification: Notification) -> bool:
        if not player.user or not player.user.telegram_chat_id:
            return False
        token = os.environ.get("TELEGRAM_BOT_TOKEN", "")
        if not token:
            return False

        emoji = _EMOJI.get(notification.tag, "📬")
        text = f"{emoji} {notification.title}\n{notification.body}"
        payload: dict = {"chat_id": player.user.telegram_chat_id, "text": text}

        if notification.event_id:
            payload["reply_markup"] = {
                "inline_keyboard": [[
                    {"text": "📅 This event", "callback_data": f"evt:{notification.event_id}"},
                    {"text": "📋 All events", "callback_data": "evts:0"},
                ]]
            }

        try:
            resp = requests.post(
                f"https://api.telegram.org/bot{token}/sendMessage",
                json=payload,
                timeout=10,
            )
            if not resp.ok:
                logger.warning(
                    "TelegramChannel: API error %s for player %s: %s",
                    resp.status_code, player.id, resp.text,
                )
            return resp.ok
        except Exception as exc:
            logger.warning("TelegramChannel: request failed for player %s: %s", player.id, exc, exc_info=True)
            return False
