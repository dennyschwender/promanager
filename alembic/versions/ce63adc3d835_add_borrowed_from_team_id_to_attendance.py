"""add borrowed_from_team_id to attendance

Revision ID: ce63adc3d835
Revises: bc81f0482c61
Create Date: 2026-03-23 22:59:21.487049

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = 'ce63adc3d835'
down_revision: Union[str, Sequence[str], None] = 'bc81f0482c61'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    with op.batch_alter_table("attendances", schema=None) as batch_op:
        batch_op.add_column(sa.Column("borrowed_from_team_id", sa.Integer(), nullable=True))
        batch_op.create_foreign_key(
            "fk_attendance_borrowed_from_team_id",
            "teams",
            ["borrowed_from_team_id"],
            ["id"],
            ondelete="SET NULL",
        )


def downgrade() -> None:
    with op.batch_alter_table("attendances", schema=None) as batch_op:
        batch_op.drop_constraint("fk_attendance_borrowed_from_team_id", type_="foreignkey")
        batch_op.drop_column("borrowed_from_team_id")
