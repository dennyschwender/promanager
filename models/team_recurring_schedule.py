"""models/team_recurring_schedule.py — TeamRecurringSchedule model."""

from __future__ import annotations

from datetime import date, time

from sqlalchemy import Date, ForeignKey, Integer, String, Text, Time
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.database import Base


class TeamRecurringSchedule(Base):
    __tablename__ = "team_recurring_schedules"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, index=True)
    team_id: Mapped[int] = mapped_column(
        Integer, ForeignKey("teams.id", ondelete="CASCADE"), nullable=False, index=True
    )
    season_id: Mapped[int | None] = mapped_column(
        Integer, ForeignKey("seasons.id", ondelete="SET NULL"), nullable=True, index=True
    )
    title: Mapped[str] = mapped_column(String(256), nullable=False)
    event_type: Mapped[str] = mapped_column(String(32), nullable=False, default="training")
    recurrence_rule: Mapped[str] = mapped_column(
        String(32),
        nullable=False,  # weekly | biweekly | monthly
    )
    start_date: Mapped[date] = mapped_column(Date, nullable=False)
    end_date: Mapped[date | None] = mapped_column(Date, nullable=True)
    event_time: Mapped[time | None] = mapped_column(Time, nullable=True)
    event_end_time: Mapped[time | None] = mapped_column(Time, nullable=True)
    location: Mapped[str | None] = mapped_column(String(256), nullable=True)
    meeting_time: Mapped[time | None] = mapped_column(Time, nullable=True)
    meeting_location: Mapped[str | None] = mapped_column(String(256), nullable=True)
    presence_type: Mapped[str] = mapped_column(String(32), nullable=False, default="normal")
    description: Mapped[str | None] = mapped_column(Text, nullable=True)
    # UUID string linking this schedule to the events it generated
    recurrence_group_id: Mapped[str] = mapped_column(String(36), nullable=False, unique=True, index=True)

    team: Mapped["Team"] = relationship(  # type: ignore[name-defined]
        "Team", back_populates="recurring_schedules"
    )
    season: Mapped["Season | None"] = relationship("Season")  # type: ignore[name-defined]

    def __repr__(self) -> str:
        return f"<TeamRecurringSchedule id={self.id} title={self.title!r}>"
