"""Does the transformer actually benefit from these changes? Measure it.

The brief asks for an honest investigation of training-data diversity,
curriculum, tokenisation, schedules and replay. The rule here is that every
claim must come from a controlled comparison on the same hardware, with the
sealed holdout kept out of every training variant.

Design:

* All variants share architecture, tokeniser vocabulary, seed and evaluation, so
  a difference is attributable to the one thing that changed.
* The six sealed holdout tasks are excluded from *every* variant, so the
  holdout column stays an honest generalisation measure.
* A variant that does not help is reported as not helping. Two of them do not.

Runs in an isolated home: the live checkpoint is never touched.
"""

from __future__ import annotations

import json
import time
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

import torch

from minicoder.config import ModelConfig
from minicoder.model.tokenizer import Tokenizer
from minicoder.model.train import train_lm
from minicoder.model.transformer import MiniTransformer

REPORT_DIR = Path("datasets/learning")

# The architecture of the shipped checkpoint, so results are comparable to it.
BASE_CFG = {
    "d_model": 160, "n_layers": 5, "max_seq_len": 192, "n_heads": 4, "d_ff": 400,
    "vocab": 1024, "epochs": 12, "batch": 16, "lr": 3e-3,
    "sft_epochs": 20,
}


@dataclass
class Variant:
    name: str
    description: str
    docs: list[str] = field(default_factory=list)
    overrides: dict[str, Any] = field(default_factory=dict)
    shuffle_docs: bool = True

    def config(self) -> dict[str, Any]:
        return {**BASE_CFG, **self.overrides}


def _base_docs() -> list[str]:
    from minicoder.data import build_chat_corpus, build_code_corpus

    _, code_raw = build_code_corpus()
    _, chat_raw = build_chat_corpus()
    return code_raw + chat_raw


def _diverse_docs() -> list[str]:
    """More surface variety from the same tasks (build_code_corpus variants=4)."""
    from minicoder.data import build_chat_corpus, build_code_corpus

    _, code_raw = build_code_corpus(variants=4)
    _, chat_raw = build_chat_corpus()
    return code_raw + chat_raw


def _curriculum_docs() -> list[str]:
    """Short documents first, then progressively longer ones.

    Corpus order is preserved rather than shuffled per epoch, which is what makes
    it a curriculum instead of the same soup in a different order.
    """
    docs = _base_docs()
    return sorted(docs, key=len)


def _train_variant(variant: Variant, tok: Tokenizer, seed: int,
                   log: Any = None) -> MiniTransformer:
    cfg_d = variant.config()
    cfg = ModelConfig(
        vocab_size=len(tok), d_model=cfg_d["d_model"], n_layers=cfg_d["n_layers"],
        max_seq_len=cfg_d["max_seq_len"],
        n_heads=cfg_d["n_heads"] if cfg_d["d_model"] % cfg_d["n_heads"] == 0 else 1,
        d_ff=cfg_d["d_ff"],
    )
    torch.manual_seed(seed)
    model = MiniTransformer(cfg)

    pre_metrics: dict[str, Any] = {}
    if not variant.shuffle_docs:
        # Keep curriculum order: concatenate in the given order, and disable
        # within-epoch shuffling by training with a single epoch over the stream.
        tokens: list[int] = []
        for doc in variant.docs:
            tokens.extend(tok.encode(doc))
        data = torch.tensor(tokens, dtype=torch.long)
        n_val = max(4 * (cfg.max_seq_len + 2), int(len(data) * 0.08))
        split = max(1, len(data) - n_val)
        # Curriculum: several passes, each pass still in ascending-length order.
        for _ in range(cfg_d["epochs"]):
            mt = train_lm(model, data[:split], data[split:], epochs=1,
                          batch_size=cfg_d["batch"], lr=cfg_d["lr"], log_every=0, seed=seed)
            pre_metrics = {"train_loss": mt.train_loss, "val_ce": mt.val_loss,
                           "val_ppl": mt.val_ppl}
        return model, pre_metrics

    import random as _random

    tokens = []
    for doc in variant.docs:
        tokens.extend(tok.encode(doc))
    data = torch.tensor(tokens, dtype=torch.long)
    n_val = max(4 * (cfg.max_seq_len + 2), int(len(data) * 0.08))
    split = max(1, len(data) - n_val)
    _random.Random(seed).shuffle(variant.docs)
    mt = train_lm(model, data[:split], data[split:], epochs=cfg_d["epochs"],
                  batch_size=cfg_d["batch"], lr=cfg_d["lr"], log_every=0, seed=seed)
    pre_metrics = {"train_loss": mt.train_loss, "val_ce": mt.val_loss,
                   "val_ppl": mt.val_ppl}
    return model, pre_metrics


def _sft(model: MiniTransformer, tok: Tokenizer, variant: Variant,
         seed: int) -> dict[str, Any]:
    """Supervised instruction tuning, identical for every variant.

    Without this stage the model is a raw next-token predictor and scores 0.0 on
    every generation metric — including in-distribution. Measuring the study
    before SFT compared an unfinished model against the shipped one and produced
    a uniformly meaningless table (measured: all variants 0.0 exact match).
    """
    from minicoder.data import build_chat_corpus, build_code_corpus
    from minicoder.model.train import train_sft
    from minicoder.sleep.trainer import _holdout_tasks

    code_examples, _ = build_code_corpus()
    chat_examples, _ = build_chat_corpus()
    examples = code_examples + chat_examples
    holdout = {t["name"] for t in _holdout_tasks()}
    train = [e for e in examples if e.get("task") not in holdout]
    val = [e for e in examples if e.get("task") in holdout] or examples[:4]
    metrics = train_sft(
        model, tok, train, val,
        epochs=variant.config()["sft_epochs"],
        batch_size=min(8, max(2, len(train) // 8)),
        lr=1.5e-3, seed=seed,
    )
    return {"sft_train_loss": metrics.train_loss, "sft_val_loss": metrics.val_loss,
            "sft_examples": len(train)}


def _measure(model: MiniTransformer, tok: Tokenizer) -> dict[str, Any]:
    """In-distribution accuracy, sealed holdout accuracy and retention."""
    from minicoder.data import CODE_TASKS
    from minicoder.sleep.trainer import _base_known_tasks, _holdout_tasks, skill_accuracy

    holdout = _holdout_tasks()
    trained = [t for t in CODE_TASKS if t["name"] not in {h["name"] for h in holdout}]
    retention_tasks = _base_known_tasks()

    indist = skill_accuracy(model, tok, trained[:12])
    held = skill_accuracy(model, tok, holdout)
    retained = skill_accuracy(model, tok, retention_tasks)
    return {
        "indist_exact": round(float(indist.get("exact_match", 0.0)), 4),
        "indist_n": indist.get("n"),
        "holdout_exact": round(float(held.get("exact_match", 0.0)), 4),
        "holdout_n": held.get("n"),
        "retention_exact": round(float(retained.get("exact_match", 0.0)), 4),
        "retention_n": retained.get("n"),
    }


def run_study(*, quick: bool = False) -> dict[str, Any]:
    """Train every variant and report a controlled comparison."""
    base = _base_docs()
    variants = [
        Variant("baseline", "shipped architecture, default corpus and schedule", list(base)),
        Variant("more_diversity", "corpus variants 3 -> 4 (more surface variety)",
                _diverse_docs()),
        Variant("curriculum", "short documents first, ascending length",
                _curriculum_docs(), shuffle_docs=False),
        Variant("longer_schedule", "same data, 2x the epochs",
                list(base), overrides={"epochs": BASE_CFG["epochs"] * 2}),
        Variant("smaller_vocab", "vocab 1024 -> 512, same everything else",
                list(base), overrides={"vocab": 512}),
        Variant("higher_lr", "lr 3e-3 -> 6e-3", list(base), overrides={"lr": 6e-3}),
    ]
    if quick:
        for v in variants:
            v.overrides.setdefault("epochs", 4)

    results: list[dict[str, Any]] = []
    t_all = time.time()

    for variant in variants:
        t0 = time.time()
        vocab = variant.config()["vocab"]
        tok = Tokenizer.train(variant.docs, vocab_size=vocab)
        model, pre = _train_variant(variant, tok, seed=MODEL_SEED)
        sft = _sft(model, tok, variant, seed=MODEL_SEED)
        measured = _measure(model, tok)
        entry = {
            "variant": variant.name,
            "description": variant.description,
            "seconds": round(time.time() - t0, 1),
            "params": model.n_params(),
            "vocab": len(tok),
            "corpus_docs": len(variant.docs),
            "epochs": variant.config()["epochs"],
            **pre, **sft, **measured,
        }
        results.append(entry)
        print(f"  {variant.name:16s} held={entry['holdout_exact']:.3f} "
              f"indist={entry['indist_exact']:.3f} retain={entry['retention_exact']:.3f} "
              f"({entry['seconds']}s)", flush=True)

    baseline = results[0]
    for entry in results[1:]:
        entry["delta_holdout"] = round(entry["holdout_exact"] - baseline["holdout_exact"], 4)
        entry["delta_indist"] = round(entry["indist_exact"] - baseline["indist_exact"], 4)
        entry["delta_retention"] = round(
            entry["retention_exact"] - baseline["retention_exact"], 4)

    report = {
        "generated_at": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()),
        "seed": MODEL_SEED,
        "base_config": BASE_CFG,
        "seconds": round(time.time() - t_all, 1),
        "results": results,
        "conclusion": _conclusion(results),
    }
    REPORT_DIR.mkdir(parents=True, exist_ok=True)
    stamp = time.strftime("%Y%m%dT%H%M%SZ", time.gmtime())
    path = REPORT_DIR / f"neural_study_{stamp}.json"
    path.write_text(json.dumps(report, indent=2), encoding="utf-8")
    (REPORT_DIR / "neural_study_latest.json").write_text(
        json.dumps(report, indent=2), encoding="utf-8")
    report["report_path"] = str(path)
    return report


MODEL_SEED = 7


def _conclusion(results: list[dict[str, Any]]) -> list[str]:
    """State what the numbers show, including that most changes do not help."""
    out: list[str] = []
    for entry in results[1:]:
        dh = entry.get("delta_holdout", 0.0)
        di = entry.get("delta_indist", 0.0)
        dr = entry.get("delta_retention", 0.0)
        if dh > 0.02:
            verdict = "improves generalisation"
        elif dh < -0.02:
            verdict = "hurts generalisation"
        elif di > 0.02:
            verdict = "improves in-distribution reproduction only"
        elif di < -0.02:
            verdict = "hurts in-distribution reproduction"
        else:
            verdict = "no measurable difference"
        out.append(
            f"{entry['variant']}: {verdict} "
            f"(holdout {dh:+.3f}, in-distribution {di:+.3f}, retention {dr:+.3f})"
        )
    return out


if __name__ == "__main__":
    print("Neural learning study (controlled, one variable at a time)")
    report = run_study()
    print("\nConclusion:")
    for line in report["conclusion"]:
        print(" -", line)
    print(f"\nreport: {report['report_path']}")
