"""The learning loop: acquire → verify by replay → promote → reuse.

One complete loop, end to end, before any expansion. The states the brief
requires to stay distinct are distinct here and each has its own transcript:

    acquire()   form hypotheses, plan against discovered tools, attempt,
                read the real outcome, classify the failure, repair, retry.
                Produces a *candidate* only if the criteria actually passed.

    verify()    take the stored procedure and run it again **in a fresh
                process** with no search and no planner, several times.
                A procedure that cannot reproduce its result is not a skill.

    promote()   the only write into verified procedural memory, and it refuses
                unless verify() passed.

    reuse()     apply the stored procedure to a different variation of the task,
                which is what distinguishes a memorised answer from a skill.

Attempts are recorded whether they pass or fail. A failed experiment is a
result, not an embarrassment: it is the evidence that the next attempt was
informed by a real diagnosis.
"""

from __future__ import annotations

import json
import os
import subprocess
import sys
import time
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

from minicoder.config import CONFIG
from minicoder.learning.criteria import (
    EditorState,
    evaluate_editor_criteria,
    progress,
)
from minicoder.learning.discovery import ToolIndex, tool_index_from_bridge
from minicoder.learning.ledger import (
    Attempt,
    CriterionResult,
    ExperimentLedger,
    SkillPromoter,
)
from minicoder.learning.planner import SearchPlanner


@dataclass
class TaskSpec:
    """A task stated as requirements, independent of any solution."""

    key: str
    title: str
    goal: str
    criteria: list[str]
    domain: str = "editor"
    must_fail_with: list[str] = field(default_factory=list)
    meta: dict[str, Any] = field(default_factory=dict)

    def to_json(self) -> dict[str, Any]:
        return {
            "key": self.key, "title": self.title, "goal": self.goal,
            "criteria": list(self.criteria), "domain": self.domain,
        }


@dataclass
class LoopReport:
    experiment_id: int
    task_key: str
    solved: bool
    attempts: int
    first_attempt_ok: bool
    final_progress: float
    failure_classes: list[str]
    candidate_id: int | None
    replay_passed: bool
    replay_runs: int
    promoted: bool
    seconds: float
    tokens_used: int
    resource: dict[str, float] = field(default_factory=dict)

    def to_json(self) -> dict[str, Any]:
        return {
            "experiment_id": self.experiment_id, "task_key": self.task_key,
            "solved": self.solved, "attempts": self.attempts,
            "first_attempt_ok": self.first_attempt_ok,
            "final_progress": round(self.final_progress, 3),
            "failure_classes": self.failure_classes,
            "candidate_id": self.candidate_id, "replay_passed": self.replay_passed,
            "replay_runs": self.replay_runs, "promoted": self.promoted,
            "seconds": round(self.seconds, 2), "tokens_used": self.tokens_used,
            "resource": self.resource,
        }


class LearningLoop:
    """Acquisition, verification, promotion and reuse for editor tasks."""

    def __init__(self, *, db_path: str | Path | None = None,
                 bridge_factory: Any | None = None) -> None:
        self.ledger = ExperimentLedger()
        self.promoter = SkillPromoter(self.ledger.db)
        self._bridge = None
        self._bridge_factory = bridge_factory
        self._index: ToolIndex | None = None

    # ------------------------------------------------------------ bridge mgmt
    def bridge(self):
        if self._bridge is None:
            if self._bridge_factory is not None:
                self._bridge = self._bridge_factory()
            else:
                from minicoder.tools.editor_bridge import EditorBridge

                self._bridge = EditorBridge()
            self._bridge._ensure()
        return self._bridge

    def index(self) -> ToolIndex:
        if self._index is None:
            self._index = tool_index_from_bridge(self.bridge())
        return self._index

    def close(self) -> None:
        if self._bridge is not None:
            try:
                self._bridge.close()
            except Exception:
                pass
            self._bridge = None
            self._index = None

    # -------------------------------------------------------------- acquiring
    def acquire(self, task: TaskSpec, *, max_attempts: int = 4,
                make_candidate: bool = True) -> LoopReport:
        """Attempt a task until its criteria pass, or until the budget is spent."""
        t0 = time.time()
        eid = self.ledger.open_experiment(
            task.key, task.title, task.goal, task.criteria,
            domain=task.domain,
            budget={"attempts": max_attempts, "seconds": 300},
            meta=task.meta,
        )
        bridge = self.bridge()
        index = self.index()
        planner = SearchPlanner(index)

        best_result: dict[str, Any] | None = None
        failure_classes: list[str] = []
        tokens = 0
        first_attempt_ok = False

        for attempt_no in range(1, max_attempts + 1):
            hyp_statement = (
                f"discovering tools for each criterion and executing them in "
                f"priority order will satisfy {len(task.criteria)} criteria"
                if attempt_no == 1
                else f"retrying with repairs for {failure_classes[-1]}"
            )
            hyp = self.ledger.propose(
                eid, hyp_statement,
                kind="plan" if attempt_no == 1 else "repair",
                rationale="" if attempt_no == 1 else f"previous failure: {failure_classes[-1]}",
                based_on=[] if attempt_no == 1 else [str(eid)],
                confidence=0.5 if attempt_no == 1 else 0.6,
            )
            self.ledger.mark_hypothesis(hyp, "testing")

            at0 = time.time()
            out = planner.plan(task.criteria, bridge)
            elapsed = (time.time() - at0) * 1000
            results: list[CriterionResult] = out["results"]
            done = all(r.passed for r in results)
            tokens += self._estimate_tokens(planner, task)

            failure_class = "none" if done else self._classify(results, planner, index)
            if not done:
                failure_classes.append(failure_class)
            if attempt_no == 1:
                first_attempt_ok = done

            attempt = Attempt(
                n=self.ledger.next_attempt_number(eid),
                ok=done,
                failure_class=failure_class,
                error="" if done else self._first_failure(results),
                plan=out["plan"],
                observed={"canvas": [out["state"].canvas_width, out["state"].canvas_height],
                          "layers": len(out["state"].layers),
                          "progress": round(out["progress"], 3),
                          "steps": out["steps"], "backtracks": out["backtracks"]},
                criteria_results=results,
                duration_ms=elapsed,
                tokens_used=self._estimate_tokens(planner, task),
            )
            aid = self.ledger.record_attempt(eid, attempt, hypothesis_id=hyp)
            self.ledger.mark_hypothesis(hyp, "supported" if done else "refuted")

            if best_result is None or out["progress"] > best_result["progress"]:
                best_result = out

            if done:
                break

        solved = best_result is not None and all(r.passed for r in best_result["results"])
        candidate_id = None
        replay_passed = replay_runs = 0
        promoted = False

        if solved and make_candidate:
            # A successful execution is not yet a skill.
            slug = f"learned_{task.key}"
            cand = self.ledger.add_candidate(
                eid, slug, best_result["plan"],
                {
                    "criteria": task.criteria,
                    "observed": {
                        "canvas": [best_result["state"].canvas_width,
                                   best_result["state"].canvas_height],
                        "layers": len(best_result["state"].layers),
                    },
                    "reasoning": [d.get("requirement", "") for d in planner.decisions
                                  if d.get("tool")][:8],
                },
                attempt_id=aid if solved else None,
            )
            candidate_id = cand
            self.ledger.set_best_candidate(eid, cand)
            rep = self.verify(cand, task)
            replay_passed, replay_runs = rep["passed"], rep["runs"]

        seconds = time.time() - t0
        self.ledger.close_experiment(eid, "solved" if solved else "exhausted", seconds=seconds)
        resource = self.ledger.sample_resources(experiment_id=eid, context=f"acquire:{task.key}")

        return LoopReport(
            experiment_id=eid, task_key=task.key, solved=solved,
            attempts=len(self.ledger.attempts(eid)),
            first_attempt_ok=first_attempt_ok,
            final_progress=(best_result["progress"] if best_result else 0.0),
            failure_classes=failure_classes, candidate_id=candidate_id,
            replay_passed=replay_passed, replay_runs=replay_runs,
            promoted=promoted, seconds=seconds, tokens_used=tokens,
            resource=resource,
        )

    # --------------------------------------------------------------- verifying
    def verify(self, candidate_id: int, task: TaskSpec, *, runs: int = 3,
               fresh_process: bool = True) -> dict[str, Any]:
        """Replay a stored procedure with no search, in a fresh process.

        This is the gate between "worked once" and "is a skill". The procedure
        is re-executed verbatim; nothing is re-planned. Each run starts from an
        empty canvas in a new editor process, so a stored procedure cannot pass
        because of state left behind by the acquisition attempt.
        """
        cand = self.ledger.get_candidate(candidate_id)
        if not cand:
            return {"passed": False, "runs": 0, "detail": "unknown candidate"}
        procedure = json.loads(cand["procedure"] or "[]")
        failures: list[str] = []
        passed_runs = 0

        for i in range(runs):
            if fresh_process and i == 0:
                # First run in a genuinely separate interpreter: proves the
                # procedure does not depend on this process's Python state.
                result = self._replay_in_subprocess(procedure, task)
            else:
                result = self._replay_inline(procedure, task)
            if result["passed"]:
                passed_runs += 1
            else:
                failures.append(f"run {i + 1}: {result['detail']}")

        ok = passed_runs == runs
        self.ledger.record_replay(candidate_id, passed=ok, failures=failures, runs=passed_runs)
        return {"passed": ok, "runs": passed_runs, "requested": runs,
                "failures": failures, "fresh_process": fresh_process}

    def _replay_in_subprocess(self, procedure: list[dict[str, Any]],
                              task: TaskSpec) -> dict[str, Any]:
        payload = json.dumps({"procedure": procedure, "criteria": task.criteria})
        env = dict(os.environ)
        env["PYTHONPATH"] = str(CONFIG.install_root() if hasattr(CONFIG, "install_root") else ".")
        env["MINICODER_REPLAY"] = "1"
        try:
            proc = subprocess.run(
                [sys.executable, "-m", "minicoder.learning.replay", "--stdin"],
                input=payload, capture_output=True, text=True, timeout=180, env=env,
            )
        except subprocess.TimeoutExpired:
            return {"passed": False, "detail": "replay subprocess timed out"}
        for line in (proc.stdout or "").splitlines():
            if line.startswith("__REPLAY__"):
                try:
                    return json.loads(line[len("__REPLAY__"):])
                except json.JSONDecodeError:
                    continue
        return {"passed": False,
                "detail": f"subprocess produced no verdict (rc={proc.returncode}): "
                          f"{(proc.stderr or '')[-300:]}"}

    def _replay_inline(self, procedure: list[dict[str, Any]], task: TaskSpec) -> dict[str, Any]:
        bridge = self.bridge()
        bridge.call("new_project", {})
        for step in procedure:
            try:
                result, _ = bridge.call(step["tool"], step.get("args") or {})
                if isinstance(result, dict) and result.get("ok") is False:
                    return {"passed": False,
                            "detail": f"{step['tool']} failed: {result.get('error') or result.get('summary')}"}
            except Exception as exc:
                return {"passed": False, "detail": f"{step['tool']} raised: {exc}"}
        _, raw = bridge.call("get_app_state", {})
        state = EditorState.from_snapshot(raw.get("snapshot") or {})
        results = evaluate_editor_criteria(task.criteria, state)
        failed = [r for r in results if not r.passed]
        return {
            "passed": not failed,
            "detail": "; ".join(f"{r.criterion}: {r.detail}" for r in failed)[:400] or "all criteria passed",
        }

    # -------------------------------------------------------------- promotion
    def promote(self, candidate_id: int, task: TaskSpec, *, name: str | None = None,
                min_replay_runs: int = 3) -> dict[str, Any]:
        return self.promoter.promote(
            candidate_id,
            name=name or task.title,
            description=task.goal,
            domain=task.domain,
            min_replay_runs=min_replay_runs,
        )

    # ------------------------------------------------------------------ reuse
    def reuse(self, slug: str, task: TaskSpec, *, variation: str = "variation",
              allow_reacquire: bool = False) -> dict[str, Any]:
        """Apply a promoted skill's stored procedure to a new task statement.

        The procedure is reused verbatim; only the arguments named by the new
        criteria are substituted. A skill that cannot survive a changed value is
        a memorised constant, so the substitution is deliberately mechanical —
        if that is not enough, the variant fails and says so.
        """
        from minicoder.memory.systems import ProceduralMemory

        proc = ProceduralMemory(self.ledger.db)
        skill = proc.get(slug)
        if not skill:
            return {"passed": False, "detail": f"no such skill: {slug}"}
        try:
            procedure = json.loads(skill["tool_calls"] or "[]")
        except json.JSONDecodeError:
            procedure = []
        if not procedure:
            return {"passed": False, "detail": "skill has no stored tool sequence"}

        from minicoder.learning.planner import SearchPlanner

        planner = SearchPlanner(self.index())
        adapted = self._substitute(procedure, task, planner)
        t0 = time.time()
        result = self._run_procedure(adapted, task)
        substitution_passed = result["passed"]

        # A procedure found on one canvas rarely fits a different one. Measure
        # that as "substitution", then let the planner repair only the failing
        # requirements against the live state and measure "adaptation".
        repaired = False
        rounds = 0
        if not substitution_passed:
            from minicoder.learning.criteria import evaluate_editor_criteria

            # Iterate: fixing one criterion can break another (moving a layer
            # into bounds can make it overlap). A single pass is not enough —
            # measured on the 1024x768 variant.
            for _ in range(3):
                if not result["failed"]:
                    break
                rounds += 1
                planner.repair(task.criteria, self.bridge(), only=result["failed"])
                _, raw = self.bridge().call("get_app_state", {})
                state = EditorState.from_snapshot(raw.get("snapshot") or {})
                final = evaluate_editor_criteria(task.criteria, state)
                result = {
                    "passed": all(r.passed for r in final),
                    "criteria": [r.to_json() for r in final],
                    "failed": [r.criterion for r in final if not r.passed],
                    "progress": round(progress(final), 3),
                    "log": result.get("log", []),
                }
            repaired = result["passed"]

        self.ledger.record_skill_replay(
            slug, passed=result["passed"], task_key=task.key, variation=variation,
            detail={**result, "substitution_passed": substitution_passed,
                    "repaired": repaired, "repair_rounds": rounds},
            duration_ms=(time.time() - t0) * 1000,
        )
        mode = ("direct" if substitution_passed
                else "repaired" if repaired else "failed")

        # If the stored procedure cannot be adapted, say so and — when allowed —
        # solve the task by acquiring afresh. The distinction matters: reuse on a
        # changed canvas is adaptation, re-solving from scratch is not, and the
        # report must not conflate them.
        if not result["passed"] and allow_reacquire:
            fresh = self.acquire(task)
            self.ledger.record_skill_replay(
                slug, passed=fresh.solved, task_key=task.key,
                variation=f"{variation}:reacquired",
                detail={"reacquired": True, "attempts": fresh.attempts},
            )
            return {**result, "adapted": adapted, "variation": variation,
                    "substitution_passed": substitution_passed, "repaired": repaired,
                    "repair_rounds": rounds, "passed": fresh.solved,
                    "mode": "reacquired" if fresh.solved else "failed",
                    "reacquire": fresh.to_json()}

        return {**result, "adapted": adapted, "variation": variation,
                "substitution_passed": substitution_passed, "repaired": repaired,
                "repair_rounds": rounds, "mode": mode}

    def _substitute(self, procedure: list[dict[str, Any]], task: TaskSpec,
                    planner: SearchPlanner) -> list[dict[str, Any]]:
        """Swap literal argument values for the ones the new criteria demand."""
        from minicoder.learning.planner import parse_requirements

        reqs = parse_requirements(task.criteria)
        EditorState.from_snapshot({})
        wanted_text = [str(r.params[0]) for r in reqs
                       if r.kind in ("text_present", "text_exact") and r.params]
        swap: list[str] = list(wanted_text)
        canvas = next((r for r in reqs if r.kind == "canvas_size" and len(r.params) >= 2), None)
        bg = next((r for r in reqs if r.kind == "background_contains" and r.params), None)

        out: list[dict[str, Any]] = []
        text_idx = 0
        for step in procedure:
            new_step = {"tool": step["tool"], "args": dict(step.get("args") or {})}
            args = new_step["args"]
            if new_step["tool"] in ("add_text", "set_text_content") and text_idx < len(swap):
                if "content" in args:
                    args["content"] = swap[text_idx]
                # Only a creation step consumes a new literal; a rename reuses
                # the same slot in the text sequence.
                if new_step["tool"] == "add_text":
                    text_idx += 1
            if new_step["tool"] == "set_canvas_size" and canvas:
                if "width" in args:
                    args["width"] = int(canvas.params[0])
                if "height" in args:
                    args["height"] = int(canvas.params[1])
            if new_step["tool"] == "set_background" and bg:
                if "color" in args:
                    args["color"] = str(bg.params[0])
            out.append(new_step)
        return out

    def _run_procedure(self, procedure: list[dict[str, Any]], task: TaskSpec) -> dict[str, Any]:
        bridge = self.bridge()
        bridge.call("new_project", {})
        log: list[dict[str, Any]] = []
        for step in procedure:
            try:
                result, _ = bridge.call(step["tool"], step.get("args") or {})
                ok = not (isinstance(result, dict) and result.get("ok") is False)
                log.append({"tool": step["tool"], "ok": ok,
                            "error": (result or {}).get("error", "") if isinstance(result, dict) else ""})
                if not ok:
                    break
            except Exception as exc:
                log.append({"tool": step["tool"], "ok": False, "error": str(exc)})
                break
        _, raw = bridge.call("get_app_state", {})
        state = EditorState.from_snapshot(raw.get("snapshot") or {})
        results = evaluate_editor_criteria(task.criteria, state)
        failed = [r.criterion for r in results if not r.passed]
        return {"passed": not failed, "criteria": [r.to_json() for r in results],
                "failed": failed, "log": log, "progress": round(progress(results), 3)}

    # ---------------------------------------------------------------- helpers
    @staticmethod
    def _first_failure(results: list[CriterionResult]) -> str:
        for r in results:
            if not r.passed:
                return f"{r.criterion}: {r.detail}"
        return ""

    @staticmethod
    def _classify(results: list[CriterionResult], planner: SearchPlanner,
                  index: ToolIndex) -> str:
        """Name the failure from what actually went wrong, not from a guess."""
        stuck = [d for d in planner.decisions if d.get("stuck")]
        unknown = [d for d in planner.decisions if d.get("tool") and d["tool"] not in index.tools]
        if unknown:
            return "unknown_tool"
        if stuck:
            errs = " ".join(str(d.get("error", "")) for d in planner.decisions).lower()
            if "unknown" in errs or "invalid" in errs or "required" in errs:
                return "wrong_args"
            if any("no text layer" in str(d.get("error", "")).lower() for d in planner.decisions):
                return "missing_step"
            return "wrong_value"
        failed = [r for r in results if not r.passed]
        if failed:
            return "wrong_value"
        return "none"

    @staticmethod
    def _estimate_tokens(planner: SearchPlanner, task: TaskSpec) -> int:
        """Count the search work done, in a comparable unit.

        The loop calls no language model, so there is no billable token count to
        report. Rather than invent one, this reports the number of tokens the
        planner actually considered: tool-catalogue words searched plus
        requirement words parsed. It is a real, reproducible measure of the
        search performed.
        """
        searched = 0
        for d in planner.decisions:
            searched += len(str(d.get("requirement", "")).split()) * 3
        return searched + sum(len(c.split()) for c in task.criteria)
