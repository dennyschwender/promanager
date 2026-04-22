"""models/event.py — Event model."""

from __future__ import annotations

from datetime import date, datetime, time, timezone

from sqlalchemy import Boolean, Date, DateTime, ForeignKey, Integer, String, Text, Time
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.database import Base


def _utcnow() -> datetime:
    return datetime.now(timezone.utc)


class Event(Base):
    __tablename__ = "events"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, index=True)
    title: Mapped[str] = mapped_column(String(256), nullable=False)

    # "match" | "training" | "other"
    event_type: Mapped[str] = mapped_column(String(32), nullable=False, default="training")

    event_date: Mapped[date] = mapped_column(Date, nullable=False, index=True)
    event_time: Mapped[time | None] = mapped_column(Time, nullable=True)
    event_end_time: Mapped[time | None] = mapped_column(Time, nullable=True)
    location: Mapped[str | None] = mapped_column(String(256), nullable=True)
    meeting_time: Mapped[time | None] = mapped_column(Time, nullable=True)
    meeting_location: Mapped[str | None] = mapped_column(String(256), nullable=True)
    # "normal" | "all" | "selection" | "available" | "no_registration"
    presence_type: Mapped[str] = mapped_column(String(32), nullable=False, default="normal")
    description: Mapped[str | None] = mapped_column(Text, nullable=True)

    season_id: Mapped[int | None] = mapped_column(
        Integer,
        ForeignKey("seasons.id", ondelete="SET NULL"),
        nullable=True,
        index=True,
    )
    team_id: Mapped[int | None] = mapped_column(
        Integer,
        ForeignKey("teams.id", ondelete="SET NULL"),
        nullable=True,
        index=True,
    )

    # ── Recurrence ──────────────────────────────────────────────────────────
    # Shared UUID string for events belonging to the same recurring series.
    recurrence_group_id: Mapped[str | None] = mapped_column(String(36), nullable=True, index=True)
    # "weekly" | "biweekly" | "monthly" — set on every event in the series.
    recurrence_rule: Mapped[str | None] = mapped_column(String(32), nullable=True)

    hide_attendance: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False)
    reminder_sent: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False, default=_utcnow)

    # ── Relationships ──────────────────────────────────────────────────────
    season: Mapped[Season | None] = relationship("Season", back_populates="events", lazy="select")
    team: Mapped[Team | None] = relationship("Team", back_populates="events", lazy="select")
    attendances: Mapped[list[Attendance]] = relationship(
        "Attendance", back_populates="event", lazy="select", cascade="all, delete-orphan"
    )
    notifications: Mapped[list[Notification]] = relationship(
        "Notification",
        back_populates="event",
        cascade="save-update, merge",  # NOT delete-orphan — DB uses ondelete="SET NULL"
        lazy="select",
    )
    telegram_notifications: Mapped[list["TelegramNotification"]] = relationship(  # noqa: F821
        back_populates="event", cascade="all, delete-orphan"
    )
    externals: Mapped[list[EventExternal]] = relationship(  # noqa: F821
        "EventExternal", back_populates="event", lazy="select", cascade="all, delete-orphan"
    )
    messages: Mapped[list["EventMessage"]] = relationship(  # noqa: F821
        "EventMessage", back_populates="event", lazy="select", cascade="all, delete-orphan"
    )

    def __repr__(self) -> str:
        return f"<Event id={self.id} title={self.title!r} date={self.event_date}>"
