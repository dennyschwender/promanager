"""models/team.py — Team model (season-independent)."""

from __future__ import annotations

from sqlalchemy import Boolean, Integer, String
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.database import Base


class Team(Base):
    __tablename__ = "teams"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, index=True)
    name: Mapped[str] = mapped_column(String(128), nullable=False)
    description: Mapped[str | None] = mapped_column(String(512), nullable=True)
    auto_reminders: Mapped[bool] = mapped_column(Boolean, nullable=False, default=True)

    # ── Relationships ──────────────────────────────────────────────────────
    player_memberships: Mapped[list[PlayerTeam]] = relationship(
        "PlayerTeam",
        back_populates="team",
        cascade="all, delete-orphan",
        lazy="select",
    )
    coaches: Mapped[list["UserTeam"]] = relationship(back_populates="team", cascade="all, delete-orphan")  # noqa: F821
    events: Mapped[list[Event]] = relationship("Event", back_populates="team", lazy="select")
    recurring_schedules: Mapped[list["TeamRecurringSchedule"]] = relationship(  # type: ignore[name-defined]
        "TeamRecurringSchedule",
        back_populates="team",
        cascade="all, delete-orphan",
        lazy="select",
    )

    def __repr__(self) -> str:
        return f"<Team id={self.id} name={self.name!r}>"
