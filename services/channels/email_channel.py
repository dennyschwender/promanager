"""services/channels/email_channel.py — Email notification channel."""

from __future__ import annotations

import logging

from models.notification import Notification
from models.player import Player
from services.auth_service import create_magic_link
from services.email_service import send_notification_email

logger = logging.getLogger(__name__)


class EmailChannel:
    """Sends a notification via email using the existing email_service."""

    def send(self, player: Player, notification: Notification) -> bool:
        if not player.email:
            logger.debug("EmailChannel: player %s has no email, skipping", player.id)
            return False
        magic = create_magic_link(player.id, "/notifications")
        ok = send_notification_email(
            to=player.email,
            title=notification.title,
            body=notification.body,
            locale=getattr(player, "locale", None) or "en",
            magic_link=magic,
        )
        if not ok:
            logger.warning("EmailChannel: failed to send to player %s (%s)", player.id, player.email)
        return ok
