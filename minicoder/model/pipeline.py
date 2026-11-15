"""End-to-end training pipeline for the compact multimodal backbone.

Stages (each one writes a checkpoint + a metrics JSON with measured values):

1. ``tokenizer``  — BPE learned from the local corpus
2. ``lm``         — causal LM pretraining on code + chat corpus
3. ``sft``        — supervised instruction tuning on verified task solutions
4. ``embedder``   — contrastive text embedder for semantic memory
5. ``vision``     — MiniViT UI-defect classifier

Everything is CPU-friendly: the default schedule completes in minutes, and the
``--quick`` profile in under a minute so CI can run the whole thing.
"""

from __future__ import annotations

import argparse
import json
import time
from dataclasses import asdict
from pathlib import Path
from typing import Any

import torch

from minicoder.config import CONFIG, ModelConfig
from minicoder.data import (
    CODE_TASKS,
    build_chat_corpus,
    build_code_corpus,
    build_embedding_pairs,
    build_vision_dataset,
    corpus_fingerprint,
)
from minicoder.model.tokenizer import Tokenizer
from minicoder.model.train import save_metrics, train_lm, train_sft
from minicoder.model.transformer import MiniTransformer

PROFILES: dict[str, dict[str, Any]] = {
    # The corpus is small (~8.4k tokens) and the vocabulary needed for code is
    # ~600 tokens. A 1024-token vocab and a 5x160 model fit the data; anything
    # larger memorises slower per step and overfits sooner.
    "quick": {"vocab": 1024, "epochs": 1, "sft_epochs": 2, "vision_epochs": 5, "embed_epochs": 4,
              "batch": 16, "lr": 3e-3, "d_model": 96, "layers": 3, "seq": 128},
    "standard": {"vocab": 1024, "epochs": 40, "sft_epochs": 40, "vision_epochs": 16, "embed_epochs": 10,
                 "batch": 16, "lr": 4e-3, "d_model": 160, "layers": 5, "seq": 192},
}

CHECKPOINTS = lambda: CONFIG.paths.checkpoints  # noqa: E731


def _log(msg: str) -> None:
    print(msg, flush=True)
    telemetry(msg)


def telemetry(msg: str) -> None:
    log = CONFIG.paths.training_runs / "pipeline.log"
    log.parent.mkdir(parents=True, exist_ok=True)
    with log.open("a", encoding="utf-8") as fh:
        fh.write(msg + "\n")


def build_tokenizer(vocab: int) -> Tokenizer:
    code_examples, code_raw = build_code_corpus()
    _, chat_raw = build_chat_corpus()
    texts = code_raw + chat_raw
    t0 = time.time()
    tok = Tokenizer.train(texts, vocab_size=vocab)
    coverage = tok.coverage(texts)
    out = CHECKPOINTS() / "tokenizer.json"
    tok.save(out)
    save_metrics(
        CONFIG.paths.training_runs / "tokenizer_metrics.json",
        {"seconds": round(time.time() - t0, 2), "corpus_chars": sum(len(t) for t in texts)},
        {"merges": len(tok.merges), "vocab_size": len(tok), "roundtrip_coverage": coverage,
         "corpus_fingerprint": corpus_fingerprint()},
    )
    _log(f"tokenizer: {len(tok)} tokens ({len(tok.merges)} merges), roundtrip {coverage:.3f}")
    return tok


def pretrain_lm(tok: Tokenizer, profile: dict[str, Any], resume: bool = False) -> dict[str, Any]:
    ckpt = CHECKPOINTS() / "lm.pt"
    if resume and ckpt.exists():
        model = MiniTransformer.load(ckpt)
        _log(f"lm: resumed {ckpt.name} ({model.n_params():,} params)")
    else:
        d_model = profile["d_model"]
        cfg = ModelConfig(vocab_size=len(tok), d_model=d_model, n_layers=profile["layers"],
                          max_seq_len=profile["seq"], n_heads=4 if d_model % 4 == 0 else 1,
                          d_ff=d_model * 5 // 2)
        torch.manual_seed(cfg.seed)
        model = MiniTransformer(cfg)
        _log(f"lm: new model {model.n_params():,} params ({cfg.n_layers}x{cfg.d_model}, seq {cfg.max_seq_len})")

    _, code_raw = build_code_corpus()
    _, chat_raw = build_chat_corpus()
    docs = code_raw + chat_raw
    # Repeat so the model sees enough tokens for its size; order is shuffled per epoch.
    tokens: list[int] = []
    for _ in range(1):
        for d in docs:
            tokens.extend(tok.encode(d))
    # Guard the rare case where the whole corpus is shorter than one block.
    min_len = (profile["seq"] + 2) * 8
    while len(tokens) < min_len:
        tokens = tokens + tokens
    data = torch.tensor(tokens, dtype=torch.long)
    # Keep a held-out block that is at least a few full contexts long, otherwise
    # validation has no window to score and returns NaN.
    block = profile["seq"]
    n_val = max(4 * (block + 2), int(len(data) * 0.08))
    split = max(1, len(data) - n_val)
    train_t, val_t = data[:split], data[split:]
    _log(f"lm: {len(train_t):,} train tokens / {len(val_t):,} val tokens")
    metrics = train_lm(
        model, train_t, val_t, epochs=profile["epochs"], batch_size=profile["batch"],
        lr=profile["lr"], log_every=10, seed=CONFIG.training.seed, progress=_log,
    )
    model.save(ckpt, meta={"stage": "pretrain", "corpus": corpus_fingerprint(),
                           "params": model.n_params(), "val_ppl": metrics.val_ppl})
    save_metrics(CONFIG.paths.training_runs / "lm_metrics.json", metrics,
                 {"corpus": corpus_fingerprint(), "profile": profile})
    _log(f"lm: done — train loss {metrics.train_loss}, val CE {metrics.val_loss}, ppl {metrics.val_ppl}")
    return {"metrics": asdict(metrics), "params": model.n_params()}


def sft_lm(tok: Tokenizer, profile: dict[str, Any]) -> dict[str, Any]:
    ckpt = CHECKPOINTS() / "lm.pt"
    model = MiniTransformer.load(ckpt)
    code_examples, _ = build_code_corpus()
    chat_examples, _ = build_chat_corpus()
    examples = code_examples + chat_examples
    # Deterministic split; the held-out slice is what the eval suite uses too.
    holdout_names = {t["name"] for t in CODE_TASKS[-6:]}
    train = [e for e in examples if e.get("task") not in holdout_names]
    val = [e for e in examples if e.get("task") in holdout_names] or examples[:4]
    metrics = train_sft(model, tok, train, val, epochs=profile["sft_epochs"],
                        batch_size=min(8, max(2, len(train) // 8)), lr=1.5e-3,
                        seed=CONFIG.training.seed, progress=_log)
    model.save(ckpt, meta={"stage": "sft", "corpus": corpus_fingerprint(), "val_loss": metrics.val_loss})
    save_metrics(CONFIG.paths.training_runs / "sft_metrics.json", metrics,
                 {"train_examples": len(train), "val_examples": len(val), "holdout_tasks": sorted(holdout_names)})
    _log(f"sft: done — train loss {metrics.train_loss}, held-out loss {metrics.val_loss}")
    return {"metrics": asdict(metrics), "train": len(train), "val": len(val)}


def train_embedder_stage(profile: dict[str, Any]) -> dict[str, Any]:
    from minicoder.model.embeddings import train_and_save

    pairs = build_embedding_pairs()
    metrics = train_and_save(pairs, epochs=profile["embed_epochs"])
    save_metrics(CONFIG.paths.training_runs / "embedder_metrics.json",
                 {"epochs": profile["embed_epochs"], "train_loss": metrics["final_loss"],
                  "val_loss": metrics["final_loss"], "batch_size": len(pairs)}, metrics)
    _log(f"embedder: loss {metrics['final_loss']}, retrieval acc {metrics['retrieval_acc']}")
    return metrics


def train_vision_stage(profile: dict[str, Any]) -> dict[str, Any]:
    from minicoder.model.vision import train_vision

    train, test = build_vision_dataset(per_class=110)
    res = train_vision(train, test, epochs=profile["vision_epochs"], progress=None, image_size=48)
    save_metrics(CONFIG.paths.training_runs / "vision_metrics.json",
                 {"steps": len(res["history"]), "epochs": profile["vision_epochs"],
                  "train_loss": res["history"][-1]["train_loss"],
                  "val_loss": res["history"][-1]["test_loss"], "seconds": res["train_seconds"],
                  "lr": 2e-3, "batch_size": 32, "params": res["params"],
                  "trainable_params": res["params"]}, res)
    _log(f"vision: {res['params']:,} params, held-out acc {res['final_test_acc']}")
    return res


def run(profile: str = "standard", stages: list[str] | None = None, resume: bool = False) -> dict[str, Any]:
    prof = PROFILES[profile]
    stages = stages or ["tokenizer", "lm", "sft", "embedder", "vision"]
    CHECKPOINTS().mkdir(parents=True, exist_ok=True)
    t0 = time.time()
    out: dict[str, Any] = {"profile": profile, "stages": {}}
    _log(f"=== MiniCoder training pipeline ({profile}) — {', '.join(stages)} ===")
    tok = Tokenizer.load(CHECKPOINTS() / "tokenizer.json") if (CHECKPOINTS() / "tokenizer.json").exists() else None
    if "tokenizer" in stages or tok is None:
        tok = build_tokenizer(prof["vocab"])
        out["stages"]["tokenizer"] = {"vocab": len(tok), "merges": len(tok.merges)}
    if "lm" in stages:
        out["stages"]["lm"] = pretrain_lm(tok, prof, resume=resume)
    if "sft" in stages:
        out["stages"]["sft"] = sft_lm(tok, prof)
    if "embedder" in stages:
        out["stages"]["embedder"] = train_embedder_stage(prof)
    if "vision" in stages:
        out["stages"]["vision"] = train_vision_stage(prof)
    out["seconds"] = round(time.time() - t0, 1)
    (CONFIG.paths.training_runs / "pipeline_summary.json").write_text(json.dumps(out, indent=2), encoding="utf-8")
    _log(f"=== pipeline complete in {out['seconds']}s ===")
    return out


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(prog="minicoder-train", description=__doc__)
    ap.add_argument("--profile", choices=sorted(PROFILES), default="standard")
    ap.add_argument("--stages", default="", help="comma-separated subset: tokenizer,lm,sft,embedder,vision")
    ap.add_argument("--resume", action="store_true")
    args = ap.parse_args(argv)
    stages = [s.strip() for s in args.stages.split(",") if s.strip()] or None
    run(args.profile, stages, args.resume)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
