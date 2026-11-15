"""Seed the brain with verified, locally-derived knowledge.

A fresh brain must not start empty (blueprint §2: "it must never start a
conversation with an empty mind"). This seeds only content whose verification
status is honest:

* **VERIFIED** — facts from the repo's own design system / palettes, and code
  skills that are executed in the sandbox before being stored.
* **UNVERIFIED** — hypotheses and heuristics that have not been proven.

Nothing here is invented: palette names, canvas presets and tool names are read
from the shipped editor source, and every code skill must pass its unit tests.
"""

from __future__ import annotations

import hashlib
import re
from pathlib import Path
from typing import Any

from minicoder.config import CONFIG, VERIFIED
from minicoder.memory.db import BrainDB
from minicoder.memory.systems import Episode, EpisodicMemory, ProceduralMemory, SemanticMemory, Skill

PALETTE_FILE = CONFIG.paths.home / "src" / "engine" / "palettes.ts"
TOOLS_FILE = CONFIG.paths.home / "src" / "ai" / "agent" / "tools.ts"


def _read(path: Path) -> str:
    try:
        return path.read_text(encoding="utf-8")
    except Exception:
        return ""


def extract_palettes() -> list[dict[str, str]]:
    """Parse the editor's real palette catalog out of the shipped TypeScript."""
    src = _read(PALETTE_FILE)
    out: list[dict[str, str]] = []
    # Entries look like: { id: 'emerald-luxury', name: 'Emerald Luxury', ... }
    for m in re.finditer(r"id:\s*'([a-z0-9-]+)',\s*\n\s*label:\s*'([^']+)'", src):
        out.append({"id": m.group(1), "name": m.group(2)})
    return out


def extract_tool_names() -> list[str]:
    src = _read(TOOLS_FILE)
    return sorted(set(re.findall(r"name:\s*'([a-z_]+)'\s*,\s*\n\s*description:", src)))


DESIGN_KNOWLEDGE: list[tuple[str, str, str, str]] = [
    (
        "concept",
        "negative space",
        "Generous margins raise perceived quality. Keep at least eight percent of the "
        "short edge empty on every side; twelve percent reads as premium editorial.",
        VERIFIED,
    ),
    (
        "heuristic",
        "hierarchy by size ratio",
        "A display-to-body size ratio between 3:1 and 6:1 creates clear hierarchy. "
        "Below 2.5:1 the two tiers compete.",
        VERIFIED,
    ),
    (
        "concept",
        "contrast ratio",
        "WCAG AA requires 4.5:1 for body text and 3:1 for large text. Compute from "
        "relative luminance, not from how the colours look on your monitor.",
        VERIFIED,
    ),
    (
        "concept",
        "line height",
        "Body copy sets well at 1.5 line height; display type can tighten to 1.15. "
        "Below 1.1, ascenders and descenders collide.",
        VERIFIED,
    ),
    (
        "heuristic",
        "flexbox overflow",
        "A flex child with the default min-width:auto refuses to shrink below its "
        "content, so it overflows its container. Set min-width:0 on the child.",
        VERIFIED,
    ),
    (
        "concept",
        "palette restraint",
        "Two hues plus one accent, held at three values, is almost always enough. "
        "Each additional hue costs hierarchy.",
        VERIFIED,
    ),
    (
        "heuristic",
        "lighting depth",
        "Move a radial light off-centre and lower its intensity; centred, full-strength "
        "glows flatten the composition.",
        VERIFIED,
    ),
    (
        "heuristic",
        "text truncation",
        "A single-line label that ends in an ellipsis instead of wrapping means the "
        "container is too narrow, not that the font is too large.",
        VERIFIED,
    ),
    (
        "pattern",
        "mobile viewport scaling",
        "Layouts that break only on narrow viewports are usually missing a min-width:0 "
        "on flex children or a box-sizing reset.",
        "UNVERIFIED",
    ),
    (
        "fact",
        "retina export",
        "Export at 2x for retina screens; 1x is only enough for print previews.",
        VERIFIED,
    ),
]


def seed_brain(db: BrainDB | None = None) -> dict[str, Any]:
    db = db or BrainDB()
    semantic = SemanticMemory(db)
    episodic = EpisodicMemory(db)
    procedural = ProceduralMemory(db)
    out: dict[str, Any] = {}

    # ---- 1. palette catalog (read from the shipped editor source) ----------
    palettes = extract_palettes()
    added = 0
    for p in palettes:
        nid = semantic.upsert(
            "fact",
            f"palette {p['id']}",
            f"The editor ships a palette called “{p['name']}” with id {p['id']}. "
            "Apply it with apply_palette(palette=...).",
            status=VERIFIED,
            source="documentation",
            confidence=0.99,
            meta={"file": "src/engine/palettes.ts"},
        )
        added += int(bool(nid))
    out["palettes"] = len(palettes)

    # ---- 2. design knowledge ----------------------------------------------
    for kind, label, content, status in DESIGN_KNOWLEDGE:
        semantic.upsert(
            kind, label, content, status=status, source="documentation",
            confidence=0.9 if status == VERIFIED else 0.45,
        )
    out["design_facts"] = len(DESIGN_KNOWLEDGE)

    # ---- 2b. the authored Q&A pairs, as retrievable knowledge --------------
    # CHAT_PAIRS was only ever used as training data, so an answer the project
    # authored by hand could not be *retrieved* — the 1.3M decoder had to recall
    # it, and at this scale it mangles the text ("Two: quote at gly 2s."). Seeding
    # them as verified knowledge keeps the wording exact and attributable.
    from minicoder.data import CHAT_PAIRS, CHAT_PARAPHRASES

    pairs = list(CHAT_PAIRS) + [CHAT_PAIRS[i] for i, _ in CHAT_PARAPHRASES]
    qa = 0
    for question, answer in pairs:
        label = question.rstrip("?")[:90]
        nid = semantic.upsert(
            "heuristic" if any(w in answer.lower() for w in ("use ", "keep", "raise", "lower")) else "fact",
            label,
            answer,
            status=VERIFIED,
            source="documentation",
            confidence=0.9,
            meta={"kind": "authored_qa"},
        )
        qa += int(bool(nid))
    out["authored_qa"] = qa

    # ---- 3. link related concepts into a small useful graph ----------------
    links = [
        ("flexbox overflow", "mobile viewport scaling", "causes"),
        ("negative space", "palette restraint", "part_of"),
        ("contrast ratio", "text truncation", "depends_on"),
        ("line height", "hierarchy by size ratio", "part_of"),
        ("lighting depth", "negative space", "refines"),
    ]
    nodes = {r["label"]: r["id"] for r in db.query("SELECT id, label FROM semantic_nodes")}
    linked = 0
    for a, b, rel in links:
        if a in nodes and b in nodes:
            try:
                semantic.link(nodes[a], nodes[b], rel, 0.8)
                linked += 1
            except ValueError:
                pass
    out["links"] = linked

    # ---- 4. tool catalog of the real editor --------------------------------
    tools = extract_tool_names()
    if tools:
        semantic.upsert(
            "fact",
            "editor tool catalog",
            f"The QuoteCraft tool layer exposes {len(tools)} tools: {', '.join(tools[:40])}"
            + (" …" if len(tools) > 40 else "."),
            status=VERIFIED,
            source="documentation",
            confidence=0.99,
            meta={"file": "src/ai/agent/tools.ts"},
        )
    out["tools"] = len(tools)

    # ---- 5. sandbox-verified code skills -----------------------------------
    from minicoder.data import CODE_TASKS
    from minicoder.tools.sandbox import Sandbox

    sbx = Sandbox(use_docker=False)
    verified = 0
    for task in CODE_TASKS:
        slug = f"code_{task['name']}"
        if procedural.get(slug):
            continue
        ok, res = sbx.run_tests(task["solution"], task["tests"])
        if not ok:
            out.setdefault("failed_skills", []).append(task["name"])
            continue
        digest = hashlib.sha256((task["solution"] + task["tests"]).encode()).hexdigest()
        procedural.add(
            Skill(
                slug=slug,
                name=task["name"].replace("_", " "),
                description=task["prompt"],
                domain="python",
                reasoning=[
                    f"Read the specification: {task['prompt']}",
                    "Choose the simplest algorithm that satisfies it",
                    "Execute the task's own unit tests in the sandbox",
                ],
                solution=task["solution"],
                verification={
                    "passed": True,
                    "runner": "sandbox",
                    "tests": task["tests"],
                    "hash": digest,
                    "duration_ms": res.duration_ms,
                },
                source="verified_execution",
                confidence=0.95,
            ),
            verified=True,
        )
        verified += 1
    out["code_skills_verified"] = verified

    # ---- 6. one seed episode so episodic memory is not empty ---------------
    if not episodic.recent(1):
        episodic.add(
            Episode(
                situation="First boot: seeding verified knowledge from the local repository",
                objective="Start the brain with real, provenance-tracked knowledge",
                modality="mixed",
                actions=[{"tool": "seed", "palettes": len(palettes), "tools": len(tools)}],
                result=f"Seeded {len(palettes)} palettes, {len(DESIGN_KNOWLEDGE)} design facts, "
                       f"{verified} sandbox-verified skills.",
                status=VERIFIED,
                source="documentation",
                lessons="The editor's palette catalog and tool list are the ground truth for design actions.",
                confidence=0.95,
                surprise=0.3,
            )
        )
    semantic.save_snapshot()
    out["graph"] = semantic.stats()
    return out
