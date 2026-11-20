"""Schema v2 with meshes (approved extension, Phase 6 of the collision milestone).

A ``reality.scene`` document with ``schema_version`` 2 and a non-empty ``meshes`` list runs on the collision solver
(``control/collision_scene.py``) under the v2 rules: sphere bodies only, no ``static`` flag, planes and spheres as in
v2, and static triangle meshes. Its result is ``reality.collision_run``. A v2 document without meshes (or with an
empty list) still runs on the sphere solver and returns ``reality.multibody_run``, unchanged.
"""

import copy

import pytest

from reality.control import collision_scene as C
from reality.control import multibody_scene as MBS
from reality.control import operations as ops
from reality.control import scene as S
from reality.control.errors import OperationError

FLOOR = {
    "id": "floor",
    "vertices": [[-1.0, -1.0, 0.0], [1.0, -1.0, 0.0], [1.0, 1.0, 0.0], [-1.0, 1.0, 0.0]],
    "triangles": [[0, 1, 2], [0, 2, 3]],
}


def _doc(**extra):
    doc = {
        "schema": "reality.scene", "schema_version": 2, "name": "ball-on-mesh",
        "environment": {"gravity": [0.0, 0.0, -9.80665]},
        "bodies": [{"id": "ball", "type": "sphere", "radius": 0.1, "material": "steel",
                    "position": [0.0, 0.0, 0.5], "velocity": [0.0, 0.0, 0.0], "omega": [0.0, 0.0, 0.0]}],
        "planes": [],
        "meshes": [copy.deepcopy(FLOOR)],
        "contacts": [{"a": "ball", "b": "floor", "friction": 0.3, "restitution": 0.0}],
    }
    doc.update(extra)
    return doc


def test_v2_with_mesh_validates_through_the_scene_validator():
    assert S.validate(_doc()) == {"valid": True, "errors": [], "warnings": []}


def test_v2_with_mesh_runs_on_the_collision_solver_and_returns_collision_run():
    out = ops.call("simulate.multibody", {"scene": _doc(), "duration": 0.2, "dt": 1e-4, "record_interval": 0.05})
    assert out["result_schema"] == "reality.collision_run"
    assert out["scene"]["schema_version"] == 2  # the document is echoed unchanged
    assert out["checks"]["finite_state"] is True


def test_sphere_rests_on_mesh_at_its_radius():
    # Measured in this milestone: centre height 0.100000084 m after 2 s at dt 1e-4 (penetration 8.4e-8 m).
    # The check below runs 0.5 s; the tolerance is the penetration tolerance of the scene run, 1e-6 m.
    res = C.run(_doc(), 0.5, dt=1e-4, record_interval=0.1)
    z = res["final_state"]["bodies"]["ball"]["position"][2]
    assert z == pytest.approx(0.1, abs=1e-6)
    assert res["checks"]["max_penetration_m"] <= res["checks"]["penetration_tolerance_m"]


def test_v2_with_mesh_run_is_deterministic():
    a = C.run(_doc(), 0.2, dt=1e-4, record_interval=0.05)
    b = C.run(_doc(), 0.2, dt=1e-4, record_interval=0.05)
    assert a["final_state"] == b["final_state"]
    assert a["records"] == b["records"]


def test_v2_with_mesh_refuses_box_bodies_with_the_v2_reason():
    doc = _doc()
    doc["bodies"].append({"id": "blk", "type": "box", "half_extents": [0.1, 0.1, 0.1], "material": "steel",
                          "position": [1.0, 0.0, 1.0], "velocity": [0.0, 0.0, 0.0], "omega": [0.0, 0.0, 0.0]})
    errors = S.validate(doc)["errors"]
    assert any("sphere bodies only" in e and "blk" in e for e in errors), errors
    with pytest.raises(OperationError) as err:
        ops.call("simulate.multibody", {"scene": doc, "duration": 0.1})
    assert err.value.code == "schema_error"


def test_v2_with_mesh_refuses_the_static_flag():
    doc = _doc()
    doc["bodies"][0]["static"] = False
    errors = S.validate(doc)["errors"]
    assert any("no static flag" in e for e in errors), errors


def test_v2_with_mesh_still_checks_the_mesh():
    doc = _doc()
    doc["meshes"][0]["triangles"] = [[0, 1, 9]]  # index out of range
    assert S.validate(doc)["valid"] is False
    with pytest.raises(OperationError) as err:
        ops.call("simulate.multibody", {"scene": doc, "duration": 0.1})
    assert err.value.code == "schema_error"


def test_v2_sphere_solver_refuses_meshes_explicitly():
    errors = MBS.validate_v2(_doc())["errors"]
    assert any("collision solver" in e for e in errors), errors
    with pytest.raises(OperationError) as err:
        MBS.run(_doc(), 0.1)
    assert err.value.code == "schema_error"


def test_v2_without_meshes_keeps_the_sphere_path():
    doc = _doc(contacts=[])
    doc["meshes"] = []
    assert C.is_v2_with_meshes(doc) is False
    assert S.validate(doc)["valid"] is True
    out = ops.call("simulate.multibody", {"scene": doc, "duration": 0.05, "dt": 1e-4})
    assert out["result_schema"] == "reality.multibody_run"


def test_v2_without_the_meshes_key_keeps_the_sphere_path():
    doc = _doc(contacts=[])
    del doc["meshes"]
    assert C.is_v2_with_meshes(doc) is False
    out = ops.call("simulate.multibody", {"scene": doc, "duration": 0.05, "dt": 1e-4})
    assert out["result_schema"] == "reality.multibody_run"


def test_v3_documents_are_not_treated_as_v2_with_meshes():
    doc = _doc()
    doc["schema_version"] = 3
    assert C.is_v2_with_meshes(doc) is False
    assert C.validate_v3(doc)["valid"] is True
