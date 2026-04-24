"""bot/__init__.py — Telegram Application factory.

`telegram_app` is None when TELEGRAM_BOT_TOKEN is not configured.
Call `init_application()` to build and initialise the instance.
"""

from __future__ import annotations

import logging

from telegram.ext import Application, CallbackQueryHandler, CommandHandler, MessageHandler, filters

logger = logging.getLogger(__name__)

telegram_app: Application | None = None


def build_application(token: str) -> Application:
    """Build and wire the Application with all handlers."""
    from bot.handlers import (  # noqa: PLC0415
        handle_callback,
        handle_cancel,
        handle_contact,
        handle_logout,
        handle_refresh,
        handle_start,
        handle_text,
    )

    app = Application.builder().token(token).build()
    app.add_handler(CommandHandler("start", handle_start))
    app.add_handler(CommandHandler("logout", handle_logout))
    app.add_handler(CommandHandler("refresh", handle_refresh))
    app.add_handler(CommandHandler("cancel", handle_cancel))
    app.add_handler(MessageHandler(filters.CONTACT, handle_contact))
    app.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, handle_text))
    app.add_handler(CallbackQueryHandler(handle_callback))
    return app


async def init_application(token: str) -> Application:
    """Build and initialise the Application. Stores it in `telegram_app`."""
    global telegram_app
    telegram_app = build_application(token)
    await telegram_app.initialize()
    logger.info("Telegram Application initialised.")
    return telegram_app


async def shutdown_application() -> None:
    """Shut down the Application cleanly."""
    global telegram_app
    if telegram_app is not None:
        await telegram_app.shutdown()
        telegram_app = None
        logger.info("Telegram Application shut down.")
