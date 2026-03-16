"""models/season.py — Season model."""

from __future__ import annotations

from datetime import date

from sqlalchemy import Boolean, Date, Integer, String
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.database import Base


class Season(Base):
    __tablename__ = "seasons"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, index=True)
    name: Mapped[str] = mapped_column(String(128), nullable=False)
    start_date: Mapped[date | None] = mapped_column(Date, nullable=True)
    end_date: Mapped[date | None] = mapped_column(Date, nullable=True)
    is_active: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False)

    # ── Relationships ──────────────────────────────────────────────────────
    events: Mapped[list[Event]] = relationship(
        "Event", back_populates="season", lazy="select"
    )
    player_memberships: Mapped[list[PlayerTeam]] = relationship(
        "PlayerTeam", back_populates="season", lazy="select"
    )

    def __repr__(self) -> str:
        return f"<Season id={self.id} name={self.name!r} active={self.is_active}>"
