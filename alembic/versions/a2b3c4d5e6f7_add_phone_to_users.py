"""add phone to users

Revision ID: a2b3c4d5e6f7
Revises: f1a2b3c4d5e6
Create Date: 2026-03-30 00:00:00.000000

"""

from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op

revision: str = "a2b3c4d5e6f7"
down_revision: Union[str, Sequence[str], None] = "f1a2b3c4d5e6"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    conn = op.get_bind()
    existing_cols = [c["name"] for c in sa.inspect(conn).get_columns("users")]
    if "phone" not in existing_cols:
        op.add_column("users", sa.Column("phone", sa.String(32), nullable=True))


def downgrade() -> None:
    op.drop_column("users", "phone")
