"""Visual & multimodal buffer.

Offline-first image memory and analysis built from scratch on Pillow/Numpy:
  * perceptual hashing (aHash/dHash) for dedup
  * thumbnail cache + luminance / edge-density / contrast statistics
  * simple rule-based UI heuristics (low-contrast text candidate detection,
    horizontal-overflow risk by ink coverage)
  * OCR is pluggable: if rapidocr/pytesseract is importable it is used,
    otherwise the pipeline reports OCR as unavailable instead of fabricating text.
"""
from __future__ import annotations
import json
import math
from pathlib import Path
import numpy as np
from PIL import Image, ImageFilter, ImageStat
from .config import get_settings
from .db import connect, log_provenance
from .util import new_id, now_iso, sha256_file, utcnow_compact


# ------------------------------------------------------------------- hashing
def _gray_small(img: Image.Image, size: tuple[int, int]) -> np.ndarray:
    return np.asarray(img.convert("L").resize(size, Image.LANCZOS), dtype=np.float32)


def average_hash(img: Image.Image, size: int = 8) -> str:
    px = _gray_small(img, (size, size))
    bits = px > px.mean()
    return "".join("1" if b else "0" for b in bits.flatten())


def difference_hash(img: Image.Image, size: int = 8) -> str:
    px = _gray_small(img, (size + 1, size))
    bits = px[:, 1:] > px[:, :-1]
    return "".join("1" if b else "0" for b in bits.flatten())


def hamming(a: str, b: str) -> int:
    return sum(c1 != c2 for c1, c2 in zip(a, b)) + abs(len(a) - len(b))


# ------------------------------------------------------------------ analysis
def image_stats(img: Image.Image) -> dict:
    gray = img.convert("L")
    small = gray.resize((min(256, gray.width), max(1, int(gray.height * min(256, gray.width) / gray.width))))
    stat = ImageStat.Stat(small)
    arr = np.asarray(small, dtype=np.float32)
    gx = np.abs(np.diff(arr, axis=1)).mean() if arr.shape[1] > 1 else 0.0
    gy = np.abs(np.diff(arr, axis=0)).mean() if arr.shape[0] > 1 else 0.0
    color = ImageStat.Stat(img.convert("RGB"))
    contrast = float(arr.std())
    return {
        "width": img.width, "height": img.height, "mode": img.mode,
        "mean_luma": round(float(stat.mean[0]), 2),
        "contrast": round(contrast, 2),
        "edge_density": round(float(gx + gy), 3),
        "channel_means": [round(float(m), 2) for m in color.mean],
        "aspect_ratio": round(img.width / max(1, img.height), 4),
    }


def contrast_ratio(rgb1: tuple[int, int, int], rgb2: tuple[int, int, int]) -> float:
    def _lum(c: tuple[int, int, int]) -> float:
        def lin(ch: int) -> float:
            v = ch / 255.0
            return v / 12.92 if v <= 0.03928 else ((v + 0.055) / 1.055) ** 2.4
        r, g, b = (lin(c[0]), lin(c[1]), lin(c[2]))
        return 0.2126 * r + 0.7152 * g + 0.0722 * b
    l1, l2 = sorted((_lum(rgb1), _lum(rgb2)), reverse=True)
    return round((l1 + 0.05) / (l2 + 0.05), 3)


def detect_low_contrast_blocks(img: Image.Image, *, grid: int = 4, threshold: float = 2.2) -> list[dict]:
    """Heuristic: grid cells whose foreground/background luma differ too little
    to be comfortably readable. Flags candidates — never asserts a bug exists."""
    gray = np.asarray(img.convert("L"), dtype=np.float32)
    h, w = gray.shape
    findings = []
    for gy in range(grid):
        for gx in range(grid):
            cell = gray[gy * h // grid:(gy + 1) * h // grid, gx * w // grid:(gx + 1) * w // grid]
            if cell.size == 0:
                continue
            lo, hi = np.percentile(cell, 5), np.percentile(cell, 95)
            if hi - lo < 28 and cell.std() > 3:  # some structure but tiny tonal range
                findings.append({
                    "cell": [gx, gy],
                    "tonal_range": round(float(hi - lo), 2),
                    "note": "low local contrast — possible hard-to-read text/detail",
                })
    return findings


def detect_overflow_risk(img: Image.Image) -> dict:
    """Ink very close to left/right edges with no margin → horizontal overflow risk."""
    gray = np.asarray(img.convert("L"), dtype=np.float32)
    h, w = gray.shape
    if w < 40:
        return {"overflow_risk": False, "reason": "image too small"}
    margin = max(2, w // 100)
    ink = gray < 200
    left_col = ink[:, :margin].mean()
    right_col = ink[:, -margin:].mean()
    return {
        "overflow_risk": bool(left_col > 0.35 or right_col > 0.35),
        "left_edge_ink": round(float(left_col), 3),
        "right_edge_ink": round(float(right_col), 3),
        "note": "ink saturation near edges; verify with a DOM/layout check before calling it a bug",
    }


# ----------------------------------------------------------------------- OCR
def _ocr_engine():
    try:
        from rapidocr_onnxruntime import RapidOCR  # type: ignore
        return ("rapidocr", RapidOCR())
    except Exception:
        pass
    try:
        import pytesseract  # type: ignore
        return ("pytesseract", pytesseract)
    except Exception:
        return (None, None)


def ocr_image(path: Path) -> dict:
    engine_name, engine = _ocr_engine()
    if engine is None:
        return {"available": False, "engine": None, "text": "",
                "note": "no OCR engine installed (pip install rapidocr-onnxruntime) — refusing to fabricate text"}
    if engine_name == "rapidocr":
        result, _ = engine(str(path))
        text = "\n".join(item[1] for item in (result or []))
        return {"available": True, "engine": "rapidocr", "text": text}
    return {"available": True, "engine": "pytesseract",
            "text": engine.image_to_string(Image.open(path))}


# --------------------------------------------------------------- ingest flow
def ingest_image(path: str | Path, *, description: str = "", tags: list[str] | None = None,
                 source: str = "visual_inspection") -> dict:
    settings = get_settings()
    settings.ensure_dirs()
    src = Path(path).expanduser().resolve()
    if not src.exists():
        raise FileNotFoundError(src)
    img = Image.open(src)
    img.load()
    stats = image_stats(img)
    ahash, dhash = average_hash(img), difference_hash(img)
    digest = sha256_file(src)
    vid = new_id("img")
    thumb_path = settings.visual_cache / f"{vid}.jpg"
    thumb = img.convert("RGB").copy()
    thumb.thumbnail((320, 320))
    thumb.save(thumb_path, "JPEG", quality=82)
    ocrs = ocr_image(src)
    record = {
        "id": vid, "original_path": str(src), "sha256": digest,
        "ahash": ahash, "dhash": dhash, "thumbnail": str(thumb_path),
        "stats": stats, "ocr": ocrs,
        "low_contrast_cells": detect_low_contrast_blocks(img),
        "overflow": detect_overflow_risk(img),
        "description": description, "tags": tags or [],
        "source": source, "created_at": now_iso(),
    }
    meta_path = settings.visual_cache / f"{vid}.json"
    meta_path.write_text(json.dumps(record, indent=2), encoding="utf-8")
    with connect() as con:
        log_provenance(con, "image", vid, source, f"sha256={digest[:16]}")
        from . import vecstore
        text = description or f"image {stats['width']}x{stats['height']} {' '.join(tags or [])}"
        vecstore.embed_and_store(con, vid, "image", text)
    record["meta_path"] = str(meta_path)
    return record


def find_similar_images(ahash: str, *, max_hamming: int = 6, limit: int = 5) -> list[dict]:
    settings = get_settings()
    out = []
    for meta_file in settings.visual_cache.glob("img_*.json"):
        try:
            rec = json.loads(meta_file.read_text(encoding="utf-8"))
        except Exception:
            continue
        d = hamming(ahash, rec.get("ahash", ""))
        if d <= max_hamming:
            out.append({"id": rec["id"], "hamming": d, "thumbnail": rec.get("thumbnail"),
                        "original_path": rec.get("original_path")})
    out.sort(key=lambda r: r["hamming"])
    return out[:limit]
