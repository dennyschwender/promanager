#!/usr/bin/env python
"""Copy the SQLite database file with a timestamp suffix.

Usage:
    python scripts/backup_db.py [--dest /path/to/backups]

If --dest is omitted, backups are written to the ``data/backups/`` directory
next to the database file.
"""

from __future__ import annotations

import argparse
import os
import shutil
import sys
from datetime import datetime

# Ensure the project root is on the path so app imports work.
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from app.config import settings


def _db_path_from_url(url: str) -> str:
    """Extract the filesystem path from a sqlite:/// URL."""
    # sqlite:///./data/proManager.db  → ./data/proManager.db
    # sqlite:////abs/path/db.sqlite     → /abs/path/db.sqlite
    if url.startswith("sqlite:///"):
        return url[len("sqlite:///"):]
    raise ValueError(f"Unsupported DATABASE_URL scheme for backup: {url!r}")


def main() -> None:
    parser = argparse.ArgumentParser(description="Backup the ProManager SQLite database.")
    parser.add_argument(
        "--dest",
        default=None,
        help="Directory to write the backup file into. "
             "Defaults to data/backups/ relative to the project root.",
    )
    args = parser.parse_args()

    # Resolve the source DB path (may be relative, resolve from cwd)
    try:
        raw_path = _db_path_from_url(settings.DATABASE_URL)
    except ValueError as exc:
        print(f"Error: {exc}", file=sys.stderr)
        sys.exit(1)

    src = os.path.abspath(raw_path)

    if not os.path.isfile(src):
        print(f"Error: database file not found at {src!r}.", file=sys.stderr)
        sys.exit(1)

    # Determine destination directory
    if args.dest:
        dest_dir = os.path.abspath(args.dest)
    else:
        # Default: data/backups/ next to the DB file
        dest_dir = os.path.join(os.path.dirname(src), "backups")

    os.makedirs(dest_dir, exist_ok=True)

    # Build timestamped filename:  proManager_2026-02-27T14-30-00.db
    timestamp = datetime.now().strftime("%Y-%m-%dT%H-%M-%S")
    base_name = os.path.basename(src)
    stem, ext = os.path.splitext(base_name)
    dest_name = f"{stem}_{timestamp}{ext}"
    dest_path = os.path.join(dest_dir, dest_name)

    shutil.copy2(src, dest_path)
    print(f"Backup written to: {dest_path}")


if __name__ == "__main__":
    main()
