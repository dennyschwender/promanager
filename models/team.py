"""models/team.py — Team model."""

from __future__ import annotations

from sqlalchemy import ForeignKey, Integer, String
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.database import Base


class Team(Base):
    __tablename__ = "teams"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, index=True)
    name: Mapped[str] = mapped_column(String(128), nullable=False)
    description: Mapped[str | None] = mapped_column(String(512), nullable=True)
    season_id: Mapped[int | None] = mapped_column(
        Integer, ForeignKey("seasons.id", ondelete="SET NULL"), nullable=True, index=True
    )

    # ── Relationships ──────────────────────────────────────────────────────
    season: Mapped[Season | None] = relationship(
        "Season", back_populates="teams", lazy="select"
    )
    players: Mapped[list[Player]] = relationship(
        "Player", back_populates="team", lazy="select"
    )
    player_memberships: Mapped[list[PlayerTeam]] = relationship(
        "PlayerTeam",
        back_populates="team",
        cascade="all, delete-orphan",
        lazy="select",
    )
    events: Mapped[list[Event]] = relationship(
        "Event", back_populates="team", lazy="select"
    )

    def __repr__(self) -> str:
        return f"<Team id={self.id} name={self.name!r}>"
