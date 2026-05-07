"""Unified notification recipient: make player_id nullable, add user_id to notifications and web_push_subscriptions.

Revision ID: t2u3v4w5x6y7
Revises: s7t8u9v0w1x2
Create Date: 2026-05-07

"""

from __future__ import annotations

import sqlalchemy as sa
from alembic import op

revision = "t2u3v4w5x6y7"
down_revision = "s7t8u9v0w1x2"
branch_labels = None
depends_on = None


def upgrade() -> None:
    # notifications: make player_id nullable, add user_id
    with op.batch_alter_table("notifications") as batch_op:
        batch_op.alter_column("player_id", existing_type=sa.Integer(), nullable=True)
        batch_op.add_column(sa.Column("user_id", sa.Integer(), sa.ForeignKey("users.id", ondelete="CASCADE"), nullable=True))
        batch_op.create_index("ix_notifications_user_id", ["user_id"])

    # web_push_subscriptions: make player_id nullable, add user_id
    with op.batch_alter_table("web_push_subscriptions") as batch_op:
        batch_op.alter_column("player_id", existing_type=sa.Integer(), nullable=True)
        batch_op.add_column(sa.Column("user_id", sa.Integer(), sa.ForeignKey("users.id", ondelete="CASCADE"), nullable=True))
        batch_op.create_index("ix_web_push_subscriptions_user_id", ["user_id"])


def downgrade() -> None:
    with op.batch_alter_table("web_push_subscriptions") as batch_op:
        batch_op.drop_index("ix_web_push_subscriptions_user_id")
        batch_op.drop_column("user_id")
        batch_op.alter_column("player_id", existing_type=sa.Integer(), nullable=False)

    with op.batch_alter_table("notifications") as batch_op:
        batch_op.drop_index("ix_notifications_user_id")
        batch_op.drop_column("user_id")
        batch_op.alter_column("player_id", existing_type=sa.Integer(), nullable=False)
