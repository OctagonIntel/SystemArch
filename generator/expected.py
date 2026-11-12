"""What the policy says each role or person should get on a table.

Shared by the generated tests and the drift check, so both read the policy the same way.
"""
from dataclasses import dataclass

from generator.policy import Person, Policy


@dataclass
class Access:
    privileges: set[str]
    columns: set[str] | None = None  # None: every column (table-level grant)
    regions: set[str] | None = None  # None: no row filter. {"*"}: every region

    def merge(self, other: "Access") -> "Access":
        cols = None if self.columns is None or other.columns is None else self.columns | other.columns
        if self.regions is None and other.regions is None:
            regions = None
        else:
            regions = (self.regions or set()) | (other.regions or set())
            if "*" in regions:
                regions = {"*"}
        return Access(self.privileges | other.privileges, cols, regions)


def visible_columns(policy: Policy, table: str, columns: list[str], clearance: str) -> set[str]:
    rank = policy.level_rank(clearance)
    levels = policy.classification.get(table, {})
    return {c for c in columns if policy.level_rank(levels.get(c, "public")) <= rank}


def role_access(policy: Policy, role_name: str, schema: str, table: str, columns: list[str]) -> Access | None:
    role = policy.roles.get(role_name)
    if role is None:
        return None
    built = bool(policy.schemas[schema].built_by) if schema in policy.schemas else False
    result = None
    for g in role.table_grants:
        if g.schema != schema or g.table not in (None, table):
            continue
        cols = visible_columns(policy, table, columns, g.clearance) if g.clearance else None
        access = Access(set(g.privileges), cols)
        if built and f"{schema}.{table}" in policy.row_filters and "SELECT" in g.privileges:
            access.regions = set(role.regions or ())
        result = access if result is None else result.merge(access)
    return result


def person_access(policy: Policy, person: Person, schema: str, table: str, columns: list[str]) -> Access | None:
    result = None
    for group in person.groups:
        access = role_access(policy, group, schema, table, columns)
        if access is not None:
            result = access if result is None else result.merge(access)
    return result


def has_schema_usage(policy: Policy, role_names, schema: str) -> bool:
    return any("USAGE" in policy.roles[r].schema_grants.get(schema, ()) for r in role_names if r in policy.roles)
