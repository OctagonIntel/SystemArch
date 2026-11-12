"""Generates new passwords for the login roles in the policy (ADR-012).

    python -m scripts.rotate_creds                 rotate every login role (service accounts and people)
    python -m scripts.rotate_creds svc_ingest_hr   rotate just that one
    python -m scripts.rotate_creds --missing-only  only roles with no password in .env yet

The password is hashed here into a SCRAM verifier before it goes to the database,
so the plain text never shows up in server or audit logs. Plain text only lives in
the git-ignored .env.
"""
import argparse
import base64
import hashlib
import hmac
import os
import secrets
import sys

from psycopg import sql

from common.db import ENV_FILE, admin_connect, password_var
from generator.policy import load_policy


def scram_verifier(password: str, iterations: int = 4096) -> str:
    salt = secrets.token_bytes(16)
    salted = hashlib.pbkdf2_hmac("sha256", password.encode(), salt, iterations)
    client_key = hmac.new(salted, b"Client Key", "sha256").digest()
    stored_key = hashlib.sha256(client_key).digest()
    server_key = hmac.new(salted, b"Server Key", "sha256").digest()
    b64 = lambda b: base64.b64encode(b).decode()
    return f"SCRAM-SHA-256${iterations}:{b64(salt)}${b64(stored_key)}:{b64(server_key)}"


def update_env_file(values: dict[str, str]) -> None:
    lines = ENV_FILE.read_text(encoding="utf-8").splitlines() if ENV_FILE.exists() else []
    remaining = dict(values)
    out = []
    for line in lines:
        key = line.split("=", 1)[0].strip()
        out.append(f"{key}={remaining.pop(key)}" if key in remaining else line)
    if remaining:
        if out and out[-1].strip():
            out.append("")
        out.append("# Login passwords (service accounts and people), written by `just rotate-creds`")
        out.extend(f"{k}={v}" for k, v in remaining.items())
    tmp = ENV_FILE.with_suffix(".tmp")
    tmp.write_text("\n".join(out) + "\n", encoding="utf-8")
    tmp.replace(ENV_FILE)


def rotate(roles: list[str] | None = None, missing_only: bool = False) -> list[str]:
    policy = load_policy()
    login_roles = policy.login_roles
    targets = roles or login_roles
    unknown = set(targets) - set(login_roles)
    if unknown:
        raise SystemExit(f"Not login roles in the policy: {', '.join(sorted(unknown))}")
    if missing_only:
        targets = [r for r in targets if not os.environ.get(password_var(r))]
    if not targets:
        return []

    new = {r: secrets.token_urlsafe(32) for r in targets}
    with admin_connect() as conn:
        for role, password in new.items():
            conn.execute(sql.SQL("ALTER ROLE {} PASSWORD {}").format(
                sql.Identifier(role), sql.Literal(scram_verifier(password))))

    env_values = {password_var(r): p for r, p in new.items()}
    update_env_file(env_values)
    os.environ.update(env_values)
    print(f"New passwords set for: {', '.join(targets)} (saved to .env)")
    return targets


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("roles", nargs="*")
    parser.add_argument("--missing-only", action="store_true")
    args = parser.parse_args()
    if not rotate(args.roles or None, args.missing_only):
        print("Nothing to rotate.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
