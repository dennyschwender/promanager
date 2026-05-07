"""Add user_id to notification_preferences for unlinked admin/coach opt-out support.

Revision ID: v4w5x6y7z8a9
Revises: u3v4w5x6y7z8
Create Date: 2026-05-07
"""

from __future__ import annotations

import sqlalchemy as sa
from alembic import op

revision = "v4w5x6y7z8a9"
down_revision = "u3v4w5x6y7z8"
branch_labels = None
depends_on = None


def upgrade() -> None:
    with op.batch_alter_table("notification_preferences") as batch_op:
        # Make player_id nullable (unlinked admins won't have one)
        batch_op.alter_column("player_id", existing_type=sa.Integer(), nullable=True)
        # Add user_id FK (no inline FK — SQLite batch mode raises on unnamed constraints)
        batch_op.add_column(sa.Column("user_id", sa.Integer(), nullable=True))
        batch_op.create_index("ix_notification_preferences_user_id", ["user_id"])
        # Rename old unnamed unique constraint and add named ones
        # SQLite batch recreates the table so we just declare the new constraints
        batch_op.create_unique_constraint("uq_notif_pref_user_channel", ["user_id", "channel"])


def downgrade() -> None:
    with op.batch_alter_table("notification_preferences") as batch_op:
        batch_op.drop_constraint("uq_notif_pref_user_channel", type_="unique")
        batch_op.drop_index("ix_notification_preferences_user_id")
        batch_op.drop_column("user_id")
        batch_op.alter_column("player_id", existing_type=sa.Integer(), nullable=False)
