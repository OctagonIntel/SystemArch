"""Turns the policy into SQL using the Jinja templates next to this file."""
from pathlib import Path

from jinja2 import Environment, FileSystemLoader, StrictUndefined

from generator.policy import Policy

env = Environment(
    loader=FileSystemLoader(Path(__file__).resolve().parent / "templates"),
    undefined=StrictUndefined,
    trim_blocks=True,
    lstrip_blocks=True,
    keep_trailing_newline=True,
)
env.filters["sql_literal"] = lambda s: "'" + str(s).replace("'", "''") + "'"
env.filters["sql_array"] = lambda xs: "ARRAY[" + ", ".join(env.filters["sql_literal"](x) for x in xs) + "]::text[]"
TEMPLATES = ("roles.sql.j2", "grants.sql.j2", "rules.sql.j2", "members.sql.j2")


def _rules(policy: Policy) -> dict:
    table_access = []
    for role in policy.roles.values():
        for g in role.table_grants:
            if not policy.schemas[g.schema].built_by:
                continue
            table_access.append({
                "role": role.name, "schema": g.schema, "table": g.table or "*",
                "privileges": g.privileges,
                "clearance_rank": policy.level_rank(g.clearance) if g.clearance else None,
                "regions": list(role.regions) if role.regions else None,
            })
    classification = [
        {"table": t, "column": c, "level": lvl, "rank": policy.level_rank(lvl)}
        for t, cols in policy.classification.items() for c, lvl in cols.items()
    ]
    row_filters = [
        {"schema": k.split(".")[0], "table": k.split(".")[1], "column": col}
        for k, col in policy.row_filters.items()
    ]
    request_rules = [
        {"group": r.name, "purpose": r.purpose, "max_days": r.request.max_days, "approvers": list(r.request.approvers)}
        for r in policy.requestable
    ]
    return {"table_access": table_access, "classification": classification, "row_filters": row_filters,
            "request_rules": request_rules}


def render(policy: Policy) -> tuple[str, ...]:
    """Returns the four parts: 1 runs as admin, 2 to 4 as the owner after the DDL."""
    roles = list(policy.roles.values())
    ctx = {
        "owner": policy.owner,
        "schemas": policy.schemas,
        "roles": roles,
        "builders": sorted(policy.builders),
        "people": policy.people,
        "human_groups": [r.name for r in roles if r.type == "human"],
        **_rules(policy),
    }
    return tuple(env.get_template(t).render(ctx) for t in TEMPLATES)
