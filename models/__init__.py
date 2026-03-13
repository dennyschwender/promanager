"""models/__init__.py — Import all models so Base.metadata is fully populated."""

from .attendance import Attendance
from .event import Event
from .player import Player
from .player_contact import PlayerContact
from .player_phone import PlayerPhone
from .player_team import PlayerTeam
from .season import Season
from .team import Team
from .team_recurring_schedule import TeamRecurringSchedule
from .user import User

__all__ = [
    "User",
    "Season",
    "Team",
    "Player",
    "PlayerTeam",
    "PlayerPhone",
    "PlayerContact",
    "Event",
    "Attendance",
    "TeamRecurringSchedule",
]
