"""Explicit intent classification and action authorization.

Phase 3 left intent implicit in two places: the answerer matched words, and the agent
decided "question or action" with a regex that required a question mark. That produced the
two defects measured in the Phase 3 report — a design question answered with a raw tool
trajectory, and an instruction-shaped request that mutated the canvas without doing what was
asked.

This module makes the decision explicit, typed and inspectable:

* six intent types, each with a confidence and the signals that produced it;
* a structured representation of what the request is about (size, quoted copy, topic);
* an authorization requirement for consequential actions, which the caller must grant.

A question never becomes an execution request here, and a consequential action never runs
without an explicit grant.
"""

from __future__ import annotations

import re
from dataclasses import dataclass, field
from enum import StrEnum
from typing import Any

from minicoder.cognition.selfmodel import classify_self


class IntentType(StrEnum):
    QUESTION = "question"
    EXPLANATION = "explanation"
    PLANNING = "planning"
    EXECUTION = "execution"
    EXPERIMENTATION = "experimentation"
    SELF_INTROSPECTION = "self_introspection"


# Verbs that change the world irreversibly or reach outside the sandbox. These need an
# explicit grant; additive canvas edits do not, because refusing those would break the
# product for no safety gain.
CONSEQUENTIAL_VERBS = re.compile(
    r"\b(delete|remove|destroy|wipe|erase|drop|reset|overwrite|clear|purge|"
    r"push|publish|deploy|send|upload|export|download|install|uninstall|"
    r"truncate|replace all|rm)\b", re.I)

_EXPLAIN = re.compile(r"\b(explain|why (does|is|do)|how (does|do|is) .* work|"
                      r"what does .* mean|difference between|describe)\b", re.I)
_PLAN = re.compile(r"\b(plan|outline|steps|approach|strategy|how would you|"
                   r"what would you do|walk me through)\b", re.I)
_EXPERIMENT = re.compile(r"\b(experiment|benchmark|measure|run a test|try .* and (see|measure)|"
                         r"ablation|compare .* against)\b", re.I)
_EXECUTE = re.compile(
    r"^\s*(build|make|create|add|apply|set|change|move|resize|duplicate|translate|"
    r"export|render|generate|draw|place|put|delete|remove|reset|clear|push|publish|"
    r"install|run|execute|do it)\b", re.I)
_QUESTION = re.compile(
    r"^(what|which|how|why|who|when|where|should|is|are|do|does|can|could|would|"
    r"tell me|list|show me)\b", re.I)


@dataclass
class Intent:
    """What the user asked for, how sure we are, and what it would take to comply."""

    type: IntentType
    confidence: float
    requires_authorization: bool = False
    consequential: list[str] = field(default_factory=list)
    entities: dict[str, Any] = field(default_factory=dict)
    signals: list[str] = field(default_factory=list)
    text: str = ""

    @property
    def is_answerable(self) -> bool:
        """True when the request must be answered rather than executed."""
        return self.type in (IntentType.QUESTION, IntentType.EXPLANATION,
                             IntentType.SELF_INTROSPECTION)

    @property
    def mutates(self) -> bool:
        return self.type in (IntentType.EXECUTION, IntentType.EXPERIMENTATION)

    def to_json(self) -> dict[str, Any]:
        return {"type": self.type.value, "confidence": round(self.confidence, 3),
                "requires_authorization": self.requires_authorization,
                "consequential": self.consequential, "entities": self.entities,
                "signals": self.signals}


def extract_entities(text: str) -> dict[str, Any]:
    """What the request names: canvas size, quoted copy, colours, formats."""
    entities: dict[str, Any] = {}
    size = re.search(r"(\d{2,5})\s*[x\u00d7]\s*(\d{2,5})", text)
    if size:
        entities["size"] = [int(size.group(1)), int(size.group(2))]
    quoted = re.search(r"[\"\u201c]([^\"\u201d]{2,120})[\"\u201d]", text)
    if not quoted:
        quoted = re.search(
            r"(?<![A-Za-z])['\u2018]([^'\u2019\n]{2,80})['\u2019](?![A-Za-z])", text)
    if quoted:
        entities["quoted_text"] = quoted.group(1)
    colours = re.findall(r"#[0-9a-fA-F]{6}\b", text)
    if colours:
        entities["colours"] = [c.lower() for c in colours]
    fmt = re.search(r"\b(png|jpe?g|pdf|svg|webp)\b", text, re.I)
    if fmt:
        entities["format"] = fmt.group(1).lower()
    return entities


def classify(text: str) -> Intent:
    """Classify one message. Order matters: the most specific signal wins."""
    stripped = (text or "").strip()
    low = stripped.lower()
    entities = extract_entities(stripped)

    if not stripped:
        return Intent(IntentType.QUESTION, 0.3, signals=["empty"], entities=entities, text=text)

    # 1. Questions about this system come first: they are answerable from records and must
    #    never be mistaken for instructions that happen to share words.
    if classify_self(stripped) is not None:
        return Intent(IntentType.SELF_INTROSPECTION, 0.9,
                      signals=[f"self:{classify_self(stripped)}"], entities=entities, text=text)

    consequential = [m.group(0).lower() for m in CONSEQUENTIAL_VERBS.finditer(stripped)]

    # 2. Experimentation: asks for measurement, not for a change to the deliverable.
    if _EXPERIMENT.search(low) and re.search(r"\b(run|try|test|measure|compare)\b", low):
        return Intent(IntentType.EXPERIMENTATION, 0.75,
                      requires_authorization=bool(consequential),
                      consequential=consequential, signals=["experiment verb"],
                      entities=entities, text=text)

    # 3. Explanation: asks how or why something works.
    if _EXPLAIN.search(low) and not _EXECUTE.match(stripped):
        return Intent(IntentType.EXPLANATION, 0.8, signals=["explain verb"],
                      entities=entities, text=text)

    # 4. Planning: asks for a plan rather than its execution.
    if _PLAN.search(low) and not _EXECUTE.match(stripped):
        return Intent(IntentType.PLANNING, 0.78, signals=["plan verb"],
                      entities=entities, text=text)

    # 5. Execution: an imperative at the start of the sentence.
    if _EXECUTE.match(stripped):
        return Intent(IntentType.EXECUTION, 0.85,
                      requires_authorization=bool(consequential),
                      consequential=consequential, signals=["imperative verb"],
                      entities=entities, text=text)

    # 6. A question anywhere else, including one without a question mark.
    if _QUESTION.match(stripped) or stripped.endswith("?"):
        return Intent(IntentType.QUESTION, 0.7, signals=["question form"],
                      entities=entities, text=text)

    # 7. Unmarked statement: treat as a question, the safe default (no mutation).
    return Intent(IntentType.QUESTION, 0.45, signals=["unmarked default"],
                  entities=entities, text=text)


def authorization_message(intent: Intent) -> str:
    """What to say when a consequential action lacks a grant."""
    what = ", ".join(intent.consequential[:3]) or "that action"
    return (f"That request would {what} and I have not been authorised to do it. "
            f"If you want it, say the same thing with explicit authorisation "
            f"(allow_actions=authorized), and I will run it and report the result.")
