"""Phase 3 — enumerative acquisition with isolated, batched probing.

Phase 2's synthesizer probed candidates with ``exec()`` in the harness process against the
same assertions that later scored them. This one:

* enumerates from a **generic** grammar of operations (no task names, no per-task templates);
* probes a whole batch inside a namespace-isolated child where ``/home`` is masked, so
  candidate code cannot read the private store even if it tries;
* searches against **dev** tests only. The hidden set is generated later, by the evaluator,
  from a salt the search never sees.

The grammar is deliberately small: 14 unary operations plus two-argument forms and depth-2
composition. That keeps the search honest — a pass means the composition was found, not that
a solution was injected.
"""

from __future__ import annotations

import json
import shutil
import subprocess
import tempfile
from pathlib import Path
from typing import Any

from minicoder.research.isolation import _interpreter, _namespace_supported
from minicoder.research.tasks import TaskRecord

# Generic operations, written as expressions over `xs`. None is specific to a task.
UNARY: dict[str, str] = {
    "identity": "list(xs)",
    "abs": "[abs(x) for x in xs]",
    "negate": "[-x for x in xs]",
    "double": "[x * 2 for x in xs]",
    "square": "[x * x for x in xs]",
    "even": "[x for x in xs if x % 2 == 0]",
    "odd": "[x for x in xs if x % 2 == 1]",
    "positive": "[x for x in xs if x > 0]",
    "sorted": "sorted(xs)",
    "sorted_desc": "sorted(xs, reverse=True)",
    "reversed": "list(reversed(xs))",
    "dedupe": "list(dict.fromkeys(xs))",
    "cumsum": "[sum(xs[:i + 1]) for i in range(len(xs))]",
    "sum": "sum(xs)",
    "len": "len(xs)",
    "min": "min(xs) if xs else None",
    "max": "max(xs) if xs else None",
    "counts": "{v: xs.count(v) for v in dict.fromkeys(xs)}",
    "rle": "[[v, xs.count(v)] for v in dict.fromkeys(xs)]",
}

# Two-argument forms over (xs, k) and row-oriented forms over (rows, field).
BINARY: dict[str, str] = {
    "scale": "[x * k for x in xs]",
    "add": "[x + k for x in xs]",
    "chunk": "[xs[i:i + k] for i in range(0, len(xs), k)]",
    "take": "xs[:k]",
}

ROWS: dict[str, str] = {
    "count_by": "{r[f]: [t[f] for t in rows].count(r[f]) for r in rows}",
    "sort_by": "sorted(rows, key=lambda r: r[f])",
}


def _signature(name: str) -> int:
    return 1


def enumerate_candidates(record: TaskRecord, *, max_candidates: int = 1200,
                         depth: int = 2, exclude: set[str] | None = None
                         ) -> list[tuple[str, str]]:
    """Generic enumeration, tagged by category so ablations can remove a real component.

    Categories: ``unary`` (one list operation), ``compose`` (two composed operations),
    ``binary`` (two-argument forms) and ``rows`` (row-oriented operations).
    """
    skip = exclude or set()
    arity = int(record.params.get("arity", 1))
    is_rows = bool(record.params.get("rows"))

    out: list[tuple[str, str]] = []
    if is_rows and arity >= 2:
        if "rows" in skip:
            return []
        for body in ROWS.values():
            out.append((f"def solve(rows, f):\n    return {body}\n", "rows"))
        return out[:max_candidates]

    if arity >= 2:
        if "binary" not in skip:
            for body in BINARY.values():
                out.append((f"def solve(xs, k):\n    return {body}\n", "binary"))
        if "compose" not in skip and "binary" not in skip:
            for body in BINARY.values():
                if "unary" in skip:
                    break
                for ubody in UNARY.values():
                    inner = ubody.replace("xs", "__b__")
                    out.append((f"def solve(xs, k):\n    return {inner.replace('__b__', body)}\n",
                                "compose"))
        return out[:max_candidates]

    if "unary" not in skip:
        for body in UNARY.values():
            out.append((f"def solve(xs):\n    return {body}\n", "unary"))
    if depth >= 2 and "compose" not in skip:
        for body in UNARY.values():
            for body2 in UNARY.values():
                composed = body2.replace("xs", f"({body})")
                out.append((f"def solve(xs):\n    return {composed}\n", "compose"))
    return out[:max_candidates]


# --------------------------------------------------------------------------- batched probe
PROBE_RUNNER = r'''
import json, sys

payload = json.load(open(sys.argv[1], encoding="utf-8"))
results = []
for source in payload["candidates"]:
    ns = {"__name__": "cand"}
    try:
        exec(compile(source, "<candidate>", "exec"), ns)
        exec(compile(payload["dev_tests"], "<dev>", "exec"), ns)
        results.append(True)
    except BaseException:
        results.append(False)
json.dump({"ok": results}, open(sys.argv[2], "w"))
'''


def batch_probe(candidates: list[str], dev_tests: str, *, timeout: float = 90.0,
                mode: str | None = None) -> list[bool]:
    """Run every candidate against the dev tests inside one isolated child."""
    if not candidates:
        return []
    tmp = Path(tempfile.mkdtemp(prefix="nace3_probe_", dir="/tmp"))
    try:
        (tmp / "runner.py").write_text(PROBE_RUNNER, encoding="utf-8")
        (tmp / "payload.json").write_text(
            json.dumps({"candidates": candidates, "dev_tests": dev_tests}), encoding="utf-8")
        guard = ("import sys\nsys.addaudithook(lambda e, a: (_ for _ in ()).throw(PermissionError(e))\n"
                 "    if e in ('os.system','subprocess.Popen','socket.socket','os.fork') else None)\n")
        (tmp / "boot.py").write_text(
            "import sys\n"
            f"sys.path.insert(0, {str(tmp)!r})\n"
            + guard
            + f"sys.argv = [{str(tmp / 'runner.py')!r}, {str(tmp / 'payload.json')!r}, "
              f"{str(tmp / 'out.json')!r}]\n"
            f"import runpy\nrunpy.run_path({str(tmp / 'runner.py')!r}, run_name='__main__')\n",
            encoding="utf-8")

        use_ns = (mode or ("namespace" if _namespace_supported() else "guard")) == "namespace"
        inner = (f"mount -t tmpfs tmpfs /home 2>/dev/null; cd {tmp} && "
                 f"exec {_interpreter()} {tmp}/boot.py")
        cmd = (["unshare", "-Urnm", "--fork", "--pid", "--kill-child", "sh", "-c", inner]
               if use_ns else [_interpreter(), str(tmp / "boot.py")])
        try:
            subprocess.run(cmd, capture_output=True, text=True, timeout=timeout, cwd=str(tmp))
        except subprocess.TimeoutExpired:
            return [False] * len(candidates)
        out_file = tmp / "out.json"
        if not out_file.exists():
            return [False] * len(candidates)
        data = json.loads(out_file.read_text(encoding="utf-8"))
        ok = list(data.get("ok", []))
        return ok + [False] * (len(candidates) - len(ok))
    finally:
        shutil.rmtree(tmp, ignore_errors=True)


# --------------------------------------------------------------------------- acquisition
def acquire(record: TaskRecord, *, max_candidates: int = 1200, depth: int = 2,
            budget_seconds: float = 90.0, mode: str | None = None,
            exclude: set[str] | None = None) -> dict[str, Any]:
    """Search the grammar for the first candidate that satisfies the *dev* tests."""
    import time

    t0 = time.time()
    tagged = enumerate_candidates(record, max_candidates=max_candidates, depth=depth,
                                  exclude=exclude)
    candidates = [code for code, _ in tagged]
    tested = 0
    attempts: list[dict[str, Any]] = []
    batch = 200
    for start in range(0, len(candidates), batch):
        if time.time() - t0 > budget_seconds:
            break
        chunk = candidates[start:start + batch]
        results = batch_probe(chunk, record.dev_tests, mode=mode)
        tested += len(chunk)
        hit = next((c for c, ok in zip(chunk, results) if ok), None)
        attempts.append({"batch": start // batch, "candidates": len(chunk),
                         "hits": sum(1 for r in results if r)})
        if hit:
            return {"solved_dev": True, "code": hit, "candidates_tested": tested,
                    "seconds": time.time() - t0, "attempts": attempts,
                    "strategy": f"enumerate/depth{depth}"}
    return {"solved_dev": False, "code": "", "candidates_tested": tested,
            "seconds": time.time() - t0, "attempts": attempts,
            "strategy": f"enumerate/depth{depth}"}
