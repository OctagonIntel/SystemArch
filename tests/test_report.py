"""The access review report (Phase 4). The first tests need no database: they read the policy."""
import pytest

from drift.check import policy_regions
from report.build import build
from report.collect import collect


@pytest.fixture(scope="module")
def offline(policy):
    return collect(policy)


def cell(review, login, table):
    return review.cells[(login, table)]


def test_policy_only_report_matches_the_policy(offline):
    assert cell(offline, "sofia_marchetti", "marts.dim_customer").regions == ["EU"]
    assert cell(offline, "daniel_reyes", "marts.fct_deals").regions == ["EU", "US"]
    assert cell(offline, "amara_okafor", "marts.dim_employee").level == "public"  # hashed
    assert cell(offline, "grace_liu", "marts_restricted.dim_employee").level == "confidential"
    assert "national_id" in cell(offline, "grace_liu", "marts_restricted.dim_employee").hidden
    assert cell(offline, "tom_whitfield", "marts_restricted.dim_employee").level == "restricted"
    assert cell(offline, "tom_whitfield", "marts_restricted.dim_employee").via == ["finance", "payroll"]
    assert cell(offline, "svc_ingest_hr", "raw.hr_employees").writes == ["INSERT"]
    assert not cell(offline, "svc_ingest_hr", "raw.hr_employees").reads
    assert cell(offline, "svc_transform", "marts.dim_customer").owner
    assert not any(cell(offline, "noah_clarke", t.key).reads for t in offline.tables)


def test_report_renders(offline, policy):
    html = build(offline, policy)
    assert "Policy only" in html and "Priya Nair" in html and "<script>" in html


@pytest.mark.parametrize("qual, regions", [
    ("true", {"*"}),
    ("false", set()),
    ("(region = ANY ('{EU,US}'::text[]))", {"EU", "US"}),
    ("(region = ANY ('{EMEA2}'::text[]))", {"EMEA2"}),
])
def test_rls_policy_regions(qual, regions):
    assert policy_regions(qual) == regions


def test_live_report_agrees_with_the_database(admin, policy):
    """The report reads the catalog its own way. It must agree with the sweep and drift check."""
    review = collect(policy, admin)
    problems = [f"{l} on {t}: {p}" for (l, t), c in review.cells.items() for p in c.problems]
    assert not review.missing_logins and not problems, "\n".join(problems)
    assert cell(review, "sofia_marchetti", "marts.dim_customer").regions == ["EU"]
    assert "national_id" in cell(review, "grace_liu", "marts_restricted.dim_employee").hidden
