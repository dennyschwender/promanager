"""tests/test_telegram_service.py"""
from models.user import User


def test_user_has_telegram_chat_id_field(db):
    user = User(
        username="tgtest",
        email="tgtest@example.com",
        hashed_password="x",
        role="member",
    )
    user.telegram_chat_id = "987654321"
    db.add(user)
    db.commit()
    db.refresh(user)
    assert user.telegram_chat_id == "987654321"
