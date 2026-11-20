"""Scene schema v3: sphere and box bodies, planes, static triangle meshes, and explicit contact pairs.

Versions 1 and 2 keep their behaviour (``scene.py``, ``multibody_scene.py``). A v3 document has ``"schema_version": 3``.
A v2 document with a non-empty ``meshes`` list is also validated and run here, under the v2 rules (spheres only, no
``static`` flag); see ``is_v2_with_meshes``.
Lists:

- ``bodies``: ``{id, type: "sphere"|"box", ...}``.
  sphere: ``radius``. box: ``half_extents`` [hx, hy, hz] in metres (half the edge lengths, along body axes).
  Both: exactly one of ``material``, ``mass``, ``density`` (box volume = 8 hx hy hz), ``position``, ``velocity``,
  ``omega`` (body frame), optional unit ``quaternion`` (w, x, y, z; default identity), optional ``static`` (bool).
  A static body never moves and must have zero velocity and omega.
- ``planes``: ``{id, normal, offset}`` (infinite).
- ``meshes``: ``{id, position, quaternion?, vertices: [[x,y,z]...], triangles: [[i,j,k]...]}``. Static only.
- ``contacts``: ``{a, b, friction, restitution}``. ``a`` is a body. ``b`` is a body, a plane or a mesh. A pair that is
  not listed does not collide.

Supported pairs: sphere-sphere, sphere-box, sphere-plane, box-plane, sphere-mesh. Pairs with two boxes
(box-box) and with a box and a mesh (box-mesh) are rejected with ``unsupported``; they are not silently ignored.
Two static items cannot form a contact.

Results: ``reality.collision_run`` version 1 (records, checks, final state, diagnostics). Only ``diagnostics`` is
not reproducible.
"""

from __future__ import annotations

import math
import platform
import time
from typing import Any, Dict, List, Optional, Tuple

from .. import __version__
from ..collision import mesh as MSH
from ..collision import solver as SV
from ..contact import Plane
from ..materials import default_database
from ..rigidbody import dot, quat_norm
from . import scene as S
from .errors import OperationError
from .resources import Deadline, ResourceLimits, peak_memory_mb
from .simulate import CHECK_EVERY_STEPS, PENETRATION_TOLERANCE_M, _check_number, _finite_list

SCHEMA = S.SCHEMA
SCHEMA_VERSION = 3
RESULT_SCHEMA = "reality.collision_run"
RESULT_SCHEMA_VERSION = 1

LIMITS = {
    "max_bodies": 256,
    "max_planes": 64,
    "max_contacts": 2048,
    **MSH.MESH_LIMITS,
}

_UNSUPPORTED = {
    ("box", "mesh"): "box-mesh contacts are not implemented in this version",
}


def _is_num(v: Any) -> bool:
    return isinstance(v, (int, float)) and not isinstance(v, bool) and math.isfinite(float(v))


def _vec3_ok(v: Any) -> bool:
    return isinstance(v, list) and len(v) == 3 and all(_is_num(x) for x in v)


def _quat_ok(q: Any) -> bool:
    return isinstance(q, list) and len(q) == 4 and all(_is_num(x) for x in q) \
        and abs(math.sqrt(sum(float(x) * float(x) for x in q)) - 1.0) <= 1e-9


def is_v2_with_meshes(scene: Any) -> bool:
    """True for a schema v2 document that lists at least one mesh.

    Such a document runs on this module's collision solver (not on the sphere solver of ``multibody_scene``), under
    the v2 rules: sphere bodies only, no ``static`` flag. Documents without meshes keep the v2 sphere path unchanged.
    """
    return (isinstance(scene, dict) and scene.get("schema_version") == 2
            and isinstance(scene.get("meshes"), list) and len(scene["meshes"]) > 0)


def validate_v3(scene: Any) -> Dict[str, Any]:
    """Return {"valid", "errors", "warnings", "counts"} for a v3 scene, or a v2 scene with meshes. Never raises."""
    errors: List[str] = []
    warnings: List[str] = []
    if not isinstance(scene, dict):
        return {"valid": False, "errors": ["scene must be a JSON object"], "warnings": [], "counts": {}}
    if scene.get("schema") != SCHEMA:
        errors.append(f"schema must be {SCHEMA!r}")
    v2_mesh = is_v2_with_meshes(scene)
    if scene.get("schema_version") != SCHEMA_VERSION and not v2_mesh:
        errors.append(f"schema_version must be {SCHEMA_VERSION} for collision scenes "
                      f"(or 2 when the scene lists meshes)")
    if not isinstance(scene.get("name"), str) or not scene.get("name"):
        errors.append("name must be a non-empty string")
    env = scene.get("environment")
    if not isinstance(env, dict) or not _vec3_ok(env.get("gravity")):
        errors.append("environment.gravity must be three finite numbers")

    bodies = scene.get("bodies") if isinstance(scene.get("bodies"), list) else None
    planes = scene.get("planes", [])
    meshes = scene.get("meshes", [])
    contacts = scene.get("contacts", [])
    if bodies is None or not bodies:
        errors.append("bodies must be a non-empty list")
        bodies = []
    for name, val in (("planes", planes), ("meshes", meshes), ("contacts", contacts)):
        if not isinstance(val, list):
            errors.append(f"{name} must be a list")
    planes = planes if isinstance(planes, list) else []
    meshes = meshes if isinstance(meshes, list) else []
    contacts = contacts if isinstance(contacts, list) else []
    if len(bodies) > LIMITS["max_bodies"]:
        errors.append(f"{len(bodies)} bodies exceed the limit {LIMITS['max_bodies']}")
    if len(planes) > LIMITS["max_planes"]:
        errors.append(f"{len(planes)} planes exceed the limit {LIMITS['max_planes']}")
    if len(meshes) > LIMITS["max_meshes"]:
        errors.append(f"{len(meshes)} meshes exceed the limit {LIMITS['max_meshes']}")
    if len(contacts) > LIMITS["max_contacts"]:
        errors.append(f"{len(contacts)} contacts exceed the limit {LIMITS['max_contacts']}")

    seen: set = set()
    kinds: Dict[str, str] = {}      # body id -> type
    static: Dict[str, bool] = {}
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
        kind = b.get("type")
        if kind not in ("sphere", "box"):
            errors.append(f"{where} ({bid!r}): type must be 'sphere' or 'box'")
            continue
        kinds[bid] = kind
        if v2_mesh and kind != "sphere":
            errors.append(f"{where} ({bid!r}): a schema v2 scene with meshes allows sphere bodies only; "
                          f"use schema_version 3 for boxes")
        if v2_mesh and "static" in b:
            errors.append(f"{where} ({bid!r}): schema v2 has no static flag; use schema_version 3")
        if kind == "sphere":
            if not (_is_num(b.get("radius")) and b["radius"] > 0):
                errors.append(f"{where} ({bid!r}): radius must be a finite number > 0")
        else:
            he = b.get("half_extents")
            if not (_vec3_ok(he) and all(x > 0 for x in he)):
                errors.append(f"{where} ({bid!r}): half_extents must be three finite numbers > 0")
        given = [k for k in ("material", "mass", "density") if b.get(k) is not None]
        is_static = b.get("static", False)
        if not isinstance(is_static, bool):
            errors.append(f"{where} ({bid!r}): static must be true or false")
            is_static = False
        static[bid] = is_static
        if not is_static:
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
        if is_static and (_vec3_ok(b.get("velocity")) and any(x != 0 for x in b["velocity"])
                          or _vec3_ok(b.get("omega")) and any(x != 0 for x in b["omega"])):
            errors.append(f"{where} ({bid!r}): a static body must have zero velocity and omega")
        if b.get("quaternion") is not None and not _quat_ok(b.get("quaternion")):
            errors.append(f"{where} ({bid!r}): quaternion must be four finite numbers, unit length")

    plane_ids: set = set()
    for i, p in enumerate(planes):
        where = f"planes[{i}]"
        if not isinstance(p, dict) or not isinstance(p.get("id"), str) or not S._ID_RE.match(p.get("id", "")):
            errors.append(f"{where}: id must be a letter-first identifier of at most 64 characters")
            continue
        pid = p["id"]
        if pid in seen:
            errors.append(f"{where}: duplicate id {pid!r}")
        seen.add(pid)
        plane_ids.add(pid)
        n = p.get("normal")
        if not _vec3_ok(n) or sum(x * x for x in n) == 0.0:
            errors.append(f"{where} ({pid!r}): normal must be three finite numbers, not all zero")
        if not _is_num(p.get("offset")):
            errors.append(f"{where} ({pid!r}): offset must be a finite number")

    mesh_ids: set = set()
    total_tris = 0
    for i, m in enumerate(meshes):
        where = f"meshes[{i}]"
        if not isinstance(m, dict) or not isinstance(m.get("id"), str) or not S._ID_RE.match(m.get("id", "")):
            errors.append(f"{where}: id must be a letter-first identifier of at most 64 characters")
            continue
        mid = m["id"]
        if mid in seen:
            errors.append(f"{where}: duplicate id {mid!r}")
        seen.add(mid)
        mesh_ids.add(mid)
        if not _vec3_ok(m.get("position", [0.0, 0.0, 0.0])):
            errors.append(f"{where} ({mid!r}): position must be three finite numbers")
        if m.get("quaternion") is not None and not _quat_ok(m.get("quaternion")):
            errors.append(f"{where} ({mid!r}): quaternion must be four finite numbers, unit length")
        me, mw, _ = MSH.validate_mesh_data(m.get("vertices"), m.get("triangles"))
        errors.extend(f"{where} ({mid!r}): {e}" for e in me)
        warnings.extend(f"{where} ({mid!r}): {w}" for w in mw)
        if isinstance(m.get("triangles"), list):
            total_tris += len(m["triangles"])
    if total_tris > LIMITS["max_total_triangles"]:
        errors.append(f"{total_tris} triangles in total exceed the limit {LIMITS['max_total_triangles']}")

    used: set = set()
    for i, c in enumerate(contacts):
        where = f"contacts[{i}]"
        if not isinstance(c, dict):
            errors.append(f"{where} must be an object")
            continue
        a, b = c.get("a"), c.get("b")
        if kinds.get(a) is None:
            errors.append(f"{where}: a={a!r} is not a body id")
            continue
        if b in kinds:
            if a == b:
                errors.append(f"{where}: a body cannot contact itself")
                continue
            key = ("body",) + tuple(sorted((a, b)))
            pair_kinds = (kinds[a], kinds[b])
            if static[a] and static[b]:
                errors.append(f"{where}: two static bodies cannot form a contact")
                continue
            if pair_kinds in _UNSUPPORTED or tuple(reversed(pair_kinds)) in _UNSUPPORTED:
                errors.append(f"{where}: unsupported pair {pair_kinds[0]}-{pair_kinds[1]}: "
                              f"{_UNSUPPORTED.get(pair_kinds, _UNSUPPORTED.get(tuple(reversed(pair_kinds))))}")
                continue
        elif b in plane_ids or b in mesh_ids:
            key = ("plane" if b in plane_ids else "mesh", a, b)
            if b in mesh_ids and kinds[a] == "box":
                errors.append(f"{where}: unsupported pair box-mesh: {_UNSUPPORTED[('box', 'mesh')]}")
                continue
            if static[a]:
                errors.append(f"{where}: a static body cannot form a contact with a static {key[0]}")
                continue
        else:
            errors.append(f"{where}: b={b!r} is not a body, plane or mesh id")
            continue
        if key in used:
            errors.append(f"{where}: contact {key[1:]!r} is listed more than once")
        used.add(key)
        if not (_is_num(c.get("friction")) and c["friction"] >= 0):
            errors.append(f"{where}: friction must be a finite number >= 0")
        if not (_is_num(c.get("restitution")) and 0.0 <= c["restitution"] <= 1.0):
            errors.append(f"{where}: restitution must be a number in [0, 1]")

    counts = {"bodies": len(bodies), "planes": len(planes), "meshes": len(meshes),
              "contacts": len(contacts), "triangles": total_tris}
    return {"valid": not errors, "errors": errors, "warnings": warnings, "counts": counts}


def require_valid_v3(scene: Any) -> Dict[str, Any]:
    result = validate_v3(scene)
    if not result["valid"]:
        raise OperationError("schema_error", "scene is not a valid schema v3 collision scene",
                             {"errors": result["errors"]})
    return result


def _mass_props(b: Dict[str, Any]) -> Tuple[float, Optional[float]]:
    """Mass and (for boxes) the volume-based density source. Static bodies have no mass."""
    if b.get("static"):
        return 0.0, None
    if b["type"] == "sphere":
        volume = 4.0 / 3.0 * math.pi * float(b["radius"]) ** 3
    else:
        hx, hy, hz = (float(x) for x in b["half_extents"])
        volume = 8.0 * hx * hy * hz
    if "material" in b:
        return default_database().get(b["material"]).density * volume, volume
    if "density" in b:
        return float(b["density"]) * volume, volume
    return float(b["mass"]), volume


def _build(scene: Dict[str, Any]):
    body_list = scene["bodies"]
    index = {b["id"]: i for i, b in enumerate(body_list)}
    plane_list = scene.get("planes", [])
    planes = {p["id"]: Plane(tuple(float(x) for x in p["normal"]), float(p["offset"])) for p in plane_list}
    mesh_list = scene.get("meshes", [])
    meshes = {}
    for m in mesh_list:
        meshes[m["id"]] = MSH.TriangleMesh(
            m["id"], tuple(tuple(float(x) for x in v) for v in m["vertices"]),
            tuple(tuple(int(k) for k in t) for t in m["triangles"]),
            tuple(float(x) for x in m.get("position", [0.0, 0.0, 0.0])),
            tuple(float(x) for x in m["quaternion"]) if m.get("quaternion") is not None else (1.0, 0.0, 0.0, 0.0))
    bodies: List[SV.Body] = []
    for b in body_list:
        mass, _ = _mass_props(b)
        q = tuple(float(x) for x in b["quaternion"]) if b.get("quaternion") is not None else (1.0, 0.0, 0.0, 0.0)
        bodies.append(SV.Body(
            name=b["id"], kind=b["type"], mass=mass,
            position=tuple(float(x) for x in b["position"]), velocity=tuple(float(x) for x in b["velocity"]),
            quaternion=q, omega_body=tuple(float(x) for x in b["omega"]),
            radius=float(b.get("radius", 0.0)),
            half=tuple(float(x) for x in b.get("half_extents", (0.0, 0.0, 0.0))),
            static=bool(b.get("static", False))))
    specs: List[SV.PairSpec] = []
    labels: List[Dict[str, str]] = []
    for c in scene.get("contacts", []):
        f, e = float(c["friction"]), float(c["restitution"])
        a_id, b_id = c["a"], c["b"]
        if b_id in planes:
            kind = "sphere_plane" if body_list[index[a_id]]["type"] == "sphere" else "box_plane"
            specs.append(SV.PairSpec(kind, None, index[a_id], f, e, planes[b_id]))
            labels.append({"kind": "plane", "body": a_id, "other": b_id})
        elif b_id in meshes:
            specs.append(SV.PairSpec("sphere_mesh", None, index[a_id], f, e, meshes[b_id]))
            labels.append({"kind": "mesh", "body": a_id, "other": b_id})
        else:
            ta, tb = body_list[index[a_id]]["type"], body_list[index[b_id]]["type"]
            if ta == "sphere" and tb == "sphere":
                specs.append(SV.PairSpec("sphere_sphere", index[a_id], index[b_id], f, e))
            elif ta == "box" and tb == "box":  # Phase 7: normal A -> B, as listed in the scene
                specs.append(SV.PairSpec("box_box", index[a_id], index[b_id], f, e))
            else:  # exactly one box: the box is the first side (normal box -> sphere)
                box_id, sph_id = (a_id, b_id) if ta == "box" else (b_id, a_id)
                specs.append(SV.PairSpec("sphere_box", index[box_id], index[sph_id], f, e))
            labels.append({"kind": "body", "body": a_id, "other": b_id})
    return bodies, specs, labels, index, meshes


def run(scene: Dict[str, Any], duration: float, dt: float = 1e-4, record_interval: float = 0.01,
        limits: Any = None, cancel_event: Any = None) -> Dict[str, Any]:
    """Run a v3 scene for ``duration`` seconds from t = 0. Same step convention as v1 and v2."""
    lim = ResourceLimits.from_dict(limits)
    require_valid_v3(scene)
    duration = _check_number(duration, "duration", positive=True)
    dt = _check_number(dt, "dt", positive=True)
    record_interval = _check_number(record_interval, "record_interval", positive=True)

    steps = max(1, int(round(duration / dt)))
    dt_eff = duration / steps
    rec_every = max(1, int(round(record_interval / dt_eff)))
    if steps > lim.max_steps:
        raise OperationError("resource_limit", f"{steps} steps exceed max_steps={lim.max_steps}",
                             {"limit": "max_steps", "value": lim.max_steps, "requested": steps})
    n_records = steps // rec_every + 2
    if n_records > lim.max_records:
        raise OperationError("resource_limit", f"{n_records} records exceed max_records={lim.max_records}",
                             {"limit": "max_records", "value": lim.max_records, "requested": n_records})

    scene_sha = S.scene_hash(scene)
    deadline = Deadline(lim)
    wall_start = time.monotonic()
    bodies, specs, labels, index, meshes = _build(scene)
    gravity = tuple(float(x) for x in scene["environment"]["gravity"])
    names = [b.name for b in bodies]

    def contact_names(touching_specs):
        out: Dict[str, List[str]] = {n: [] for n in names}
        for si in touching_specs:
            lab = labels[si]
            out[lab["body"]].append(f"{lab['kind']}:{lab['other']}")
            if lab["kind"] == "body":
                out[lab["other"]].append(f"body:{lab['body']}")
        return out

    def sample(k: int, touching: Dict[str, List[str]]) -> Dict[str, Any]:
        ke = 0.0
        pe = 0.0
        recs: Dict[str, Any] = {}
        for b in bodies:
            if b.static:  # same keys as a dynamic body, so every reader works on any body; a static body is at rest
                recs[b.name] = {"static": True, "position": list(b.position), "velocity": [0.0, 0.0, 0.0],
                                "quaternion": list(b.quaternion), "omega_body": [0.0, 0.0, 0.0],
                                "omega_world": [0.0, 0.0, 0.0], "kinetic_energy_translational": 0.0,
                                "kinetic_energy_rotational": 0.0, "potential_energy_gravity": 0.0,
                                "contacts": touching.get(b.name, [])}
                continue
            ke_t = 0.5 * b.mass * dot(b.velocity, b.velocity)
            ke_r = b.kinetic_energy() - ke_t
            pe_b = -b.mass * dot(gravity, b.position)
            ke += ke_t + ke_r
            pe += pe_b
            recs[b.name] = {
                "position": list(b.position), "velocity": list(b.velocity), "quaternion": list(b.quaternion),
                "omega_body": list(b.omega_body), "omega_world": list(b.omega_world()),
                "kinetic_energy_translational": ke_t, "kinetic_energy_rotational": ke_r,
                "potential_energy_gravity": pe_b, "contacts": touching.get(b.name, []),
            }
        p = SV.total_momentum(bodies)
        return {"t": k * dt_eff, "bodies": recs, "momentum_total": list(p), "energy_total": ke + pe}

    records = [sample(0, {})]
    max_pen = 0.0
    max_quat_err = 0.0
    for k in range(1, steps + 1):
        if cancel_event is not None and cancel_event.is_set():
            raise OperationError("cancelled", f"run cancelled at step {k} of {steps}",
                                 {"step": k, "time": (k - 1) * dt_eff})
        if k % CHECK_EVERY_STEPS == 0:
            deadline.check(f"at step {k}")
        info = SV.step(bodies, specs, dt_eff, gravity)
        for b in bodies:
            if not (_finite_list(b.position) and _finite_list(b.velocity) and _finite_list(b.omega_body)
                    and _finite_list(b.quaternion)):
                raise OperationError("invalid_state", f"non-finite state at step {k}, t = {k * dt_eff:.6g} s",
                                     {"step": k, "time": k * dt_eff})
            if not b.static:
                max_quat_err = max(max_quat_err, abs(quat_norm(b.quaternion) - 1.0))
        max_pen = max(max_pen, info.max_penetration)
        if max_pen > PENETRATION_TOLERANCE_M:
            raise OperationError("invalid_state",
                                 f"penetration {max_pen:.3e} m exceeds {PENETRATION_TOLERANCE_M} m at step {k}",
                                 {"step": k, "max_penetration_m": max_pen, "tolerance_m": PENETRATION_TOLERANCE_M})
        if k % rec_every == 0 or k == steps:
            records.append(sample(k, contact_names(info.touching)))

    t_end = steps * dt_eff
    final_state = {
        "time": t_end, "scene_sha256": scene_sha,
        "bodies": {b.name: {"position": list(b.position), "velocity": list(b.velocity),
                            "quaternion": list(b.quaternion), "omega_body": list(b.omega_body)}
                   for b in bodies},
    }
    wall = time.monotonic() - wall_start
    return {
        "result_schema": RESULT_SCHEMA,
        "result_schema_version": RESULT_SCHEMA_VERSION,
        "scene": scene,
        "scene_sha256": scene_sha,
        "configuration": {
            "duration_s": duration, "dt_requested_s": dt, "dt_s": dt_eff, "steps": steps,
            "record_interval_requested_s": record_interval, "record_interval_s": rec_every * dt_eff,
            "integrator": "collision.solver.step: predict, detect, sequential impulses (8), move, project (2), rotate",
            "bodies": len(bodies), "contacts": len(specs),
            "meshes": {mid: {"triangles": len(m.triangles), "bvh_nodes": m.bvh.node_count}
                       for mid, m in meshes.items()},
        },
        "software": {"package": "reality", "version": __version__, "python": platform.python_version()},
        "random_seed": None,
        "random_seed_reason": "the kernel has no stochastic component",
        "limits": lim.to_dict(),
        "checks": {
            "finite_state": True,
            "max_penetration_m": max_pen,
            "penetration_tolerance_m": PENETRATION_TOLERANCE_M,
            "max_quaternion_norm_error": max_quat_err,
        },
        "records": records,
        "final_state": final_state,
        "diagnostics": {  # not reproducible: wall-clock and memory are measured, not computed
            "wall_seconds": round(wall, 4),
            "steps_per_second": round(steps / wall, 1) if wall > 0 else None,
            "peak_memory_mb": peak_memory_mb(),
        },
    }
