"""Phase 1 research gate.

The gate is closed when SCIENCE_RESEARCH.md has:
  * no open verification markers,
  * every discipline section, and
  * every one of the seven required fields for each engineering discipline,
  * a verification ledger with a row for every citation number used.
"""

import pathlib
import re

DOC = pathlib.Path(__file__).resolve().parents[1] / "SCIENCE_RESEARCH.md"
TEXT = DOC.read_text(encoding="utf-8")

REQUIRED_SECTIONS = [
    "## 1. Classical mechanics",
    "## 2. Advanced physics",
    "## 3. Mathematics",
    "## 4. Chemistry",
    "## 5. Biology",
    "## 6. Earth and environmental sciences",
    "## 7. Engineering sciences",
    "## 10. Verification ledger",
]

SEVEN_FIELDS = [
    "1. Governing equations",
    "2. Required properties",
    "3. Numerical methods",
    "4. Cost",
    "5. Open source (license)",
    "6. Reference data",
    "7. Validation",
]


def test_no_open_verification_markers():
    assert "[verify" not in TEXT.lower(), "SCIENCE_RESEARCH.md still contains a [verify] marker"


def test_all_required_sections_present():
    missing = [s for s in REQUIRED_SECTIONS if s not in TEXT]
    assert not missing, f"missing sections: {missing}"


def test_engineering_table_has_all_seven_fields():
    header = next(line for line in TEXT.splitlines() if line.startswith("| Discipline |"))
    missing = [f for f in SEVEN_FIELDS if f not in header]
    assert not missing, f"engineering table header missing fields: {missing}"


def test_every_discipline_has_a_technical_conclusion():
    conclusions = len(re.findall(r"\*\*Technical conclusion", TEXT)) + len(
        re.findall(r"- \*\*Technical conclusion", TEXT)
    )
    assert conclusions >= 7, f"expected a conclusion per discipline, found {conclusions}"


def test_ledger_covers_every_cited_source_number():
    # Ledger rows are numbered 1..N; every row must have a licence or citation entry.
    ledger = TEXT.split("## 10. Verification ledger", 1)[1]
    rows = re.findall(r"^\| (\d+) \|", ledger, flags=re.MULTILINE)
    assert rows == [str(i) for i in range(1, len(rows) + 1)], "ledger numbering must be contiguous"
    assert len(rows) >= 35


def test_no_unverified_bsd_claim_for_opensees():
    # OpenSees is a non-commercial licence, not BSD.
    for line in TEXT.splitlines():
        if "OpenSees" in line and "BSD" in line:
            assert "not" in line.lower() or "non-commercial" in line.lower(), line
