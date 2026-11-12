"""Loads policy/access.yaml and checks it before anything touches the database."""
import re
from dataclasses import dataclass, field
from pathlib import Path

import yaml

POLICY_FILE = Path(__file__).resolve().parent.parent / "policy" / "access.yaml"

# Names go straight into SQL, so they have to be plain lowercase identifiers.
NAME = re.compile(r"^[a-z_][a-z0-9_]{0,62}$")
SCHEMA_PRIVILEGES = {"USAGE", "CREATE"}
TABLE_PRIVILEGES = {"SELECT", "INSERT", "UPDATE", "DELETE", "TRUNCATE", "REFERENCES", "TRIGGER"}
ROLE_TYPES = {"service", "human"}


class PolicyError(ValueError):
    pass


@dataclass(frozen=True)
class TableGrant:
    schema: str
    table: str | None  # None means every table in the schema
    privileges: tuple[str, ...]


@dataclass
class Role:
    name: str
    type: str
    purpose: str
    login: bool
    schema_grants: dict[str, tuple[str, ...]] = field(default_factory=dict)
    table_grants: list[TableGrant] = field(default_factory=list)


@dataclass
class Policy:
    owner: str
    schemas: dict[str, str]
    roles: dict[str, Role]

    @property
    def login_roles(self) -> list[Role]:
        return [r for r in self.roles.values() if r.login]


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


def load_policy(path: Path = POLICY_FILE) -> Policy:
    data = yaml.safe_load(path.read_text(encoding="utf-8"))
    if data.get("version") != 1:
        raise PolicyError("only policy version 1 is supported")

    owner = _name(data.get("owner"), "owner")
    schemas = {_name(s, "schema"): str(desc) for s, desc in (data.get("schemas") or {}).items()}
    if not schemas:
        raise PolicyError("policy defines no schemas")

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

        role = Role(name, rtype, spec["purpose"], login=bool(spec.get("login", rtype == "service")))

        for schema, privs in (spec.get("schemas") or {}).items():
            if schema not in schemas:
                raise PolicyError(f"{name}: schema {schema!r} isn't declared")
            role.schema_grants[schema] = _privileges(privs, SCHEMA_PRIVILEGES, f"{name} on {schema}")

        for target, privs in (spec.get("tables") or {}).items():
            schema, _, table = str(target).partition(".")
            if schema not in schemas or not table:
                raise PolicyError(f"{name}: {target!r} must look like schema.table or schema.*")
            if "USAGE" not in role.schema_grants.get(schema, ()):
                raise PolicyError(f"{name}: has table grants in {schema} but no USAGE on it")
            role.table_grants.append(TableGrant(
                schema,
                None if table == "*" else _name(table, "table"),
                _privileges(privs, TABLE_PRIVILEGES, f"{name} on {target}"),
            ))

        roles[name] = role

    return Policy(owner, schemas, roles)
