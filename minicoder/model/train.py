"""Training loops: causal LM pretraining, SFT on skill traces, and LoRA adapters.

All numbers produced here are measured, never fabricated. Every run writes a
JSON metrics file next to its checkpoint so the evaluation suite and the
dashboard read real values.
"""

from __future__ import annotations

import json
import math
import os
import random
import time
from dataclasses import dataclass, asdict
from pathlib import Path
from typing import Any, Iterable, Sequence

import torch
import torch.nn.functional as F

# Use every available core: transformers are matmul-bound and exit early otherwise.
torch.set_num_threads(max(1, (os.cpu_count() or 2)))

from minicoder.config import CONFIG, TrainingConfig
from minicoder.model.transformer import MiniTransformer


@dataclass
class TrainMetrics:
    steps: int = 0
    epochs: int = 0
    train_loss: float = 0.0
    val_loss: float = 0.0
    val_ppl: float = 0.0
    tokens_seen: int = 0
    seconds: float = 0.0
    lr: float = 0.0
    batch_size: int = 0
    params: int = 0
    trainable_params: int = 0


def _batches(
    arr: torch.Tensor, batch_size: int, block: int, shuffle: bool, seed: int = 0
) -> Iterable[tuple[torch.Tensor, torch.Tensor]]:
    """Yield (x, y) next-token pairs from a flat token tensor."""
    n = len(arr) - block - 1
    if n <= 0:
        return
    starts = list(range(0, n, block))
    if shuffle:
        random.Random(seed).shuffle(starts)
    for i in range(0, len(starts) - batch_size + 1, batch_size):
        chunk = starts[i : i + batch_size]
        xs = torch.stack([arr[s : s + block] for s in chunk])
        ys = torch.stack([arr[s + 1 : s + block + 1] for s in chunk])
        yield xs, ys


@torch.no_grad()
def evaluate_lm(
    model: MiniTransformer, tokens: torch.Tensor, block: int, batch_size: int = 8
) -> tuple[float, float]:
    """Return (cross-entropy, perplexity) on a held-out token stream."""
    if len(tokens) < block + 2:
        return float("nan"), float("nan")
    model.eval()
    losses, weights = 0.0, 0
    for xs, ys in _batches(tokens, batch_size, block, shuffle=False):
        _, loss = model(xs, ys)
        if loss is None:
            continue
        losses += float(loss) * xs.numel()
        weights += xs.numel()
    model.train()
    if weights == 0:
        return float("nan"), float("nan")
    ce = losses / weights
    return ce, math.exp(min(ce, 20.0))


def train_lm(
    model: MiniTransformer,
    train_tokens: torch.Tensor,
    val_tokens: torch.Tensor,
    epochs: int = 1,
    batch_size: int = 8,
    lr: float = 3e-3,
    weight_decay: float = 0.01,
    warmup: int = 20,
    log_every: int = 20,
    seed: int = 0,
    params_filter: Sequence[torch.nn.Parameter] | None = None,
    progress: Any = None,
) -> TrainMetrics:
    """Train the causal LM with AdamW + cosine decay."""
    torch.manual_seed(seed)
    model.train()
    params = list(params_filter) if params_filter is not None else list(model.parameters())
    opt = torch.optim.AdamW(params, lr=lr, weight_decay=weight_decay, betas=(0.9, 0.95))
    steps_per_epoch = max(1, (len(train_tokens) - model.cfg.max_seq_len - 1) // model.cfg.max_seq_len // batch_size)
    total_steps = max(1, steps_per_epoch * epochs)
    sched = torch.optim.lr_scheduler.LambdaLR(
        opt,
        lambda s: min(1.0, (s + 1) / max(1, warmup))
        * (0.05 + 0.95 * 0.5 * (1 + math.cos(math.pi * min(1.0, s / total_steps)))),
    )
    t0 = time.time()
    metrics = TrainMetrics(lr=lr, batch_size=batch_size, params=model.n_params(), trainable_params=sum(p.numel() for p in params))
    running = 0.0
    for epoch in range(epochs):
        for xs, ys in _batches(train_tokens, batch_size, model.cfg.max_seq_len, shuffle=True, seed=seed + epoch):
            logits, loss = model(xs, ys)
            opt.zero_grad(set_to_none=True)
            assert loss is not None
            loss.backward()
            torch.nn.utils.clip_grad_norm_(params, 1.0)
            opt.step()
            sched.step()
            metrics.steps += 1
            metrics.tokens_seen += int(xs.numel())
            running = 0.985 * running + 0.015 * float(loss.detach())
            if log_every and metrics.steps % log_every == 0:
                msg = f"  step {metrics.steps:5d} | loss {running:.4f} | lr {sched.get_last_lr()[0]:.2e} | {time.time()-t0:.1f}s"
                if progress:
                    progress(msg)
                else:
                    print(msg, flush=True)
        metrics.epochs = epoch + 1
    ce, ppl = evaluate_lm(model, val_tokens, model.cfg.max_seq_len)
    if ce != ce:  # NaN guard: too little held-out data to score
        ce, ppl = float("nan"), float("nan")
    metrics.train_loss = round(running, 4)
    metrics.val_loss = round(ce, 4)
    metrics.val_ppl = round(ppl, 3)
    metrics.seconds = round(time.time() - t0, 2)
    return metrics


def save_metrics(path: Path, metrics: TrainMetrics | dict[str, Any] | None, extra: dict[str, Any] | None = None) -> None:
    """Write measured metrics; ``metrics`` may be a TrainMetrics or a plain dict."""
    path.parent.mkdir(parents=True, exist_ok=True)
    if metrics is None:
        payload = {}
    elif isinstance(metrics, TrainMetrics):
        payload = asdict(metrics)
    else:
        payload = dict(metrics)
    payload.update(extra or {})
    path.write_text(json.dumps(payload, indent=2), encoding="utf-8")


# ------------------------------------------------------------------ SFT
def sft_examples_to_ids(
    tok,
    examples: list[dict[str, str]],
    max_len: int,
) -> list[tuple[list[int], list[int], list[int]]]:
    """Convert {prompt, response} pairs into (input, target, mask) id triples.

    Loss is applied to response tokens only — the standard supervised
    fine-tuning objective for instruction following.
    """
    out = []
    for ex in examples:
        p = tok.encode(ex["prompt"].strip() + "\n", add_bos=True)
        r = tok.encode(ex["response"].strip(), add_eos=True)
        ids = (p + r)[: max_len + 1]
        mask = [0] * len(p) + [1] * len(r)
        ids, mask = ids[: max_len + 1], mask[: max_len + 1]
        out.append((ids[:-1], ids[1:], mask[1:]))
    return out


def pad_batch(
    triples: list[tuple[list[int], list[int], list[int]]], pad_id: int = 0
) -> tuple[torch.Tensor, torch.Tensor, torch.Tensor]:
    T = max(len(t[0]) for t in triples)
    xs, ys, ms = [], [], []
    for x, y, m in triples:
        p = T - len(x)
        xs.append(x + [pad_id] * p)
        ys.append(y + [pad_id] * p)
        ms.append(m + [0] * p)
    return torch.tensor(xs), torch.tensor(ys), torch.tensor(ms)


def train_sft(
    model: MiniTransformer,
    tok,
    train_examples: list[dict[str, str]],
    val_examples: list[dict[str, str]],
    epochs: int = 3,
    batch_size: int = 8,
    lr: float = 1e-3,
    seed: int = 0,
    params_filter: Sequence[torch.nn.Parameter] | None = None,
    progress: Any = None,
) -> TrainMetrics:
    torch.manual_seed(seed)
    model.train()
    params = list(params_filter) if params_filter is not None else list(model.parameters())
    opt = torch.optim.AdamW(params, lr=lr, betas=(0.9, 0.95), weight_decay=0.0)
    train_ids = sft_examples_to_ids(tok, train_examples, model.cfg.max_seq_len)
    val_ids = sft_examples_to_ids(tok, val_examples, model.cfg.max_seq_len)
    t0 = time.time()
    metrics = TrainMetrics(lr=lr, batch_size=batch_size, params=model.n_params(), trainable_params=sum(p.numel() for p in params))
    rng = random.Random(seed)
    running = 0.0
    for epoch in range(epochs):
        order = list(range(len(train_ids)))
        rng.shuffle(order)
        for i in range(0, len(order) - batch_size + 1, batch_size):
            batch = [train_ids[j] for j in order[i : i + batch_size]]
            xs, ys, ms = pad_batch(batch)
            _, loss = model(xs, ys, loss_mask=ms)
            assert loss is not None
            opt.zero_grad(set_to_none=True)
            loss.backward()
            torch.nn.utils.clip_grad_norm_(params, 1.0)
            opt.step()
            metrics.steps += 1
            metrics.tokens_seen += int((ms > 0).sum())
            running = 0.97 * running + 0.03 * float(loss.detach())
            if metrics.steps % 50 == 0:
                msg = f"  sft step {metrics.steps:5d} | loss {running:.4f} | {time.time()-t0:.1f}s"
                if progress:
                    progress(msg)
                else:
                    print(msg, flush=True)
        metrics.epochs = epoch + 1
    # Held-out response-only loss.
    if val_ids:
        model.eval()
        tot, n = 0.0, 0
        with torch.no_grad():
            for i in range(0, len(val_ids), batch_size):
                xs, ys, ms = pad_batch(val_ids[i : i + batch_size])
                _, loss = model(xs, ys, loss_mask=ms)
                if loss is not None:
                    tot += float(loss)
                    n += 1
        model.train()
        metrics.val_loss = round(tot / max(1, n), 4)
        metrics.val_ppl = round(math.exp(min(metrics.val_loss, 20.0)), 3)
    metrics.train_loss = round(running, 4)
    metrics.seconds = round(time.time() - t0, 2)
    return metrics


# ------------------------------------------------------- contrastive embedder
def train_embedder(
    embedder,
    tok,
    pairs: list[tuple[str, str]],
    epochs: int = 6,
    lr: float = 2e-3,
    max_len: int = 64,
    seed: int = 0,
) -> dict[str, float]:
    """Symmetric InfoNCE so retrieval similarity is meaningful."""
    torch.manual_seed(seed)
    opt = torch.optim.AdamW(embedder.parameters(), lr=lr)
    a = [torch.tensor(tok.encode(x)[:max_len]) for x, _ in pairs]
    b = [torch.tensor(tok.encode(y)[:max_len]) for _, y in pairs]

    def batchify(items):
        T = max(1, max(len(t) for t in items))
        out = torch.zeros(len(items), T, dtype=torch.long)
        for i, t in enumerate(items):
            out[i, : len(t)] = t
        return out

    A, B = batchify(a), batchify(b)
    embedder.train()
    last = 0.0
    best = float("inf")
    for epoch in range(epochs):
        za, zb = embedder(A), embedder(B)
        logits = za @ zb.T / 0.07
        labels = torch.arange(len(pairs))
        loss = 0.5 * (F.cross_entropy(logits, labels) + F.cross_entropy(logits.T, labels))
        opt.zero_grad(set_to_none=True)
        loss.backward()
        opt.step()
        last = float(loss.detach())
        best = min(best, last)
    embedder.eval()
    with torch.no_grad():
        za, zb = embedder(A), embedder(B)
        acc = float(((za @ zb.T).argmax(-1) == torch.arange(len(pairs))).float().mean())
    return {"final_loss": round(last, 4), "best_loss": round(best, 4), "retrieval_acc": round(acc, 4), "pairs": len(pairs)}
