"""Planning: search over tool sequences, driven by criteria and failure feedback.

This is deliberately *not* a template. The old agent mapped keywords to a fixed
tool sequence with a regex table, which is why it extracted nothing from novel
instructions. Here:

1. Criteria are parsed into *requirements* (what must exist in the world).
2. For each requirement, tool discovery searches the live catalogue for tools
   whose own descriptions match — the planner never assumes a tool name.
3. Arguments are derived from the requirement's parameters and the current
   state (e.g. the string inside ``text_present("SALE")`` becomes the content
   of an ``add_text`` call; the canvas size comes from ``canvas_size(...)``).
4. Steps are executed one at a time and criterion progress is measured after
   each. A step that makes no progress is undone and the next candidate is tried.
5. Failures are classified and repaired: unknown tool names are resolved through
   discovery, wrong arguments are corrected from the error, wrong values get a
   corrective step.

The planner can fail. When it does, the failure is recorded with its class, and
that record is what makes the next attempt different.
"""

from __future__ import annotations

import re
from dataclasses import dataclass, field
from typing import Any

from minicoder.learning.criteria import (
    CriterionResult,
    EditorState,
    evaluate_editor_criteria,
    parse_editor_criterion,
    progress,
)
from minicoder.learning.discovery import ToolIndex

# Phase 5: the planner is in-process operator code (CLI acquisition or a granted
# sleep cycle).  It presents an internal context instead of bypassing the guard.
from minicoder.security import internal_context as _internal_context

_PLANNER_AUTH = _internal_context("learning.planner")


# Priority order for satisfying requirements: establish the canvas, then the
# background, then content, then arrangement. This is a *search heuristic*, not
# a solution — the tools and arguments are still discovered per requirement.
_PRIORITY = {
    "canvas_size": 0,
    "background_contains": 1,
    "text_present": 2,
    "text_exact": 2,
    "count": 3,
    "min_font_size": 4,
    "layer_property": 4,
    "centred": 5,
    "centered": 5,
    "within_canvas": 6,
    "no_overlap": 6,
}

# What each requirement kind needs, expressed as words to search the catalogue
# with. These are *queries*, not tool names: discovery decides which tool fits.
_REQUIREMENT_QUERIES = {
    "canvas_size": "resize canvas size dimensions artboard",
    "background_contains": "background colour fill canvas",
    "text_present": "add text layer content words",
    "text_exact": "add text layer content words",
    "count": "add shape layer element",
    "min_font_size": "font size typography text",
    "layer_property": "set style typography layer property",
    "centred": "align centre horizontal position",
    "centered": "align centre horizontal position",
    "within_canvas": "translate move layer offset position coordinates",
    "no_overlap": "translate move layer offset spacing position",
}


@dataclass
class Requirement:
    kind: str
    text: str
    params: list[Any] = field(default_factory=list)
    satisfied: bool = False
    detail: str = ""

    @property
    def priority(self) -> int:
        return _PRIORITY.get(self.kind, 3)

    def query(self) -> str:
        base = _REQUIREMENT_QUERIES.get(self.kind, self.kind.replace("_", " "))
        extra = " ".join(str(p) for p in self.params if isinstance(p, str))
        return f"{base} {extra}".strip()


def parse_requirements(criteria: list[str]) -> list[Requirement]:
    reqs: list[Requirement] = []
    for text in criteria:
        m = re.match(r"^\s*([a-z_]+)\s*\((.*)\)\s*$", text, re.S)
        if not m:
            continue
        from minicoder.learning.criteria import _args

        reqs.append(Requirement(kind=m.group(1), text=text, params=_args(m.group(2))))
    reqs.sort(key=lambda r: (r.priority, r.text))
    return reqs



def partial_credit(reqs: list[Requirement], state: EditorState) -> float:
    """Search heuristic: how close is the world to satisfying each requirement?

    Boolean success is not enough to guide search. ``count(shape, >=, 2)`` scores
    0 until two shapes exist, so the first shape looked like no progress and was
    reverted — a deadlock, measured on ``tool_discovery_shape``. Partial credit
    makes the first shape worth something, which is what lets the greedy loop
    reach the target.
    """
    if not reqs:
        return 0.0
    scores: list[float] = []
    for req in reqs:
        try:
            pred = parse_editor_criterion(req.text)
            passed, _ = pred(state)
            if passed:
                scores.append(1.0)
                continue
        except Exception:
            scores.append(0.0)
            continue
        # Not satisfied: award partial credit where a measure exists.
        if req.kind == "count" and len(req.params) >= 3:
            want = float(req.params[2])
            pool = state.of_type(str(req.params[0])) if req.params[0] else state.layers
            got = len(pool)
            scores.append(min(got / want, 0.95) if want > 0 else 0.0)
        elif req.kind == "min_font_size" and req.params:
            want = float(req.params[0])
            pool = state.of_type("text")
            got = max((float(l.get("size") or 0) for l in pool), default=0.0)
            scores.append(min(got / want, 0.95) if want > 0 else 0.0)
        elif req.kind == "within_canvas":
            inside = 0
            for layer in state.layers:
                lx, ly = float(layer.get("x") or 0), float(layer.get("y") or 0)
                lw, lh = float(layer.get("w") or 0), float(layer.get("h") or 0)
                if (lx >= -2 and ly >= -2
                        and (not state.canvas_width or lx + lw <= state.canvas_width + 2)
                        and (not state.canvas_height or ly + lh <= state.canvas_height + 2)):
                    inside += 1
            scores.append(min(inside / len(state.layers), 0.95) if state.layers else 0.0)
        elif req.kind == "no_overlap":
            texts = state.of_type("text")
            total = len(texts) * (len(texts) - 1) // 2
            if total <= 0:
                scores.append(1.0)
            else:
                clashes = 0
                for i in range(len(texts)):
                    for j in range(i + 1, len(texts)):
                        a, b = texts[i], texts[j]
                        ax, ay = float(a.get("x") or 0), float(a.get("y") or 0)
                        aw, ah = float(a.get("w") or 0), float(a.get("h") or 0)
                        bx, by = float(b.get("x") or 0), float(b.get("y") or 0)
                        bw, bh = float(b.get("w") or 0), float(b.get("h") or 0)
                        if (ax < bx + bw and bx < ax + aw
                                and ay < by + bh and by < ay + ah):
                            clashes += 1
                scores.append(min(1.0 - clashes / total, 0.95))
        elif req.kind == "text_present" and req.params:
            # An empty canvas gets no credit; a near-miss text gets some.
            scores.append(0.0)
        else:
            scores.append(0.0)
    return sum(scores) / len(scores)


class SearchPlanner:
    """Greedy best-first construction with undo-based backtracking."""

    def __init__(self, index: ToolIndex, *, max_backtracks: int = 6) -> None:
        self.index = index
        self.max_backtracks = max_backtracks
        self.decisions: list[dict[str, Any]] = []   # audit trail of every choice

    # ------------------------------------------------------------ arg filling
    def _derive_args(self, tool_name: str, req: Requirement, state: EditorState) -> dict[str, Any]:
        """Fill a tool's arguments from the requirement and the current state.

        Only arguments the tool actually declares are produced, and required
        ones are always filled. Values come from the requirement's parameters
        or from the observed state — never from a stored solution.
        """
        tool = self.index.get(tool_name)
        if tool is None:
            return {}
        declared = {p.name: p for p in tool.params}
        args: dict[str, Any] = {}
        strings = [p for p in req.params if isinstance(p, str)]
        numbers = [p for p in req.params if isinstance(p, (int, float))]

        def pick(*names: str) -> str | None:
            for n in names:
                if n in declared:
                    return n
            return None

        if req.kind == "canvas_size" and len(numbers) >= 2:
            for name, val in (("width", numbers[0]), ("height", numbers[1])):
                if name in declared:
                    args[name] = int(val)
        elif req.kind in ("text_present", "text_exact") and strings:
            name = pick("content", "text", "value")
            if name:
                args[name] = strings[0]
            role = pick("role")
            if role:
                args[role] = "quote"
            # add_text drops every layer at the same default position, so a
            # second text layer overlaps the first and breaks no_overlap().
            # Derive a position below the lowest existing text instead.
            existing = state.of_type("text")
            if existing and "x" in declared and "y" in declared:
                lowest = max(float(l.get("y") or 0) + float(l.get("h") or 0) for l in existing)
                args["x"] = int(min(float(l.get("x") or 0) for l in existing))
                args["y"] = int(lowest + 24)
        elif req.kind == "background_contains" and strings:
            name = pick("color", "colour", "value", "background")
            if name:
                args[name] = strings[0]
        elif req.kind == "count" and strings:
            name = pick("shape", "kind", "type")
            if name:
                choices = declared[name].choices or []
                wanted = strings[0]
                if choices:
                    # Prefer an exact match; else the first stated kind. This is
                    # how the invalid shape='shape' was eliminated.
                    args[name] = wanted if wanted in choices else choices[0]
                else:
                    args[name] = wanted
            # place it somewhere sensible inside the canvas
            for pname, val in (("x", 40), ("y", 40), ("width", 120), ("height", 120)):
                if pname in declared:
                    args[pname] = val
        elif req.kind == "min_font_size" and numbers:
            name = pick("size", "fontSize", "font_size")
            if name:
                args[name] = float(numbers[0])
            if strings:
                cname = pick("content", "text")
                if cname:
                    args[cname] = strings[0]
        elif req.kind in ("centred", "centered"):
            name = pick("align", "alignment", "mode")
            if name:
                choices = declared[name].choices or []
                args[name] = "hcenter" if (not choices or "hcenter" in choices) else choices[0]
            if strings:
                tname = pick("textContains", "nameContains", "content")
                if tname:
                    args[tname] = strings[0]
        elif req.kind == "within_canvas":
            # Derive the movement needed from the observed overflow, rather than
            # hoping a default offset helps. Repair could not fix the aspect-ratio
            # variant without this (measured: within_canvas stayed failed).
            # A single shift must resolve the *dominant* overflow. Using max()
            # against a zero start discarded negative (right/bottom) shifts
            # entirely, so the derived offset was always 0 (measured bug).
            def _shift(lo_edges, hi_edges, extent):
                bottom = max(hi_edges) if hi_edges else None
                if extent and bottom is not None and bottom > extent:
                    return extent - bottom
                top = min(lo_edges) if lo_edges else 0.0
                return -top if top < 0 else 0.0

            overflow_x = _shift(
                [float(l.get("x") or 0) for l in state.layers],
                [float(l.get("x") or 0) + float(l.get("w") or 0) for l in state.layers],
                state.canvas_width,
            )
            overflow_y = _shift(
                [float(l.get("y") or 0) for l in state.layers],
                [float(l.get("y") or 0) + float(l.get("h") or 0) for l in state.layers],
                state.canvas_height,
            )
            if "dx" in declared:
                args["dx"] = float(overflow_x)
            if "dy" in declared:
                args["dy"] = float(overflow_y)
            # Move only the layers that are actually outside. Translating every
            # layer pushed in-bounds layers out and made the criterion worse
            # (measured: the repair was rejected and the variant failed).
            offenders = []
            for layer in state.layers:
                lx, ly = float(layer.get("x") or 0), float(layer.get("y") or 0)
                lw, lh = float(layer.get("w") or 0), float(layer.get("h") or 0)
                if (lx < -2 or ly < -2
                        or (state.canvas_width and lx + lw > state.canvas_width + 2)
                        or (state.canvas_height and ly + lh > state.canvas_height + 2)):
                    if layer.get("id"):
                        offenders.append(layer["id"])
            if "ids" in declared and offenders:
                args["ids"] = offenders
            elif "all" in declared and not offenders:
                args["all"] = True
        elif req.kind == "no_overlap":
            texts = state.of_type("text")
            moved = False
            for i in range(len(texts)):
                for j in range(i + 1, len(texts)):
                    a, b = texts[i], texts[j]
                    ax, ay = float(a.get("x") or 0), float(a.get("y") or 0)
                    aw, ah = float(a.get("w") or 0), float(a.get("h") or 0)
                    bx, by = float(b.get("x") or 0), float(b.get("y") or 0)
                    bw, bh = float(b.get("w") or 0), float(b.get("h") or 0)
                    if ax < bx + bw and bx < ax + aw and ay < by + bh and by < ay + ah:
                        gap = 24.0
                        dy = (ay + ah + gap) - by      # push b below a
                        if "dy" in declared:
                            args["dy"] = dy
                        if "dx" in declared:
                            args["dx"] = 0.0
                        if "ids" in declared and b.get("id"):
                            args["ids"] = [b["id"]]
                        moved = True
                        break
                if moved:
                    break
        elif req.kind == "layer_property" and len(req.params) >= 3:
            prop, want = str(req.params[1]), req.params[2]
            name = pick(prop, "property", "value")
            if name:
                args[name] = want
            if len(strings) >= 3:
                tname = pick("textContains", "nameContains")
                if tname:
                    args[tname] = strings[-1]

        # Fill anything still required with a neutral default rather than failing.
        for p in tool.params:
            if p.required and p.name not in args:
                args[p.name] = {"number": 0, "integer": 0, "boolean": False,
                                "array": [], "object": {}}.get(p.type, "")
        return args

    def candidates_for(self, req: Requirement, *, limit: int = 4) -> list[str]:
        """Tools worth trying for this requirement, best first."""
        ranked = self.index.search(req.query(), limit=limit + 3)
        names = [t.name for _, t in ranked if not self.index.is_read_only(t.name)][:limit]
        # The tool that creates text is the one whose name says so. Only that
        # one is promoted — promoting a decorative tool here made the planner
        # add quote marks forever (measured).
        if req.kind in ("text_present", "text_exact"):
            if "add_text" in self.index.tools and "add_text" not in names:
                names.insert(0, "add_text")
            if "add_text" in names:
                # Creation first: set_text_content renames an existing layer,
                # which "works" only for the task it was found on.
                names = ["add_text"] + [n for n in names if n != "add_text"]
        return names[:limit]

    # --------------------------------------------------------------- planning
    def repair(self, criteria: list[str], bridge: Any, *, only: list[str] | None = None,
               budget_steps: int = 20) -> dict[str, Any]:
        """Fix only the criteria that currently fail, without starting over.

        This is what makes a reused procedure *adapt* rather than merely
        substitute: a procedure found on a 720x960 canvas can be re-flown on a
        1024x768 one, and the layers that no longer fit are corrected here.
        """
        return self.plan(criteria, bridge, budget_steps=budget_steps,
                         reset=False, only=only)

    def plan(self, criteria: list[str], bridge: Any, *, budget_steps: int = 40,
             reset: bool = True, only: list[str] | None = None) -> dict[str, Any]:
        """Build a tool sequence by executing and measuring as we go.

        Each candidate step is executed for real, criterion progress is measured,
        and only a strict improvement is kept. A candidate that did not improve is
        reverted *if and only if it changed the world* — an earlier version undid
        unconditionally, which popped the preceding successful step and silently
        destroyed progress (measured: the canvas resize was rolled back and every
        later criterion failed).
        """
        self.decisions = []
        reqs = parse_requirements(criteria)
        if only is not None:
            wanted = set(only)
            reqs = [r for r in reqs if r.text in wanted]
        plan: list[dict[str, Any]] = []
        if reset:
            bridge.call("new_project", {}, auth=_PLANNER_AUTH)
        state = self._state(bridge)
        results = evaluate_editor_criteria(criteria, state)
        best = partial_credit(reqs, state)
        steps = 0
        backtracks = 0

        # Declare the canvas even when the default happens to match, so the
        # stored procedure carries its own assumptions and can be reused at a
        # different size.
        canvas_req = next((r for r in reqs if r.kind == "canvas_size"
                           and len(r.params) >= 2), None)
        if canvas_req is not None and reset:
            args = {"width": int(canvas_req.params[0]), "height": int(canvas_req.params[1])}
            outcome = self._execute(bridge, "set_canvas_size", args)
            if outcome["ok"]:
                plan.append({"tool": "set_canvas_size", "args": args})
                steps += 1
                state = self._state(bridge)
                results = evaluate_editor_criteria(criteria, state)
                best = partial_credit(reqs, state)

        while best < 1.0 and steps < budget_steps:
            unmet = self._unmet(reqs, results)
            if not unmet:
                break
            made_progress = False
            for req in unmet:
                # Several tools can satisfy one requirement, and one requirement
                # can need several calls (count >= 2 needs two adds). Try the
                # candidates for this requirement; on success restart the outer
                # scan so a newly-unblocked requirement can be served.
                signature_before = self._signature(state)
                for tool_name in self.candidates_for(req):
                    if steps >= budget_steps:
                        break
                    steps += 1
                    args = self._derive_args(tool_name, req, state)
                    outcome = self._execute(bridge, tool_name, args)
                    new_state = self._state(bridge)
                    new_results = evaluate_editor_criteria(criteria, new_state)
                    new_progress = partial_credit(reqs, new_state)
                    changed = self._signature(new_state) != signature_before
                    self.decisions.append({
                        "requirement": req.text, "tool": tool_name, "args": args,
                        "ok": outcome["ok"], "progress": round(new_progress, 3),
                        "changed_state": changed, "error": outcome.get("error", "")[:160],
                    })
                    if outcome["ok"] and new_progress > best:
                        plan.append({"tool": tool_name, "args": args})
                        state, results, best = new_state, new_results, new_progress
                        made_progress = True
                        break
                    if changed:
                        # Only revert work that actually happened; otherwise undo
                        # would eat the previous accepted step.
                        bridge.call("undo", {}, auth=_PLANNER_AUTH)
                        backtracks += 1
                        state = self._state(bridge)
                        if self._signature(state) != signature_before:
                            self.decisions.append({
                                "corruption": True,
                                "expected": signature_before,
                                "actual": self._signature(state),
                            })
                            state = self._state(bridge)
                if made_progress:
                    break
            if not made_progress:
                stuck = [r.text for r in self._unmet(reqs, results)]
                self.decisions.append({"stuck": True, "unmet": stuck,
                                       "progress": round(best, 3)})
                break

        satisfied = all(r.passed for r in results) if results else False
        return {"plan": plan, "state": state, "results": results,
                "progress": progress(results), "search_score": best,
                "steps": steps, "backtracks": backtracks,
                "satisfied": satisfied}

    @staticmethod
    def _unmet(reqs: list[Requirement], results: list[CriterionResult]) -> list[Requirement]:
        """Requirements not yet satisfied, matched by criterion text.

        reqs is priority-sorted while results follow criteria order, so zipping
        them pairs the wrong requirement with the wrong result (measured bug).
        """
        by_text = {r.criterion: r for r in results}
        return [r for r in reqs
                if not by_text.get(r.text, CriterionResult(r.text, True)).passed]

    @staticmethod
    def _signature(state: EditorState) -> tuple:
        return (
            state.canvas_width,
            state.canvas_height,
            str(state.background),
            len(state.layers),
            tuple(sorted(str(l.get("text") or "") for l in state.layers)),
        )

    # --------------------------------------------------------------- helpers
    @staticmethod
    def _state(bridge: Any) -> EditorState:
        _, raw = bridge.call("get_app_state", {}, auth=_PLANNER_AUTH)
        return EditorState.from_snapshot(raw.get("snapshot") or {})

    @staticmethod
    def _execute(bridge: Any, tool: str, args: dict[str, Any]) -> dict[str, Any]:
        try:
            result, _ = bridge.call(tool, args, auth=_PLANNER_AUTH)
            if isinstance(result, dict) and result.get("ok") is False:
                return {"ok": False, "error": str(result.get("error") or result.get("summary") or "")}
            return {"ok": True}
        except Exception as exc:
            return {"ok": False, "error": str(exc)}


def classify_failure(step: dict[str, Any], outcome: dict[str, Any],
                     index: ToolIndex) -> str:
    """Map an observed failure onto the ledger's taxonomy."""
    tool = step.get("tool", "")
    if tool not in index.tools:
        return "unknown_tool"
    err = (outcome.get("error") or "").lower()
    if any(k in err for k in ("unknown argument", "missing", "required", "invalid", "unexpected")):
        return "wrong_args"
    if err:
        return "wrong_value"
    return "wrong_value"


def repair(step: dict[str, Any], failure_class: str, index: ToolIndex) -> dict[str, Any] | None:
    """Produce a corrected step for a classified failure, or None if unrepairable."""
    if failure_class == "unknown_tool":
        tool, how = index.resolve(step.get("tool", ""))
        if tool is None:
            return None
        return {"tool": tool.name, "args": dict(step.get("args") or {}), "repaired": how}
    if failure_class == "wrong_args":
        tool = index.get(step.get("tool", ""))
        if tool is None:
            return None
        # Drop arguments the tool does not declare; keep the rest.
        declared = {p.name for p in tool.params}
        kept = {k: v for k, v in (step.get("args") or {}).items() if k in declared}
        for p in tool.params:
            if p.required and p.name not in kept:
                kept[p.name] = {"number": 0, "integer": 0, "boolean": False,
                                "array": [], "object": {}}.get(p.type, "")
        return {"tool": tool.name, "args": kept, "repaired": "pruned_args"}
    return None
