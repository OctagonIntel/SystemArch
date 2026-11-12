"""Loads and validates policy/access.yaml and policy/people.yaml."""
import re
from dataclasses import dataclass, field
from pathlib import Path

import yaml

POLICY_DIR = Path(__file__).resolve().parent.parent / "policy"
POLICY_FILE = POLICY_DIR / "access.yaml"
PEOPLE_FILE = POLICY_DIR / "people.yaml"

# Names go straight into SQL, so they have to be plain lowercase identifiers.
NAME = re.compile(r"^[a-z_][a-z0-9_]{0,62}$")
PERSON_ID = re.compile(r"^[a-z]+(\.[a-z]+)+$")
SCHEMA_PRIVILEGES = {"USAGE", "CREATE"}
TABLE_PRIVILEGES = {"SELECT", "INSERT", "UPDATE", "DELETE", "TRUNCATE", "REFERENCES", "TRIGGER"}
FUNCTION_PRIVILEGES = {"EXECUTE"}
ROLE_TYPES = {"service", "human"}


class PolicyError(ValueError):
    pass


@dataclass(frozen=True)
class TableGrant:
    schema: str
    table: str | None  # None means every table in the schema
    privileges: tuple[str, ...]
    clearance: str | None = None  # only for SELECT on dbt-built tables: highest column level the role sees

    @property
    def target(self) -> str:
        return f"{self.schema}.{self.table or '*'}"


@dataclass
class Role:
    name: str
    type: str
    purpose: str
    login: bool
    regions: tuple[str, ...] | None = None  # None: no row filter declared. ("*",) means every region.
    schema_grants: dict[str, tuple[str, ...]] = field(default_factory=dict)
    table_grants: list[TableGrant] = field(default_factory=list)
    function_grants: dict[str, tuple[str, ...]] = field(default_factory=dict)


@dataclass(frozen=True)
class Schema:
    name: str
    description: str
    built_by: str | None  # the service account whose dbt run creates (and owns) the tables


@dataclass(frozen=True)
class Person:
    id: str
    login: str
    name: str
    department: str
    groups: tuple[str, ...]


@dataclass
class Policy:
    owner: str
    schemas: dict[str, Schema]
    roles: dict[str, Role]
    levels: list[str]
    classification: dict[str, dict[str, str]]  # table -> column -> level, public left out
    declared_columns: dict[str, set[str]]  # table -> every column given a level, public included
    row_filters: dict[str, str]  # schema.table -> column
    people: list[Person] = field(default_factory=list)
    platform_readers: set[str] = field(default_factory=set)

    @property
    def login_roles(self) -> list[str]:
        return [r.name for r in self.roles.values() if r.login] + [p.login for p in self.people]

    @property
    def builders(self) -> set[str]:
        return {s.built_by for s in self.schemas.values() if s.built_by}

    def level_rank(self, level: str) -> int:
        return self.levels.index(level)


def _name(value, what: str) -> str:
    if not isinstance(value, str) or not NAME.match(value):
        raise PolicyError(f"{what} {value!r} must be a lowercase identifier")
    return value


def _privileges(values, allowed: set[str], where: str) -> tuple[str, ...]:
    if not isinstance(values, list) or not values:
        raise PolicyError(f"{where}: privileges must be a non-empty list")
    privs = tuple(str(v).upper() for v in values)
    bad = set(privs) - allowed
    if bad:
        raise PolicyError(f"{where}: unknown privileges {sorted(bad)}")
    return privs


def _schemas(raw: dict) -> dict[str, Schema]:
    out = {}
    for name, spec in (raw or {}).items():
        _name(name, "schema")
        if isinstance(spec, str):
            spec = {"description": spec}
        out[name] = Schema(name, str(spec.get("description", "")), spec.get("built_by"))
    if not out:
        raise PolicyError("policy defines no schemas")
    return out


def _classification(data: dict) -> tuple[list[str], dict[str, dict[str, str]], dict[str, set[str]]]:
    spec = data.get("classification") or {}
    levels = spec.get("levels") or ["public"]
    if levels[0] != "public":
        raise PolicyError("classification levels must start with public, the lowest")
    columns, declared = {}, {}
    for table, cols in (spec.get("columns") or {}).items():
        _name(table, "classified table")
        columns[table], declared[table] = {}, set()
        for col, level in (cols or {}).items():
            _name(col, f"column in {table}")
            if level not in levels:
                raise PolicyError(f"{table}.{col}: level {level!r} isn't one of {levels}")
            declared[table].add(col)
            if level == "public":
                continue
            columns[table][col] = level
    return levels, columns, declared


def _people(path: Path, roles: dict[str, Role]) -> list[Person]:
    if not path.exists():
        return []
    data = yaml.safe_load(path.read_text(encoding="utf-8")) or {}
    people, seen = [], set()
    for entry in data.get("people") or []:
        pid = str(entry.get("id", ""))
        if not PERSON_ID.match(pid):
            raise PolicyError(f"person id {pid!r} must look like first.last")
        login = pid.replace(".", "_")
        _name(login, "login")
        if login in seen:
            raise PolicyError(f"{pid} is listed twice")
        if login in roles:
            raise PolicyError(f"{pid}: login {login} clashes with a policy role")
        seen.add(login)
        groups = tuple(entry.get("groups") or [])
        for g in groups:
            if g not in roles:
                raise PolicyError(f"{pid}: group {g!r} isn't a role in access.yaml")
            # Separation of duties: people only ever get human group roles.
            if roles[g].type != "human" or roles[g].login:
                raise PolicyError(f"{pid}: {g} is not a human group role, people can't hold it")
        people.append(Person(pid, login, str(entry.get("name", pid)), str(entry.get("department", "")), groups))
    return people


def load_policy(path: Path = POLICY_FILE, people_path: Path = PEOPLE_FILE) -> Policy:
    data = yaml.safe_load(path.read_text(encoding="utf-8"))
    if data.get("version") != 1:
        raise PolicyError("only policy version 1 is supported")

    owner = _name(data.get("owner"), "owner")
    schemas = _schemas(data.get("schemas"))
    levels, classification, declared = _classification(data)

    row_filters = {}
    for target, column in (data.get("row_filters") or {}).items():
        schema, _, table = str(target).partition(".")
        if schema not in schemas or not schemas[schema].built_by:
            raise PolicyError(f"row filter on {target}: RLS is only applied to dbt-built schemas")
        row_filters[f"{schema}.{_name(table, 'table')}"] = _name(column, "row filter column")

    roles: dict[str, Role] = {}
    for name, spec in (data.get("roles") or {}).items():
        _name(name, "role")
        if name == owner:
            raise PolicyError(f"{name}: the owner can't also be a policy role")
        spec = spec or {}
        rtype = spec.get("type")
        if rtype not in ROLE_TYPES:
            raise PolicyError(f"{name}: type must be one of {sorted(ROLE_TYPES)}")
        if rtype == "service" and not name.startswith("svc_"):
            raise PolicyError(f"{name}: service accounts must start with svc_")
        if rtype == "human" and name.startswith("svc_"):
            raise PolicyError(f"{name}: only service accounts may start with svc_")
        if not spec.get("purpose"):
            raise PolicyError(f"{name}: every role needs a purpose")
        # Human roles are groups. People log in through their own role (people.yaml).
        login = rtype == "service"

        regions = spec.get("regions")
        if regions is not None:
            regions = ("*",) if regions == "all" else tuple(str(r) for r in regions)
        role = Role(name, rtype, spec["purpose"], login, regions)

        for schema, privs in (spec.get("schemas") or {}).items():
            if schema not in schemas:
                raise PolicyError(f"{name}: schema {schema!r} isn't declared")
            role.schema_grants[schema] = _privileges(privs, SCHEMA_PRIVILEGES, f"{name} on {schema}")

        for target, grant in (spec.get("tables") or {}).items():
            schema, _, table = str(target).partition(".")
            if schema not in schemas or not table:
                raise PolicyError(f"{name}: {target!r} must look like schema.table or schema.*")
            if "USAGE" not in role.schema_grants.get(schema, ()):
                raise PolicyError(f"{name}: has table grants in {schema} but no USAGE on it")
            clearance = None
            if isinstance(grant, dict):
                clearance = grant.get("clearance")
                grant = grant.get("privileges")
            privs = _privileges(grant, TABLE_PRIVILEGES, f"{name} on {target}")
            if clearance is not None:
                if clearance not in levels:
                    raise PolicyError(f"{name} on {target}: clearance {clearance!r} isn't one of {levels}")
                if privs != ("SELECT",) or not schemas[schema].built_by:
                    raise PolicyError(f"{name} on {target}: clearance only works for SELECT on dbt-built tables")
            role.table_grants.append(TableGrant(schema, None if table == "*" else _name(table, "table"), privs, clearance))

        for target, privs in (spec.get("functions") or {}).items():
            schema, _, fn = str(target).partition(".")
            if schema not in schemas or not fn:
                raise PolicyError(f"{name}: function {target!r} must look like schema.function")
            role.function_grants[f"{schema}.{_name(fn, 'function')}"] = _privileges(privs, FUNCTION_PRIVILEGES, f"{name} on {target}")

        # Anyone who can read a row-filtered table has to say which rows. No silent defaults.
        for g in role.table_grants:
            if "SELECT" not in g.privileges:
                continue
            hits = [t for t in row_filters if t.startswith(f"{g.schema}.") and (g.table is None or t == g.target)]
            if hits and role.regions is None:
                raise PolicyError(f"{name}: reads row-filtered {hits[0]} but has no `regions:`")

        roles[name] = role

    for s in schemas.values():
        if s.built_by and s.built_by not in roles:
            raise PolicyError(f"schema {s.name}: built_by {s.built_by} isn't a role")

    policy = Policy(owner, schemas, roles, levels, classification, declared, row_filters)
    policy.people = _people(people_path, roles)
    policy.platform_readers = set(data.get("platform_readers") or [])
    return policy
