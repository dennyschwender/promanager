"""services/scheduler.py — Background scheduler jobs (asyncio-based, no extra deps)."""

from __future__ import annotations

import asyncio
import logging
from datetime import datetime, timedelta, timezone

from services.email_service import send_event_reminder

logger = logging.getLogger(__name__)


def send_due_reminders() -> int:
    """Send reminder emails for events whose reminder window has arrived.

    Finds events where:
    - reminder_sent is False
    - event_date/time is within REMINDER_HOURS_BEFORE hours from now
    - event has not already passed

    Marks event.reminder_sent = True after sending.
    Returns the total number of emails sent.
    """
    from app.config import settings
    from app.database import SessionLocal
    from models.attendance import Attendance
    from models.event import Event
    from services.auth_service import create_magic_link
    from services.notification_service import get_preference

    db = SessionLocal()
    total_sent = 0
    try:
        now = datetime.now(timezone.utc)
        cutoff = now + timedelta(hours=settings.REMINDER_HOURS_BEFORE)
        cutoff_date = cutoff.date()
        today = now.date()

        # Events that are due for a reminder: upcoming, reminder not yet sent
        events = (
            db.query(Event)
            .filter(
                Event.reminder_sent.is_(False),
                Event.event_date >= today,
                Event.event_date <= cutoff_date,
            )
            .all()
        )

        for event in events:
            # Skip events whose team has auto_reminders disabled
            if event.team_id and event.team and not event.team.auto_reminders:
                continue

            # Precise time-based window check — only when event has a time set.
            # Events with no time use the date-level filter above; we don't skip
            # them based on time since we don't know when they happen.
            if event.event_time:
                event_dt = datetime.combine(event.event_date, event.event_time).replace(tzinfo=timezone.utc)
                if event_dt < now:
                    # Event is already in the past — mark sent to avoid repeated checks
                    event.reminder_sent = True
                    db.add(event)
                    continue
                if event_dt > cutoff:
                    # Not yet within the reminder window
                    continue

            # Find attendances with unknown status that have a player email
            attendances = (
                db.query(Attendance)
                .filter(
                    Attendance.event_id == event.id,
                    Attendance.status == "unknown",
                )
                .all()
            )

            sent = 0
            for att in attendances:
                player = att.player
                if not player or not player.email:
                    continue
                # Respect player's email notification preference (default True if not set)
                if not get_preference(player.id, "email", db):
                    continue
                magic = (
                    create_magic_link(player.user.id, f"/events/{event.id}", player.user.email)  # type: ignore[union-attr, arg-type]
                    if player.user_id
                    else None
                )
                ok = send_event_reminder(
                    player_email=player.email,
                    player_name=player.full_name,
                    event_title=event.title,
                    event_date=event.event_date,
                    event_time=event.event_time,
                    event_location=event.location or "",
                    locale=getattr(player, "locale", None) or "en",
                    magic_link=magic,
                )
                if ok:
                    sent += 1

            # Dispatch in-app / web push / Telegram for the same recipients.
            # Email is handled above with personalized magic links — exclude here.
            if attendances:
                from services.notification_service import send_notifications  # noqa: PLC0415

                event_time_str = event.event_time.strftime("%H:%M") if event.event_time else ""
                notif_body = str(event.event_date) + (f" {event_time_str}" if event_time_str else "")
                if event.location:
                    notif_body += f" · {event.location}"
                send_notifications(
                    event=event,
                    title=f"⏰ Reminder: {event.title}",
                    body=notif_body,
                    tag="reminder",
                    recipient_statuses=["unknown"],
                    admin_channels=["inapp", "webpush", "telegram"],
                    db=db,
                    background_tasks=None,
                )

            event.reminder_sent = True
            db.add(event)
            total_sent += sent
            logger.info("Reminder: sent %d emails for event %r (id=%d)", sent, event.title, event.id)

        db.commit()
    except Exception:
        logger.exception("Reminder job failed")
        db.rollback()
    finally:
        db.close()

    return total_sent


async def reminder_loop(interval_seconds: int = 900) -> None:
    """Run send_due_reminders every `interval_seconds` (default 15 min).

    Designed to be started as an asyncio background task from the lifespan.
    Exits cleanly when the task is cancelled on shutdown.
    """
    logger.info("Reminder scheduler started (interval=%ds)", interval_seconds)
    while True:
        try:
            await asyncio.sleep(interval_seconds)
            sent = await asyncio.get_event_loop().run_in_executor(None, send_due_reminders)
            if sent:
                logger.info("Reminder scheduler: %d email(s) dispatched", sent)
        except asyncio.CancelledError:
            logger.info("Reminder scheduler stopped.")
            break
        except Exception:
            logger.exception("Unexpected error in reminder loop — continuing")


def backup_database() -> str | None:
    """Create a timestamped SQLite backup in data/backups/.

    Prunes files older than BACKUP_KEEP_DAYS days.
    Returns the backup file path on success, None on failure or non-SQLite DB.
    """
    import os
    import shutil
    from datetime import datetime, timedelta

    from app.config import settings

    url = settings.DATABASE_URL
    if not url.startswith("sqlite:///"):
        logger.debug("Backup skipped — not a SQLite database (%s)", url)
        return None

    raw_path = url[len("sqlite:///") :]
    src = os.path.abspath(raw_path)
    if not os.path.isfile(src):
        logger.warning("Backup skipped — database file not found at %r", src)
        return None

    dest_dir = os.path.join(os.path.dirname(src), "backups")
    os.makedirs(dest_dir, exist_ok=True)

    timestamp = datetime.now().strftime("%Y-%m-%dT%H-%M-%S")
    stem, ext = os.path.splitext(os.path.basename(src))
    dest_path = os.path.join(dest_dir, f"{stem}_{timestamp}{ext}")

    shutil.copy2(src, dest_path)
    logger.info("Backup written to %r", dest_path)

    # Prune backups older than BACKUP_KEEP_DAYS
    cutoff = datetime.now() - timedelta(days=settings.BACKUP_KEEP_DAYS)
    pruned = 0
    for fname in os.listdir(dest_dir):
        fpath = os.path.join(dest_dir, fname)
        if os.path.isfile(fpath) and os.path.getmtime(fpath) < cutoff.timestamp():
            os.remove(fpath)
            pruned += 1
    if pruned:
        logger.info("Backup pruner: removed %d old backup(s)", pruned)

    return dest_path


def cleanup_expired_injury_absences() -> int:
    """Delete expired Injury absences and revert future attendance.

    Runs in a thread executor; must not share DB sessions across threads.
    Returns the number of absences cleaned up.
    """
    from app.database import SessionLocal
    from services.absence_service import cleanup_expired_injury_absences as _do_cleanup

    db = SessionLocal()
    try:
        return _do_cleanup(db)
    except Exception:
        logger.exception("Injury cleanup failed")
        db.rollback()
        return 0
    finally:
        db.close()


async def cleanup_loop(interval_seconds: int = 3600) -> None:
    """Run cleanup_expired_injury_absences every `interval_seconds` (default 1h).

    Designed to be started as an asyncio background task from the lifespan.
    """
    logger.info("Injury cleanup scheduler started (interval=%ds)", interval_seconds)
    await asyncio.sleep(300)
    while True:
        try:
            await asyncio.sleep(interval_seconds)
            count = await asyncio.get_event_loop().run_in_executor(None, cleanup_expired_injury_absences)
            if count:
                logger.info("Injury cleanup: removed %d expired absence(s)", count)
        except asyncio.CancelledError:
            logger.info("Injury cleanup scheduler stopped.")
            break
        except Exception:
            logger.exception("Unexpected error in injury cleanup loop — continuing")


async def backup_loop(interval_seconds: int = 86400) -> None:
    """Run backup_database once a day.

    Designed to be started as an asyncio background task from the lifespan.
    Runs the first backup shortly after startup (60s), then every 24h.
    """
    logger.info("Backup scheduler started (interval=%ds)", interval_seconds)
    # Short initial delay so startup noise settles before the first backup
    await asyncio.sleep(60)
    while True:
        try:
            path = await asyncio.get_event_loop().run_in_executor(None, backup_database)
            if path:
                logger.info("Backup scheduler: backup complete → %s", path)
        except asyncio.CancelledError:
            logger.info("Backup scheduler stopped.")
            break
        except Exception:
            logger.exception("Unexpected error in backup loop — continuing")
        try:
            await asyncio.sleep(interval_seconds)
        except asyncio.CancelledError:
            logger.info("Backup scheduler stopped.")
            break
