"""From-scratch, offline text embeddings.

Signed feature-hashing (a.k.a. hashing trick) over word unigrams + bigrams,
projected into a fixed 384-d float32 space, L2-normalised. Deterministic,
zero network, zero model downloads — works on a laptop with no GPU and no
internet. It is a *lexical* embedder: strong on keyword/overlap similarity,
weaker on deep paraphrase. The interface is pluggable — drop in a
sentence-transformers embedder later without touching call sites.
"""
from __future__ import annotations
import math
import zlib
import numpy as np
from .config import get_settings
from .util import tokenize


def _hash(text: str) -> int:
    # stable across runs & platforms (zlib.crc32), unlike builtin hash()
    return zlib.crc32(text.encode("utf-8"))


def embed_text(text: str, dim: int | None = None) -> np.ndarray:
    dim = dim or get_settings().embedding_dim
    vec = np.zeros(dim, dtype=np.float32)
    tokens = tokenize(text)
    if not tokens:
        return vec
    features: list[tuple[str, float]] = []
    for tok in tokens:
        features.append((tok, 1.0))
    for a, b in zip(tokens, tokens[1:]):
        features.append((a + "_" + b, 1.4))  # bigrams weigh a bit more
    for feat, weight in features:
        h = _hash(feat)
        idx = h % dim
        sign = 1.0 if (h & 0x80000000) == 0 else -1.0
        vec[idx] += sign * weight
    norm = float(np.linalg.norm(vec))
    if norm > 0:
        vec /= norm
    return vec


def cosine(a: np.ndarray, b: np.ndarray) -> float:
    """Vectors are L2-normalised by construction; still guard degenerate cases."""
    na = float(np.linalg.norm(a))
    nb = float(np.linalg.norm(b))
    if na == 0.0 or nb == 0.0:
        return 0.0
    return float(np.dot(a, b) / (na * nb))


def to_blob(vec: np.ndarray) -> bytes:
    return np.ascontiguousarray(vec.astype(np.float32)).tobytes()


def from_blob(blob: bytes) -> np.ndarray:
    return np.frombuffer(blob, dtype=np.float32).copy()
