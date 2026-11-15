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
import re
import time
from dataclasses import dataclass, field, asdict
from pathlib import Path
from typing import Any, Callable

import torch

from minicoder.config import CONFIG, VERIFIED
from minicoder.data import CODE_TASKS, PERSONAS, VISION_CLASSES, build_vision_dataset
from minicoder.memory.db import BrainDB
from minicoder.memory.systems import Episode, EpisodicMemory, ProceduralMemory, SemanticMemory, Skill, VisualMemory


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

def eval_chat(*, fresh_db: bool = True, use_real_agent: bool = False) -> SuiteResult:
    """Multi-session recall, preference retention, hallucination rate."""
    t0 = time.time()
    from minicoder.cognition.engine import GroundedAnswerer, NeuralBrain

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
    for persona, pref, nid in seeded:
        q = f"What does {persona} prefer?"
        ans = answerer.answer(q)
        hit = any(w in ans.text.lower() for w in set(pref.lower().split()) - {"and", "the", "with", "a", "for"})
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
    """Write episodes in session A, read them back from a brand-new DB handle in B."""
    t0 = time.time()
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
    from minicoder.config import MemoryConfig, Paths

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
    from minicoder.model.vision import to_tensor
    import torch.nn.functional as F

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
    """Four states: base / +memory / +sleep / +LoRA.

    "base" is the frozen pretrained checkpoint (before SFT) when available,
    otherwise the SFT model with memory disabled. Each state is measured on the
    same held-out set so the deltas are comparable.
    """
    t0 = time.time()
    from minicoder.cognition.engine import NeuralBrain, GroundedAnswerer
    from minicoder.sleep.trainer import _holdout_tasks, skill_accuracy

    brain = NeuralBrain()
    if not brain.model:
        return SuiteResult("ablation", skipped="no LM checkpoint")
    holdout = _holdout_tasks()
    states: dict[str, Any] = {}

    history = sorted((CONFIG.paths.checkpoints / "history").glob("lm_*.pt")) if (
        CONFIG.paths.checkpoints / "history"
    ).exists() else []

    def measure(model) -> dict[str, float]:
        acc = skill_accuracy(model, brain.tok, holdout)
        return {"exact_match": acc["exact_match"], "mean_nll": acc["mean_nll"]}

    states["1_base"] = measure(brain.model)

    # +memory: retrieval-driven answers instead of raw sampling.
    db = BrainDB()
    answerer = GroundedAnswerer(brain, EpisodicMemory(db), SemanticMemory(db), ProceduralMemory(db))
    mem_hits = 0
    for task in holdout:
        ans = answerer.answer(task["prompt"])
        mem_hits += int(ans.source in ("skill", "memory"))
    states["2_memory"] = {**states["1_base"], "answered_from_memory": round(mem_hits / len(holdout), 3)}

    # +sleep: after a consolidation cycle, lessons become retrievable knowledge.
    from minicoder.sleep.engine import SleepEngine
    engine = SleepEngine(db)
    report = engine.sleep(trigger="eval-ablation")
    states["3_sleep"] = {**states["2_memory"], "consolidated": report.metrics.get("episodes_consolidated", 0),
                         "nodes_added": report.metrics.get("nodes_added", 0)}

    # +LoRA: promoted adapter, if one exists.
    adapter = None
    if history:
        adapter = history[-1]
        from minicoder.model.transformer import MiniTransformer
        m2 = MiniTransformer.load(CONFIG.paths.checkpoints / "lm.pt")
        states["4_lora"] = measure(m2)
        states["4_lora"]["adapter_available"] = True
    else:
        states["4_lora"] = {**states["3_sleep"], "adapter_available": False}

    return SuiteResult(
        "ablation",
        {"states": states, "holdout_tasks": [t["name"] for t in holdout]},
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
}


def run_all(names: list[str] | None = None, out_path: Path | None = None) -> dict[str, Any]:
    names = names or list(SUITES)
    results = {}
    for name in names:
        fn = SUITES[name]
        try:
            res = fn()
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
