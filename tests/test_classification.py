"""Every column with personal data has a level (ADR-013), and marts hides everything above public."""
import re

import pytest
from psycopg import sql

HASH = re.compile(r"^[0-9a-f]{16}$")


def columns_of(admin, schema, table):
    return [r[0] for r in admin.execute("""
        select a.attname from pg_attribute a join pg_class c on c.oid = a.attrelid
        join pg_namespace n on n.oid = c.relnamespace
        where n.nspname = %s and c.relname = %s and a.attnum > 0 and not a.attisdropped""", (schema, table)).fetchall()]


def restricted_tables(admin):
    return [r[0] for r in admin.execute("""
        select c.relname from pg_class c join pg_namespace n on n.oid = c.relnamespace
        where n.nspname = 'marts_restricted' and c.relkind = 'r'""").fetchall()]


def test_every_restricted_column_has_a_level(admin, policy):
    missing = [f"{t}.{c}" for t in restricted_tables(admin) for c in columns_of(admin, "marts_restricted", t)
               if c not in policy.declared_columns.get(t, set())]
    assert not missing, f"Give these a level in access.yaml: {missing}"


def test_classified_columns_exist(admin, policy):
    stale = [f"{t}.{c}" for t, cols in policy.declared_columns.items() for c in cols
             if c not in columns_of(admin, "marts_restricted", t)]
    assert not stale, f"Classified in access.yaml but not in the table: {stale}"


@pytest.mark.parametrize("table", ["dim_employee", "dim_customer", "fct_tickets"])
def test_marts_hashes_everything_above_public(admin, policy, table):
    owner = admin.execute("select pg_get_userbyid(relowner) from pg_class where oid = %s::regclass",
                          (f"marts.{table}",)).fetchone()[0]
    admin.execute(sql.SQL("SET ROLE {}").format(sql.Identifier(owner)))
    try:
        for col in policy.classification.get(table, {}):
            bad = admin.execute(sql.SQL("select count(*) from marts.{} where {} is not null and {}::text !~ %s").format(
                sql.Identifier(table), sql.Identifier(col), sql.Identifier(col)), (HASH.pattern,)).fetchone()[0]
            assert bad == 0, f"marts.{table}.{col}: {bad} values aren't hashed"
    finally:
        admin.execute("RESET ROLE")
