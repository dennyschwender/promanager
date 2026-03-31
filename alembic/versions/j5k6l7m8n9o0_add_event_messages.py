"""add event_messages table

Revision ID: j5k6l7m8n9o0
Revises: i4j5k6l7m8n9
Create Date: 2026-03-31 00:00:00.000000
"""

from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op

revision: str = "j5k6l7m8n9o0"
down_revision: Union[str, None] = "i4j5k6l7m8n9"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.create_table(
        "event_messages",
        sa.Column("id", sa.Integer(), nullable=False),
        sa.Column("event_id", sa.Integer(), nullable=False),
        sa.Column("user_id", sa.Integer(), nullable=True),
        sa.Column("lane", sa.String(16), nullable=False),
        sa.Column("body", sa.Text(), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.ForeignKeyConstraint(["event_id"], ["events.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["user_id"], ["users.id"], ondelete="SET NULL"),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index("ix_event_messages_id", "event_messages", ["id"])
    op.create_index("ix_event_messages_event_id", "event_messages", ["event_id"])
    op.create_index("ix_event_messages_user_id", "event_messages", ["user_id"])


def downgrade() -> None:
    op.drop_index("ix_event_messages_user_id", table_name="event_messages")
    op.drop_index("ix_event_messages_event_id", table_name="event_messages")
    op.drop_index("ix_event_messages_id", table_name="event_messages")
    op.drop_table("event_messages")
