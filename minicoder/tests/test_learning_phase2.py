"""Tests for the Phase 2 learning loop.

The assertions here are mostly about *refusal*: the sandbox must refuse escapes,
the promoter must refuse unverified candidates, the guard must refuse regressions.
A system that cannot refuse is a system that cannot be trusted to learn.

Bridge-backed tests are grouped behind one session-scoped bridge because starting
the editor subprocess costs about ten seconds.
"""

from __future__ import annotations

import json
from pathlib import Path

import pytest

from minicoder.learning.criteria import (
    EditorState,
    evaluate_editor_criteria,
    progress,
)
from minicoder.learning.ledger import Attempt, CriterionResult, ExperimentLedger
from minicoder.tools.sandbox import Sandbox

# ------------------------------------------------------------------ sandbox


@pytest.mark.parametrize(
    "code,label",
    [
        ("open('/etc/passwd').read()", "filesystem read"),
        ("import os; os.system('echo hi')", "process spawn"),
        ("import subprocess; subprocess.run(['echo','x'])", "subprocess"),
        ("import socket; socket.socket()", "socket"),
        ("import ctypes; ctypes.CDLL('libc.so.6')", "ctypes"),
    ],
)
def test_sandbox_blocks_escapes(code: str, label: str) -> None:
    """The guard must refuse filesystem, process, socket and ctypes access.

    Before the audit hook existed, open('/etc/passwd') and os.system both
    succeeded — the sandbox was permissioned only in its documentation.
    """
    sandbox = Sandbox()
    ok, result = sandbox.run_tests(code, "pass", timeout=10)
    assert not ok, f"{label} was not blocked"
    assert "not permitted" in (result.stderr + result.stdout)


def test_sandbox_allows_legitimate_work() -> None:
    """Confining the sandbox must not break ordinary computation or scratch I/O."""
    sandbox = Sandbox()
    ok, result = sandbox.run_tests(
        "import json\n"
        "def solve(xs):\n"
        "    open('scratch.txt', 'w').write('ok')\n"
        "    return json.dumps(sorted(xs))\n",
        "assert solve([3,1,2]) == '[1, 2, 3]'\nassert open('scratch.txt').read() == 'ok'",
        timeout=10,
    )
    assert ok, result.stderr


def test_sandbox_still_fails_wrong_answers() -> None:
    sandbox = Sandbox()
    ok, _ = sandbox.run_tests("def solve(n):\n    return n", "assert solve(3) == 6")
    assert not ok


# ------------------------------------------------------------------- ledger


@pytest.fixture()
def ledger(home: Path) -> ExperimentLedger:  # noqa: ARG001 - home isolates the DB
    return ExperimentLedger()


def test_experiment_requires_a_criterion(ledger: ExperimentLedger) -> None:
    with pytest.raises(ValueError, match="criterion"):
        ledger.open_experiment("k", "t", "g", [])


def test_four_states_are_distinct(ledger: ExperimentLedger) -> None:
    """A hypothesis, an attempt, a candidate and a skill must not be conflated."""
    eid = ledger.open_experiment("k", "Task", "Goal", ["canvas_size(10, 10)"])
    hyp = ledger.propose(eid, "setting the canvas will satisfy it")
    aid = ledger.record_attempt(
        eid,
        Attempt(n=1, ok=False, failure_class="wrong_value",
                error="canvas still 1080x1350",
                criteria_results=[CriterionResult("canvas_size(10, 10)", False, "1080x1350")]),
        hypothesis_id=hyp,
    )
    # A failed attempt produces no candidate and no skill.
    assert ledger.candidates() == []
    assert ledger.summary()["candidates"] == 0
    assert ledger.summary()["attempts_failed"] == 1
    assert ledger.attempts(eid)[0]["failure_class"] == "wrong_value"
    assert aid > 0


def test_invalid_failure_class_is_rejected(ledger: ExperimentLedger) -> None:
    eid = ledger.open_experiment("k", "Task", "Goal", ["x"])
    with pytest.raises(ValueError, match="failure class"):
        ledger.record_attempt(eid, Attempt(n=1, ok=False, failure_class="made_up"))


def test_promoter_refuses_unverified_candidate(ledger: ExperimentLedger) -> None:
    """The central rule: a successful execution is not a skill."""
    from minicoder.learning.ledger import SkillPromoter
    from minicoder.memory.systems import ProceduralMemory

    eid = ledger.open_experiment("k", "Task", "Goal", ["x"])
    cand = ledger.add_candidate(eid, "learned_never", [], {"criteria": ["x"]})
    out = SkillPromoter(ledger.db).promote(cand, name="n", description="d")
    assert out["promoted"] is False
    assert "replay" in out["reason"]
    assert ProceduralMemory(ledger.db).get("learned_never") is None
    assert ledger.get_candidate(cand)["status"] == "rejected"


def test_promoter_requires_multiple_replays(ledger: ExperimentLedger) -> None:
    from minicoder.learning.ledger import SkillPromoter

    eid = ledger.open_experiment("k", "Task", "Goal", ["x"])
    cand = ledger.add_candidate(eid, "learned_once", [], {"criteria": ["x"]})
    ledger.record_replay(cand, passed=True, failures=[], runs=1)
    out = SkillPromoter(ledger.db).promote(cand, name="n", description="d",
                                          min_replay_runs=3)
    assert out["promoted"] is False
    assert "replay runs" in out["reason"]


def test_promoter_admits_after_replay(ledger: ExperimentLedger) -> None:
    from minicoder.learning.ledger import SkillPromoter
    from minicoder.memory.systems import ProceduralMemory

    eid = ledger.open_experiment("k", "Task", "Goal", ["x"])
    cand = ledger.add_candidate(eid, "learned_ok", [{"tool": "noop", "args": {}}],
                               {"criteria": ["x"], "reasoning": ["did it"]})
    ledger.record_replay(cand, passed=True, failures=[], runs=3)
    out = SkillPromoter(ledger.db).promote(cand, name="Learned", description="d")
    assert out["promoted"] is True
    skill = ProceduralMemory(ledger.db).get("learned_ok")
    assert skill is not None
    assert json.loads(skill["verification"])["replay_runs"] == 3


# ----------------------------------------------------------------- criteria


def _state(**over) -> EditorState:
    base = {
        "canvas": {"width": 800, "height": 800, "background": "#101010"},
        "layers": [
            {"type": "text", "text": "HEADLINE", "x": 300, "y": 300, "w": 200, "h": 80,
             "size": 60, "align": "center"},
            {"type": "text", "text": "sub", "x": 320, "y": 450, "w": 160, "h": 30, "size": 18},
        ],
    }
    base.update(over)
    return EditorState.from_snapshot(base)


def test_criteria_split_pass_and_fail() -> None:
    results = evaluate_editor_criteria(
        ['canvas_size(800, 800)', 'text_present("HEADLINE")', 'centred(text, "HEADLINE")',
         'count(text, >=, 2)', 'no_overlap()', 'canvas_size(1, 1)',
         'text_present("ABSENT")'],
        _state(),
    )
    passed = [r.criterion for r in results if r.passed]
    failed = [r.criterion for r in results if not r.passed]
    assert 'canvas_size(800, 800)' in passed
    assert 'centred(text, "HEADLINE")' in passed
    assert 'canvas_size(1, 1)' in failed
    assert 'text_present("ABSENT")' in failed
    assert progress(results) == pytest.approx(len(passed) / len(results))


def test_unknown_criterion_is_an_error_not_a_silent_pass() -> None:
    results = evaluate_editor_criteria(['not_a_thing(1)'], _state())
    assert results[0].passed is False
    assert "criterion error" in results[0].detail


def test_no_overlap_detects_a_collision() -> None:
    state = _state()
    state.layers[1]["y"] = 310          # sits on top of the headline
    results = evaluate_editor_criteria(["no_overlap()"], state)
    assert results[0].passed is False
    assert "overlapping" in results[0].detail


# ---------------------------------------------------------------- discovery


def test_discovery_extracts_enum_vocabulary() -> None:
    """The planner must read valid values off the tool, not invent them.

    Inventing them produced shape='shape', which the editor rejected.
    """
    from minicoder.learning.discovery import ToolIndex

    index = ToolIndex([
        {"name": "add_shape",
         "description": "Add a geometric shape: rect, roundedRect, circle, ellipse, "
                        "triangle, polygon, star, line.",
         "parameters": {"properties": {"shape": {"type": "string"},
                                       "x": {"type": "number"}}, "required": ["shape"]}},
    ])
    tool = index.get("add_shape")
    assert tool is not None
    shape_param = next(p for p in tool.params if p.name == "shape")
    assert "rect" in shape_param.choices
    assert "circle" in shape_param.choices
    # A coordinate must never inherit an enum vocabulary.
    x_param = next(p for p in tool.params if p.name == "x")
    assert x_param.choices == []


def test_discovery_resolves_invented_names() -> None:
    from minicoder.learning.discovery import ToolIndex

    index = ToolIndex([
        {"name": "add_text", "description": "add text"},
        {"name": "set_canvas_size", "description": "resize"},
    ])
    tool, how = index.resolve("addText")
    assert tool is not None and tool.name == "add_text"
    assert how in {"fuzzy", "normalised", "searched"}
    tool, _ = index.resolve("add_texts")
    assert tool is not None and tool.name == "add_text"
    assert index.resolve("definitely_not_a_tool")[0] is None


def test_read_only_tools_are_never_actions() -> None:
    from minicoder.learning.discovery import ToolIndex

    index = ToolIndex([{"name": "get_app_state", "description": "read"}])
    assert index.is_read_only("get_app_state") is True
    assert index.is_read_only("add_text") is False


# ------------------------------------------------------------------- synth


def test_synth_solves_a_simple_transformation() -> None:
    from minicoder.learning.benchmark import BenchTask
    from minicoder.learning.synth import synth_task

    task = BenchTask("t_double", "python", "easy", "double", entry="solve",
                     tests="assert solve([1,2])==[2,4]")
    result = synth_task(task, deadline=20)
    assert result.solved
    # The recorded success must come from the confined executor, not the probe.
    assert result.confirmed_in_sandbox


def test_synth_reports_failure_instead_of_inventing_success() -> None:
    from minicoder.learning.benchmark import BenchTask
    from minicoder.learning.synth import synth_task

    # No composition of the primitives can satisfy this.
    task = BenchTask("t_impossible", "python", "hard", "impossible", entry="solve",
                     tests="assert solve(1)==42")
    result = synth_task(task, deadline=10, max_depth=2)
    assert result.solved is False
    assert result.failure


def test_benchmark_is_sealed(home: Path) -> None:  # noqa: ARG001
    # Isolated home: the seal also checks promoted skills, and reading the live
    # brain would make this test depend on whatever the developer last ran.
    from minicoder.learning.benchmark import assert_sealed

    report = assert_sealed()
    assert report["sealed"] is True, report["problems"]
    assert report["tasks"] > 0


def test_benchmark_tests_are_discriminating() -> None:
    """No task may be satisfiable by a plausible-but-wrong program.

    Two tasks in the first draft were: a count solved by sum(), a last-element
    task solved by len(). Both were caught here and the fixtures strengthened.
    """
    from minicoder.learning.benchmark import audit_test_strength

    assert audit_test_strength() == []


def test_benchmark_definitions_are_verifiable() -> None:
    from minicoder.learning.benchmark import validate_task_definitions

    assert validate_task_definitions() == []


# --------------------------------------------------------------- safeguard


def test_regression_guard_detects_a_collapse() -> None:
    from minicoder.learning.safeguard import RegressionGuard

    verdict = RegressionGuard().compare(
        {"skill_accuracy": 0.875, "val_ce": 5.68},
        {"skill_accuracy": 0.0, "val_ce": 356.1},
    )
    assert verdict.passed is False
    assert {r["metric"] for r in verdict.regressions} == {"skill_accuracy", "val_ce"}


def test_regression_guard_admits_an_improvement() -> None:
    from minicoder.learning.safeguard import RegressionGuard

    verdict = RegressionGuard().compare(
        {"skill_accuracy": 0.5, "val_ce": 6.0},
        {"skill_accuracy": 0.7, "val_ce": 5.5},
    )
    assert verdict.passed is True
    assert len(verdict.improvements) == 2


def test_baseline_is_immutable_and_tamper_evident(tmp_path: Path, home: Path) -> None:  # noqa: ARG001
    # `home` redirects CONFIG at a throwaway directory. Without it, a restore
    # that defaulted to CONFIG.paths.checkpoints wrote a test fixture over the
    # real lm.pt (measured: the live checkpoint became 8 bytes of the string
    # "original"). Tests must not be able to reach production weights.
    from minicoder.learning.safeguard import BaselineRegistry

    source = tmp_path / "ckpt"
    source.mkdir()
    (source / "lm.pt").write_bytes(b"weights")
    (source / "tokenizer.json").write_bytes(b"{}")

    registry = BaselineRegistry(root=tmp_path / "baselines")
    created = registry.snapshot("b1", source=source)
    assert created["created"] is True
    assert registry.verify_baseline("b1")["intact"] is True

    # A second snapshot of the same name must not overwrite the first.
    assert registry.snapshot("b1", source=source)["created"] is False

    # Tampering is detected by hash.
    target = tmp_path / "baselines" / "b1" / "lm.pt"
    target.chmod(0o644)
    target.write_bytes(b"tampered")
    integrity = registry.verify_baseline("b1")
    assert integrity["intact"] is False
    assert any("lm.pt" in p for p in integrity["problems"])


def test_baseline_restore_returns_the_original(tmp_path: Path, home: Path) -> None:  # noqa: ARG001
    from minicoder.learning.safeguard import BaselineRegistry

    source = tmp_path / "ckpt"
    source.mkdir()
    (source / "lm.pt").write_bytes(b"original")
    registry = BaselineRegistry(root=tmp_path / "baselines")
    registry.snapshot("b2", source=source)
    (source / "lm.pt").write_bytes(b"wrecked")
    out = registry.restore("b2", target=source)
    assert out["restored"] is True
    assert (source / "lm.pt").read_bytes() == b"original"


# ---------------------------------------------------------------- end to end
@pytest.fixture(scope="session")
def bridge():
    """One editor subprocess for every bridge-backed test (~10s to start)."""
    from minicoder.tools.editor_bridge import EditorBridge

    b = EditorBridge()
    try:
        b._ensure()
        yield b
    finally:
        try:
            b.close()
        except Exception:
            pass


@pytest.mark.slow
def test_planner_solves_an_unseen_task(bridge, home: Path) -> None:  # noqa: ARG001
    """No keyword table covers this task; the planner must search for it."""
    from minicoder.learning.discovery import tool_index_from_bridge
    from minicoder.learning.planner import SearchPlanner

    criteria = [
        'canvas_size(640, 900)', 'background_contains("#20303a")',
        'text_present("Tide Tables")', 'text_present("Low water 06:12")',
        'count(shape, >=, 1)', 'centred(text, "Tide Tables")',
        'within_canvas()', 'no_overlap()',
    ]
    planner = SearchPlanner(tool_index_from_bridge(bridge))
    out = planner.plan(criteria, bridge)
    assert out["progress"] == 1.0
    assert out["plan"], "an empty plan cannot satisfy eight criteria"


@pytest.mark.slow
def test_planner_undoes_only_what_it_changed(bridge) -> None:
    """A failed candidate must not roll back the previous accepted step.

    The original implementation called undo unconditionally, which popped the
    canvas resize and silently destroyed progress.
    """
    from minicoder.learning.discovery import tool_index_from_bridge
    from minicoder.learning.planner import SearchPlanner

    planner = SearchPlanner(tool_index_from_bridge(bridge))
    out = planner.plan(['canvas_size(500, 500)', 'text_present("KEEP")'], bridge)
    assert out["progress"] == 1.0
    # The canvas requirement had to survive the text search.
    assert out["state"].canvas_width == 500


@pytest.mark.slow
def test_learning_loop_promotes_only_after_fresh_replay(bridge, home: Path) -> None:  # noqa: ARG001
    from minicoder.learning.engine import LearningLoop, TaskSpec

    task = TaskSpec("t_loop", "Loop", "a 400x400 canvas with the word LOOP",
                    ['canvas_size(400, 400)', 'text_present("LOOP")'])
    loop = LearningLoop()
    try:
        loop._bridge = bridge          # reuse the session bridge
        loop._index = None
        rep = loop.acquire(task)
        assert rep.solved
        assert rep.candidate_id is not None
        assert rep.replay_passed
        assert rep.replay_runs == 3
        promoted = loop.promote(rep.candidate_id, task)
        assert promoted["promoted"] is True
    finally:
        loop._bridge = None


@pytest.mark.slow
def test_replay_subprocess_rejects_a_bad_procedure(home: Path) -> None:
    """The fresh-process replay must actually verify, not rubber-stamp."""
    import io
    import sys

    from minicoder.learning.replay import main as replay_main

    payload = json.dumps({
        "procedure": [{"tool": "set_canvas_size", "args": {"width": 300, "height": 300}}],
        "criteria": ['canvas_size(999, 999)'],
    })
    old_stdin, old_stdout = sys.stdin, sys.stdout
    sys.stdin = io.StringIO(payload)
    sys.stdout = io.StringIO()
    try:
        replay_main(["--stdin"])
        out = sys.stdout.getvalue()
    finally:
        sys.stdin, sys.stdout = old_stdin, old_stdout
    verdict = json.loads(out.split("__REPLAY__")[-1].strip())
    assert verdict["passed"] is False


def test_restore_defaults_to_the_recorded_origin(tmp_path: Path, home: Path) -> None:  # noqa: ARG001
    """A restore must go back where the baseline came from, not somewhere global.

    Defaulting to CONFIG.paths.checkpoints repaired the wrong directory and left
    the actual source broken.
    """
    from minicoder.learning.safeguard import BaselineRegistry

    source = tmp_path / "origin"
    source.mkdir()
    (source / "lm.pt").write_bytes(b"good")
    registry = BaselineRegistry(root=tmp_path / "baselines")
    registry.snapshot("origin_baseline", source=source)
    (source / "lm.pt").write_bytes(b"bad")
    registry.restore("origin_baseline")
    assert (source / "lm.pt").read_bytes() == b"good"


@pytest.mark.slow
def test_benchmark_does_not_contaminate_production_memory(tmp_path: Path) -> None:
    """A benchmark run must leave the live brain's procedural memory untouched.

    Measured before isolation existed: one run promoted three `learned_*` skills
    into production memory and then tripped the seal on the next run.
    """
    from minicoder import config as config_mod
    from minicoder.learning.runner import run_benchmark

    live_home = config_mod.activate_home(tmp_path / "live")
    try:
        from minicoder.memory.db import BrainDB

        db = BrainDB()
        before_skills = db.query_one("SELECT COUNT(*) FROM skills")[0]
        before_experiments = db.query_one("SELECT COUNT(*) FROM experiments")[0]
        db.close()
    finally:
        config_mod.activate_home(live_home)

    run_benchmark(editor=False, out_dir=tmp_path / "reports")

    live_home = config_mod.activate_home(tmp_path / "live")
    try:
        from minicoder.memory.db import BrainDB

        db = BrainDB()
        assert db.query_one("SELECT COUNT(*) FROM skills")[0] == before_skills
        assert db.query_one("SELECT COUNT(*) FROM experiments")[0] == before_experiments
        db.close()
    finally:
        config_mod.activate_home(live_home)
