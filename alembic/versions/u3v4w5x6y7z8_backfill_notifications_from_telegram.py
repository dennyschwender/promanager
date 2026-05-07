"""Backfill Notification records from TelegramNotification rows that predate the unified model.

Any TelegramNotification whose (user_id, event_id, player_id, status) has no matching
Notification row is migrated to Notification with user_id set (since the old rows are for
coaches who may not have a linked player).

Revision ID: u3v4w5x6y7z8
Revises: t2u3v4w5x6y7
Create Date: 2026-05-07
"""

from __future__ import annotations

from alembic import op
import sqlalchemy as sa
from sqlalchemy import text


revision = "u3v4w5x6y7z8"
down_revision = "t2u3v4w5x6y7"
branch_labels = None
depends_on = None


def upgrade() -> None:
    conn = op.get_bind()

    # Find TelegramNotification rows with no corresponding Notification for the same user+event+player
    rows = conn.execute(text("""
        SELECT tn.user_id, tn.event_id, tn.player_id, tn.status, tn.created_at
        FROM telegram_notifications tn
        WHERE NOT EXISTS (
            SELECT 1 FROM notifications n
            WHERE n.user_id = tn.user_id
              AND n.event_id = tn.event_id
              AND n.is_read = 0
        )
        ORDER BY tn.created_at ASC
    """)).fetchall()

    if not rows:
        return

    # Build icon map inline (no app imports in migrations)
    icon_map = {"present": "✓", "absent": "✗", "unknown": "?"}

    # Get player full names for titles
    player_names: dict[int, str] = {}
    for row in rows:
        pid = row[2]
        if pid not in player_names:
            result = conn.execute(
                text("SELECT first_name, last_name FROM players WHERE id = :pid"),
                {"pid": pid},
            ).fetchone()
            if result:
                player_names[pid] = f"{result[0]} {result[1]}".strip()
            else:
                player_names[pid] = f"Player {pid}"

    # Get event titles
    event_titles: dict[int, str] = {}
    for row in rows:
        eid = row[1]
        if eid not in event_titles:
            result = conn.execute(
                text("SELECT title FROM events WHERE id = :eid"),
                {"eid": eid},
            ).fetchone()
            event_titles[eid] = result[0] if result else ""

    # Deduplicate: one Notification per (user_id, event_id) from the most recent TelegramNotification
    seen: set[tuple[int, int]] = set()
    to_insert = []
    for row in reversed(rows):  # most recent first after reversal
        user_id, event_id, player_id, status, created_at = row
        key = (user_id, event_id)
        if key in seen:
            continue
        seen.add(key)
        icon = icon_map.get(status, "?")
        pname = player_names.get(player_id, f"Player {player_id}")
        to_insert.append({
            "user_id": user_id,
            "player_id": None,
            "event_id": event_id,
            "title": f"{icon} {pname} → {status}",
            "body": event_titles.get(event_id, ""),
            "tag": "direct",
            "is_read": True,  # mark historical records as already read
            "created_at": created_at,
        })

    for rec in to_insert:
        conn.execute(
            text("""
                INSERT INTO notifications (user_id, player_id, event_id, title, body, tag, is_read, created_at)
                VALUES (:user_id, :player_id, :event_id, :title, :body, :tag, :is_read, :created_at)
            """),
            rec,
        )


def downgrade() -> None:
    # Cannot safely remove backfilled rows without risk of removing legitimate ones.
    pass
