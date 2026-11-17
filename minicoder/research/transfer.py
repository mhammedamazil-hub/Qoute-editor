"""Phase 3 — transfer, retention and meta-learning measurements.

All three read the acquisition library and re-score the *same* stored programs against new
inputs. Nothing is re-synthesised here, so a pass means the procedure generalised rather than
the search got lucky a second time.
"""

from __future__ import annotations

import json
import random
import time
from pathlib import Path
from typing import Any

from minicoder.research import tasks as task_mod
from minicoder.research.evaluator import Verdict, evaluate
from minicoder.research.isolation import run_python_isolated
from minicoder.research.private import PrivateStore

# Materially different transfer categories. Each changes something the original draw did
# not vary, so passing the original task again cannot produce these numbers.
TRANSFER_KINDS = ("near_size", "distribution", "edge_cases", "cross_domain")


def _shift_value(value: Any) -> Any:
    """A different input distribution: shift integers, swap the word pool."""
    if isinstance(value, int) and not isinstance(value, bool):
        return value + 1000
    if isinstance(value, float):
        return value + 1000.0
    if isinstance(value, str):
        return "".join(chr((ord(c) - 97 + 13) % 26 + 97) if c.isalpha() and c.islower() else c
                       for c in value) or "x"
    if isinstance(value, list):
        return [_shift_value(v) for v in value]
    if isinstance(value, dict):
        return {k: _shift_value(v) for k, v in value.items()}
    return value


def variant_inputs(family: str, salt: str, kind: str, count: int = 4) -> list[list[Any]]:
    fam = task_mod.FAMILIES.get(family)
    if fam is None:
        return []
    rng = random.Random(f"{salt}|{family}|{kind}")
    out: list[list[Any]] = []
    for i in range(count):
        if kind == "near_size":
            out.append(fam.draw(rng, 12 + i))          # larger inputs than any dev draw
        elif kind == "distribution":
            out.append(_shift_value(fam.draw(rng, 6 + i)))
        elif kind == "edge_cases":
            if fam.edge_draws:
                out.append(fam.edge_draws[i % len(fam.edge_draws)](rng))
        elif kind == "cross_domain":
            # Same invariant, different container: feed a tuple-based structure where the
            # family expects a list, which a procedure that hard-codes list fusion fails.
            args = fam.draw(rng, 5 + i)
            out.append([tuple(a) if isinstance(a, list) else a for a in args])
    return [a for a in out if a]


def score_program(family: str, code: str, inputs: list[list[Any]], *,
                  mode: str | None = None, timeout: float = 15.0) -> dict[str, Any]:
    """Run one stored program on arbitrary inputs and compare with the reference."""
    expected = [task_mod.expected_output(family, args) for args in inputs]
    usable = [(a, e) for a, e in zip(inputs, expected)
              if not isinstance(e, task_mod._Missing)]
    if not usable:
        return {"cases": 0, "passed": 0, "rate": 0.0, "verdict": "no_reference"}
    out = run_python_isolated(code, [a for a, _ in usable], timeout=timeout, mode=mode)
    if not out.ok:
        return {"cases": len(usable), "passed": 0, "rate": 0.0,
                "verdict": "exception" if "PermissionError" not in out.error else "cheating",
                "error": out.error[:200]}
    passed = sum(1 for (_, exp), got in zip(usable, out.values)
                 if json.loads(json.dumps(exp, default=repr)) == json.loads(json.dumps(got, default=repr)))
    return {"cases": len(usable), "passed": passed, "rate": round(passed / len(usable), 3),
            "verdict": "pass" if passed == len(usable) else "wrong_value"}


def transfer_report(library: dict[str, Any], store: PrivateStore, *,
                    mode: str | None = None) -> dict[str, Any]:
    salt = store.salt()  # noqa: F841 - salt feeds variant_inputs below
    entries = library.get("entries", {})
    per_family: dict[str, Any] = {}
    totals = {kind: {"cases": 0, "passed": 0} for kind in TRANSFER_KINDS}
    for family, code in sorted(entries.items()):
        rows = {}
        for kind in TRANSFER_KINDS:
            inputs = variant_inputs(family, salt, kind)
            if not inputs:
                rows[kind] = {"cases": 0, "passed": 0, "rate": None, "verdict": "no_variant"}
                continue
            got = score_program(family, code, inputs, mode=mode)
            rows[kind] = got
            totals[kind]["cases"] += got["cases"]
            totals[kind]["passed"] += got["passed"]
        per_family[family] = rows
    summary = {
        kind: {"cases": totals[kind]["cases"], "passed": totals[kind]["passed"],
               "rate": (round(totals[kind]["passed"] / totals[kind]["cases"], 3)
                        if totals[kind]["cases"] else None)}
        for kind in TRANSFER_KINDS
    }
    return {"generated_at": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()),
            "families": len(entries), "summary": summary, "per_family": per_family,
            "note": ("Programs are re-scored unchanged. 'distribution' shifts integer values "
                     "by 1000 and rotates lower-case letters; 'cross_domain' converts lists to "
                     "tuples; neither appears in the acquisition draws.")}


def retention_report(library: dict[str, Any], store: PrivateStore, *,
                     mode: str | None = None, cycles: int = 0) -> dict[str, Any]:
    """Execution-based retention: the stored program must still pass hidden tests."""
    rows = {}
    verified = set(library.get("verified", []))
    tasks = library.get("tasks", {})
    for family, code in sorted(library.get("entries", {}).items()):
        # Score the *same task* the procedure was acquired for. Scoring another task of the
        # family measures transfer, not retention, and mixing them overstated decay
        # (measured: 'chunk' looked lost when it was merely applied to a different draw).
        record = _record_for(family, tasks.get(family))
        verdict: Verdict = evaluate(record, code, store=store, mode=mode)
        rows[family] = {"retained": verdict.passed, "verdict": verdict.verdict,
                        "cases": verdict.cases, "record_present": True,
                        "verified_at_acquisition": family in verified}
    retained = sum(1 for r in rows.values() if r["retained"])
    verified_rows = [r for f, r in rows.items() if f in verified]
    return {"generated_at": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()),
            "cycles": cycles, "families": len(rows), "retained": retained,
            "retention_rate": round(retained / max(1, len(rows)), 3),
            "verified_at_acquisition": len(verified_rows),
            "verified_retained": sum(1 for r in verified_rows if r["retained"]),
            "per_family": rows,
            "note": "record_present is reported separately and never counted as retention."}


def meta_report(acquisition: dict[str, Any]) -> dict[str, Any]:
    """Learning efficiency: does a later task of a family cost less than the first?"""
    rows = acquisition.get("rows", [])
    first: dict[tuple[str, str], int] = {}
    later: dict[tuple[str, str], list[int]] = {}
    for row in rows:
        if row["arm"] != "C" or row["kind"] != "regular":   # C never reuses, so cost is comparable
            continue
        key = (str(row["seed"]), row["family"])
        if key not in first:
            first[key] = row["candidates"]
        else:
            later.setdefault(key, []).append(row["candidates"])

    reuse_rows = [r for r in rows if r["arm"] == "E" and r["reused"]]
    c_cost = [r["candidates"] for r in rows if r["arm"] == "C" and r["kind"] != "impossible"]
    e_cost = [r["candidates"] for r in rows if r["arm"] == "E" and r["kind"] != "impossible"]
    return {
        "mean_candidates_arm_C": round(sum(c_cost) / max(1, len(c_cost)), 1),
        "mean_candidates_arm_E": round(sum(e_cost) / max(1, len(e_cost)), 1),
        "cost_reduction_from_reuse": (round(1 - (sum(e_cost) / max(1, len(e_cost)))
                                            / max(1e-9, sum(c_cost) / max(1, len(c_cost))), 3)
                                      if c_cost and e_cost else None),
        "generated_at": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()),
        "first_occurrence_candidates": round(
            sum(first.values()) / max(1, len(first)), 1),
        "later_occurrence_candidates": round(
            sum(sum(v) for v in later.values()) / max(1, sum(len(v) for v in later.values())), 1),
        "families_measured": len(first),
        "reused_tasks_full_arm": len(reuse_rows),
        "note": ("Candidates are the real search cost. Arm C re-synthesises on every task; "
                 "arm E reuses a consolidated procedure. A lower later-occurrence cost without "
                 "reuse is the grammar finding the same program, and is labelled as such."),
    }


def _record_for(family: str, task: dict[str, Any] | None = None) -> task_mod.TaskRecord:
    seed = int((task or {}).get("seed", 0))
    key = (task or {}).get("key")
    recs = task_mod.generate(seed, 24)
    if key:
        for rec in recs:
            if rec.key == key:
                return rec
    for rec in recs:
        if rec.family == family:
            return rec
    return recs[0]


def write_reports(out_dir: Path, acquisition: dict[str, Any], transfer: dict[str, Any],
                  retention: dict[str, Any], meta: dict[str, Any]) -> dict[str, str]:
    out_dir.mkdir(parents=True, exist_ok=True)
    stamp = time.strftime("%Y%m%dT%H%M%SZ", time.gmtime())
    paths = {}
    for name, payload in (("acquisition", acquisition), ("transfer", transfer),
                          ("retention", retention), ("meta", meta)):
        dated = out_dir / f"{name}_{stamp}.json"
        dated.write_text(json.dumps(payload, indent=2, default=str), encoding="utf-8")
        (out_dir / f"{name}_latest.json").write_text(json.dumps(payload, indent=2, default=str),
                                                     encoding="utf-8")
        paths[name] = str(dated)
    return paths
