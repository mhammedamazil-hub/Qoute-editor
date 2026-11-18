"""The design agent: plans, acts on the real editor, verifies, and records skills.

Flow for one instruction (the ACT half of the lifecycle):

    metacognition.pre_action  ->  plan (grounded prompt + skill retrieval)
      ->  execute tool calls against the *real* QuoteCraft store
      ->  deterministic verification of the resulting store state
      ->  metacognition.post_action
      ->  episode + (on success) procedural skill

A trajectory only becomes a ``VERIFIED`` skill when the verification pass is
unambiguous. Otherwise it is stored as a failure and fed to sleep as a lesson,
never as training data.
"""

from __future__ import annotations

import json
import re
import time
from dataclasses import dataclass, field
from typing import Any

from minicoder.cognition.engine import GroundedAnswerer, NeuralBrain
from minicoder.cognition.metacognition import Metacognition
from minicoder.config import FAILED, UNVERIFIED, VERIFIED
from minicoder.memory.db import BrainDB
from minicoder.memory.systems import (
    Episode,
    EpisodicMemory,
    ProceduralMemory,
    SemanticMemory,
    Skill,
    WorkingMemory,
)
from minicoder.tools.editor_bridge import BridgeUnavailable, EditorBridge, verify_tool_outcome


@dataclass
class Step:
    tool: str
    args: dict[str, Any]
    ok: bool = False
    summary: str = ""
    checks: list[str] = field(default_factory=list)
    ms: float = 0.0

    def to_json(self) -> dict[str, Any]:
        return {"tool": self.tool, "args": self.args, "ok": self.ok,
                "summary": self.summary, "checks": self.checks, "ms": round(self.ms, 1)}


@dataclass
class Trajectory:
    instruction: str
    steps: list[Step] = field(default_factory=list)
    verified: bool = False
    source: str = ""
    summary: str = ""
    error: str = ""
    plan: list[str] = field(default_factory=list)
    confidence: float = 0.0
    seconds: float = 0.0
    tool_names: list[str] = field(default_factory=list)
    intent: dict[str, Any] = field(default_factory=dict)

    def to_json(self) -> dict[str, Any]:
        return {
            "instruction": self.instruction,
            "plan": self.plan,
            "steps": [s.to_json() for s in self.steps],
            "verified": self.verified,
            "summary": self.summary,
            "error": self.error,
            "confidence": self.confidence,
            "seconds": round(self.seconds, 2),
            "intent": self.intent,
        }


# --------------------------------------------------------------------------
# instruction understanding (grounded, deterministic, testable)
# --------------------------------------------------------------------------

PALETTES = {
    "emerald": "emerald-luxury", "green": "emerald-luxury", "luxury": "emerald-luxury",
    "midnight": "midnight-gold", "gold": "midnight-gold", "dark": "midnight-gold",
    "ivory": "ivory-editorial", "editorial": "ivory-editorial", "light": "ivory-editorial",
    "neon": "neon-night", "sunset": "sunset-warm", "warm": "sunset-warm",
    "mono": "mono-press", "brutalist": "mono-press", "navy": "royal-navy",
    "royal": "royal-navy", "sage": "sage-calm", "calm": "sage-calm", "pastel": "sage-calm",
}
FONTS = {
    "playfair": "Playfair Display", "cormorant": "Cormorant Garamond",
    "inter": "Inter", "poppins": "Poppins", "montserrat": "Montserrat",
    "manrope": "Manrope", "grotesk": "Space Grotesk",
}


_INTERROGATIVE = re.compile(
    r"^\s*(what|which|how|why|who|when|where|should|can|could|is|are|do|does)\b", re.I
)


def _scrub_copy(candidate: str) -> str:
    """Reject text that is a question rather than poster copy.

    Poster copy is a statement. Anything that begins interrogatively or carries
    an inline question mark is instructional text that leaked into the copy
    field, which would otherwise print "Which palette reads as premium?" on a
    poster (an observed defect in a learned skill).
    """
    t = (candidate or "").strip().strip('"“”').strip()
    if not t:
        return ""
    t = re.split(r"(?<=[?!])\s", t)[0].strip()
    if "?" in t or _INTERROGATIVE.match(t):
        return ""
    return t


def parse_instruction(instruction: str) -> dict[str, Any]:
    """Extract canvas, palette, fonts, quote text and layout intent."""
    text = instruction.strip()
    low = text.lower()
    intent: dict[str, Any] = {}

    m = re.search(r"(\d{3,4})\s*[x×]\s*(\d{3,4})", low)
    if m:
        intent["width"], intent["height"] = int(m.group(1)), int(m.group(2))
    elif "story" in low or "portrait" in low:
        intent["width"], intent["height"] = 1080, 1920
    elif "square" in low or "carousel" in low:
        intent["width"], intent["height"] = 1080, 1080
    elif "landscape" in low or "wide" in low:
        intent["width"], intent["height"] = 1920, 1080

    for key, palette in PALETTES.items():
        if key in low:
            intent["palette"] = palette
            intent["palette_key"] = key
            break
    for key, font in FONTS.items():
        if key in low:
            intent["font"] = font
            break

    # ---- the copy on the poster -------------------------------------------
    # Priority: an explicit quotation, then a phrase introduced by
    # about/saying/reads/says. A quoted *question* is still a question, and
    # question text must never reach the canvas (measured defect: a learned
    # skill printed "As premium? is not given..." as poster copy).
    DOMAIN_WORDS = re.compile(
        r"\b(poster|design|canvas|image|graphic|layout|composition|carousel|story|square|"
        r"portrait|landscape|palette|theme|font|light|glow|text|type|quote|colour|color)\b",
        re.I,
    )
    STATEMENT_MARKER = re.compile(r"\b(is|are|be|not|never|you|we|it|will|can|must|does)\b", re.I)

    quoted = re.search(r'["“]([^"”]{3,160})["”]', text)
    quote = _scrub_copy(quoted.group(1)) if quoted else ""

    if not quote:
        # Single quotes, and the unquoted case after a naming verb. Measured: "build a
        # 1080x1350 poster with the headline 'Quiet'" produced no text step at all,
        # because only typographic double quotes were recognised.
        named = re.search(
            r"\b(?:headline|title|caption|quote|text|reads?|saying|announcing)\b[^'\"\u201c\u201d\n]{0,12}"
            r"(?<![A-Za-z])['\u2018]([^'\u2019\n]{2,60})['\u2019](?![A-Za-z])", text, re.I)
        if named:
            quote = _scrub_copy(named.group(1))
    if not quote:
        lone = re.search(
            r"(?<![A-Za-z])['\u2018]([^'\u2019\n]{2,60})['\u2019](?![A-Za-z])", text)
        if lone:
            quote = _scrub_copy(lone.group(1))

    if not quote:
        for verb in ("about", "saying", "reads", "says"):
            m = re.search(rf'\b{verb}\s+["“\']?([^"”\'\n]{{3,160}})', text, re.I)
            if not m:
                continue
            raw = re.split(r"(?:\.|,|\s+(?:at|with|and|in|on|using)\s+)", m.group(1))[0]
            candidate = _scrub_copy(raw)
            if not candidate or DOMAIN_WORDS.search(candidate):
                continue
            # A short noun phrase is a topic the agent composes around; a full
            # clause in the author's own voice is the quotation itself.
            if len(candidate.split()) <= 3 and not STATEMENT_MARKER.search(candidate):
                intent["topic"] = candidate
            else:
                quote = candidate
            break

    if quote:
        intent["quote"] = quote

    intent["centered"] = bool(re.search(r"\b(centred|centered|centre|center)\b", low))
    intent["minimal"] = bool(re.search(r"\b(minimal|clean|negative space|breathing)\b", low))
    intent["premium"] = bool(re.search(r"\b(premium|luxur\w*|elegant|cinematic)\b", low))
    intent["light"] = bool(re.search(r"\b(light|glow|lamp|amber|sunlight)\b", low))
    intent["export"] = bool(re.search(r"\bexport|png|jpg|download\b", low))
    return intent


# --------------------------------------------------------------------------
# the agent
# --------------------------------------------------------------------------

class DesignAgent:
    def __init__(
        self,
        db: BrainDB | None = None,
        bridge: EditorBridge | None = None,
        *,
        brain: NeuralBrain | None = None,
    ) -> None:
        self.db = db or BrainDB()
        self.bridge = bridge or EditorBridge()
        self.episodic = EpisodicMemory(self.db)
        self.semantic = SemanticMemory(self.db)
        self.procedural = ProceduralMemory(self.db)
        self.working = WorkingMemory()
        self.mc = Metacognition(self.db)
        self.brain = brain or NeuralBrain()
        self.answerer = GroundedAnswerer(self.brain, self.episodic, self.semantic, self.procedural)

    # ------------------------------------------------------------- planning
    def capabilities(self) -> dict[str, Any]:
        """What the connected editor can actually do right now."""
        try:
            names = {t["name"] for t in self.bridge.list_tools()}
        except BridgeUnavailable:
            return {"tools": set(), "online": False}
        return {"tools": names, "online": True}

    def plan(self, instruction: str) -> tuple[list[dict[str, Any]], dict[str, Any]]:
        """Decompose an instruction into deterministic, verifiable editor actions.

        Every step here is a pure store mutation with no network dependency, so
        the whole trajectory can be verified offline. ``generate_design`` is
        deliberately excluded: it calls a remote Gemini service, which is the
        *editor's* optional AI feature, not this brain's — depending on it would
        make verification non-reproducible.
        """
        intent = parse_instruction(instruction)
        if intent.get("topic") and not intent.get("quote"):
            intent["quote"] = self._author_quote(intent["topic"])
            intent["authored"] = True
        steps: list[dict[str, Any]] = []
        low = instruction.lower()

        if intent.get("width") and intent.get("height"):
            steps.append({"tool": "set_canvas_size",
                          "args": {"width": intent["width"], "height": intent["height"]}})
        # A concrete style -> palette mapping, only when the user asked for it.
        if intent.get("palette") and re.search(r"\b(palette|colou?r|theme|look|style|feel)\b", low):
            steps.append({"tool": "apply_palette", "args": {"palette": intent["palette"]}})
        if intent.get("quote"):
            q = intent["quote"][:160]
            args: dict[str, Any] = {"content": q, "role": "quote", "x": 120, "y": 340, "width": 840}
            if intent.get("font"):
                args["fontFamily"] = intent["font"]
            if intent.get("centered") or len(q.split()) <= 8:
                args["align"] = "center"
            steps.append({"tool": "add_text", "args": args})
            # The editor seeds new text layers with placeholder copy, so the
            # words are written explicitly afterwards (verified in post-check).
            steps.append({"tool": "set_text_content",
                          "args": {"all": True, "types": ["text"], "content": q}})
        if intent.get("premium") or intent.get("light"):
            steps.append({"tool": "add_light",
                          "args": {"x": 540, "y": 380, "radius": 760, "intensity": 0.32,
                                   "blendMode": "screen"}})
        if intent.get("minimal"):
            steps.append({"tool": "align_elements", "args": {"types": ["text"], "mode": "hcenter"}})
        if intent.get("export"):
            steps.append({"tool": "export_image",
                          "args": {"format": "png", "scale": 2, "download": False}})
        return steps, intent

    @staticmethod
    def _author_quote(topic: str) -> str:
        """Compose a short line around a topic when the user gave no quote text.

        This is deterministic template composition, not a neural generation, and
        the trajectory records ``authored: true`` so nothing pretends authorship
        it does not have.
        """
        t = topic.strip().rstrip(".")
        return f"{t[:1].upper() + t[1:]} is not given. It is built, one quiet day at a time."

    # ------------------------------------------------------------ execution
    @staticmethod
    def _unmet_requirements(instruction: str, state: dict[str, Any]) -> list[str]:
        """Requirements the instruction states explicitly and the canvas does not meet.

        Only checks things the instruction actually names — a quoted headline, a WxH canvas,
        a dark background — so it cannot invent expectations the user never expressed.
        """
        from minicoder.learning.criteria import EditorState, evaluate_editor_criteria

        try:
            snapshot = state.get("snapshot") if isinstance(state, dict) else None
            if not snapshot:
                return []
            observed = EditorState.from_snapshot(snapshot)
        except Exception:  # noqa: BLE001 - a malformed state must not fail the request
            return []

        criteria: list[str] = []
        for quoted in re.findall(r"['\"\u201c]([^'\"\u201d]{2,60})['\"\u201d]", instruction):
            criteria.append(f'text_present("{quoted}")')
        size = re.search(r"(\d{2,5})\s*[x\u00d7]\s*(\d{2,5})", instruction)
        if size:
            criteria.append(f"canvas_size({int(size.group(1))}, {int(size.group(2))})")
        if not criteria:
            return []
        unmet = []
        for result in evaluate_editor_criteria(criteria, observed):
            if not result.passed:
                unmet.append(result.detail or result.text)
        return unmet

    def execute(self, instruction: str, *, dry_run: bool = False,
                authorize: bool = False, auth=None) -> Trajectory:
        """Run one instruction.

        ``auth`` is the Phase 5 authorization context (a consumed grant or an
        explicit internal context).  ``authorize`` is the Phase 4 boolean and is
        kept only so old clients do not crash: it grants nothing.  A mutating
        plan without ``auth`` raises ``AuthorizationRequired`` *before the first
        step runs*, so a refusal can never leave a half-applied canvas.
        """
        t0 = time.time()
        traj = Trajectory(instruction=instruction)
        try:
            self.bridge._ensure()
        except BridgeUnavailable as exc:
            traj.error = f"editor bridge unavailable: {exc}"
            self._record(traj, intent={})
            return traj
        traj.tool_names = [t["name"] for t in self.bridge.list_tools()]
        memories = self.semantic.search(instruction, limit=3)
        pre = self.mc.pre_action(instruction, memories=memories, tools_available=True)
        traj.confidence = pre.calibrated_confidence
        self.working.put("message", instruction, priority=0.9)
        for m in memories:
            self.working.put("constraint", f"{m['label']}: {m['content'][:160]}", priority=0.6)

        if pre.needs_clarification:
            traj.summary = pre.clarification_question
            traj.plan = ["ask clarification"]
            traj.verified = False
            self._record(traj, intent={})
            return traj

        # Explicit, typed intent. Phase 3 inferred this with a regex that required a
        # question mark, which is how "How many fonts should I use in one poster" reached
        # the planner and mutated the canvas.
        from minicoder.cognition.intent import IntentType, authorization_message, classify

        intent = classify(instruction)
        traj.intent = intent.to_json()

        if intent.requires_authorization and not (auth is not None and getattr(auth, 'authorized', False)):
            traj.summary = authorization_message(intent)
            traj.plan = ["authorization required"]
            traj.source = "refuse"
            traj.verified = False
            self._observe_outcome(traj, intent.to_json(), authorized=False)
            self._record(traj, intent=intent.to_json())
            return traj

        if intent.type == IntentType.PLANNING:
            planned, plan_intent = self.plan(instruction)
            if planned:
                lines = [f"{i}. {p['tool']}" + (f"({', '.join(list(p['args'])[:3])})" if p["args"] else "")
                         for i, p in enumerate(planned, 1)]
                traj.summary = ("Here is the plan, nothing has been changed yet:\n"
                                + "\n".join(lines)
                                + "\nSay \"go ahead\" and I will run it.")
                traj.plan = [p["tool"] for p in planned]
                traj.source = "plan"
                traj.verified = False
                self._observe_outcome(traj, plan_intent)
                self._record(traj, intent=plan_intent)
                return traj

        if intent.is_answerable:
            gen = self.answerer.answer(instruction)
            traj.plan = ["answer from memory (no canvas mutation)"]
            traj.summary = gen.text
            traj.verified = gen.source in ("skill", "memory")
            traj.source = gen.source
            traj.confidence = pre.calibrated_confidence
            traj.seconds = time.time() - t0
            self._observe_outcome(traj, intent.to_json(), authorized=bool(auth is not None and getattr(auth, 'authorized', False)))
            self._record(traj, intent={}, answer=gen.to_json())
            return traj

        planned, plan_intent = self.plan(instruction)
        traj.plan = [f"{p['tool']}({', '.join(f'{k}={v!r}' for k, v in list(p['args'].items())[:2])})" for p in planned]
        if not planned:
            # Nothing actionable -> answer from memory instead of touching the canvas.
            gen = self.answerer.answer(instruction)
            traj.summary = gen.text
            traj.verified = gen.source in ("skill", "memory")
            traj.error = ""
            traj.source = gen.source
            traj.plan = ["answer (no canvas action implied)"]
            self._observe_outcome(traj, intent.to_json(), authorized=bool(auth is not None and getattr(auth, 'authorized', False)))
            self._record(traj, intent=plan_intent, answer=gen.to_json())
            return traj
        if dry_run:
            traj.summary = f"dry run: {len(planned)} step(s) planned"
            traj.verified = True
            return traj

        # Authorize the whole plan before executing the first step.  The bridge
        # re-checks every call; this up-front pass exists so a plan is either
        # fully authorized or not started at all.
        from minicoder.security.guard import check_plan

        check_plan(planned, auth)
        state = self.bridge.state()
        checks: list[str] = []
        for p in planned:
            step = Step(tool=p["tool"], args=p["args"])
            s0 = time.time()
            try:
                result, new_state = self.bridge.call(p["tool"], p["args"], auth=auth)
                ok, checks = verify_tool_outcome(p["tool"], p["args"], result, state, new_state)
                step.ok = ok
                step.summary = str(result.get("summary", ""))[:300]
                step.checks = checks
                state = new_state
            except BridgeUnavailable as exc:
                step.ok = False
                step.summary = f"bridge error: {exc}"
            step.ms = (time.time() - s0) * 1000
            traj.steps.append(step)
            self.working.put("tool_result", f"{p['tool']}: {step.summary}", priority=0.5)
            if not step.ok:
                break

        traj.verified = bool(traj.steps) and all(s.ok for s in traj.steps)
        # Steps succeeding is not the instruction being satisfied. Measured: "build a
        # 1080x1350 poster with headline 'Quiet'" resized the canvas, reported success, and
        # never placed the headline. Check what was asked for against what exists now.
        unmet = self._unmet_requirements(instruction, state)
        traj.summary = self._narrate(traj) if traj.verified else (
            "; ".join(s.summary for s in traj.steps if s.summary)[:600] or "no steps executed"
        )
        if unmet:
            traj.verified = False
            traj.summary = (traj.summary + " " if traj.summary else "") + (
                "But this does not satisfy the request: " + "; ".join(unmet) + ".")
        post = self.mc.post_action(
            expected="; ".join(traj.plan), observed=traj.summary,
            tool_ok=all(s.ok for s in traj.steps), all_checks_passed=traj.verified,
            predicted_confidence=traj.confidence,
        )
        self.mc.observe_outcome(traj.confidence, 1.0 if post.matched else 0.0)
        traj.verified = post.matched
        traj.confidence = round(max(0.0, min(1.0, traj.confidence + post.confidence_delta)), 3)
        traj.seconds = time.time() - t0
        self._observe_outcome(traj, intent.to_json(), authorized=bool(auth is not None and getattr(auth, 'authorized', False)))
        self._record(traj, intent=plan_intent, post=post.to_json())
        return traj

    @staticmethod
    def _narrate(traj: Trajectory) -> str:
        """A short, human-readable account of what actually changed on the canvas."""
        parts = [s.summary.rstrip(".") for s in traj.steps if s.summary]
        checks = sum(len(s.checks) for s in traj.steps)
        body = "; ".join(parts[:5])
        return f"{body}. Verified against {checks} deterministic checks on the live editor store."

    def _observe_outcome(self, traj: Trajectory, intent: dict[str, Any], *,
                         authorized: bool = False) -> None:
        """Turn a finished trajectory into a calibration sample and an audit row.

        Only trajectories that actually ran and were checked count: a refusal or
        a plan has no measured outcome, and inventing one would corrupt the very
        number this is meant to score.
        """
        from minicoder.cognition.metacognition import audit

        ran = bool(traj.steps) and traj.source not in ("refuse", "plan")
        if ran:
            self.mc.observe_outcome(
                traj.confidence, 1.0 if traj.verified else 0.0, source="execution",
                detail={"instruction": traj.instruction[:160],
                        "steps": [s.tool for s in traj.steps][:6],
                        "intent": intent.get("type", "")})
        if intent.get("requires_authorization") or intent.get("consequential"):
            # ``allowed`` records the authorization decision, not whether a plan
            # happened to exist: a granted request that turned out unactionable is
            # audited as granted-but-unexecuted, which is the honest distinction.
            audit(self.db, "execute", intent=str(intent.get("type", "")),
                  authorized=authorized, allowed=authorized,
                  detail={"instruction": traj.instruction[:160],
                          "actions": intent.get("consequential", [])[:4],
                          "executed": bool(traj.steps),
                          "outcome": traj.source, "verified": traj.verified})

    def _record(self, traj: Trajectory, intent: dict[str, Any], post: dict[str, Any] | None = None,
                answer: dict[str, Any] | None = None) -> int:
        status = VERIFIED if traj.verified else (FAILED if traj.steps and not traj.verified else UNVERIFIED)
        modality = "mixed"
        surprise = 1.0 if (traj.steps and not traj.verified) else (0.65 if traj.verified else 0.15)
        lesson = ""
        if traj.verified and traj.steps:
            lesson = (
                f"A {len(traj.steps)}-step trajectory on the QuoteCraft editor satisfies "
                f"{sum(len(s.checks) for s in traj.steps)} deterministic checks "
                f"({', '.join(s.tool for s in traj.steps)})."
            )
        elif traj.error:
            lesson = f"Trajectory failed: {traj.error[:180]}"
        elif traj.steps:
            bad = next((s for s in traj.steps if not s.ok), None)
            lesson = f"Step {bad.tool if bad else '?'} failed verification: {bad.summary if bad else ''}"[:200]
        ep = Episode(
            situation=traj.instruction[:400],
            objective=(intent.get("quote") or traj.instruction)[:200],
            modality=modality,
            actions=[s.to_json() for s in traj.steps],
            result=traj.summary[:600],
            status=status,
            source="verified_execution" if traj.verified else "unverified_hypothesis",
            mistakes="" if traj.verified else (traj.error or next((s.summary for s in traj.steps if not s.ok), "")),
            lessons=lesson,
            confidence=traj.confidence,
            surprise=surprise,
            meta={"plan": traj.plan, "post": post or {}, "intent": intent, "answer": answer or {}},
        )
        eid = self.episodic.add(ep)
        if traj.verified and traj.steps:
            # Ordered slug: a trajectory is a procedure, so step order matters.
            slug = "canvas_" + "_".join(s.tool.replace("_elements", "").replace("_", "") for s in traj.steps)[:70]
            verification_payload = json.dumps(
                [{"tool": s.tool, "args": s.args} for s in traj.steps], sort_keys=True
            )
            import hashlib as _hash

            vhash = _hash.sha256(verification_payload.encode()).hexdigest()
            skill = Skill(
                slug=slug,
                name=f"Compose a poster via {len(traj.steps)} editor actions",
                description=f"Given a quote-poster instruction, apply: {', '.join(traj.plan)}",
                domain="design",
                params_schema={"instruction": "string", "intent": "object"},
                reasoning=[f"Parsed intent: {json.dumps(intent, sort_keys=True)[:200]}"],
                tool_calls=[s.to_json() for s in traj.steps],
                solution=json.dumps([{"tool": s.tool, "args": s.args} for s in traj.steps]),
                verification={"passed": True, "runner": "editor-bridge",
                              "checks": [c for s in traj.steps for c in s.checks],
                              "hash": vhash, "episode_id": eid},
                source="verified_execution",
                confidence=traj.confidence,
                episode_ids=[eid],
            )
            self.procedural.add(skill, verified=True)
        return eid
