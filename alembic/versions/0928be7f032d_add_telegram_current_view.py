"""add_telegram_current_view

Revision ID: 0928be7f032d
Revises: r6s7t8u9v0w1
Create Date: 2026-04-24 14:37:26.364844

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = '0928be7f032d'
down_revision: Union[str, Sequence[str], None] = 'r6s7t8u9v0w1'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    """Upgrade schema."""
    op.add_column(
        "users",
        sa.Column("telegram_current_view", sa.String(20), nullable=False, server_default="home"),
    )


def downgrade() -> None:
    """Downgrade schema."""
    op.drop_column("users", "telegram_current_view")
