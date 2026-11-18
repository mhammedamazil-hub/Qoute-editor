"""Phase 4 tests: the six Phase 3 defects plus one test per new subsystem.

The defect tests are the point. Each one pins a failure that was observed on the
live system, so a future change that reintroduces it fails here instead of in a
report:

1. a raw tool trajectory returned as an answer;
2. a question that mutated the canvas;
3. introspection that could not see an existing sleep report;
4. duplicate semantic nodes;
5. skill examples with an empty body;
6. the acceptance suite writing to production memory.
"""

from __future__ import annotations

import json
from pathlib import Path

import pytest


# --------------------------------------------------------------------------- 1
def test_no_raw_trajectory_in_an_answer(home: Path) -> None:
    """Defect 1: a question was answered with JSON steps instead of prose."""
    from minicoder.cognition.engine import GroundedAnswerer
    from minicoder.memory.db import BrainDB
    from minicoder.memory.systems import EpisodicMemory, ProceduralMemory, SemanticMemory

    db = BrainDB()
    proc = ProceduralMemory(db)
    db.execute(
        "INSERT INTO skills(slug, name, domain, description, reasoning, tool_calls,"
        " solution, verification, status, source, confidence, created_at, updated_at)"
        " VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?)",
        ("canvas_setcanvassize", "canvas set canvas size", "editor",
         "Create a poster canvas. Task: canvas set canvas size", "[]",
         json.dumps([{"tool": "set_canvas_size",
                      "args": {"width": 1080, "height": 1350}}]),
         "set_canvas_size(width=1080, height=1350)",
         json.dumps({"passed": True, "hash": "x"}), "VERIFIED", "verified_execution",
         0.8, "2026-11-01T00:00:00+00:00", "2026-11-01T00:00:00+00:00"),
    )
    semantic = SemanticMemory(db)
    semantic.upsert("fact", "poster fonts",
                    "Two: one display face for the quote, one quiet face for attribution.",
                    status="VERIFIED", source="documentation", confidence=0.9)
    answerer = GroundedAnswerer(None, EpisodicMemory(db), semantic, proc)
    answer = answerer.answer("How many fonts should I use in one poster?")

    text = answer.text
    assert "Two" in text
    # The two giveaways of a leaked trajectory: tool syntax and a JSON body.
    assert "set_canvas_size(" not in text
    assert not text.strip().startswith("{") and '{"tool"' not in text
    assert not text.strip().startswith("[")


# --------------------------------------------------------------------------- 2
def test_a_question_never_mutates_the_canvas(home: Path) -> None:
    """Defect 2: 'How many fonts…' reached the planner and changed the canvas."""
    from minicoder.cognition.agent import DesignAgent
    from minicoder.memory.db import BrainDB

    agent = DesignAgent(BrainDB())
    traj = agent.execute("How many fonts should I use in one poster?")
    assert traj.intent.get("type") == "question"
    assert traj.steps == []
    assert traj.source in ("memory", "self", "refuse", "unknown")


# --------------------------------------------------------------------------- 3
def test_introspection_reads_an_existing_sleep_report(home: Path) -> None:
    """Defect 3: the system denied having a sleep report it had just written."""
    from minicoder.cognition.selfmodel import self_answer
    from minicoder.memory.db import BrainDB

    db = BrainDB()
    logs = home / "memory" / "sleep_logs"
    logs.mkdir(parents=True, exist_ok=True)
    (logs / "sleep_0007.json").write_text(json.dumps({
        "cycle_id": 7, "trigger": "test", "duration_seconds": 1.5,
        "stages": [{"stage": i, "name": "s", "ms": 1} for i in range(1, 9)],
        "metrics": {"episodes_consolidated": 3, "nodes_added": 2},
        "learned": [], "promoted": [], "archived": [], "conflicts": [],
        "shard": {"created": False},
    }))
    answer = self_answer("Summarise your last sleep cycle.", db=db)
    assert answer is not None
    text = answer["text"] if isinstance(answer, dict) else answer
    assert "#7" in text and "8 stages" in text
    # It must not claim a cycle that does not exist.
    assert "999" not in text


# --------------------------------------------------------------------------- 4
def test_no_duplicate_semantic_nodes(home: Path) -> None:
    """Defect 4: consolidation inserted the same node repeatedly."""
    from minicoder.memory.db import BrainDB
    from minicoder.memory.systems import SemanticMemory

    db = BrainDB()
    semantic = SemanticMemory(db)
    for _ in range(4):
        semantic.upsert("fact", "poster margins", "Keep a 60px margin on all sides.",
                        status="VERIFIED", source="documentation", confidence=0.7)
    rows = db.query("SELECT id FROM semantic_nodes WHERE label = 'poster margins'")
    assert len(rows) == 1


# --------------------------------------------------------------------------- 5
def test_skills_without_a_body_never_become_examples(home: Path) -> None:
    """Defect 5: an empty example crashed stage 7 on the live cycle.

    The guard lives in the shard builder, which must drop any example whose
    response is blank rather than write it into a training shard.
    """
    from minicoder.memory.db import BrainDB
    from minicoder.sleep.compiler import build_shard

    db = BrainDB()
    for slug, solution in (("empty_one", ""), ("real_one", "def solve(xs):\n    return xs")):
        db.execute(
            "INSERT INTO skills(slug, name, domain, description, reasoning, tool_calls,"
            " solution, verification, status, source, confidence, created_at, updated_at)"
            " VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?)",
            (slug, slug, "code", f"Task: {slug}", "[]",
             json.dumps([{"tool": "run_python", "args": {}}]), solution,
             json.dumps({"passed": True, "hash": "x"}), "VERIFIED",
             "verified_execution", 0.8, "2026-11-01T00:00:00+00:00",
             "2026-11-01T00:00:00+00:00"))
    shard = build_shard(seed=7)
    path = Path(shard["path"])
    assert path.exists()
    rows = [json.loads(line) for line in path.read_text().splitlines() if line.strip()]
    assert rows, "the shard should still contain the usable skill"
    assert all(str(r.get("response", "")).strip() for r in rows), "blank example reached a shard"
    assert all(r.get("skill") != "empty_one" for r in rows)


def test_adaptive_verification_flags_a_skill_with_an_empty_solution(db) -> None:
    from minicoder.sleep.adaptive import AdaptiveAnalysis

    db.execute(
        "INSERT INTO skills(slug, name, domain, description, reasoning, tool_calls,"
        " solution, verification, status, source, confidence, created_at, updated_at)"
        " VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?)",
        ("empty_solution", "empty", "editor", "", "[]", "[]", "",
         json.dumps({"passed": True}), "VERIFIED", "learning_loop", 0.5,
         "2026-11-01T00:00:00+00:00", "2026-11-01T00:00:00+00:00"),
    )
    report = AdaptiveAnalysis(db).verify_skills()
    assert report["broken_count"] >= 1
    assert any(b["slug"] == "empty_solution" for b in report["broken"])


# --------------------------------------------------------------------------- 6
def test_acceptance_cannot_write_to_production(home: Path, monkeypatch) -> None:
    """Defect 6: `minicoder acceptance` promoted a skill into the live brain."""
    from minicoder import cli
    from minicoder.memory.db import BrainDB

    production = BrainDB()
    before = production.query_one("SELECT COUNT(*) c FROM skills")["c"]

    def fake_run():
        # Simulates the acceptance suite promoting a skill wherever it is pointed.
        live = BrainDB()
        live.execute(
            "INSERT INTO skills(slug, name, domain, description, reasoning, tool_calls,"
            " solution, verification, status, source, confidence, created_at, updated_at)"
            " VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?)",
            ("contaminated", "bad", "editor", "", "[]", "[]", "x",
             json.dumps({"passed": True}), "VERIFIED", "learning_loop", 0.5,
             "2026-11-01T00:00:00+00:00", "2026-11-01T00:00:00+00:00"))
        return {"all_passed": True, "checks": []}

    monkeypatch.setattr("minicoder.learning.acceptance.run", fake_run)
    args = type("A", (), {"json": True, "live": False})()
    assert cli.cmd_acceptance(args) == 0

    after = BrainDB().query_one("SELECT COUNT(*) c FROM skills")["c"]
    assert after == before, "acceptance run leaked a skill into production memory"
    names = {r["slug"] for r in BrainDB().query("SELECT slug FROM skills")}
    assert "contaminated" not in names


# ------------------------------------------------------------------ M1 intent
@pytest.mark.parametrize(("text", "expected"), [
    ("How many fonts should I use in one poster?", "question"),
    ("Explain why a flex child overflows.", "explanation"),
    ("How would you build a poster for a jazz night?", "planning"),
    ("Build a 1080x1350 poster with the headline 'Quiet'.", "execution"),
    ("Run an experiment to see which palette wins.", "experimentation"),
    ("Summarise your last sleep cycle.", "self_introspection"),
])
def test_intent_router_classifies_six_types(text: str, expected: str) -> None:
    from minicoder.cognition.intent import classify

    intent = classify(text)
    assert intent.type.value == expected
    assert 0.0 < intent.confidence <= 1.0


def test_consequential_action_requires_authorization(home: Path) -> None:
    from minicoder.cognition.agent import DesignAgent
    from minicoder.memory.db import BrainDB

    db = BrainDB()
    agent = DesignAgent(db)
    traj = agent.execute("delete every layer on the canvas")
    assert traj.intent["requires_authorization"] is True
    assert traj.source == "refuse"
    assert traj.steps == []
    assert "authoris" in traj.summary.lower() or "authoriz" in traj.summary.lower()
    audit = db.query_one("SELECT * FROM audit_log ORDER BY id DESC LIMIT 1")
    assert audit is not None and audit["allowed"] == 0


# -------------------------------------------------------- M4 generalization
def test_generalization_hidden_axes_differ_from_dev() -> None:
    from minicoder.research.tasks import hidden_draw

    base = hidden_draw("abs_all", "salt", "k", 0)
    assert hidden_draw("abs_all", "salt", "k", 0) == base, "default draws must be reproducible"
    larger = hidden_draw("abs_all", "salt", "k", 0, scale=3)
    assert len(larger[0]) > len(base[0])
    edge = hidden_draw("abs_all", "salt", "k", 0, edge_only=True)
    assert len(edge[0]) <= 3, "boundary draws should be short"


def test_generalization_builds_all_seven_axes(tmp_path: Path) -> None:
    from minicoder.research.generalization import AXES, GeneralizationEngine

    engine = GeneralizationEngine(root=Path(__file__).resolve().parents[2])
    tasks = engine.build_tasks(seed=11, per_axis=1)
    assert [name for name, _ in AXES] == list(tasks)
    assert all(tasks[name] for name in tasks), "an axis produced no tasks"


def test_leakage_guard_detects_a_planted_hidden_key(home: Path) -> None:
    from minicoder.memory.db import BrainDB
    from minicoder.memory.systems import SemanticMemory
    from minicoder.research.generalization import GeneralizationEngine, _library_hash

    engine = GeneralizationEngine(root=Path(__file__).resolve().parents[2])
    tasks = engine.build_tasks(seed=11, per_axis=1)
    # Plant the key that this seed actually produced; family selection is
    # seed-dependent, so a hardcoded key would test nothing.
    key = tasks["unseen_family"][0].key
    SemanticMemory(BrainDB()).upsert(
        "fact", "leaked hidden task", f"saw {key} during training",
        status="UNVERIFIED", source="training_data", confidence=0.5)
    report = engine._leakage({}, {}, _library_hash(engine.library_path),
                             tasks, type("R", (), {"results": []})())
    assert report["ok"] is False
    assert any("hidden task identifiers" in f for f in report["findings"])


def test_frozen_baseline_is_written_once(tmp_path: Path) -> None:
    from minicoder.research.generalization import GeneralizationEngine

    engine = GeneralizationEngine(root=tmp_path)
    engine.research_dir.mkdir(parents=True, exist_ok=True)
    engine.library_path.write_text(json.dumps({"entries": {"abs_all": "x"}, "verified": []}))
    first = engine.freeze_baseline()
    assert first["created"] is True
    engine.library_path.write_text(json.dumps({"entries": {"abs_all": "CHANGED"},
                                               "verified": ["abs_all"]}))
    second = engine.freeze_baseline()
    assert second["created"] is False
    assert second["hash"] == first["hash"], "the baseline moved after it was frozen"


# ------------------------------------------------------------- M5 sleep 2.0
def test_abstraction_is_idempotent(db) -> None:
    from minicoder.memory.systems import SemanticMemory
    from minicoder.sleep.adaptive import AdaptiveAnalysis

    semantic = SemanticMemory(db)
    for i in range(5):
        semantic.upsert("fact", f"palette note {i}",
                        f"Emerald palette variant {i} reads as premium.",
                        status="VERIFIED", source="documentation", confidence=0.8)
    analysis = AdaptiveAnalysis(db, semantic)
    first = analysis.abstract()
    second = analysis.abstract()
    assert first["created"] >= 1
    assert second["created"] == 0, "a second identical pass created new abstractions"


def test_promotion_requires_three_passing_replays(db) -> None:
    from minicoder.sleep.adaptive import AdaptiveAnalysis

    analysis = AdaptiveAnalysis(db)
    db.execute(
        "INSERT INTO experiments(ts, task_key, title, goal, domain, success_criteria,"
        " budget, status) VALUES ('2026-11-01T00:00:00+00:00','promo','Promotion probe',"
        " 'prove the gate holds','editor','[]',1,'solved')")
    experiment_id = int(db.query_one("SELECT MAX(id) i FROM experiments")["i"])
    rows = [
        ("thin_evidence", 1, 1, 0),
        ("solid_evidence", 3, 3, 0),
        ("flaky_evidence", 3, 1, 2),
        ("empty_procedure", 3, 3, 0),
    ]
    for slug, runs, passed, failed in rows:
        proc = "[]" if slug == "empty_procedure" else json.dumps(
            [{"tool": "set_canvas_size", "args": {"width": 10, "height": 10}}])
        db.execute(
            "INSERT INTO skill_candidates(ts, experiment_id, slug, procedure, replay_runs,"
            " replay_passed, replay_failures, status)"
            " VALUES (?,?,?,?,?,?,?, 'replay_passed')",
            ("2026-11-01T00:00:00+00:00", experiment_id, slug, proc, runs, passed,
             json.dumps([0] * failed)))
    result = analysis.promote_candidates()
    promoted = {p["slug"] for p in result["items"]}
    assert promoted == {"solid_evidence"}
    assert result["held"] >= 2 and result["rejected"] >= 1


def test_redundancy_archives_the_weaker_copy_only(db) -> None:
    from minicoder.memory.systems import SemanticMemory
    from minicoder.sleep.adaptive import AdaptiveAnalysis

    semantic = SemanticMemory(db)
    # Same kind and label with different content would be a conflict, so write the
    # duplicate rows directly — this is exactly what a resumed cycle used to do.
    for label, confidence in (("duplicate claim", 0.4), ("duplicate claim (rev 2)", 0.9)):
        db.execute(
            "INSERT INTO semantic_nodes(kind, label, content, status, source, confidence,"
            " created_at, updated_at, access_count, last_access, archived, meta)"
            " VALUES ('fact', ?, 'Keep a 60px margin on all sides.',"
            " 'VERIFIED', 'documentation', ?, '2026-11-01T00:00:00+00:00',"
            " '2026-11-01T00:00:00+00:00', 1, '2026-11-01T00:00:00+00:00', 0, '{}')",
            (label, confidence))
    analysis = AdaptiveAnalysis(db, semantic)
    groups = analysis.find_redundant()
    assert len(groups) == 1
    archived = analysis.dedupe(groups)
    assert archived["archived"] == 1
    live = db.query("SELECT confidence FROM semantic_nodes WHERE label LIKE 'duplicate claim%'"
                    " AND archived = 0")
    assert len(live) == 1 and live[0]["confidence"] == 0.9


def test_fingerprint_ignores_timing_but_not_content() -> None:
    from minicoder.sleep.adaptive import AdaptiveAnalysis

    a = {"stages": [{"stage": 1, "name": "x", "ms": 5, "count": 2, "started_at": "t1"}]}
    b = {"stages": [{"stage": 1, "name": "x", "ms": 900, "count": 2, "started_at": "t2"}]}
    c = {"stages": [{"stage": 1, "name": "x", "ms": 5, "count": 3}]}
    assert AdaptiveAnalysis.fingerprint(a) == AdaptiveAnalysis.fingerprint(b)
    assert AdaptiveAnalysis.fingerprint(a) != AdaptiveAnalysis.fingerprint(c)


# --------------------------------------------------------- M6 metacognition
def test_calibration_persists_and_scores_against_outcomes(home: Path) -> None:
    from minicoder.cognition.metacognition import Metacognition
    from minicoder.memory.db import BrainDB

    db = BrainDB()
    mc = Metacognition(db)
    assert mc.calibration()["n"] == 0
    for predicted, outcome in [(0.9, 1.0), (0.9, 1.0), (0.9, 0.0), (0.9, 1.0)]:
        mc.observe_outcome(predicted, outcome, source="execution")
    fresh = Metacognition(BrainDB())
    cal = fresh.calibration()
    assert cal["n"] == 4, "calibration did not survive a new instance"
    # Brier for three successes and one failure at 0.9:
    expected = (3 * (0.9 - 1.0) ** 2 + (0.9 - 0.0) ** 2) / 4
    assert abs(cal["brier"] - round(expected, 4)) < 1e-6


def test_coverage_says_insufficient_without_support(home: Path) -> None:
    from minicoder.cognition.metacognition import Metacognition
    from minicoder.memory.db import BrainDB
    from minicoder.memory.systems import SemanticMemory

    db = BrainDB()
    mc = Metacognition(db)
    empty = mc.coverage("what is the airspeed of an unladen swallow?",
                        semantic=SemanticMemory(db))
    assert empty["recommendation"] in ("insufficient", "experiment")
    assert empty["support_memories"] == 0


def test_should_experiment_needs_measured_poor_calibration(home: Path) -> None:
    from minicoder.cognition.metacognition import Metacognition
    from minicoder.memory.db import BrainDB

    mc = Metacognition(BrainDB())
    assert mc.should_experiment() is False  # no evidence yet
    for _ in range(5):
        mc.observe_outcome(0.95, 0.0, source="execution")
    assert mc.should_experiment() is True


# ------------------------------------------------------------- M7 security
def test_audit_log_records_refusal_and_grant(home: Path) -> None:
    from minicoder.cognition.agent import DesignAgent
    from minicoder.memory.db import BrainDB

    db = BrainDB()
    agent = DesignAgent(db)
    agent.execute("delete every layer on the canvas")
    rows = db.query("SELECT * FROM audit_log")
    assert rows and rows[-1]["allowed"] == 0 and rows[-1]["authorized"] == 0
    # Phase 5: the Phase 4 ``authorize=True`` boolean no longer grants anything.
    # A refusal must be recorded as a refusal, not as an approval.
    agent.execute("delete every layer on the canvas", authorize=True)
    rows = db.query("SELECT * FROM audit_log")
    assert rows[-1]["allowed"] == 0 and rows[-1]["authorized"] == 0
    detail = json.loads(rows[-1]["detail"])
    assert detail["executed"] is False, "this request has no delete tool: nothing ran"

    # Real authority is an explicit internal context (the operator's own process)
    # or a consumed grant; only then does the audit record an approval.
    from minicoder.security import internal_context

    agent.execute("delete every layer on the canvas", auth=internal_context("test.audit"))
    rows = db.query("SELECT * FROM audit_log")
    assert rows[-1]["allowed"] == 1 and rows[-1]["authorized"] == 1


def test_private_store_is_outside_the_repository() -> None:
    from minicoder.research.private import PrivateStore

    store = PrivateStore.open()
    assert store.reachable_from(Path.cwd()) is False
