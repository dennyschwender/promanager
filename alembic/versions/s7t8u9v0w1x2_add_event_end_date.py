"""Add event_end_date column to events table."""
from alembic import op
import sqlalchemy as sa

revision = "s7t8u9v0w1x2"
down_revision = "0928be7f032d"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column("events", sa.Column("event_end_date", sa.Date(), nullable=True))


def downgrade() -> None:
    op.drop_column("events", "event_end_date")
