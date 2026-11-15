"""Vision model training + inference helpers (the image viewer's neural core)."""

from __future__ import annotations

import json
import random
from pathlib import Path
from typing import Any

import numpy as np
import torch
import torch.nn.functional as F
from PIL import Image

from minicoder.config import CONFIG, ModelConfig
from minicoder.model.transformer import MiniViT

_MEAN = np.array([0.5, 0.5, 0.5], dtype=np.float32)
_STD = np.array([0.5, 0.5, 0.5], dtype=np.float32)


def to_tensor(images: list[Image.Image], size: int = 32) -> torch.Tensor:
    arrs = []
    for img in images:
        im = img.convert("RGB").resize((size, size), Image.BILINEAR)
        a = np.asarray(im, dtype=np.float32) / 255.0
        a = (a - _MEAN) / _STD
        arrs.append(torch.from_numpy(a).permute(2, 0, 1))
    return torch.stack(arrs)


def train_vision(
    train: list[tuple[Image.Image, int]],
    test: list[tuple[Image.Image, int]],
    epochs: int = 12,
    batch_size: int = 32,
    lr: float = 2e-3,
    seed: int = 0,
    progress: Any = None,
    image_size: int | None = None,
) -> dict[str, Any]:
    cfg = ModelConfig()
    if image_size:
        cfg = ModelConfig(vision_image_size=image_size, vision_patch=4)
    torch.manual_seed(seed)
    n_classes = max(label for _, label in train) + 1
    model = MiniViT(cfg, n_classes=n_classes)
    opt = torch.optim.AdamW(model.parameters(), lr=lr, weight_decay=1e-4)
    rng = random.Random(seed)
    order = list(range(len(train)))
    t0 = __import__("time").time()
    history = []
    best_acc, best_state, best_epoch = -1.0, None, 0
    for epoch in range(epochs):
        rng.shuffle(order)
        total, correct, loss_sum, n = 0, 0, 0.0, 0
        model.train()
        for i in range(0, len(order), batch_size):
            batch = [train[j] for j in order[i : i + batch_size]]
            x = to_tensor([b[0] for b in batch], cfg.vision_image_size)
            y = torch.tensor([b[1] for b in batch])
            logits = model(x)
            loss = F.cross_entropy(logits, y)
            opt.zero_grad(set_to_none=True)
            loss.backward()
            opt.step()
            loss_sum += float(loss.detach()) * len(batch)
            correct += int((logits.argmax(-1) == y).sum())
            total += len(batch)
            n += 1
        model.eval()
        with torch.no_grad():
            xt = to_tensor([b[0] for b in test], cfg.vision_image_size)
            yt = torch.tensor([b[1] for b in test])
            test_logits = model(xt)
            test_acc = float((test_logits.argmax(-1) == yt).float().mean())
            test_loss = float(F.cross_entropy(test_logits, yt))
        row = {
            "epoch": epoch + 1,
            "train_loss": round(loss_sum / total, 4),
            "train_acc": round(correct / total, 4),
            "test_loss": round(test_loss, 4),
            "test_acc": round(test_acc, 4),
        }
        history.append(row)
        if test_acc > best_acc:  # keep the best checkpoint, not the last one
            best_acc, best_epoch = test_acc, epoch + 1
            best_state = {k: v.detach().clone() for k, v in model.state_dict().items()}
        if progress:
            progress(json.dumps(row))
    if best_state is not None:
        model.load_state_dict(best_state)
    save_vision(model, CONFIG.paths.checkpoints / "vision.pt", best_epoch=best_epoch)
    return {
        "model": "MiniViT",
        "params": model.n_params(),
        "classes": n_classes,
        "epochs": epochs,
        "history": history,
        "final_test_acc": round(best_acc, 4),
        "best_epoch": best_epoch,
        "image_size": cfg.vision_image_size,
        "train_seconds": round(__import__("time").time() - t0, 2),
    }


def save_vision(model: MiniViT, path: Path, best_epoch: int | None = None) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    tmp = path.with_suffix(".tmp")
    torch.save(
        {
            "model_cfg": model.cfg.__dict__,
            "n_classes": model.head.out_features,
            "state_dict": model.state_dict(),
            "best_epoch": best_epoch,
        },
        tmp,
    )
    tmp.replace(path)


def load_vision(path: Path) -> MiniViT:
    blob = torch.load(path, map_location="cpu", weights_only=False)
    cfg = ModelConfig(**blob["model_cfg"])
    model = MiniViT(cfg, n_classes=blob["n_classes"])
    model.load_state_dict(blob["state_dict"])
    model.eval()
    return model
