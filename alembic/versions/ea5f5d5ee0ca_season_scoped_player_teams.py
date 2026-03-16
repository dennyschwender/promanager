"""season_scoped_player_teams

Revision ID: ea5f5d5ee0ca
Revises: a1b2c3d4e5f6
Create Date: 2026-03-16 19:43:23.609790

IMPORTANT: This migration is IRREVERSIBLE. The season_id column on teams is permanently removed.
downgrade() raises NotImplementedError. Back up your database before running.
"""

from __future__ import annotations

from alembic import op
import sqlalchemy as sa

# revision identifiers, used by Alembic.
revision = "ea5f5d5ee0ca"
down_revision = "a1b2c3d4e5f6"
branch_labels = None
depends_on = None


def _get_active_season_id(conn) -> int:
    """Return the id of the single active season. Raises RuntimeError if 0 or 2+."""
    result = conn.execute(sa.text("SELECT id FROM seasons WHERE is_active = 1")).fetchall()
    if len(result) == 0:
        raise RuntimeError(
            "Migration aborted: no active season found. Activate exactly one season before running this migration."
        )
    if len(result) > 1:
        raise RuntimeError(
            f"Migration aborted: {len(result)} active seasons found. "
            "Exactly one season must be active before running this migration."
        )
    return result[0][0]


def upgrade() -> None:
    conn = op.get_bind()

    # Pre-flight: exactly one active season must exist
    active_season_id = _get_active_season_id(conn)

    # ── Step 1: Add season_id to player_teams (nullable for now) ──────────────
    with op.batch_alter_table("player_teams") as batch_op:
        batch_op.add_column(sa.Column("season_id", sa.Integer(), nullable=True))

    # ── Step 2: Populate season_id for all existing rows ──────────────────────
    conn.execute(
        sa.text("UPDATE player_teams SET season_id = :sid"),
        {"sid": active_season_id},
    )

    # ── Step 3: Rebuild player_teams with new PK and NOT NULL season_id ───────
    # `recreate="always"` forces Alembic to fully rebuild the table on SQLite,
    # which is required to change the composite primary key.
    with op.batch_alter_table("player_teams", recreate="always") as batch_op:
        # Drop old unique constraint (it will be replaced by the new PK)
        batch_op.drop_constraint("uq_player_team", type_="unique")
        batch_op.alter_column("season_id", nullable=False)
        # Explicitly set the new composite PK to include season_id
        batch_op.create_primary_key("pk_player_teams", ["player_id", "team_id", "season_id"])
        batch_op.create_foreign_key(
            "fk_player_teams_season_id",
            "seasons",
            ["season_id"],
            ["id"],
            ondelete="CASCADE",
        )
        batch_op.create_index("ix_player_teams_season_id", ["season_id"])

    # ── Step 4: Remove season_id from teams ───────────────────────────────────
    # On SQLite, batch_alter_table with recreate="always" handles implicit FK
    # removal — no explicit drop_constraint needed (unnamed FKs are not tracked).
    with op.batch_alter_table("teams", recreate="always") as batch_op:
        batch_op.drop_index("ix_teams_season_id")
        batch_op.drop_column("season_id")


def downgrade() -> None:
    raise NotImplementedError(
        "This migration is intentionally irreversible. "
        "The season_id data on teams has been permanently removed. "
        "Restore from a database backup to revert."
    )
