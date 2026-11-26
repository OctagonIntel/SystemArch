"""Access review report (Phase 4): one HTML page showing who can read what.

    python -m report.build                 read the live database and compare it with the policy
    python -m report.build --policy-only   what the policy grants, no database needed

Writes report/out/access-review-<date>.html. The live report reads the catalog as admin,
the same way the drift check does. It never logs in as anyone.
"""
import argparse
import subprocess
import sys
from datetime import datetime, timezone
from itertools import groupby
from pathlib import Path

from jinja2 import Environment, FileSystemLoader, StrictUndefined, select_autoescape

from common.db import REPO, admin_connect
from generator.policy import PolicyError, load_policy
from report.collect import HASHED_SCHEMA, SOURCE_SCHEMAS, Cell, Review, collect, column_level

OUT_DIR = REPO / "report" / "out"
SHORT = {"public": "pub", "internal": "int", "confidential": "conf", "restricted": "restr"}

env = Environment(
    loader=FileSystemLoader(Path(__file__).resolve().parent / "templates"),
    autoescape=select_autoescape(["html", "j2"]),
    undefined=StrictUndefined,
    trim_blocks=True,
    lstrip_blocks=True,
)


def _git() -> str:
    try:
        sha = subprocess.run(["git", "rev-parse", "--short", "HEAD"], cwd=REPO, capture_output=True,
                             text=True, check=True).stdout.strip()
        dirty = subprocess.run(["git", "status", "--porcelain", "--", "policy"], cwd=REPO,
                               capture_output=True, text=True, check=True).stdout.strip()
        return f"{sha} (policy has uncommitted changes)" if dirty else sha
    except (OSError, subprocess.CalledProcessError):
        return "unknown"


def _regions(regions) -> str:
    if regions is None:
        return ""
    if regions == ["*"]:
        return "all regions"
    return " ".join(regions) or "no rows"


def _cell_view(review: Review, login, t, cell: Cell) -> dict:
    if not cell.reads:
        label, css = "", "none"
    elif cell.owner:
        label, css = "own", "owner"
    else:
        label, css = SHORT.get(cell.level, cell.level[:4]), f"lvl-{review.levels.index(cell.level)}"
    tip = [f"{login.label} on {t.key}"]
    if cell.owner:
        tip.append("Owns the table: reads everything, can grant access")
    elif cell.reads:
        tip.append(f"Reads up to {cell.level}")
        if cell.hidden:
            tip.append(f"Columns: {len(cell.columns)} of {len(cell.columns) + len(cell.hidden)}, "
                       f"not {', '.join(cell.hidden)}")
        hashed = [c for c in t.hashed if c in cell.columns]
        if hashed:
            tip.append(f"Hashed: {', '.join(hashed)}")
    else:
        tip.append("No read access")
    if cell.regions is not None and cell.reads:
        tip.append(f"Rows: {_regions(cell.regions)}")
    if cell.writes:
        tip.append(f"Can {', '.join(cell.writes)}")
    if cell.via and cell.via != ["owner"] and (cell.reads or cell.writes):
        tip.append(f"Through {', '.join(cell.via)}")
    tip += [f"Differs from policy: {p}" for p in cell.problems]
    sub = []
    if cell.regions is not None and cell.reads and not cell.owner:
        sub.append("all" if cell.regions == ["*"] else ("·".join(cell.regions) or "∅"))
    if cell.writes:
        sub.append("W")
    return {"label": label, "css": css, "sub": " ".join(sub), "tip": "\n".join(tip),
            "bad": bool(cell.problems), "empty": not (cell.reads or cell.writes or cell.problems)}


def _display(login) -> str:
    return login.label if login.kind == "person" else login.name


def _sensitive(review: Review, policy) -> list[dict]:
    """Every clear-text column above public, most sensitive first, with who can read it."""
    names = {l.name: l for l in review.logins}
    rows = []
    for t in review.tables:
        if t.schema in SOURCE_SCHEMAS or t.schema == HASHED_SCHEMA:
            continue
        for col in t.columns:
            level = column_level(policy, t.schema, t.name, col)
            if level == "public":
                continue
            readers = [names[l] for l in names
                       if col in review.cells[(l, t.key)].columns or review.cells[(l, t.key)].owner]
            rows.append({"object": f"{t.key}.{col}", "level": level, "rank": review.levels.index(level),
                         "readers": [{"name": _display(r),
                                      "via": "owner" if review.cells[(r.name, t.key)].owner
                                      else ", ".join(review.cells[(r.name, t.key)].via)} for r in readers]})
    source = [t for t in review.tables if t.schema in SOURCE_SCHEMAS]
    if source:
        readers = [l for l in review.logins if any(review.cells[(l.name, t.key)].reads for t in source)]
        rows.append({"object": "raw.* and staging.* (unmasked source data)", "level": review.levels[-1],
                     "rank": len(review.levels) - 1,
                     "readers": [{"name": _display(r),
                                  "via": "owner" if any(review.cells[(r.name, t.key)].owner for t in source)
                                  else r.name} for r in readers]})
    return sorted(rows, key=lambda r: -r["rank"])


def build(review: Review, policy) -> str:
    login_groups = [
        {"title": f"People · {dept}" if kind == "person" else "Service accounts", "logins": list(items)}
        for (kind, dept), items in groupby(review.logins, key=lambda l: (l.kind, l.department))
    ]
    schema_groups = [{"name": s, "tables": list(ts)} for s, ts in groupby(review.tables, key=lambda t: t.schema)]
    cells = {f"{l}|{k}": _cell_view(review, next(x for x in review.logins if x.name == l),
                                     next(t for t in review.tables if t.key == k), c)
             for (l, k), c in review.cells.items()}
    problems = [(l, k, p) for (l, k), c in review.cells.items() for p in c.problems]
    restricted_people = sorted({
        l.label for l in review.logins if l.kind == "person"
        for t in review.tables if (c := review.cells[(l.name, t.key)]).level == review.levels[-1]})
    details = []
    for l in review.logins:
        rows = [{"table": t, "cell": review.cells[(l.name, t.key)], "view": cells[f"{l.name}|{t.key}"]}
                for t in review.tables]
        rows = [r for r in rows if not r["view"]["empty"]]
        details.append({"login": l, "rows": rows, "bad": any(r["cell"].problems for r in rows)})

    return env.get_template("access_review.html.j2").render(
        review=review,
        generated=datetime.now(timezone.utc).strftime("%Y-%m-%d %H:%M UTC"),
        commit=_git(),
        login_groups=login_groups,
        schema_groups=schema_groups,
        cells=cells,
        problems=problems,
        sensitive=_sensitive(review, policy),
        restricted_people=restricted_people,
        details=details,
        short=SHORT,
        regions=_regions,
        people=sum(l.kind == "person" for l in review.logins),
        services=sum(l.kind == "service" for l in review.logins),
    )


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--policy-only", action="store_true", help="render what the policy grants, no database")
    parser.add_argument("--out", type=Path, help="where to write the HTML")
    args = parser.parse_args()

    try:
        policy = load_policy()
    except PolicyError as e:
        print(f"Policy is invalid: {e}")
        return 1

    if args.policy_only:
        review = collect(policy)
    else:
        with admin_connect(autocommit=True) as conn:
            review = collect(policy, conn)

    stamp = datetime.now(timezone.utc).strftime("%Y-%m-%d")
    out = args.out or OUT_DIR / f"access-review-{stamp}{'-policy' if args.policy_only else ''}.html"
    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_text(build(review, policy), encoding="utf-8")

    differences = sum(len(c.problems) for c in review.cells.values()) + len(review.drift)
    print(f"Access review written to {out.relative_to(REPO) if out.is_relative_to(REPO) else out}")
    if review.mode == "live":
        print("The database matches the policy." if not differences else
              f"{differences} difference(s) between the database and the policy, listed in the report.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
