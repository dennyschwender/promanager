"""scripts/cleanup_archived_attendance.py

One-off script: remove future attendance rows for already-archived players.

Run from the project root:
    python scripts/cleanup_archived_attendance.py [--dry-run]
"""

from __future__ import annotations

import argparse
import sys
from datetime import date
from pathlib import Path

# Make sure project root is on the path
sys.path.insert(0, str(Path(__file__).parent.parent))

from sqlalchemy.orm import Session

from app.database import engine
from models.attendance import Attendance
from models.event import Event
from models.player import Player


def run(dry_run: bool = False) -> None:
    today = date.today()

    with Session(engine) as db:
        archived_players = db.query(Player).filter(Player.archived_at.isnot(None)).all()

        if not archived_players:
            print("No archived players found.")
            return

        total_deleted = 0
        for player in archived_players:
            future_ids = [
                r[0]
                for r in db.query(Attendance.id)
                .join(Event, Event.id == Attendance.event_id)
                .filter(Attendance.player_id == player.id, Event.event_date >= today)
                .all()
            ]
            if future_ids:
                print(
                    f"  {'[DRY RUN] Would delete' if dry_run else 'Deleting'} "
                    f"{len(future_ids)} future attendance row(s) for "
                    f"{player.full_name} (archived {player.archived_at.date()})"
                )
                if not dry_run:
                    db.query(Attendance).filter(Attendance.id.in_(future_ids)).delete(
                        synchronize_session=False
                    )
                total_deleted += len(future_ids)

        if not dry_run and total_deleted:
            db.commit()

        print(
            f"\n{'Would remove' if dry_run else 'Removed'} "
            f"{total_deleted} future attendance row(s) across {len(archived_players)} archived player(s)."
        )


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="Clean up future attendance rows for archived players.")
    parser.add_argument("--dry-run", action="store_true", help="Show what would be deleted without making changes.")
    args = parser.parse_args()
    run(dry_run=args.dry_run)
