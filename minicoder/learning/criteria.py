"""Machine-checkable success criteria.

A criterion is a requirement stated *independently* of any solution. It is
evaluated against the observed world (editor snapshot, or a Python program's
result) and returns a pass/fail plus the evidence for it. The planner sees the
criterion text — it must know what to aim at — but never a solution.

Two families:

* **editor criteria** — predicates over the bridge's state snapshot
  (canvas, layers, selection). Written as a small DSL so a task author can
  state "a text layer containing the word 'SALE' is horizontally centred"
  without writing code.
* **program criteria** — Python assertions executed against the candidate
  program's namespace in the sandbox.

A criterion that cannot be evaluated is a bug in the task, not a failure of the
system, so evaluation errors are reported as ``error`` rather than ``fail``.
"""

from __future__ import annotations

import ast
import re
from dataclasses import dataclass
from typing import Any

from minicoder.learning.ledger import CriterionResult


# ===================================================================== editor
@dataclass
class EditorState:
    """A normalised view of the editor snapshot the bridge returns."""

    canvas_width: int = 0
    canvas_height: int = 0
    background: Any = None
    layers: list[dict[str, Any]] = None  # type: ignore[assignment]

    def __post_init__(self) -> None:
        if self.layers is None:
            self.layers = []

    @classmethod
    def from_snapshot(cls, snapshot: dict[str, Any]) -> EditorState:
        canvas = snapshot.get("canvas") or {}
        layers = snapshot.get("layers") or []
        return cls(
            canvas_width=int(canvas.get("width") or 0),
            canvas_height=int(canvas.get("height") or 0),
            background=canvas.get("background"),
            layers=[dict(l) for l in layers],
        )

    def of_type(self, type_: str) -> list[dict[str, Any]]:
        return [l for l in self.layers if l.get("type") == type_]

    def with_text(self, needle: str) -> list[dict[str, Any]]:
        return [
            l for l in self.layers
            if l.get("type") == "text" and needle.lower() in str(l.get("text") or "").lower()
        ]

    def centre_x(self, layer: dict[str, Any]) -> float:
        return float(layer.get("x") or 0) + float(layer.get("w") or 0) / 2.0

    def centre_y(self, layer: dict[str, Any]) -> float:
        return float(layer.get("y") or 0) + float(layer.get("h") or 0) / 2.0


def _num(v: Any) -> float:
    try:
        return float(v)
    except (TypeError, ValueError):
        return 0.0


# Each predicate: (description, fn(state) -> (passed, detail))
def _pred_canvas_size(w: int, h: int):
    def fn(s: EditorState):
        ok = s.canvas_width == w and s.canvas_height == h
        return ok, f"canvas is {s.canvas_width}x{s.canvas_height}, wanted {w}x{h}"
    return fn


def _pred_layer_count(type_: str, n: int, op: str = "=="):
    def fn(s: EditorState):
        got = len(s.of_type(type_)) if type_ else len(s.layers)
        ok = {"==": got == n, ">=": got >= n, "<=": got <= n, ">": got > n}[op]
        what = f"{type_} layers" if type_ else "layers"
        return ok, f"{got} {what}, wanted {op} {n}"
    return fn


def _pred_text_present(needle: str):
    def fn(s: EditorState):
        found = s.with_text(needle)
        return bool(found), f"{len(found)} text layer(s) containing {needle!r}"
    return fn


def _pred_text_exact(needle: str):
    def fn(s: EditorState):
        found = [l for l in s.of_type("text") if str(l.get("text") or "").strip() == needle]
        return bool(found), f"{len(found)} text layer(s) exactly {needle!r}"
    return fn


def _pred_centred(type_: str, needle: str = "", tol: float = 8.0):
    def fn(s: EditorState):
        pool = s.with_text(needle) if needle else s.of_type(type_)
        if not pool:
            return False, f"no {type_} layer to centre"
        target = s.canvas_width / 2.0
        best = min(pool, key=lambda l: abs(s.centre_x(l) - target))
        off = abs(s.centre_x(best) - target)
        return off <= tol, f"centre x={s.centre_x(best):.1f}, canvas centre={target:.1f}, off by {off:.1f}"
    return fn


def _pred_within_canvas(tol: float = 2.0):
    def fn(s: EditorState):
        outside = []
        for l in s.layers:
            x, y = _num(l.get("x")), _num(l.get("y"))
            w, h = _num(l.get("w")), _num(l.get("h"))
            if x < -tol or y < -tol or x + w > s.canvas_width + tol or y + h > s.canvas_height + tol:
                outside.append(l.get("name") or l.get("type"))
        return not outside, (f"{len(outside)} layer(s) outside canvas: {outside[:3]}"
                            if outside else "all layers inside canvas")
    return fn


def _pred_no_overlap():
    def fn(s: EditorState):
        texts = s.of_type("text")
        overlaps = []
        for i in range(len(texts)):
            for j in range(i + 1, len(texts)):
                a, b = texts[i], texts[j]
                ax, ay, aw, ah = _num(a.get("x")), _num(a.get("y")), _num(a.get("w")), _num(a.get("h"))
                bx, by, bw, bh = _num(b.get("x")), _num(b.get("y")), _num(b.get("w")), _num(b.get("h"))
                if ax < bx + bw and bx < ax + aw and ay < by + bh and by < ay + ah:
                    overlaps.append((a.get("text", "")[:20], b.get("text", "")[:20]))
        return not overlaps, (f"{len(overlaps)} overlapping text pair(s): {overlaps[:2]}"
                              if overlaps else "no text overlaps")
    return fn


def _pred_background_contains(needle: str):
    def fn(s: EditorState):
        bg = str(s.background or "").lower()
        return needle.lower() in bg, f"background={str(s.background)[:60]!r}"
    return fn


def _pred_layer_property(type_: str, prop: str, want: Any, needle: str = ""):
    def fn(s: EditorState):
        pool = s.with_text(needle) if needle else s.of_type(type_)
        if not pool:
            return False, f"no {type_} layer"
        got = pool[0].get(prop)
        ok = str(got).lower() == str(want).lower()
        return ok, f"{type_}.{prop}={got!r}, wanted {want!r}"
    return fn


def _pred_min_font_size(min_size: float, needle: str = ""):
    def fn(s: EditorState):
        pool = s.with_text(needle) if needle else s.of_type("text")
        if not pool:
            return False, "no text layer"
        got = max(_num(l.get("size")) for l in pool)
        return got >= min_size, f"largest font {got}, wanted >= {min_size}"
    return fn


# DSL:  canvas_size(800, 800) | count(text, >=, 2) | text_present("SALE")
#       centred(text, "SALE") | within_canvas() | no_overlap()
#       background_contains("#1a1a2e") | layer_property(text, align, center, "SALE")
#       min_font_size(48, "SALE") | text_exact("Hello")
_DSL = re.compile(r"^\s*([a-z_]+)\s*\((.*)\)\s*$", re.S)


def _args(text: str) -> list[Any]:
    """Parse the argument list of a DSL call without eval."""
    out: list[Any] = []
    for part in re.split(r",(?![^()]*\))", text):
        part = part.strip()
        if not part:
            continue
        if (part.startswith('"') and part.endswith('"')) or (part.startswith("'") and part.endswith("'")):
            out.append(part[1:-1])
        elif part in (">=", "<=", "==", ">", "<"):
            out.append(part)
        else:
            try:
                out.append(int(part))
            except ValueError:
                try:
                    out.append(float(part))
                except ValueError:
                    out.append(part)
    return out


_BUILDERS = {
    "canvas_size": lambda a: _pred_canvas_size(int(a[0]), int(a[1])),
    "count": lambda a: _pred_layer_count(str(a[0]), int(a[2]), str(a[1])),
    "layer_count": lambda a: _pred_layer_count(str(a[0]), int(a[2]), str(a[1])),
    "text_present": lambda a: _pred_text_present(str(a[0])),
    "text_exact": lambda a: _pred_text_exact(str(a[0])),
    "centred": lambda a: _pred_centred(str(a[0]), str(a[1]) if len(a) > 1 else ""),
    "centered": lambda a: _pred_centred(str(a[0]), str(a[1]) if len(a) > 1 else ""),
    "within_canvas": lambda a: _pred_within_canvas(),
    "no_overlap": lambda a: _pred_no_overlap(),
    "background_contains": lambda a: _pred_background_contains(str(a[0])),
    "layer_property": lambda a: _pred_layer_property(
        str(a[0]), str(a[1]), a[2], str(a[3]) if len(a) > 3 else ""
    ),
    "min_font_size": lambda a: _pred_min_font_size(float(a[0]), str(a[1]) if len(a) > 1 else ""),
}


def parse_editor_criterion(text: str):
    """Compile a DSL criterion into a predicate over EditorState."""
    m = _DSL.match(text)
    if not m:
        raise ValueError(f"unrecognised criterion syntax: {text!r}")
    name, argstr = m.group(1), m.group(2)
    if name not in _BUILDERS:
        raise ValueError(f"unknown criterion {name!r}; known: {sorted(_BUILDERS)}")
    return _BUILDERS[name](_args(argstr))


def evaluate_editor_criteria(criteria: list[str], state: EditorState) -> list[CriterionResult]:
    results: list[CriterionResult] = []
    for text in criteria:
        try:
            pred = parse_editor_criterion(text)
            passed, detail = pred(state)
            results.append(CriterionResult(text, bool(passed), detail))
        except Exception as exc:  # a broken criterion is a task bug, not a system failure
            results.append(CriterionResult(text, False, f"criterion error: {exc}"))
    return results


# ===================================================================== program
def evaluate_program_criteria(criteria: list[str], code: str, *, timeout: float = 10.0) -> list[CriterionResult]:
    """Run assertions against the candidate program in the sandbox.

    Each criterion is a Python expression that must be truthy in the program's
    namespace after execution. The sandbox guard applies, so a program cannot
    pass by reading the answer key off disk.
    """
    from minicoder.tools.sandbox import Sandbox

    sandbox = Sandbox()
    results: list[CriterionResult] = []
    # Execute once, then evaluate each criterion in the resulting namespace.
    harness = code + "\n\n# --- criterion namespace capture ---\n"
    res = sandbox.run_python(harness, timeout=timeout)
    if not res.ok:
        return [CriterionResult(c, False, f"program did not run: {res.stderr.strip()[-200:]}")
                for c in criteria]
    # Re-run with a namespace dump: simplest robust route is to append a
    # serialiser that prints the namespace as JSON.
    dump = (
        code
        + "\n\nimport json as _json\n"
        + "_out = {}\n"
        + "for _k, _v in list(globals().items()):\n"
        + "    if _k.startswith('_'): continue\n"
        + "    try:\n"
        + "        _out[_k] = _json.dumps(_v)\n"
        + "    except Exception:\n"
        + "        pass\n"
        + "print('__NS__' + _json.dumps(_out))\n"
    )
    res2 = sandbox.run_python(dump, timeout=timeout)
    namespace: dict[str, Any] = {}
    for line in res2.stdout.splitlines():
        if line.startswith("__NS__"):
            try:
                namespace = {k: ast.literal_eval(v) if isinstance(v, str) else v
                             for k, v in ast.literal_eval(line[6:]).items()}
            except Exception:
                namespace = {}
            break
    for text in criteria:
        try:
            value = eval(text, {"__builtins__": {}}, namespace)  # noqa: S307 - task-authored
            results.append(CriterionResult(text, bool(value), f"{text} -> {value!r}"[:200]))
        except Exception as exc:
            results.append(CriterionResult(text, False, f"criterion error: {exc}"))
    return results


def all_passed(results: list[CriterionResult]) -> bool:
    return bool(results) and all(r.passed for r in results)


def progress(results: list[CriterionResult]) -> float:
    """Fraction of criteria satisfied — the search heuristic."""
    if not results:
        return 0.0
    return sum(1 for r in results if r.passed) / len(results)
