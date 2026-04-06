"""models/player_absence.py — Player absence (period or recurring)."""

from __future__ import annotations

from datetime import date, datetime, timezone
from typing import TYPE_CHECKING

from sqlalchemy import Date, DateTime, ForeignKey, Integer, String
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.database import Base

if TYPE_CHECKING:
    from models.player import Player
    from models.season import Season


def _utcnow() -> datetime:
    return datetime.now(timezone.utc)


class PlayerAbsence(Base):
    __tablename__ = "player_absences"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, index=True)

    player_id: Mapped[int] = mapped_column(
        Integer,
        ForeignKey("players.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )

    # "period" | "recurring"
    absence_type: Mapped[str] = mapped_column(String(16), nullable=False)

    # Period absence: start and end date (inclusive, full day)
    start_date: Mapped[date | None] = mapped_column(Date, nullable=True)
    end_date: Mapped[date | None] = mapped_column(Date, nullable=True)

    # Recurring absence: RFC 5545 rrule string (e.g., "FREQ=WEEKLY;BYDAY=FR")
    rrule: Mapped[str | None] = mapped_column(String(256), nullable=True)

    # Optional end date for recurring rule (auto-set to season end if not provided)
    rrule_until: Mapped[date | None] = mapped_column(Date, nullable=True)

    # Season ID for context (required for recurring, optional for period)
    season_id: Mapped[int | None] = mapped_column(
        ForeignKey("seasons.id", ondelete="CASCADE"),
        nullable=True,
        index=True,
    )

    # Reason (e.g., "Injury recovery", "Family vacation")
    reason: Mapped[str | None] = mapped_column(String(512), nullable=True)

    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        nullable=False,
        default=_utcnow,
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        nullable=False,
        default=_utcnow,
        onupdate=_utcnow,
    )

    # ── Relationships ──────────────────────────────────────────────────────
    player: Mapped["Player"] = relationship("Player", back_populates="absences", lazy="select")
    season: Mapped["Season | None"] = relationship("Season", lazy="select")

    def __repr__(self) -> str:
        return f"<PlayerAbsence id={self.id} player_id={self.player_id} type={self.absence_type}>"
