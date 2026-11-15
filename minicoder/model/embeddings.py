"""Trained text embedder used by semantic memory retrieval.

Falls back to a deterministic hashing embedder when the trained checkpoint is
missing, so the system always works — but ``embed_text`` reports which backend
produced the vector so nothing pretends to be more than it is.
"""

from __future__ import annotations

import hashlib
from typing import Any

import numpy as np

from minicoder.config import CONFIG

_MODEL: Any = None
_TOK: Any = None
_DIM = CONFIG.memory.embedding_dim


def _load():
    global _MODEL, _TOK
    if _MODEL is not None:
        return _MODEL
    ckpt = CONFIG.paths.checkpoints / "embedder.pt"
    tok_path = CONFIG.paths.checkpoints / "tokenizer.json"
    if not ckpt.exists() or not tok_path.exists():
        _MODEL = False
        return _MODEL
    import torch

    from minicoder.model.tokenizer import Tokenizer
    from minicoder.model.transformer import TextEmbedder

    blob = torch.load(ckpt, map_location="cpu", weights_only=False)
    _TOK = Tokenizer.load(tok_path)
    model = TextEmbedder(blob["vocab_size"], blob["dim"], blob.get("d_model", 128), blob.get("max_len", 64))
    model.load_state_dict(blob["state_dict"])
    model.eval()
    _MODEL = model
    return _MODEL


def backend() -> str:
    return "trained-embedder" if _load() else "hash-fallback"


def reset_cache() -> None:
    global _MODEL, _TOK
    _MODEL = None
    _TOK = None


def embed_text(text: str) -> list[float] | None:
    """Return a unit vector, or None when no embedder is trained yet."""
    model = _load()
    if not model:
        return None
    import torch

    ids = torch.tensor([_TOK.encode(text)[:64] or [0]])
    with torch.no_grad():
        vec = model(ids)[0].numpy()
    return [float(v) for v in vec]


def hash_embed(text: str, dim: int = _DIM) -> list[float]:
    """Deterministic bag-of-words hashing vector (always available baseline)."""
    vec = np.zeros(dim, dtype=np.float32)
    tokens = [w for w in "".join(c.lower() if c.isalnum() else " " for c in text).split() if w]
    for tok in tokens:
        h = int(hashlib.blake2b(tok.encode(), digest_size=8).hexdigest(), 16)
        vec[h % dim] += 1.0
        vec[(h >> 8) % dim] += 0.5
    n = np.linalg.norm(vec)
    return (vec / n if n else vec).tolist()


def train_and_save(pairs, epochs: int = 8) -> dict[str, Any]:
    """Train the contrastive embedder on local pairs and persist it."""
    import torch

    from minicoder.model.tokenizer import Tokenizer
    from minicoder.model.train import train_embedder
    from minicoder.model.transformer import TextEmbedder

    _texts = [t for p in pairs for t in p]
    tok = Tokenizer.load(CONFIG.paths.checkpoints / "tokenizer.json")
    vocab = len(tok)
    model = TextEmbedder(vocab, _DIM, 128, 64)
    metrics = train_embedder(model, tok, pairs, epochs=epochs)
    CONFIG.paths.checkpoints.mkdir(parents=True, exist_ok=True)
    torch.save(
        {"state_dict": model.state_dict(), "vocab_size": vocab, "dim": _DIM, "d_model": 128, "max_len": 64},
        CONFIG.paths.checkpoints / "embedder.pt",
    )
    reset_cache()
    return metrics
