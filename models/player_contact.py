"""models/player_contact.py — Optional emergency/personal contact for a player."""

from __future__ import annotations

from sqlalchemy import ForeignKey, Integer, String
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.database import Base


class PlayerContact(Base):
    __tablename__ = "player_contacts"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, index=True)
    player_id: Mapped[int] = mapped_column(
        Integer, ForeignKey("players.id", ondelete="CASCADE"), nullable=False, unique=True, index=True
    )
    # Relationship to the player (e.g. "Parent", "Spouse", "Guardian")
    relationship_label: Mapped[str | None] = mapped_column(String(64), nullable=True)

    first_name: Mapped[str] = mapped_column(String(64), nullable=False)
    last_name: Mapped[str] = mapped_column(String(64), nullable=False)
    email: Mapped[str | None] = mapped_column(String(128), nullable=True)
    phone: Mapped[str | None] = mapped_column(String(32), nullable=True)
    phone2: Mapped[str | None] = mapped_column(String(32), nullable=True)

    street: Mapped[str | None] = mapped_column(String(256), nullable=True)
    postcode: Mapped[str | None] = mapped_column(String(16), nullable=True)
    city: Mapped[str | None] = mapped_column(String(128), nullable=True)

    player: Mapped[Player] = relationship("Player", back_populates="contact")

    @property
    def full_name(self) -> str:
        return f"{self.first_name} {self.last_name}"

    def __repr__(self) -> str:
        return f"<PlayerContact player_id={self.player_id} name={self.full_name!r}>"
