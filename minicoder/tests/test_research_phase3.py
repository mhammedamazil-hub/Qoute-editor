"""Phase 3 — tests for the research infrastructure.

These cover the parts that, if wrong, would make every published number meaningless:
the hidden/dev split, evaluator integrity, isolation, cheat detection, and the guarantee that
research runs never touch production memory.
"""

from __future__ import annotations

import json
from pathlib import Path

import pytest

from minicoder.research import tasks as task_mod
from minicoder.research.evaluator import detect_hardcoding, evaluate
from minicoder.research.isolation import available_modes, probe_escapes, run_python_isolated
from minicoder.research.private import PrivateStore
from minicoder.research.synth import acquire, batch_probe, enumerate_candidates


# --------------------------------------------------------------------------- fixtures
@pytest.fixture()
def store(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> PrivateStore:
    monkeypatch.setenv("NACE_PRIVATE_DIR", str(tmp_path / "private"))
    s = PrivateStore.open(create=True)
    s.repin()
    return s


@pytest.fixture()
def record() -> task_mod.TaskRecord:
    return next(r for r in task_mod.generate(11, 24) if r.family == "abs_all")


# --------------------------------------------------------------------------- generation
def test_generation_is_deterministic_and_hashed() -> None:
    a = task_mod.generate(11, 12)
    b = task_mod.generate(11, 12)
    c = task_mod.generate(23, 12)
    assert [r.generation_hash for r in a] == [r.generation_hash for r in b]
    assert [r.generation_hash for r in a] != [r.generation_hash for r in c]
    assert all(len(r.generation_hash) == 64 for r in a)


def test_generated_tasks_are_not_renamed_benchmark_tasks() -> None:
    from minicoder.learning.benchmark import ALL_TASKS

    generated = {r.key for r in task_mod.generate(11, 24)}
    assert not generated & {t.key for t in ALL_TASKS}


def test_hidden_draws_differ_from_dev_and_need_the_salt() -> None:
    rec = task_mod.generate(11, 24)[0]
    dev_inputs = [line.split("solve(", 1)[1].split(") ==")[0]
                  for line in rec.dev_tests.splitlines() if "solve(" in line]
    hidden_a = task_mod.hidden_draw(rec.family, "salt-a", rec.key, 0)
    hidden_b = task_mod.hidden_draw(rec.family, "salt-b", rec.key, 0)
    assert repr(hidden_a) not in " ".join(dev_inputs)
    assert hidden_a != hidden_b, "a different salt must produce different hidden inputs"
    # And the record itself must not carry the hidden set.
    assert "hidden" not in json.dumps(rec.to_json()).lower()


def test_edge_cases_and_specials_are_generated() -> None:
    recs = task_mod.generate(11, 24)
    kinds = {r.kind for r in recs}
    assert {"regular", "composition", "adversarial", "impossible"} <= kinds


# --------------------------------------------------------------------------- evaluator
def test_evaluator_passes_a_correct_program(record, store) -> None:
    verdict = evaluate(record, "def solve(xs):\n    return [abs(x) for x in xs]\n", store=store)
    assert verdict.passed, verdict.detail
    assert verdict.cases >= 3


def test_evaluator_fails_a_wrong_program(record, store) -> None:
    verdict = evaluate(record, "def solve(xs):\n    return list(xs)\n", store=store)
    assert not verdict.passed
    assert verdict.verdict in {"wrong_value", "wrong_type"}


def test_evaluator_flags_hardcoded_dev_answers(record, store) -> None:
    first = next(line for line in record.dev_tests.splitlines() if "solve(" in line)
    args = first.split("solve(", 1)[1].split(") ==")[0]
    expected = first.split("==", 1)[1].strip()
    code = f"def solve(xs):\n    if xs == {args}:\n        return {expected}\n    return xs\n"
    verdict = evaluate(record, code, store=store)
    assert verdict.verdict == "cheating", verdict.verdict
    assert verdict.detections["dev_literals_in_code"]


def test_evaluator_refuses_when_sources_were_modified(store) -> None:
    store.repin()
    assert store.verify()["ok"] is True
    # Simulate tampering by writing a manifest with a wrong hash for a pinned source.
    manifest_path = store.root / "manifest.json"
    manifest = json.loads(manifest_path.read_text())
    manifest["sources"]["minicoder/research/tasks.py"] = "0" * 64
    manifest_path.write_text(json.dumps(manifest))
    assert store.verify()["ok"] is False


def test_detect_hardcoding_sees_lookup_tables(record) -> None:
    findings = detect_hardcoding(
        "def solve(xs):\n    t = {'a': 1, 'b': 2}\n    return t.get(xs, 0)\n", record)
    assert findings["lookup_tables"] >= 1


# --------------------------------------------------------------------------- isolation
def test_isolation_runs_code_and_returns_values() -> None:
    out = run_python_isolated("def solve(x):\n    return x * 2\n", [[21]])
    assert out.ok and out.values == [42]


def test_isolation_times_out_instead_of_hanging() -> None:
    out = run_python_isolated("def solve():\n    while True:\n        pass\n", [[]], timeout=2)
    assert out.timed_out and not out.ok


@pytest.mark.slow
def test_escape_matrix_has_no_escapes_in_any_mode() -> None:
    for mode in [m.name for m in available_modes()]:
        rows = probe_escapes(mode)
        escaped = [r["probe"] for r in rows if r["escaped"]]
        assert not escaped, f"{mode} allowed: {escaped}"


def test_phase2_guard_bypass_is_closed_by_the_new_guard(tmp_path: Path) -> None:
    """The audit found chdir+relative-open escaped the Phase 2 hook; it must not here."""
    code = ('def solve():\n'
            '    import os\n'
            '    os.chdir("/")\n'
            '    return open("etc/hostname").read()\n')
    out = run_python_isolated(code, [[]], mode="guard")
    assert not out.ok


# --------------------------------------------------------------------------- synthesis
def test_candidate_generation_is_tagged_for_ablations(record) -> None:
    tagged = enumerate_candidates(record)
    assert tagged and all(isinstance(t, tuple) and t[1] in
                          {"unary", "compose", "binary", "rows"} for t in tagged)
    no_compose = enumerate_candidates(record, depth=1)
    assert all(tag != "compose" for _, tag in no_compose)


def test_batch_probe_isolates_candidates(record) -> None:
    good = "def solve(xs):\n    return [abs(x) for x in xs]\n"
    bad = "def solve(xs):\n    return list(xs)\n"
    assert batch_probe([bad, good], record.dev_tests) == [False, True]


def test_acquisition_finds_a_program_and_it_survives_hidden_tests(record, store) -> None:
    got = acquire(record, budget_seconds=30)
    assert got["solved_dev"] and got["code"]
    verdict = evaluate(record, got["code"], store=store)
    assert verdict.passed, verdict.detail


# --------------------------------------------------------------------------- production safety
@pytest.mark.slow
def test_research_run_never_touches_production_memory(tmp_path: Path) -> None:
    from minicoder.research.experiment import run_experiment

    report = run_experiment(seeds=[11], n_tasks=6, arms=("A", "C"),
                            budget=10, out_dir=tmp_path, warmup_seed=None)
    assert report["production_memory"]["unchanged"] is True
    assert tmp_path.exists()


def test_reports_carry_provenance(tmp_path: Path) -> None:
    from minicoder.research.experiment import render_markdown, run_experiment

    report = run_experiment(seeds=[11], n_tasks=6, arms=("A",), budget=10,
                            out_dir=tmp_path, warmup_seed=None)
    for field in ("experiment_id", "git_commit", "generator_version", "hardware",
                  "config", "rate_ci", "production_memory", "tasks_generated"):
        assert field in report
    assert len(report["git_commit"]) >= 7
    assert "Hidden-test pass rate" in render_markdown(report)


# --------------------------------------------------------------------------- sleep fixes
def test_semantic_remember_is_idempotent(home: Path) -> None:
    """Consolidation must not abort when a node label already exists.

    Measured in sleep cycle 4: stage 2 died with "UNIQUE constraint failed:
    semantic_nodes.kind, semantic_nodes.label" and every later stage ran on partial memory.
    """
    from minicoder.config import SOURCE_USER_INSTRUCTION as SRC
    from minicoder.memory.systems import SemanticMemory

    mem = SemanticMemory()
    first = mem.upsert("fact", "duplicate probe", "value one", source=SRC)
    # The second write must not raise even though (kind, label) is unique. It may take
    # any of the upsert paths (update, contradiction revision); what must not happen is
    # the IntegrityError that killed the consolidation stage.
    second = mem.upsert("fact", "duplicate probe", "value two", source=SRC)
    assert isinstance(first, int) and isinstance(second, int)
    count = mem.db.query_one(
        "SELECT COUNT(*) FROM semantic_nodes WHERE kind='fact' AND label='duplicate probe'")[0]
    assert count == 1
    # And the plain insert path used by consolidation is itself idempotent now.
    same = mem.upsert("fact", "duplicate probe", "value one", source=SRC)
    assert mem.db.query_one(
        "SELECT COUNT(*) FROM semantic_nodes WHERE kind='fact' AND label='duplicate probe'")[0] == 1
    assert same == first


def test_shard_builder_skips_blank_examples(tmp_path: Path, home: Path) -> None:
    """A lesson with an empty side must be dropped, not written and then rejected.

    Measured in sleep cycle 4: stage 7 died with "line 1: empty prompt/response".
    """
    from minicoder.sleep.compiler import build_shard

    out = build_shard(out_dir=tmp_path)
    if not out.get("created"):
        pytest.skip(f"no shard produced in this environment: {out.get('reason')}")
    for line in Path(out["path"]).read_text(encoding="utf-8").splitlines():
        if not line.strip():
            continue
        obj = json.loads(line)
        assert obj["prompt"].strip() and obj["response"].strip()
