"""Scene schema v2: several sphere bodies, planes and per-contact parameters (PROJECT REALITY, Phase 3 extension).

Schema v1 (``scene.py``, ``simulate.py``) holds one body and is unchanged. Schema v2 is the same ``reality.scene``
document with ``"schema_version": 2`` and these lists:

- ``bodies``: sphere bodies, each with ``id``, ``type`` = "sphere", ``radius`` and exactly one of ``material``,
  ``mass`` or ``density``, plus ``position``, ``velocity``, ``omega`` (body frame) and an optional unit ``quaternion``
  (w, x, y, z; default identity). Mass properties come from
  ``scene.mass_properties``, the same derivation as v1.
- ``planes``: ``id``, ``normal`` (non-zero), ``offset`` (metres).
- ``contacts``: ``a`` (a body id) and ``b`` (a plane id or another body id), with ``friction`` >= 0 and
  ``restitution`` in [0, 1]. Each contact carries its own coefficients. A contact that is not listed does not
  collide.

The stepper is ``multibody.step_bodies`` (sequential impulses). Result documents are ``reality.multibody_run``
version 1. They have the same parts as v1 run documents: the scene and its hash, the numerical configuration, the
limits, checks, records, a final state and a ``diagnostics`` block. Only ``diagnostics`` is non-reproducible.

Not supported in v2 (rejected or absent, not silently ignored): checkpoints, parameter sweeps, non-sphere shapes,
mesh bodies.
"""

from __future__ import annotations

import math
import platform
import time
from typing import Any, Dict, List

from .. import __version__
from .. import contact as CT
from .. import multibody as MB
from .. import rigidbody as RB
from ..materials import default_database
from . import scene as S
from .errors import OperationError
from .resources import Deadline, ResourceLimits, peak_memory_mb
from .simulate import CHECK_EVERY_STEPS, PENETRATION_TOLERANCE_M, _check_number, _finite_list

SCHEMA = S.SCHEMA
SCHEMA_VERSION = 2
RESULT_SCHEMA = "reality.multibody_run"
RESULT_SCHEMA_VERSION = 1


def _is_num(v: Any) -> bool:
    return isinstance(v, (int, float)) and not isinstance(v, bool) and math.isfinite(float(v))


def _vec3_ok(v: Any) -> bool:
    return isinstance(v, list) and len(v) == 3 and all(_is_num(x) for x in v)


def validate_v2(scene: Any) -> Dict[str, Any]:
    """Return {"valid", "errors", "warnings"} for a schema v2 scene. Never raises."""
    errors: List[str] = []
    if not isinstance(scene, dict):
        return {"valid": False, "errors": ["scene must be a JSON object"], "warnings": []}
    if scene.get("schema") != SCHEMA:
        errors.append(f"schema must be {SCHEMA!r}")
    if scene.get("schema_version") != SCHEMA_VERSION:
        errors.append(f"schema_version must be {SCHEMA_VERSION} for multi-body scenes")
    if isinstance(scene.get("meshes"), list) and scene["meshes"]:
        # refused here so the sphere solver never ignores meshes; the collision solver validates them
        errors.append("meshes are not handled by the sphere solver; a schema v2 scene with meshes runs through "
                      "simulate.multibody on the collision solver (collision_scene)")
    if not isinstance(scene.get("name"), str) or not scene.get("name"):
        errors.append("name must be a non-empty string")
    env = scene.get("environment")
    if not isinstance(env, dict) or not _vec3_ok(env.get("gravity")):
        errors.append("environment.gravity must be three finite numbers")
    bodies = scene.get("bodies")
    planes = scene.get("planes", [])
    contacts = scene.get("contacts", [])
    if not isinstance(bodies, list) or not bodies:
        errors.append("bodies must be a non-empty list")
        bodies = []
    if not isinstance(planes, list) or not isinstance(contacts, list):
        errors.append("planes and contacts must be lists")
        planes, contacts = [], []

    seen: set = set()
    body_ids: set = set()
    for i, b in enumerate(bodies):
        where = f"bodies[{i}]"
        if not isinstance(b, dict):
            errors.append(f"{where} must be an object")
            continue
        bid = b.get("id")
        if not isinstance(bid, str) or not S._ID_RE.match(bid):
            errors.append(f"{where}: id must be a letter-first identifier of at most 64 characters")
            continue
        if bid in seen:
            errors.append(f"{where}: duplicate id {bid!r}")
        seen.add(bid)
        body_ids.add(bid)
        if b.get("type") != "sphere":
            errors.append(f"{where} ({bid!r}): type must be 'sphere'")
        if not (_is_num(b.get("radius")) and b["radius"] > 0):
            errors.append(f"{where} ({bid!r}): radius must be a finite number > 0")
        given = [k for k in ("material", "mass", "density") if b.get(k) is not None]
        if len(given) != 1:
            errors.append(f"{where} ({bid!r}): give exactly one of material, mass or density")
        elif given[0] == "material":
            if not isinstance(b["material"], str) or b["material"].lower() not in default_database():
                errors.append(f"{where} ({bid!r}): unknown material {b.get('material')!r}")
        elif not (_is_num(b[given[0]]) and b[given[0]] > 0):
            errors.append(f"{where} ({bid!r}): {given[0]} must be a finite number > 0")
        for key in ("position", "velocity", "omega"):
            if not _vec3_ok(b.get(key)):
                errors.append(f"{where} ({bid!r}): {key} must be three finite numbers")
        q = b.get("quaternion")
        if q is not None:
            if not (isinstance(q, list) and len(q) == 4 and all(_is_num(x) for x in q)):
                errors.append(f"{where} ({bid!r}): quaternion must be four finite numbers (w, x, y, z)")
            elif abs(math.sqrt(sum(x * x for x in q)) - 1.0) > 1e-9:
                errors.append(f"{where} ({bid!r}): quaternion must be a unit quaternion")

    plane_ids: set = set()
    for i, p in enumerate(planes):
        where = f"planes[{i}]"
        if not isinstance(p, dict):
            errors.append(f"{where} must be an object")
            continue
        pid = p.get("id")
        if not isinstance(pid, str) or not S._ID_RE.match(pid):
            errors.append(f"{where}: id must be a letter-first identifier of at most 64 characters")
            continue
        if pid in seen:
            errors.append(f"{where}: id {pid!r} is already used")
        seen.add(pid)
        plane_ids.add(pid)
        n = p.get("normal")
        if not _vec3_ok(n) or sum(x * x for x in n) == 0.0:
            errors.append(f"{where} ({pid!r}): normal must be three finite numbers, not all zero")
        if not _is_num(p.get("offset")):
            errors.append(f"{where} ({pid!r}): offset must be a finite number")

    used: set = set()
    for i, c in enumerate(contacts):
        where = f"contacts[{i}]"
        if not isinstance(c, dict):
            errors.append(f"{where} must be an object")
            continue
        a, b = c.get("a"), c.get("b")
        if a not in body_ids:
            errors.append(f"{where}: a={a!r} is not a body id")
            continue
        if b in plane_ids:
            key = ("plane", a, b)
        elif b in body_ids:
            if a == b:
                errors.append(f"{where}: a body cannot contact itself")
                continue
            key = ("pair",) + tuple(sorted((a, b)))
        else:
            errors.append(f"{where}: b={b!r} is neither a plane nor a body id")
            continue
        if key in used:
            errors.append(f"{where}: contact {key[1:]!r} is listed more than once")
        used.add(key)
        if not (_is_num(c.get("friction")) and c["friction"] >= 0):
            errors.append(f"{where}: friction must be a finite number >= 0")
        if not (_is_num(c.get("restitution")) and 0.0 <= c["restitution"] <= 1.0):
            errors.append(f"{where}: restitution must be a number in [0, 1]")
    return {"valid": not errors, "errors": errors, "warnings": []}


def require_valid_v2(scene: Any) -> None:
    result = validate_v2(scene)
    if not result["valid"]:
        raise OperationError("schema_error", "scene is not a valid schema v2 scene", {"errors": result["errors"]})


def _build(scene: Dict[str, Any]):
    body_list = scene["bodies"]
    index = {b["id"]: i for i, b in enumerate(body_list)}
    plane_list = scene.get("planes", [])
    plane_ids = [p["id"] for p in plane_list]
    pindex = {pid: i for i, pid in enumerate(plane_ids)}
    bodies: List[MB.Sphere] = []
    props: List[Dict[str, Any]] = []
    for b in body_list:
        pr = S.mass_properties(b)
        props.append(pr)
        q = tuple(float(x) for x in b["quaternion"]) if b.get("quaternion") is not None else (1.0, 0.0, 0.0, 0.0)
        bodies.append(MB.Sphere(b["id"], pr["mass"], float(b["radius"]), tuple(b["position"]),
                                tuple(b["velocity"]), quaternion=q, omega_body=tuple(b["omega"])))
    planes = [CT.Plane(tuple(p["normal"]), float(p["offset"])) for p in plane_list]
    contacts: List[Any] = []
    labels: List[Dict[str, str]] = []
    for c in scene.get("contacts", []):
        f, e = float(c["friction"]), float(c["restitution"])
        if c["b"] in pindex:
            contacts.append(MB.PlaneContact(index[c["a"]], pindex[c["b"]], f, e))
            labels.append({"kind": "plane", "a": c["a"], "b": c["b"]})
        else:
            contacts.append(MB.PairContact(index[c["a"]], index[c["b"]], f, e))
            labels.append({"kind": "pair", "a": c["a"], "b": c["b"]})
    return bodies, props, planes, contacts, labels, index


def run(scene: Dict[str, Any], duration: float, dt: float = 1e-4, record_interval: float = 0.01,
        limits: Any = None, cancel_event: Any = None) -> Dict[str, Any]:
    """Run a schema v2 scene for ``duration`` seconds from t = 0. Same step convention as v1 (``dt_eff``)."""
    lim = ResourceLimits.from_dict(limits)
    require_valid_v2(scene)
    duration = _check_number(duration, "duration", positive=True)
    dt = _check_number(dt, "dt", positive=True)
    record_interval = _check_number(record_interval, "record_interval", positive=True)

    steps = max(1, int(round(duration / dt)))
    dt_eff = duration / steps
    rec_every = max(1, int(round(record_interval / dt_eff)))
    if steps > lim.max_steps:
        raise OperationError("resource_limit",
                             f"{steps} steps exceed max_steps={lim.max_steps}; increase dt or lower duration",
                             {"limit": "max_steps", "value": lim.max_steps, "requested": steps})
    n_records = steps // rec_every + 2
    if n_records > lim.max_records:
        raise OperationError("resource_limit",
                             f"{n_records} records exceed max_records={lim.max_records}; increase record_interval",
                             {"limit": "max_records", "value": lim.max_records, "requested": n_records})

    bodies, props, planes, contacts, labels, index = _build(scene)
    gravity = tuple(float(x) for x in scene["environment"]["gravity"])
    body_ids = [b.name for b in bodies]
    plane_names = [p["id"] for p in scene.get("planes", [])]
    radii = [float(b["radius"]) for b in scene["bodies"]]
    scene_sha = S.scene_hash(scene)
    deadline = Deadline(lim)
    wall_start = time.monotonic()

    def contact_names(info: MB.StepInfo) -> Dict[str, List[str]]:
        out: Dict[str, List[str]] = {bid: [] for bid in body_ids}
        for body_i, plane_i in info.touching_planes:
            out[body_ids[body_i]].append(f"plane:{plane_names[plane_i]}")
        for a_i, b_i in info.touching_pairs:
            out[body_ids[a_i]].append(f"body:{body_ids[b_i]}")
            out[body_ids[b_i]].append(f"body:{body_ids[a_i]}")
        return out

    def sample(k: int, touching: Dict[str, List[str]]) -> Dict[str, Any]:
        ke_total = 0.0
        pe_total = 0.0
        body_rec: Dict[str, Any] = {}
        for i, s in enumerate(bodies):
            m = s.mass
            ke_t = 0.5 * m * RB.dot(s.velocity, s.velocity)
            ke_r = 0.5 * s.inertia * RB.dot(s.omega_body, s.omega_body)
            pe = -m * RB.dot(gravity, s.position)
            ke_total += ke_t + ke_r
            pe_total += pe
            body_rec[s.name] = {
                "position": list(s.position),
                "velocity": list(s.velocity),
                "quaternion": list(s.quaternion),
                "omega_body": list(s.omega_body),
                "omega_world": list(s.omega_world()),
                "kinetic_energy_translational": ke_t,
                "kinetic_energy_rotational": ke_r,
                "potential_energy_gravity": pe,
                "contacts": touching.get(s.name, []),
            }
        p = MB.total_momentum(bodies)
        return {"t": k * dt_eff, "bodies": body_rec, "momentum_total": list(p),
                "energy_total": ke_total + pe_total}

    records: List[Dict[str, Any]] = [sample(0, {})]
    max_penetration = 0.0
    max_quat_error = 0.0
    for k in range(1, steps + 1):
        if cancel_event is not None and cancel_event.is_set():
            raise OperationError("cancelled", f"run cancelled at step {k} of {steps}",
                                 {"step": k, "time": (k - 1) * dt_eff})
        if k % CHECK_EVERY_STEPS == 0:
            deadline.check(f"at step {k}")
        info = MB.step_bodies(bodies, planes, contacts, dt_eff, gravity)
        for s in bodies:
            if not (_finite_list(s.position) and _finite_list(s.velocity) and _finite_list(s.omega_body)
                    and _finite_list(s.quaternion)):
                raise OperationError("invalid_state", f"non-finite state at step {k}, t = {k * dt_eff:.6g} s",
                                     {"step": k, "time": k * dt_eff})
            max_quat_error = max(max_quat_error, abs(RB.norm(s.quaternion) - 1.0))
        for c in labels:
            if c["kind"] == "plane":
                pl = planes[plane_names.index(c["b"])]
                gap = RB.dot(pl.normal, bodies[index[c["a"]]].position) - pl.offset - radii[index[c["a"]]]
                if gap < 0.0:
                    max_penetration = max(max_penetration, -gap)
            else:
                ia, ib = index[c["a"]], index[c["b"]]
                d = RB.norm(RB.sub(bodies[ib].position, bodies[ia].position))
                gap = d - (radii[ia] + radii[ib])
                if gap < 0.0:
                    max_penetration = max(max_penetration, -gap)
        if max_penetration > PENETRATION_TOLERANCE_M:
            raise OperationError("invalid_state",
                                 f"penetration {max_penetration:.3e} m exceeds {PENETRATION_TOLERANCE_M} m at step {k}",
                                 {"step": k, "max_penetration_m": max_penetration,
                                  "tolerance_m": PENETRATION_TOLERANCE_M})
        if k % rec_every == 0 or k == steps:
            records.append(sample(k, contact_names(info)))

    t_end = steps * dt_eff
    final_state = {
        "time": t_end,
        "scene_sha256": scene_sha,
        "bodies": {s.name: {"position": list(s.position), "velocity": list(s.velocity),
                            "quaternion": list(s.quaternion), "omega_body": list(s.omega_body)}
                   for s in bodies},
    }
    wall = time.monotonic() - wall_start
    return {
        "result_schema": RESULT_SCHEMA,
        "result_schema_version": RESULT_SCHEMA_VERSION,
        "scene": scene,
        "scene_sha256": scene_sha,
        "configuration": {
            "duration_s": duration,
            "dt_requested_s": dt,
            "dt_s": dt_eff,
            "steps": steps,
            "record_interval_requested_s": record_interval,
            "record_interval_s": rec_every * dt_eff,
            "integrator": "multibody.step_bodies: sequential impulses, fixed step, 8 iterations",
            "bodies": len(bodies),
            "contacts": len(contacts),
        },
        "software": {"package": "reality", "version": __version__, "python": platform.python_version()},
        "random_seed": None,
        "random_seed_reason": "the kernel has no stochastic component",
        "limits": lim.to_dict(),
        "checks": {
            "finite_state": True,
            "max_penetration_m": max_penetration,
            "penetration_tolerance_m": PENETRATION_TOLERANCE_M,
            "max_quaternion_norm_error": max_quat_error,
        },
        "records": records,
        "final_state": final_state,
        "diagnostics": {  # not reproducible: wall-clock and memory are measured, not computed
            "wall_seconds": round(wall, 4),
            "steps_per_second": round(steps / wall, 1) if wall > 0 else None,
            "peak_memory_mb": peak_memory_mb(),
        },
    }
