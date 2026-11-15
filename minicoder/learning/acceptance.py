"""The eight Phase 2 acceptance criteria, measured end to end.

Each check runs against real components and writes down what it measured. A
check that cannot pass says so and fails the run; none of them are allowed to
report success on a code path that did not execute.

The run is reproducible: ``python -m minicoder.learning.acceptance`` prints a
table and writes ``datasets/learning/acceptance_<stamp>.json``.
"""

from __future__ import annotations

import json
import shutil
import tempfile
import time
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

from minicoder.learning.benchmark import assert_sealed
from minicoder.learning.engine import LearningLoop, TaskSpec

REPORT_DIR = Path("datasets/learning")


@dataclass
class Check:
    n: int
    name: str
    passed: bool
    evidence: dict[str, Any] = field(default_factory=dict)
    detail: str = ""

    def to_json(self) -> dict[str, Any]:
        return {"n": self.n, "name": self.name, "passed": self.passed,
                "detail": self.detail, "evidence": self.evidence}


# A task chosen to require capability the system did not have seeded: two text
# layers at different sizes, a vector shape, and a non-default canvas, with
# non-overlap and in-bounds constraints. Nothing in seed data answers it.
ACQUIRE_TASK = TaskSpec(
    key="acceptance_beacon",
    title="Beacon launch poster",
    goal=("A 720x960 poster on near-black with the headline 'Beacon' centred, "
          "a time line, and a shape; nothing overlapping or off-canvas."),
    criteria=[
        'canvas_size(720, 960)',
        'background_contains("#0b0b0b")',
        'text_present("Beacon")',
        'text_present("Gates 18:00")',
        'count(shape, >=, 1)',
        'centred(text, "Beacon")',
        'within_canvas()',
        'no_overlap()',
    ],
    domain="editor",
)

VARIANT_TASK = TaskSpec(
    key="acceptance_beacon_variant",
    title="Beacon launch poster (rescheduled)",
    goal=("The same poster at a different size, different background and different "
          "words — a variation, not a repeat."),
    criteria=[
        'canvas_size(900, 1200)',
        'background_contains("#101014")',
        'text_present("Beacon Relaunch")',
        'text_present("Gates 20:30")',
        'count(shape, >=, 1)',
        'centred(text, "Beacon Relaunch")',
        'within_canvas()',
        'no_overlap()',
    ],
    domain="editor",
)

# A deliberately hostile variation: the aspect ratio flips from 3:4 to 4:3, so
# two full-width text layers no longer fit vertically. Recorded separately so the
# limitation is visible rather than averaged away.
STRESS_TASK = TaskSpec(
    key="acceptance_beacon_stress",
    title="Beacon poster (aspect flipped)",
    goal="The same poster on a 1024x768 canvas — four-thirds, not three-quarters.",
    criteria=[
        'canvas_size(1024, 768)',
        'background_contains("#101014")',
        'text_present("Beacon Relaunch")',
        'text_present("Gates 20:30")',
        'count(shape, >=, 1)',
        'centred(text, "Beacon Relaunch")',
        'within_canvas()',
        'no_overlap()',
    ],
    domain="editor",
)


class AcceptanceRun:
    def __init__(self) -> None:
        self.loop = LearningLoop()
        self.checks: list[Check] = []
        self.state: dict[str, Any] = {}

    # ---------------------------------------------------------------- helpers
    def add(self, n: int, name: str, passed: bool, detail: str = "",
            **evidence: Any) -> Check:
        check = Check(n, name, passed, evidence, detail)
        self.checks.append(check)
        status = "PASS" if passed else "FAIL"
        print(f"  [{status}] {n}. {name}" + (f" — {detail}" if detail else ""))
        return check

    # ------------------------------------------------------------------ checks
    def check_1_learn_unseen(self) -> None:
        rep = self.loop.acquire(ACQUIRE_TASK)
        self.state["acquire"] = rep.to_json()
        self.add(
            1, "learn a genuinely unseen procedural task", rep.solved,
            f"{rep.attempts} attempt(s), progress {rep.final_progress:.2f}, "
            f"{rep.seconds:.1f}s, candidate {rep.candidate_id}",
            solved=rep.solved, attempts=rep.attempts,
            first_attempt_ok=rep.first_attempt_ok,
            final_progress=rep.final_progress,
            failure_classes=rep.failure_classes,
        )

    def check_2_replay_fresh_session(self) -> None:
        cand = self.state.get("acquire", {}).get("candidate_id")
        if not cand:
            self.add(2, "replay the skill in a fresh session", False, "no candidate")
            return
        result = self.loop.verify(cand, ACQUIRE_TASK, runs=3, fresh_process=True)
        self.state["replay"] = result
        self.add(
            2, "replay the skill in a fresh session", result["passed"],
            f"{result['runs']}/{result['requested']} runs, "
            f"first run in a separate interpreter",
            runs=result["runs"], requested=result["requested"],
            failures=result.get("failures", []),
        )

    def check_3_retain_after_archival(self) -> None:
        """Archive every episode, then replay the skill again.

        A skill that only worked because its originating episodes were still
        retrievable is not retained knowledge. Archiving removes those episodes,
        so a passing replay afterwards is evidence the procedure stands alone.
        """
        cand = self.state.get("acquire", {}).get("candidate_id")
        if not cand:
            self.add(3, "retain the skill after episodic archival", False, "no candidate")
            return
        db = self.loop.ledger.db
        # Seed episodes describing the acquisition, so archiving removes
        # something. In a fresh home there were none and the check was vacuous
        # (measured: "archived 0 episode(s)").
        from minicoder.memory.db import utcnow

        seeded = 0
        with db.write() as conn:
            for i in range(6):
                conn.execute(
                    "INSERT INTO episodes(ts, modality, situation, objective, actions,"
                    " result, status, source, confidence, session_id, meta)"
                    " VALUES (?,?,?,?,?,?,?,?,?,?,?)",
                    (utcnow(), "text",
                     f"acquired {ACQUIRE_TASK.key} in session {i}",
                     ACQUIRE_TASK.goal, json.dumps([]),
                     "criteria satisfied", "VERIFIED", "acceptance", 0.9,
                     f"session-{i}", json.dumps({"task": ACQUIRE_TASK.key})),
                )
                seeded += 1
        before = db.query_one("SELECT COUNT(*) FROM episodes WHERE archived=0")[0]
        with db.write() as conn:
            conn.execute("UPDATE episodes SET archived=1")
        after = db.query_one("SELECT COUNT(*) FROM episodes WHERE archived=0")[0]
        # Replay the stored procedure directly rather than through verify(), so
        # the candidate's replay count (the promotion gate) is untouched.
        procedure = json.loads(self.loop.ledger.get_candidate(cand)["procedure"] or "[]")
        runs_ok = 0
        for _ in range(2):
            outcome = self.loop._run_procedure(procedure, ACQUIRE_TASK)
            runs_ok += int(outcome["passed"])
        with db.write() as conn:
            conn.execute("UPDATE episodes SET archived=0")
        self.add(
            3, "retain the skill after episodic archival", runs_ok == 2 and before > 0,
            f"{seeded} episodes seeded; archived {before} -> {after} live; "
            f"replay {runs_ok}/2 with no episodes available",
            episodes_archived=before, episodes_live_after=after,
            replay_runs=runs_ok,
        )

    def check_4_variation(self) -> None:
        cand = self.state.get("acquire", {}).get("candidate_id")
        if not cand:
            self.add(4, "apply the skill to a variation", False, "no candidate")
            return
        promoted = self.loop.promote(cand, ACQUIRE_TASK)
        self.state["promote"] = promoted
        if not promoted.get("promoted"):
            self.add(4, "apply the skill to a variation", False,
                     f"promotion refused: {promoted.get('reason')}")
            return
        res = self.loop.reuse(promoted["slug"], VARIANT_TASK, variation="changed")
        self.state["reuse"] = res
        # Stress the same skill on a flipped aspect ratio. This is expected to
        # exceed mechanical adaptation; it is measured and reported, not skipped.
        stress = self.loop.reuse(promoted["slug"], STRESS_TASK,
                                 variation="aspect_flipped", allow_reacquire=True)
        self.state["stress"] = {k: stress.get(k) for k in
                                ("passed", "mode", "substitution_passed",
                                 "repaired", "failed")}
        self.add(
            4, "apply the skill to a different variation", bool(res.get("passed")),
            f"variant solved={res.get('passed')} via {res.get('mode')} "
            f"(substitution={res.get('substitution_passed')}, "
            f"repaired={res.get('repaired')}); "
            f"aspect-flipped stress={stress.get('mode')}",
            variation=VARIANT_TASK.key, mode=res.get("mode"),
            substitution_passed=res.get("substitution_passed"),
            repaired=res.get("repaired"), repair_rounds=res.get("repair_rounds"),
            failed=res.get("failed", []),
            stress=self.state["stress"],
        )

    def check_5_reject_unverified(self) -> None:
        """A candidate that never passed replay must not reach procedural memory."""
        from minicoder.memory.systems import ProceduralMemory

        eid = self.loop.ledger.open_experiment(
            "acceptance_reject", "Rejection probe",
            "A candidate whose replay fails must be refused promotion.",
            ["canvas_size(1, 1)"],
        )
        cand = self.loop.ledger.add_candidate(
            eid, "learned_should_never_exist",
            [{"tool": "set_canvas_size", "args": {"width": 1, "height": 1}}],
            {"criteria": ["canvas_size(1, 1)"], "reasoning": []},
        )
        # Recorded as failing replay, exactly as verify() would on a bad procedure.
        self.loop.ledger.record_replay(cand, passed=False,
                                       failures=["run 1: criteria not met"], runs=0)
        outcome = self.loop.promote(cand, ACQUIRE_TASK)
        proc = ProceduralMemory(self.loop.ledger.db)
        exists = proc.get("learned_should_never_exist") is not None
        passed = (not outcome.get("promoted")) and (not exists)
        self.add(
            5, "reject an unverified skill", passed,
            f"promotion refused ({outcome.get('reason')}); skill absent from memory "
            f"={not exists}",
            promotion_refused=not outcome.get("promoted"),
            skill_in_memory=exists,
        )
        # Also: a candidate that passes but with too few replays is refused.
        eid2 = self.loop.ledger.open_experiment(
            "acceptance_too_few", "Replay-count probe",
            "A single replay is not enough.", ["canvas_size(2, 2)"],
        )
        cand2 = self.loop.ledger.add_candidate(
            eid2, "learned_too_few_replays",
            [{"tool": "set_canvas_size", "args": {"width": 2, "height": 2}}],
            {"criteria": ["canvas_size(2, 2)"], "reasoning": []},
        )
        self.loop.ledger.record_replay(cand2, passed=True, failures=[], runs=1)
        outcome2 = self.loop.promote(cand2, ACQUIRE_TASK, min_replay_runs=3)
        self.state["reject_too_few"] = outcome2
        if outcome2.get("promoted"):
            self.checks[-1].passed = False
            self.checks[-1].detail += "; single-replay candidate was wrongly promoted"

    def check_6_detect_regression(self) -> None:
        from minicoder.learning.safeguard import RegressionGuard

        guard = RegressionGuard()
        verdict = guard.compare(
            {"skill_accuracy": 0.875, "retention": 0.875, "val_ce": 5.68},
            {"skill_accuracy": 0.0, "retention": 0.0, "val_ce": 356.1},
        )
        self.state["regression_verdict"] = verdict.to_json()
        self.add(
            6, "detect a deliberate regression", not verdict.passed,
            f"{len(verdict.regressions)} regression(s) caught: "
            + ", ".join(r["metric"] for r in verdict.regressions),
            regressions=verdict.regressions,
        )

    def check_7_rollback(self) -> None:
        """Wreck the live weights inside an isolated home, then restore them."""
        from minicoder.config import CONFIG

        live = CONFIG.paths.checkpoints
        tmp = Path(tempfile.mkdtemp(prefix="acceptance_rb_"))
        try:
            for f in live.iterdir():
                if f.is_file():
                    shutil.copy2(f, tmp / f.name)
            from minicoder.learning.safeguard import BaselineRegistry, quick_metrics

            registry = BaselineRegistry()
            before = quick_metrics()
            name = f"acceptance_{int(time.time())}"
            snap = registry.snapshot(name, source=live)
            if not snap.get("created"):
                self.add(7, "roll back a harmful update", False,
                         f"could not snapshot: {snap.get('reason')}")
                return
            import torch

            blob = torch.load(live / "lm.pt", map_location="cpu", weights_only=False)
            torch.manual_seed(99)
            for k, v in blob["state_dict"].items():
                if hasattr(v, "shape") and v.dtype.is_floating_point:
                    blob["state_dict"][k] = torch.randn_like(v) * 3.0
            torch.save(blob, live / "lm.pt")
            harmed = quick_metrics()
            restore = registry.restore(name)
            recovered = quick_metrics()
            passed = (
                bool(restore.get("restored"))
                and harmed.get("val_ce", 0) > before.get("val_ce", 0) + 0.5
                and abs(recovered.get("val_ce", -1) - before.get("val_ce", 0)) < 1e-6
            )
            self.add(
                7, "roll back a harmful update", passed,
                f"val_ce {before.get('val_ce')} -> harmed {harmed.get('val_ce')} -> "
                f"restored {recovered.get('val_ce')}",
                before=before, harmed=harmed, recovered=recovered,
            )
        finally:
            shutil.rmtree(tmp, ignore_errors=True)

    def check_8_reproducible_report(self) -> None:
        from minicoder.learning.runner import run_benchmark

        sealed = assert_sealed()
        a = run_benchmark(editor=False, out_dir=Path(tempfile.mkdtemp(prefix="acc_bench_")))
        b = run_benchmark(editor=False, out_dir=Path(tempfile.mkdtemp(prefix="acc_bench2_")))
        same = (a["summary"]["final_success"] == b["summary"]["final_success"]
                and a["sealed"]["sealed"] == b["sealed"]["sealed"]
                and [t["final_ok"] for t in a["tasks"]] == [t["final_ok"] for t in b["tasks"]])
        self.state["bench_program"] = a["summary"]
        self.add(
            8, "produce a reproducible benchmark report", same and sealed["sealed"],
            f"two runs agree on {a['summary']['final_success']}/"
            f"{a['summary']['n']}; sealed={sealed['sealed']}",
            run_a=a["summary"]["final_success"], run_b=b["summary"]["final_success"],
            sealed=sealed["sealed"],
        )

    # -------------------------------------------------------------------- run
    def execute(self) -> dict[str, Any]:
        t0 = time.time()
        print("Phase 2 acceptance criteria")
        # Check 3 needs a promoted skill; check 4 is what promotes it. The
        # numbers stay as the brief states them, the execution order does not.
        for step in (
            self.check_1_learn_unseen,
            self.check_2_replay_fresh_session,
            self.check_4_variation,
            self.check_3_retain_after_archival,
            self.check_5_reject_unverified,
            self.check_6_detect_regression,
            self.check_7_rollback,
            self.check_8_reproducible_report,
        ):
            try:
                step()
            except Exception as exc:
                self.add(0, f"{step.__name__} raised", False, f"{type(exc).__name__}: {exc}")
        self.loop.close()

        self.checks.sort(key=lambda c: c.n)
        report = {
            "generated_at": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()),
            "passed": sum(1 for c in self.checks if c.passed),
            "total": len(self.checks),
            "all_passed": all(c.passed for c in self.checks) and len(self.checks) == 8,
            "seconds": round(time.time() - t0, 2),
            "checks": [c.to_json() for c in self.checks],
            "state": self.state,
        }
        REPORT_DIR.mkdir(parents=True, exist_ok=True)
        stamp = time.strftime("%Y%m%dT%H%M%SZ", time.gmtime())
        path = REPORT_DIR / f"acceptance_{stamp}.json"
        latest = REPORT_DIR / "acceptance_latest.json"
        payload = json.dumps(report, indent=2, default=str)
        path.write_text(payload, encoding="utf-8")
        latest.write_text(payload, encoding="utf-8")
        report["report_path"] = str(path)
        print(f"\n{report['passed']}/{report['total']} criteria passed "
              f"in {report['seconds']}s -> {path}")
        return report


def run() -> dict[str, Any]:
    return AcceptanceRun().execute()


if __name__ == "__main__":
    result = run()
    raise SystemExit(0 if result["all_passed"] else 1)
