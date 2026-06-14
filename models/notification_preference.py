"""models/notification_preference.py — Per-player, per-channel opt-in."""

from __future__ import annotations

from enum import StrEnum
from typing import TYPE_CHECKING

from sqlalchemy import Boolean, ForeignKey, Integer, String, UniqueConstraint
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.database import Base


class ChannelType(StrEnum):
    EMAIL = "email"
    INAPP = "inapp"
    WEBPUSH = "webpush"
    TELEGRAM = "telegram"


CHANNELS = tuple(c.value for c in ChannelType)


if TYPE_CHECKING:
    from models.player import Player
    from models.user import User


class NotificationPreference(Base):
    __tablename__ = "notification_preferences"
    # Uniqueness enforced per recipient (either player or user) + channel
    __table_args__ = (
        UniqueConstraint("player_id", "channel", name="uq_notif_pref_player_channel"),
        UniqueConstraint("user_id", "channel", name="uq_notif_pref_user_channel"),
    )

    id: Mapped[int] = mapped_column(Integer, primary_key=True, index=True)
    player_id: Mapped[int | None] = mapped_column(
        Integer, ForeignKey("players.id", ondelete="CASCADE"), nullable=True, index=True
    )
    user_id: Mapped[int | None] = mapped_column(
        Integer, ForeignKey("users.id", ondelete="CASCADE"), nullable=True, index=True
    )
    channel: Mapped[str] = mapped_column(String(32), nullable=False)
    enabled: Mapped[bool] = mapped_column(Boolean, nullable=False, default=True)

    player: Mapped[Player | None] = relationship("Player", back_populates="notification_preferences")
    user: Mapped[User | None] = relationship("User", back_populates="notification_preferences")
