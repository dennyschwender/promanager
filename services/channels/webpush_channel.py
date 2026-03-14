"""services/channels/webpush_channel.py — Web Push notification channel."""
from __future__ import annotations

import json
import logging

from sqlalchemy.orm import Session

from app.config import settings
from models.notification import Notification
from models.player import Player
from models.web_push_subscription import WebPushSubscription

logger = logging.getLogger(__name__)


def _is_configured() -> bool:
    return bool(settings.VAPID_PRIVATE_KEY and settings.VAPID_PUBLIC_KEY)


class WebPushChannel:
    """Sends browser push notifications via pywebpush."""

    def send(self, player: Player, notification: Notification, db: Session) -> bool:
        if not _is_configured():
            logger.debug("WebPushChannel: VAPID not configured, skipping")
            return False

        try:
            from pywebpush import WebPushException, webpush  # noqa: PLC0415, F401
        except ImportError:
            logger.warning("pywebpush not installed — Web Push unavailable")
            return False

        subscriptions = (
            db.query(WebPushSubscription)
            .filter(WebPushSubscription.player_id == player.id)
            .all()
        )
        if not subscriptions:
            return False

        payload = json.dumps({"title": notification.title, "body": notification.body})
        vapid_claims = {"sub": settings.VAPID_SUBJECT}
        sent = False

        to_delete = []
        for sub in subscriptions:
            subscription_info = {
                "endpoint": sub.endpoint,
                "keys": {"p256dh": sub.p256dh_key, "auth": sub.auth_key},
            }
            try:
                webpush(
                    subscription_info=subscription_info,
                    data=payload,
                    vapid_private_key=settings.VAPID_PRIVATE_KEY,
                    vapid_claims=vapid_claims,
                )
                sent = True
            except Exception as exc:
                is_gone = hasattr(exc, "response") and getattr(
                    exc.response, "status_code", None
                ) == 410
                if is_gone:
                    logger.info(
                        "WebPushChannel: removing expired subscription %s", sub.id
                    )
                    to_delete.append(sub)
                else:
                    logger.warning(
                        "WebPushChannel: push failed for sub %s: %s", sub.id, exc
                    )

        for sub in to_delete:
            db.delete(sub)
        if to_delete:
            db.commit()

        return sent
