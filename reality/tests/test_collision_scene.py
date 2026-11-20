"""Schema v3 collision scenes: validation with explicit reasons, unsupported pairs, limits, runs and operations.

v1 and v2 are covered by their own files (test_control.py, test_multibody_scene.py) which are unchanged.
"""

import copy
import math
import threading

import pytest

from reality.control import collision_scene as C
from reality.control import operations as ops
from reality.control import scene as S
from reality.control.errors import OperationError
from reality.materials import default_database

GRAV = [0.0, 0.0, -9.80665]


def _doc(bodies=(), planes=(), meshes=(), contacts=()):
    # deep copies: mutation tests edit their document, which must never leak into another test
    return copy.deepcopy({"schema": S.SCHEMA, "schema_version": 3, "name": "t", "environment": {"gravity": GRAV},
                          "bodies": list(bodies), "planes": list(planes), "meshes": list(meshes),
                          "contacts": list(contacts)})


def _box(bid="box", z=0.2, **extra):
    b = {"id": bid, "type": "box", "half_extents": [0.1, 0.05, 0.2], "density": 2500.0,
         "position": [0.0, 0.0, z], "velocity": [0.0, 0.0, 0.0], "omega": [0.0, 0.0, 0.0]}
    b.update(extra)
    return b


def _sphere(bid="ball", z=1.0, **extra):
    b = {"id": bid, "type": "sphere", "radius": 0.1, "mass": 1.0, "position": [0.0, 0.0, z],
         "velocity": [0.0, 0.0, 0.0], "omega": [0.0, 0.0, 0.0]}
    b.update(extra)
    return b


FLOOR = {"id": "floor", "normal": [0.0, 0.0, 1.0], "offset": 0.0}
TWO_TRI = {"id": "floor_mesh", "vertices": [[-1, -1, 0], [1, -1, 0], [1, 1, 0], [-1, 1, 0]],
           "triangles": [[0, 1, 2], [0, 2, 3]]}


def _swap_material(body, name):
    body.pop("density")
    body["material"] = name


def _errors(doc):
    return C.validate_v3(doc)["errors"]


# ---------------------------------------------------------------- valid documents
def test_valid_box_on_plane_document_passes():
    doc = _doc([_box()], [FLOOR], contacts=[{"a": "box", "b": "floor", "friction": 0.5, "restitution": 0.0}])
    r = C.validate_v3(doc)
    assert r["valid"] and r["errors"] == []
    assert r["counts"] == {"bodies": 1, "planes": 1, "meshes": 0, "contacts": 1, "triangles": 0}


def test_valid_mesh_and_static_sphere_document_passes():
    doc = _doc([_sphere(), _box(z=0.5), _sphere("pillar", z=0.0, mass=None, static=True)],
               meshes=[TWO_TRI],
               contacts=[{"a": "ball", "b": "floor_mesh", "friction": 0.1, "restitution": 0.5},
                         {"a": "box", "b": "pillar", "friction": 0.2, "restitution": 0.0}])
    doc["bodies"][2].pop("mass")
    assert C.validate_v3(doc)["valid"], C.validate_v3(doc)["errors"]


def test_quaternion_is_optional_and_must_be_unit():
    ok = _doc([_box(quaternion=[0.7071067811865476, 0.0, 0.0, 0.7071067811865476])], [FLOOR])
    assert C.validate_v3(ok)["valid"]
    bad = _doc([_box(quaternion=[1.0, 1.0, 0.0, 0.0])], [FLOOR])
    assert any("quaternion must be four finite numbers, unit length" in e for e in _errors(bad))


# ---------------------------------------------------------------- explicit rejections
@pytest.mark.parametrize("mutate, fragment", [
    (lambda d: d.update(schema_version=2), "schema_version must be 3"),
    (lambda d: d.update(schema="wrong"), "schema must be"),
    (lambda d: d["environment"].update(gravity=[0, 0]), "environment.gravity must be three finite numbers"),
    (lambda d: d.update(bodies=[]), "bodies must be a non-empty list"),
    (lambda d: d.update(planes="floor"), "planes must be a list"),
    (lambda d: d["bodies"][0].update(type="cylinder"), "type must be 'sphere' or 'box'"),
    (lambda d: d["bodies"][0].update(id="1bad"), "id must be a letter-first identifier"),
    (lambda d: d["bodies"][0].update(half_extents=[0.1, 0.0, 0.1]), "half_extents must be three finite numbers > 0"),
    (lambda d: d["bodies"][0].update(half_extents=[0.1, float("nan"), 0.1]), "half_extents must be three"),
    (lambda d: d["bodies"][0].pop("density"), "give exactly one of material, mass or density"),
    (lambda d: d["bodies"][0].update(mass=3.0), "give exactly one of material, mass or density"),
    (lambda d: _swap_material(d["bodies"][0], "unobtainium"), "unknown material 'unobtainium'"),
    (lambda d: d["bodies"][0].update(density=-1.0), "density must be a finite number > 0"),
    (lambda d: d["bodies"][0].update(position=[0, 0]), "position must be three finite numbers"),
    (lambda d: d["bodies"][0].update(static=True, velocity=[1.0, 0.0, 0.0]),
     "a static body must have zero velocity and omega"),
    (lambda d: d["bodies"][0].update(static="yes"), "static must be true or false"),
    (lambda d: d["bodies"][0].update(id="floor"), "duplicate id"),
    (lambda d: d["planes"][0].update(normal=[0, 0, 0]), "normal must be three finite numbers, not all zero"),
    (lambda d: d["planes"][0].update(offset="x"), "offset must be a finite number"),
    (lambda d: d["contacts"][0].update(a="nope"), "a='nope' is not a body id"),
    (lambda d: d["contacts"][0].update(b="nope"), "b='nope' is not a body, plane or mesh id"),
    (lambda d: d["contacts"][0].update(friction=-0.1), "friction must be a finite number >= 0"),
    (lambda d: d["contacts"][0].update(restitution=1.5), "restitution must be a number in [0, 1]"),
    (lambda d: d["contacts"].append(dict(d["contacts"][0])), "listed more than once"),
])
def test_invalid_document_is_rejected_with_the_reason(mutate, fragment):
    doc = _doc([_box()], [FLOOR], contacts=[{"a": "box", "b": "floor", "friction": 0.5, "restitution": 0.0}])
    mutate(doc)
    errors = _errors(doc)
    assert errors, "invalid document was accepted"
    assert any(fragment in e for e in errors), errors


def test_self_contact_and_static_static_are_rejected():
    doc = _doc([_box(), _sphere("s", static=True, velocity=[0, 0, 0])],
               contacts=[{"a": "box", "b": "box", "friction": 0.1, "restitution": 0.0}])
    assert any("cannot contact itself" in e for e in _errors(doc))
    static_pair = _doc([_sphere("p", static=True, mass=None), _sphere("q", static=True, mass=None, z=1.0)],
                       contacts=[{"a": "p", "b": "q", "friction": 0.1, "restitution": 0.0}])
    static_pair["bodies"][0].pop("mass")
    static_pair["bodies"][1].pop("mass")
    assert any("two static bodies cannot form a contact" in e for e in _errors(static_pair))


def test_box_box_is_refused_explicitly_not_ignored():
    doc = _doc([_box("a"), _box("b", z=1.0)],
               contacts=[{"a": "a", "b": "b", "friction": 0.1, "restitution": 0.0}])
    errors = _errors(doc)
    assert any("unsupported pair box-box" in e and "not implemented" in e for e in errors), errors


def test_box_mesh_is_refused_explicitly():
    doc = _doc([_box()], meshes=[TWO_TRI], contacts=[{"a": "box", "b": "floor_mesh", "friction": 0.1,
                                                      "restitution": 0.0}])
    assert any("unsupported pair box-mesh" in e for e in _errors(doc))


def test_mesh_errors_are_reported_with_the_mesh_id():
    bad_mesh = {"id": "m", "vertices": [[0, 0, 0], [1, 0, 0], [0, 1, 0]], "triangles": [[0, 1, 9]]}
    errors = _errors(_doc([_sphere()], meshes=[bad_mesh]))
    assert any("meshes[0] ('m')" in e and "outside 0..2" in e for e in errors), errors


def test_resource_limits_are_reported_as_errors():
    many = [_sphere(f"s{i}", z=float(i)) for i in range(C.LIMITS["max_bodies"] + 1)]
    assert any("exceed the limit" in e for e in _errors(_doc(many)))


def test_validate_never_raises_on_malformed_input():
    for junk in (None, 5, "x", [], {}, {"bodies": 5}, {"schema_version": 3, "bodies": [None]},
                 {"schema_version": 3, "bodies": [{"id": None}], "contacts": [None]}):
        r = C.validate_v3(junk)
        assert r["valid"] is False and r["errors"]


def test_require_valid_raises_schema_error_with_errors_attached():
    with pytest.raises(OperationError) as info:
        C.require_valid_v3(_doc([]))
    assert info.value.code == "schema_error"
    assert info.value.details["errors"]


# ---------------------------------------------------------------- materials and mass
def test_material_gives_mass_from_the_database_density():
    steel = default_database().get("steel").density
    b = _sphere(mass=None, material="steel")
    b.pop("mass")
    doc = _doc([b], [FLOOR])
    assert C.validate_v3(doc)["valid"]
    mass, volume = C._mass_props(b)
    assert mass == pytest.approx(steel * 4.0 / 3.0 * math.pi * 0.1 ** 3, rel=1e-14)


# ---------------------------------------------------------------- dispatch
def test_scene_validate_routes_version_3_to_the_collision_schema():
    assert S.validate(_doc([_box()], [FLOOR]))["valid"]
    # a box-box pair is only refused by the v3 validator, so this proves the v3 path ran
    boxes = _doc([_box("a"), _box("b", z=1.0)], contacts=[{"a": "a", "b": "b", "friction": 0.1, "restitution": 0.0}])
    v = S.validate(boxes)
    assert v["valid"] is False and any("unsupported pair box-box" in e for e in v["errors"])


# ---------------------------------------------------------------- runs
def test_box_rests_on_plane_and_the_run_document_is_complete():
    doc = _doc([_box(z=0.2 + 0.001)], [FLOOR], contacts=[{"a": "box", "b": "floor", "friction": 0.5,
                                                          "restitution": 0.0}])
    r = C.run(doc, 1.0, dt=1e-4, record_interval=0.1)
    assert r["result_schema"] == "reality.collision_run" and r["result_schema_version"] == 1
    assert r["configuration"]["steps"] == 10000
    assert len(r["records"]) == 11
    final = r["records"][-1]["bodies"]["box"]
    assert final["position"][2] == pytest.approx(0.2, abs=1e-4)
    assert abs(final["velocity"][2]) < 1e-3
    assert r["checks"]["max_penetration_m"] <= 1e-6
    assert r["checks"]["max_quaternion_norm_error"] < 1e-12
    assert "wall_seconds" in r["diagnostics"]
    assert r["random_seed"] is None


def test_sphere_on_mesh_never_sinks_below_the_surface_and_has_no_ghost_drift():
    ball = _sphere(z=0.5, velocity=[0.0, 0.0, 0.0], position=[0.2, 0.1, 0.5])
    doc = _doc([ball], meshes=[TWO_TRI],
               contacts=[{"a": "ball", "b": "floor_mesh", "friction": 0.2, "restitution": 0.0}])
    r = C.run(doc, 2.0, dt=1e-4, record_interval=0.05)
    zs = [rec["bodies"]["ball"]["position"][2] for rec in r["records"]]
    xs = [rec["bodies"]["ball"]["position"][0] for rec in r["records"]]
    assert min(zs[len(zs) // 2:]) == pytest.approx(0.1, abs=1e-6)
    assert max(abs(x - 0.2) for x in xs) < 1e-9
    assert r["checks"]["max_penetration_m"] <= 1e-6


def test_run_is_deterministic():
    doc = _doc([_box(z=0.201)], [FLOOR], contacts=[{"a": "box", "b": "floor", "friction": 0.5, "restitution": 0.0}])
    a = C.run(doc, 0.5, dt=1e-4, record_interval=0.1)
    b = C.run(doc, 0.5, dt=1e-4, record_interval=0.1)
    assert a["records"] == b["records"]
    assert a["final_state"] == b["final_state"]
    assert a["scene_sha256"] == b["scene_sha256"]


def test_run_refuses_too_many_steps_and_records():
    doc = _doc([_box()], [FLOOR])
    with pytest.raises(OperationError) as info:
        C.run(doc, 100.0, dt=1e-4, record_interval=0.01, limits={"max_steps": 1000})
    assert info.value.code == "resource_limit"
    with pytest.raises(OperationError) as info:
        C.run(doc, 1.0, dt=1e-4, record_interval=0.0001, limits={"max_records": 50})
    assert info.value.code == "resource_limit"


def test_run_honours_cancellation():
    flag = threading.Event()
    flag.set()
    with pytest.raises(OperationError) as info:
        C.run(_doc([_box()], [FLOOR]), 1.0, dt=1e-4, cancel_event=flag)
    assert info.value.code == "cancelled"


def test_static_body_is_reported_static_and_never_moves():
    anchor = _sphere("anchor", z=0.1, static=True, mass=None)
    anchor.pop("mass")
    doc = _doc([anchor, _box(z=0.25)], contacts=[{"a": "box", "b": "anchor", "friction": 0.5,
                                                  "restitution": 0.0}])
    r = C.run(doc, 1.0, dt=1e-4, record_interval=0.5)
    assert r["records"][-1]["bodies"]["anchor"]["static"] is True
    assert r["records"][-1]["bodies"]["anchor"]["position"] == [0.0, 0.0, 0.1]


def test_unsupported_pair_is_not_run():
    doc = _doc([_box("a"), _box("b", z=1.0)], contacts=[{"a": "a", "b": "b", "friction": 0.1, "restitution": 0.0}])
    with pytest.raises(OperationError) as info:
        C.run(doc, 0.1)
    assert info.value.code == "schema_error"


# ---------------------------------------------------------------- operations
def test_simulate_multibody_dispatches_v3_and_keeps_v2_output_type():
    doc = _doc([_box(z=0.201)], [FLOOR], contacts=[{"a": "box", "b": "floor", "friction": 0.5, "restitution": 0.0}])
    out = ops.call("simulate.multibody", {"scene": doc, "duration": 0.1, "dt": 1e-4, "record_interval": 0.05})
    assert out["result_schema"] == "reality.collision_run"


def test_collision_query_lists_initial_contacts_only():
    doc = _doc([_box(z=0.2 - 0.001)], [FLOOR], contacts=[{"a": "box", "b": "floor", "friction": 0.5,
                                                          "restitution": 0.0}])
    out = ops.call("collision.query", {"scene": doc})
    assert out["count"] == 4
    # four box corners touch the plane: the feature is the box vertex, as box_corners_plane labels it
    assert all(c["kind"] == "plane" and c["feature"] == "vertex" for c in out["contacts"])
    assert all(c["normal"] == [0.0, 0.0, 1.0] for c in out["contacts"])
    far = _doc([_box(z=1.0)], [FLOOR], contacts=[{"a": "box", "b": "floor", "friction": 0.5, "restitution": 0.0}])
    assert ops.call("collision.query", {"scene": far})["count"] == 0


def test_collision_validate_mesh_operation():
    good = ops.call("collision.validate_mesh", {"vertices": TWO_TRI["vertices"],
                                                "triangles": TWO_TRI["triangles"]})
    assert good["valid"] and good["bvh"]["nodes"] >= 1
    bad = ops.call("collision.validate_mesh", {"vertices": [[0, 0, 0], [1, 0, 0], [2, 0, 0]],
                                               "triangles": [[0, 1, 2]]})
    assert bad["valid"] is True and bad["degenerate_triangles"] == 1 and bad["warnings"]
    worse = ops.call("collision.validate_mesh", {"vertices": [[0, 0, 0], [1, 0, 0], [2, 0, 0]],
                                                 "triangles": [[0, 0, 1]]})
    assert worse["valid"] is False and worse["errors"]
