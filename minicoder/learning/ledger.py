"""Experiment ledger: the four states, kept apart.

The brief is explicit that a hypothesis, an attempted solution, a successful
execution and a verified reusable skill must never be confused. Each is a
distinct row type here, and every transition is recorded with its evidence:

    experiments      a question + machine-checkable success criteria
      hypotheses     a stated guess about how to answer it
      attempts       one execution of that guess, with its real observed result
    skill_candidates a procedure that satisfied the criteria at least once
    skills           (existing table) only after independent replay passed

Nothing promotes itself. ``SkillPromoter`` is the only path from a candidate to
verified procedural memory, and it refuses unless replay passed.
"""

from __future__ import annotations

import json
from dataclasses import dataclass, field
from typing import Any

from minicoder.memory.db import BrainDB, utcnow

# Failure taxonomy. Distinguishing these is what makes repair possible: a wrong
# tool name needs a different fix from a right tool with wrong arguments, which
# needs a different fix from a correct call that produced the wrong value.
FAILURE_CLASSES = (
    "none",            # no failure
    "unknown_tool",    # the tool does not exist in the catalogue
    "wrong_args",      # tool exists, arguments were rejected
    "wrong_value",     # tool ran, but the result is not what the criterion wants
    "missing_step",    # the plan never performed the action the criterion needs
    "assertion",       # program ran and an assertion failed
    "crash",           # program raised
    "timeout",         # exceeded the budget
    "budget_exhausted",
)

EXPERIMENT_STATES = ("open", "solved", "exhausted", "abandoned")
HYPOTHESIS_STATES = ("proposed", "testing", "supported", "refuted", "inconclusive")
CANDIDATE_STATES = ("candidate", "replay_passed", "replay_failed", "promoted", "rejected")


@dataclass
class CriterionResult:
    """One machine-checkable requirement and whether the world satisfied it."""

    criterion: str
    passed: bool
    detail: str = ""

    def to_json(self) -> dict[str, Any]:
        return {"criterion": self.criterion, "passed": self.passed, "detail": self.detail}


@dataclass
class Attempt:
    """One execution and what actually happened."""

    n: int
    ok: bool
    failure_class: str = "none"
    error: str = ""
    plan: list[dict[str, Any]] = field(default_factory=list)
    code: str = ""
    observed: dict[str, Any] = field(default_factory=dict)
    criteria_results: list[CriterionResult] = field(default_factory=list)
    duration_ms: float = 0.0
    tokens_used: int = 0
    kind: str = "tool_sequence"
    id: int | None = None

    def to_json(self) -> dict[str, Any]:
        return {
            "n": self.n,
            "ok": self.ok,
            "failure_class": self.failure_class,
            "error": self.error,
            "plan": self.plan,
            "code": self.code,
            "observed": self.observed,
            "criteria_results": [c.to_json() for c in self.criteria_results],
            "duration_ms": round(self.duration_ms, 1),
            "tokens_used": self.tokens_used,
            "kind": self.kind,
            "id": self.id,
        }


class ExperimentLedger:
    """Append-only record of what was tried, what happened, and what was concluded."""

    def __init__(self, db: BrainDB | None = None) -> None:
        self.db = db or BrainDB()

    # ------------------------------------------------------------ experiments
    def open_experiment(
        self,
        task_key: str,
        title: str,
        goal: str,
        success_criteria: list[str],
        *,
        domain: str = "general",
        budget: dict[str, Any] | None = None,
        meta: dict[str, Any] | None = None,
    ) -> int:
        if not success_criteria:
            raise ValueError("an experiment needs at least one machine-checkable criterion")
        out: list[int] = []
        with self.db.write() as conn:
            cur = conn.execute(
                "INSERT INTO experiments(ts, task_key, title, goal, domain, success_criteria,"
                " budget, status, meta) VALUES (?,?,?,?,?,?,?,?,?)",
                (
                    utcnow(), task_key, title, goal, domain,
                    json.dumps(success_criteria),
                    json.dumps(budget or {"attempts": 8, "seconds": 120}),
                    "open",
                    json.dumps(meta or {}),
                ),
            )
            out.append(int(cur.lastrowid))
        return out[0]

    def get_experiment(self, experiment_id: int) -> dict[str, Any] | None:
        row = self.db.query_one("SELECT * FROM experiments WHERE id=?", (experiment_id,))
        return dict(row) if row else None

    def close_experiment(self, experiment_id: int, status: str, *, seconds: float = 0.0) -> None:
        if status not in EXPERIMENT_STATES:
            raise ValueError(f"invalid experiment state {status!r}")
        self.db.execute(
            "UPDATE experiments SET status=?, ended_at=?, seconds=? WHERE id=?",
            (status, utcnow(), round(seconds, 3), experiment_id),
        )

    def set_best_candidate(self, experiment_id: int, candidate_id: int) -> None:
        self.db.execute(
            "UPDATE experiments SET best_candidate_id=? WHERE id=?", (candidate_id, experiment_id)
        )

    def experiments(self, limit: int = 50) -> list[dict[str, Any]]:
        return [dict(r) for r in self.db.query(
            "SELECT * FROM experiments ORDER BY id DESC LIMIT ?", (limit,)
        )]

    # ------------------------------------------------------------- hypotheses
    def propose(
        self,
        experiment_id: int,
        statement: str,
        *,
        kind: str = "plan",
        rationale: str = "",
        based_on: list[str] | None = None,
        confidence: float = 0.5,
    ) -> int:
        if not statement.strip():
            raise ValueError("a hypothesis must state something")
        with self.db.write() as conn:
            cur = conn.execute(
                "INSERT INTO hypotheses(experiment_id, ts, kind, statement, rationale, based_on,"
                " status, confidence) VALUES (?,?,?,?,?,?,?,?)",
                (
                    experiment_id, utcnow(), kind, statement.strip(), rationale,
                    json.dumps(based_on or []), "proposed", float(confidence),
                ),
            )
            return int(cur.lastrowid)

    def mark_hypothesis(self, hypothesis_id: int, status: str, *, confidence: float | None = None) -> None:
        if status not in HYPOTHESIS_STATES:
            raise ValueError(f"invalid hypothesis state {status!r}")
        if confidence is None:
            self.db.execute("UPDATE hypotheses SET status=? WHERE id=?", (status, hypothesis_id))
        else:
            self.db.execute(
                "UPDATE hypotheses SET status=?, confidence=? WHERE id=?",
                (status, float(confidence), hypothesis_id),
            )

    def hypotheses(self, experiment_id: int) -> list[dict[str, Any]]:
        return [dict(r) for r in self.db.query(
            "SELECT * FROM hypotheses WHERE experiment_id=? ORDER BY id", (experiment_id,)
        )]

    # --------------------------------------------------------------- attempts
    def record_attempt(self, experiment_id: int, attempt: Attempt, *,
                       hypothesis_id: int | None = None) -> int:
        if attempt.failure_class not in FAILURE_CLASSES:
            raise ValueError(f"invalid failure class {attempt.failure_class!r}")
        with self.db.write() as conn:
            cur = conn.execute(
                "INSERT INTO attempts(experiment_id, hypothesis_id, ts, n, kind, plan, code, ok,"
                " failure_class, error, observed, criteria_results, duration_ms, tokens_used)"
                " VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,?)",
                (
                    experiment_id, hypothesis_id, utcnow(), attempt.n, attempt.kind,
                    json.dumps(attempt.plan), attempt.code, int(attempt.ok),
                    attempt.failure_class, attempt.error[:4000],
                    json.dumps(attempt.observed, default=str)[:20000],
                    json.dumps([c.to_json() for c in attempt.criteria_results]),
                    round(attempt.duration_ms, 1), attempt.tokens_used,
                ),
            )
            aid = int(cur.lastrowid)
        attempt.id = aid
        self.db.log_provenance(
            "attempts", aid, "execute",
            detail={"experiment": experiment_id, "n": attempt.n,
                    "ok": attempt.ok, "failure": attempt.failure_class},
        )
        return aid

    def next_attempt_number(self, experiment_id: int) -> int:
        row = self.db.query_one(
            "SELECT COALESCE(MAX(n), 0) FROM attempts WHERE experiment_id=?", (experiment_id,)
        )
        return int(row[0]) + 1 if row else 1

    def attempts(self, experiment_id: int) -> list[dict[str, Any]]:
        return [dict(r) for r in self.db.query(
            "SELECT * FROM attempts WHERE experiment_id=? ORDER BY n", (experiment_id,)
        )]

    def failure_history(self, experiment_id: int) -> list[str]:
        return [r["failure_class"] for r in self.db.query(
            "SELECT failure_class FROM attempts WHERE experiment_id=? ORDER BY n", (experiment_id,)
        )]

    # ------------------------------------------------------- skill candidates
    def add_candidate(
        self,
        experiment_id: int,
        slug: str,
        procedure: list[dict[str, Any]],
        verification: dict[str, Any],
        *,
        attempt_id: int | None = None,
        procedure_kind: str = "tool_sequence",
        supersedes: str = "",
    ) -> int:
        with self.db.write() as conn:
            cur = conn.execute(
                "INSERT INTO skill_candidates(experiment_id, attempt_id, ts, slug, procedure,"
                " procedure_kind, verification, status, supersedes) VALUES (?,?,?,?,?,?,?,?,?)",
                (
                    experiment_id, attempt_id, utcnow(), slug, json.dumps(procedure),
                    procedure_kind, json.dumps(verification, default=str), "candidate", supersedes,
                ),
            )
            return int(cur.lastrowid)

    def get_candidate(self, candidate_id: int) -> dict[str, Any] | None:
        row = self.db.query_one("SELECT * FROM skill_candidates WHERE id=?", (candidate_id,))
        return dict(row) if row else None

    def candidates(self, *, status: str | None = None, limit: int = 100) -> list[dict[str, Any]]:
        if status:
            return [dict(r) for r in self.db.query(
                "SELECT * FROM skill_candidates WHERE status=? ORDER BY id DESC LIMIT ?",
                (status, limit),
            )]
        return [dict(r) for r in self.db.query(
            "SELECT * FROM skill_candidates ORDER BY id DESC LIMIT ?", (limit,)
        )]

    def record_replay(self, candidate_id: int, *, passed: bool, failures: list[str],
                      runs: int) -> None:
        status = "replay_passed" if passed else "replay_failed"
        self.db.execute(
            "UPDATE skill_candidates SET replay_passed=?, replay_runs=?, replay_failures=?,"
            " status=? WHERE id=?",
            (int(passed), runs, json.dumps(failures), status, candidate_id),
        )

    def mark_candidate(self, candidate_id: int, status: str, *, promoted_skill: str = "") -> None:
        if status not in CANDIDATE_STATES:
            raise ValueError(f"invalid candidate state {status!r}")
        if promoted_skill:
            self.db.execute(
                "UPDATE skill_candidates SET status=?, promoted_skill=? WHERE id=?",
                (status, promoted_skill, candidate_id),
            )
        else:
            self.db.execute(
                "UPDATE skill_candidates SET status=? WHERE id=?", (status, candidate_id)
            )

    # ------------------------------------------------------------- replays
    def record_skill_replay(self, skill_slug: str, *, passed: bool, task_key: str = "",
                            variation: str = "original", detail: dict[str, Any] | None = None,
                            duration_ms: float = 0.0) -> None:
        self.db.execute(
            "INSERT INTO skill_replays(ts, skill_slug, task_key, variation, passed, detail,"
            " duration_ms) VALUES (?,?,?,?,?,?,?)",
            (utcnow(), skill_slug, task_key, variation, int(passed),
             json.dumps(detail or {}, default=str), round(duration_ms, 1)),
        )

    def replays(self, skill_slug: str, limit: int = 50) -> list[dict[str, Any]]:
        return [dict(r) for r in self.db.query(
            "SELECT * FROM skill_replays WHERE skill_slug=? ORDER BY id DESC LIMIT ?",
            (skill_slug, limit),
        )]

    # ------------------------------------------------------------ resources
    def sample_resources(self, *, experiment_id: int | None = None, context: str = "") -> dict[str, float]:
        import psutil

        proc = psutil.Process()
        with proc.oneshot():
            rss = proc.memory_info().rss / (1024 * 1024)
            cpu = sum(proc.cpu_times()[:2])
        self.db.execute(
            "INSERT INTO resource_samples(ts, experiment_id, rss_mb, cpu_seconds, context)"
            " VALUES (?,?,?,?,?)",
            (utcnow(), experiment_id, round(rss, 1), round(cpu, 2), context),
        )
        return {"rss_mb": round(rss, 1), "cpu_seconds": round(cpu, 2)}

    def summary(self) -> dict[str, Any]:
        def one(sql: str) -> int:
            row = self.db.query_one(sql)
            return int(row[0]) if row else 0

        return {
            "experiments": one("SELECT COUNT(*) FROM experiments"),
            "solved": one("SELECT COUNT(*) FROM experiments WHERE status='solved'"),
            "attempts": one("SELECT COUNT(*) FROM attempts"),
            "attempts_failed": one("SELECT COUNT(*) FROM attempts WHERE ok=0"),
            "hypotheses": one("SELECT COUNT(*) FROM hypotheses"),
            "candidates": one("SELECT COUNT(*) FROM skill_candidates"),
            "replay_passed": one(
                "SELECT COUNT(*) FROM skill_candidates WHERE replay_passed=1"),
            "promoted": one("SELECT COUNT(*) FROM skill_candidates WHERE status='promoted'"),
            "rejected": one("SELECT COUNT(*) FROM skill_candidates WHERE status='rejected'"),
        }


class SkillPromoter:
    """The only path from a candidate procedure to verified procedural memory.

    Refuses unless independent replay passed. That refusal is the difference
    between "it worked once" and "it is a skill".
    """

    def __init__(self, db: BrainDB | None = None) -> None:
        from minicoder.memory.systems import ProceduralMemory

        self.db = db or BrainDB()
        self.procedural = ProceduralMemory(self.db)
        self.ledger = ExperimentLedger(self.db)

    def promote(self, candidate_id: int, *, name: str, description: str,
                domain: str = "general", min_replay_runs: int = 3) -> dict[str, Any]:
        from minicoder.memory.systems import Skill

        cand = self.ledger.get_candidate(candidate_id)
        if not cand:
            return {"promoted": False, "reason": "unknown candidate"}
        if cand["status"] == "promoted":
            return {"promoted": False, "reason": "already promoted"}
        if not cand["replay_passed"]:
            self.ledger.mark_candidate(candidate_id, "rejected")
            return {"promoted": False, "reason": "independent replay did not pass"}
        if int(cand["replay_runs"]) < min_replay_runs:
            return {
                "promoted": False,
                "reason": f"needs >= {min_replay_runs} replay runs, had {cand['replay_runs']}",
            }
        verification = json.loads(cand["verification"] or "{}")
        procedure = json.loads(cand["procedure"] or "[]")
        skill = Skill(
            slug=cand["slug"],
            name=name,
            description=description,
            domain=domain,
            reasoning=verification.get("reasoning", []),
            tool_calls=procedure if cand["procedure_kind"] == "tool_sequence" else [],
            solution=verification.get("program", ""),
            verification={
                "passed": True,
                "runner": "learning-loop",
                "criteria": verification.get("criteria", []),
                "replay_runs": cand["replay_runs"],
                "experiment_id": cand["experiment_id"],
                "candidate_id": candidate_id,
            },
            source="verified_execution",
            confidence=0.9,
            meta={"candidate_id": candidate_id, "learned": True},
            episode_ids=[],
        )
        sid = self.procedural.add(skill, verified=True)
        self.ledger.mark_candidate(candidate_id, "promoted", promoted_skill=skill.slug)
        self.db.log_provenance(
            "skills", sid, "promote",
            detail={"candidate": candidate_id, "replays": cand["replay_runs"]},
        )
        return {"promoted": True, "skill_id": sid, "slug": skill.slug}
