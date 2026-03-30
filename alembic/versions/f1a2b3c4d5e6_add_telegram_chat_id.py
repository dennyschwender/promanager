"""add telegram_chat_id to users

Revision ID: f1a2b3c4d5e6
Revises: ce63adc3d835
Create Date: 2026-03-30 00:00:00.000000

"""

from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op

revision: str = "f1a2b3c4d5e6"
down_revision: Union[str, Sequence[str], None] = "ce63adc3d835"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    conn = op.get_bind()
    existing_cols = [c["name"] for c in sa.inspect(conn).get_columns("users")]
    if "telegram_chat_id" not in existing_cols:
        op.add_column(
            "users",
            sa.Column("telegram_chat_id", sa.String(64), nullable=True),
        )
    existing_indexes = [i["name"] for i in sa.inspect(conn).get_indexes("users")]
    if "ix_users_telegram_chat_id_unique" not in existing_indexes:
        op.create_index("ix_users_telegram_chat_id_unique", "users", ["telegram_chat_id"], unique=True)


def downgrade() -> None:
    op.drop_index("ix_users_telegram_chat_id_unique", table_name="users")
    op.drop_column("users", "telegram_chat_id")
