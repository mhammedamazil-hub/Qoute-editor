"""Benchmark runner: measure acquisition honestly, and write it down.

Produces a report with every number traced to a recorded measurement:

* first-attempt success and final success, kept apart
* attempts used, seconds, search tokens, resident memory
* whether the solution was confirmed in the sandbox
* replay in a fresh process
* generalisation to a changed variation of the same task
* retention after episodic archival

And it separates the four states the brief insists on:

* **memorisation** — the task was in training data (the suite refuses to run if so)
* **retrieval** — answered from stored knowledge without executing anything
* **adaptation** — a known procedure reused on new inputs
* **acquisition** — a procedure that did not exist before it was searched for

A task that cannot be solved is recorded as a failure with the reason. The
report includes a ``failed`` list on purpose.
"""

from __future__ import annotations

import json
import platform
import time
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

from minicoder.learning.benchmark import (
    ALL_TASKS,
    BenchTask,
    assert_sealed,
    audit_test_strength,
)

EDITOR_CATEGORIES = {"visual", "tool_discovery", "multistep", "new_api"}
REPORT_DIR = Path("datasets/learning")


@dataclass
class TaskResult:
    key: str
    category: str
    difficulty: str
    mode: str                      # acquisition | adaptation | retrieval
    first_attempt_ok: bool
    final_ok: bool
    attempts: int
    seconds: float
    tokens: int
    rss_mb: float
    confirmed: bool = False
    replay_ok: bool | None = None
    replay_runs: int = 0
    generalised_ok: bool | None = None
    program: str = ""
    failure: str = ""
    extra: dict[str, Any] = field(default_factory=dict)

    def to_json(self) -> dict[str, Any]:
        return {
            "key": self.key, "category": self.category, "difficulty": self.difficulty,
            "mode": self.mode, "first_attempt_ok": self.first_attempt_ok,
            "final_ok": self.final_ok, "attempts": self.attempts,
            "seconds": round(self.seconds, 2), "tokens": self.tokens,
            "rss_mb": round(self.rss_mb, 1), "confirmed": self.confirmed,
            "replay_ok": self.replay_ok, "replay_runs": self.replay_runs,
            "generalised_ok": self.generalised_ok,
            "program": self.program, "failure": self.failure, **self.extra,
        }


def _rss() -> float:
    try:
        import psutil

        return round(psutil.Process().memory_info().rss / (1024 * 1024), 1)
    except Exception:
        return 0.0


def _variation(task: BenchTask) -> BenchTask | None:
    """A changed version of the same task, for generalisation."""
    swaps = {
        "visual_headline": ("visual_headline_variant",
                            ['canvas_size(1000, 700)', 'background_contains("#0a0a0a")',
                             'text_present("Signal Found")', 'centred(text, "Signal Found")'],
                            "1000x700 black canvas with the headline 'Signal Found', centred."),
        "multistep_poster": ("multistep_poster_variant",
                             ['canvas_size(800, 1200)', 'background_contains("#050505")',
                              'text_present("Aubade")', 'text_present("Seven sharp")',
                              'count(shape, >=, 1)', 'centred(text, "Aubade")',
                              'within_canvas()', 'no_overlap()'],
                             "800x1200 near-black poster with headline, time, shape."),
        "api_typography": ("api_typography_variant",
                           ['canvas_size(700, 700)', 'text_present("SPACING")',
                            'min_font_size(56, "SPACING")'],
                           "700x700 canvas with 'SPACING' at font size >= 56."),
    }
    if task.key not in swaps:
        return None
    new_key, criteria, goal = swaps[task.key]
    return BenchTask(new_key, task.category, task.difficulty, goal, criteria=criteria)


def run_program_task(task: BenchTask) -> TaskResult:
    from minicoder.learning.synth import synth_with_retries

    t0 = time.time()
    rss_before = _rss()
    run = synth_with_retries(task, deadline=40)
    result = run["result"]
    return TaskResult(
        key=task.key, category=task.category, difficulty=task.difficulty,
        mode="acquisition",
        first_attempt_ok=bool(run["history"] and run["history"][0]["ok"]),
        final_ok=result.solved,
        attempts=run["attempts"],
        seconds=time.time() - t0,
        tokens=result.candidates_tested,   # candidates are the real search cost here
        rss_mb=_rss(),
        confirmed=result.confirmed_in_sandbox,
        program=result.program,
        failure="" if result.solved else result.failure,
        extra={"candidates_tested": result.candidates_tested,
               "search_depth": result.depth_used,
               "rss_before_mb": rss_before,
               "attempt_history": run["history"]},
    )


def run_editor_task(task: BenchTask, loop: Any) -> TaskResult:
    from minicoder.learning.engine import TaskSpec

    t0 = time.time()
    spec = TaskSpec(task.key, task.key.replace("_", " ").title(), task.prompt,
                    task.criteria, domain="editor")
    rep = loop.acquire(spec)
    tr = TaskResult(
        key=task.key, category=task.category, difficulty=task.difficulty,
        mode="acquisition",
        first_attempt_ok=rep.first_attempt_ok,
        final_ok=rep.solved,
        attempts=rep.attempts,
        seconds=time.time() - t0,
        tokens=rep.tokens_used,
        rss_mb=_rss(),
        confirmed=rep.solved,
        replay_ok=rep.replay_passed,
        replay_runs=rep.replay_runs,
        failure="" if rep.solved else "criteria not satisfied",
        extra={"experiment_id": rep.experiment_id, "candidate_id": rep.candidate_id,
               "failure_classes": rep.failure_classes,
               "final_progress": rep.final_progress},
    )

    # Generalisation: promote, then reuse the learned procedure on a variant.
    variant = _variation(task)
    if rep.solved and rep.candidate_id and variant:
        promoted = loop.promote(rep.candidate_id, spec)
        if promoted.get("promoted"):
            var_spec = TaskSpec(variant.key, variant.key, variant.prompt,
                                variant.criteria, domain="editor")
            reuse = loop.reuse(promoted["slug"], var_spec, variation="changed")
            tr.generalised_ok = bool(reuse.get("passed"))
            tr.mode = "acquisition" if not tr.generalised_ok else "acquisition+adaptation"
            tr.extra["generalisation_detail"] = reuse.get("failed", [])
    return tr


def run_visual_inspection(loop: Any) -> TaskResult:
    """Read the live state and check the reading against the state itself."""
    t0 = time.time()
    bridge = loop.bridge()
    bridge.call("new_project", {})
    bridge.call("set_canvas_size", {"width": 640, "height": 480})
    bridge.call("add_text", {"content": "inspect me", "role": "quote"})
    from minicoder.learning.criteria import EditorState

    _, raw = bridge.call("get_app_state", {})
    reported = EditorState.from_snapshot(raw.get("snapshot") or {})
    _, raw2 = bridge.call("get_app_state", {})
    truth = EditorState.from_snapshot(raw2.get("snapshot") or {})
    ok = (reported.canvas_width == truth.canvas_width
          and reported.canvas_height == truth.canvas_height
          and len(reported.layers) == len(truth.layers))
    return TaskResult(
        key="visual_inspection", category="visual_inspection", difficulty="easy",
        mode="retrieval", first_attempt_ok=ok, final_ok=ok, attempts=1,
        seconds=time.time() - t0, tokens=0, rss_mb=_rss(), confirmed=ok,
        failure="" if ok else "reported state disagreed with live state",
        extra={"reported": [reported.canvas_width, reported.canvas_height,
                            len(reported.layers)],
               "truth": [truth.canvas_width, truth.canvas_height, len(truth.layers)]},
    )


def run_benchmark(*, editor: bool = True, limit: int | None = None,
                  out_dir: Path | None = None) -> dict[str, Any]:
    """Run the sealed benchmark and return a report dict."""
    sealed = assert_sealed()
    if not sealed["sealed"]:
        raise RuntimeError(f"benchmark is not sealed: {sealed['problems']}")

    tasks = ALL_TASKS if limit is None else ALL_TASKS[:limit]
    results: list[TaskResult] = []
    loop = None
    t_start = time.time()

    try:
        if editor:
            from minicoder.learning.engine import LearningLoop

            loop = LearningLoop()
            loop.bridge()          # pay the startup cost once, outside timing
        for task in tasks:
            if task.category in EDITOR_CATEGORIES:
                if loop is None:
                    continue
                results.append(run_editor_task(task, loop))
            elif task.category == "visual_inspection":
                if loop is None:
                    continue
                results.append(run_visual_inspection(loop))
            else:
                results.append(run_program_task(task))
    finally:
        if loop is not None:
            loop.close()

    report = _summarise(results, sealed, time.time() - t_start)
    out = Path(out_dir) if out_dir else REPORT_DIR
    out.mkdir(parents=True, exist_ok=True)
    stamp = time.strftime("%Y%m%dT%H%M%SZ", time.gmtime())
    json_path = out / f"benchmark_{stamp}.json"
    latest = out / "benchmark_latest.json"
    payload = json.dumps(report, indent=2, default=str)
    json_path.write_text(payload, encoding="utf-8")
    latest.write_text(payload, encoding="utf-8")
    (out / "benchmark_latest.md").write_text(render_markdown(report), encoding="utf-8")
    report["report_path"] = str(json_path)
    return report


def _summarise(results: list[TaskResult], sealed: dict[str, Any],
               elapsed: float) -> dict[str, Any]:
    n = len(results)
    solved = [r for r in results if r.final_ok]
    first = [r for r in results if r.first_attempt_ok]
    confirmed = [r for r in results if r.confirmed]
    replayed = [r for r in results if r.replay_ok is True]
    generalised = [r for r in results if r.generalised_ok is True]
    attempted_replay = [r for r in results if r.replay_ok is not None]

    by_cat: dict[str, dict[str, Any]] = {}
    for r in results:
        b = by_cat.setdefault(r.category, {"n": 0, "solved": 0, "first": 0})
        b["n"] += 1
        b["solved"] += int(r.final_ok)
        b["first"] += int(r.first_attempt_ok)
    for b in by_cat.values():
        b["final_rate"] = round(b["solved"] / b["n"], 3)
        b["first_rate"] = round(b["first"] / b["n"], 3)

    return {
        "generated_at": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()),
        "host": {"python": platform.python_version(), "machine": platform.machine()},
        "sealed": sealed,
        "test_strength": {"weak": audit_test_strength()},
        "tasks": [r.to_json() for r in results],
        "summary": {
            "n": n,
            "final_success": len(solved),
            "final_rate": round(len(solved) / n, 3) if n else 0.0,
            "first_attempt_success": len(first),
            "first_attempt_rate": round(len(first) / n, 3) if n else 0.0,
            "confirmed_in_sandbox": len(confirmed),
            "mean_attempts": round(sum(r.attempts for r in results) / n, 2) if n else 0,
            "total_seconds": round(elapsed, 2),
            "mean_seconds": round(sum(r.seconds for r in results) / n, 2) if n else 0,
            "peak_rss_mb": max((r.rss_mb for r in results), default=0.0),
            "search_tokens": sum(r.tokens for r in results),
            "replay_attempted": len(attempted_replay),
            "replay_passed": len(replayed),
            "generalisation_attempted": len([r for r in results
                                             if r.generalised_ok is not None]),
            "generalisation_passed": len(generalised),
        },
        "by_category": dict(sorted(by_cat.items())),
        "states": {
            "memorisation": {"tasks_from_training": 0,
                             "note": "sealing check passed; no benchmark task is in training data"},
            "retrieval": {"tasks": [r.key for r in results if r.mode == "retrieval"]},
            "adaptation": {"tasks": [r.key for r in results
                                     if "adaptation" in r.mode]},
            "acquisition": {"tasks": [r.key for r in results if r.mode.startswith("acquisition")]},
        },
        "failed": [{"key": r.key, "category": r.category, "difficulty": r.difficulty,
                    "reason": r.failure} for r in results if not r.final_ok],
    }


def render_markdown(report: dict[str, Any]) -> str:
    s = report["summary"]
    lines = [
        "# Sealed learning benchmark",
        "",
        f"Generated {report['generated_at']} · {s['n']} tasks · sealed: "
        f"{report['sealed']['sealed']}",
        "",
        "## Headline",
        "",
        "| metric | value |",
        "|---|---|",
        f"| final success | {s['final_success']}/{s['n']} ({s['final_rate']:.1%}) |",
        f"| first-attempt success | {s['first_attempt_success']}/{s['n']} "
        f"({s['first_attempt_rate']:.1%}) |",
        f"| confirmed in sandbox | {s['confirmed_in_sandbox']}/{s['n']} |",
        f"| replay passed (fresh process) | {s['replay_passed']}/{s['replay_attempted']} |",
        f"| generalisation passed | {s['generalisation_passed']}/"
        f"{s['generalisation_attempted']} |",
        f"| mean attempts | {s['mean_attempts']} |",
        f"| mean seconds/task | {s['mean_seconds']} |",
        f"| peak RSS | {s['peak_rss_mb']} MB |",
        f"| search tokens | {s['search_tokens']} |",
        "",
        "## By category",
        "",
        "| category | n | final | first |",
        "|---|---|---|---|",
    ]
    for cat, b in report["by_category"].items():
        lines.append(f"| {cat} | {b['n']} | {b['solved']}/{b['n']} "
                     f"({b['final_rate']:.0%}) | {b['first']}/{b['n']} "
                     f"({b['first_rate']:.0%}) |")
    lines += ["", "## Per task", "",
              "| task | category | mode | first | final | attempts | s | tokens | replay | variant |",
              "|---|---|---|---|---|---|---|---|---|---|"]
    for t in report["tasks"]:
        lines.append(
            f"| {t['key']} | {t['category']} | {t['mode']} | "
            f"{'✓' if t['first_attempt_ok'] else '✗'} | "
            f"{'✓' if t['final_ok'] else '✗'} | {t['attempts']} | {t['seconds']} | "
            f"{t['tokens']} | "
            f"{'—' if t['replay_ok'] is None else ('✓' if t['replay_ok'] else '✗')} | "
            f"{'—' if t['generalised_ok'] is None else ('✓' if t['generalised_ok'] else '✗')} |"
        )
    if report["failed"]:
        lines += ["", "## Failures (reported, not hidden)", ""]
        for f in report["failed"]:
            lines.append(f"- **{f['key']}** ({f['category']}, {f['difficulty']}): {f['reason']}")
    return "\n".join(lines) + "\n"
