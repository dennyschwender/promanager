"""add player_absences table

Revision ID: k6l7m8n9o0p1
Revises: j5k6l7m8n9o0
Create Date: 2026-04-06 00:00:00.000000
"""

from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op

revision: str = "k6l7m8n9o0p1"
down_revision: Union[str, None] = "j5k6l7m8n9o0"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.create_table(
        "player_absences",
        sa.Column("id", sa.Integer(), nullable=False),
        sa.Column("player_id", sa.Integer(), nullable=False),
        sa.Column("absence_type", sa.String(16), nullable=False),
        sa.Column("start_date", sa.Date(), nullable=True),
        sa.Column("end_date", sa.Date(), nullable=True),
        sa.Column("rrule", sa.String(256), nullable=True),
        sa.Column("rrule_until", sa.Date(), nullable=True),
        sa.Column("season_id", sa.Integer(), nullable=True),
        sa.Column("reason", sa.String(512), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
        sa.ForeignKeyConstraint(["player_id"], ["players.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["season_id"], ["seasons.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index("ix_player_absences_id", "player_absences", ["id"])
    op.create_index("ix_player_absences_player_id", "player_absences", ["player_id"])
    op.create_index("ix_player_absences_season_id", "player_absences", ["season_id"])


def downgrade() -> None:
    op.drop_index("ix_player_absences_season_id", table_name="player_absences")
    op.drop_index("ix_player_absences_player_id", table_name="player_absences")
    op.drop_index("ix_player_absences_id", table_name="player_absences")
    op.drop_table("player_absences")
