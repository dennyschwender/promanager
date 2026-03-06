#!/usr/bin/env python
"""Create an admin user from the command line.

Usage:
    python scripts/create_admin.py --username admin --email admin@example.com --password secret
"""

from __future__ import annotations

import os
import sys

# Ensure the project root is on the path so app/services imports work.
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

import argparse

from app.database import SessionLocal, init_db
from services.auth_service import create_user, get_user_by_username


def main() -> None:
    parser = argparse.ArgumentParser(description="Create an admin user for ProManager.")
    parser.add_argument("--username", required=True, help="Login username")
    parser.add_argument("--email", required=True, help="Email address")
    parser.add_argument("--password", required=True, help="Plain-text password (min 8 chars)")
    args = parser.parse_args()

    if len(args.password) < 8:
        print("Error: password must be at least 8 characters.", file=sys.stderr)
        sys.exit(1)

    init_db()
    db = SessionLocal()
    try:
        if get_user_by_username(db, args.username):
            print(
                f"Error: username '{args.username}' already exists.",
                file=sys.stderr,
            )
            sys.exit(1)

        user = create_user(db, args.username, args.email, args.password, role="admin")
        print(f"Admin user '{user.username}' (id={user.id}) created successfully.")
    finally:
        db.close()


if __name__ == "__main__":
    main()
