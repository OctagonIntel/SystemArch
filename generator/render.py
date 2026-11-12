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


def render(policy: Policy) -> tuple[str, str]:
    """Returns (part 1 run as admin, part 2 run as the owner)."""
    ctx = {
        "owner": policy.owner,
        "schemas": policy.schemas,
        "roles": list(policy.roles.values()),
    }
    return env.get_template("roles.sql.j2").render(ctx), env.get_template("grants.sql.j2").render(ctx)
