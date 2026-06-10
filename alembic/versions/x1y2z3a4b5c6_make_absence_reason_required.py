"""make absence reason required

Revision ID: x1y2z3a4b5c6
Revises: w5x6y7z8a9b0
Create Date: 2026-06-10

"""

from __future__ import annotations

from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op

revision: str = "x1y2z3a4b5c6"
down_revision: Union[str, None] = "w5x6y7z8a9b0"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    with op.batch_alter_table("player_absences") as batch_op:
        batch_op.alter_column("reason", existing_type=sa.String(512), nullable=False)


def downgrade() -> None:
    with op.batch_alter_table("player_absences") as batch_op:
        batch_op.alter_column("reason", existing_type=sa.String(512), nullable=True)
