"""Inspection and preview on schema v2 and v3 results (the audit found KeyError 'bodies' on v2 before this fix).

Schema v1 behaviour is pinned by tests/test_control.py, which is unchanged apart from the operation count.
"""

import math

import pytest

from reality.control import collision_scene as C
from reality.control import inspection as I
from reality.control import operations as ops
from reality.control import preview as P
from reality.control.errors import OperationError
from reality.objects import Box

PNG_SIG = b"\x89PNG\r\n\x1a\n"


def _v2_stack():
    g = [0.0, 0.0, -9.80665]
    return {
        "schema": "reality.scene", "schema_version": 2, "name": "stack", "environment": {"gravity": g},
        "bodies": [
            {"id": "a", "type": "sphere", "radius": 0.05, "mass": 2.0, "position": [0.0, 0.0, 0.05],
             "velocity": [0.0, 0.0, 0.0], "omega": [0.0, 0.0, 0.0]},
            {"id": "b", "type": "sphere", "radius": 0.05, "material": "steel", "position": [0.0, 0.0, 0.151],
             "velocity": [0.0, 0.0, 0.0], "omega": [0.0, 0.0, 0.0]},
        ],
        "planes": [{"id": "floor", "normal": [0.0, 0.0, 1.0], "offset": 0.0}],
        "contacts": [{"a": "a", "b": "floor", "friction": 0.5, "restitution": 0.0},
                     {"a": "b", "b": "floor", "friction": 0.5, "restitution": 0.0},
                     {"a": "a", "b": "b", "friction": 0.5, "restitution": 0.0}],
    }


def _v3_doc(bodies, meshes=(), contacts=(), planes=()):
    return {"schema": "reality.scene", "schema_version": 3, "name": "t",
            "environment": {"gravity": [0.0, 0.0, -9.80665]}, "bodies": list(bodies), "planes": list(planes),
            "meshes": list(meshes), "contacts": list(contacts)}


BOX = {"id": "box", "type": "box", "half_extents": [0.1, 0.05, 0.2], "density": 2500.0,
       "position": [0.0, 0.0, 0.2 + 0.001], "velocity": [0.0, 0.0, 0.0], "omega": [0.0, 0.0, 0.0]}
FLOOR = {"id": "floor", "normal": [0.0, 0.0, 1.0], "offset": 0.0}


# ---------------------------------------------------------------- schema v2
@pytest.fixture(scope="module")
def v2_result():
    return ops.call("simulate.multibody", {"scene": _v2_stack(), "duration": 0.2, "dt": 1e-4,
                                           "record_interval": 0.02})


def test_v2_summary_works_and_names_the_first_body(v2_result):
    s = ops.call("inspect.summary", {"result": v2_result})
    assert s["records"] == len(v2_result["records"])
    assert s["rolling_onset"]["available"] is False
    assert "single-sphere" in s["rolling_onset"]["reason"]


def test_v2_body_inspection_reads_each_body_by_id(v2_result):
    a = ops.call("inspect.body", {"result": v2_result, "body": "a"})
    b = ops.call("inspect.body", {"result": v2_result, "body": "b"})
    assert a["values"]["mass_kg"] == pytest.approx(2.0, rel=1e-14)
    assert b["values"]["density_source"] == "material:steel"
    assert b["values"]["mass_kg"] == pytest.approx(7850.0 * 4.0 / 3.0 * math.pi * 0.05 ** 3, rel=1e-12)
    assert a["values"]["gravity_force_N"][2] == pytest.approx(2.0 * -9.80665, rel=1e-14)


def test_v2_body_on_a_plane_has_contact_point_velocity_and_body_contacts_are_listed(v2_result):
    rec = ops.call("inspect.body", {"result": v2_result, "body": "a", "index": -1})["values"]
    # the record keeps the raw entries: 'plane:<id>' for planes and 'body:<id>' for body-body contacts
    assert "plane:floor" in rec["contact_planes"]
    assert "body:b" in rec["contact_planes"]
    assert rec["in_contact"] is True
    assert rec["contact_point_velocity_m_s"] is not None


def test_v2_series_and_scene_accept_every_body(v2_result):
    ser = ops.call("inspect.series", {"result": v2_result, "body": "b", "fields": ["z", "contacts"]})
    assert len(ser["z"]) == len(v2_result["records"])
    scene = ops.call("inspect.scene", {"result": v2_result})
    assert sorted(scene["bodies"]) == ["a", "b"]


def test_v2_series_refuses_unknown_body(v2_result):
    with pytest.raises(OperationError) as info:
        ops.call("inspect.series", {"result": v2_result, "body": "zzz"})
    assert info.value.code == "not_found"


def test_v2_preview_draws_both_spheres_and_is_a_png(v2_result):
    out = ops.call("preview.frame", {"result": v2_result, "width": 64, "height": 48})
    assert out["mime_type"] == "image/png"
    import base64
    assert base64.b64decode(out["png_base64"])[:8] == PNG_SIG
    d = out["description"]
    assert sorted(d["projected"]) == ["a", "b"]
    assert d["overlay_body"] == "a"
    for bid in ("a", "b"):
        px, py = d["projected"][bid]["centre_px"]
        assert 0 <= px <= 64 and 0 <= py <= 48
        assert d["projected"][bid]["radius_px"] > 0


def test_v2_preview_is_deterministic(v2_result):
    a = ops.call("preview.frame", {"result": v2_result, "width": 48, "height": 32})
    b = ops.call("preview.frame", {"result": v2_result, "width": 48, "height": 32})
    assert a == b


# ---------------------------------------------------------------- schema v3: boxes and statics
def test_box_mass_and_inertia_match_the_validated_box_class():
    props = I.body_properties(BOX)
    ref = Box(size=(0.2, 0.1, 0.4))
    assert props["volume"] == pytest.approx(ref.volume(), rel=1e-14)
    assert props["mass"] == pytest.approx(2500.0 * ref.volume(), rel=1e-14)
    k = ref.principal_inertia_per_mass()
    for got, want in zip(props["inertia_principal_body"], k):
        assert got == pytest.approx(props["mass"] * want, rel=1e-12)


def test_v3_box_inspection_and_summary_work_and_preview_refuses_boxes():
    doc = _v3_doc([BOX], planes=[FLOOR], contacts=[{"a": "box", "b": "floor", "friction": 0.5, "restitution": 0.0}])
    res = ops.call("simulate.multibody", {"scene": doc, "duration": 0.1, "dt": 1e-4, "record_interval": 0.02})
    body = ops.call("inspect.body", {"result": res, "body": "box"})
    assert body["values"]["density_source"] == "density"
    assert body["values"]["in_contact"] is True
    s = ops.call("inspect.summary", {"result": res})
    assert s["rolling_onset"]["available"] is False
    with pytest.raises(OperationError) as info:
        ops.call("preview.frame", {"result": res})
    assert info.value.code == "unsupported" and "box" in info.value.message


def test_v3_static_sphere_has_no_mass_and_no_gravity_force():
    anchor = {"id": "anchor", "type": "sphere", "radius": 0.1, "static": True, "position": [0.0, 0.0, 0.1],
              "velocity": [0.0, 0.0, 0.0], "omega": [0.0, 0.0, 0.0]}
    doc = _v3_doc([anchor, {"id": "ball", "type": "sphere", "radius": 0.05, "mass": 1.0,
                            "position": [0.0, 0.0, 0.4], "velocity": [0.0, 0.0, 0.0], "omega": [0.0, 0.0, 0.0]}])
    res = ops.call("simulate.multibody", {"scene": doc, "duration": 0.05, "dt": 1e-4, "record_interval": 0.01})
    a = ops.call("inspect.body", {"result": res, "body": "anchor"})["values"]
    assert a["mass_kg"] is None and a["gravity_force_N"] is None
    assert a["density_source"] == "static: no mass"
    ball = ops.call("inspect.body", {"result": res, "body": "ball"})["values"]
    assert ball["gravity_force_N"][2] == pytest.approx(-9.80665, rel=1e-12)


def test_v3_mesh_scene_preview_is_refused_explicitly():
    mesh = {"id": "m", "vertices": [[-1, -1, 0], [1, -1, 0], [1, 1, 0], [-1, 1, 0]],
            "triangles": [[0, 1, 2], [0, 2, 3]]}
    ball = {"id": "ball", "type": "sphere", "radius": 0.1, "mass": 1.0, "position": [0.0, 0.0, 0.5],
            "velocity": [0.0, 0.0, 0.0], "omega": [0.0, 0.0, 0.0]}
    doc = _v3_doc([ball], meshes=[mesh], contacts=[{"a": "ball", "b": "m", "friction": 0.1, "restitution": 0.0}])
    res = ops.call("simulate.multibody", {"scene": doc, "duration": 0.05, "dt": 1e-4, "record_interval": 0.01})
    with pytest.raises(OperationError) as info:
        ops.call("preview.frame", {"result": res})
    assert info.value.code == "unsupported" and "mesh" in info.value.message


def test_preview_refuses_more_spheres_than_the_design_limit():
    bodies = [{"id": f"s{i}", "type": "sphere", "radius": 0.01, "mass": 1.0, "position": [i * 0.03, 0.0, 0.5],
               "velocity": [0.0, 0.0, 0.0], "omega": [0.0, 0.0, 0.0]} for i in range(P.MAX_RENDER_SPHERES + 1)]
    res = C.run(_v3_doc(bodies), 0.001, dt=1e-4, record_interval=0.001)
    with pytest.raises(OperationError) as info:
        P.render_frame(res, width=32, height=32)
    assert info.value.code == "resource_limit"


def test_v3_rolling_onset_is_refused_as_not_single_body():
    doc = _v3_doc([BOX], planes=[FLOOR], contacts=[{"a": "box", "b": "floor", "friction": 0.5, "restitution": 0.0}])
    res = C.run(doc, 0.05, dt=1e-4, record_interval=0.01)
    out = I.rolling_onset(res, "box")
    assert out["available"] is False and "single-sphere" in out["reason"]
