"""routes/telegram.py — Telegram webhook endpoint."""

from __future__ import annotations

import logging

from fastapi import APIRouter, Header, HTTPException, Request
from fastapi.responses import JSONResponse

from app.config import settings

try:
    from telegram import Update
except ModuleNotFoundError:
    class Update:  # type: ignore[no-redef]
        @staticmethod
        def de_json(data, bot):
            return None

router = APIRouter()
logger = logging.getLogger(__name__)


def _get_app():
    """Return the telegram Application instance (or None if not initialised)."""
    try:
        import bot as _bot  # noqa: PLC0415

        return _bot.telegram_app
    except Exception:
        return None


@router.post("/telegram/webhook", include_in_schema=False)
async def telegram_webhook(
    request: Request,
    x_telegram_bot_api_secret_token: str | None = Header(default=None),
) -> JSONResponse:
    secret = settings.TELEGRAM_WEBHOOK_SECRET
    if not secret or x_telegram_bot_api_secret_token != secret:
        raise HTTPException(status_code=403, detail="Forbidden")

    app = _get_app()
    if app is None:
        return JSONResponse({"ok": True})

    data = await request.json()
    update = Update.de_json(data, app.bot)  # type: ignore[union-attr]
    await app.process_update(update)
    return JSONResponse({"ok": True})
