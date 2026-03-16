"""models/player_team.py — Player ↔ Team many-to-many association with priority,
role, position, shirt number, membership status, and season scope."""

from __future__ import annotations

from datetime import date

from sqlalchemy import Boolean, Date, ForeignKey, Integer, String
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.database import Base


class PlayerTeam(Base):
    __tablename__ = "player_teams"
    # No separate UniqueConstraint needed — composite PK already enforces uniqueness.

    player_id: Mapped[int] = mapped_column(Integer, ForeignKey("players.id", ondelete="CASCADE"), primary_key=True)
    team_id: Mapped[int] = mapped_column(Integer, ForeignKey("teams.id", ondelete="CASCADE"), primary_key=True)
    season_id: Mapped[int] = mapped_column(
        Integer, ForeignKey("seasons.id", ondelete="CASCADE"), primary_key=True, index=True
    )
    # 1 = highest priority; higher numbers = lower priority
    priority: Mapped[int] = mapped_column(Integer, nullable=False, default=1)

    # ── Per-team role & position ──────────────────────────────────────
    # "player" | "coach" | "assistant" | "team_leader"
    role: Mapped[str] = mapped_column(String(32), nullable=False, default="player")
    # "goalie" | "defender" | "center" | "forward" | None
    position: Mapped[str | None] = mapped_column(String(32), nullable=True)
    shirt_number: Mapped[int | None] = mapped_column(Integer, nullable=True)

    # ── Membership status ──────────────────────────────────────────
    # "active" | "inactive" | "injured"
    membership_status: Mapped[str] = mapped_column(String(16), nullable=False, default="active")
    injured_until: Mapped[date | None] = mapped_column(Date, nullable=True)
    # When True the player is absent by default for this team's events in this season.
    absent_by_default: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False)

    # ── Relationships ──────────────────────────────────────────────────────
    player: Mapped[Player] = relationship("Player", back_populates="team_memberships")
    team: Mapped[Team] = relationship("Team", back_populates="player_memberships")
    season: Mapped[Season] = relationship("Season", back_populates="player_memberships")

    def __repr__(self) -> str:
        return (
            f"<PlayerTeam player_id={self.player_id} "
            f"team_id={self.team_id} season_id={self.season_id} priority={self.priority}>"
        )
