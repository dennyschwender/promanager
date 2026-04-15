"""add position to event_externals

Revision ID: l7m8n9o0p1q2
Revises: k6l7m8n9o0p1
Create Date: 2026-04-15 00:00:00.000000

"""

from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op

revision: str = "l7m8n9o0p1q2"
down_revision: Union[str, Sequence[str], None] = "k6l7m8n9o0p1"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    conn = op.get_bind()
    cols = [c["name"] for c in sa.inspect(conn).get_columns("event_externals")]
    if "position" not in cols:
        op.add_column("event_externals", sa.Column("position", sa.String(32), nullable=True))


def downgrade() -> None:
    op.drop_column("event_externals", "position")
