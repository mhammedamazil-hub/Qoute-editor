"""Tests for the AI control layer: registry, schema checks, scene, simulation, inspection, preview, export, CLI, MCP.

Simulations here are short (0.2 to 1 s) to keep the suite fast. Physical accuracy is tested in test_validation_registry
and through the SIM-01..03 validation cases, not here.
"""

import base64
import copy
import io
import json
import os
import struct
import subprocess
import sys

import pytest

from reality.control import api, mcp
from reality.control import inspection as I
from reality.control import operations as ops
from reality.control import scene as S
from reality.control import simulate as SIM
from reality.control.errors import OperationError
from reality.control.schema import validate_args

SRC = os.path.join(os.path.dirname(__file__), "..", "src")


def sphere_plane(friction=0.1, restitution=0.0, v0=2.0):
    sc = S.new_scene("t")
    sc = S.add_sphere(sc, "ball", 0.05, material="steel", position=[0.0, 0.0, 0.05], velocity=[v0, 0.0, 0.0])
    sc = S.add_plane(sc, "floor")
    return S.set_contact(sc, "ball", "floor", friction, restitution)


# ------------------------------------------------------------------ registry
def test_registry_names_are_unique_and_documented():
    names = [o["name"] for o in ops.list_operations()]
    assert len(names) == len(set(names))
    assert len(names) == 25  # 23 before the collision milestone; + collision.query and collision.validate_mesh
    for o in ops.list_operations():
        assert o["description"]
        assert o["input_schema"]["type"] == "object"


def test_unknown_operation_is_not_found():
    with pytest.raises(OperationError) as e:
        ops.call("does.not_exist")
    assert e.value.code == "not_found"


def test_unexpected_argument_is_rejected():
    with pytest.raises(OperationError) as e:
        ops.call("scene.create", {"name": "x", "surprise": 1})
    assert e.value.code == "invalid_argument"
    assert "unknown argument" in e.value.message


def test_wrong_type_is_rejected():
    with pytest.raises(OperationError) as e:
        ops.call("scene.create", {"name": 5})
    assert e.value.code == "invalid_argument"


def test_schema_checks_numeric_bounds_and_enums():
    schema = {"type": "object", "properties": {"x": {"type": "number", "minimum": 0}}, "required": ["x"],
              "additionalProperties": False}
    validate_args({"x": 1}, schema, "op")
    with pytest.raises(OperationError):
        validate_args({"x": -1}, schema, "op")
    with pytest.raises(OperationError):
        validate_args({}, schema, "op")
    with pytest.raises(OperationError):
        validate_args({"x": True}, schema, "op")  # bool is not a number


def test_api_call_json_turns_errors_into_documents():
    out = json.loads(api.call_json("nope", "{}"))
    assert out["error"]["code"] == "not_found"
    out = json.loads(api.call_json("scene.create", "{bad"))
    assert out["error"]["code"] == "invalid_argument"
    created = json.loads(api.call_json("scene.create", json.dumps({"name": "ok"})))
    assert created["name"] == "ok"


# -------------------------------------------------------------------- scene
def test_scene_roundtrip_is_plain_json_and_hash_is_stable():
    sc = sphere_plane()
    text = json.dumps(sc, allow_nan=False)
    again = json.loads(text)
    assert S.scene_hash(again) == S.scene_hash(sc)
    assert S.validate(again)["valid"]


def test_material_mass_matches_density_times_volume():
    sc = sphere_plane()
    body = sc["bodies"][0]
    props = S.mass_properties(body)
    import math
    expected = 7850.0 * 4.0 / 3.0 * math.pi * 0.05 ** 3
    assert props["mass"] == pytest.approx(expected, rel=1e-12)


def test_add_sphere_needs_exactly_one_of_material_mass_density():
    sc = S.new_scene("t")
    with pytest.raises(OperationError):
        S.add_sphere(sc, "a", 0.1)
    with pytest.raises(OperationError):
        S.add_sphere(sc, "a", 0.1, material="steel", mass=1.0)


def test_duplicate_and_bad_ids_are_refused():
    sc = sphere_plane()
    with pytest.raises(OperationError):
        S.add_plane(sc, "ball")
    with pytest.raises(OperationError):
        S.add_sphere(sc, "1bad", 0.1, material="steel")


def test_set_contact_refuses_unknown_pairs_and_bad_values():
    sc = sphere_plane()
    with pytest.raises(OperationError) as e:
        S.set_contact(sc, "ball", "wall", 0.1)
    assert e.value.code == "not_found"
    with pytest.raises(OperationError):
        S.set_contact(sc, "ball", "floor", -0.1)
    with pytest.raises(OperationError):
        S.set_contact(sc, "ball", "floor", 0.1, restitution=1.5)


def test_validate_accepts_free_body_without_planes_and_reports_bad_input_as_errors():
    sc = S.new_scene("t")
    sc = S.add_sphere(sc, "ball", 0.05, material="steel")
    report = S.validate(sc)
    assert report == {"valid": True, "errors": [], "warnings": []}  # a lone body is a valid free-fall scene
    broken = copy.deepcopy(sc)
    broken["bodies"][0]["radius"] = -1.0
    bad = S.validate(broken)
    assert bad["valid"] is False and bad["errors"]


def test_material_list_matches_database():
    out = ops.call("scene.materials")
    assert len(out["materials"]) == 18
    assert {m["name"] for m in out["materials"]} >= {"steel", "aluminum", "water"}


# --------------------------------------------------------------- simulate
def test_run_is_deterministic_apart_from_diagnostics():
    sc = sphere_plane()
    a = SIM.run(sc, 0.3, dt=1e-4, record_interval=0.01)
    b = SIM.run(sc, 0.3, dt=1e-4, record_interval=0.01)
    a.pop("diagnostics")
    b.pop("diagnostics")
    assert a == b


def test_run_document_has_schema_and_reproducibility_fields():
    res = SIM.run(sphere_plane(), 0.1, dt=1e-4, record_interval=0.01)
    assert res["result_schema"] == "reality.run" and res["result_schema_version"] == 1
    assert res["random_seed"] is None
    assert len(res["scene_sha256"]) == 64
    assert res["configuration"]["steps"] == 1000
    assert "diagnostics" in res


def test_run_refuses_invalid_scene_and_bad_numbers():
    sc = sphere_plane()
    with pytest.raises(OperationError):
        SIM.run(sc, 0.0)
    with pytest.raises(OperationError):
        SIM.run(sc, 0.1, dt=0.0)
    two = S.add_sphere(sc, "other", 0.05, material="steel")
    with pytest.raises(OperationError) as e:
        SIM.run(two, 0.1)
    assert e.value.code == "unsupported"


def test_resource_limit_stops_before_running():
    with pytest.raises(OperationError) as e:
        SIM.run(sphere_plane(), 1.0, dt=1e-4, limits={"max_steps": 100})
    assert e.value.code == "resource_limit"
    assert e.value.details["limit"] == "max_steps"


def test_checkpoint_resume_matches_continuous_run():
    sc = sphere_plane(friction=0.2)
    full = SIM.run(sc, 0.4, dt=1e-4, record_interval=0.1)
    first = SIM.run(sc, 0.2, dt=1e-4, record_interval=0.1)
    second = SIM.run(sc, 0.2, dt=1e-4, record_interval=0.1, checkpoint=first["final_state"])
    assert second["final_state"] == full["final_state"]


def test_zero_friction_keeps_spin_and_speed():
    sc = S.new_scene("z")
    sc = S.add_sphere(sc, "ball", 0.05, material="steel", position=[0.0, 0.0, 0.05],
                      velocity=[2.0, 0.0, 0.0], omega=[0.0, 20.0, 0.0])
    sc = S.add_plane(sc, "floor")
    sc = S.set_contact(sc, "ball", "floor", 0.0, 0.0)
    res = SIM.run(sc, 0.2, dt=1e-4, record_interval=0.05)
    final = res["final_state"]["bodies"]["ball"]
    assert final["omega_body"] == pytest.approx([0.0, 20.0, 0.0], abs=1e-9)
    assert final["velocity"] == pytest.approx([2.0, 0.0, 0.0], abs=1e-9)


def test_threads_other_than_one_are_refused():
    with pytest.raises(OperationError) as e:
        SIM.run(sphere_plane(), 0.05, limits={"threads": 4})
    assert e.value.code == "unsupported"


def test_checkpoint_from_other_scene_is_refused():
    a = sphere_plane(friction=0.2)
    b = sphere_plane(friction=0.5)
    first = SIM.run(a, 0.1, dt=1e-4)
    with pytest.raises(OperationError) as e:
        SIM.run(b, 0.1, dt=1e-4, checkpoint=first["final_state"])
    assert e.value.code in ("invalid_state", "invalid_argument", "schema_error")


def test_sweep_returns_one_summary_per_value_and_no_records():
    out = SIM.sweep_contact_parameter(sphere_plane(), "ball", "floor", [0.05, 0.3], 0.2, dt=1e-4)
    assert [r["friction"] for r in out["runs"]] == [0.05, 0.3]
    assert all("records" in r["summary"] for r in out["runs"])
    assert all("records" not in r for r in out["runs"])


def test_sweep_keeps_restitution_of_base_scene():
    base = sphere_plane(friction=0.1, restitution=0.4)
    out = SIM.sweep_contact_parameter(base, "ball", "floor", [0.2], 0.05, dt=1e-4)
    assert out["runs"][0]["friction"] == 0.2


# -------------------------------------------------------------- inspection
@pytest.fixture(scope="module")
def run_doc():
    return SIM.run(sphere_plane(friction=0.1), 0.8, dt=1e-4, record_interval=0.01)


def test_body_state_reports_supported_and_unsupported_quantities(run_doc):
    st = I.body_state(run_doc, "ball", -1)
    assert st["values"]["time_s"] == pytest.approx(0.8)
    assert len(st["values"]["position_m"]) == 3
    assert st.get("unsupported") is not None


def test_series_rejects_unknown_fields(run_doc):
    with pytest.raises(OperationError):
        I.series(run_doc, "ball", ["not_a_field"])
    out = I.series(run_doc, "ball", ["x", "speed"])
    assert len(out["t"]) == len(run_doc["records"])


def test_rolling_onset_matches_analytic_slide_to_roll():
    res = SIM.run(sphere_plane(friction=0.1), 0.7, dt=1e-4, record_interval=0.01)
    onset = I.rolling_onset(res, "ball")
    assert onset["available"]
    analytic = 2.0 * 2.0 / (7.0 * 0.1 * 9.80665)
    assert onset["time_s"] == pytest.approx(analytic, rel=5e-3)


def test_unknown_body_is_not_found(run_doc):
    with pytest.raises(OperationError) as e:
        I.body_state(run_doc, "ghost", -1)
    assert e.value.code == "not_found"


# ----------------------------------------------------------------- preview
def test_preview_writes_valid_png_of_requested_size(tmp_path, run_doc):
    out = tmp_path / "f.png"
    res = ops.call("preview.frame", {"result": run_doc, "out_path": str(out), "width": 40, "height": 24})
    data = out.read_bytes()
    assert data[:8] == b"\x89PNG\r\n\x1a\n"
    w, h = struct.unpack(">II", data[16:24])
    assert (w, h) == (40, 24)
    assert res["description"]["image"]["width_px"] == 40


def test_preview_is_deterministic(run_doc):
    a = ops.call("preview.frame", {"result": run_doc, "width": 32, "height": 20, "include_base64": True})
    b = ops.call("preview.frame", {"result": run_doc, "width": 32, "height": 20, "include_base64": True})
    assert a["png_base64"] == b["png_base64"]
    assert base64.b64decode(a["png_base64"])[:4] == b"\x89PNG"


def test_preview_refuses_oversize_images(run_doc):
    with pytest.raises(OperationError) as e:
        ops.call("preview.frame", {"result": run_doc, "width": 4000, "height": 4000})
    assert e.value.code == "resource_limit"


# -------------------------------------------------------- experiment, export
def test_compare_reports_scene_change_and_rolling_onset_shift():
    a = SIM.run(sphere_plane(friction=0.1), 0.7, dt=1e-4, record_interval=0.01)
    b = SIM.run(sphere_plane(friction=0.3), 0.7, dt=1e-4, record_interval=0.01)
    out = ops.call("experiment.compare", {"a": a, "b": b, "body": "ball"})
    paths = [c["path"] for c in out["scene_changes"]]
    assert "contacts[0].friction" in paths
    assert out["rolling_onset_s"]["delta_b_minus_a"] < 0  # larger mu rolls sooner


def test_export_bundle_hashes_match_files(tmp_path, run_doc):
    import hashlib
    sc = sphere_plane(friction=0.1)
    out = ops.call("export.bundle", {"out_dir": str(tmp_path / "b"), "scene": sc, "result": run_doc})
    for name, meta in out["files"].items():
        data = (tmp_path / "b" / name).read_bytes()
        assert hashlib.sha256(data).hexdigest() == meta["sha256"]
    report = (tmp_path / "b" / "report.md").read_text()
    assert run_doc["scene_sha256"] in report


def test_validate_run_sim_domain_passes():
    out = ops.call("validate.run", {"domain": "sim"})
    assert out["total"] == 3
    assert out["all_passed"]


# ------------------------------------------------------------------- CLI
def _cli(args, cwd):
    env = dict(os.environ, PYTHONPATH=os.path.abspath(SRC))
    return subprocess.run([sys.executable, "-m", "reality.control", *args], cwd=cwd, env=env,
                          capture_output=True, text=True, timeout=120)


def test_cli_workflow_end_to_end(tmp_path):
    p = _cli(["scene", "new", "s.json", "--name", "cli"], tmp_path)
    assert p.returncode == 0, p.stderr
    assert _cli(["scene", "add-sphere", "s.json", "--id", "ball", "--radius", "0.05", "--material", "steel",
                 "--position", "0", "0", "0.05", "--velocity", "2", "0", "0"], tmp_path).returncode == 0
    assert _cli(["scene", "add-plane", "s.json", "--id", "floor"], tmp_path).returncode == 0
    assert _cli(["scene", "set-contact", "s.json", "--body", "ball", "--plane", "floor",
                 "--friction", "0.1"], tmp_path).returncode == 0
    p = _cli(["scene", "validate", "s.json"], tmp_path)
    assert p.returncode == 0 and json.loads(p.stdout)["valid"]
    p = _cli(["simulate", "run", "s.json", "--duration", "0.2", "--out", "r.json"], tmp_path)
    assert p.returncode == 0, p.stderr
    p = _cli(["inspect", "summary", "r.json"], tmp_path)
    assert p.returncode == 0 and json.loads(p.stdout)["records"] == 21
    p = _cli(["preview", "frame", "r.json", "--out", "f.png", "--width", "32", "--height", "20"], tmp_path)
    assert p.returncode == 0 and (tmp_path / "f.png").exists()


def test_cli_errors_are_json_with_exit_1(tmp_path):
    p = _cli(["scene", "validate", "missing.json"], tmp_path)
    assert p.returncode == 1
    assert json.loads(p.stdout)["error"]["code"] == "not_found"


def test_cli_usage_error_exits_2(tmp_path):
    assert _cli(["no-such-command"], tmp_path).returncode == 2


# ------------------------------------------------------------------- MCP
def test_mcp_initialize_and_tools_list():
    r = mcp.handle({"jsonrpc": "2.0", "id": 1, "method": "initialize", "params": {}})
    assert r["result"]["serverInfo"]["name"] == "reality"
    listed = mcp.handle({"jsonrpc": "2.0", "id": 2, "method": "tools/list"})["result"]["tools"]
    names = {t["name"] for t in listed}
    assert "scene_add_sphere" in names and "simulate_run" in names
    assert all("." not in n for n in names)


def test_mcp_tool_call_returns_content_and_error_flag():
    r = mcp.handle({"jsonrpc": "2.0", "id": 3, "method": "tools/call",
                    "params": {"name": "scene_create", "arguments": {"name": "m"}}})
    assert r["result"]["isError"] is False
    bad = mcp.handle({"jsonrpc": "2.0", "id": 4, "method": "tools/call",
                      "params": {"name": "scene_create", "arguments": {"name": 3}}})
    assert bad["result"]["isError"] is True


def test_mcp_protocol_errors_and_notifications():
    assert mcp.handle({"jsonrpc": "2.0", "method": "notifications/initialized"}) is None
    assert mcp.handle({"jsonrpc": "2.0", "id": 5, "method": "nope"})["error"]["code"] == -32601
    assert mcp.handle({"jsonrpc": "2.0", "id": 6, "method": "tools/call",
                       "params": {"name": "missing_tool"}})["error"]["code"] == -32602


def test_mcp_serve_handles_bad_json_line():
    stdin = io.StringIO('not json\n{"jsonrpc":"2.0","id":9,"method":"ping"}\n')
    stdout = io.StringIO()
    assert mcp.serve(stdin, stdout) == 0
    lines = [json.loads(x) for x in stdout.getvalue().splitlines()]
    assert lines[0]["error"]["code"] == -32700
    assert lines[1]["id"] == 9 and lines[1]["result"] == {}
