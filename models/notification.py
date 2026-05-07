"""models/notification.py — Per-player or per-user notification record.

Either player_id or user_id must be set (not both required, but at least one).
player_id: used for member notifications routed through the player identity.
user_id:   used for admin/coach notifications when no linked player exists.
"""

from __future__ import annotations

from datetime import datetime, timezone

from sqlalchemy import Boolean, DateTime, ForeignKey, Integer, String, Text
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.database import Base


def _utcnow() -> datetime:
    return datetime.now(timezone.utc)


class Notification(Base):
    __tablename__ = "notifications"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, index=True)
    player_id: Mapped[int | None] = mapped_column(
        Integer, ForeignKey("players.id", ondelete="CASCADE"), nullable=True, index=True
    )
    user_id: Mapped[int | None] = mapped_column(
        Integer, ForeignKey("users.id", ondelete="CASCADE"), nullable=True, index=True
    )
    event_id: Mapped[int | None] = mapped_column(
        Integer, ForeignKey("events.id", ondelete="SET NULL"), nullable=True, index=True
    )
    title: Mapped[str] = mapped_column(String(256), nullable=False)
    body: Mapped[str] = mapped_column(Text, nullable=False)
    # "direct" | "announcement"
    tag: Mapped[str] = mapped_column(String(32), nullable=False, default="direct")
    is_read: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False, default=_utcnow)

    player: Mapped[Player | None] = relationship("Player", back_populates="notifications")
    user: Mapped[User | None] = relationship("User", back_populates="notifications")
    event: Mapped[Event | None] = relationship("Event", back_populates="notifications")
