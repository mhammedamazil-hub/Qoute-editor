#!/usr/bin/env python3
"""CI gate 2 — train MiniCoder-Nano from scratch on the verified shards.

* replay buffer = all shard_*.jsonl in the dataset dir (older skills prevent
  catastrophic forgetting of previously compiled capabilities)
* deterministic 80/20 train/holdout split (seeded — reproducible)
* gate: trained perplexity must beat untrained baseline perplexity on the
  holdout; writes eval_report.json with the REAL measured numbers; saves the
  adapter (minicoder-nano.npz) for the release step.

Exits 0 when the gate passes, 1 otherwise. Never fabricates results: whatever
is printed came out of the run.
"""
import argparse
import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
from minicoder.nano import NanoLM, NanoConfig  # noqa: E402


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--datasets", default="datasets/sleep_skills")
    ap.add_argument("--out", default="minicoder/release")
    ap.add_argument("--steps", type=int, default=600)
    ap.add_argument("--seed", type=int, default=7)
    args = ap.parse_args()

    ds = Path(args.datasets)
    lines = []
    for f in sorted(ds.glob("shard_*.jsonl")):
        lines.extend(l for l in f.read_text(encoding="utf-8").splitlines() if l.strip())
    if len(lines) < 20:
        print(json.dumps({"error": f"need >= 20 examples across shards, found {len(lines)}"}))
        return 1

    split = int(len(lines) * 0.8)
    train_lines, holdout_lines = lines[:split], lines[split:]
    model = NanoLM(NanoConfig())
    baseline_ppl = model.perplexity(holdout_lines)
    stats = model.train_on_texts(train_lines, steps=args.steps, batch_size=32,
                                 lr=3e-3, seed=args.seed, log_every=0)
    trained_ppl = model.perplexity(holdout_lines)
    gate_pass = trained_ppl < baseline_ppl

    out = Path(args.out)
    out.mkdir(parents=True, exist_ok=True)
    model.save(out / "minicoder-nano.npz")
    report = {
        "gate_pass": bool(gate_pass),
        "examples_total": len(lines),
        "train_examples": len(train_lines),
        "holdout_examples": len(holdout_lines),
        "baseline_perplexity": round(baseline_ppl, 4),
        "trained_perplexity": round(trained_ppl, 4),
        "improvement_pct": round(100.0 * (1.0 - trained_ppl / baseline_ppl), 2),
        "training": stats,
        "model": "minicoder-nano (from-scratch byte-level MLP, see nano.py)",
        "note": "Numbers are measured on this run; nothing is precomputed or synthetic.",
    }
    (out / "eval_report.json").write_text(json.dumps(report, indent=2), encoding="utf-8")
    print(json.dumps(report, indent=2))
    return 0 if gate_pass else 1


if __name__ == "__main__":
    sys.exit(main())
