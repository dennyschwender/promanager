"""add unique constraint on players.user_id

Revision ID: h3i4j5k6l7m8
Revises: g2h3i4j5k6l7
Create Date: 2026-03-31 00:00:00.000000

"""

from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op

revision: str = "h3i4j5k6l7m8"
down_revision: Union[str, Sequence[str], None] = "g2h3i4j5k6l7"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    conn = op.get_bind()

    # Remove duplicate user_id links — keep the first player (lowest id) for each user_id
    conn.execute(sa.text("""
        UPDATE players SET user_id = NULL
        WHERE user_id IS NOT NULL
          AND id NOT IN (
              SELECT MIN(id) FROM players
              WHERE user_id IS NOT NULL
              GROUP BY user_id
          )
    """))

    with op.batch_alter_table("players", schema=None) as batch_op:
        batch_op.create_unique_constraint("uq_players_user_id", ["user_id"])


def downgrade() -> None:
    with op.batch_alter_table("players", schema=None) as batch_op:
        batch_op.drop_constraint("uq_players_user_id", type_="unique")
