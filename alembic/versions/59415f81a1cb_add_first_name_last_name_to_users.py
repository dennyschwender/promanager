"""add first_name last_name to users

Revision ID: 59415f81a1cb
Revises: a2b3c4d5e6f7
Create Date: 2026-03-30 20:40:14.438016

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = '59415f81a1cb'
down_revision: Union[str, Sequence[str], None] = 'a2b3c4d5e6f7'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    conn = op.get_bind()
    existing_cols = [c["name"] for c in sa.inspect(conn).get_columns("users")]
    with op.batch_alter_table('users', schema=None) as batch_op:
        if 'first_name' not in existing_cols:
            batch_op.add_column(sa.Column('first_name', sa.String(length=64), nullable=True))
        if 'last_name' not in existing_cols:
            batch_op.add_column(sa.Column('last_name', sa.String(length=64), nullable=True))


def downgrade() -> None:
    with op.batch_alter_table('users', schema=None) as batch_op:
        batch_op.drop_column('last_name')
        batch_op.drop_column('first_name')
