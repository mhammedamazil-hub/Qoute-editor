"""Tool discovery: find out what the world actually offers before planning.

The brief requires the system to "inspect available tools and their actual
interfaces". The old agent hardcoded a regex table of keywords and assumed the
tool names; this module instead asks the editor for its live catalogue and then
answers questions about it from what came back.

Everything here is derived from the bridge at runtime. There is no embedded list
of tool names: if the editor gains or loses a tool, discovery reflects it.
"""

from __future__ import annotations

import json
import re
from dataclasses import dataclass, field
from difflib import SequenceMatcher, get_close_matches
from typing import Any


@dataclass
class ToolParam:
    name: str
    type: str = "string"
    required: bool = False
    description: str = ""
    choices: list[str] = None  # type: ignore[assignment]  # valid values, if the tool states them

    def __post_init__(self) -> None:
        if self.choices is None:
            self.choices = []


@dataclass
class ToolInfo:
    name: str
    description: str
    params: list[ToolParam] = field(default_factory=list)
    aliases: list[str] = field(default_factory=list)

    def signature(self) -> str:
        parts = []
        for p in self.params:
            parts.append(f"{p.name}:{p.type}" + ("" if p.required else "?"))
        return f"{self.name}({', '.join(parts)})"

    def to_json(self) -> dict[str, Any]:
        return {
            "name": self.name,
            "description": self.description,
            "params": [p.__dict__ for p in self.params],
            "signature": self.signature(),
        }


# Only these parameter names can legitimately take a value from a stated list.
# A coordinate or a width must never inherit an enum vocabulary.
CATEGORICAL_PARAMS = frozenset({
    "shape", "kind", "type", "mode", "align", "alignment", "blendMode",
    "preset", "role", "theme", "density", "accent", "panel", "direction",
})

_ENUM_HINT = re.compile(r"\b(rect|roundedRect|circle|ellipse|triangle|polygon|star|line|"
                        r"left|right|center|centre|top|bottom|hcenter|vcenter|canvas|"
                        r"dark|light|system|solid|gradient)\b")


def _choices_from_description(description: str, param_name: str) -> list[str]:
    """Extract a stated set of valid values for a parameter from prose.

    ``add_shape`` says "rect, roundedRect, circle, ellipse, triangle, polygon,
    star, line". Reading that is how the planner learns the vocabulary instead
    of inventing it — which is what produced the invalid ``shape='shape'``.
    """
    if not description:
        return []
    # Look for a comma-separated list of short tokens in the description.
    for m in re.finditer(r"([A-Za-z][A-Za-z0-9_ ]{1,80}?(?:,\s*[A-Za-z][A-Za-z0-9_ ]{1,30}){2,})", description):
        tokens = [t.strip() for t in m.group(1).split(",")]
        tokens = [t for t in tokens if t and len(t) <= 20 and " " not in t]
        if len(tokens) >= 3:
            return tokens
    return []


# Words in a tool description that should retrieve that tool. Derived from the
# live description text, not from a fixed synonym table: this expands whatever
# vocabulary the editor actually ships with.
_STOP = frozenset(
    """a an the and or but if then than that this these those is are was were be been being
    of in on at to for from by with without into over under up down out off
    it its they them their use used using can may will should would
    one more most some any each every all""".split()
)


def _words(text: str) -> list[str]:
    return [w for w in re.findall(r"[a-z][a-z0-9_]{1,}", (text or "").lower()) if w not in _STOP]


class ToolIndex:
    """A searchable view over the live tool catalogue."""

    def __init__(self, tools: list[dict[str, Any]]) -> None:
        self.tools: dict[str, ToolInfo] = {}
        for raw in tools:
            name = raw.get("name") or ""
            if not name:
                continue
            params = self._parse_params(raw)
            desc = (raw.get("description") or "").strip()
            for p in params:
                if not p.choices and p.name in CATEGORICAL_PARAMS and _ENUM_HINT.search(desc or ""):
                    p.choices = _choices_from_description(desc, p.name)
            self.tools[name] = ToolInfo(
                name=name,
                description=(raw.get("description") or "").strip(),
                params=params,
            )

    @staticmethod
    def _parse_params(raw: dict[str, Any]) -> list[ToolParam]:
        """Normalise the bridge's parameter description into a simple schema.

        The editor declares parameters as JSON-schema objects in one of three
        shapes (``properties`` dict, ``parameters`` dict, or a list of names), so
        discovery accepts all three rather than assuming one.
        """
        schema = raw.get("parameters") or raw.get("params") or raw.get("input_schema") or {}
        required = set(schema.get("required") or []) if isinstance(schema, dict) else set()
        out: list[ToolParam] = []
        if isinstance(schema, dict):
            props = schema.get("properties") or {}
            for pname, spec in props.items():
                spec = spec if isinstance(spec, dict) else {}
                out.append(
                    ToolParam(
                        name=pname,
                        type=str(spec.get("type") or "string"),
                        required=pname in required,
                        description=str(spec.get("description") or ""),
                        choices=_choices_from_description(str(spec.get("description") or ""), pname),
                    )
                )
        elif isinstance(schema, list):
            for item in schema:
                if isinstance(item, str):
                    out.append(ToolParam(name=item, required=True))
                elif isinstance(item, dict) and item.get("name"):
                    out.append(
                        ToolParam(
                            name=item["name"],
                            type=str(item.get("type") or "string"),
                            required=bool(item.get("required")),
                            description=str(item.get("description") or ""),
                        )
                    )
        return out

    # ------------------------------------------------------------- querying
    def get(self, name: str) -> ToolInfo | None:
        return self.tools.get(name)

    def names(self) -> list[str]:
        return sorted(self.tools)

    def _score(self, tool: ToolInfo, query_words: list[str]) -> float:
        hay = set(_words(tool.name.replace("_", " ")) + _words(tool.description))
        name_words = set(_words(tool.name.replace("_", " ")))
        if not query_words:
            return 0.0
        hits = sum(1 for w in query_words if w in hay)
        name_hits = sum(1 for w in query_words if w in name_words)
        score = hits / len(query_words)
        score += 0.5 * (name_hits / len(query_words))     # a name match is stronger evidence
        # Substring evidence for morphology the stemmer would miss (truncate/truncation).
        for w in query_words:
            if len(w) >= 5 and any(w[:5] in h for h in hay):
                score += 0.15
        return score

    def search(self, query: str, limit: int = 5) -> list[tuple[float, ToolInfo]]:
        qw = _words(query)
        scored = [(self._score(t, qw), t) for t in self.tools.values()]
        scored = [s for s in scored if s[0] > 0]
        scored.sort(key=lambda pair: -pair[0])
        return scored[:limit]

    def resolve(self, wanted: str) -> tuple[ToolInfo | None, str]:
        """Map a name the planner invented onto a tool that actually exists.

        Returns (tool, how). ``how`` is one of exact | fuzzy | None, and is
        recorded so an attempt can be classified honestly: a plan that guessed a
        name and was corrected is different from one that knew the name.
        """
        if wanted in self.tools:
            return self.tools[wanted], "exact"
        # normalise separators and case
        key = re.sub(r"[^a-z0-9]+", "_", wanted.lower()).strip("_")
        if key in self.tools:
            return self.tools[key], "normalised"
        # plural/singular and common verb/noun drift
        for cand in (key.rstrip("s"), key + "s"):
            if cand in self.tools:
                return self.tools[cand], "inflected"
        close = get_close_matches(key, list(self.tools), n=1, cutoff=0.72)
        if close:
            return self.tools[close[0]], "fuzzy"
        # last resort: does the search rank anything clearly?
        ranked = self.search(wanted.replace("_", " "), limit=1)
        if ranked and ranked[0][0] >= 0.6:
            return ranked[0][1], "searched"
        return None, "none"

    def describe(self, name: str) -> dict[str, Any]:
        """The documentation a planner needs for one tool, from the live catalogue."""
        tool = self.tools.get(name)
        return tool.to_json() if tool else {"error": f"no such tool: {name}"}

    def catalogue(self) -> str:
        """Compact catalogue text suitable for prompting or reasoning."""
        lines = []
        for t in sorted(self.tools.values(), key=lambda x: x.name):
            desc = " ".join(t.description.split())[:150]
            lines.append(f"- {t.signature()} :: {desc}")
        return "\n".join(lines)

    READ_ONLY = frozenset({"get_app_state", "list_templates"})

    def is_read_only(self, name: str) -> bool:
        return name in self.READ_ONLY or name.startswith("list_") or name.startswith("get_")

    def unknown_names(self, plan: list[dict[str, Any]]) -> list[str]:
        """Names in a plan that do not exist — the first thing repair must fix."""
        return [step.get("tool", "") for step in plan if step.get("tool") not in self.tools]

    def similarity(self, a: str, b: str) -> float:
        return SequenceMatcher(None, a, b).ratio()


def tool_index_from_bridge(bridge: Any) -> ToolIndex:
    return ToolIndex(bridge.list_tools())


def tool_index_from_snapshot(snapshot: dict[str, Any]) -> ToolIndex:
    """Build an index from a persisted catalogue (used by offline benchmark runs)."""
    return ToolIndex(snapshot.get("tools", []))


def dump_index(index: ToolIndex, path) -> None:
    from pathlib import Path

    Path(path).write_text(
        json.dumps([t.to_json() for t in index.tools.values()], indent=2),
        encoding="utf-8",
    )
