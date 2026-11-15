import json
import numpy as np
from PIL import Image
from minicoder import visual


def _make_image(tmp_path, name="ui.png", color=(240, 240, 240)):
    img = Image.new("RGB", (160, 100), color)
    for x in range(20, 140):  # dark text-ish bar
        for y in range(40, 60):
            img.putpixel((x, y), (30, 30, 30))
    p = tmp_path / name
    img.save(p)
    return p


def test_ingest_and_stats(brain_home, tmp_path):
    p = _make_image(tmp_path)
    rec = visual.ingest_image(p, description="test UI screenshot", tags=["ui", "test"])
    assert rec["stats"]["width"] == 160
    for key in ("mean_luma", "contrast", "edge_density", "aspect_ratio"):
        assert key in rec["stats"]
    assert "available" in rec["ocr"]  # engine may or may not exist — never fabricated either way
    assert json.loads(open(rec["meta_path"]).read())["id"] == rec["id"]


def test_similar_image_dedup(brain_home, tmp_path):
    p1 = _make_image(tmp_path, "a.png")
    rec = visual.ingest_image(p1, description="original")
    similar = visual.find_similar_images(rec["ahash"])
    assert any(s["id"] == rec["id"] for s in similar)


def test_overflow_heuristic_flags_edge_ink(brain_home):
    img = Image.new("RGB", (200, 100), (255, 255, 255))
    for x in range(0, 6):
        for y in range(100):
            img.putpixel((x, y), (0, 0, 0))
    for x in range(194, 200):
        for y in range(100):
            img.putpixel((x, y), (0, 0, 0))
    out = visual.detect_overflow_risk(img)
    assert out["overflow_risk"] is True
