"""Policy validation and data rules that don't depend on who is logged in."""
from pathlib import Path

import pytest
import yaml

from common.db import as_role
from generator.policy import POLICY_FILE, PolicyError, load_policy

DBT_PROJECT = Path(__file__).resolve().parent.parent / "dbt" / "dbt_project.yml"


def policy_with_regions(tmp_path, regions) -> Path:
    data = yaml.safe_load(POLICY_FILE.read_text(encoding="utf-8"))
    data["roles"]["sales_eu"]["regions"] = regions
    path = tmp_path / "access.yaml"
    path.write_text(yaml.safe_dump(data), encoding="utf-8")
    return path


@pytest.mark.parametrize("regions", ["EU", 7, [""], [None]])
def test_regions_must_be_all_or_a_list(tmp_path, regions):
    with pytest.raises(PolicyError, match="regions must be"):
        load_policy(policy_with_regions(tmp_path, regions))


@pytest.mark.parametrize("regions, expected", [("all", ("*",)), (["EU", "US"], ("EU", "US")), ([], ())])
def test_valid_regions(tmp_path, regions, expected):
    assert load_policy(policy_with_regions(tmp_path, regions)).roles["sales_eu"].regions == expected


def test_salary_totals_hide_small_groups(admin):
    """agg_salary_by_department is readable by analysts, so no group may be small enough to be one person."""
    minimum = yaml.safe_load(DBT_PROJECT.read_text(encoding="utf-8"))["vars"]["min_group_size"]
    owner = admin.execute("select pg_get_userbyid(relowner) from pg_class where oid = 'marts.agg_salary_by_department'::regclass").fetchone()[0]
    with as_role(admin, owner):
        smallest = admin.execute("select min(headcount) from marts.agg_salary_by_department").fetchone()[0]
    assert smallest is None or smallest >= minimum, f"a salary group of {smallest} people, minimum is {minimum}"
