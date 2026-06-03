"""models/event_lineup.py — Per-event group lineup (coach tool)."""

from __future__ import annotations

import json
from datetime import datetime, timezone
from typing import Any

from sqlalchemy import DateTime, ForeignKey, Integer, Text, UniqueConstraint
from sqlalchemy.orm import Mapped, mapped_column

from app.database import Base


class EventLineup(Base):
    __tablename__ = "event_lineups"
    __table_args__ = (UniqueConstraint("event_id", name="uq_event_lineup_event"),)

    id: Mapped[int] = mapped_column(Integer, primary_key=True, index=True)
    event_id: Mapped[int] = mapped_column(
        Integer, ForeignKey("events.id", ondelete="CASCADE"), nullable=False, unique=True, index=True
    )
    groups_json: Mapped[str] = mapped_column(Text, nullable=False, default="[]")
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        nullable=False,
        default=lambda: datetime.now(timezone.utc),
        onupdate=lambda: datetime.now(timezone.utc),
    )

    @property
    def groups(self) -> list[dict[str, Any]]:
        return json.loads(self.groups_json)

    @groups.setter
    def groups(self, value: list[dict[str, Any]]) -> None:
        self.groups_json = json.dumps(value, ensure_ascii=False)
