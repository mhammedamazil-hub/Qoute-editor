"""MiniCoder-Nano — a from-scratch, pure-NumPy neural language model.

No frameworks, no pretrained weights, no downloads: byte-level vocabulary (256),
a fixed-window context, one ReLU hidden layer, softmax cross-entropy, and an
Adam optimiser implemented by hand. It is tiny on purpose (~170 kparams) so it
trains in seconds on a CPU and is honest about what it is: a small neural
network that measurably learns the statistics of the verified skill shards it
is fed. It is NOT a general-purpose LLM; baselines are reported alongside
every measurement and nothing is fabricated.

Architecture (config): K context bytes → embeddings (d) → concat → Linear(H, ReLU)
→ Linear(V=256) → softmax. Trained by next-byte prediction.
"""
from __future__ import annotations
import json
import math
import time
from dataclasses import dataclass, asdict
from pathlib import Path
import numpy as np

VOCAB = 256  # raw byte vocabulary — every UTF-8 string is representable


@dataclass
class NanoConfig:
    context: int = 16
    embed_dim: int = 24
    hidden: int = 256
    seed: int = 1337

    @property
    def input_dim(self) -> int:
        return self.context * self.embed_dim

    def param_count(self) -> int:
        return (VOCAB * self.embed_dim + self.input_dim * self.hidden + self.hidden
                + self.hidden * VOCAB + VOCAB)


class NanoLM:
    def __init__(self, config: NanoConfig | None = None) -> None:
        self.cfg = config or NanoConfig()
        rng = np.random.default_rng(self.cfg.seed)
        d, h, K = self.cfg.embed_dim, self.cfg.hidden, self.cfg.context
        scale = lambda fan_in: math.sqrt(2.0 / fan_in)
        self.E = (rng.standard_normal((VOCAB, d)) * 0.05).astype(np.float32)
        self.W1 = (rng.standard_normal((self.cfg.input_dim, h)) * scale(self.cfg.input_dim)).astype(np.float32)
        self.b1 = np.zeros(h, dtype=np.float32)
        self.W2 = (rng.standard_normal((h, VOCAB)) * scale(h)).astype(np.float32)
        self.b2 = np.zeros(VOCAB, dtype=np.float32)
        self._adam: dict[str, list[np.ndarray]] = {
            name: [np.zeros_like(p), np.zeros_like(p)] for name, p in self._params().items()
        }
        self._adam_t = 0

    # ------------------------------------------------------------- plumbing
    def _params(self) -> dict[str, np.ndarray]:
        return {"E": self.E, "W1": self.W1, "b1": self.b1, "W2": self.W2, "b2": self.b2}

    def state_dict(self) -> dict[str, np.ndarray]:
        return {k: v.copy() for k, v in self._params().items()}

    def load_state_dict(self, state: dict[str, np.ndarray]) -> None:
        for k, v in state.items():
            getattr(self, k)[...] = v.astype(np.float32)

    # ------------------------------------------------------------- forward
    def _forward(self, xb: np.ndarray, targets: np.ndarray | None = None):
        B = xb.shape[0]
        emb = self.E[xb]                       # [B, K, d]
        h_in = emb.reshape(B, self.cfg.input_dim)
        z1 = h_in @ self.W1 + self.b1
        a1 = np.maximum(z1, 0.0)
        z2 = a1 @ self.W2 + self.b2
        z2 = z2 - z2.max(axis=1, keepdims=True)   # stable softmax
        exp = np.exp(z2)
        probs = exp / exp.sum(axis=1, keepdims=True)
        loss = None
        if targets is not None:
            picked = probs[np.arange(B), targets]
            loss = float(-np.log(np.clip(picked, 1e-12, 1.0)).mean())
        cache = (xb, emb, h_in, z1, a1, probs)
        return probs, loss, cache

    def _backward(self, cache, targets: np.ndarray):
        xb, emb, h_in, z1, a1, probs = cache
        B = xb.shape[0]
        dz2 = probs.copy()
        dz2[np.arange(B), targets] -= 1.0
        dz2 /= B
        dW2 = a1.T @ dz2
        db2 = dz2.sum(axis=0)
        da1 = dz2 @ self.W2.T
        dz1 = da1 * (z1 > 0)
        dW1 = h_in.T @ dz1
        db1 = dz1.sum(axis=0)
        dh_in = dz1 @ self.W1.T
        d_emb = dh_in.reshape(B, self.cfg.context, self.cfg.embed_dim)
        dE = np.zeros_like(self.E)
        np.add.at(dE, xb, d_emb)
        return {"E": dE, "W1": dW1, "b1": db1, "W2": dW2, "b2": db2}

    def _adam_step(self, grads: dict[str, np.ndarray], lr: float,
                   beta1: float = 0.9, beta2: float = 0.999, eps: float = 1e-8) -> None:
        self._adam_t += 1
        t = self._adam_t
        for name, p in self._params().items():
            m, v = self._adam[name]
            g = grads[name]
            m *= beta1; m += (1 - beta1) * g
            v *= beta2; v += (1 - beta2) * (g * g)
            m_hat = m / (1 - beta1 ** t)
            v_hat = v / (1 - beta2 ** t)
            p -= lr * m_hat / (np.sqrt(v_hat) + eps)

    # -------------------------------------------------------------- corpus
    @staticmethod
    def _to_bytes(text: str) -> np.ndarray:
        return np.frombuffer(text.encode("utf-8", errors="ignore"), dtype=np.uint8).astype(np.int64)

    def _batches(self, data: np.ndarray, batch_size: int, rng):
        K = self.cfg.context
        n = len(data) - K - 1
        if n <= 0:
            raise ValueError("corpus too small: need more than context+1 bytes")
        starts = rng.integers(0, n, size=batch_size)
        xb = np.stack([data[s:s + K] for s in starts])
        yb = np.stack([data[s + K] for s in starts])
        return xb, yb

    # -------------------------------------------------------------- public
    def train_on_texts(self, texts: list[str], *, steps: int = 300, batch_size: int = 32,
                       lr: float = 3e-3, seed: int = 7,
                       log_every: int = 50) -> dict:
        data = self._to_bytes("\n\n".join(texts))
        rng = np.random.default_rng(seed)
        losses: list[float] = []
        t0 = time.time()
        for step in range(1, steps + 1):
            xb, yb = self._batches(data, batch_size, rng)
            _, loss, cache = self._forward(xb, yb)
            grads = self._backward(cache, yb)
            self._adam_step(grads, lr)
            losses.append(loss)
            if log_every and step % log_every == 0:
                recent = float(np.mean(losses[-log_every:]))
                print(f"[nano] step {step}/{steps} loss={recent:.4f}")
        return {
            "steps": steps, "final_loss": float(np.mean(losses[-20:])),
            "initial_loss": float(np.mean(losses[:20])),
            "seconds": round(time.time() - t0, 3),
            "tokens_seen": steps * batch_size,
            "param_count": self.cfg.param_count(),
            "architecture": f"byte-MLP ctx={self.cfg.context} d={self.cfg.embed_dim} h={self.cfg.hidden}",
        }

    def perplexity(self, texts: list[str], *, max_positions: int = 20000) -> float:
        data = self._to_bytes("\n\n".join(texts))
        K = self.cfg.context
        if len(data) <= K + 1:
            return float("inf")
        ce_total, count = 0.0, 0
        stride = max(1, (len(data) - K - 1) // max_positions)
        for s in range(0, len(data) - K - 1, stride):
            xb = data[s:s + K][None, :]
            yb = np.array([data[s + K]], dtype=np.int64)
            probs, _, _ = self._forward(xb)
            p = max(float(probs[0, yb[0]]), 1e-12)
            ce_total += -math.log(p)
            count += 1
        return math.exp(ce_total / max(1, count))

    def generate(self, prompt: str, *, max_bytes: int = 200, temperature: float = 0.8,
                 seed: int = 0) -> str:
        rng = np.random.default_rng(seed)
        out = bytearray(prompt.encode("utf-8"))
        temp = max(1e-3, temperature)
        for _ in range(max_bytes):
            ctx = np.array(out[-self.cfg.context:], dtype=np.int64)
            if len(ctx) < self.cfg.context:
                ctx = np.pad(ctx, (self.cfg.context - len(ctx), 0))
            probs, _, _ = self._forward(ctx[None, :])
            logits = np.log(np.clip(probs[0], 1e-12, 1.0)) / temp
            logits -= logits.max()
            p = np.exp(logits); p /= p.sum()
            nxt = int(rng.choice(VOCAB, p=p))
            out.append(nxt)
        return bytes(out).decode("utf-8", errors="ignore")

    # ------------------------------------------------------------ persistence
    def save(self, path: Path) -> Path:
        path = Path(path)
        path.parent.mkdir(parents=True, exist_ok=True)
        np.savez(path, cfg=json.dumps(asdict(self.cfg)), **self.state_dict())
        return path.with_suffix(".npz")

    @classmethod
    def load(cls, path: Path) -> "NanoLM":
        path = Path(path)
        if path.suffix != ".npz":
            path = path.with_suffix(".npz")
        blob = np.load(path, allow_pickle=False)
        cfg = NanoConfig(**json.loads(str(blob["cfg"])))
        model = cls(cfg)
        model.load_state_dict({k: blob[k] for k in ("E", "W1", "b1", "W2", "b2")})
        return model
