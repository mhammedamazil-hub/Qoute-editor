"""The engine's generated files must match the kernel. If this fails, run:
    PYTHONPATH=reality/src python3 reality/tools/export_engine_assets.py
"""

import json
import pathlib
import re

from reality.control import scene as S
from reality.materials import default_database

ENGINE = pathlib.Path(__file__).resolve().parents[2] / "engine"


def test_generated_material_densities_match_database():
    text = (ENGINE / "src" / "physics" / "materials.generated.ts").read_text(encoding="utf-8")
    pairs = dict((k, float(v)) for k, v in re.findall(r'"([a-z_]+)": ([0-9.eE+-]+),', text))
    db = default_database()
    assert set(pairs) == set(db.names())
    for name in db.names():
        assert pairs[name] == float(db.get(name).density), name


def test_fixtures_match_current_scene_files():
    for path in sorted((ENGINE / "public" / "scenes").glob("*.json")):
        scene = json.loads(path.read_text(encoding="utf-8"))
        fixture = json.loads((ENGINE / "test" / "fixtures" / f"{path.stem}.json").read_text(encoding="utf-8"))
        assert fixture["scene_sha256"] == S.scene_hash(scene), path.name
