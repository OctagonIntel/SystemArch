"""Compares the live database with the policy and lists every difference.

    python -m drift.check           exit 1 if anything drifted
    python -m drift.check --json    machine-readable, for the report

Scope (ADR-015): our schemas and every role the policy manages. Any grant in our
schemas to a role the policy doesn't know is drift too.
"""
import argparse
import json
import re
import sys
from dataclasses import asdict, dataclass

from psycopg import sql

from common.db import admin_connect
from generator.expected import role_access
from generator.policy import Policy, load_policy
from generator.render import _rules

RELKINDS = ("r", "p", "v", "m")
WRITE_ATTRS = ("rolsuper", "rolcreaterole", "rolcreatedb", "rolbypassrls", "rolreplication")
PRIV_NAMES = {"r": "SELECT", "a": "INSERT", "w": "UPDATE", "d": "DELETE", "D": "TRUNCATE", "x": "REFERENCES", "t": "TRIGGER"}


@dataclass(frozen=True)
class Finding:
    area: str
    object: str
    problem: str

    def __str__(self):
        return f"{self.area:<11} {self.object:<45} {self.problem}"


def _diff(area, obj, expected: set, actual: set, what: str) -> list[Finding]:
    out = [Finding(area, obj, f"extra {what}: {x}") for x in sorted(actual - expected)]
    out += [Finding(area, obj, f"missing {what}: {x}") for x in sorted(expected - actual)]
    return out


def check_roles(conn, policy: Policy, admin: str) -> list[Finding]:
    found = []
    rows = {r[0]: r for r in conn.execute(
        f"select rolname, rolcanlogin, {', '.join(WRITE_ATTRS)}, "
        "shobj_description(oid, 'pg_authid') from pg_roles").fetchall()}

    expected_login = {policy.owner: False}
    expected_login.update({r.name: r.login for r in policy.roles.values()})
    expected_login.update({p.login: True for p in policy.people})

    for name, login in expected_login.items():
        row = rows.get(name)
        if row is None:
            found.append(Finding("role", name, "doesn't exist"))
            continue
        if row[1] != login:
            found.append(Finding("role", name, f"login is {row[1]}, policy says {login}"))
        for attr, value in zip(WRITE_ATTRS, row[2:7]):
            if value:
                found.append(Finding("role", name, f"has {attr.removeprefix('rol').upper()}"))

    people = {p.login for p in policy.people}
    for name, row in rows.items():
        comment = row[7] or ""
        if comment.startswith("person: ") and name not in people:
            found.append(Finding("role", name, "is a person who isn't in people.yaml"))
        if comment.startswith("left: ") and row[1]:
            found.append(Finding("role", name, "left but can still log in"))

    # Memberships. The admin is a member of roles it created or acts as, that's expected.
    managed = set(expected_login)
    expected = {(g, p.login) for p in policy.people for g in p.groups}
    actual = {
        (role, member) for role, member in conn.execute(
            "select roleid::regrole::text, member::regrole::text from pg_auth_members").fetchall()
        if (role in managed or member in managed) and member != admin
    }
    found += _diff("membership", "group -> member", expected, actual, "membership")
    return found


def _acl(conn, query: str, params) -> set[tuple[str, str]]:
    return {(g, p) for g, p in conn.execute(query, params).fetchall()}


def check_schemas(conn, policy: Policy) -> list[Finding]:
    found = []
    for schema in policy.schemas:
        row = conn.execute(
            "select pg_get_userbyid(nspowner) from pg_namespace where nspname = %s", (schema,)).fetchone()
        if row is None:
            found.append(Finding("schema", schema, "doesn't exist"))
            continue
        if row[0] != policy.owner:
            found.append(Finding("schema", schema, f"owned by {row[0]}, should be {policy.owner}"))
        actual = _acl(conn, """
            select case a.grantee when 0 then 'PUBLIC' else pg_get_userbyid(a.grantee) end, a.privilege_type
            from pg_namespace n, aclexplode(coalesce(n.nspacl, acldefault('n', n.nspowner))) a
            where n.nspname = %s and a.grantee <> n.nspowner""", (schema,))
        expected = {(r.name, p) for r in policy.roles.values() for p in r.schema_grants.get(schema, ())}
        found += _diff("schema", schema, expected, actual, "grant")
    return found


def check_relations(conn, policy: Policy) -> list[Finding]:
    found = []
    rels = conn.execute("""
        select c.oid, n.nspname, c.relname, pg_get_userbyid(c.relowner), c.relrowsecurity
        from pg_class c join pg_namespace n on n.oid = c.relnamespace
        where n.nspname = any(%s) and c.relkind = any(%s)
        order by 2, 3""", (list(policy.schemas), list(RELKINDS))).fetchall()

    for oid, schema, table, owner, rls in rels:
        obj = f"{schema}.{table}"
        creators = {r.name for r in policy.roles.values() if "CREATE" in r.schema_grants.get(schema, ())}
        if owner != policy.owner and owner not in creators:
            found.append(Finding("owner", obj, f"owned by {owner}, who can't create in {schema}"))

        columns = [r[0] for r in conn.execute(
            "select attname from pg_attribute where attrelid = %s and attnum > 0 and not attisdropped order by attnum",
            (oid,)).fetchall()]

        expected_table, expected_cols, expected_policies = set(), set(), {}
        for role in policy.roles:
            if role == owner:
                continue
            access = role_access(policy, role, schema, table, columns)
            if access is None:
                continue
            if access.columns is None:
                expected_table |= {(role, p) for p in access.privileges}
            else:
                expected_cols |= {(role, f"{c} SELECT") for c in access.columns}
            if access.regions is not None:
                expected_policies[f"{role}_rows"] = (role, access.regions)

        actual_table = _acl(conn, """
            select case a.grantee when 0 then 'PUBLIC' else pg_get_userbyid(a.grantee) end, a.privilege_type
            from pg_class c, aclexplode(coalesce(c.relacl, acldefault('r', c.relowner))) a
            where c.oid = %s and a.grantee <> c.relowner""", (oid,))
        actual_cols = _acl(conn, """
            select case a.grantee when 0 then 'PUBLIC' else pg_get_userbyid(a.grantee) end,
                   att.attname || ' ' || a.privilege_type
            from pg_attribute att, aclexplode(att.attacl) a
            where att.attrelid = %s and att.attnum > 0 and att.attacl is not null""", (oid,))
        found += _diff("grant", obj, expected_table, actual_table, "table grant")
        found += _diff("grant", obj, expected_cols, actual_cols, "column grant")

        filtered = obj in policy.row_filters
        if rls != filtered:
            found.append(Finding("rls", obj, f"row level security is {'on' if rls else 'off'}, policy says {'on' if filtered else 'off'}"))
        actual_policies = {}
        for name, roles, cmd, permissive, qual in conn.execute("""
                select polname, array(select rolname from pg_roles where oid = any(polroles) order by 1),
                       polcmd, polpermissive, pg_get_expr(polqual, polrelid)
                from pg_policy where polrelid = %s""", (oid,)).fetchall():
            if cmd != "r" or not permissive or len(roles) != 1:
                found.append(Finding("rls", obj, f"policy {name} isn't a single-role permissive SELECT policy"))
                continue
            regions = {"*"} if qual == "true" else set(re.findall(r"[A-Za-z_]+", (re.search(r"'\{(.*)\}'", qual or "") or [None, ""])[1]))
            actual_policies[name] = (roles[0], regions)
        for name in actual_policies.keys() | expected_policies.keys():
            exp, act = expected_policies.get(name), actual_policies.get(name)
            if exp != act:
                found.append(Finding("rls", obj, f"policy {name}: expected {_fmt(exp)}, found {_fmt(act)}"))
    return found


def _fmt(p):
    return "nothing" if p is None else f"{p[0]} sees {', '.join(sorted(p[1])) or 'no rows'}"


def check_functions(conn, policy: Policy) -> list[Finding]:
    found = []
    for oid, schema, name in conn.execute("""
            select p.oid, n.nspname, p.proname from pg_proc p join pg_namespace n on n.oid = p.pronamespace
            where n.nspname = any(%s)""", (list(policy.schemas),)).fetchall():
        actual = _acl(conn, """
            select case a.grantee when 0 then 'PUBLIC' else pg_get_userbyid(a.grantee) end, a.privilege_type
            from pg_proc p, aclexplode(coalesce(p.proacl, acldefault('f', p.proowner))) a
            where p.oid = %s and a.grantee <> p.proowner""", (oid,))
        expected = {(r.name, p) for r in policy.roles.values() for p in r.function_grants.get(f"{schema}.{name}", ())}
        found += _diff("function", f"{schema}.{name}", expected, actual, "grant")
    return found


def check_default_privileges(conn, policy: Policy) -> list[Finding]:
    managed = [policy.owner, *policy.roles, *(p.login for p in policy.people)]
    rows = conn.execute("""
        select pg_get_userbyid(d.defaclrole), coalesce(n.nspname, 'all schemas'), d.defaclobjtype
        from pg_default_acl d left join pg_namespace n on n.oid = d.defaclnamespace
        where n.nspname = any(%s) or pg_get_userbyid(d.defaclrole) = any(%s)""",
        (list(policy.schemas), managed)).fetchall()
    return [Finding("default", f"{role} in {schema}", f"default privileges on new {kind} objects") for role, schema, kind in rows]


def check_rules(conn, policy: Policy) -> list[Finding]:
    """The governance tables must hold exactly what the policy renders to."""
    rules = _rules(policy)
    conn.execute(sql.SQL("SET ROLE {}").format(sql.Identifier(policy.owner)))
    try:
        actual = {tuple(r) for r in conn.execute(
            "select role_name, schema_name, table_name, array_to_string(privileges, ','), clearance_rank, "
            "array_to_string(regions, ',') from governance.table_access").fetchall()}
        actual_cls = {tuple(r) for r in conn.execute(
            "select table_name, column_name, level from governance.column_classification").fetchall()}
        actual_rf = {tuple(r) for r in conn.execute(
            "select schema_name, table_name, column_name from governance.row_filters").fetchall()}
    finally:
        conn.execute("RESET ROLE")
    expected = {(a["role"], a["schema"], a["table"], ",".join(a["privileges"]), a["clearance_rank"],
                 ",".join(a["regions"]) if a["regions"] else None) for a in rules["table_access"]}
    expected_cls = {(c["table"], c["column"], c["level"]) for c in rules["classification"]}
    expected_rf = {(f["schema"], f["table"], f["column"]) for f in rules["row_filters"]}
    return (_diff("rules", "governance.table_access", expected, actual, "row")
            + _diff("rules", "governance.column_classification", expected_cls, actual_cls, "row")
            + _diff("rules", "governance.row_filters", expected_rf, actual_rf, "row"))


def find_drift(conn, policy: Policy) -> list[Finding]:
    admin = conn.execute("select current_user").fetchone()[0]
    return (check_roles(conn, policy, admin) + check_schemas(conn, policy) + check_relations(conn, policy)
            + check_functions(conn, policy) + check_default_privileges(conn, policy) + check_rules(conn, policy))


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--json", action="store_true")
    args = parser.parse_args()

    policy = load_policy()
    with admin_connect(autocommit=True) as conn:
        findings = find_drift(conn, policy)

    if args.json:
        print(json.dumps([asdict(f) for f in findings], indent=1))
    elif findings:
        print(f"Drift: {len(findings)} difference(s) between the database and the policy\n")
        for f in findings:
            print(f"  {f}")
        print("\n`just apply-policy` puts it back. If the change was wanted, put it in the policy first.")
    else:
        print("No drift. The database matches the policy.")
    return 1 if findings else 0


if __name__ == "__main__":
    sys.exit(main())
