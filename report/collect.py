"""Works out who can read what, for the access review report (Phase 4).

Two sources, kept apart so they can be compared:
  expected  what policy/*.yaml grants, through generator.expected (same as the tests and drift)
  actual    what the live catalog says each login can do, read as admin

In policy-only mode there is no actual side, and the tables are the ones the policy names.
"""
from dataclasses import dataclass, field

import yaml

from drift.check import find_drift, policy_regions  # one parser for apply_access's RLS policies
from generator.expected import has_schema_usage, person_access, role_access
from generator.policy import PEOPLE_FILE, Policy

WRITES = ("INSERT", "UPDATE", "DELETE", "TRUNCATE")

# raw and staging hold source data unmasked and unclassified, so any read there counts
# as the highest level. marts holds the hashed copies (ADR-005): classified columns there
# are tokens, not personal data.
SOURCE_SCHEMAS = {"raw", "staging"}
HASHED_SCHEMA = "marts"


@dataclass
class Table:
    schema: str
    name: str
    columns: list[str]  # empty in policy-only mode when the policy doesn't list them
    owner: str
    row_filter: str | None
    hashed: list[str] = field(default_factory=list)

    @property
    def key(self) -> str:
        return f"{self.schema}.{self.name}"


@dataclass
class Login:
    name: str
    kind: str  # person | service
    label: str  # the person's name, or the service account's purpose
    department: str
    groups: list[str]


@dataclass
class Cell:
    level: str | None = None  # highest clear-text level readable, None if it can't read at all
    owner: bool = False
    columns: list[str] = field(default_factory=list)  # readable
    hidden: list[str] = field(default_factory=list)  # in the table, not readable
    writes: list[str] = field(default_factory=list)
    regions: list[str] | None = None  # None: no row filter. ["*"]: every region. []: no rows
    via: list[str] = field(default_factory=list)  # groups (or the account itself) the policy grants it through
    problems: list[str] = field(default_factory=list)  # live database differs from the policy

    @property
    def reads(self) -> bool:
        return self.owner or self.level is not None


@dataclass
class Review:
    mode: str  # live | policy
    levels: list[str]
    logins: list[Login]
    tables: list[Table]
    cells: dict[tuple[str, str], Cell]  # (login, table key) -> cell
    people_exported_at: str
    drift: list = field(default_factory=list)
    leavers: list[tuple[str, str]] = field(default_factory=list)
    bypass: list[str] = field(default_factory=list)  # roles that read everything, grants or not
    missing_logins: list[str] = field(default_factory=list)


def logins_of(policy: Policy) -> list[Login]:
    people = sorted(policy.people, key=lambda p: (p.department, p.name))
    out = [Login(p.login, "person", p.name, p.department, list(p.groups)) for p in people]
    out += [Login(r.name, "service", r.purpose, "", [r.name]) for r in policy.roles.values() if r.login]
    return out


def column_level(policy: Policy, schema: str, table: str, column: str) -> str:
    if schema in SOURCE_SCHEMAS:
        return policy.levels[-1]
    if schema == HASHED_SCHEMA:
        return "public"
    return policy.classification.get(table, {}).get(column, "public")


def table_level(policy: Policy, t: Table, columns: list[str]) -> str:
    """Highest level among the readable columns. A table with unknown columns counts as a whole."""
    if not t.columns:
        return policy.levels[-1] if t.schema in SOURCE_SCHEMAS else "public"
    return max((column_level(policy, t.schema, t.name, c) for c in columns),
               key=policy.level_rank, default="public")


def expected_cell(policy: Policy, login: Login, t: Table) -> Cell:
    if t.owner == login.name:
        return Cell(level=table_level(policy, t, t.columns), owner=True, columns=list(t.columns), via=["owner"])
    person = next((p for p in policy.people if p.login == login.name), None)
    if person:
        access = person_access(policy, person, t.schema, t.name, t.columns)
        via = [g for g in person.groups if role_access(policy, g, t.schema, t.name, t.columns)]
    else:
        access = role_access(policy, login.name, t.schema, t.name, t.columns)
        via = [login.name]
    cell = Cell()
    if access is None or not has_schema_usage(policy, login.groups, t.schema):
        return cell
    cell.via = via
    cell.writes = [p for p in WRITES if p in access.privileges]
    if "SELECT" in access.privileges:
        cell.columns = [c for c in t.columns if access.columns is None or c in access.columns]
        cell.hidden = [c for c in t.columns if c not in cell.columns]
        cell.level = table_level(policy, t, cell.columns)
        if access.regions is not None:
            cell.regions = sorted(access.regions)
    return cell


# Live catalog -------------------------------------------------------------------------

def live_tables(conn, policy: Policy) -> list[Table]:
    out = []
    for oid, schema, name, owner in conn.execute("""
            select c.oid, n.nspname, c.relname, pg_get_userbyid(c.relowner)
            from pg_class c join pg_namespace n on n.oid = c.relnamespace
            where n.nspname = any(%s) and c.relkind in ('r', 'p', 'v', 'm') order by 2, 3""",
            (list(policy.schemas),)).fetchall():
        cols = [r[0] for r in conn.execute(
            "select attname from pg_attribute where attrelid = %s and attnum > 0 and not attisdropped order by attnum",
            (oid,)).fetchall()]
        out.append(Table(schema, name, cols, owner, policy.row_filters.get(f"{schema}.{name}"),
                         hashed=_hashed(policy, schema, name, cols)))
    return out


def _hashed(policy: Policy, schema: str, table: str, columns: list[str]) -> list[str]:
    if schema != HASHED_SCHEMA:
        return []
    return [c for c in columns if c in policy.classification.get(table, {})]


def actual_cells(conn, policy: Policy, logins: list[str], tables: list[Table]) -> dict[tuple[str, str], Cell]:
    """What the catalog says, per login and table. Privileges count only with USAGE on the schema."""
    keys = [t.key for t in tables]
    by_key = {t.key: t for t in tables}
    cells = {(l, k): Cell() for l in logins for k in keys}

    for login, key, column in conn.execute("""
            select l.name, n.nspname || '.' || c.relname, a.attname
            from unnest(%s::text[]) l(name)
            cross join unnest(%s::text[]) k(key)
            join pg_class c on c.oid = to_regclass(k.key)
            join pg_namespace n on n.oid = c.relnamespace
            join pg_attribute a on a.attrelid = c.oid and a.attnum > 0 and not a.attisdropped
            where has_schema_privilege(l.name, n.oid, 'USAGE')
              and has_column_privilege(l.name, c.oid, a.attnum, 'SELECT')
            order by a.attnum""", (logins, keys)).fetchall():
        cells[(login, key)].columns.append(column)

    for login, key, priv in conn.execute("""
            select l.name, n.nspname || '.' || c.relname, p.priv
            from unnest(%s::text[]) l(name)
            cross join unnest(%s::text[]) k(key)
            join pg_class c on c.oid = to_regclass(k.key)
            join pg_namespace n on n.oid = c.relnamespace
            cross join unnest(%s::text[]) p(priv)
            where has_schema_privilege(l.name, n.oid, 'USAGE') and has_table_privilege(l.name, c.oid, p.priv)""",
            (logins, keys, list(WRITES))).fetchall():
        cells[(login, key)].writes.append(priv)

    bypass = {r[0] for r in conn.execute(
        "select rolname from pg_roles where rolname = any(%s) and (rolbypassrls or rolsuper)", (logins,)).fetchall()}
    rls = {f"{r[0]}.{r[1]}" for r in conn.execute("""
            select n.nspname, c.relname from pg_class c join pg_namespace n on n.oid = c.relnamespace
            where n.nspname = any(%s) and c.relrowsecurity""", (list(policy.schemas),)).fetchall()}
    seen = {}
    for login, key, qual in conn.execute("""
            select l.name, n.nspname || '.' || c.relname, pg_get_expr(p.polqual, p.polrelid)
            from unnest(%s::text[]) l(name)
            join pg_policy p on true
            join pg_class c on c.oid = p.polrelid
            join pg_namespace n on n.oid = c.relnamespace
            where n.nspname = any(%s) and p.polcmd in ('r', '*')
              and (0::oid = any(p.polroles) or exists (
                    select 1 from unnest(p.polroles) r(oid) where pg_has_role(l.name, r.oid, 'USAGE')))""",
            (logins, list(policy.schemas))).fetchall():
        seen.setdefault((login, key), set()).update(policy_regions(qual))

    for (login, key), cell in cells.items():
        t = by_key[key]
        cell.writes = [p for p in WRITES if p in cell.writes]
        if t.owner == login:
            cell.owner = True
        if cell.columns:
            cell.hidden = [c for c in t.columns if c not in cell.columns]
            cell.level = table_level(policy, t, cell.columns)
        if key in rls and cell.reads and not cell.owner and login not in bypass:
            regions = seen.get((login, key), set())
            cell.regions = ["*"] if "*" in regions else sorted(regions)
    return cells


def compare(expected: Cell, actual: Cell) -> list[str]:
    if expected.owner or actual.owner:
        return [] if expected.owner == actual.owner else ["owner differs from the policy"]
    out = []
    extra = sorted(set(actual.columns) - set(expected.columns))
    missing = sorted(set(expected.columns) - set(actual.columns))
    if extra:
        out.append(f"can read {', '.join(extra)}, policy says no")
    if missing:
        out.append(f"can't read {', '.join(missing)}, policy says yes")
    for p in sorted(set(actual.writes) - set(expected.writes)):
        out.append(f"can {p}, policy says no")
    for p in sorted(set(expected.writes) - set(actual.writes)):
        out.append(f"can't {p}, policy says yes")
    if actual.reads and expected.reads and actual.regions != expected.regions:
        out.append(f"sees regions {_regions(actual.regions)}, policy says {_regions(expected.regions)}")
    return out


def _regions(r):
    if r is None:
        return "all (no row filter)"
    return "all" if r == ["*"] else (", ".join(r) or "none")


# Policy only ---------------------------------------------------------------------------

def policy_tables(policy: Policy) -> list[Table]:
    """The tables the policy names, with columns where classification lists them."""
    named = set(policy.row_filters)
    for role in policy.roles.values():
        named |= {g.target for g in role.table_grants if g.table}
    for table in policy.declared_columns:
        for schema in policy.schemas.values():
            if schema.built_by:
                named.add(f"{schema.name}.{table}")
    out = []
    for key in sorted(named):
        schema, name = key.split(".")
        built = policy.schemas[schema].built_by
        cols = sorted(policy.declared_columns.get(name, ())) if built else []
        out.append(Table(schema, name, cols, built or policy.owner, policy.row_filters.get(key),
                         hashed=_hashed(policy, schema, name, cols)))
    return out


# Both ------------------------------------------------------------------------------------

def _people_exported_at() -> str:
    data = yaml.safe_load(PEOPLE_FILE.read_text(encoding="utf-8")) or {}
    return str(data.get("exported_at", "unknown"))


def collect(policy: Policy, conn=None) -> Review:
    logins = logins_of(policy)
    tables = live_tables(conn, policy) if conn else policy_tables(policy)
    review = Review("live" if conn else "policy", policy.levels, logins, tables, {}, _people_exported_at())

    if conn is None:
        review.bypass = sorted(policy.platform_readers)
        for login in logins:
            for t in tables:
                review.cells[(login.name, t.key)] = expected_cell(policy, login, t)
        return review

    existing = {r[0] for r in conn.execute(
        "select rolname from pg_roles where rolname = any(%s)", ([l.name for l in logins],)).fetchall()}
    review.missing_logins = [l.name for l in logins if l.name not in existing]
    actual = actual_cells(conn, policy, sorted(existing), tables)
    for login in logins:
        for t in tables:
            exp = expected_cell(policy, login, t)
            if login.name not in existing:
                exp.problems = ["login doesn't exist in the database"] if exp.reads else []
                review.cells[(login.name, t.key)] = exp
                continue
            act = actual[(login.name, t.key)]
            act.via = exp.via
            act.problems = compare(exp, act)
            review.cells[(login.name, t.key)] = act

    review.drift = find_drift(conn, policy)
    review.leavers = [tuple(r) for r in conn.execute("""
        select rolname, shobj_description(oid, 'pg_authid') from pg_roles
        where shobj_description(oid, 'pg_authid') like 'left: %' order by 1""").fetchall()]
    review.bypass = sorted(r[0] for r in conn.execute("""
        select r.rolname from pg_roles r
        where r.rolname not in ('pg_read_all_data', 'pg_write_all_data', current_user)
          and (r.rolsuper or r.rolbypassrls
               or pg_has_role(r.oid, 'pg_read_all_data', 'MEMBER') or pg_has_role(r.oid, 'pg_write_all_data', 'MEMBER'))
          and r.rolname !~ '^pg_'""").fetchall())
    return review
