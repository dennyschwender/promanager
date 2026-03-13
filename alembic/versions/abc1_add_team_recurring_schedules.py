"""add team_recurring_schedules table

Revision ID: abc1add0sched
Revises: 7d6728f4bc65
Create Date: 2026-03-13 12:00:00.000000
"""
from typing import Sequence, Union

import sqlalchemy as sa

from alembic import op

revision: str = "abc1add0sched"
down_revision: Union[str, Sequence[str], None] = "7d6728f4bc65"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.create_table(
        "team_recurring_schedules",
        sa.Column("id", sa.Integer(), nullable=False),
        sa.Column("team_id", sa.Integer(), nullable=False),
        sa.Column("title", sa.String(length=256), nullable=False),
        sa.Column("event_type", sa.String(length=32), nullable=False),
        sa.Column("recurrence_rule", sa.String(length=32), nullable=False),
        sa.Column("start_date", sa.Date(), nullable=False),
        sa.Column("end_date", sa.Date(), nullable=True),
        sa.Column("event_time", sa.Time(), nullable=True),
        sa.Column("event_end_time", sa.Time(), nullable=True),
        sa.Column("location", sa.String(length=256), nullable=True),
        sa.Column("meeting_time", sa.Time(), nullable=True),
        sa.Column("meeting_location", sa.String(length=256), nullable=True),
        sa.Column("presence_type", sa.String(length=32), nullable=False),
        sa.Column("description", sa.Text(), nullable=True),
        sa.Column("recurrence_group_id", sa.String(length=36), nullable=False),
        sa.ForeignKeyConstraint(["team_id"], ["teams.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("recurrence_group_id"),
    )
    with op.batch_alter_table("team_recurring_schedules", schema=None) as batch_op:
        batch_op.create_index(
            batch_op.f("ix_team_recurring_schedules_id"), ["id"], unique=False
        )
        batch_op.create_index(
            batch_op.f("ix_team_recurring_schedules_team_id"), ["team_id"], unique=False
        )
        batch_op.create_index(
            batch_op.f("ix_team_recurring_schedules_recurrence_group_id"),
            ["recurrence_group_id"],
            unique=True,
        )


def downgrade() -> None:
    op.drop_table("team_recurring_schedules")
