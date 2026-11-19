"""Observation of simulation results (see API_REFERENCE.md and AI_CAPABILITY_MATRIX.md).

Rules of this module:

- Only quantities the physical model produces are reported as values. Every other quantity the brief lists appears
  under ``unsupported`` with the reason, so no value is ever invented.
- Quantities marked ``derived`` are computed from recorded states (finite differences, geometry). They are not
  solver outputs and say so in the ``method`` text.
"""

from __future__ import annotations

import math
from typing import Any, Dict, List, Optional

from . import scene as S
from .errors import OperationError

UNSUPPORTED_BODY_FIELDS = {
    "contact_force_N": "the contact solver does not expose impulses or forces in this release",
    "torque_N_m": "the contact solver does not expose torques in this release",
    "temperature_K": "the rigid-body model has no thermal state",
    "pressure_Pa": "the rigid-body model has no pressure field",
    "stress_Pa": "the rigid body is not deformable; no stress field exists",
    "strain": "the rigid body is not deformable; no strain field exists",
    "solver_convergence": "the stepper is explicit and fixed-step; it has no iterations to converge",
}


def _record(result: Dict[str, Any], index: int) -> Dict[str, Any]:
    recs = result.get("records")
    if not recs:
        raise OperationError("not_found", "result has no records")
    n = len(recs)
    if index < -n or index >= n:
        raise OperationError("invalid_argument", f"index {index} is outside 0..{n - 1}",
                             {"records": n})
    return recs[index] if index >= 0 else recs[n + index]


def _body_props(result: Dict[str, Any], body_id: str) -> Dict[str, Any]:
    body = next((b for b in result["scene"]["bodies"] if b["id"] == body_id), None)
    if body is None:
        raise OperationError("not_found", f"no body {body_id!r} in this result",
                             {"bodies": result.get("bodies", [])})
    return {"body": body, "props": S.mass_properties(body)}


def _cross(a, b):
    return (a[1] * b[2] - a[2] * b[1], a[2] * b[0] - a[0] * b[2], a[0] * b[1] - a[1] * b[0])


def _contact_point_velocity(state: Dict[str, Any], normal, radius: float):
    """Velocity of the contact point on the sphere at -R n (world frame). Derived."""
    r_c = (-radius * normal[0], -radius * normal[1], -radius * normal[2])
    w = _cross(state["omega_world"], r_c)
    return (state["velocity"][0] + w[0], state["velocity"][1] + w[1], state["velocity"][2] + w[2])


def _unit(v):
    n = math.sqrt(sum(x * x for x in v))
    return None if n == 0 else (v[0] / n, v[1] / n, v[2] / n)


def body_state(result: Dict[str, Any], body_id: str, index: int = -1) -> Dict[str, Any]:
    """Every supported quantity for one body at one record, plus what is unsupported and why."""
    rec = _record(result, index)
    st = rec["bodies"].get(body_id)
    if st is None:
        raise OperationError("not_found", f"no body {body_id!r} in record {index}")
    info = _body_props(result, body_id)
    props, body = info["props"], info["body"]
    recs = result["records"]
    n = len(recs)
    idx = index if index >= 0 else n + index
    # Acceleration: centred finite difference of recorded velocity (derived, not a solver output).
    lo, hi = max(0, idx - 1), min(n - 1, idx + 1)
    if hi > lo:
        dt = recs[hi]["t"] - recs[lo]["t"]
        a_val = [(recs[hi]["bodies"][body_id]["velocity"][i] - recs[lo]["bodies"][body_id]["velocity"][i]) / dt
                 for i in range(3)]
        accel_method = "derived: centred finite difference of recorded velocity"
    else:
        a_val = None
        accel_method = "unavailable: needs at least two records"
    g = result["scene"]["environment"]["gravity"]
    m = props["mass"]
    values: Dict[str, Any] = {
        "time_s": rec["t"],
        "record_index": idx,
        "position_m": st["position"],
        "velocity_m_s": st["velocity"],
        "speed_m_s": math.sqrt(sum(x * x for x in st["velocity"])),
        "acceleration_m_s2": a_val,
        "orientation_quaternion_wxyz": st["quaternion"],
        "angular_velocity_world_rad_s": st["omega_world"],
        "angular_velocity_body_rad_s": st["omega_body"],
        "mass_kg": m,
        "volume_m3": props["volume"],
        "density_kg_m3": props["density"],
        "density_source": props["density_source"],
        "inertia_principal_body_kg_m2": props["inertia_principal_body"],
        "gravity_force_N": [m * g[i] for i in range(3)],
        "kinetic_energy_translational_J": st["kinetic_energy_translational"],
        "kinetic_energy_rotational_J": st["kinetic_energy_rotational"],
        "potential_energy_gravity_J": st["potential_energy_gravity"],
        "contact_planes": st["contacts"],
        "in_contact": bool(st["contacts"]),
    }
    if st["contacts"]:
        plane = next(p for p in result["scene"]["planes"] if p["id"] == st["contacts"][0])
        n_hat = _unit(plane["normal"])
        vc = _contact_point_velocity(st, n_hat, body["radius"])
        values["contact_point_velocity_m_s"] = list(vc)
        values["slip_speed_m_s"] = math.sqrt(sum(x * x for x in vc))
    else:
        values["contact_point_velocity_m_s"] = None
        values["slip_speed_m_s"] = None
    unsupported = dict(UNSUPPORTED_BODY_FIELDS)
    unsupported["acceleration_m_s2_method"] = accel_method if a_val is None else None
    unsupported = {k: v for k, v in unsupported.items() if v is not None}
    checks = result["checks"]
    e0 = result["records"][0]["energy_total"]
    return {
        "body_id": body_id,
        "values": values,
        "unsupported": unsupported,
        "numerical": {
            "dt_s": result["configuration"]["dt_s"],
            "steps": result["configuration"]["steps"],
            "max_penetration_m": checks["max_penetration_m"],
            "max_quaternion_norm_error": checks["max_quaternion_norm_error"],
            "energy_total_J": rec["energy_total"],
            "energy_change_from_start_J": rec["energy_total"] - e0,
            "energy_note": "friction and restitution remove energy; the change is physical, not an error measure",
        },
    }


def scene_state(result: Dict[str, Any], index: int = -1) -> Dict[str, Any]:
    rec = _record(result, index)
    return {
        "time_s": rec["t"],
        "bodies": {bid: body_state(result, bid, index)["values"] for bid in result["bodies"]},
        "planes": [dict(p) for p in result["scene"]["planes"]],
        "gravity_m_s2": result["scene"]["environment"]["gravity"],
        "energy_total_J": rec["energy_total"],
        "checks": result["checks"],
    }


SERIES_FIELDS = {
    "x": lambda s: s["position"][0],
    "y": lambda s: s["position"][1],
    "z": lambda s: s["position"][2],
    "vx": lambda s: s["velocity"][0],
    "vy": lambda s: s["velocity"][1],
    "vz": lambda s: s["velocity"][2],
    "speed": lambda s: math.sqrt(sum(x * x for x in s["velocity"])),
    "omega_wz": lambda s: s["omega_world"][2],
    "ke_translational": lambda s: s["kinetic_energy_translational"],
    "ke_rotational": lambda s: s["kinetic_energy_rotational"],
    "potential_gravity": lambda s: s["potential_energy_gravity"],
    "contacts": lambda s: len(s["contacts"]),
}


def series(result: Dict[str, Any], body_id: str, fields: Optional[List[str]] = None) -> Dict[str, Any]:
    fields = fields or ["x", "z", "vx", "speed", "omega_wz", "contacts"]
    unknown = [f for f in fields if f not in SERIES_FIELDS]
    if unknown:
        raise OperationError("invalid_argument", f"unknown series fields {unknown}",
                             {"allowed": sorted(SERIES_FIELDS)})
    if body_id not in result.get("bodies", []):
        raise OperationError("not_found", f"no body {body_id!r} in this result")
    out: Dict[str, Any] = {"body_id": body_id, "t": [r["t"] for r in result["records"]]}
    for f in fields:
        out[f] = [SERIES_FIELDS[f](r["bodies"][body_id]) for r in result["records"]]
    return out


def rolling_onset(result: Dict[str, Any], body_id: str) -> Dict[str, Any]:
    """Time at which a sliding sphere starts to roll, from the contact-point slip (derived).

    With constant Coulomb friction the slip speed falls linearly in time until rolling starts (exact for the
    continuum model). The onset is the zero of a least-squares line fitted to the slip samples between 10 % and 90 %
    of the initial slip. This is an estimate from recorded states, not a solver output.
    """
    info = _body_props(result, body_id)
    radius = info["body"]["radius"]
    contacts = S.contacts_for(result["scene"], body_id)
    if not contacts:
        return {"available": False, "reason": "the body has no contact entry"}
    plane = next(p for p in result["scene"]["planes"] if p["id"] == contacts[0]["plane"])
    n_hat = _unit(plane["normal"])
    samples = []
    for r in result["records"]:
        st = r["bodies"][body_id]
        if st["contacts"]:
            samples.append((r["t"], _contact_point_velocity(st, n_hat, radius)))
    if len(samples) < 3:
        return {"available": False, "reason": "fewer than 3 records in contact"}
    s0_vec = samples[0][1]
    s0 = math.sqrt(sum(x * x for x in s0_vec))
    if s0 < 1e-9:
        return {"available": False, "reason": "no initial slip"}
    e = tuple(x / s0 for x in s0_vec)
    pts = []
    for t, vc in samples:
        s = sum(vc[i] * e[i] for i in range(3))
        if 0.1 * s0 <= s <= 0.9 * s0:
            pts.append((t, s))
    if len(pts) < 3:
        return {"available": False, "reason": "too few samples in the 10-90 % slip window; use a finer record_interval"}
    n = len(pts)
    mt = sum(p[0] for p in pts) / n
    ms = sum(p[1] for p in pts) / n
    sxx = sum((p[0] - mt) ** 2 for p in pts)
    if sxx == 0.0:
        return {"available": False, "reason": "degenerate time samples"}
    slope = sum((p[0] - mt) * (p[1] - ms) for p in pts) / sxx
    if slope >= 0.0:
        return {"available": False, "reason": "slip is not decreasing"}
    intercept = ms - slope * mt
    return {
        "available": True,
        "time_s": -intercept / slope,
        "initial_slip_m_s": s0,
        "points_used": n,
        "method": "derived: least-squares zero of contact-point slip over 10-90 % of initial slip",
    }


def summary(result: Dict[str, Any]) -> Dict[str, Any]:
    body_id = result["bodies"][0]
    last = body_state(result, body_id, -1)["values"]
    return {
        "final_time_s": last["time_s"],
        "final_position_m": last["position_m"],
        "final_velocity_m_s": last["velocity_m_s"],
        "final_angular_velocity_world_rad_s": last["angular_velocity_world_rad_s"],
        "in_contact_at_end": last["in_contact"],
        "rolling_onset": rolling_onset(result, body_id),
        "max_penetration_m": result["checks"]["max_penetration_m"],
        "records": len(result["records"]),
    }
