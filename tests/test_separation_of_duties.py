"""Separation-of-duties rules, checked on the live catalog for every role in the database,
not just the ones in the policy."""
import pytest

PERSON = "shobj_description(r.oid, 'pg_authid') like 'person: %%'"


@pytest.fixture(scope="module")
def trusted(admin, policy):
    """The admin connection and the platform's read-everything roles. Checked separately below."""
    admin_user = admin.execute("select current_user").fetchone()[0]
    return sorted({admin_user, "pg_read_all_data", "pg_write_all_data"} | policy.platform_readers)


def roles_where(admin, trusted, condition: str, params=()) -> set[str]:
    return {row[0] for row in admin.execute(
        f"select r.rolname from pg_roles r where not r.rolsuper and r.rolname <> all(%s) and {condition}",
        (trusted, *params)).fetchall()}


def tables_in(admin, schemas) -> list[int]:
    return [r[0] for r in admin.execute("""
        select c.oid from pg_class c join pg_namespace n on n.oid = c.relnamespace
        where n.nspname = any(%s) and c.relkind in ('r', 'p', 'v', 'm')""", (list(schemas),)).fetchall()]


def owners(admin, schemas) -> set[str]:
    return {r[0] for r in admin.execute("""
        select distinct pg_get_userbyid(c.relowner) from pg_class c join pg_namespace n on n.oid = c.relnamespace
        where n.nspname = any(%s)""", (list(schemas),)).fetchall()}


def test_nobody_both_loads_raw_and_reads_marts(admin, trusted):
    raw, marts = tables_in(admin, ["raw"]), tables_in(admin, ["marts", "marts_restricted"])
    both = roles_where(admin, trusted, """
        exists (select 1 from unnest(%s::oid[]) t(oid), unnest(array['INSERT','UPDATE','DELETE']) p
                where has_table_privilege(r.oid, t.oid, p))
        and exists (select 1 from unnest(%s::oid[]) t(oid) where has_table_privilege(r.oid, t.oid, 'SELECT'))""",
        (raw, marts))
    assert not both, f"These roles can write raw and read marts: {sorted(both)}"


def test_people_never_hold_service_roles(admin, policy):
    held = {row for row in admin.execute(f"""
        select r.rolname, g.rolname from pg_roles r, pg_roles g
        where {PERSON} and pg_has_role(r.oid, g.oid, 'MEMBER')
          and (g.rolname like 'svc\\_%%' or g.rolname = %s)""", (policy.owner,)).fetchall()}
    assert not held, f"People holding service or owner roles: {sorted(held)}"


def test_service_accounts_are_in_no_groups(admin, policy):
    services = [r.name for r in policy.roles.values() if r.type == "service"]
    held = {row for row in admin.execute("""
        select m.member::regrole::text, m.roleid::regrole::text from pg_auth_members m
        where m.member::regrole::text = any(%s)""", (services,)).fetchall()}
    assert not held, f"Service accounts in groups: {sorted(held)}"


def test_auditor_sees_no_business_data(admin, trusted):
    business = tables_in(admin, ["raw", "staging", "marts", "marts_restricted"])
    readers = roles_where(admin, trusted, """
        pg_has_role(r.oid, 'auditor', 'MEMBER')
        and exists (select 1 from unnest(%s::oid[]) t(oid) where has_any_column_privilege(r.oid, t.oid, 'SELECT'))""",
        (business,))
    assert not readers, f"Auditor members who can read business data: {sorted(readers)}"


def test_nobody_reads_the_hashing_salt(admin, policy, trusted):
    readers = roles_where(admin, trusted, "r.rolname <> %s and has_table_privilege(r.oid, 'governance.pii_salt', 'SELECT')",
                          (policy.owner,))
    assert not readers, f"Can read the salt: {sorted(readers)}"


@pytest.mark.parametrize("column", ["national_id", "date_of_birth"])
def test_only_hr_and_payroll_see_restricted_ids(admin, policy, trusted, column):
    builders = owners(admin, ["marts_restricted"])  # the dbt owner, accepted in ADR-014
    readers = roles_where(admin, trusted, """
        r.rolname <> all(%s) and has_column_privilege(r.oid, 'marts_restricted.dim_employee', %s, 'SELECT')""",
        (list(builders), column))
    allowed = {"hr", "payroll"} | {p.login for p in policy.people if {"hr", "payroll"} & set(p.groups)}
    assert readers <= allowed, f"Unexpected readers of {column}: {sorted(readers - allowed)}"


def test_only_known_platform_roles_read_everything(admin, policy):
    """Anyone holding pg_read_all_data or pg_write_all_data skips our grants entirely."""
    admin_user = admin.execute("select current_user").fetchone()[0]
    found = {row[0] for row in admin.execute("""
        select r.rolname from pg_roles r
        where not r.rolsuper and r.rolname <> %s and r.rolname not in ('pg_read_all_data', 'pg_write_all_data')
          and (pg_has_role(r.oid, 'pg_read_all_data', 'MEMBER') or pg_has_role(r.oid, 'pg_write_all_data', 'MEMBER'))""",
        (admin_user,)).fetchall()}
    unknown = found - policy.platform_readers
    assert not unknown, f"Roles that bypass every grant, not listed in platform_readers: {sorted(unknown)}"
