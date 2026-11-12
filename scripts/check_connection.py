"""Phase 0 smoke test: can we reach the warehouse, and what can the admin connection do?

Reports the server version, the connected role, and whether that role can create
roles (needed by apply-policy). Never prints the connection string.
"""
import os
import sys

import psycopg
from dotenv import load_dotenv


def main() -> int:
    load_dotenv()
    url = os.environ.get("ADMIN_DATABASE_URL")
    if not url or "<" in url:
        print("ADMIN_DATABASE_URL is not set. Copy .env.example to .env and fill it in.")
        return 1

    try:
        with psycopg.connect(url, connect_timeout=10) as conn:
            row = conn.execute(
                """
                select current_setting('server_version'),
                       current_user,
                       r.rolcreaterole,
                       r.rolsuper,
                       exists (select 1 from pg_available_extensions where name = 'pgaudit')
                from pg_roles r where r.rolname = current_user
                """
            ).fetchone()
    except psycopg.OperationalError as e:
        print(f"Connection failed: {e}")
        return 1

    version, user, createrole, superuser, pgaudit = row
    print(f"Connected. Postgres {version} as '{user}'")
    print(f"  CREATEROLE: {createrole}   SUPERUSER: {superuser}   pgaudit available: {pgaudit}")
    if not version.startswith("17"):
        print("  WARNING: CI runs Postgres 17 (ADR-001); this server differs.")
    if not createrole:
        print("  WARNING: this role cannot create roles - apply-policy will fail.")
        return 1
    return 0


if __name__ == "__main__":
    sys.exit(main())
