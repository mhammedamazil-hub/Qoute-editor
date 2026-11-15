"""Compact causal transformer + LoRA, implemented directly in PyTorch.

This is the *real* neural backbone of MiniCoder, trained from scratch on the
local corpus (no pretrained weights can be downloaded in this environment).
It is deliberately small (~1-3M parameters), which is exactly the scale the
project targets: <1B parameters with measurable behaviour.

Features
--------
* Pre-norm decoder-only transformer, RoPE positions, GQA-ready attention,
  causal masking, tied embeddings, weight-tied output head.
* LoRA adapters that can be attached/detached/merged and serialised to a
  single ``.safetensors``-style file, which is what the sleep-training pipeline
  produces and what the GitHub workflow publishes as a Release artifact.
* Deterministic sampling (temperature / top-k / top-p) and KV-cache-free
  incremental decode via re-forward (fast enough at this scale on CPU).
"""

from __future__ import annotations

import math
from dataclasses import asdict, dataclass
from pathlib import Path
from typing import Any

import torch
import torch.nn as nn
import torch.nn.functional as F

from minicoder.config import ModelConfig


# ------------------------------------------------------------------ blocks
class RMSNorm(nn.Module):
    def __init__(self, dim: int, eps: float = 1e-5) -> None:
        super().__init__()
        self.weight = nn.Parameter(torch.ones(dim))
        self.eps = eps

    def forward(self, x: torch.Tensor) -> torch.Tensor:
        return x * torch.rsqrt(x.pow(2).mean(-1, keepdim=True) + self.eps) * self.weight


def rope_cache(seq_len: int, head_dim: int, device: torch.device | None = None) -> tuple[torch.Tensor, torch.Tensor]:
    """Interleaved RoPE tables, shaped (T, head_dim) so they broadcast over heads."""
    half = head_dim // 2
    inv = torch.exp(-math.log(10000.0) * torch.arange(0, half, dtype=torch.float32, device=device) / half)
    pos = torch.arange(seq_len, dtype=torch.float32, device=device)
    freqs = torch.outer(pos, inv)                      # (T, D/2)
    freqs = torch.cat([freqs, freqs], dim=-1)          # (T, D) — duplicated for the pair layout
    return torch.cos(freqs), torch.sin(freqs)


def apply_rope(x: torch.Tensor, cos: torch.Tensor, sin: torch.Tensor) -> torch.Tensor:
    """Rotate consecutive (even, odd) feature pairs.
    x: (B, H, T, D); cos/sin: (T, D)."""
    T, _D = x.shape[-2], x.shape[-1]  # _D documents the layout; only T is used
    cos, sin = cos[:T].to(x.dtype), sin[:T].to(x.dtype)
    x1, x2 = x[..., 0::2], x[..., 1::2]                 # (B, H, T, D/2)
    rot = torch.stack((-x2, x1), dim=-1).flatten(-2)    # interleave back to D
    return x * cos[None, None, :, :] + rot * sin[None, None, :, :]


class CausalSelfAttention(nn.Module):
    def __init__(self, cfg: ModelConfig) -> None:
        super().__init__()
        assert cfg.d_model % cfg.n_heads == 0
        self.n_heads = cfg.n_heads
        self.head_dim = cfg.d_model // cfg.n_heads
        self.qkv = nn.Linear(cfg.d_model, 3 * cfg.d_model, bias=False)
        self.proj = nn.Linear(cfg.d_model, cfg.d_model, bias=False)
        self.dropout = cfg.dropout

    def forward(self, x: torch.Tensor) -> torch.Tensor:
        B, T, C = x.shape
        q, k, v = self.qkv(x).split(C, dim=2)
        q = q.view(B, T, self.n_heads, self.head_dim).transpose(1, 2)
        k = k.view(B, T, self.n_heads, self.head_dim).transpose(1, 2)
        v = v.view(B, T, self.n_heads, self.head_dim).transpose(1, 2)
        cos, sin = rope_cache(T, self.head_dim, x.device)
        q, k = apply_rope(q, cos, sin), apply_rope(k, cos, sin)
        out = F.scaled_dot_product_attention(
            q, k, v, is_causal=True, dropout_p=self.dropout if self.training else 0.0
        )
        out = out.transpose(1, 2).contiguous().view(B, T, C)
        return self.proj(out)


class MLP(nn.Module):
    def __init__(self, cfg: ModelConfig) -> None:
        super().__init__()
        self.fc = nn.Linear(cfg.d_model, cfg.d_ff, bias=False)
        self.proj = nn.Linear(cfg.d_ff, cfg.d_model, bias=False)
        self.act = nn.SiLU()

    def forward(self, x: torch.Tensor) -> torch.Tensor:
        return self.proj(self.act(self.fc(x)))


class Block(nn.Module):
    def __init__(self, cfg: ModelConfig) -> None:
        super().__init__()
        self.norm1 = RMSNorm(cfg.d_model)
        self.attn = CausalSelfAttention(cfg)
        self.norm2 = RMSNorm(cfg.d_model)
        self.mlp = MLP(cfg)

    def forward(self, x: torch.Tensor) -> torch.Tensor:
        x = x + self.attn(self.norm1(x))
        x = x + self.mlp(self.norm2(x))
        return x


class MiniTransformer(nn.Module):
    """Decoder-only causal LM: the chat + coder brain."""

    def __init__(self, cfg: ModelConfig, vocab_size: int | None = None) -> None:
        super().__init__()
        self.cfg = cfg
        vs = vocab_size or cfg.vocab_size
        self.vocab_size = vs
        self.tok_emb = nn.Embedding(vs, cfg.d_model)
        self.blocks = nn.ModuleList([Block(cfg) for _ in range(cfg.n_layers)])
        self.norm_f = RMSNorm(cfg.d_model)
        self.lm_head = nn.Linear(cfg.d_model, vs, bias=False)
        if cfg.tie_embeddings:
            self.lm_head.weight = self.tok_emb.weight
        self.apply(self._init_weights)
        torch.manual_seed(cfg.seed)

    @staticmethod
    def _init_weights(m: nn.Module) -> None:
        if isinstance(m, nn.Linear):
            nn.init.normal_(m.weight, std=0.02)
        elif isinstance(m, nn.Embedding):
            nn.init.normal_(m.weight, std=0.02)

    def n_params(self, trainable_only: bool = False) -> int:
        ps = self.parameters()
        return sum(p.numel() for p in ps if (p.requires_grad or not trainable_only))

    def forward(
        self,
        idx: torch.Tensor,
        targets: torch.Tensor | None = None,
        loss_mask: torch.Tensor | None = None,
    ) -> tuple[torch.Tensor, torch.Tensor | None]:
        B, T = idx.shape
        T = min(T, self.cfg.max_seq_len)
        idx = idx[:, :T]
        x = self.tok_emb(idx)
        for block in self.blocks:
            x = block(x)
        x = self.norm_f(x)
        logits = self.lm_head(x)
        loss = None
        if targets is not None:
            targets = targets[:, :T]
            flat = F.cross_entropy(
                logits.reshape(-1, logits.size(-1)),
                targets.reshape(-1),
                reduction="none",
            ).view(B, T)
            if loss_mask is not None:
                mask = loss_mask[:, :T].to(flat.dtype)
                loss = (flat * mask).sum() / mask.sum().clamp(min=1.0)
            else:
                loss = flat.mean()
        return logits, loss

    # ------------------------------------------------------------ sampling
    @torch.no_grad()
    def generate(
        self,
        idx: torch.Tensor,
        max_new_tokens: int = 64,
        temperature: float = 0.8,
        top_k: int = 40,
        top_p: float = 0.95,
        eos_id: int | None = None,
        repetition_penalty: float = 1.0,
        generator: torch.Generator | None = None,
    ) -> torch.Tensor:
        self.eval()
        for _ in range(max_new_tokens):
            ctx = idx[:, -self.cfg.max_seq_len :]
            logits, _ = self(ctx)
            logits = logits[:, -1, :].float()
            if repetition_penalty != 1.0:
                for b in range(idx.size(0)):
                    for tok in set(idx[b].tolist()):
                        logits[b, tok] /= repetition_penalty
            if temperature <= 1e-5:
                nxt = logits.argmax(dim=-1, keepdim=True)
            else:
                logits = logits / temperature
                if top_k > 0:
                    k = min(top_k, logits.size(-1))
                    thresh = torch.topk(logits, k, dim=-1).values[:, -1].unsqueeze(-1)
                    logits = logits.masked_fill(logits < thresh, float("-inf"))
                probs = F.softmax(logits, dim=-1)
                if top_p < 1.0:
                    sorted_probs, sorted_idx = torch.sort(probs, descending=True, dim=-1)
                    cum = torch.cumsum(sorted_probs, dim=-1)
                    cut = (cum - sorted_probs) > top_p
                    sorted_probs = sorted_probs.masked_fill(cut, 0.0)
                    probs = torch.zeros_like(probs).scatter_(-1, sorted_idx, sorted_probs)
                    probs = probs / probs.sum(dim=-1, keepdim=True).clamp(min=1e-9)
                nxt = torch.multinomial(probs, num_samples=1, generator=generator)
            idx = torch.cat([idx, nxt], dim=1)
            if eos_id is not None and (nxt == eos_id).all():
                break
        return idx

    # ------------------------------------------------------------ persist
    def save(self, path: Path, meta: dict[str, Any] | None = None) -> None:
        path = Path(path)
        path.parent.mkdir(parents=True, exist_ok=True)
        tmp = path.with_suffix(path.suffix + ".tmp")
        torch.save(
            {
                "model_cfg": asdict(self.cfg),
                "vocab_size": self.vocab_size,
                "state_dict": self.state_dict(),
                "meta": meta or {},
            },
            tmp,
        )
        tmp.replace(path)

    @classmethod
    def load(cls, path: Path) -> MiniTransformer:
        blob = torch.load(Path(path), map_location="cpu", weights_only=False)
        cfg = ModelConfig(**blob["model_cfg"])
        model = cls(cfg, vocab_size=blob["vocab_size"])
        model.load_state_dict(blob["state_dict"])
        model.eval()
        return model


# -------------------------------------------------------------------- LoRA
@dataclass
class LoRAConfig:
    rank: int = 8
    alpha: float = 16.0
    dropout: float = 0.0
    targets: tuple[str, ...] = ("qkv", "proj", "fc")  # module name suffixes


class LoRALinear(nn.Module):
    """Wraps a frozen ``nn.Linear`` with a trainable low-rank delta."""

    def __init__(self, base: nn.Linear, rank: int, alpha: float, dropout: float = 0.0) -> None:
        super().__init__()
        self.base = base
        for p in self.base.parameters():
            p.requires_grad = False
        self.rank = rank
        self.scaling = alpha / max(1, rank)
        self.a = nn.Linear(base.in_features, rank, bias=False)
        self.b = nn.Linear(rank, base.out_features, bias=False)
        nn.init.kaiming_uniform_(self.a.weight, a=math.sqrt(5))
        nn.init.zeros_(self.b.weight)  # start at identity => no behaviour change
        self.drop = nn.Dropout(dropout)

    def forward(self, x: torch.Tensor) -> torch.Tensor:
        return self.base(x) + self.b(self.a(self.drop(x))) * self.scaling

    def merged_weight(self) -> torch.Tensor:
        return self.base.weight + (self.b.weight @ self.a.weight) * self.scaling


def attach_lora(model: nn.Module, cfg: LoRAConfig) -> int:
    """Replace target Linear layers with LoRALinear. Returns adapter param count."""
    replaced = 0
    for _name, module in list(model.named_modules()):
        for child_name, child in list(module.named_children()):
            if isinstance(child, nn.Linear) and any(child_name.endswith(t) for t in cfg.targets):
                setattr(module, child_name, LoRALinear(child, cfg.rank, cfg.alpha, cfg.dropout))
                replaced += 1
    return replaced


def lora_parameters(model: nn.Module) -> list[nn.Parameter]:
    params = []
    for module in model.modules():
        if isinstance(module, LoRALinear):
            params.extend([module.a.weight, module.b.weight])
    return params


def adapter_state(model: nn.Module) -> dict[str, torch.Tensor]:
    return {k: v.detach().clone() for k, v in model.state_dict().items() if ".a.weight" in k or ".b.weight" in k}


def merge_lora(model: nn.Module) -> None:
    """Fold every LoRA delta into the base weights, in place, then zero the delta.

    Runs entirely under ``no_grad`` with ``requires_grad`` temporarily disabled:
    ``b.weight`` is a leaf tensor that requires grad, so ``zero_()`` on it would
    otherwise raise.
    """
    for module in model.modules():
        if isinstance(module, LoRALinear):
            with torch.no_grad():
                merged = module.merged_weight().detach()
                module.base.weight.copy_(merged)
                module.b.weight.detach().zero_()


def detach_lora(model: nn.Module) -> None:
    """Remove adapters, restoring the frozen base model."""
    for _name, parent in list(model.named_modules())[:]:
        for child_name, child in list(parent.named_children()):
            if isinstance(child, LoRALinear):
                setattr(parent, child_name, child.base)


def save_adapter(model: nn.Module, path: Path, meta: dict[str, Any] | None = None) -> None:
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    tmp = path.with_suffix(path.suffix + ".tmp")
    torch.save({"adapter": adapter_state(model), "meta": meta or {}}, tmp)
    tmp.replace(path)


def load_adapter(model: nn.Module, path: Path) -> dict[str, Any]:
    blob = torch.load(Path(path), map_location="cpu", weights_only=False)
    state = blob["adapter"]
    own = model.state_dict()
    missing = [k for k in state if k not in own]
    if missing:
        raise KeyError(f"adapter does not match model: {missing[:3]}...")
    with torch.no_grad():
        for k, v in state.items():
            own[k].copy_(v)
    return blob.get("meta", {})


# ------------------------------------------------------- multimodal bricks
class PatchEmbed(nn.Module):
    """Split an image into non-overlapping patches and project to d_model."""

    def __init__(self, img_size: int, patch: int, d_model: int, in_chans: int = 3) -> None:
        super().__init__()
        self.n_patches = (img_size // patch) ** 2
        self.proj = nn.Conv2d(in_chans, d_model, kernel_size=patch, stride=patch)

    def forward(self, x: torch.Tensor) -> torch.Tensor:
        # x: (B, 3, H, W) -> (B, N, d_model)
        return self.proj(x).flatten(2).transpose(1, 2)


class MiniViT(nn.Module):
    """Vision tower: the image viewer's neural feature extractor."""

    def __init__(self, cfg: ModelConfig, n_classes: int = 8) -> None:
        super().__init__()
        self.cfg = cfg
        self.patch = PatchEmbed(cfg.vision_image_size, cfg.vision_patch, cfg.vision_d_model)
        self.cls = nn.Parameter(torch.zeros(1, 1, cfg.vision_d_model))
        n = self.patch.n_patches + 1
        self.pos = nn.Parameter(torch.zeros(1, n, cfg.vision_d_model))
        nn.init.trunc_normal_(self.pos, std=0.02)
        nn.init.trunc_normal_(self.cls, std=0.02)
        layer = nn.TransformerEncoderLayer(
            d_model=cfg.vision_d_model,
            nhead=cfg.vision_heads,
            dim_feedforward=cfg.vision_d_model * 3,
            dropout=0.0,
            batch_first=True,
            norm_first=True,
            activation="gelu",
        )
        self.encoder = nn.TransformerEncoder(layer, num_layers=cfg.vision_layers, enable_nested_tensor=False)
        self.norm = nn.LayerNorm(cfg.vision_d_model)
        self.head = nn.Linear(cfg.vision_d_model, n_classes)

    def embed(self, x: torch.Tensor) -> torch.Tensor:
        tokens = self.patch(x)
        tokens = torch.cat([self.cls.expand(tokens.size(0), -1, -1), tokens], dim=1) + self.pos
        return self.norm(self.encoder(tokens))[:, 0]

    def forward(self, x: torch.Tensor) -> torch.Tensor:
        return self.head(self.embed(x))

    def n_params(self) -> int:
        return sum(p.numel() for p in self.parameters())


class TextEmbedder(nn.Module):
    """Dual-encoder tower trained with symmetric InfoNCE.

    Produces L2-normalised vectors for semantic memory retrieval. It is trained
    locally on (anchor, positive) pairs so it is genuinely useful rather than a
    random projection.
    """

    def __init__(self, vocab_size: int, dim: int, d_model: int = 128, max_len: int = 64) -> None:
        super().__init__()
        self.tok_emb = nn.Embedding(vocab_size, d_model)
        self.pos = nn.Parameter(torch.zeros(1, max_len, d_model))
        nn.init.trunc_normal_(self.pos, std=0.02)
        layer = nn.TransformerEncoderLayer(
            d_model=d_model, nhead=4, dim_feedforward=d_model * 2,
            dropout=0.0, batch_first=True, norm_first=True, activation="gelu",
        )
        self.encoder = nn.TransformerEncoder(layer, num_layers=2, enable_nested_tensor=False)
        self.proj = nn.Linear(d_model, dim)
        self.max_len = max_len

    def forward(self, idx: torch.Tensor) -> torch.Tensor:
        idx = idx[:, : self.max_len]
        x = self.tok_emb(idx) + self.pos[:, : idx.size(1)]
        mask = (idx != 0).float()
        h = self.encoder(x, src_key_padding_mask=(mask == 0))
        pooled = (h * mask.unsqueeze(-1)).sum(1) / mask.sum(1, keepdim=True).clamp(min=1.0)
        return F.normalize(self.proj(pooled), dim=-1)
