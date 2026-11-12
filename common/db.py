"""Connection helpers. Only apply-policy and rotate-creds use the admin connection,
everything else connects as its own role."""
import os
from pathlib import Path

import psycopg
from dotenv import load_dotenv

REPO = Path(__file__).resolve().parent.parent
ENV_FILE = REPO / ".env"
load_dotenv(ENV_FILE)


def password_var(role: str) -> str:
    return f"{role.upper()}_PASSWORD"


def login_name(role: str) -> str:
    """Supabase's pooler wants role.project_ref as the username. Plain Postgres (CI) doesn't."""
    ref = os.environ.get("SUPABASE_PROJECT_REF")
    return f"{role}.{ref}" if ref else role


def admin_connect(**kwargs) -> psycopg.Connection:
    url = os.environ.get("ADMIN_DATABASE_URL")
    if not url or "<" in url:
        raise SystemExit("ADMIN_DATABASE_URL isn't set. Copy .env.example to .env and fill it in.")
    return psycopg.connect(url, connect_timeout=10, **kwargs)


def connect_as(role: str, **kwargs) -> psycopg.Connection:
    password = os.environ.get(password_var(role))
    if not password:
        raise SystemExit(f"{password_var(role)} isn't set. Run `just apply-policy` or `just rotate-creds`.")
    conn = psycopg.connect(
        host=os.environ["DB_HOST"],
        port=os.environ.get("DB_PORT", "5432"),
        dbname=os.environ.get("DB_NAME", "postgres"),
        user=login_name(role),
        password=password,
        connect_timeout=10,
        **kwargs,
    )
    actual = conn.execute("select current_user").fetchone()[0]
    if actual != role:
        conn.close()
        raise RuntimeError(f"Expected to be connected as {role} but the database says {actual}")
    return conn
