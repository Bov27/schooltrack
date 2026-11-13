"""Operational commands. They run with the owner connection (MIGRATIONS_DATABASE_URL),
because creating the first platform administrator cannot go through the API.

    python -m app.cli create-platform-admin --email admin@example.test --name "Platform Admin"

    python -m app.cli seed-demo [--lat 2.4419 --lng -76.6063]

The admin password is read from SCHOOLTRACK_ADMIN_PASSWORD, the shared password of the
demo accounts from SCHOOLTRACK_DEMO_PASSWORD; both are prompted for when unset.
"""

import argparse
import getpass
import os
import sys

import psycopg

from app.core.security import hash_password
from app.demo import ACCOUNTS, DemoAlreadyExistsError, seed_demo
from app.modules.identity.service import normalize_email

MIN_PASSWORD_LENGTH = 12


def _owner_dsn() -> str:
    url = os.environ.get("MIGRATIONS_DATABASE_URL")
    if not url:
        sys.exit("MIGRATIONS_DATABASE_URL (owner role) must be set")
    # SQLAlchemy URL -> libpq URL
    return url.replace("postgresql+psycopg://", "postgresql://", 1)


def _read_password(env_var: str = "SCHOOLTRACK_ADMIN_PASSWORD") -> str:
    password = os.environ.get(env_var) or getpass.getpass("Password: ")
    if len(password) < MIN_PASSWORD_LENGTH:
        sys.exit(f"Password must have at least {MIN_PASSWORD_LENGTH} characters")
    return password


def create_platform_admin(email: str, name: str) -> None:
    password_hash = hash_password(_read_password())
    with psycopg.connect(_owner_dsn()) as conn:
        user_id = conn.execute(
            """
            INSERT INTO users (email, full_name, password_hash)
            VALUES (%s, %s, %s)
            ON CONFLICT (email) DO UPDATE
                SET password_hash = EXCLUDED.password_hash, updated_at = now()
            RETURNING id
            """,
            (normalize_email(email), name, password_hash),
        ).fetchone()
        if user_id is None:  # pragma: no cover - RETURNING always yields a row here
            sys.exit("Could not create the user")
        conn.execute(
            "INSERT INTO platform_admins (user_id) VALUES (%s) ON CONFLICT DO NOTHING",
            (user_id[0],),
        )
    print(f"Platform admin ready: {normalize_email(email)} ({user_id[0]})")


def create_demo(lat: float, lng: float, days: int) -> None:
    password = _read_password("SCHOOLTRACK_DEMO_PASSWORD")
    with psycopg.connect(_owner_dsn()) as conn:
        try:
            institution_id = seed_demo(conn, password, center=(lat, lng), days=days)
        except DemoAlreadyExistsError as exc:
            sys.exit(str(exc))
    print(f"Demo institution ready ({institution_id}). Accounts, all with the password you chose:")
    for account in ACCOUNTS:
        print(f"  {account.email:<36} {account.description}")


def main(argv: list[str] | None = None) -> None:
    parser = argparse.ArgumentParser(prog="python -m app.cli")
    commands = parser.add_subparsers(dest="command", required=True)
    admin = commands.add_parser("create-platform-admin", help="Create or reset a Super Admin")
    admin.add_argument("--email", required=True)
    admin.add_argument("--name", required=True)
    demo = commands.add_parser("seed-demo", help="Create the fictional demo institution")
    demo.add_argument("--lat", type=float, default=2.4419, help="Geofence centre latitude")
    demo.add_argument("--lng", type=float, default=-76.6063, help="Geofence centre longitude")
    demo.add_argument("--days", type=int, default=10, help="School days of history")
    args = parser.parse_args(argv)

    if args.command == "create-platform-admin":
        create_platform_admin(args.email, args.name)
    elif args.command == "seed-demo":
        create_demo(args.lat, args.lng, args.days)


if __name__ == "__main__":
    main()
