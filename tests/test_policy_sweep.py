"""Generated from access.yaml: every login against every table in our schemas.
For each one, work out what the policy allows and check the database agrees."""
import pytest
from psycopg import sql

from conftest import ALLOW, DENY
from generator.expected import has_schema_usage, person_access, role_access
from generator.policy import load_policy

WRITES = ["INSERT", "UPDATE", "DELETE", "TRUNCATE"]
POLICY = load_policy()
LOGINS = [p.login for p in POLICY.people] + [r.name for r in POLICY.roles.values() if r.login]


@pytest.fixture(scope="session")
def catalog(admin, policy):
    """Every table in our schemas, with its columns and, if filtered, the regions it holds."""
    tables = []
    for oid, schema, name, owner in admin.execute("""
            select c.oid, n.nspname, c.relname, pg_get_userbyid(c.relowner)
            from pg_class c join pg_namespace n on n.oid = c.relnamespace
            where n.nspname = any(%s) and c.relkind in ('r', 'p', 'v', 'm') order by 2, 3""",
            (list(policy.schemas),)).fetchall():
        cols = [r[0] for r in admin.execute(
            "select attname from pg_attribute where attrelid = %s and attnum > 0 and not attisdropped order by attnum",
            (oid,)).fetchall()]
        regions = None
        column = policy.row_filters.get(f"{schema}.{name}")
        if column:
            admin.execute(sql.SQL("SET ROLE {}").format(sql.Identifier(owner)))
            regions = {r[0] for r in admin.execute(
                sql.SQL("select distinct {} from {}.{}").format(*map(sql.Identifier, (column, schema, name)))).fetchall()}
            admin.execute("RESET ROLE")
        tables.append({"oid": oid, "schema": schema, "name": name, "owner": owner, "columns": cols,
                       "filter": column, "regions": regions})
    return tables


def expected_for(policy, login, t):
    person = next((p for p in policy.people if p.login == login), None)
    if person:
        return person_access(policy, person, t["schema"], t["name"], t["columns"]), list(person.groups)
    return role_access(policy, login, t["schema"], t["name"], t["columns"]), [login]


@pytest.mark.parametrize("login", LOGINS)
def test_login_matches_policy(login, policy, sessions, catalog):
    problems = []
    q = lambda *parts: sql.SQL(" ").join(parts).as_string()

    for t in catalog:
        if t["owner"] == login:
            continue  # owners skip grants (ADR-014); the drift check covers ownership
        rel = sql.Identifier(t["schema"], t["name"])
        exp, roles = expected_for(policy, login, t)
        reads = exp is not None and "SELECT" in exp.privileges and has_schema_usage(policy, roles, t["schema"])
        where = f"{t['schema']}.{t['name']}"

        if not reads:
            outcome, _ = sessions.run(login, q(sql.SQL("select 1 from"), rel, sql.SQL("limit 0")))
            if outcome != DENY:
                problems.append(f"{where}: can read, policy says no")
            continue

        star, _ = sessions.run(login, q(sql.SQL("select * from"), rel, sql.SQL("limit 0")))
        if exp.columns is None or not set(t["columns"]) - exp.columns:
            if star != ALLOW:
                problems.append(f"{where}: can't read, policy says yes")
        else:
            if star != DENY:
                problems.append(f"{where}: reads every column, policy allows only some")
            allowed = [c for c in t["columns"] if c in exp.columns]
            outcome, _ = sessions.run(login, q(sql.SQL("select"), sql.SQL(", ").join(map(sql.Identifier, allowed)),
                                               sql.SQL("from"), rel, sql.SQL("limit 0")))
            if outcome != ALLOW:
                problems.append(f"{where}: can't read the columns the policy allows")
            for col in sorted(set(t["columns"]) - exp.columns):
                outcome, _ = sessions.run(login, q(sql.SQL("select"), sql.Identifier(col), sql.SQL("from"), rel, sql.SQL("limit 0")))
                if outcome != DENY:
                    problems.append(f"{where}.{col}: readable, above this login's clearance")

        if exp.regions is not None:
            want = t["regions"] if "*" in exp.regions else t["regions"] & exp.regions
            _, rows = sessions.run(login, q(sql.SQL("select distinct"), sql.Identifier(t["filter"]), sql.SQL("from"), rel))
            got = {r[0] for r in rows}
            if got != want:
                problems.append(f"{where}: sees regions {sorted(got)}, policy says {sorted(want)}")

    # Write rights, checked as the login itself
    _, rows = sessions.run(login, """
        select c.oid, p from unnest(%s::oid[]) c(oid), unnest(%s::text[]) p
        where has_table_privilege(c.oid, p)""", ([t["oid"] for t in catalog if t["owner"] != login], WRITES))
    actual = {(oid, p) for oid, p in rows}
    expected = set()
    for t in catalog:
        if t["owner"] == login:
            continue
        exp, _ = expected_for(policy, login, t)
        if exp:
            expected |= {(t["oid"], p) for p in exp.privileges if p in WRITES}
    names = {t["oid"]: f"{t['schema']}.{t['name']}" for t in catalog}
    problems += [f"{names[o]}: can {p}, policy says no" for o, p in sorted(actual - expected)]
    problems += [f"{names[o]}: can't {p}, policy says yes" for o, p in sorted(expected - actual)]

    assert not problems, f"{login}:\n  " + "\n  ".join(problems)
