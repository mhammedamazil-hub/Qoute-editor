"""The operation registry: the single implementation behind the CLI, the Python API and the MCP adapter.

Each operation has a name, a description, a JSON-Schema input description and a function that takes keyword
arguments and returns a JSON-compatible dictionary. Adapters only parse input, call ``call`` and render output.
See ``AI_CONTROL_ARCHITECTURE.md`` section 2.1 and ``API_REFERENCE.md`` for the full list.
"""

from __future__ import annotations

import hashlib
import json
import os
import platform
import shutil
from dataclasses import dataclass
from typing import Any, Callable, Dict, List, Optional

from .. import __version__
from ..materials import default_database
from . import inspection as I
from . import preview as P
from . import scene as S
from . import multibody_scene as MBS
from . import collision_scene as CS
from ..collision import mesh as MSH
from ..collision import solver as SVN
from . import simulate as SIM
from .errors import OperationError
from .resources import DEFAULTS
from .schema import validate_args

_REGISTRY: Dict[str, "Operation"] = {}

SCENE = {"type": "object", "description": "a scene document (schema reality.scene v1)"}
RESULT = {"type": "object", "description": "a run result document (schema reality.run v1)"}
ID = {"type": "string", "description": "object id: letter first, then letters, digits, '_' or '-'"}
VEC3 = {"type": "array", "items": {"type": "number"}, "minItems": 3, "maxItems": 3}
LIMITS = {"type": "object", "description": "optional resource limits, see RESOURCE_LIMITS.md",
          "additionalProperties": False,
          "properties": {k: {"type": "number", "minimum": 0} for k in DEFAULTS}}


@dataclass
class Operation:
    name: str
    description: str
    input_schema: Dict[str, Any]
    func: Callable[..., Dict[str, Any]]


def _op(name: str, description: str, properties: Dict[str, Any], required: List[str]):
    schema = {"type": "object", "properties": properties, "required": required, "additionalProperties": False}

    def deco(fn):
        if name in _REGISTRY:
            raise RuntimeError(f"duplicate operation {name}")
        _REGISTRY[name] = Operation(name, description, schema, fn)
        return fn
    return deco


def list_operations() -> List[Dict[str, Any]]:
    return [{"name": op.name, "description": op.description, "input_schema": op.input_schema}
            for op in sorted(_REGISTRY.values(), key=lambda o: o.name)]


def call(name: str, args: Optional[Dict[str, Any]] = None) -> Dict[str, Any]:
    """Run one operation. Raises ``OperationError`` for every expected failure."""
    if name not in _REGISTRY:
        raise OperationError("not_found", f"unknown operation {name!r}",
                             {"available": sorted(_REGISTRY)})
    if args is None:
        args = {}
    if not isinstance(args, dict):
        raise OperationError("invalid_argument", "arguments must be a JSON object")
    op = _REGISTRY[name]
    validate_args(args, op.input_schema, name)
    result = op.func(**args)
    try:
        json.dumps(result, allow_nan=False)
    except (TypeError, ValueError) as exc:  # pragma: no cover - guards future regressions
        raise OperationError("invalid_state", f"{name} produced a non-JSON result: {exc}") from exc
    return result


# ------------------------------------------------------------------ scene
@_op("scene.create", "Create an empty scene with gravity (default standard gravity, -z).",
     {"name": {"type": "string", "minLength": 1, "maxLength": 120},
      "gravity": VEC3}, ["name"])
def _scene_create(name, gravity=None):
    return S.new_scene(name, gravity)


@_op("scene.add_sphere", "Add a solid sphere. Give exactly one of material, mass or density.",
     {"scene": SCENE, "id": ID, "radius": {"type": "number", "minimum": 0, "description": "metres"},
      "material": {"type": "string", "description": "material name, see scene.materials"},
      "mass": {"type": "number", "minimum": 0, "description": "kg"},
      "density": {"type": "number", "minimum": 0, "description": "kg/m^3"},
      "position": VEC3, "velocity": VEC3, "omega": {**VEC3, "description": "angular velocity, rad/s"}},
     ["scene", "id", "radius"])
def _scene_add_sphere(scene, id, radius, material=None, mass=None, density=None,
                      position=None, velocity=None, omega=None):
    return S.add_sphere(scene, id, radius, material=material, mass=mass, density=density,
                        position=position, velocity=velocity, omega=omega)


@_op("scene.add_plane", "Add an infinite plane {x : n . x = offset}. The free side is n . x > offset.",
     {"scene": SCENE, "id": ID, "normal": VEC3, "offset": {"type": "number"}}, ["scene", "id"])
def _scene_add_plane(scene, id, normal=None, offset=0.0):
    return S.add_plane(scene, id, normal=normal, offset=offset)


@_op("scene.set_body", "Change a body's radius, material, mass, density, position, velocity or omega.",
     {"scene": SCENE, "id": ID,
      "fields": {"type": "object", "additionalProperties": False,
                 "properties": {"radius": {"type": "number", "minimum": 0},
                                "material": {"type": "string"}, "mass": {"type": "number", "minimum": 0},
                                "density": {"type": "number", "minimum": 0},
                                "position": VEC3, "velocity": VEC3, "omega": VEC3}}},
     ["scene", "id", "fields"])
def _scene_set_body(scene, id, fields):
    return S.set_body(scene, id, fields)


@_op("scene.set_gravity", "Set the uniform gravity vector (m/s^2).",
     {"scene": SCENE, "gravity": VEC3}, ["scene", "gravity"])
def _scene_set_gravity(scene, gravity):
    return S.set_gravity(scene, gravity)


@_op("scene.set_contact", "Set friction (Coulomb) and restitution for one body-plane pair.",
     {"scene": SCENE, "body": ID, "plane": ID,
      "friction": {"type": "number", "minimum": 0, "description": "dimensionless Coulomb coefficient"},
      "restitution": {"type": "number", "minimum": 0, "maximum": 1}},
     ["scene", "body", "plane", "friction"])
def _scene_set_contact(scene, body, plane, friction, restitution=0.0):
    return S.set_contact(scene, body, plane, friction, restitution)


@_op("scene.remove", "Remove a body or plane and its contact entries.",
     {"scene": SCENE, "id": ID}, ["scene", "id"])
def _scene_remove(scene, id):
    return S.remove(scene, id)


@_op("scene.validate", "Check a scene. Returns valid, errors and warnings; never fails on bad input.",
     {"scene": SCENE}, ["scene"])
def _scene_validate(scene):
    return S.validate(scene)


@_op("scene.describe", "Numerical summary of a valid scene: masses, inertia, densities, contacts.",
     {"scene": SCENE}, ["scene"])
def _scene_describe(scene):
    return S.describe(scene)


@_op("scene.materials", "List the material names accepted by scene.add_sphere.", {}, [])
def _scene_materials():
    db = default_database()
    return {"materials": [{"name": n, "density_kg_m3": db.get(n).density} for n in db.names()]}


# -------------------------------------------------------------- simulate
@_op("simulate.run",
     "Run a scene headless from t = 0, or from a checkpoint. Returns the full run document.",
     {"scene": SCENE,
      "duration": {"type": "number", "minimum": 0, "description": "seconds"},
      "dt": {"type": "number", "minimum": 0, "description": "requested step, seconds (default 1e-4)"},
      "record_interval": {"type": "number", "minimum": 0, "description": "seconds between samples (default 0.01)"},
      "checkpoint": {"type": "object", "description": "final_state of an earlier run of the same scene"},
      "limits": LIMITS},
     ["scene", "duration"])
def _simulate_run(scene, duration, dt=1e-4, record_interval=0.01, checkpoint=None, limits=None):
    return SIM.run(scene, duration, dt=dt, record_interval=record_interval, checkpoint=checkpoint, limits=limits)


@_op("simulate.multibody",
     "Run a multi-body scene headless: schema v2 (spheres, planes; returns reality.multibody_run) or schema v3 "
     "(spheres and boxes, planes, static triangle meshes; returns reality.collision_run). Dispatch is by schema_version. "
     "Checkpoints and sweeps are not available for v2 or v3.",
     {"scene": {"type": "object", "description": "reality.scene document with schema_version 2"},
      "duration": {"type": "number", "minimum": 0, "description": "seconds"},
      "dt": {"type": "number", "minimum": 0, "description": "requested step, seconds (default 1e-4)"},
      "record_interval": {"type": "number", "minimum": 0, "description": "seconds between samples (default 0.01)"},
      "limits": LIMITS},
     ["scene", "duration"])
def _simulate_multibody(scene, duration, dt=1e-4, record_interval=0.01, limits=None):
    if isinstance(scene, dict) and scene.get("schema_version") == 3:
        return CS.run(scene, duration, dt=dt, record_interval=record_interval, limits=limits)
    return MBS.run(scene, duration, dt=dt, record_interval=record_interval, limits=limits)


@_op("collision.validate_mesh",
     "Check raw triangle-mesh data (vertices, triangles) against the mesh rules and limits. Returns errors, "
     "warnings, the number of zero-area triangles, and BVH statistics when the data is valid.",
     {"vertices": {"type": "array", "items": {"type": "array", "items": {"type": "number"}}},
      "triangles": {"type": "array", "items": {"type": "array", "items": {"type": "integer"}}}},
     ["vertices", "triangles"])
def _collision_validate_mesh(vertices, triangles):
    errors, warnings, degenerate = MSH.validate_mesh_data(vertices, triangles)
    out = {"valid": not errors, "errors": errors, "warnings": warnings, "degenerate_triangles": degenerate,
           "limits": dict(MSH.MESH_LIMITS)}
    if not errors:
        mesh = MSH.TriangleMesh("probe", tuple(tuple(float(x) for x in v) for v in vertices),
                                tuple(tuple(int(k) for k in t) for t in triangles))
        out["bvh"] = {"nodes": mesh.bvh.node_count, "leaf_size": MSH.LEAF_SIZE}
    return out


@_op("collision.query",
     "List the contacts of a schema v3 scene at its initial state (no time step): every listed pair with at least one "
     "touching contact, with normal, point, depth and feature (face, edge, vertex, sphere).",
     {"scene": {"type": "object", "description": "reality.scene document with schema_version 3"}},
     ["scene"])
def _collision_query(scene):
    CS.require_valid_v3(scene)
    bodies, specs, labels, index, meshes = CS._build(scene)
    out = []
    for si, cts in SVN.contacts_now(bodies, specs):
        for ct in cts:
            out.append({"a": labels[si]["body"], "b": labels[si]["other"], "kind": labels[si]["kind"],
                        "normal": list(ct.normal), "point": list(ct.point), "depth": ct.depth,
                        "feature": ct.feature})
    return {"contacts": out, "count": len(out), "scene_sha256": S.scene_hash(scene)}


@_op("simulate.sweep_friction",
     "Run one scene for several friction values; returns a summary per value (not full records).",
     {"scene": SCENE, "body": ID, "plane": ID,
      "friction_values": {"type": "array", "items": {"type": "number", "minimum": 0}, "minItems": 1, "maxItems": 100},
      "duration": {"type": "number", "minimum": 0},
      "dt": {"type": "number", "minimum": 0}, "record_interval": {"type": "number", "minimum": 0},
      "limits": LIMITS},
     ["scene", "body", "plane", "friction_values", "duration"])
def _simulate_sweep(scene, body, plane, friction_values, duration, dt=1e-4, record_interval=0.01, limits=None):
    return SIM.sweep_contact_parameter(scene, body, plane, friction_values, duration, dt=dt,
                                       record_interval=record_interval, limits=limits)


# --------------------------------------------------------------- inspect
@_op("inspect.body", "Supported quantities of one body at one record, plus the unsupported list with reasons.",
     {"result": RESULT, "body": ID, "index": {"type": "integer", "description": "record index; -1 is the last"}},
     ["result", "body"])
def _inspect_body(result, body, index=-1):
    return I.body_state(result, body, index)


@_op("inspect.scene", "All bodies and planes at one record, with energy and checks.",
     {"result": RESULT, "index": {"type": "integer"}}, ["result"])
def _inspect_scene(result, index=-1):
    return I.scene_state(result, index)


@_op("inspect.series", "Time series of chosen fields for one body (for example x, z, vx, speed, omega_wz, contacts).",
     {"result": RESULT, "body": ID,
      "fields": {"type": "array", "items": {"type": "string", "enum": sorted(I.SERIES_FIELDS)}}},
     ["result", "body"])
def _inspect_series(result, body, fields=None):
    return I.series(result, body, fields)


@_op("inspect.rolling_onset", "Time a sliding sphere starts to roll (derived from contact-point slip).",
     {"result": RESULT, "body": ID}, ["result", "body"])
def _inspect_rolling(result, body):
    return I.rolling_onset(result, body)


@_op("inspect.summary", "Final state, rolling onset and checks for one run.",
     {"result": RESULT}, ["result"])
def _inspect_summary(result):
    return I.summary(result)


# --------------------------------------------------------------- preview
@_op("preview.frame",
     "Render one frame to a PNG (CPU ray cast) and return the numerical description alongside it.",
     {"result": RESULT, "index": {"type": "integer"},
      "width": {"type": "integer", "minimum": 16}, "height": {"type": "integer", "minimum": 16},
      "azimuth_deg": {"type": "number"}, "elevation_deg": {"type": "number", "minimum": -89, "maximum": 89},
      "show_velocity": {"type": "boolean"}, "show_gravity": {"type": "boolean"},
      "show_contacts": {"type": "boolean"},
      "out_path": {"type": "string", "description": "file to write (must end in .png); omit to get base64 only"},
      "include_base64": {"type": "boolean"}, "limits": LIMITS},
     ["result"])
def _preview_frame(result, index=-1, width=480, height=320, azimuth_deg=-35.0, elevation_deg=20.0,
                   show_velocity=True, show_gravity=True, show_contacts=True, out_path=None,
                   include_base64=False, limits=None):
    return P.render_frame(result, index=index, width=width, height=height, azimuth_deg=azimuth_deg,
                          elevation_deg=elevation_deg, show_velocity=show_velocity, show_gravity=show_gravity,
                          show_contacts=show_contacts, out_path=out_path, include_base64=include_base64,
                          limits=limits)


# ------------------------------------------------------------ experiment
def _diff(a: Any, b: Any, path: str, out: List[Dict[str, Any]]) -> None:
    if isinstance(a, dict) and isinstance(b, dict):
        for k in sorted(set(a) | set(b)):
            if k not in a or k not in b:
                out.append({"path": f"{path}.{k}" if path else k, "a": a.get(k), "b": b.get(k)})
            else:
                _diff(a[k], b[k], f"{path}.{k}" if path else k, out)
    elif isinstance(a, list) and isinstance(b, list) and len(a) == len(b):
        for i, (x, y) in enumerate(zip(a, b)):
            _diff(x, y, f"{path}[{i}]", out)
    elif a != b:
        out.append({"path": path, "a": a, "b": b})


@_op("experiment.compare",
     "Compare two run results of one body: changed scene fields, final states, rolling onset and energy.",
     {"a": RESULT, "b": RESULT, "body": ID}, ["a", "b", "body"])
def _experiment_compare(a, b, body):
    sa = I.body_state(a, body, -1)["values"]
    sb = I.body_state(b, body, -1)["values"]
    changed_scene: List[Dict[str, Any]] = []
    _diff(a["scene"], b["scene"], "", changed_scene)
    changed_scene = [c for c in changed_scene if c["path"] not in ("name",)]

    def vec_diff(x, y):
        return [y[i] - x[i] for i in range(3)]

    onset_a = I.rolling_onset(a, body)
    onset_b = I.rolling_onset(b, body)
    onset_delta = None
    if onset_a.get("available") and onset_b.get("available"):
        onset_delta = onset_b["time_s"] - onset_a["time_s"]
    return {
        "body": body,
        "scene_changes": changed_scene,
        "time_s": {"a": sa["time_s"], "b": sb["time_s"]},
        "final_position_m": {"a": sa["position_m"], "b": sb["position_m"],
                             "delta_b_minus_a": vec_diff(sa["position_m"], sb["position_m"])},
        "final_velocity_m_s": {"a": sa["velocity_m_s"], "b": sb["velocity_m_s"],
                               "delta_b_minus_a": vec_diff(sa["velocity_m_s"], sb["velocity_m_s"])},
        "final_speed_m_s": {"a": sa["speed_m_s"], "b": sb["speed_m_s"],
                            "delta_b_minus_a": sb["speed_m_s"] - sa["speed_m_s"]},
        "rolling_onset_s": {"a": onset_a, "b": onset_b, "delta_b_minus_a": onset_delta},
        "energy_total_J": {"a": a["records"][-1]["energy_total"], "b": b["records"][-1]["energy_total"]},
        "dt_s": {"a": a["configuration"]["dt_s"], "b": b["configuration"]["dt_s"]},
        "note": "a difference in friction or restitution changes dynamics; a difference in dt changes only accuracy",
    }


# ---------------------------------------------------------------- export
@_op("export.bundle",
     "Write scene.json, run.json, report.md and (optionally) a preview PNG into one directory, with SHA-256 hashes.",
     {"out_dir": {"type": "string", "minLength": 1},
      "scene": SCENE, "result": RESULT,
      "preview_path": {"type": "string", "description": "an existing PNG to copy into the bundle"}},
     ["out_dir", "scene", "result"])
def _export_bundle(out_dir, scene, result, preview_path=None):
    S.require_valid(scene)
    os.makedirs(out_dir, exist_ok=True)
    files: Dict[str, Dict[str, Any]] = {}

    def write(name: str, text: str) -> None:
        path = os.path.join(out_dir, name)
        data = text.encode("utf-8")
        with open(path, "wb") as fh:
            fh.write(data)
        files[name] = {"sha256": hashlib.sha256(data).hexdigest(), "bytes": len(data)}

    write("scene.json", json.dumps(scene, indent=2, allow_nan=False) + "\n")
    write("run.json", json.dumps(result, indent=2, allow_nan=False) + "\n")
    body_id = result["bodies"][0]
    summ = I.summary(result)
    lines = [
        f"# Run report: {scene['name']}",
        "",
        f"- Scene SHA-256: `{result['scene_sha256']}`",
        f"- reality {result['software']['version']}, Python {result['software']['python']}",
        f"- Duration {result['configuration']['duration_s']} s, step {result['configuration']['dt_s']} s, "
        f"{result['configuration']['steps']} steps",
        f"- Contact: friction {result['configuration']['contact_friction']}, restitution "
        f"{result['configuration']['contact_restitution']}",
        f"- Final position (m): {summ['final_position_m']}",
        f"- Final velocity (m/s): {summ['final_velocity_m_s']}",
        f"- Rolling onset (derived): {summ['rolling_onset']}",
        f"- Max penetration (m): {summ['max_penetration_m']}",
        f"- Random seed: {result['random_seed']} ({result['random_seed_reason']})",
        "",
        "Numbers in this report are computed from `run.json`. The image, if present, is for visual checks only.",
        "",
    ]
    write("report.md", "\n".join(lines))
    if preview_path is not None:
        if not os.path.isfile(preview_path):
            raise OperationError("not_found", f"preview file {preview_path!r} does not exist")
        dst = os.path.join(out_dir, "preview.png")
        shutil.copyfile(preview_path, dst)
        with open(dst, "rb") as fh:
            data = fh.read()
        files["preview.png"] = {"sha256": hashlib.sha256(data).hexdigest(), "bytes": len(data)}
    return {"out_dir": out_dir, "files": files, "body": body_id}


# ------------------------------------------------------------ validation
@_op("validate.run",
     "Run validation cases from the registry. domain: 'sim' (scene pipeline), 'all', or a domain name.",
     {"domain": {"type": "string", "description": "'all', 'sim', or a registry domain such as 'rigid body'"}},
     [])
def _validate_run(domain="all"):
    from ..validation import CASES
    chosen = [c for c in CASES if domain == "all" or c.case_id.lower().startswith(domain.lower())
              or c.domain == domain]
    if not chosen:
        raise OperationError("not_found", f"no validation cases match {domain!r}")
    rows = []
    for c in chosen:
        measured, err, ok = c.evaluate()
        rows.append({
            "case_id": c.case_id, "domain": c.domain, "solver": c.solver, "description": c.description,
            "kind": c.kind, "reference": c.reference, "reference_source": c.reference_source,
            "measured": measured, "absolute_error": abs(measured - c.reference),
            "relative_error": (abs(measured - c.reference) / abs(c.reference)) if c.reference != 0 else None,
            "tolerance": c.tolerance, "passed": bool(ok),
            "model": getattr(c, "model", ""), "initial_conditions": getattr(c, "initial_conditions", ""),
            "limitations": getattr(c, "limitations", ""),
        })
    return {"domain": domain, "cases": rows, "passed": sum(r["passed"] for r in rows),
            "total": len(rows), "all_passed": all(r["passed"] for r in rows)}


# ---------------------------------------------------------------- system
@_op("system.info", "Package version, Python version, default resource limits and interface list.", {}, [])
def _system_info():
    return {
        "package": "reality",
        "version": __version__,
        "python": platform.python_version(),
        "platform": platform.machine(),
        "default_limits": dict(DEFAULTS),
        "operations": len(_REGISTRY),
        "interfaces": ["cli", "python-api", "mcp-stdio"],
        "scene_schema_version": S.SCHEMA_VERSION,
        "result_schema_version": SIM.RESULT_SCHEMA_VERSION,
    }
