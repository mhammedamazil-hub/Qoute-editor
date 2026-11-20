"""Scene schema v2 (multi-body) and the simulate.multibody operation. Schema v1 must keep working alongside it."""

import copy
import math

import pytest

from reality.control import multibody_scene as M
from reality.control import operations as OP
from reality.control import scene as S
from reality.control.errors import OperationError


def _two_body_scene(gravity=(0.0, 0.0, 0.0)):
    return {
        "schema": "reality.scene", "schema_version": 2, "name": "pair",
        "environment": {"gravity": list(gravity)},
        "bodies": [
            {"id": "a", "type": "sphere", "radius": 0.05, "mass": 2.0,
             "position": [0.0, 0.0, 0.0], "velocity": [1.0, 0.0, 0.0], "omega": [0.0, 0.0, 0.0]},
            {"id": "b", "type": "sphere", "radius": 0.05, "density": 2000.0,
             "position": [0.5, 0.0, 0.0], "velocity": [-1.0, 0.0, 0.0], "omega": [0.0, 0.0, 0.0]},
        ],
        "planes": [],
        "contacts": [{"a": "a", "b": "b", "friction": 0.0, "restitution": 1.0}],
    }


def _stack_scene():
    sc = _two_body_scene(gravity=(0.0, 0.0, -9.80665))
    sc["bodies"][0].update({"position": [0.0, 0.0, 0.05], "velocity": [0.0, 0.0, 0.0]})
    sc["bodies"][1].update({"position": [0.0, 0.0, 0.151], "velocity": [0.0, 0.0, 0.0],
                            "material": "steel"})
    del sc["bodies"][1]["density"]
    sc["planes"] = [{"id": "floor", "normal": [0.0, 0.0, 1.0], "offset": 0.0}]
    sc["contacts"] = [
        {"a": "a", "b": "floor", "friction": 0.5, "restitution": 0.0},
        {"a": "b", "b": "floor", "friction": 0.5, "restitution": 0.0},
        {"a": "a", "b": "b", "friction": 0.5, "restitution": 0.0},
    ]
    return sc


def test_valid_multibody_scene_passes_validation_and_v1_validator_dispatches():
    sc = _stack_scene()
    assert M.validate_v2(sc)["valid"]
    assert S.validate(sc)["valid"]


def test_version_one_scenes_are_unaffected():
    v1 = S.new_scene("single")
    v1 = S.add_sphere(v1, "ball", 0.05, material="steel", position=[0.0, 0.0, 1.0])
    v1 = S.add_plane(v1, "floor")
    v1 = S.set_contact(v1, "ball", "floor", 0.3, 0.5)
    assert S.validate(v1)["valid"]
    assert OP.call("simulate.run", {"scene": v1, "duration": 0.05})["result_schema"] == "reality.run"


@pytest.mark.parametrize("mutate, fragment", [
    (lambda s: s["bodies"][1].update({"id": "a"}), "duplicate id"),
    (lambda s: s["bodies"][0].update({"radius": -1.0}), "radius"),
    (lambda s: s["bodies"][0].update({"mass": 1.0, "density": 1.0}), "exactly one"),
    (lambda s: (s["bodies"][0].update({"material": "unobtainium"}), s["bodies"][0].pop("mass")), "unknown material"),
    (lambda s: s["bodies"][0].update({"type": "box"}), "type must be 'sphere'"),
    (lambda s: s["bodies"][0].update({"position": [0.0, 0.0]}), "position"),
    (lambda s: s["contacts"].append({"a": "a", "b": "ghost", "friction": 0.0, "restitution": 0.0}),
     "neither a plane nor a body"),
    (lambda s: s["contacts"].append({"a": "a", "b": "a", "friction": 0.0, "restitution": 0.0}),
     "cannot contact itself"),
    (lambda s: s["contacts"][0].update({"restitution": 1.5}), "restitution"),
    (lambda s: s["contacts"][0].update({"friction": -0.1}), "friction"),
    (lambda s: s["contacts"].append({"a": "b", "b": "a", "friction": 0.0, "restitution": 0.0}),
     "more than once"),
    (lambda s: s.update({"schema_version": 1}), "schema_version must be 2"),
])
def test_invalid_multibody_scenes_are_rejected(mutate, fragment):
    sc = copy.deepcopy(_two_body_scene())
    mutate(sc)
    result = M.validate_v2(sc)
    assert not result["valid"]
    assert any(fragment in e for e in result["errors"]), result["errors"]


def test_run_result_has_records_energy_momentum_and_checks():
    res = OP.call("simulate.multibody", {"scene": _two_body_scene(), "duration": 0.2, "dt": 1e-4,
                                         "record_interval": 0.05})
    assert res["result_schema"] == "reality.multibody_run"
    assert res["configuration"]["steps"] == 2000
    rec = res["records"][-1]
    assert set(rec["bodies"]) == {"a", "b"}
    assert len(rec["momentum_total"]) == 3
    assert res["checks"]["finite_state"] is True
    assert res["checks"]["max_penetration_m"] <= res["checks"]["penetration_tolerance_m"]
    assert "diagnostics" in res


def test_elastic_pair_run_conserves_momentum_and_energy_and_matches_1d_elastic_formula():
    res = OP.call("simulate.multibody", {"scene": _two_body_scene(), "duration": 0.5, "dt": 1e-4,
                                         "record_interval": 0.05})
    p0 = res["records"][0]["momentum_total"]
    p1 = res["records"][-1]["momentum_total"]
    assert max(abs(x - y) for x, y in zip(p0, p1)) < 1e-12
    e0 = res["records"][0]["energy_total"]
    e1 = res["records"][-1]["energy_total"]
    assert abs(e1 - e0) / e0 < 1e-9
    # masses differ (a: 2.0 kg; b: 2000 kg/m^3 * sphere volume), so compare with the 1D elastic collision formula
    ma = 2.0
    mb = 2000.0 * 4.0 / 3.0 * math.pi * 0.05 ** 3
    va, vb = 1.0, -1.0
    va_exp = ((ma - mb) * va + 2 * mb * vb) / (ma + mb)
    vb_exp = ((mb - ma) * vb + 2 * ma * va) / (ma + mb)
    assert res["records"][-1]["bodies"]["a"]["velocity"][0] == pytest.approx(va_exp, abs=1e-6)
    assert res["records"][-1]["bodies"]["b"]["velocity"][0] == pytest.approx(vb_exp, abs=1e-6)


def test_stack_rests_on_floor_with_no_penetration():
    res = OP.call("simulate.multibody", {"scene": _stack_scene(), "duration": 1.0, "dt": 1e-4,
                                         "record_interval": 0.1})
    fin = res["final_state"]["bodies"]
    assert fin["a"]["position"][2] == pytest.approx(0.05, abs=1e-5)
    assert fin["b"]["position"][2] == pytest.approx(0.15, abs=1e-5)
    assert res["checks"]["max_penetration_m"] < 1e-6


def test_run_is_deterministic_apart_from_diagnostics():
    a = OP.call("simulate.multibody", {"scene": _stack_scene(), "duration": 0.3, "dt": 1e-4})
    b = OP.call("simulate.multibody", {"scene": _stack_scene(), "duration": 0.3, "dt": 1e-4})
    a.pop("diagnostics")
    b.pop("diagnostics")
    assert a == b


def test_invalid_scene_raises_schema_error_from_operation():
    sc = copy.deepcopy(_two_body_scene())
    sc["contacts"][0]["b"] = "nobody"
    with pytest.raises(OperationError) as err:
        OP.call("simulate.multibody", {"scene": sc, "duration": 0.1})
    assert err.value.code == "schema_error"


def test_resource_limits_are_enforced():
    with pytest.raises(OperationError) as err:
        OP.call("simulate.multibody", {"scene": _two_body_scene(), "duration": 10.0, "dt": 1e-4,
                                       "limits": {"max_steps": 100}})
    assert err.value.code == "resource_limit"


def test_v1_runner_refuses_v2_scenes_with_a_pointer_to_multibody():
    with pytest.raises(OperationError) as err:
        OP.call("simulate.run", {"scene": _two_body_scene(), "duration": 0.1})
    assert err.value.code == "unsupported"
    assert "simulate.multibody" in str(err.value)


def test_operation_is_registered_and_listed():
    names = [op["name"] for op in OP.list_operations()]
    assert "simulate.multibody" in names
