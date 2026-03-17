import pytest
from models.user_team import UserTeam


def test_user_team_importable():
    assert UserTeam.__tablename__ == "user_team"
