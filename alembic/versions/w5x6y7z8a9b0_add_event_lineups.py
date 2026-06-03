"""add event_lineups table

Revision ID: w5x6y7z8a9b0
Revises: v4w5x6y7z8a9
Create Date: 2026-05-18

"""

from __future__ import annotations

from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op

revision: str = "w5x6y7z8a9b0"
down_revision: Union[str, None] = "v4w5x6y7z8a9"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.create_table(
        "event_lineups",
        sa.Column("id", sa.Integer(), nullable=False),
        sa.Column("event_id", sa.Integer(), nullable=False),
        sa.Column("groups_json", sa.Text(), nullable=False, server_default="[]"),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
        sa.ForeignKeyConstraint(["event_id"], ["events.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("event_id", name="uq_event_lineup_event"),
    )
    op.create_index("ix_event_lineups_id", "event_lineups", ["id"])
    op.create_index("ix_event_lineups_event_id", "event_lineups", ["event_id"])


def downgrade() -> None:
    op.drop_index("ix_event_lineups_event_id", table_name="event_lineups")
    op.drop_index("ix_event_lineups_id", table_name="event_lineups")
    op.drop_table("event_lineups")
