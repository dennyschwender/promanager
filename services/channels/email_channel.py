"""services/channels/email_channel.py — Email notification channel."""
from __future__ import annotations

import logging

from models.notification import Notification
from models.player import Player
from services.email_service import send_email

logger = logging.getLogger(__name__)


class EmailChannel:
    """Sends a notification via email using the existing email_service."""

    def send(self, player: Player, notification: Notification) -> bool:
        if not player.email:
            logger.debug("EmailChannel: player %s has no email, skipping", player.id)
            return False
        subject = notification.title
        body_text = notification.body
        body_html = (
            f"<p>{notification.body.replace(chr(10), '<br>')}</p>"
            f"<p><small>Tag: {notification.tag}</small></p>"
        )
        ok = send_email(player.email, subject, body_html, body_text)
        if not ok:
            logger.warning(
                "EmailChannel: failed to send to player %s (%s)", player.id, player.email
            )
        return ok
