"""The hand-written cases in cases.yaml, each run as the real person or account."""
from pathlib import Path

import pytest
import yaml

CASES = yaml.safe_load((Path(__file__).parent / "cases.yaml").read_text(encoding="utf-8"))


@pytest.mark.parametrize("case", CASES, ids=[c["name"] for c in CASES])
def test_case(case, sessions):
    outcome, result = sessions.run(case["who"], case["sql"])
    assert outcome == case["expect"], f"{case['who']}: expected {case['expect']}, got {outcome}: {result}"
    if "rows" in case:
        assert {r[0] for r in result} == set(case["rows"])
