"""Add telegram_notification_message_id column to users table."""
from alembic import op
import sqlalchemy as sa


revision = "r6s7t8u9v0w1"
down_revision = "q5r6s7t8u9v0"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column("users", sa.Column("telegram_notification_message_id", sa.Integer(), nullable=True))


def downgrade() -> None:
    op.drop_column("users", "telegram_notification_message_id")
