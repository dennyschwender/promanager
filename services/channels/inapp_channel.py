"""services/channels/inapp_channel.py — In-app channel + SSE connection registry.

The SSE registry is a module-level dict keyed by player_id.
Each connected browser tab has its own asyncio.Queue.

Constraint: in-process only — does not work with multiple Uvicorn workers.
ProManager must run with --workers 1 (enforced by SQLite anyway).
"""

from __future__ import annotations

import asyncio
import json
import logging

from models.notification import Notification
from models.player import Player

logger = logging.getLogger(__name__)

# player_id → list of queues (one per open browser tab/connection)
_connections: dict[int, list[asyncio.Queue]] = {}


def register_connection(player_id: int) -> asyncio.Queue:
    """Create and register a new SSE queue for *player_id*. Call on connect."""
    q: asyncio.Queue = asyncio.Queue()
    _connections.setdefault(player_id, []).append(q)
    logger.debug("SSE: registered connection for player %s (%d total)", player_id, len(_connections[player_id]))
    return q


def unregister_connection(player_id: int, q: asyncio.Queue) -> None:
    """Remove the queue when the SSE connection closes."""
    queues = _connections.get(player_id, [])
    try:
        queues.remove(q)
    except ValueError:
        pass
    if not queues:
        _connections.pop(player_id, None)
    logger.debug("SSE: unregistered connection for player %s", player_id)


def push_unread_count(player_id: int, unread_count: int) -> None:
    """Push an unread-count update to all connected tabs for *player_id*.

    Safe to call from sync context (puts items into thread-safe queues).
    If the player has no open connection the event is silently dropped —
    the badge will update on next page load via the middleware-embedded count.
    """
    queues = _connections.get(player_id, [])
    payload = json.dumps({"unread_count": unread_count})
    for q in queues:
        try:
            q.put_nowait(payload)
        except asyncio.QueueFull:
            logger.warning("SSE queue full for player %s — dropping event", player_id)


def push_payload(player_id: int, payload: dict) -> None:
    """Push an arbitrary JSON payload to all connected tabs for *player_id*.

    Used for chat events (chat_message, chat_delete) that bypass the
    Notification table.
    """
    queues = _connections.get(player_id, [])
    data = json.dumps(payload)
    for q in queues:
        try:
            q.put_nowait(data)
        except asyncio.QueueFull:
            logger.warning("SSE queue full for player %s — dropping chat event", player_id)


class InAppChannel:
    """Signals the SSE stream for connected players."""

    def send(self, player: Player, notification: Notification, unread_count: int) -> bool:
        push_unread_count(player.id, unread_count)
        return True
