"""Tool classification and the policy that follows from it.

Every tool the editor bridge exposes is classified here, explicitly.  The
classification is the *policy input* for authorization: a tool that is not in
this table is not "probably read-only" — it is unknown, and unknown tools are
rejected (fail closed).

The table is deliberately a data structure rather than a set of ``if`` branches
so the inventory can be printed (`python -m minicoder.cli security inventory`),
tested exhaustively against the live bridge, and reviewed in one place.
"""

from __future__ import annotations

import hashlib
import re
import unicodedata
from dataclasses import dataclass
from enum import StrEnum
from typing import Any


class ToolClass(StrEnum):
    """How much authority a tool needs.

    The ordering matters: ``READ_ONLY`` needs no grant, everything else does.
    """

    READ_ONLY = "read_only"          # observes; no design state changes
    REVERSIBLE = "reversible"        # mutates the design, undoable in-place
    CONSEQUENTIAL = "consequential"  # leaves the sandbox or replaces a design
    DESTRUCTIVE = "destructive"      # removes work irreversibly


#: Latent-1 authority: read-only tools may run without a grant.
GRANT_REQUIRED: frozenset[ToolClass] = frozenset(
    {ToolClass.REVERSIBLE, ToolClass.CONSEQUENTIAL, ToolClass.DESTRUCTIVE}
)

#: All 37 tools the bridge currently exposes.  A tool missing from this map is
#: rejected at execution time; a tool present in the bridge but absent here is a
#: test failure (``test_tool_inventory_matches_bridge``).
TOOL_CLASSES: dict[str, ToolClass] = {
    # --- observation -------------------------------------------------------
    "get_app_state": ToolClass.READ_ONLY,
    "list_templates": ToolClass.READ_ONLY,
    # --- view/selection state (no design content) --------------------------
    "zoom": ToolClass.REVERSIBLE,
    "set_preview_mode": ToolClass.REVERSIBLE,
    "open_panel": ToolClass.REVERSIBLE,
    "set_ui_preference": ToolClass.REVERSIBLE,
    "select_elements": ToolClass.REVERSIBLE,
    # --- canvas / design content ------------------------------------------
    "new_project": ToolClass.DESTRUCTIVE,
    "set_canvas_size": ToolClass.REVERSIBLE,
    "set_background": ToolClass.REVERSIBLE,
    "apply_palette": ToolClass.REVERSIBLE,
    "apply_template": ToolClass.REVERSIBLE,
    "add_text": ToolClass.REVERSIBLE,
    "add_quote_mark": ToolClass.REVERSIBLE,
    "add_shape": ToolClass.REVERSIBLE,
    "add_light": ToolClass.REVERSIBLE,
    "add_gradient_layer": ToolClass.REVERSIBLE,
    "add_particles": ToolClass.REVERSIBLE,
    "add_decoration": ToolClass.REVERSIBLE,
    "update_elements": ToolClass.REVERSIBLE,
    "set_text_content": ToolClass.REVERSIBLE,
    "set_typography": ToolClass.REVERSIBLE,
    "set_layer_style": ToolClass.REVERSIBLE,
    "translate_elements": ToolClass.REVERSIBLE,
    "resize_elements": ToolClass.REVERSIBLE,
    "duplicate_elements": ToolClass.REVERSIBLE,
    "reorder_elements": ToolClass.REVERSIBLE,
    "group_elements": ToolClass.REVERSIBLE,
    "ungroup_elements": ToolClass.REVERSIBLE,
    "align_elements": ToolClass.REVERSIBLE,
    "distribute_elements": ToolClass.REVERSIBLE,
    "undo": ToolClass.REVERSIBLE,
    "redo": ToolClass.REVERSIBLE,
    # --- destructive -------------------------------------------------------
    "delete_elements": ToolClass.DESTRUCTIVE,
    # --- leaves the sandbox / bulk generation -----------------------------
    "save_project": ToolClass.CONSEQUENTIAL,
    "export_image": ToolClass.CONSEQUENTIAL,
    "generate_design": ToolClass.CONSEQUENTIAL,
}


def classify_tool(name: str) -> ToolClass | None:
    """Return the class of ``name`` or ``None`` when it is not a known tool."""
    return TOOL_CLASSES.get((name or "").strip())


def is_mutating(name: str) -> bool:
    """True when the tool needs a grant.  Unknown tools count as mutating."""
    cls = classify_tool(name)
    if cls is None:
        return True
    return cls in GRANT_REQUIRED


def unknown_tools(names: list[str]) -> list[str]:
    return [n for n in names if n not in TOOL_CLASSES]


def inventory() -> list[dict[str, str]]:
    return [
        {"tool": name, "class": cls.value}
        for name, cls in sorted(TOOL_CLASSES.items(), key=lambda kv: (kv[1].value, kv[0]))
    ]


# --------------------------------------------------------------------------
# actions: what a grant authorizes
# --------------------------------------------------------------------------

ACTION_TOOL = "editor.tool"                # scope = exact tool name
ACTION_INSTRUCTION = "editor.instruction"  # scope = sha256 of the instruction
ACTION_CANVAS = "editor.canvas"            # scope = "WxH"
ACTION_MEMORY_WRITE = "memory.write"       # scope = label
ACTION_SNAPSHOT = "memory.snapshot"        # scope = "brain"
ACTION_SLEEP_RUN = "sleep.run"             # scope = "cycle"
ACTION_VISION_INSPECT = "vision.inspect"   # scope = "upload"

GRANTABLE_ACTIONS: frozenset[str] = frozenset(
    {
        ACTION_TOOL,
        ACTION_INSTRUCTION,
        ACTION_CANVAS,
        ACTION_MEMORY_WRITE,
        ACTION_SNAPSHOT,
        ACTION_SLEEP_RUN,
        ACTION_VISION_INSPECT,
    }
)

#: Actions whose resource is a canvas.  Used to reject a grant minted for one
#: resource being presented for another.
RESOURCE_BY_ACTION: dict[str, str] = {
    ACTION_TOOL: "canvas",
    ACTION_INSTRUCTION: "canvas",
    ACTION_CANVAS: "canvas",
    ACTION_MEMORY_WRITE: "memory:semantic",
    ACTION_SNAPSHOT: "memory",
    ACTION_SLEEP_RUN: "memory",
    ACTION_VISION_INSPECT: "memory:visual",
}


def resource_for(action: str) -> str:
    return RESOURCE_BY_ACTION.get(action, "unknown")


# --------------------------------------------------------------------------
# canonicalisation: a grant is bound to the *exact* operation
# --------------------------------------------------------------------------

_WS = re.compile(r"\s+")
_PUNCT = re.compile(r"[\u2018\u2019\u201c\u201d]")


def canonical_instruction(text: str) -> str:
    """Normalise an instruction so a grant cannot be stretched to a near miss.

    Case and whitespace are normalised because they do not change meaning;
    punctuation that carries meaning (``?``, ``!``, quotes) is preserved.
    """
    s = unicodedata.normalize("NFKC", text or "")
    s = _PUNCT.sub("'", s)
    s = _WS.sub(" ", s).strip().lower()
    return s


def instruction_scope(text: str) -> str:
    return "sha256:" + hashlib.sha256(canonical_instruction(text).encode("utf-8")).hexdigest()


@dataclass(frozen=True)
class ToolRequest:
    tool: str
    args: dict[str, Any]

    @property
    def tool_class(self) -> ToolClass | None:
        return classify_tool(self.tool)
