"""add auto_reminders to teams

Revision ID: 6804a438e2b0
Revises: 208fee070e95
Create Date: 2026-04-16 17:32:21.623429

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = '6804a438e2b0'
down_revision: Union[str, Sequence[str], None] = '208fee070e95'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    with op.batch_alter_table('teams', schema=None) as batch_op:
        batch_op.add_column(sa.Column('auto_reminders', sa.Boolean(), nullable=False, server_default=sa.true()))


def downgrade() -> None:
    with op.batch_alter_table('teams', schema=None) as batch_op:
        batch_op.drop_column('auto_reminders')
