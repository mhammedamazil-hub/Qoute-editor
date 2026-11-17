"""Phase 3 — controlled experiments over blind tasks.

Arms (identical task records, seeds and budgets):

A  baseline        the model alone: no search, no memory of solutions
B  memory only     reuse a previously stored program for the family, no acquisition
C  discovery only  acquire, but discard the result: no retention across tasks
D  acquisition     acquire and keep the program in run memory, never consolidated
E  full            acquire, consolidate into the research library, reuse it later
F1..F3             ablations of the acquisition search (depth, binary ops, row ops)

Every arm is scored by the independent evaluator on hidden inputs only. The agent never
receives expected values, only a verdict class. Production memory is never written: the live
brain's row counts are asserted unchanged before and after a run.
"""

from __future__ import annotations

import json
import platform
import subprocess
import time
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

from minicoder.research import synth
from minicoder.research.evaluator import Verdict, evaluate
from minicoder.research.private import PrivateStore
from minicoder.research.tasks import GENERATOR_VERSION, TaskRecord, generate

RESEARCH_DIR = Path("datasets/research")
LIBRARY = RESEARCH_DIR / "library.json"
ARMS = ("A", "B", "C", "D", "E", "F1", "F2", "F3")


# --------------------------------------------------------------------------- helpers
def _live_brain_counts() -> dict[str, int]:
    from minicoder.memory.db import BrainDB

    db = BrainDB()
    try:
        return {
            "skills": db.query_one("SELECT COUNT(*) FROM skills")[0],
            "experiments": db.query_one("SELECT COUNT(*) FROM experiments")[0],
            "skill_candidates": db.query_one("SELECT COUNT(*) FROM skill_candidates")[0],
        }
    finally:
        db.close()


def _git_commit() -> str:
    try:
        return subprocess.run(["git", "rev-parse", "HEAD"], capture_output=True, text=True,
                              timeout=10).stdout.strip() or "unknown"
    except (OSError, subprocess.SubprocessError):
        return "unknown"


def _hardware() -> dict[str, Any]:
    import os

    try:
        import torch

        torch_version = torch.__version__
        cuda = torch.cuda.is_available()
    except Exception:
        torch_version, cuda = "absent", False
    return {"cores": os.cpu_count(), "torch": torch_version, "cuda": cuda,
            "python": platform.python_version(), "platform": platform.platform()}


def bootstrap_ci(values: list[float], *, resamples: int = 10000,
                 alpha: float = 0.05) -> dict[str, float]:
    """Percentile bootstrap. n < 5 is reported as observed, not established."""
    import random

    clean = [v for v in values if v is not None]
    if not clean:
        return {"mean": 0.0, "lo": 0.0, "hi": 0.0, "n": 0, "established": False}
    if len(clean) == 1:
        return {"mean": clean[0], "lo": clean[0], "hi": clean[0], "n": 1, "established": False}
    rng = random.Random(12345)
    means = []
    for _ in range(resamples):
        means.append(sum(rng.choice(clean) for _ in clean) / len(clean))
    means.sort()
    lo = means[int((alpha / 2) * len(means))]
    hi = means[int((1 - alpha / 2) * len(means)) - 1]
    return {"mean": round(sum(clean) / len(clean), 4), "lo": round(lo, 4), "hi": round(hi, 4),
            "n": len(clean), "established": len(clean) >= 5}


# --------------------------------------------------------------------------- library
def load_library(path: Path | None = None) -> dict[str, Any]:
    p = path or LIBRARY
    if not p.exists():
        return {"entries": {}}
    return json.loads(p.read_text(encoding="utf-8"))


def save_library(lib: dict[str, Any], path: Path | None = None) -> None:
    p = path or LIBRARY
    p.parent.mkdir(parents=True, exist_ok=True)
    p.write_text(json.dumps(lib, indent=2, sort_keys=True), encoding="utf-8")


# --------------------------------------------------------------------------- arms
@dataclass
class ArmResult:
    arm: str
    key: str
    seed: int
    family: str
    kind: str
    acquired: bool
    verdict: str
    dev_pass: bool = False
    test_fitted: bool = False
    candidates: int = 0
    seconds: float = 0.0
    strategy: str = ""
    reused: bool = False
    notes: str = ""
    detections: dict[str, Any] = field(default_factory=dict)
    mode: str = ""
    os_boundary: bool = False

    def to_json(self) -> dict[str, Any]:
        return {"arm": self.arm, "key": self.key, "seed": self.seed,
                "family": self.family, "kind": self.kind,
                "acquired": self.acquired, "verdict": self.verdict, "dev_pass": self.dev_pass,
                "test_fitted": self.test_fitted, "candidates": self.candidates,
                "seconds": round(self.seconds, 3), "strategy": self.strategy,
                "reused": self.reused, "notes": self.notes,
                "detections": self.detections, "mode": self.mode,
                "os_boundary": self.os_boundary}


def _dev_pass(code: str, record: TaskRecord, mode: str | None) -> bool:
    if not code.strip():
        return False
    return bool(synth.batch_probe([code], record.dev_tests, mode=mode)[0])


def _model_attempt(record: TaskRecord) -> tuple[str, str]:
    """Arm A: what the system can do with no acquisition at all."""
    try:
        from minicoder.cognition.engine import NeuralBrain

        brain = NeuralBrain()
        if not brain.model:
            return "", "no checkpoint available"
        gen = brain.best_of(f"# {record.prompt}\ndef solve", k=3, max_new_tokens=96)
        text = (gen.text or "").strip()
        if "def solve" not in text:
            text = "def solve(xs):\n    return " + (text.splitlines()[0] if text else "None") + "\n"
        return text, "model best_of k=3"
    except Exception as exc:  # noqa: BLE001 - an unavailable model is a failed arm, not a crash
        return "", f"model unavailable: {type(exc).__name__}"


def run_arm(arm: str, record: TaskRecord, store: PrivateStore, *,
            library: dict[str, Any], run_cache: dict[str, str],
            mode: str | None = None, budget: float = 60.0) -> ArmResult:
    t0 = time.time()
    base = {"arm": arm, "key": record.key, "seed": record.seed,
            "family": record.family, "kind": record.kind}

    if arm == "A":
        code, note = _model_attempt(record)
        verdict: Verdict = evaluate(record, code, store=store, mode=mode)
        return ArmResult(**base, acquired=False, verdict=verdict.verdict,
                         dev_pass=_dev_pass(code, record, mode), candidates=0,
                         seconds=time.time() - t0, strategy="model_only", notes=note,
                         detections=verdict.detections, mode=verdict.mode,
                         os_boundary=verdict.os_boundary)

    if arm == "B":
        code = library.get("entries", {}).get(record.family, "")
        verdict = evaluate(record, code, store=store, mode=mode) if code else Verdict("no_result")
        return ArmResult(**base, acquired=False, verdict=verdict.verdict,
                         dev_pass=_dev_pass(code, record, mode) if code else False,
                         seconds=time.time() - t0, strategy="memory_retrieval",
                         reused=bool(code), notes="no acquisition" if not code else "reused stored",
                         mode=verdict.mode, os_boundary=verdict.os_boundary)

    if arm in ("C", "D", "E"):
        cached = run_cache.get(record.family) or (library["entries"].get(record.family)
                                                 if arm == "E" else "")
        if cached:
            verdict = evaluate(record, cached, store=store, mode=mode)
            return ArmResult(**base, acquired=False, verdict=verdict.verdict,
                             dev_pass=_dev_pass(cached, record, mode), reused=True,
                             seconds=time.time() - t0, strategy="reuse",
                             notes="reused a previously acquired program",
                             mode=verdict.mode, os_boundary=verdict.os_boundary)
        got = synth.acquire(record, budget_seconds=budget, mode=mode)
        code = got["code"]
        verdict = evaluate(record, code, store=store, mode=mode)
        dev_ok = _dev_pass(code, record, mode)
        if code and arm == "D":
            run_cache[record.family] = code
        if code and arm == "E":
            run_cache[record.family] = code
            library.setdefault("entries", {})[record.family] = code
            library.setdefault("tasks", {})[record.family] = {
                "key": record.key, "seed": record.seed}
            if verdict.passed:
                library.setdefault("verified", [])
                if record.family not in library["verified"]:
                    library["verified"].append(record.family)
        return ArmResult(**base, acquired=bool(code), verdict=verdict.verdict, dev_pass=dev_ok,
                         test_fitted=bool(dev_ok and not verdict.passed),
                         candidates=got["candidates_tested"], seconds=time.time() - t0,
                         strategy=got["strategy"], detections=verdict.detections,
                         mode=verdict.mode, os_boundary=verdict.os_boundary,
                         notes="" if code else "grammar exhausted")

    if arm in ("F1", "F2", "F3"):
        depth = 1 if arm == "F1" else 2
        exclude = {"binary"} if arm == "F2" else ({"rows"} if arm == "F3" else set())
        got = synth.acquire(record, depth=depth, budget_seconds=budget, mode=mode,
                            exclude=exclude)
        code = got["code"]
        verdict = evaluate(record, code, store=store, mode=mode) if code else Verdict("no_result")
        dev_ok = _dev_pass(code, record, mode) if code else False
        return ArmResult(**base, acquired=bool(code), verdict=verdict.verdict, dev_pass=dev_ok,
                         test_fitted=bool(dev_ok and not verdict.passed),
                         candidates=got["candidates_tested"], seconds=time.time() - t0,
                         strategy=f"ablation_{arm}", detections=verdict.detections,
                         mode=verdict.mode, os_boundary=verdict.os_boundary)

    raise ValueError(f"unknown arm {arm!r}")


# --------------------------------------------------------------------------- experiment
def run_experiment(*, seeds: list[int] | None = None, n_tasks: int = 24,
                   arms: tuple[str, ...] = ARMS, budget: float = 60.0,
                   mode: str | None = None, out_dir: Path | None = None,
                   library_path: Path | None = None,
                   warmup_seed: int | None = 5) -> dict[str, Any]:
    """Run the arms.

    ``warmup_seed`` builds the memory library arm B retrieves from, on a seed that is
    disjoint from the measured seeds. Without that split arm B was reading a library left
    behind by an earlier run — measured: it scored 35/66 on tasks the same generator had
    already solved, which is leakage, not memory.
    """
    seeds = seeds or [11]
    store = PrivateStore.open(create=True)
    pinned = store.repin()
    before = _live_brain_counts()

    out = Path(out_dir) if out_dir else RESEARCH_DIR
    out.mkdir(parents=True, exist_ok=True)
    # The library follows the output directory. Without this, a test or a run into a temp
    # directory still wrote the experiment library in the repository — measured: a small
    # test run replaced the real library with an empty one.
    if library_path is None and out_dir is not None:
        library_path = out / "library.json"

    memory_library: dict[str, Any] = {"entries": {}}
    warmup_info: dict[str, Any] = {"seed": warmup_seed, "entries": 0, "source": "none"}
    if warmup_seed is not None:
        warm_records = generate(warmup_seed, n_tasks)
        for record in warm_records:
            if record.kind != "regular":
                continue
            got = synth.acquire(record, budget_seconds=budget, mode=mode)
            if got["code"]:
                memory_library["entries"].setdefault(record.family, got["code"])
        warmup_info = {"seed": warmup_seed, "entries": len(memory_library["entries"]),
                       "source": "warmup seed (disjoint from measured seeds)"}

    # E consolidates into its own library, starting empty so its reuse is its own.
    library: dict[str, Any] = {"entries": {}}

    rows: list[ArmResult] = []
    generated: dict[str, Any] = {}
    for seed in seeds:
        records = generate(seed, n_tasks)
        generated[str(seed)] = [
            {"key": r.key, "family": r.family, "kind": r.kind, "hash": r.generation_hash,
             "difficulty": r.difficulty, "expected_verdict": r.expected_verdict}
            for r in records
        ]
        for arm in arms:
            run_cache: dict[str, str] = {}
            for record in records:
                if record.kind == "impossible" and arm not in ("A",):
                    # Nothing can be acquired without network; record it as expected-fail.
                    rows.append(ArmResult(arm=arm, key=record.key, seed=record.seed,
                                          family=record.family,
                                          kind=record.kind, acquired=False,
                                          verdict="expected_fail", notes="no network access"))
                    continue
                rows.append(run_arm(arm, record, store,
                                    library=memory_library if arm == "B" else library,
                                    run_cache=run_cache, mode=mode, budget=budget))

    after = _live_brain_counts()
    save_library(library, library_path)

    report = _summarise(rows, seeds=seeds, arms=arms, generated=generated,
                        store=store, pinned=pinned, before=before, after=after,
                        n_tasks=n_tasks, library_path=library_path,
                        warmup=warmup_info,
                        library_entries=sorted(library["entries"]))
    return report


def _summarise(rows: list[ArmResult], *, seeds: list[int], arms: tuple[str, ...],
               generated: dict[str, Any], store: PrivateStore, pinned: dict[str, Any],
               before: dict[str, int], after: dict[str, int], n_tasks: int,
               library_path: Path | None, warmup: dict[str, Any] | None = None,
               library_entries: list[str] | None = None) -> dict[str, Any]:
    by_arm: dict[str, Any] = {}
    for arm in arms:
        arm_rows = [r for r in rows if r.arm == arm]
        scored = [r for r in arm_rows if r.kind != "impossible"]
        passed = [r for r in scored if r.verdict == "pass"]
        by_arm[arm] = {
            "tasks": len(scored),
            "hidden_pass": len(passed),
            "hidden_pass_rate": round(len(passed) / max(1, len(scored)), 4),
            "dev_pass": sum(1 for r in scored if r.dev_pass),
            "test_fitted": sum(1 for r in scored if r.test_fitted),
            "reused": sum(1 for r in scored if r.reused),
            "mean_candidates": round(sum(r.candidates for r in scored) / max(1, len(scored)), 1),
            "mean_seconds": round(sum(r.seconds for r in scored) / max(1, len(scored)), 2),
            "verdicts": _count([r.verdict for r in scored]),
            "per_task": {r.key: r.verdict for r in scored},
        }

    per_seed = {}
    for seed in seeds:
        seed_rows = [r for r in rows if r.seed == seed and r.kind != "impossible"]
        per_seed[str(seed)] = {
            arm: {"pass": sum(1 for r in seed_rows if r.arm == arm and r.verdict == "pass"),
                  "tasks": sum(1 for r in seed_rows if r.arm == arm)}
            for arm in arms}

    rates = {arm: by_arm[arm]["hidden_pass_rate"] for arm in arms}
    return {
        "experiment_id": f"p3-{time.strftime('%Y%m%dT%H%M%SZ', time.gmtime())}",
        "generated_at": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()),
        "git_commit": _git_commit(),
        "generator_version": GENERATOR_VERSION,
        "evaluator": {"pinned": pinned},
        "hardware": _hardware(),
        "config": {"seeds": seeds, "n_tasks": n_tasks, "arms": list(arms),
                   "library": str(library_path or LIBRARY)},
        "memory_library": {"warmup": warmup or {}, "consolidated_families": library_entries or []},
        "production_memory": {"before": before, "after": after,
                              "unchanged": before == after},
        "tasks_generated": generated,
        "arms": by_arm,
        "rates": rates,
        "rate_ci": {arm: bootstrap_ci([1.0 if r.verdict == "pass" else 0.0
                                       for r in rows if r.arm == arm and r.kind != "impossible"])
                    for arm in arms},
        "per_seed": per_seed,
        "rows": [r.to_json() for r in rows],
    }


def _count(values: list[str]) -> dict[str, int]:
    out: dict[str, int] = {}
    for v in values:
        out[v] = out.get(v, 0) + 1
    return out


def render_markdown(report: dict[str, Any]) -> str:
    lines = [f"# Phase 3 acquisition experiment `{report['experiment_id']}`", "",
             f"- commit `{report['git_commit']}`",
             f"- generator `{report['generator_version']}`",
             f"- tasks per seed: {report['config']['n_tasks']}, seeds {report['config']['seeds']}",
             f"- hardware: {report['hardware']['cores']} cores, torch {report['hardware']['torch']}",
             f"- production memory unchanged: **{report['production_memory']['unchanged']}**", "",
             "## Hidden-test pass rate by arm", "",
             "| arm | tasks | hidden pass | rate | 95% CI | dev pass | test-fitted | mean candidates | mean s |",
             "|---|---|---|---|---|---|---|---|---|"]
    for arm, data in report["arms"].items():
        ci = report["rate_ci"][arm]
        est = "" if ci["established"] else " *(observed)*"
        lines.append(
            f"| {arm} | {data['tasks']} | {data['hidden_pass']} | "
            f"{data['hidden_pass_rate']:.3f}{est} | [{ci['lo']:.3f}, {ci['hi']:.3f}] | "
            f"{data['dev_pass']} | {data['test_fitted']} | {data['mean_candidates']} | "
            f"{data['mean_seconds']} |")
    lines += ["", "## Verdicts by arm", ""]
    for arm, data in report["arms"].items():
        lines.append(f"- **{arm}**: {data['verdicts']}")
    lines += ["", "## Notes", "",
              "Every arm is scored by the independent evaluator on hidden inputs generated from a",
              "private salt. `dev pass` counts tasks whose program satisfied the visible dev tests;",
              "`test-fitted` counts tasks that passed dev and failed hidden — the honest measure of",
              "how much of the apparent success is overfitting to the visible examples.", ""]
    return "\n".join(lines)
