"""add_user_locale

Revision ID: a1b2c3d4e5f6
Revises: 17990e6d0210
Create Date: 2026-03-14

"""
from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op

revision: str = "a1b2c3d4e5f6"
down_revision: Union[str, Sequence[str], None] = "17990e6d0210"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.add_column(
        "users",
        sa.Column("locale", sa.String(5), nullable=False, server_default="en"),
    )


def downgrade() -> None:
    op.drop_column("users", "locale")
