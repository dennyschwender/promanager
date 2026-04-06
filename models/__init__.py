"""models/__init__.py — Import all models so Base.metadata is fully populated."""

from .attendance import Attendance
from .event_external import EventExternal
from .event_message import EventMessage
from .event import Event
from .notification import Notification
from .notification_preference import NotificationPreference
from .player import Player
from .player_absence import PlayerAbsence
from .player_contact import PlayerContact
from .player_phone import PlayerPhone
from .player_team import PlayerTeam
from .season import Season
from .team import Team
from .team_recurring_schedule import TeamRecurringSchedule
from .user import User
from .user_team import UserTeam as UserTeam  # noqa: F401
from .web_push_subscription import WebPushSubscription

__all__ = [
    "User",
    "Season",
    "Team",
    "Player",
    "PlayerAbsence",
    "PlayerTeam",
    "PlayerPhone",
    "PlayerContact",
    "Event",
    "Attendance",
    "EventExternal",
    "EventMessage",
    "TeamRecurringSchedule",
    "Notification",
    "NotificationPreference",
    "WebPushSubscription",
    "UserTeam",
]
