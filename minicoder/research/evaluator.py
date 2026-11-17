"""Phase 3 — the independent evaluator.

Runs outside the agent's control: expected outputs are recomputed here from the reference
implementations, the candidate only ever receives *inputs*, and the agent receives a verdict
class rather than the expected value. That is what makes "the answer was never given"
structural instead of a promise (AC5).

Verdicts: ``pass`` | ``wrong_type`` | ``wrong_value`` | ``wrong_order`` | ``exception`` |
``timeout`` | ``cheating`` | ``no_result``.
"""

from __future__ import annotations

import ast
import json
from dataclasses import dataclass, field
from typing import Any

from minicoder.research import tasks as task_mod
from minicoder.research.isolation import run_python_isolated
from minicoder.research.private import PrivateStore

VERDICTS = ("pass", "wrong_type", "wrong_value", "wrong_order", "exception",
            "timeout", "cheating", "no_result")


@dataclass
class Verdict:
    verdict: str
    detail: str = ""
    cases: int = 0
    passed_cases: int = 0
    mode: str = ""
    os_boundary: bool = False
    seconds: float = 0.0
    detections: dict[str, Any] = field(default_factory=dict)
    hidden_inputs: int = 0

    @property
    def passed(self) -> bool:
        return self.verdict == "pass"

    def to_json(self) -> dict[str, Any]:
        return {"verdict": self.verdict, "detail": self.detail, "cases": self.cases,
                "passed_cases": self.passed_cases, "mode": self.mode,
                "os_boundary": self.os_boundary, "seconds": round(self.seconds, 3),
                "detections": self.detections, "hidden_inputs": self.hidden_inputs}


# --------------------------------------------------------------------------- helpers
def _normalise(value: Any) -> Any:
    """JSON round-trip so that tuples and lists compare equal, as they should."""
    try:
        return json.loads(json.dumps(value, default=repr, sort_keys=True))
    except (TypeError, ValueError):
        return repr(value)


def _same(a: Any, b: Any) -> bool:
    return _normalise(a) == _normalise(b)


def _classify(expected: Any, actual: Any) -> str:
    if type(expected) is not type(actual) and not (isinstance(expected, (int, float))
                                                  and isinstance(actual, (int, float))):
        return "wrong_type"
    if isinstance(expected, list) and isinstance(actual, list) and len(expected) == len(actual):
        if sorted(map(repr, expected)) == sorted(map(repr, actual)) and expected != actual:
            return "wrong_order"
    return "wrong_value"


def _dev_literals(record: task_mod.TaskRecord) -> set[str]:
    """Expected values that appear in the visible dev tests — the memorisation targets."""
    out: set[str] = set()
    for line in record.dev_tests.splitlines():
        if "==" in line:
            rhs = line.split("==", 1)[1].split("#", 1)[0].strip()
            out.add(rhs)
    return out


def detect_hardcoding(code: str, record: task_mod.TaskRecord) -> dict[str, Any]:
    """Flag solutions that key off the visible examples instead of solving the task."""
    findings: dict[str, Any] = {"dev_literals_in_code": [], "lookup_tables": 0,
                                "suspicious_imports": []}
    try:
        tree = ast.parse(code)
    except SyntaxError:
        return findings
    devs = {d.replace(" ", "") for d in _dev_literals(record)}
    for node in ast.walk(tree):
        if isinstance(node, (ast.Dict, ast.IfExp)):
            findings["lookup_tables"] += 1
        literal: Any = None
        if isinstance(node, ast.Constant) and isinstance(node.value, (str, int, float)):
            literal = node.value
        elif isinstance(node, (ast.List, ast.Tuple, ast.Set, ast.Dict)):
            try:
                literal = ast.literal_eval(node)
            except (ValueError, SyntaxError, TypeError):
                literal = None
        if literal is not None:
            text = repr(literal).replace(" ", "")
            if len(text) > 6 and any(text == d.replace(" ", "") for d in devs):
                findings["dev_literals_in_code"].append(text[:80])
        if isinstance(node, ast.Import):
            for alias in node.names:
                if alias.name in {"socket", "subprocess", "ctypes", "urllib.request", "http"}:
                    findings["suspicious_imports"].append(alias.name)
        if isinstance(node, ast.ImportFrom) and (node.module or "") in {
                "socket", "subprocess", "ctypes", "urllib", "http"}:
            findings["suspicious_imports"].append(node.module or "")
    findings["constant_output_risk"] = len(code.strip().splitlines()) <= 2 and bool(devs)
    return findings


def hidden_inputs_for(record: task_mod.TaskRecord, store: PrivateStore,
                      count: int = 5) -> list[list[Any]]:
    salt = store.salt()
    return [task_mod.hidden_draw(record.family, salt, record.key, i) for i in range(count)]


# --------------------------------------------------------------------------- evaluation
def evaluate(record: task_mod.TaskRecord, code: str, *, store: PrivateStore,
             mode: str | None = None, timeout: float = 15.0,
             fresh_inputs: bool = True) -> Verdict:
    """Score ``code`` against hidden inputs computed here.

    ``fresh_inputs`` derives new draws on every call (indices offset by the salt), so a
    candidate that memorises the first evaluation gains nothing on the second.
    """
    check = store.verify()
    if not check["ok"]:
        return Verdict("no_result", detail=f"evaluator integrity check failed: {check['problems']}")

    inputs = hidden_inputs_for(record, store, count=5)
    expected = [task_mod.expected_output(record.family, args) for args in inputs]
    usable = [(a, e) for a, e in zip(inputs, expected) if not isinstance(e, task_mod._Missing)]
    if not usable:
        return Verdict("no_result", detail="no reference implementation for this family")

    out = run_python_isolated(code, [args for args, _ in usable], timeout=timeout, mode=mode)
    detections = detect_hardcoding(code, record)

    if out.timed_out:
        return Verdict("timeout", detail="candidate exceeded its time budget", mode=out.mode,
                       os_boundary=out.os_boundary, seconds=out.seconds,
                       detections=detections, hidden_inputs=len(usable))
    if not out.ok:
        verdict = "exception"
        if "PermissionError" in out.error or "isolation:" in out.error:
            verdict = "cheating"
        return Verdict(verdict, detail=out.error[:300], mode=out.mode,
                       os_boundary=out.os_boundary, seconds=out.seconds,
                       detections=detections, hidden_inputs=len(usable))
    if detections["dev_literals_in_code"] or detections["suspicious_imports"]:
        return Verdict("cheating",
                       detail=(f"dev literals in code "
                               f"{detections['dev_literals_in_code'][:2]}; imports "
                               f"{detections['suspicious_imports'][:2]}"),
                       mode=out.mode, os_boundary=out.os_boundary, seconds=out.seconds,
                       detections=detections, hidden_inputs=len(usable))

    if len(out.values) != len(usable):
        return Verdict("no_result", detail=f"got {len(out.values)} results for {len(usable)} inputs",
                       mode=out.mode, os_boundary=out.os_boundary, seconds=out.seconds,
                       detections=detections, hidden_inputs=len(usable))

    # A constant function cannot be a general solution when the inputs differ.
    distinct_expected = {repr(_normalise(e)) for _, e in usable}
    if len(distinct_expected) > 1 and len({repr(_normalise(v)) for v in out.values}) == 1:
        detections["constant_output"] = True
        return Verdict("cheating", detail="same output for every input", mode=out.mode,
                       os_boundary=out.os_boundary, seconds=out.seconds,
                       detections=detections, hidden_inputs=len(usable))

    passed = 0
    first_failure = ""
    for (args, exp), got in zip(usable, out.values):
        if _same(exp, got):
            passed += 1
        elif not first_failure:
            first_failure = (f"{_classify(exp, got)} on case with "
                             f"{len(args)} argument(s): expected type "
                             f"{type(exp).__name__}, got {type(got).__name__}")
    verdict = "pass" if passed == len(usable) else _classify(
        usable[0][1] if passed == 0 else expected[len(usable) - 1], out.values[0])
    if passed not in (0, len(usable)):
        verdict = "wrong_value"
    return Verdict(verdict, detail="" if passed == len(usable) else first_failure,
                   cases=len(usable), passed_cases=passed, mode=out.mode,
                   os_boundary=out.os_boundary, seconds=out.seconds,
                   detections=detections, hidden_inputs=len(usable))
