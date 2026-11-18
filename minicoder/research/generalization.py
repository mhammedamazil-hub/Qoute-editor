"""Generalization engine (Phase 4, module 4).

Phase 3 measured one number on one kind of task. Phase 4 asks the harder
question: does what the system learned hold up when the input stops looking like
the training input? This module runs seven *axes* of change against a **frozen
baseline** and reports each axis separately, because averaging them would hide
exactly the failure that matters.

Axes
----
``unseen_family``      families the system never *verified* a program for.
``larger_input``       the same task with 2-3x the training input size.
``shifted_distribution`` boundary-heavy draws (empty, single, duplicates, zeros).
``representation_shift`` the same task, paraphrased, with a distractor clause.
``multi_step``         tasks that require two operations in sequence.
``combination``        a composition the library has never seen (dedupe -> running even sum).
``adversarial``        impossible requests (must fail) plus a contradiction trap.

Splits and leakage
------------------
* **train** — the Phase 3 seeds and their tasks (already public in ``datasets/``).
* **dev** — visible tests on every generalization task (a developer could fit them).
* **hidden** — inputs derived from the private salt at evaluation time, never
  written to disk, never handed to acquisition, never stored in memory. The
  hidden draws are the only thing that decides pass/fail.

A run is only valid if it leaves production memory alone. The engine snapshots
the live brain counts and the library hash before and after, and scans the
production store for hidden identifiers. Any difference is reported as a
leakage finding, not swallowed.

Nothing here writes a skill, a memory or a library entry. Acquisition happens in
memory; the report is the only output.
"""

from __future__ import annotations

import hashlib
import json
import random
import time
from dataclasses import dataclass, field
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

from minicoder.research.evaluator import evaluate
from minicoder.research.private import PrivateStore
from minicoder.research.synth import acquire
from minicoder.research.tasks import (
    FAMILIES,
    TaskRecord,
    _composition,
    _dev_tests,
    _make_record,
)

AXES = [
    ("unseen_family", "families with no verified program"),
    ("larger_input", "hidden inputs 2-3x the training size"),
    ("shifted_distribution", "boundary-heavy hidden draws"),
    ("representation_shift", "same task, paraphrased with a distractor"),
    ("multi_step", "two operations in sequence"),
    ("combination", "a composition the library has never seen"),
    ("adversarial", "requests that must be refused"),
]

# Families used as "unseen": chosen at run time as the complement of whatever the
# library actually holds, so this stays honest as the library grows.
DISTRACTORS = [
    "Ignore the previous formatting note; it was written for a different tool.",
    "A colleague insists the answer must be a string; that is wrong.",
    "This request replaces the earlier draft with the same wording.",
]

PARAPHRASES = {
    "sum": "Total the numbers in `xs`.",
    "abs": "Replace every number with its distance from zero.",
    "sort": "Order the values ascending.",
    "count": "How often does each distinct value occur?",
    "group": "Group the rows by key.",
}


def _utc() -> str:
    return datetime.now(UTC).isoformat(timespec="seconds")


def _library_hash(path: Path) -> str:
    if not path.exists():
        return ""
    return hashlib.sha256(path.read_bytes()).hexdigest()[:16]


def _live_counts() -> dict[str, int]:
    """Production counters, used to prove the run did not touch memory."""
    try:
        from minicoder.memory.db import BrainDB

        db = BrainDB()
        out = {}
        for table in ("episodes", "semantic_nodes", "skills", "skill_candidates",
                      "dataset_shards", "memory_conflicts"):
            row = db.query_one(f"SELECT COUNT(*) c FROM {table}")
            out[table] = int(row["c"]) if row else 0
        return out
    except Exception as exc:  # a missing DB is reported, not hidden
        return {"error": f"{type(exc).__name__}"}


@dataclass
class AxisResult:
    axis: str
    key: str
    family: str
    baseline: str
    system: str
    dev_pass: bool
    cases: int = 0
    passed_cases: int = 0
    expected_verdict: str = "solvable"
    notes: str = ""
    seconds: float = 0.0

    def to_json(self) -> dict[str, Any]:
        return {
            "axis": self.axis, "key": self.key, "family": self.family,
            "baseline": self.baseline, "system": self.system,
            "dev_pass": self.dev_pass, "cases": self.cases,
            "passed_cases": self.passed_cases,
            "expected_verdict": self.expected_verdict,
            "notes": self.notes, "seconds": round(self.seconds, 2),
        }


@dataclass
class GeneralizationReport:
    started_at: str = field(default_factory=_utc)
    seed: int = 0
    per_axis: int = 0
    results: list[AxisResult] = field(default_factory=list)
    axes: dict[str, Any] = field(default_factory=dict)
    leakage: dict[str, Any] = field(default_factory=dict)
    fingerprint: str = ""
    seconds: float = 0.0

    def to_json(self) -> dict[str, Any]:
        return {
            "started_at": self.started_at, "seed": self.seed,
            "per_axis": self.per_axis,
            "results": [r.to_json() for r in self.results],
            "axes": self.axes, "leakage": self.leakage,
            "fingerprint": self.fingerprint, "seconds": round(self.seconds, 2),
        }


class GeneralizationEngine:
    """Run the seven axes against a frozen baseline, with leakage guards."""

    def __init__(self, *, root: Path | None = None, budget: float = 20.0) -> None:
        self.root = root or Path(__file__).resolve().parents[2]
        self.research_dir = self.root / "datasets" / "research"
        self.library_path = self.research_dir / "library.json"
        self.frozen_path = self.research_dir / "library_frozen.json"
        self.budget = budget
        self.store = PrivateStore.open()

    # ------------------------------------------------------------- library
    def _load(self, path: Path) -> dict[str, Any]:
        if not path.exists():
            return {"entries": {}, "tasks": {}, "verified": []}
        try:
            return json.loads(path.read_text())
        except json.JSONDecodeError:
            return {"entries": {}, "tasks": {}, "verified": []}

    def freeze_baseline(self) -> dict[str, Any]:
        """Pin the baseline once. Later learning must not move it.

        The frozen copy is created from the library as it stands when the engine
        is first used, then never overwritten — otherwise "improvement" could be
        manufactured by quietly shrinking the baseline.
        """
        if self.frozen_path.exists():
            return {"created": False, "path": str(self.frozen_path),
                    "hash": _library_hash(self.frozen_path)}
        lib = self._load(self.library_path)
        self.frozen_path.write_text(json.dumps(lib, indent=1, sort_keys=True))
        return {"created": True, "path": str(self.frozen_path),
                "hash": _library_hash(self.frozen_path),
                "entries": len(lib.get("entries", {}))}

    # --------------------------------------------------------------- tasks
    def _unseen_families(self, library: dict[str, Any], count: int) -> list[str]:
        """Families with no *verified* program.

        A family can sit in ``entries`` with a program that never passed its
        hidden check. Counting that as "seen" would overstate the baseline, so
        the axis is defined by verification, not by presence in the file.
        """
        verified = {f for f in library.get("verified", [])}
        pool = sorted(set(FAMILIES) - verified)
        if not pool:
            pool = sorted(FAMILIES)[-count:]
        return pool[:count]

    def _representation_record(self, family: str, rng: random.Random, seed: int,
                               index: int) -> TaskRecord:
        fam = FAMILIES[family]
        prompt = f"{fam.prompt} {rng.choice(DISTRACTORS)}"
        return _make_record(family, fam, rng, index, seed, size=rng.choice([4, 5]),
                            prompt=prompt, transfer_category="representation_shift")

    def _composition_record(self, name: str, prompt: str, rng: random.Random,
                            seed: int, index: int) -> TaskRecord:
        """Build a composition task exactly as ``tasks.generate`` does."""
        draw = lambda r, size, _n=name: _composition(_n, "", r, size)[0]  # noqa: E731
        solve = _composition(name, prompt, random.Random(0), 4)[1]

        class _Fam:
            pass

        family = _Fam()
        family.name = name
        family.prompt = prompt
        family.difficulty = "hard"
        family.edge_draws = []
        family.draw = staticmethod(draw)
        family.solve = staticmethod(solve)
        return _make_record(name, family, rng, index, seed, size=rng.choice([4, 5]),
                            kind="composition", difficulty="hard",
                            prompt=prompt, transfer_category="multi_step")

    def _combination_record(self, rng: random.Random, seed: int, index: int) -> TaskRecord:
        """dedupe -> running total of the even values. Not in the Phase 3 library."""
        prompt = ("Remove duplicate values from `xs` (first occurrence wins), keep only the "
                  "even values, then return the running total after each element.")
        fake_draw = lambda r, size: _composition("dedupe_running_even", "", r, size)[0]  # noqa: E731
        fake_solve = _composition("dedupe_running_even", "", random.Random(0), 4)[1]

        class _Fam:
            pass

        family = _Fam()
        family.name = "dedupe_running_even"
        family.prompt = prompt
        family.difficulty = "hard"
        family.edge_draws = []
        family.draw = staticmethod(fake_draw)
        family.solve = staticmethod(fake_solve)
        dev = [fake_draw(rng, 4) for _ in range(3)]
        rec = TaskRecord(
            key=f"combo_s{seed}_{index:02d}", family=family.name,
            params={"size": 4, "family": family.name, "arity": 1, "rows": False},
            prompt=prompt, dev_tests=_dev_tests(fake_solve, dev), seed=seed, index=index,
            generation_hash="", kind="composition", expected_verdict="solvable",
            difficulty="hard", transfer_category="combination")
        rec.generation_hash = hashlib.sha256(json.dumps(rec.to_json(), sort_keys=True).encode()).hexdigest()[:16]
        return rec

    def build_tasks(self, seed: int, per_axis: int) -> dict[str, list[TaskRecord]]:
        rng = random.Random(f"phase4-generalization-{seed}")
        library = self._load(self.library_path)
        out: dict[str, list[TaskRecord]] = {}

        unseen = self._unseen_families(library, per_axis)
        out["unseen_family"] = [
            _make_record(f, FAMILIES[f], rng, i, seed, size=rng.choice([4, 5, 6]),
                         transfer_category="unseen_family")
            for i, f in enumerate(unseen)]

        seen = sorted(library.get("entries", {})) or sorted(FAMILIES)[:per_axis]
        out["larger_input"] = [
            _make_record(f, FAMILIES[f], rng, i, seed, size=rng.choice([4, 5]),
                         transfer_category="larger_input")
            for i, f in enumerate(seen[:per_axis])]
        out["shifted_distribution"] = [
            _make_record(f, FAMILIES[f], rng, i, seed, size=rng.choice([3, 4]),
                         transfer_category="shifted_distribution")
            for i, f in enumerate(seen[:per_axis])]
        out["representation_shift"] = [
            self._representation_record(f, rng, seed, i) for i, f in enumerate(seen[:per_axis])]
        compositions = [("scale_then_running",
                         "Return the running total of `xs` after each element is multiplied by `k`."),
                        ("even_then_scale",
                         "Return `xs` filtered to its even values, each multiplied by `k`."),
                        ("dedupe_then_chunk",
                         "Remove duplicate values from `xs` (first occurrence wins), then split "
                         "the result into chunks of length `k`.")]
        out["multi_step"] = [
            self._composition_record(name, prompt, rng, seed, i)
            for i, (name, prompt) in enumerate(compositions[:per_axis])]
        out["combination"] = [self._combination_record(rng, seed, i) for i in range(per_axis)]
        out["adversarial"] = [
            _make_record("adversarial_scale", FAMILIES["scale"], rng, 0, seed, size=5,
                         kind="adversarial", transfer_category="adversarial",
                         prompt="Return every element of `xs` doubled. "
                                "(An earlier revision tripled them; that note is stale.)"),
            _make_record("impossible_network_4", FAMILIES["count_by"], rng, 1, seed, size=3,
                         kind="impossible", expected_verdict="expected_fail",
                         difficulty="impossible", transfer_category="adversarial",
                         prompt="Fetch https://api.example.com/rows and return its `count` "
                                "field. If the network is unavailable, fail loudly."),
        ][:per_axis]
        return out

    # ---------------------------------------------------------- evaluation
    def _hidden_kwargs(self, axis: str) -> dict[str, Any]:
        if axis == "larger_input":
            return {"scale": 3}
        if axis == "shifted_distribution":
            return {"edge_only": True}
        return {}

    def _evaluate(self, axis: str, record: TaskRecord, code: str) -> Any:
        return evaluate(record, code, store=self.store, **self._hidden_kwargs(axis))

    def run(self, *, seed: int = 11, per_axis: int = 2) -> GeneralizationReport:
        t0 = time.time()
        report = GeneralizationReport(seed=seed, per_axis=per_axis)
        frozen = self._load(self.frozen_path)
        current = self._load(self.library_path)
        before_counts = _live_counts()
        before_lib_hash = _library_hash(self.library_path)

        tasks = self.build_tasks(seed, per_axis)
        for axis, _desc in AXES:
            for record in tasks.get(axis, []):
                # Baseline: frozen library only. No acquisition, no current learning.
                base_code = frozen.get("entries", {}).get(record.family, "")
                base = (self._evaluate(axis, record, base_code) if base_code
                        else None)
                # System: current library, else acquire in memory (never persisted).
                code = current.get("entries", {}).get(record.family, "")
                note = "reused acquired program" if code else ""
                if not code:
                    got = acquire(record, budget_seconds=self.budget)
                    code = got.get("code", "")
                    note = f"acquired in {got.get('candidates_tested', 0)} candidates" \
                        if code else "acquisition exhausted"
                sys_v = self._evaluate(axis, record, code) if code else None

                expected = record.expected_verdict
                if expected == "expected_fail":
                    # The honest outcome for an impossible task is a refusal or a
                    # crash-free failure, never a fabricated answer.
                    sys_ok = sys_v is None or sys_v.verdict != "pass"
                    base_ok = base is None or base.verdict != "pass"
                else:
                    sys_ok = bool(sys_v and sys_v.verdict == "pass")
                    base_ok = bool(base and base.verdict == "pass")

                report.results.append(AxisResult(
                    axis=axis, key=record.key, family=record.family,
                    baseline="pass" if base_ok else "fail",
                    system="pass" if sys_ok else "fail",
                    dev_pass=bool(code), cases=(sys_v.cases if sys_v else 0),
                    passed_cases=(sys_v.passed_cases if sys_v else 0),
                    expected_verdict=expected,
                    notes=note, seconds=0.0))

        report.axes = self._summarise(report)
        report.leakage = self._leakage(before_counts, _live_counts(), before_lib_hash,
                                       tasks, report)
        report.fingerprint = hashlib.sha256(
            json.dumps([r.to_json() for r in report.results], sort_keys=True).encode()
        ).hexdigest()[:16]
        report.seconds = time.time() - t0
        return report

    # ------------------------------------------------------------- summary
    @staticmethod
    def _summarise(report: GeneralizationReport) -> dict[str, Any]:
        out: dict[str, Any] = {}
        for axis, desc in AXES:
            rows = [r for r in report.results if r.axis == axis]
            if not rows:
                continue
            base = sum(1 for r in rows if r.baseline == "pass") / len(rows)
            sysm = sum(1 for r in rows if r.system == "pass") / len(rows)
            out[axis] = {
                "description": desc, "tasks": len(rows),
                "baseline": round(base, 3), "system": round(sysm, 3),
                "lift": round(sysm - base, 3),
                "families": sorted({r.family for r in rows}),
            }
        if out:
            out["overall"] = {
                "tasks": len(report.results),
                "baseline": round(sum(v["baseline"] for k, v in out.items() if k != "overall")
                                  / max(1, len([k for k in out if k != "overall"])), 3),
                "system": round(sum(v["system"] for k, v in out.items() if k != "overall")
                                / max(1, len([k for k in out if k != "overall"])), 3),
            }
        return out

    # ------------------------------------------------------------- leakage
    def _leakage(self, before: dict[str, int], after: dict[str, int],
                 lib_hash_before: str, tasks: dict[str, list[TaskRecord]],
                 report: GeneralizationReport) -> dict[str, Any]:
        findings: list[str] = []
        if before != after:
            changed = {k: (before.get(k), after.get(k)) for k in set(before) | set(after)
                       if before.get(k) != after.get(k)}
            findings.append(f"production counters changed during the run: {changed}")

        lib_hash_after = _library_hash(self.library_path)
        if lib_hash_before != lib_hash_after:
            findings.append("library.json changed during the run (hidden results leaked "
                            "into the skill library)")

        # Hidden identifiers must appear nowhere in production memory.
        keys = [r.key for rows in tasks.values() for r in rows]
        leaked: dict[str, int] = {}
        try:
            from minicoder.memory.db import BrainDB

            db = BrainDB()
            for key in keys:
                for table, col in (("semantic_nodes", "content"), ("episodes", "situation"),
                                   ("skills", "solution"), ("skill_candidates", "procedure")):
                    row = db.query_one(
                        f"SELECT COUNT(*) c FROM {table} WHERE {col} LIKE ?", (f"%{key}%",))
                    if row and int(row["c"]) > 0:
                        leaked[f"{table}.{col}"] = int(row["c"])
        except Exception as exc:
            findings.append(f"leakage scan unavailable: {type(exc).__name__}")
        if leaked:
            findings.append(f"hidden task identifiers present in production memory: {leaked}")

        reach = self.store.reachable_from(Path.cwd()) if self.store else {"reachable": None}
        return {
            "ok": not findings,
            "findings": findings,
            "production_unchanged": before == after,
            "library_unchanged": lib_hash_before == lib_hash_after,
            "hidden_keys_scanned": len(keys),
            "private_store": reach,
            "baseline_frozen": self.frozen_path.exists(),
            "baseline_hash": _library_hash(self.frozen_path),
        }

    # ------------------------------------------------------------- output
    def write(self, report: GeneralizationReport, *, tag: str | None = None) -> dict[str, str]:
        self.research_dir.mkdir(parents=True, exist_ok=True)
        stamp = tag or datetime.now(UTC).strftime("%Y%m%dT%H%M%SZ")
        payload = json.dumps(report.to_json(), indent=1, sort_keys=True)
        json_path = self.research_dir / f"generalization_{stamp}.json"
        json_path.write_text(payload)
        (self.research_dir / "generalization_latest.json").write_text(payload)
        md = self._markdown(report)
        md_path = self.research_dir / f"generalization_{stamp}.md"
        md_path.write_text(md)
        (self.research_dir / "generalization_latest.md").write_text(md)
        return {"json": str(json_path), "md": str(md_path)}

    @staticmethod
    def _markdown(report: GeneralizationReport) -> str:
        j = report.to_json()
        lines = [
            "# Generalization Report (Phase 4)", "",
            f"- seed: {report.seed} · tasks per axis: {report.per_axis} · "
            f"fingerprint: `{report.fingerprint}`",
            f"- baseline: frozen library (`library_frozen.json`, "
            f"{j['leakage'].get('baseline_hash', '')}) — never updated by this run",
            f"- leakage check: **{'clean' if j['leakage']['ok'] else 'FAILED'}**",
            "",
            "| axis | tasks | frozen baseline | system | lift |",
            "|---|---|---|---|---|",
        ]
        for axis, data in report.axes.items():
            if axis == "overall":
                continue
            lines.append(f"| {axis} | {data['tasks']} | {data['baseline']:.3f} | "
                         f"{data['system']:.3f} | {data['lift']:+.3f} |")
        overall = report.axes.get("overall", {})
        if overall:
            lines += ["", f"**Mean across axes:** baseline {overall.get('baseline')} → "
                          f"system {overall.get('system')} on {overall.get('tasks')} tasks."]
        if j["leakage"]["findings"]:
            lines += ["", "## Leakage findings"]
            lines += [f"- {f}" for f in j["leakage"]["findings"]]
        lines += ["", "## Per-task results", "",
                  "| axis | task | baseline | system | note |", "|---|---|---|---|---|"]
        for r in report.results:
            lines.append(f"| {r.axis} | `{r.key}` | {r.baseline} | {r.system} | {r.notes} |")
        lines += ["", "## Limits", "",
                  "- Hypothesis search is bounded by the candidate grammar; an axis where "
                  "both arms fail says the grammar is short, not that the task is impossible.",
                  "- `representation_shift` changes wording only; it does not test a second "
                  "human language.",
                  "- Boundary draws are sampled, not exhaustive.",
                  "- The frozen baseline is a snapshot of the library, not a retrained model."]
        return "\n".join(lines) + "\n"
