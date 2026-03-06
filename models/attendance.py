"""models/attendance.py — Attendance model."""

from __future__ import annotations

from datetime import datetime, timezone

from sqlalchemy import DateTime, ForeignKey, Integer, String, UniqueConstraint
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.database import Base


def _utcnow() -> datetime:
    return datetime.now(timezone.utc)


class Attendance(Base):
    __tablename__ = "attendances"
    __table_args__ = (
        UniqueConstraint("event_id", "player_id", name="uq_attendance_event_player"),
    )

    id: Mapped[int] = mapped_column(Integer, primary_key=True, index=True)

    event_id: Mapped[int] = mapped_column(
        Integer,
        ForeignKey("events.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    player_id: Mapped[int] = mapped_column(
        Integer,
        ForeignKey("players.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )

    # "present" | "absent" | "maybe" | "unknown"
    status: Mapped[str] = mapped_column(String(16), nullable=False, default="unknown")

    note: Mapped[str | None] = mapped_column(String(512), nullable=True)
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        nullable=False,
        default=_utcnow,
        onupdate=_utcnow,
    )

    # ── Relationships ──────────────────────────────────────────────────────
    event: Mapped[Event] = relationship(
        "Event", back_populates="attendances", lazy="select"
    )
    player: Mapped[Player] = relationship(
        "Player", back_populates="attendances", lazy="select"
    )

    def __repr__(self) -> str:
        return (
            f"<Attendance id={self.id} event_id={self.event_id} "
            f"player_id={self.player_id} status={self.status!r}>"
        )
