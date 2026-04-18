"""Add player_type to players and backfill staff player records.

Revision ID: o3p4q5r6s7t8
Revises: n2o3p4q5r6s7
Create Date: 2026-04-18
"""

from __future__ import annotations

import sqlalchemy as sa
from alembic import op

revision = "o3p4q5r6s7t8"
down_revision = "n2o3p4q5r6s7"
branch_labels = None
depends_on = None


def upgrade() -> None:
    # Add player_type column
    op.add_column("players", sa.Column("player_type", sa.String(16), nullable=False, server_default="player"))

    # Backfill: create Player records for users with no linked player
    conn = op.get_bind()
    users = conn.execute(
        sa.text("""
            SELECT u.id, u.first_name, u.last_name, u.email, u.phone, u.role
            FROM users u
            WHERE u.role IN ('admin', 'coach')
              AND NOT EXISTS (SELECT 1 FROM players p WHERE p.user_id = u.id)
        """)
    ).fetchall()

    for user in users:
        first_name = user.first_name or user.role.capitalize()
        last_name = user.last_name or ""
        conn.execute(
            sa.text("""
                INSERT INTO players (first_name, last_name, email, phone, is_active, player_type, user_id)
                VALUES (:first_name, :last_name, :email, :phone, 1, :player_type, :user_id)
            """),
            {
                "first_name": first_name,
                "last_name": last_name,
                "email": user.email,
                "phone": user.phone,
                "player_type": user.role,
                "user_id": user.id,
            },
        )


def downgrade() -> None:
    # Remove backfilled staff players
    conn = op.get_bind()
    conn.execute(sa.text("DELETE FROM players WHERE player_type IN ('admin', 'coach')"))
    op.drop_column("players", "player_type")
