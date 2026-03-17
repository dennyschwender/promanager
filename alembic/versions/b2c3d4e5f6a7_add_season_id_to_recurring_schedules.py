"""add season_id to team_recurring_schedules

Revision ID: b2c3d4e5f6a7
Revises: abc1add0sched
Create Date: 2026-03-17 00:00:00.000000
"""

from typing import Sequence, Union

import sqlalchemy as sa

from alembic import op

revision: str = "b2c3d4e5f6a7"
down_revision: Union[str, Sequence[str], None] = ("abc1add0sched", "ea5f5d5ee0ca")
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    with op.batch_alter_table("team_recurring_schedules", schema=None) as batch_op:
        batch_op.add_column(sa.Column("season_id", sa.Integer(), nullable=True))
        batch_op.create_foreign_key(
            "fk_recurring_schedule_season",
            "seasons",
            ["season_id"],
            ["id"],
            ondelete="SET NULL",
        )


def downgrade() -> None:
    with op.batch_alter_table("team_recurring_schedules", schema=None) as batch_op:
        batch_op.drop_constraint("fk_recurring_schedule_season", type_="foreignkey")
        batch_op.drop_column("season_id")
