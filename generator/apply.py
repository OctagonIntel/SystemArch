"""Applies policy/access.yaml to the warehouse.

    python -m generator.apply          apply it
    python -m generator.apply --plan   just print the SQL

Order, all in one transaction: roles and schemas (as admin), then raw table DDL and
grants (as the owner). Safe to run as often as you like, it converges on the policy.
"""
import argparse
import sys

from psycopg import sql

from common.db import REPO, admin_connect
from generator.policy import Policy, PolicyError, load_policy
from generator.render import render

DDL_DIR = REPO / "ddl"


def ddl_files():
    return sorted(DDL_DIR.glob("*.sql"))


def missing_tables(conn, policy: Policy) -> list[str]:
    wanted = {f"{g.schema}.{g.table}" for r in policy.roles.values() for g in r.table_grants if g.table}
    return sorted(t for t in wanted if conn.execute("select to_regclass(%s)", (t,)).fetchone()[0] is None)


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--plan", action="store_true", help="print the SQL instead of running it")
    args = parser.parse_args()

    try:
        policy = load_policy()
    except PolicyError as e:
        print(f"Policy is invalid: {e}")
        return 1

    part1, part2 = render(policy)

    if args.plan:
        print(part1)
        print(f"SET ROLE {policy.owner};")
        for f in ddl_files():
            print(f"-- {f.relative_to(REPO)}\n{f.read_text(encoding='utf-8')}")
        print(part2)
        print("RESET ROLE;")
        return 0

    with admin_connect() as conn:  # commits on success, rolls back on any error
        conn.execute(part1)
        conn.execute(sql.SQL("SET ROLE {}").format(sql.Identifier(policy.owner)))
        for f in ddl_files():
            conn.execute(f.read_text(encoding="utf-8"))
        missing = missing_tables(conn, policy)
        if missing:
            raise SystemExit(f"Policy grants on tables that don't exist: {', '.join(missing)}")
        conn.execute(part2)
        conn.execute("RESET ROLE")

    print(f"Applied policy: {len(policy.roles)} roles, {len(policy.schemas)} schemas, owner {policy.owner}")

    # New login roles need a password before anything can connect as them (ADR-012).
    from scripts.rotate_creds import rotate
    rotate(missing_only=True)
    return 0


if __name__ == "__main__":
    sys.exit(main())
