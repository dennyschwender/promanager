"""add telegram notification preference for all players

Revision ID: q5r6s7t8u9v0
Revises: p4q5r6s7t8u9
Create Date: 2026-04-20
"""
from collections.abc import Sequence
from typing import Union

import sqlalchemy as sa
from alembic import op

revision: str = "q5r6s7t8u9v0"
down_revision: Union[str, Sequence[str], None] = "p4q5r6s7t8u9"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.execute("""
        INSERT OR IGNORE INTO notification_preferences (player_id, channel, enabled)
        SELECT id, 'telegram', 1
        FROM players
    """)


def downgrade() -> None:
    op.execute("DELETE FROM notification_preferences WHERE channel = 'telegram'")
