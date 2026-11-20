"""Blender add-on core (bpy-free): timestep choice, scene building, id mapping and frame mapping.

The add-on package ``blender_addon/reality_physics/__init__.py`` imports ``bpy`` at module level, so this test loads
``scene_build.py`` by file path. The Blender-side checks (keyframes, OBJ round trip) are in
``tools/blender_smoke.py`` and need the ``bpy`` module.
"""

import importlib.util
import math
from pathlib import Path

import pytest

from reality.control import multibody_scene as MBS
from reality.control import scene as S

_PATH = Path(__file__).resolve().parents[1] / "blender_addon" / "reality_physics" / "scene_build.py"
_spec = importlib.util.spec_from_file_location("reality_scene_build", _PATH)
SB = importlib.util.module_from_spec(_spec)
_spec.loader.exec_module(SB)


def test_timestep_makes_each_frame_a_whole_number_of_steps():
    for fps in (24.0, 23.976, 25.0, 30.0, 60.0):
        step = SB.bake_timestep(fps)
        assert step["dt"] <= SB.MAX_TIMESTEP_S + 1e-15
        assert step["substeps"] * step["dt"] == pytest.approx(1.0 / fps, rel=1e-12)
        assert isinstance(step["substeps"], int) and step["substeps"] >= 1


def test_timestep_for_24_fps_is_42_substeps():
    step = SB.bake_timestep(24.0)
    assert step["substeps"] == 42
    assert step["dt"] == pytest.approx(1.0 / (24.0 * 42), rel=1e-12)


@pytest.mark.parametrize("bad", [0, -24, float("nan"), float("inf")])
def test_timestep_rejects_bad_fps(bad):
    with pytest.raises(ValueError):
        SB.bake_timestep(bad)


def test_safe_id_maps_blender_names_to_schema_ids():
    assert SB.safe_id("Sphere.001", []) == "Sphere_001"
    assert SB.safe_id("1ball", []) == "b_1ball"
    assert SB.safe_id("Sphere.001", ["Sphere_001"]) == "Sphere_001_2"
    assert SB.safe_id("a b", ["a_b"]) == "a_b_2"
    long_id = SB.safe_id("x" * 200, [])
    assert len(long_id) <= 64 and long_id[0].isalpha()


def test_safe_id_output_always_passes_scene_id_rule():
    for name in ("Sphere", "Sphere.001", "ball-2", "Plane (floor)", "9lives", "é"):
        sid = SB.safe_id(name, [])
        assert S._ID_RE.match(sid), sid
        assert sid[0].isalpha() and len(sid) <= 64


def _ball(**overrides):
    b = {"id": "ball", "radius": 0.05, "material": "steel", "position": [0.0, 0.0, 2.0],
         "velocity": [0.0, 0.0, 0.0], "friction": 0.5, "restitution": 0.6}
    b.update(overrides)
    return b


def _floor(**overrides):
    p = {"id": "floor", "normal": [0.0, 0.0, 1.0], "offset": 0.0, "friction": 0.5, "restitution": 0.6}
    p.update(overrides)
    return p


def test_build_scene_is_valid_v2_and_uses_smaller_coefficients():
    bodies = [_ball(friction=0.3, restitution=0.9), _ball(id="ball2", friction=0.8, restitution=0.2,
                                                           position=[0.2, 0.0, 2.0])]
    planes = [_floor(friction=0.6, restitution=0.5)]
    scene = SB.build_scene(bodies, planes)
    assert MBS.validate_v2(scene)["valid"]
    by_pair = {tuple(sorted((c["a"], c["b"]))): c for c in scene["contacts"]}
    assert by_pair[("ball", "floor")]["friction"] == pytest.approx(0.3)
    assert by_pair[("ball", "floor")]["restitution"] == pytest.approx(0.5)
    assert by_pair[("ball", "ball2")]["friction"] == pytest.approx(0.3)
    assert by_pair[("ball", "ball2")]["restitution"] == pytest.approx(0.2)
    assert len(scene["contacts"]) == 3  # 2 body-plane + 1 body-body


def test_bake_drop_lands_and_bounces_with_no_penetration_and_unit_quaternions():
    out = SB.bake_scene([_ball()], [_floor()], frames=48, fps=24.0, frame_start=1)
    samples = out["samples"]
    assert [s["frame"] for s in samples] == list(range(1, 50))
    assert samples[0]["bodies"]["ball"]["position"][2] == pytest.approx(2.0)
    z = [s["bodies"]["ball"]["position"][2] for s in samples]
    assert min(z) >= 0.05 - 1e-6              # never below the floor (radius above z = 0)
    assert max(z[1:]) < 2.0 + 1e-9            # the ball does not climb above its release height
    assert out["result"]["checks"]["max_penetration_m"] <= 1e-6
    for s in samples:
        q = s["bodies"]["ball"]["quaternion"]
        assert math.sqrt(sum(x * x for x in q)) == pytest.approx(1.0, abs=1e-9)


def test_bake_is_deterministic():
    a = SB.bake_scene([_ball()], [_floor()], frames=24, fps=24.0)
    b = SB.bake_scene([_ball()], [_floor()], frames=24, fps=24.0)
    a["result"].pop("diagnostics")
    b["result"].pop("diagnostics")
    assert a["samples"] == b["samples"]


def test_frame_samples_map_times_to_frames_with_frame_start_offset():
    result = {"records": [{"t": k / 24.0, "bodies": {"b": {"position": [0.0, 0.0, 1.0],
                                                           "quaternion": [1.0, 0.0, 0.0, 0.0]}}}
                          for k in range(4)]}
    frames = [s["frame"] for s in SB.frame_samples(result, 24.0, frame_start=101)]
    assert frames == [101, 102, 103, 104]


def test_frame_samples_reject_records_between_frames():
    result = {"records": [{"t": 0.5 / 24.0, "bodies": {}}]}
    with pytest.raises(ValueError, match="does not fall on a frame"):
        SB.frame_samples(result, 24.0, frame_start=1)


def test_bake_scene_rejects_non_positive_frame_count():
    with pytest.raises(ValueError):
        SB.bake_scene([_ball()], [_floor()], frames=0, fps=24.0)
