"""The live database matches the policy exactly (ADR-015)."""
from drift.check import find_drift


def test_no_drift(admin, policy):
    findings = find_drift(admin, policy)
    assert not findings, "Drift:\n  " + "\n  ".join(map(str, findings))
