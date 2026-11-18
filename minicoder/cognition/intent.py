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
import unicodedata
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


# ---------------------------------------------------------------------------
# Detection layer.
#
# Phase 5 note: this is *detection*, not enforcement.  The audit showed that
# authorization decided from surface form alone (and decided too early) let 12 of
# 18 destructive rephrasings through.  Enforcement now lives at the tool
# boundary (``minicoder.security.guard``), so a classifier miss cannot execute
# anything; a classifier false positive only costs an unnecessary refusal.
# ---------------------------------------------------------------------------

# Verbs that change the world irreversibly or reach outside the sandbox.
CONSEQUENTIAL_VERBS = re.compile(
    r"\b(delete|remove|destroy|wipe|erase|drop|reset|overwrite|clear|purge|"
    r"trash|scrap|discard|ditch|nuke|obliterate|strip|dispose|"
    r"push|publish|deploy|send|upload|export|download|install|uninstall|"
    r"truncate|replace all|rm)\b", re.I)

# Phrases that express the same consequences without a consequential verb.  The
# audit's bypass list is reproduced here deliberately, and generalised: the point
# is to cover the *meaning* ("start again", "throw it away"), not the exact
# strings that were tested.
_RISK_PHRASES: tuple[tuple[re.Pattern[str], str], ...] = (
    (re.compile(r"\bfrom scratch\b|\bstart (over|again|anew)\b|\bfresh start\b", re.I),
     "restart_from_scratch"),
    (re.compile(r"\b(blank|empty|clean) (canvas|page|board|project|slate)\b", re.I),
     "blank_canvas"),
    (re.compile(r"\bmake (it|this|the \w+) (empty|blank|disappear|go away)\b", re.I),
     "make_empty"),
    (re.compile(r"\b(get rid of|dispose of|throw (it|them|that|this|everything)? ?(away|out))\b", re.I),
     "get_rid_of"),
    (re.compile(r"\btake (it|them|that|those|everything) (out|off|down|away)\b", re.I),
     "take_out"),
    (re.compile(r"\b(scrap|ditch|shelve|bin|junk) (it|this|that|the \w+|everything)\b", re.I),
     "discard"),
    (re.compile(r"\b(start (it )?(all )?over|begin again|back to square one)\b", re.I),
     "start_over"),
    (re.compile(r"\b(nuke|annihilate|obliterate|flatten) (the|this|everything|it)\b", re.I),
     "destroy"),
    (re.compile(r"\b(remove|clear|delete|drop) (the )?(entire|whole|all|every) (project|design|canvas|board|work)\b", re.I),
     "remove_everything"),
    (re.compile(r"\b(entire|whole) (project|design|canvas|board)\b", re.I),
     "whole_project"),
    (re.compile(r"\b(everything|all of it|all of them|all the layers|every layer|all layers)\b", re.I),
     "everything_scope"),
    (re.compile(r"\b(write|save|dump|export) (it |this |the project )?to\b", re.I),
     "write_outside"),
    (re.compile(r"\b(paste|print|show|reveal|leak|exfiltrate|send) (me )?(the |your )?"
                r"(token|key|secret|credentials?|password)\b", re.I),
     "secret_access"),
    (re.compile(r"\b(reset|drop|wipe|truncate) (the )?(database|db|memory|brain)\b", re.I),
     "reset_database"),
)

# A question that *asks for an action* ("could you delete…") is an instruction;
# a question *about* an action ("how do I delete…") is not.
_REQUEST_FORM = re.compile(
    r"^\s*(could|can|would|will|are you able to|do you mind|please|kindly|go ahead and|"
    r"i want you to|i need you to|let'?s)\b", re.I)
_INFORMATIONAL = re.compile(
    r"^\s*(how (do|can|would|should) (i|you|we)|what (happens|would happen) if|"
    r"should i|is it (safe|possible) to)\b",
    re.I)
_NEGATION = re.compile(
    r"\b(do not|don'?t|dont|never|must not|mustn'?t|should not|shouldn'?t|stop|without|"
    r"no need to|not going to|won'?t)\b", re.I)

_EXPLAIN = re.compile(r"\b(explain|why (does|is|do)|how (does|do|is) .* work|"
                      r"what does .* mean|difference between|describe)\b", re.I)
_PLAN = re.compile(r"\b(plan|outline|steps|approach|strategy|how would you|"
                   r"what would you do|walk me through)\b", re.I)
_EXPERIMENT = re.compile(r"\b(experiment|benchmark|measure|run a test|try .* and (see|measure)|"
                         r"ablation|compare .* against)\b", re.I)
_EXECUTE = re.compile(
    r"^\s*(build|make|create|add|apply|set|change|move|resize|duplicate|translate|"
    r"export|render|generate|draw|place|put|delete|remove|reset|clear|push|publish|"
    r"install|run|execute|do it|"
    # Phase 5: verbs the bypass corpus used, which the Phase 4 list missed.
    r"wipe|erase|purge|trash|scrap|discard|ditch|nuke|obliterate|blank|empty|"
    r"start|restart|begin|throw|take|strip|drop|"
    r"get rid of)\b", re.I)

_QUESTION = re.compile(
    r"^(what|which|how|why|who|when|where|should|is|are|do|does|can|could|would|"
    r"tell me|list|show me)\b", re.I)

_LEET = str.maketrans({"0": "o", "1": "l", "3": "e", "4": "a", "5": "s", "7": "t", "8": "b", "@": "a", "$": "s"})
_ZERO_WIDTH = re.compile(r"[\u200b-\u200f\u2060\ufeff]")


def normalize_for_detection(text: str) -> str:
    """Lower-case, de-obfuscated text used *only* for risk detection.

    Handles the trivial evasions the audit used: digit substitution ("d3lete"),
    zero-width characters, Cyrillic/Greek homoglyphs and padded whitespace.
    """
    s = _ZERO_WIDTH.sub("", text or "")
    s = unicodedata.normalize("NFKC", s)
    s = "".join(
        {"а": "a", "е": "e", "о": "o", "р": "p", "с": "c", "х": "x", "у": "y", "і": "i"}.get(c, c)
        for c in s
    )
    s = s.translate(_LEET)
    return re.sub(r"\s+", " ", s).strip().lower()


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
    risk: float = 0.0          # 0..1 detection confidence that the request is destructive
    negated: bool = False      # "do not delete …" — a refusal-shaped request
    informational: bool = False  # "how do I delete …" — a question, not an instruction

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
                "signals": self.signals, "risk": round(self.risk, 3),
                "negated": self.negated, "informational": self.informational}


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


def detect_risk(text: str) -> tuple[list[str], float]:
    """Consequential signals in ``text`` plus a 0..1 risk score."""
    probe = normalize_for_detection(text)
    signals: list[str] = []

    for m in CONSEQUENTIAL_VERBS.finditer(probe):
        verb = m.group(0).lower()
        if verb not in signals:
            signals.append(verb)
    for pattern, label in _RISK_PHRASES:
        if pattern.search(probe) and label not in signals:
            signals.append(label)

    # A consequential verb plus a whole-scope word ("everything", "all layers")
    # is a stronger signal than either alone.
    score = 0.0
    if signals:
        score = 0.45
    if any(s in signals for s in ("everything_scope", "whole_project", "remove_everything",
                                 "reset_database", "secret_access", "destroy", "write_outside")):
        score = min(1.0, score + 0.4)
    if len(signals) >= 3:
        score = min(1.0, score + 0.15)
    return signals, round(score, 3)


def classify(text: str) -> Intent:
    """Classify one message.

    Phase 5 ordering fix: the type is decided first, then authorization is
    derived from the *complete* risk picture.  In Phase 4 the authorization flag
    was computed before the final type/verb scan, so any phrasing that only later
    reclassified as a command skipped the gate entirely.
    """
    stripped = (text or "").strip()
    low = stripped.lower()
    entities = extract_entities(stripped)
    probe = normalize_for_detection(stripped)

    if not stripped:
        return Intent(IntentType.QUESTION, 0.3, signals=["empty"], entities=entities, text=text)

    risk_signals, risk = detect_risk(stripped)
    negated = bool(_NEGATION.search(probe)) and bool(risk_signals)
    informational = bool(_INFORMATIONAL.match(probe))
    request_form = bool(_REQUEST_FORM.match(probe))
    imperative = bool(_EXECUTE.match(stripped) or _EXECUTE.match(probe))

    # 1. Questions about this system come first: they are answerable from records.
    if classify_self(stripped) is not None and not risk_signals:
        return Intent(IntentType.SELF_INTROSPECTION, 0.9,
                      signals=[f"self:{classify_self(stripped)}"], entities=entities, text=text)

    # 2. A negated destructive request ("do not delete anything") is refused-shaped:
    #    nothing should run, and it is *not* a green light for the same action.
    if negated:
        return Intent(IntentType.QUESTION, 0.6, requires_authorization=True,
                      consequential=risk_signals, signals=risk_signals + ["negated"],
                      entities=entities, text=text, risk=risk, negated=True)

    # 3. A question *about* an action ("how do I delete a layer?") is informational.
    if informational and risk_signals and not request_form:
        return Intent(IntentType.QUESTION, 0.7, requires_authorization=False,
                      consequential=risk_signals, signals=risk_signals + ["informational"],
                      entities=entities, text=text, risk=risk, informational=True)

    # 4. A request-shaped question ("could you delete all the layers?") is an
    #    instruction with a question mark on it.
    if request_form and imperative or (request_form and risk_signals):
        return Intent(IntentType.EXECUTION, 0.8, requires_authorization=bool(risk_signals),
                      consequential=risk_signals, signals=risk_signals + ["request form"],
                      entities=entities, text=text, risk=risk)

    # 5. Experimentation.
    if _EXPERIMENT.search(low) and re.search(r"\b(run|try|test|measure|compare)\b", low):
        return Intent(IntentType.EXPERIMENTATION, 0.75,
                      requires_authorization=bool(risk_signals),
                      consequential=risk_signals, signals=risk_signals + ["experiment verb"],
                      entities=entities, text=text, risk=risk)

    # 6. Explanation.
    if _EXPLAIN.search(low) and not imperative:
        return Intent(IntentType.EXPLANATION, 0.8, signals=["explain verb"],
                      entities=entities, text=text, risk=risk)

    # 7. Planning.
    if _PLAN.search(low) and not imperative:
        return Intent(IntentType.PLANNING, 0.78, signals=["plan verb"],
                      entities=entities, text=text, risk=risk)

    # 8. Execution: an imperative, or a bare destructive phrase ("blank canvas").
    if imperative or (risk_signals and risk >= 0.6):
        return Intent(IntentType.EXECUTION, 0.85,
                      requires_authorization=bool(risk_signals),
                      consequential=risk_signals, signals=risk_signals + ["imperative"],
                      entities=entities, text=text, risk=risk)

    # 9. A question anywhere else.  Ambiguous consequential requests fail closed:
    #    the type may be a question, but the authority flag is set from the risk
    #    picture, not from the sentence shape (this is the Phase 4 ordering bug).
    if _QUESTION.match(stripped) or stripped.endswith("?"):
        return Intent(IntentType.QUESTION, 0.7, requires_authorization=bool(risk_signals),
                      consequential=risk_signals, signals=risk_signals + ["question form"],
                      entities=entities, text=text, risk=risk)

    # 10. Unmarked statement: the safe default (no mutation, still fail closed
    #     when the wording is consequential).
    return Intent(IntentType.QUESTION, 0.45, requires_authorization=bool(risk_signals),
                  consequential=risk_signals, signals=risk_signals + ["unmarked default"],
                  entities=entities, text=text, risk=risk)


def authorization_message(intent: Intent) -> str:
    """What to say when a consequential action lacks a grant."""
    what = ", ".join(intent.consequential[:3]) or "that action"
    return (f"That request would {what} and no authorization grant covers it, so I have not "
            f"run it. Mint a single-use grant for this exact instruction and retry: "
            f"POST /api/security/grant with action=editor.instruction and the instruction hash.")
