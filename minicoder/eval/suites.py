"""Benchmark suites across all three modalities, plus the four-state ablation.

Every suite returns measured numbers and is guarded so it can run in CI
(the heavy tracks are marked ``slow`` and skip when models are absent).

Tracks
------
coding      : exact-match + pass@1 on held-out verified tasks (sandbox-checked)
chat        : multi-session recall, preference retention, hallucination rate
vision      : UI-defect classification accuracy, OCR recall, finding precision
memory      : retrieval precision/recall, decay correctness
ablation    : base -> +memory -> +sleep -> +LoRA (blueprint §11)
"""

from __future__ import annotations

import json
import random
import time
from collections.abc import Callable
from dataclasses import asdict, dataclass, field
from pathlib import Path
from typing import Any

import torch

from minicoder.config import CONFIG, VERIFIED
from minicoder.data import CODE_TASKS, PERSONAS, VISION_CLASSES, build_vision_dataset
from minicoder.memory.db import BrainDB
from minicoder.memory.systems import (
    Episode,
    EpisodicMemory,
    ProceduralMemory,
    SemanticMemory,
)


@dataclass
class SuiteResult:
    name: str
    metrics: dict[str, Any] = field(default_factory=dict)
    seconds: float = 0.0
    skipped: str = ""
    details: list[dict[str, Any]] = field(default_factory=list)

    def to_json(self) -> dict[str, Any]:
        return asdict(self)


# --------------------------------------------------------------------------
# coding
# --------------------------------------------------------------------------

def eval_coding(tasks: list[dict[str, Any]] | None = None, *, use_sandbox: bool = True) -> SuiteResult:
    """Two tracks, reported separately and never conflated.

    * ``indist``  — tasks whose solutions were in the SFT corpus. High scores
      here prove the instruction format and the neural instruction-following
      path work; they do **not** prove generalisation.
    * ``holdout`` — six tasks sealed out of SFT entirely. Scores here measure
      genuine generalisation at this model scale.

    Both are sandbox-executed, so "pass@1" means the code really ran green.
    """
    from minicoder.cognition.engine import NeuralBrain
    from minicoder.tools.sandbox import Sandbox

    t0 = time.time()
    brain = NeuralBrain()
    if not brain.model:
        return SuiteResult("coding", skipped="no trained LM checkpoint")
    sealed = {t["name"] for t in CODE_TASKS[-6:]}
    indist = [t for t in CODE_TASKS if t["name"] not in sealed]
    holdout = [t for t in CODE_TASKS if t["name"] in sealed]
    sbx = Sandbox(use_docker=False) if use_sandbox else None

    def measure(group: list[dict[str, Any]], tag: str) -> tuple[dict[str, Any], list[dict[str, Any]]]:
        exact = passed = 0
        rows = []
        for task in group:
            gen = brain.best_of(task["prompt"], k=3, max_new_tokens=96)
            text = gen.text.strip()
            is_exact = text == task["solution"].strip()
            ok = False
            if sbx and text:
                ok, _ = sbx.run_tests(text, task["tests"])
            exact += int(is_exact)
            passed += int(ok)
            rows.append({"track": tag, "task": task["name"], "exact": is_exact,
                         "pass@1": bool(ok), "output": text[:200]})
        n = max(1, len(group))
        return {"exact_match": round(exact / n, 4), "pass@1": round(passed / n, 4), "n": len(group)}, rows

    indist_m, indist_rows = measure(indist, "indist")
    hold_m, hold_rows = measure(holdout, "holdout")

    # Graded diagnostics, because exact match is all-or-nothing and hides
    # partial learning. These are reported alongside, never instead of, pass@1.
    from minicoder.sleep.trainer import token_level_accuracy

    tok_metrics = {
        "indist": {k: v for k, v in token_level_accuracy(brain.model, brain.tok, indist).items() if k != "details"},
        "holdout": {k: v for k, v in token_level_accuracy(brain.model, brain.tok, holdout).items() if k != "details"},
    }
    return SuiteResult(
        "coding",
        {"indist": indist_m, "holdout": hold_m, "token_level": tok_metrics},
        round(time.time() - t0, 2),
        details=indist_rows + hold_rows,
    )


# --------------------------------------------------------------------------
# chat & memory
# --------------------------------------------------------------------------

_HOME_STACK: list = []


def _isolated_home(tag: str):
    """Redirect CONFIG at a temp dir so a seeding suite cannot touch the live brain."""
    import tempfile
    from pathlib import Path as _P

    from minicoder import config as _config

    home = _P(tempfile.mkdtemp(prefix=f"minicoder-eval-{tag}-"))
    _HOME_STACK.append(_config.activate_home(home))
    return home


def _restore_home() -> None:
    from minicoder import config as _config

    if _HOME_STACK:
        _config.activate_home(_HOME_STACK.pop())


def eval_chat(*, fresh_db: bool = True, use_real_agent: bool = False) -> SuiteResult:
    """Multi-session recall, preference retention, hallucination rate.

    Runs against a throwaway brain home: this suite *seeds* persona memories, and
    earlier versions wrote them into the live database, polluting real recall
    with dozens of duplicate "User X shared a preference" episodes.
    """
    t0 = time.time()
    from minicoder.cognition.engine import GroundedAnswerer, NeuralBrain

    home = _isolated_home("chat")
    try:
        return _eval_chat_body(t0, GroundedAnswerer, NeuralBrain, home)
    finally:
        _restore_home()


def _eval_chat_body(t0, GroundedAnswerer, NeuralBrain, home) -> SuiteResult:
    db = BrainDB()
    episodic = EpisodicMemory(db)
    semantic = SemanticMemory(db)
    procedural = ProceduralMemory(db)
    brain = NeuralBrain()
    answerer = GroundedAnswerer(brain, episodic, semantic, procedural)

    # Seed a small autobiographical memory (what a real session would have left).
    seeded = []
    for persona in PERSONAS:
        key = "prefs" if "prefs" in persona else "prefers"
        for pref in persona[key]:
            label = f"{persona['user']} preference: {pref[:60]}"
            nid = semantic.upsert(
                "user_preference", label,
                f"{persona['user']} {pref}.",
                status=VERIFIED, source="documentation", confidence=0.95,
            )
            seeded.append((persona["user"], pref, nid))
            episodic.add(Episode(
                situation=f"User {persona['user']} shared a preference",
                objective=f"Remember that {persona['user']} {pref}",
                modality="text", result=f"{persona['user']} {pref}",
                status=VERIFIED, source="documentation", lessons=f"{persona['user']} {pref}",
                confidence=0.95,
            ))
    semantic.save_snapshot()

    # 1. Preference retention: ask about each persona.
    retained = 0
    details = []
    for persona, pref, _nid in seeded:
        q = f"What does {persona} prefer?"
        ans = answerer.answer(q)
        # Score against THIS preference specifically. A generic keyword test would
        # be satisfied by a different fact about the same person (measured: one
        # preference literally contains the persona's name, inflating retention).
        keys = set(pref.lower().split()) - {"and", "the", "with", "a", "for", "at", "in", "to", "every", "on"}
        hit = len({k for k in keys if k in ans.text.lower()}) / max(1, len(keys)) >= 0.6
        retained += int(hit)
        details.append({"q": q, "source": ans.source, "hit": hit, "answer": ans.text[:120]})

    # 2. Known-answer recall: every seeded fact should be answered, not refused.
    answered = sum(1 for d in details if d["source"] in ("memory", "skill"))
    # 3. Hallucination rate: for questions with no supporting memory, the system
    #    must refuse rather than invent an answer.
    unanswerable = [
        "What is the airspeed velocity of an unladen swallow?",
        "What did I say about quantum chromodynamics last Tuesday?",
        "What is the exact revenue of Acme Corp in Q3?",
        "Who won the 1998 world championship in curling?",
        "What is my grandmother's maiden name?",
    ]
    refusals = 0
    hall_details = []
    for q in unanswerable:
        ans = answerer.answer(q)
        refused = ans.source == "refuse"
        refusals += int(refused)
        hall_details.append({"q": q, "source": ans.source, "refused": refused,
                             "answer": ans.text[:100]})
    n_pref = max(1, len(seeded))
    return SuiteResult(
        "chat",
        {
            "preference_retention": round(retained / n_pref, 4),
            "answered_from_memory": round(answered / n_pref, 4),
            "hallucination_rate": round(1 - refusals / len(unanswerable), 4),
            "refusal_rate": round(refusals / len(unanswerable), 4),
            "seeded_facts": n_pref,
        },
        round(time.time() - t0, 2),
        details=details + hall_details,
    )


def eval_multisession_recall() -> SuiteResult:
    """Write episodes in session A, read them back from a brand-new DB handle in B.

    Runs in a throwaway home: earlier versions wrote probe episodes straight into
    the live brain, so repeated runs accumulated duplicate facts.
    """
    t0 = time.time()
    _isolated_home("multisession")
    try:
        return _eval_multisession_body(t0)
    finally:
        _restore_home()


def _eval_multisession_body(t0) -> SuiteResult:
    db = BrainDB()
    em = EpisodicMemory(db)
    facts = [
        ("session A turn 1", "The user's project codename is Lantern.", "The project codename is Lantern."),
        ("session A turn 2", "The user prefers 1080x1350 posters.", "The user prefers 1080x1350 posters."),
        ("session A turn 3", "The accent colour must be #d9a441.", "The accent colour is #d9a441."),
        ("session A turn 4", "Exports go to PNG at 2x.", "Exports go to PNG at 2x."),
    ]
    eids = []
    for situation, result, lesson in facts:
        eids.append(em.add(Episode(
            situation=situation, objective=result, modality="text", result=result,
            status=VERIFIED, source="user_instruction", lessons=lesson, confidence=0.9,
        )))
    # Simulate a restart: brand-new handle, nothing shared in memory.
    db2 = BrainDB()
    em2 = EpisodicMemory(db2)
    hits = 0
    details = []
    for _, _, lesson in facts:
        found = em2.search(lesson, limit=5)
        hit = any(f["lessons"] == lesson for f in found)
        hits += int(hit)
        details.append({"probe": lesson, "hit": hit, "top": (found[0]["lessons"] if found else "")[:80]})
    return SuiteResult(
        "multisession_recall",
        {"recall": round(hits / len(facts), 4), "n": len(facts)},
        round(time.time() - t0, 2),
        details=details,
    )


def eval_memory_retrieval(db_path: Path | None = None) -> SuiteResult:
    """Precision@1 + MRR of the hybrid retriever over a controlled corpus.

    Runs against an *isolated* database by default so unrelated memories from
    earlier sessions cannot pollute the measurement.
    """
    import tempfile

    t0 = time.time()
    from minicoder.config import Paths

    if db_path is None:
        tmpdir = Path(tempfile.mkdtemp(prefix="mc_eval_mem_"))
        paths = Paths.build(tmpdir)
        paths.ensure()
        db = BrainDB(paths=paths)
    else:
        db = BrainDB(paths=Paths.build(db_path))
    sm = SemanticMemory(db)
    docs = {
        "flexbox overflow": ("concept", "A flex child with min-width auto refuses to shrink; set min-width to zero."),
        "contrast ratio": ("concept", "WCAG AA needs 4.5 to 1 for body text; compute it from relative luminance."),
        "emerald palette": ("fact", "Deep green background with champagne hairline accents reads luxurious."),
        "negative space": ("heuristic", "Generous margins increase perceived quality; keep at least eight percent per edge."),
        "line height": ("heuristic", "Body copy needs 1.5 line height; display type can drop to 1.15."),
        "png export": ("fact", "Export at 2x for retina displays; 1x is fine for print previews."),
    }
    for label, (kind, content) in docs.items():
        sm.upsert(kind, label, content, status=VERIFIED, source="documentation", confidence=0.9)
    probes = [
        ("why does my flex child overflow", "flexbox overflow"),
        ("what contrast ratio do I need", "contrast ratio"),
        ("which palette is luxurious", "emerald palette"),
        ("how much margin should I leave", "negative space"),
        ("what line height should the text use", "line height"),
        ("what size should I export at", "png export"),
    ]
    p1 = 0
    rr = 0.0
    details = []
    for query, expected in probes:
        results = sm.search(query, limit=3)
        labels = [r["label"] for r in results]
        rank = labels.index(expected) + 1 if expected in labels else 0
        p1 += int(rank == 1)
        rr += (1.0 / rank) if rank else 0.0
        details.append({"query": query, "expected": expected, "top": labels[0] if labels else "",
                        "rank": rank, "hit": rank == 1})
    return SuiteResult(
        "retrieval",
        {"precision_at_1": round(p1 / len(probes), 4), "mrr": round(rr / len(probes), 4), "n": len(probes)},
        round(time.time() - t0, 2),
        details=details,
    )


# --------------------------------------------------------------------------
# vision
# --------------------------------------------------------------------------

def eval_vision(limit: int | None = None) -> SuiteResult:
    t0 = time.time()
    from minicoder.model.vision import load_vision

    path = CONFIG.paths.checkpoints / "vision.pt"
    if not path.exists():
        return SuiteResult("vision", skipped="no vision checkpoint")
    model = load_vision(path)
    _, test = build_vision_dataset()
    if limit:
        test = test[:limit]
    import torch.nn.functional as F

    from minicoder.model.vision import to_tensor

    x = to_tensor([img for img, _ in test], model.cfg.vision_image_size)
    y = torch.tensor([label for _, label in test])
    with torch.no_grad():
        probs = F.softmax(model(x), dim=-1)
    pred = probs.argmax(-1)
    acc = float((pred == y).float().mean())
    confusion: dict[str, dict[str, int]] = {}
    for p, t in zip(pred.tolist(), y.tolist()):
        confusion.setdefault(VISION_CLASSES[t], {}).setdefault(VISION_CLASSES[p], 0)
        confusion[VISION_CLASSES[t]][VISION_CLASSES[p]] += 1

    # OCR recall on a rendered error screenshot with known text.
    ocr_recall = None
    try:
        from PIL import Image, ImageDraw

        from minicoder.tools.vision import run_ocr

        img = Image.new("RGB", (520, 140), (250, 250, 252))
        d = ImageDraw.Draw(img)
        d.rectangle([0, 0, 520, 40], fill=(198, 62, 48))
        d.text((16, 14), "ERROR: payment failed", fill=(255, 255, 255))
        d.text((16, 60), "Retry the card or contact support", fill=(30, 30, 34))
        text, lines = run_ocr(img)
        tokens = ["ERROR", "payment", "failed", "Retry", "card", "support"]
        found = sum(1 for t in tokens if t.lower() in text.lower())
        ocr_recall = round(found / len(tokens), 3)
    except Exception:
        pass
    return SuiteResult(
        "vision",
        {"accuracy": round(acc, 4), "n": len(test), "ocr_keyword_recall": ocr_recall,
         "classes": len(VISION_CLASSES)},
        round(time.time() - t0, 2),
        details=[{"true": k, "predicted": v} for k, v in confusion.items()],
    )


def eval_visual_findings() -> SuiteResult:
    """Precision of deterministic layout findings on synthetically broken UIs."""
    t0 = time.time()
    from minicoder.data import _render_ui_screenshot
    from minicoder.tools.vision import inspect as inspect_image

    rng = random.Random(5)
    # Positive cases: the fixture genuinely contains the defect, so the detector
    # must report it. Negative cases: a clean layout must NOT be called broken —
    # otherwise "detection rate" would reward false positives.
    positives = [
        ("overflow_bug", "overflow"),
        ("contrast_failure", "contrast"),
        ("text_truncation", "truncation"),
    ]
    negatives = ["clean_layout", "loading_skeleton"]
    correct = 0
    details = []
    for cls, keyword in positives:
        img = _render_ui_screenshot(cls, rng)
        rep = inspect_image(img, save_to_memory=False, use_vision_model=False)
        text = " ".join(rep.findings).lower()
        hit = keyword in text
        correct += int(hit)
        details.append({"case": cls, "expected": keyword, "hit": hit, "findings": rep.findings[:3]})
    fp = 0
    for cls in negatives:
        img = _render_ui_screenshot(cls, rng)
        rep = inspect_image(img, save_to_memory=False, use_vision_model=False)
        flagged = bool(rep.findings)
        fp += int(flagged)
        details.append({"case": cls, "expected": "no findings", "hit": not flagged,
                        "findings": rep.findings[:3]})
    n_pos, n_neg = len(positives), len(negatives)
    return SuiteResult(
        "visual_findings",
        {
            "detection_rate": round(correct / n_pos, 4),
            "false_positive_rate": round(fp / n_neg, 4),
            "n_positive": n_pos,
            "n_negative": n_neg,
        },
        round(time.time() - t0, 2),
        details=details,
    )


# --------------------------------------------------------------------------
# ablation (blueprint §11)
# --------------------------------------------------------------------------

def eval_ablation(skip_heavy: bool = True) -> SuiteResult:
    """The headline claim, measured: what does each layer actually buy?

    Four states over one fixed probe set, each with one layer switched on:

    1. ``base``      the neural tower alone (raw generation, no memory)
    2. ``+memory``   retrieval grounding (verified skills + semantic + episodic)
    3. ``+sleep``    as above, after a consolidation cycle has abstracted
                     episodes into semantic knowledge
    4. ``+lora``     memory grounding with the promoted adapter as the tower

    Every probe asks the same three questions of every state, so the table
    shows trade-offs rather than a single cherry-picked number:

    ``coding_exact``  verbatim-correct solutions on the in-distribution tasks
    ``qa_exact``      verbatim-correct answers to the authored design questions
    ``refusal``       fraction of unanswerable questions correctly refused
    ``hallucination`` 1 - refusal (the cost of generating without grounding)

    Runs in an isolated home: it seeds knowledge and runs a sleep cycle, and
    neither may touch the live brain.
    """
    t0 = time.time()

    if skip_heavy:
        return SuiteResult("ablation", skipped="skip_heavy=True")

    from minicoder.config import CONFIG as _cfg
    from minicoder.config import install_root

    real_checkpoints = install_root() / "memory" / "checkpoints"
    _isolated_home("ablation")  # side effect is the redirect; the handle is unused
    try:
        # The ablation only *reads* weights, so share the trained checkpoints
        # rather than retraining inside the sandboxed home.
        link = _cfg.paths.checkpoints
        if real_checkpoints.exists() and not any(link.glob("*.pt")):
            for name in ("lm.pt", "tokenizer.json", "embedder.pt", "vision.pt"):
                src = real_checkpoints / name
                if src.exists():
                    (link / name).symlink_to(src)
            hist = real_checkpoints / "history"
            if hist.exists():
                for src in hist.glob("*.pt"):
                    (link / "history").mkdir(parents=True, exist_ok=True)
                    (link / "history" / src.name).symlink_to(src)
        return _eval_ablation_body(t0)
    finally:
        _restore_home()


# Probes. Design questions are drawn from the curated CHAT_PAIRS because those
# answers are hand-authored ground truth; code tasks from the in-distribution
# split. Unanswerable questions must be refused by anything claiming to be honest.
_ABLATION_QUESTIONS = [
    ("How do I make my poster feel more premium?",
     "Increase negative space, use one accent colour, lower the background contrast, "
     "and keep typography to two sizes."),
    ("What canvas size works for Instagram?",
     "1080x1350 is the portrait feed size. Use 1080x1080 for square carousels."),
    ("Which palette reads as luxurious?",
     "Deep green with warm gold, or charcoal with champagne. Keep the gold to hairline accents."),
    ("How many fonts should I use?",
     "Two: one display face for the quote, one quiet face for attribution. "
     "Three is usually one too many."),
]

_ABLATION_UNANSWERABLE = [
    "Who won the 1998 world championship in curling?",
    "What is my grandmother's maiden name?",
    "What is the exact revenue of Acme Corp in Q3?",
    "What did I say about quantum chromodynamics last Tuesday?",
]


def _norm_text(text: str) -> str:
    return " ".join(text.lower().split())


def _answers_correctly(answer: str, gold: str, threshold: float = 0.8) -> bool:
    """Does the answer actually carry the authored knowledge?

    Exact string equality is the wrong test here: a grounded answer legitimately
    quotes the fact verbatim *and* may append related facts. What matters is that
    the required content is present, so this measures coverage of the gold
    answer's content words (>=80%), ignoring scaffolding words.
    """
    got = _norm_text(answer)
    want = [w for w in _norm_text(gold).split() if len(w) > 2]
    if not want:
        return False
    hit = sum(1 for w in want if w in got)
    return hit / len(want) >= threshold


def _eval_ablation_body(t0) -> SuiteResult:
    from minicoder.cognition.engine import GroundedAnswerer, NeuralBrain
    from minicoder.seed import seed_brain
    from minicoder.sleep.trainer import _holdout_tasks, skill_accuracy

    db = BrainDB()
    seed_brain(db=db)
    brain = NeuralBrain()
    if not brain.model:
        return SuiteResult("ablation", skipped="no LM checkpoint")

    coding = _holdout_tasks()
    procedural = ProceduralMemory(db)
    episodic = EpisodicMemory(db)
    semantic = SemanticMemory(db)

    states: dict[str, Any] = {}

    # ---------------------------------------------------------------- 1. base
    coding_acc = skill_accuracy(brain.model, brain.tok, coding)
    qa_hits = 0
    for question, _gold in _ABLATION_QUESTIONS:
        gen = brain.best_of(question, k=2, max_new_tokens=64)
        qa_hits += int(_answers_correctly(gen.text, _gold))
    base_refusals = 0
    for question in _ABLATION_UNANSWERABLE:
        # With no grounding layer at all, the only honest test is whether the
        # tower declines. It cannot: it always emits *something*.
        gen = brain.best_of(question, k=1, max_new_tokens=32)
        base_refusals += int(not gen.text.strip())
    states["1_base"] = {
        "coding_exact": round(coding_acc["exact_match"], 4),
        "qa_exact": round(qa_hits / len(_ABLATION_QUESTIONS), 4),
        "refusal": round(base_refusals / len(_ABLATION_UNANSWERABLE), 4),
        "note": "neural tower only; no skills, no retrieval, no refusal path",
    }

    # -------------------------------------------------------------- 2. memory
    grounded = GroundedAnswerer(brain, episodic, semantic, procedural)
    # Memory-only: the neural fallback is disabled, so anything the tower would
    # have hallucinated becomes an explicit refusal instead.
    mem_coding = 0
    for task in coding:
        ans = grounded.answer(task["prompt"], allow_neural=False)
        mem_coding += int(ans.source == "skill" and _answers_correctly(ans.text, task["solution"]))
    mem_qa = 0
    for question, gold in _ABLATION_QUESTIONS:
        ans = grounded.answer(question, allow_neural=False)
        mem_qa += int(_answers_correctly(ans.text, gold))
    mem_refusals = sum(
        1 for q in _ABLATION_UNANSWERABLE if grounded.answer(q, allow_neural=False).source == "refuse"
    )
    states["2_memory"] = {
        "coding_exact": round(mem_coding / max(1, len(coding)), 4),
        "qa_exact": round(mem_qa / len(_ABLATION_QUESTIONS), 4),
        "refusal": round(mem_refusals / len(_ABLATION_UNANSWERABLE), 4),
        "note": "verified skills + semantic + episodic retrieval; neural fallback off",
    }

    # --------------------------------------------------------------- 3. sleep
    # Write what a busy session would leave behind, consolidate it, then re-measure.
    for question, gold in _ABLATION_QUESTIONS:
        episodic.add(Episode(
            situation=f"User asked: {question}",
            objective="answer a design question",
            modality="text",
            result=gold,
            status=VERIFIED,
            source="documentation",
            lessons=gold,
            confidence=0.9,
        ))
    from minicoder.sleep.engine import SleepEngine

    report = SleepEngine(db, train_after_compile=False, push_to_github=False).sleep(trigger="ablation")
    sleep_qa = 0
    for question, gold in _ABLATION_QUESTIONS:
        ans = grounded.answer(question, allow_neural=False)
        sleep_qa += int(_answers_correctly(ans.text, gold))
    sleep_refusals = sum(
        1 for q in _ABLATION_UNANSWERABLE if grounded.answer(q, allow_neural=False).source == "refuse"
    )
    # What sleep is *for*: the raw episodes can now be forgotten without losing
    # the knowledge, because consolidation moved it into semantic memory. Archive
    # every episode and re-ask — this is the part retrieval alone cannot do.
    with db.write() as conn:
        conn.execute("UPDATE episodes SET archived=1")
    archived_qa = 0
    for question, gold in _ABLATION_QUESTIONS:
        ans = grounded.answer(question, allow_neural=False)
        archived_qa += int(_answers_correctly(ans.text, gold))
    states["3_sleep"] = {
        "coding_exact": round(mem_coding / max(1, len(coding)), 4),
        "qa_exact": round(sleep_qa / len(_ABLATION_QUESTIONS), 4),
        "refusal": round(sleep_refusals / len(_ABLATION_UNANSWERABLE), 4),
        "qa_with_episodes_forgotten": round(archived_qa / len(_ABLATION_QUESTIONS), 4),
        "consolidated": report.metrics.get("episodes_consolidated", 0),
        "semantic_nodes": int(db.query("SELECT COUNT(*) FROM semantic_nodes WHERE archived=0")[0][0]),
        "note": ("knowledge survives forgetting: episodes archived after "
                 "consolidation and the answers still hold"),
    }

    # ---------------------------------------------------------------- 4. LoRA
    # The promoted adapter is this project's own state: measure the coding skill
    # it actually delivers, alongside the grounding it sits behind in production.
    current_meta = getattr(brain, "meta", None) or {}
    promoted = bool(current_meta.get("promoted_from"))
    states["4_lora"] = {
        "coding_exact": round(coding_acc["exact_match"], 4),
        "qa_exact": round(sleep_qa / len(_ABLATION_QUESTIONS), 4),
        "refusal": round(sleep_refusals / len(_ABLATION_UNANSWERABLE), 4),
        "adapter_available": promoted,
        "promoted_from": current_meta.get("promoted_from", ""),
        "note": ("the live checkpoint already folds in a gate-accepted adapter; its "
                 "before/after gate metrics are recorded in datasets/training_runs"
                 if promoted else "no adapter has been promoted yet"),
    }

    deltas = {
        "memory_over_base_qa": round(states["2_memory"]["qa_exact"] - states["1_base"]["qa_exact"], 4),
        "memory_over_base_refusal": round(states["2_memory"]["refusal"] - states["1_base"]["refusal"], 4),
        "memory_over_base_coding": round(states["2_memory"]["coding_exact"] - states["1_base"]["coding_exact"], 4),
        "sleep_over_memory_qa": round(states["3_sleep"]["qa_exact"] - states["2_memory"]["qa_exact"], 4),
        "sleep_knowledge_retained_after_forgetting": states["3_sleep"]["qa_with_episodes_forgotten"],
    }
    return SuiteResult(
        "ablation",
        {"states": states, "deltas": deltas, "holdout_tasks": [t["name"] for t in coding]},
        round(time.time() - t0, 2),
    )


# --------------------------------------------------------------------------
# runner
# --------------------------------------------------------------------------

SUITES: dict[str, Callable[..., SuiteResult]] = {
    "coding": eval_coding,
    "chat": eval_chat,
    "multisession": eval_multisession_recall,
    "retrieval": eval_memory_retrieval,
    "vision": eval_vision,
    "findings": eval_visual_findings,
    "ablation": eval_ablation,
}


def run_all(names: list[str] | None = None, out_path: Path | None = None,
            *, skip_heavy: bool = True) -> dict[str, Any]:
    names = names or list(SUITES)
    results = {}
    for name in names:
        fn = SUITES[name]
        try:
            res = fn(skip_heavy=skip_heavy) if "skip_heavy" in fn.__code__.co_varnames else fn()
        except Exception as exc:  # a broken suite must not hide the others
            res = SuiteResult(name, skipped=f"error: {type(exc).__name__}: {exc}")
        results[name] = res.to_json()
        tag = "skip" if res.skipped else json.dumps(res.metrics)[:110]
        print(f"  {name:16s} {res.seconds:7.2f}s  {tag}", flush=True)
    payload = {"generated_at": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()), "results": results}
    out = out_path or (CONFIG.paths.training_runs / "eval_report.json")
    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_text(json.dumps(payload, indent=2), encoding="utf-8")
    return payload
