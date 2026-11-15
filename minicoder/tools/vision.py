"""Image viewer & visual inspection pipeline.

Capabilities (all offline, no network):
* load + normalise an image (PIL), dedupe via SHA-256
* OCR text extraction (RapidOCR when installed, graceful fallback otherwise)
* layout analysis: bounding boxes of coloured regions, edge overflow detection,
  nested-container inference, dominant palette extraction
* neural classification through the project's own MiniViT
* structured semantic description + UI graph, so visual memories can be
  recalled from purely textual chat later ("that red banner from yesterday")
"""

from __future__ import annotations

import json
from dataclasses import dataclass, field, asdict
from pathlib import Path
from typing import Any

import numpy as np
from PIL import Image, ImageDraw

from minicoder.config import CONFIG

_OCR = None


def _get_ocr():
    global _OCR
    if _OCR is None:
        try:
            from rapidocr_onnxruntime import RapidOCR

            _OCR = RapidOCR()
        except Exception:  # pragma: no cover - optional dependency
            _OCR = False
    return _OCR


# ------------------------------------------------------------------ types
@dataclass
class Box:
    x: int
    y: int
    w: int
    h: int
    kind: str = "region"
    label: str = ""
    color: tuple[int, int, int] = (0, 0, 0)
    confidence: float = 1.0


@dataclass
class VisualReport:
    width: int
    height: int
    sha256: str
    ocr_text: str = ""
    ocr_lines: list[dict[str, Any]] = field(default_factory=list)
    boxes: list[Box] = field(default_factory=list)
    palette: list[str] = field(default_factory=list)
    findings: list[str] = field(default_factory=list)
    ui_class: str = ""
    ui_class_confidence: float = 0.0
    class_scores: dict[str, float] = field(default_factory=dict)
    description: str = ""
    ui_graph: dict[str, Any] = field(default_factory=dict)
    ink_rows: int = 0
    ink_ratio: float = 0.0

    def to_json(self) -> dict[str, Any]:
        d = asdict(self)
        d["boxes"] = [asdict(b) if isinstance(b, Box) else b for b in self.boxes]
        return d


# ------------------------------------------------------------------- core
def sha256_img(img: Image.Image) -> str:
    import hashlib

    h = hashlib.sha256()
    h.update(np.asarray(img.convert("RGB")).tobytes())
    return h.hexdigest()


def run_ocr(img: Image.Image) -> tuple[str, list[dict[str, Any]]]:
    ocr = _get_ocr()
    if not ocr:
        return "", []
    arr = np.asarray(img.convert("RGB"))
    try:
        result, _ = ocr(arr)
    except Exception:
        return "", []
    lines = []
    for item in result or []:
        box, text, score = item[0], item[1], float(item[2])
        xs = [p[0] for p in box]
        ys = [p[1] for p in box]
        lines.append(
            {
                "text": text,
                "confidence": round(score, 4),
                "box": [int(min(xs)), int(min(ys)), int(max(xs) - min(xs)), int(max(ys) - min(ys))],
            }
        )
    lines.sort(key=lambda l: (l["box"][1], l["box"][0]))
    return " ".join(l["text"] for l in lines), lines


def detect_regions(img: Image.Image, min_area_ratio: float = 0.004) -> list[Box]:
    """Connected-component layout analysis over quantised colours."""
    rgb = np.asarray(img.convert("RGB"))
    h, w, _ = rgb.shape
    # quantise to reduce anti-aliasing noise
    q = (rgb // 24 * 24).astype(np.int32)
    key = q[:, :, 0] * 10000 + q[:, :, 1] * 100 + q[:, :, 2]
    boxes: list[Box] = []
    for colour_key in np.unique(key):
        mask = key == colour_key
        if mask.sum() < min_area_ratio * w * h:
            continue
        ys, xs = np.where(mask)
        x0, x1, y0, y1 = xs.min(), xs.max(), ys.min(), ys.max()
        fill = mask.sum() / max(1, (x1 - x0 + 1) * (y1 - y0 + 1))
        if fill < 0.55:
            continue
        cval = rgb[mask].mean(axis=0).astype(int)
        boxes.append(
            Box(
                x=int(x0),
                y=int(y0),
                w=int(x1 - x0 + 1),
                h=int(y1 - y0 + 1),
                kind="region",
                color=(int(cval[0]), int(cval[1]), int(cval[2])),
                confidence=round(float(fill), 3),
            )
        )
    boxes.sort(key=lambda b: -b.w * b.h)
    return boxes[:24]


def ink_coverage(img: Image.Image) -> float:
    """Fraction of pixels that differ from the background — how much "content" exists."""
    gray = np.asarray(img.convert("L"), dtype=np.float32)
    # Count everything that differs from the *corner* background: a solid block
    # of near-background colour is still content, however subtle its delta.
    bg = float(np.median([gray[0, 0], gray[0, -1], gray[-1, 0], gray[-1, -1]]))
    return float((np.abs(gray - bg) > 8).mean())


def count_edge_ink(img: Image.Image, edge_ratio: float = 0.985) -> int:
    """Number of text-like rows whose dark pixels reach the right edge.

    A row counts when it contains ink somewhere in the left 90% *and* also in
    the final ~1.5% of columns — the signature of a clipped line.
    """
    gray = np.asarray(img.convert("L"), dtype=np.float32)
    h, w = gray.shape
    bg = float(np.median(gray))
    ink = np.abs(gray - bg) > 40
    edge = ink[:, int(w * edge_ratio) :]
    body = ink[:, : int(w * 0.9)]
    rows = int(((edge.sum(axis=1) >= 2) & (body.sum(axis=1) >= 4)).sum())
    return rows


def extract_palette(img: Image.Image, k: int = 5) -> list[str]:
    small = img.convert("RGB").resize((48, 48))
    q = small.quantize(colors=k, method=Image.Quantize.MEDIANCUT)
    pal = q.getpalette() or []
    counts = sorted(q.getcolors() or [], reverse=True)
    out: list[str] = []
    for _count, idx in counts[:k]:
        r, g, b = pal[idx * 3 : idx * 3 + 3]
        out.append(f"#{r:02x}{g:02x}{b:02x}")
    return out


def _luminance(c: tuple[int, int, int]) -> float:
    r, g, b = [v / 255 for v in c]
    return 0.2126 * r + 0.7152 * g + 0.0722 * b


def analyse_layout(report: VisualReport) -> list[str]:
    """Deterministic heuristic findings — labelled as hypotheses, not facts.

    Signals are geometric and photometric only; no claim is made about intent.
    """
    findings: list[str] = []
    w, h = report.width, report.height
    tol = 2
    for b in report.boxes:
        if b.x + b.w > w + tol or b.y + b.h > h + tol:
            findings.append(f"overflow: region at ({b.x},{b.y}) extends past the {w}x{h} viewport")
        # A block that ends within a hairline of the right edge is clipped by it.
        elif b.x + b.w >= w - 2 and b.w > 0.25 * w and b.h > 0.02 * h and (b.x > 2 or b.y > 2):
            findings.append(
                f"overflow: region at ({b.x},{b.y}) is clipped by the right edge "
                f"({b.x + b.w}/{w}px)"
            )
    if len(report.boxes) >= 3:
        # Column edges of side-by-side blocks only; a full-bleed background and
        # stacked full-width rows legitimately start at different x positions.
        columns = [b for b in report.boxes if b.w < 0.6 * w and b.h > 0.15 * h]
        xs = sorted({b.x for b in columns})
        gaps = [b - a for a, b in zip(xs, xs[1:])]
        if len(gaps) >= 2 and min(gaps) > 0 and (max(gaps) - min(gaps)) > 0.12 * w:
            findings.append(
                f"alignment: column gutters vary by {max(gaps) - min(gaps)}px "
                f"({min(gaps)}px vs {max(gaps)}px)"
            )
    if report.palette and len(report.palette) >= 2:
        cols = [tuple(int(p[i : i + 2], 16) for i in (1, 3, 5)) for p in report.palette[:4]]
        lums = sorted(_luminance(c) for c in cols)
        spread = lums[-1] - lums[0]
        # Real failure = the text/background pair is unreadable: a WCAG contrast
        # ratio under 3:1. Low overall spread alone is normal for skeletons and
        # soft surfaces, so it is not enough to call it a defect.
        ratio = (lums[-1] + 0.05) / (lums[0] + 0.05)
        # Skeletons/placeholders are intentionally low-contrast and are made of
        # large filled blocks, so "how much ink" cannot separate them from text —
        # the *shape* does. Text produces many short horizontal ink runs; blocks
        # produce few long ones. Flag only the text-like case.
        if spread < 0.20 and ratio < 3.0 and report.ink_rows == 0 and 0.02 < report.ink_ratio < 0.15:
            findings.append(
                f"contrast: dominant colours reach only {ratio:.2f}:1 contrast (needs 3:1 minimum)"
            )
    # Truncation without OCR: count rows of "ink" that run into the right edge.
    if getattr(report, "ink_rows", 0) >= 3:
        findings.append(
            f"truncation: {report.ink_rows} text row(s) run into the right edge"
        )
    texts = [l for l in report.ocr_lines]
    if texts:
        clipped = [l for l in texts if l["box"][0] + l["box"][2] >= w - 2]
        if clipped:
            findings.append(f"truncation: {len(clipped)} OCR line(s) touch the right edge")
        if any(k in report.ocr_text.lower() for k in ("error", "failed", "exception")):
            findings.append("error-message: OCR contains an error keyword")
    return findings


def describe(report: VisualReport) -> str:
    parts = [f"{report.width}x{report.height} screenshot"]
    if report.ocr_text:
        snippet = report.ocr_text[:120]
        parts.append(f'text reads "{snippet}"')
    if report.palette:
        parts.append("dominant colours " + ", ".join(report.palette[:3]))
    parts.append(f"{len(report.boxes)} layout regions detected")
    if report.ui_class:
        parts.append(f"looks like a {report.ui_class.replace('_', ' ')}")
    if report.findings:
        parts.append("issues: " + "; ".join(report.findings[:3]))
    return ", ".join(parts) + "."


def build_ui_graph(report: VisualReport) -> dict[str, Any]:
    """Nested containment graph of detected regions (a crude UI accessibility tree)."""
    nodes = []
    for i, b in enumerate(report.boxes):
        nodes.append({"id": i, "role": b.kind, "label": b.label or f"region{i}", "box": [b.x, b.y, b.w, b.h]})
    edges = []
    for i, a in enumerate(report.boxes):
        for j, b in enumerate(report.boxes):
            if i == j:
                continue
            inside = a.x <= b.x and a.y <= b.y and a.x + a.w >= b.x + b.w and a.y + a.h >= b.y + b.h
            if inside and (a.w * a.h) > (b.w * b.h):
                edges.append({"parent": i, "child": j, "relation": "contains"})
    roots = [n["id"] for n in nodes if not any(e["child"] == n["id"] for e in edges)]
    return {"nodes": nodes, "edges": edges, "roots": roots}


def classify(img: Image.Image, model=None, vocab: list[str] | None = None) -> tuple[str, float, dict[str, float]]:
    """Neural UI-defect classification through the project's MiniViT."""
    if model is None:
        return "", 0.0, {}
    import torch
    import torch.nn.functional as F

    from minicoder.model.vision import to_tensor

    x = to_tensor([img], size=model.cfg.vision_image_size)
    with torch.no_grad():
        logits = model(x)
        probs = F.softmax(logits, dim=-1)[0]
    labels = vocab or [str(i) for i in range(probs.numel())]
    scores = {labels[i]: round(float(probs[i]), 4) for i in range(min(len(labels), probs.numel()))}
    best = max(scores, key=scores.get)
    return best, scores[best], scores


def inspect(
    image: str | Path | Image.Image,
    *,
    save_to_memory: bool = True,
    use_vision_model: bool = True,
    ocr: bool = True,
) -> VisualReport:
    """Full visual inspection pass; optionally stores a visual memory record."""
    from minicoder.data import VISION_CLASSES

    if isinstance(image, (str, Path)):
        img = Image.open(image).convert("RGB")
    else:
        img = image.convert("RGB")
    report = VisualReport(width=img.width, height=img.height, sha256=sha256_img(img))
    if ocr:
        report.ocr_text, report.ocr_lines = run_ocr(img)
    report.boxes = detect_regions(img)
    report.ink_rows = count_edge_ink(img)
    report.ink_ratio = round(ink_coverage(img), 4)
    report.palette = extract_palette(img)
    if use_vision_model:
        model = _vision_model()
        if model is not None:
            cls, conf, scores = classify(img, model, VISION_CLASSES)
            report.ui_class, report.ui_class_confidence, report.class_scores = cls, conf, scores
    report.findings = analyse_layout(report)
    report.ui_graph = build_ui_graph(report)
    report.description = describe(report)
    if save_to_memory:
        _store(report, img)
    return report


_VISION = None


def _vision_model():
    global _VISION
    if _VISION is None:
        path = CONFIG.paths.checkpoints / "vision.pt"
        if not path.exists():
            _VISION = False
        else:
            from minicoder.model.vision import load_vision

            _VISION = load_vision(path)
    return _VISION or None


def reset_vision_cache() -> None:
    global _VISION
    _VISION = None


def _store(report: VisualReport, img: Image.Image) -> None:
    from minicoder.memory.db import BrainDB

    db = BrainDB()
    cache = CONFIG.paths.visual_cache
    cache.mkdir(parents=True, exist_ok=True)
    existing = db.query_one("SELECT id FROM visual_memories WHERE sha256=?", (report.sha256,))
    img_path = cache / f"{report.sha256[:16]}.png"
    if not img_path.exists():
        img.save(img_path)
    thumb = img.copy()
    thumb.thumbnail((160, 160))
    thumb_path = cache / f"{report.sha256[:16]}_thumb.png"
    thumb.save(thumb_path)
    payload = (
        str(img_path.relative_to(CONFIG.paths.home)),
        str(thumb_path.relative_to(CONFIG.paths.home)),
        report.sha256,
        report.width,
        report.height,
        report.ocr_text,
        report.description,
        json.dumps([asdict(b) for b in report.boxes]),
        json.dumps([report.ui_class] if report.ui_class else []),
    )
    if existing:
        db.execute(
            "UPDATE visual_memories SET ocr_text=?, description=?, boxes=? WHERE id=?",
            (report.ocr_text, report.description, payload[7], existing["id"]),
        )
        return
    from minicoder.memory.db import utcnow

    db.execute(
        "INSERT INTO visual_memories(ts, image_path, thumb_path, sha256, width, height, ocr_text,"
        " description, boxes, labels, status, source) VALUES (?,?,?,?,?,?,?,?,?,?,?,?)",
        (*payload, "UNVERIFIED", "visual_inspection"),
    )
    db.log_provenance("visual_memories", None, "inspect", detail={"sha": report.sha256[:12]})
