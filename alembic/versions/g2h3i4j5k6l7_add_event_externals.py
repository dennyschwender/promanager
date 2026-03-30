"""add event_externals table

Revision ID: g2h3i4j5k6l7
Revises: f1a2b3c4d5e6
Create Date: 2026-03-30 00:00:00.000000

"""

from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op

revision: str = "g2h3i4j5k6l7"
down_revision: Union[str, Sequence[str], None] = ("f1a2b3c4d5e6", "59415f81a1cb")
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    conn = op.get_bind()
    existing_tables = sa.inspect(conn).get_table_names()
    if "event_externals" not in existing_tables:
        op.create_table(
            "event_externals",
            sa.Column("id", sa.Integer(), primary_key=True, index=True),
            sa.Column("event_id", sa.Integer(), sa.ForeignKey("events.id", ondelete="CASCADE"), nullable=False, index=True),
            sa.Column("first_name", sa.String(128), nullable=False),
            sa.Column("last_name", sa.String(128), nullable=False),
            sa.Column("note", sa.String(512), nullable=True),
            sa.Column("status", sa.String(16), nullable=False, server_default="unknown"),
            sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        )


def downgrade() -> None:
    op.drop_table("event_externals")
