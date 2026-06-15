"""backfill telegram notification preferences for existing players and users

Ensures every player and user has a telegram NotificationPreference row
so the opt-in default change (8767c54) doesn't break existing users.

Also adds the user_id column that was missing in the local schema (the
v4w5x6y7z8a9 migration added it to the chain but it was never physically
applied to this database).

Revision ID: e6f24bd3768d
Revises: d6db6960611f
Create Date: 2026-06-15 15:28:09.054219

"""

from __future__ import annotations

import sqlalchemy as sa
from alembic import op

revision = "e6f24bd3768d"
down_revision = "d6db6960611f"
branch_labels = None
depends_on = None


def upgrade() -> None:
    conn = op.get_bind()

    # ── Schema: add user_id column if missing, make player_id nullable ─────
    inspector = sa.inspect(conn)
    columns = [c["name"] for c in inspector.get_columns("notification_preferences")]
    has_user_id = "user_id" in columns
    player_nullable = next(
        (c.get("nullable") for c in inspector.get_columns("notification_preferences") if c["name"] == "player_id"),
        None,
    )

    if not has_user_id or player_nullable is False:
        with op.batch_alter_table("notification_preferences") as batch_op:
            if not has_user_id:
                batch_op.add_column(sa.Column("user_id", sa.Integer(), nullable=True))
                batch_op.create_index("ix_notification_preferences_user_id", ["user_id"])
                batch_op.create_unique_constraint("uq_notif_pref_user_channel", ["user_id", "channel"])
            if player_nullable is False:
                batch_op.alter_column("player_id", existing_type=sa.Integer(), nullable=True)
        # Re-read schema: batch mode recreates the table, so we need a fresh connection
        # for the data backfill below.  Batch mode auto-commits in the WITH block.

    # ── Data: backfill telegram preference for players who lack one ────────
    conn.execute(
        sa.text("""
            INSERT OR IGNORE INTO notification_preferences (player_id, channel, enabled)
            SELECT p.id, 'telegram', 1
            FROM players p
            WHERE p.id NOT IN (
                SELECT np.player_id FROM notification_preferences np
                WHERE np.player_id IS NOT NULL AND np.channel = 'telegram'
            )
        """)
    )

    # ── Data: backfill for users (admins/coaches without linked player) ────
    conn.execute(
        sa.text("""
            INSERT OR IGNORE INTO notification_preferences (user_id, channel, enabled)
            SELECT u.id, 'telegram', 1
            FROM users u
            WHERE u.id NOT IN (
                SELECT np.user_id FROM notification_preferences np
                WHERE np.user_id IS NOT NULL AND np.channel = 'telegram'
            )
        """)
    )


def downgrade() -> None:
    conn = op.get_bind()
    conn.execute(sa.text("DELETE FROM notification_preferences WHERE channel = 'telegram'"))
    # user_id column removal handled by the prior v4w5x6y7z8a9 downgrade
