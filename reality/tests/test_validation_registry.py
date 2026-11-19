"""Every registered scientific validation case must pass. A failing case means a solver regressed."""

import pytest

from reality import validation as V

CASES = V.CASES


def test_registry_is_not_empty_and_covers_all_domains():
    domains = {c.domain for c in CASES}
    assert {"mechanics", "gravity", "thermal", "optics", "acoustics", "fracture", "structures", "materials", "objects"} <= domains
    assert len(CASES) >= 40


def test_case_ids_are_unique():
    ids = [c.case_id for c in CASES]
    assert len(ids) == len(set(ids))


@pytest.mark.parametrize("case", CASES, ids=[c.case_id for c in CASES])
def test_validation_case(case):
    measured, err, ok = case.evaluate()
    assert ok, f"{case.case_id} ({case.description}): measured={measured!r}, error={err:.3e}, tol={case.tolerance:g}"
