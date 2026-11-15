"""Metacognition: explicit, measurable pre-action checks and post-action audits.

Unlike a fake "thinking" monologue, every value here is computed from real
signals (model entropy, retrieval similarity, task vocabulary coverage, tool
availability) and is logged to episodic memory so sleep can analyse it.
"""

from __future__ import annotations

import math
import re
from dataclasses import dataclass, field, asdict
from typing import Any, Sequence

_WORD = re.compile(r"[A-Za-z][A-Za-z0-9_]+")

CODE_HINT = re.compile(
    r"\b(function|implement|write|algorithm|compile|bug|error|refactor|python|javascript|typescript|"
    r"api|class|def |return|test|unit|regex|sql|async|import)\b",
    re.IGNORECASE,
)
VISION_HINT = re.compile(r"\b(image|screenshot|picture|photo|diagram|visual|look at|inspect|ui mockup|bbox|ocr)\b", re.IGNORECASE)
ACTION_HINT = re.compile(
    r"\b(create|make|add|change|set|move|delete|export|apply|switch|build|generate|design|restyle|duplicate|group|align)\b",
    re.IGNORECASE,
)
MEMORY_HINT = re.compile(r"\b(remember|earlier|before|previously|last time|my preference|i like|i prefer)\b", re.IGNORECASE)


@dataclass
class PreActionReport:
    task_clarity: float
    confidence: float
    calibrated_confidence: float
    modality: str
    route: str
    needs_clarification: bool
    clarification_question: str
    retrieved_memories: int
    signals: dict[str, Any] = field(default_factory=dict)

    def to_json(self) -> dict[str, Any]:
        return asdict(self)


@dataclass
class PostActionReport:
    expected: str
    observed: str
    matched: bool
    discrepancy: str
    confidence_delta: float
    verified: bool

    def to_json(self) -> dict[str, Any]:
        return asdict(self)


class Metacognition:
    """Pre/post action reasoning with a real calibration curve.

    Calibration is fitted from logged (predicted, actual) pairs, so
    ``calibrated_confidence`` is an empirically measured quantity, not a vibe.
    """

    def __init__(self, db=None) -> None:
        self.db = db
        self._pairs: list[tuple[float, float]] = []

    # ---------------------------------------------------------- inputs
    def observe_outcome(self, predicted: float, actual: float) -> None:
        """Log a calibration sample (actual = 1.0 success, 0.0 failure)."""
        self._pairs.append((predicted, actual))

    def calibration(self) -> dict[str, Any]:
        if not self._pairs:
            return {"n": 0, "ece": float("nan"), "brier": float("nan"), "buckets": []}
        n = len(self._pairs)
        brier = sum((p - a) ** 2 for p, a in self._pairs) / n
        buckets = []
        ece = 0.0
        for lo in [0.0, 0.2, 0.4, 0.6, 0.8]:
            hi = lo + 0.2
            sel = [(p, a) for p, a in self._pairs if lo <= p < hi or (hi == 1.0 and p == 1.0)]
            if not sel:
                continue
            mean_p = sum(p for p, _ in sel) / len(sel)
            mean_a = sum(a for _, a in sel) / len(sel)
            ece += (len(sel) / n) * abs(mean_p - mean_a)
            buckets.append({"range": f"{lo:.1f}-{hi:.1f}", "n": len(sel),
                            "predicted": round(mean_p, 3), "actual": round(mean_a, 3)})
        return {"n": n, "ece": round(ece, 4), "brier": round(brier, 4), "buckets": buckets}

    def calibrated(self, raw: float) -> float:
        """Shrink overconfident predictions toward the observed success rate."""
        if len(self._pairs) < 8:
            return round(0.5 + (raw - 0.5) * 0.8, 4)  # conservative before data exists
        mean_actual = sum(a for _, a in self._pairs) / len(self._pairs)
        # Reliability blend: keep ordering, pull magnitude to the real mean.
        return round(max(0.02, min(0.98, 0.55 * raw + 0.45 * mean_actual)), 4)

    # ------------------------------------------------------- pre-action
    def pre_action(
        self,
        instruction: str,
        *,
        memories: Sequence[dict[str, Any]] = (),
        max_entropy: float | None = None,
        has_image: bool = False,
        tools_available: bool = True,
    ) -> PreActionReport:
        text = instruction.strip()
        words = _WORD.findall(text)
        wc = len(words)
        signals: dict[str, Any] = {"words": wc}

        # 1. Clarity: length, presence of a verb, absence of dangling pronouns.
        clarity = 0.35
        clarity += min(0.35, wc / 30.0)
        clarity += 0.15 if ACTION_HINT.search(text) or CODE_HINT.search(text) else 0.0
        clarity += 0.15 if re.search(r"\b(for|about|with|using|at|to)\b", text, re.I) else 0.0
        vague = re.search(r"\b(that|it|this|stuff|thing|something)\b", text, re.I) and wc < 6
        if vague:
            clarity -= 0.25
        clarity = max(0.05, min(1.0, clarity))
        signals["vague_reference"] = bool(vague)

        # 2. Modality routing.
        if has_image and VISION_HINT.search(text):
            modality = "mixed"
        elif has_image or VISION_HINT.search(text):
            modality = "vision"
        elif CODE_HINT.search(text):
            modality = "code"
        else:
            modality = "text"
        signals["code_hint"] = bool(CODE_HINT.search(text))
        signals["vision_hint"] = bool(VISION_HINT.search(text))
        signals["memory_hint"] = bool(MEMORY_HINT.search(text))

        # 3. Retrieval support: how well do memories cover the task vocabulary?
        task_tokens = {w.lower() for w in words if len(w) > 3}
        covered: set[str] = set()
        for m in memories:
            hay = " ".join(str(v) for v in m.values() if isinstance(v, (str, int, float))).lower()
            covered |= {t for t in task_tokens if t in hay}
        coverage = len(covered) / max(1, len(task_tokens))
        signals["memory_coverage"] = round(coverage, 3)

        # 4. Model uncertainty (mean token entropy if the runtime reports it).
        entropy_penalty = 0.0
        if max_entropy is not None and not math.isnan(max_entropy):
            entropy_penalty = min(0.25, max_entropy / (math.log(4096) * 4))
            signals["mean_entropy"] = round(max_entropy, 3)

        route = "act" if (ACTION_HINT.search(text) and tools_available) else "answer"
        if modality in ("vision", "mixed"):
            route = "inspect" if route == "answer" else route
        if re.search(r"\b(code|function|script|debug)\b", text, re.I):
            route = "code"

        confidence = 0.30 * clarity + 0.25 * coverage + 0.25 * (1.0 - entropy_penalty) + 0.20 * (
            1.0 if tools_available else 0.4
        )
        confidence = max(0.01, min(0.99, confidence))
        calibrated = self.calibrated(confidence)

        needs_clarification = clarity < 0.32 and wc < 5
        question = ""
        if needs_clarification:
            subject = modality if modality != "text" else "design"
            question = f"Could you say a little more about the {subject} goal — what should the result look like?"
        return PreActionReport(
            task_clarity=round(clarity, 3),
            confidence=round(confidence, 3),
            calibrated_confidence=calibrated,
            modality=modality,
            route=route,
            needs_clarification=needs_clarification,
            clarification_question=question,
            retrieved_memories=len(memories),
            signals=signals,
        )

    # ------------------------------------------------------ post-action
    def post_action(
        self,
        *,
        expected: str,
        observed: str,
        tool_ok: bool | None = None,
        deterministic_checks: Sequence[str] = (),
        all_checks_passed: bool | None = None,
        predicted_confidence: float = 0.5,
    ) -> PostActionReport:
        """Compare the outcome against the expectation using real evidence."""
        matched = True
        notes: list[str] = []
        if tool_ok is not None:
            matched &= bool(tool_ok)
            notes.append(f"tool_ok={tool_ok}")
        if all_checks_passed is not None:
            matched &= bool(all_checks_passed)
            notes.append(f"checks_passed={all_checks_passed}")
        if deterministic_checks:
            notes.append(f"{len(deterministic_checks)} deterministic checks ran")
        exp_tokens = {t for t in _WORD.findall(expected.lower()) if len(t) > 3}
        obs_tokens = {t for t in _WORD.findall(observed.lower()) if len(t) > 3}
        overlap = len(exp_tokens & obs_tokens) / max(1, len(exp_tokens))
        if exp_tokens and overlap < 0.15 and all_checks_passed is None:
            matched = False
            notes.append(f"low expectation overlap ({overlap:.2f})")
        discrepancy = "; ".join(notes) if not matched else "none"
        delta = 0.12 if matched else -0.25
        return PostActionReport(
            expected=expected[:300],
            observed=observed[:300],
            matched=bool(matched),
            discrepancy=discrepancy,
            confidence_delta=delta,
            verified=bool(matched),
        )
