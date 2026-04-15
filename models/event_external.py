"""models/event_external.py — External (non-registered) participant for an event."""

from __future__ import annotations

from datetime import datetime, timezone

from sqlalchemy import DateTime, ForeignKey, Integer, String
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.database import Base


def _utcnow() -> datetime:
    return datetime.now(timezone.utc)


class EventExternal(Base):
    __tablename__ = "event_externals"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, index=True)
    event_id: Mapped[int] = mapped_column(
        Integer, ForeignKey("events.id", ondelete="CASCADE"), nullable=False, index=True
    )
    first_name: Mapped[str] = mapped_column(String(128), nullable=False)
    last_name: Mapped[str] = mapped_column(String(128), nullable=False)
    note: Mapped[str | None] = mapped_column(String(512), nullable=True)
    # "present" | "absent" | "maybe" | "unknown"
    status: Mapped[str] = mapped_column(String(16), nullable=False, default="unknown")
    # "goalie" | "defender" | "center" | "forward" | None
    position: Mapped[str | None] = mapped_column(String(32), nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False, default=_utcnow)

    event: Mapped["Event"] = relationship("Event", back_populates="externals", lazy="select")  # noqa: F821

    @property
    def full_name(self) -> str:
        return f"{self.first_name} {self.last_name}"

    def __repr__(self) -> str:
        return f"<EventExternal id={self.id} event_id={self.event_id} name={self.full_name!r} status={self.status!r}>"
