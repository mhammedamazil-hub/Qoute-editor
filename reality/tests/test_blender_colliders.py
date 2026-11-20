"""Blender add-on core, Phase 6: boxes, static bodies, static triangle meshes (bpy-free).

Loads ``scene_build.py`` by file path, like ``test_blender_scene_build.py``. The Blender-side checks (marking,
OBJ import, keyframes) are in ``tools/blender_smoke.py`` and need ``bpy``.
"""

import importlib.util
import math
from pathlib import Path

import pytest

from reality.control import scene as S

_PATH = Path(__file__).resolve().parents[1] / "blender_addon" / "reality_physics" / "scene_build.py"
_spec = importlib.util.spec_from_file_location("reality_scene_build_colliders", _PATH)
SB = importlib.util.module_from_spec(_spec)
_spec.loader.exec_module(SB)

FLOOR_MESH = {
    "id": "floor", "position": [0.0, 0.0, 0.0],
    "vertices": [[-2.0, -2.0, 0.0], [2.0, -2.0, 0.0], [2.0, 2.0, 0.0], [-2.0, 2.0, 0.0]],
    "triangles": [[0, 1, 2], [0, 2, 3]],
    "friction": 0.4, "restitution": 0.2,
}
GROUND = {"id": "ground", "normal": [0.0, 0.0, 1.0], "offset": 0.0, "friction": 0.5, "restitution": 0.0}


def _box(**overrides):
    b = {"id": "box", "shape": "box", "half_extents": [0.1, 0.1, 0.1], "material": "steel",
         "position": [0.0, 0.0, 0.5], "velocity": [0.0, 0.0, 0.0], "omega": [0.0, 0.0, 0.0],
         "friction": 0.5, "restitution": 0.0}
    b.update(overrides)
    return b


def _ball(**overrides):
    b = {"id": "ball", "shape": "sphere", "radius": 0.05, "material": "steel",
         "position": [0.0, 0.0, 0.5], "velocity": [0.0, 0.0, 0.0], "omega": [0.0, 0.0, 0.0],
         "friction": 0.5, "restitution": 0.0}
    b.update(overrides)
    return b


def test_all_sphere_dynamic_scene_is_still_written_as_v2_and_matches_build_scene():
    bodies = [_ball()]
    planes = [GROUND]
    assert SB.build_any(bodies, planes) == SB.build_scene(bodies, planes)


def test_v2_mesh_scene_adds_meshes_and_mesh_contacts():
    scene = SB.build_any([_ball(friction=0.9, restitution=0.5)], [], [FLOOR_MESH])
    assert scene["schema_version"] == 2
    assert [m["id"] for m in scene["meshes"]] == ["floor"]
    (contact,) = scene["contacts"]
    assert (contact["a"], contact["b"]) == ("ball", "floor")
    assert contact["friction"] == pytest.approx(0.4)      # smaller of 0.9 and 0.4
    assert contact["restitution"] == pytest.approx(0.2)   # smaller of 0.5 and 0.2
    assert S.validate(scene)["valid"]


def test_box_scene_is_v3_and_box_rests_on_plane_at_its_half_height():
    out = SB.bake_scene([_box()], [GROUND], frames=48, fps=24.0, frame_start=1)
    assert out["scene"]["schema_version"] == 3
    z = [s["bodies"]["box"]["position"][2] for s in out["samples"]]
    assert z[-1] == pytest.approx(0.1, abs=1e-4)
    assert out["result"]["checks"]["max_penetration_m"] <= 1e-6
    for s in out["samples"]:
        q = s["bodies"]["box"]["quaternion"]
        assert math.sqrt(sum(x * x for x in q)) == pytest.approx(1.0, abs=1e-9)


def test_sphere_bakes_onto_a_static_mesh_floor_at_its_radius():
    out = SB.bake_scene([_ball()], [], frames=48, fps=24.0, frame_start=1, meshes=[FLOOR_MESH])
    z = out["samples"][-1]["bodies"]["ball"]["position"][2]
    assert z == pytest.approx(0.05, abs=1e-4)
    assert out["keyed"] == ["ball"]
    assert out["static"] == []


def test_static_bodies_and_meshes_are_not_keyed():
    static_box = _box(id="pillar", static=True, position=[1.0, 0.0, 0.0])
    for key in ("material", "velocity", "omega"):
        static_box.pop(key, None)
    static_box["velocity"] = [0.0, 0.0, 0.0]
    static_box["omega"] = [0.0, 0.0, 0.0]
    out = SB.bake_scene([_ball(), static_box], [GROUND], frames=24, fps=24.0, meshes=[FLOOR_MESH])
    assert out["keyed"] == ["ball"]
    assert out["static"] == ["pillar"]
    for s in out["samples"]:
        assert set(s["bodies"]) == {"ball"}
    # the static box is still in the simulation: the scene validates and the static record is present
    assert out["result"]["records"][-1]["bodies"]["pillar"]["static"] is True


def test_dynamic_sphere_rests_on_a_static_box_top():
    top = _box(id="table", static=True, position=[0.0, 0.0, 0.0])
    for key in ("material", "velocity", "omega"):
        top.pop(key, None)
    top["velocity"] = [0.0, 0.0, 0.0]
    top["omega"] = [0.0, 0.0, 0.0]
    out = SB.bake_scene([_ball(position=[0.0, 0.0, 0.4]), top], [], frames=48, fps=24.0, frame_start=1, meshes=[])
    # table top at z = 0.1; the ball (radius 0.05) rests with its centre at z = 0.15
    assert out["samples"][-1]["bodies"]["ball"]["position"][2] == pytest.approx(0.15, abs=1e-4)


def test_box_on_a_mesh_is_refused_with_the_kernel_reason():
    with pytest.raises(ValueError, match="box-mesh"):
        SB.bake_scene([_box()], [], frames=24, fps=24.0, meshes=[FLOOR_MESH])


def test_box_on_box_is_refused_with_the_kernel_reason():
    other = _box(id="box2", position=[0.5, 0.0, 0.5])
    with pytest.raises(ValueError, match="box-box"):
        SB.bake_scene([_box(), other], [GROUND], frames=24, fps=24.0)


def test_dynamic_body_without_material_is_refused():
    bad = _box()
    del bad["material"]
    with pytest.raises(ValueError, match="material"):
        SB.bake_scene([bad], [GROUND], frames=24, fps=24.0)


def test_static_body_with_velocity_is_refused():
    bad = _box(id="pillar", static=True)
    bad.pop("material")
    bad["velocity"] = [0.0, 0.0, 1.0]
    with pytest.raises(ValueError, match="zero velocity"):
        SB.bake_scene([bad], [GROUND], frames=24, fps=24.0)


def test_two_static_bodies_never_get_a_contact():
    a = _box(id="a", static=True, position=[0.0, 0.0, 0.0])
    b = _box(id="b", static=True, position=[0.5, 0.0, 0.0])
    for body in (a, b):
        body.pop("material")
        body["velocity"] = [0.0, 0.0, 0.0]
        body["omega"] = [0.0, 0.0, 0.0]
    scene = SB.build_any([a, b, _ball()], [])
    pairs = {tuple(sorted((c["a"], c["b"]))) for c in scene["contacts"]}
    assert ("a", "b") not in pairs
    assert ("a", "ball") in pairs and ("b", "ball") in pairs  # pairs are stored sorted


def test_box_bake_is_deterministic():
    a = SB.bake_scene([_box()], [GROUND], frames=24, fps=24.0)
    b = SB.bake_scene([_box()], [GROUND], frames=24, fps=24.0)
    a["result"].pop("diagnostics")
    b["result"].pop("diagnostics")
    assert a["samples"] == b["samples"]


def test_frame_samples_can_keep_only_selected_ids():
    result = {"records": [{"t": 0.0, "bodies": {"a": {"position": [0.0, 0.0, 1.0], "quaternion": [1.0, 0.0, 0.0, 0.0]},
                                               "b": {"position": [0.0, 0.0, 2.0], "quaternion": [1.0, 0.0, 0.0, 0.0]}}}]}
    (s,) = SB.frame_samples(result, 24.0, frame_start=1, ids=["b"])
    assert set(s["bodies"]) == {"b"}


def test_unit_quaternion_fixes_float32_rounding_to_double_precision():
    import struct
    q32 = [struct.unpack("f", struct.pack("f", x))[0] for x in (0.7071068, 0.7071068, 0.0, 0.0)]
    assert abs(math.sqrt(sum(x * x for x in q32)) - 1.0) > 1e-9  # the float32 input is outside the kernel tolerance
    u = SB.unit_quaternion(q32)
    assert abs(math.sqrt(sum(x * x for x in u)) - 1.0) <= 1e-15
    assert SB.unit_quaternion([1.0, 0.0, 0.0, 0.0]) == [1.0, 0.0, 0.0, 0.0]


def test_unit_quaternion_rejects_zero_and_non_finite_input():
    with pytest.raises(ValueError):
        SB.unit_quaternion([0.0, 0.0, 0.0, 0.0])
    with pytest.raises(ValueError):
        SB.unit_quaternion([1.0, float("nan"), 0.0, 0.0])
    with pytest.raises(ValueError):
        SB.unit_quaternion([1.0, 0.0, 0.0])
