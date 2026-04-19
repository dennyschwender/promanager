"""add calendar_token to users

Revision ID: p4q5r6s7t8u9
Revises: o3p4q5r6s7t8
Create Date: 2026-04-19
"""
from collections.abc import Sequence
from typing import Union

import sqlalchemy as sa
from alembic import op

revision: str = "p4q5r6s7t8u9"
down_revision: Union[str, Sequence[str], None] = "o3p4q5r6s7t8"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    with op.batch_alter_table("users", schema=None) as batch_op:
        batch_op.add_column(sa.Column("calendar_token", sa.String(64), nullable=True))
        batch_op.create_unique_constraint("uq_users_calendar_token", ["calendar_token"])
        batch_op.create_index("ix_users_calendar_token", ["calendar_token"], unique=True)


def downgrade() -> None:
    with op.batch_alter_table("users", schema=None) as batch_op:
        batch_op.drop_index("ix_users_calendar_token")
        batch_op.drop_constraint("uq_users_calendar_token", type_="unique")
        batch_op.drop_column("calendar_token")
