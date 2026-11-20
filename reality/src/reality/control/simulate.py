"""Headless simulation of one sphere on planes (schema v1 scenes).

The stepper is ``contact.step_sphere`` (fixed step, predict-detect-resolve). This module adds only bookkeeping:
recording, resource budgets, state checks, checkpoints and parameter sweeps. It does not change the physics.

Result documents (``reality.run`` version 1) hold everything needed to reproduce the run: the scene, the numerical
configuration, the software version, the seed (null, because nothing is stochastic) and the limits used. Wall-clock
and memory numbers are kept under ``diagnostics`` only, so the rest of the document is bit-for-bit reproducible.
"""

from __future__ import annotations

import math
import platform
import time
from typing import Any, Dict, List, Optional

from .. import __version__
from .. import contact as CT
from .. import rigidbody as RB
from . import scene as S
from .errors import OperationError
from .resources import Deadline, ResourceLimits, peak_memory_mb

RESULT_SCHEMA = "reality.run"
RESULT_SCHEMA_VERSION = 1
PENETRATION_TOLERANCE_M = 1e-6  # larger penetration after the solver step is treated as an invalid state
CHECK_EVERY_STEPS = 500


def _finite_list(values) -> bool:
    return all(math.isfinite(x) for x in values)


def _check_number(value: Any, name: str, positive: bool) -> float:
    if isinstance(value, bool) or not isinstance(value, (int, float)) or not math.isfinite(float(value)):
        raise OperationError("invalid_argument", f"{name} must be a finite number")
    if positive and float(value) <= 0.0:
        raise OperationError("invalid_argument", f"{name} must be > 0")
    return float(value)


def run(scene: Dict[str, Any], duration: float, dt: float = 1e-4, record_interval: float = 0.01,
        checkpoint: Optional[Dict[str, Any]] = None, limits: Optional[Dict[str, Any]] = None,
        cancel_event: Any = None) -> Dict[str, Any]:
    """Run a scene for ``duration`` seconds from t = 0, or continue from ``checkpoint``.

    The step is ``dt_eff = duration / steps`` with ``steps = round(duration / dt)``, the same convention as
    ``rigidbody.integrate``. ``record_interval`` is rounded to a whole number of steps.
    """
    lim = ResourceLimits.from_dict(limits)
    S.require_valid(scene)
    if scene.get("schema_version") != 1:
        raise OperationError("unsupported", "simulate.run takes schema v1 scenes; use simulate.multibody for v2")
    if len(scene["bodies"]) != 1:
        raise OperationError("unsupported", "a run needs exactly one body in schema v1")
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

    body = scene["bodies"][0]
    body_id = body["id"]
    props = S.mass_properties(body)
    contacts = S.contacts_for(scene, body_id)
    friction = contacts[0]["friction"] if contacts else 0.0
    restitution = contacts[0]["restitution"] if contacts else 0.0
    plane_by_id = {p["id"]: p for p in scene["planes"]}
    active_planes = [c["plane"] for c in contacts]
    planes = [CT.Plane(tuple(plane_by_id[pid]["normal"]), plane_by_id[pid]["offset"]) for pid in active_planes]
    gravity = tuple(scene["environment"]["gravity"])
    radius = body["radius"]
    scene_sha = S.scene_hash(scene)

    if checkpoint is not None:
        if not isinstance(checkpoint, dict) or checkpoint.get("scene_sha256") != scene_sha:
            raise OperationError("invalid_argument",
                                 "checkpoint does not belong to this scene (scene_sha256 differs)")
        t0 = _check_number(checkpoint["time"], "checkpoint.time", positive=False)
        st = checkpoint["bodies"].get(body_id)
        if st is None:
            raise OperationError("invalid_argument", f"checkpoint has no state for body {body_id!r}")
        pos, vel, quat, omega = st["position"], st["velocity"], st["quaternion"], st["omega_body"]
    else:
        t0 = 0.0
        pos, vel = body["position"], body["velocity"]
        quat, omega = [1.0, 0.0, 0.0, 0.0], body["omega"]

    rb = RB.RigidBody(props["mass"], tuple(props["inertia_principal_body"]),
                      position=tuple(pos), velocity=tuple(vel), quaternion=tuple(quat), omega=tuple(omega))
    deadline = Deadline(lim)
    records: List[Dict[str, Any]] = []
    max_penetration = 0.0
    max_quat_error = 0.0
    m = props["mass"]
    inertia = props["inertia_principal_body"]
    wall_start = time.monotonic()
    touching: List[int] = []

    def sample(step: int, touched: List[int]) -> Dict[str, Any]:
        t = t0 + step * dt_eff
        omega_world = RB.mat_vec(rb.rotation(), rb.omega)
        ke_t = 0.5 * m * RB.dot(rb.velocity, rb.velocity)
        ke_r = 0.5 * sum(inertia[i] * rb.omega[i] ** 2 for i in range(3))
        pe = -m * RB.dot(gravity, rb.position)
        return {
            "t": t,
            "bodies": {body_id: {
                "position": list(rb.position),
                "velocity": list(rb.velocity),
                "quaternion": list(rb.quaternion),
                "omega_body": list(rb.omega),
                "omega_world": list(omega_world),
                "kinetic_energy_translational": ke_t,
                "kinetic_energy_rotational": ke_r,
                "potential_energy_gravity": pe,
                "contacts": [active_planes[i] for i in touched],
            }},
            "energy_total": ke_t + ke_r + pe,
        }

    records.append(sample(0, []))
    for k in range(1, steps + 1):
        if cancel_event is not None and cancel_event.is_set():
            raise OperationError("cancelled", f"run cancelled at step {k} of {steps}",
                                 {"step": k, "time": t0 + (k - 1) * dt_eff})
        if k % CHECK_EVERY_STEPS == 0:
            deadline.check(f"at step {k}")
        touching = CT.step_sphere(rb, dt_eff, gravity, radius, planes,
                                  restitution=restitution, friction=friction)
        if not (_finite_list(rb.position) and _finite_list(rb.velocity) and _finite_list(rb.omega)
                and _finite_list(rb.quaternion)):
            raise OperationError("invalid_state", f"non-finite state at step {k}, t = {t0 + k * dt_eff:.6g} s",
                                 {"step": k, "time": t0 + k * dt_eff})
        for pl in planes:
            gap = RB.dot(pl.normal, rb.position) - pl.offset - radius
            if gap < 0.0:
                max_penetration = max(max_penetration, -gap)
        qn = abs(RB.norm(rb.quaternion) - 1.0)
        max_quat_error = max(max_quat_error, qn)
        if k % rec_every == 0 or k == steps:
            records.append(sample(k, touching))
    if max_penetration > PENETRATION_TOLERANCE_M:
        raise OperationError("invalid_state",
                             f"penetration {max_penetration:.3e} m exceeds {PENETRATION_TOLERANCE_M} m",
                             {"max_penetration_m": max_penetration, "tolerance_m": PENETRATION_TOLERANCE_M})

    t_end = t0 + steps * dt_eff
    final_state = {
        "time": t_end,
        "scene_sha256": scene_sha,
        "bodies": {body_id: {
            "position": list(rb.position), "velocity": list(rb.velocity),
            "quaternion": list(rb.quaternion), "omega_body": list(rb.omega),
        }},
    }
    wall = time.monotonic() - wall_start
    return {
        "result_schema": RESULT_SCHEMA,
        "result_schema_version": RESULT_SCHEMA_VERSION,
        "scene": scene,
        "scene_sha256": scene_sha,
        "configuration": {
            "duration_s": duration,
            "start_time_s": t0,
            "end_time_s": t_end,
            "dt_requested_s": dt,
            "dt_s": dt_eff,
            "steps": steps,
            "record_interval_requested_s": record_interval,
            "record_interval_s": rec_every * dt_eff,
            "integrator": "contact.step_sphere: fixed step, predict-detect-resolve (explicit)",
            "contact_friction": friction,
            "contact_restitution": restitution,
            "resumed_from_checkpoint": checkpoint is not None,
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
        "diagnostics": {  # not reproducible: wall-clock and memory are measured, not computed
            "wall_seconds": round(wall, 4),
            "steps_per_second": round(steps / wall, 1) if wall > 0 else None,
            "peak_memory_mb": peak_memory_mb(),
            "threads": 1,
        },
        "bodies": [body_id],
        "planes": [p["id"] for p in scene["planes"]],
        "records": records,
        "final_state": final_state,
    }


def sweep_contact_parameter(scene: Dict[str, Any], body: str, plane: str, friction_values: List[float],
                            duration: float, dt: float = 1e-4, record_interval: float = 0.01,
                            limits: Optional[Dict[str, Any]] = None) -> Dict[str, Any]:
    """Run the same scene for each friction value and return one summary per run (no full records)."""
    from .inspection import summary  # local import: inspection depends on this module's output format
    if not isinstance(friction_values, list) or not friction_values:
        raise OperationError("invalid_argument", "friction_values must be a non-empty list")
    if len(friction_values) > 100:
        raise OperationError("resource_limit", "at most 100 sweep values per call",
                             {"limit": "sweep_values", "value": 100})
    base_contacts = [c for c in S.contacts_for(scene, body) if c["plane"] == plane]
    restitution = base_contacts[0]["restitution"] if base_contacts else 0.0
    runs = []
    for f in friction_values:
        s2 = S.set_contact(scene, body, plane, f, restitution)
        res = run(s2, duration, dt=dt, record_interval=record_interval, limits=limits)
        runs.append({"friction": float(f), "summary": summary(res)})
    return {"parameter": "contact.friction", "body": body, "plane": plane,
            "duration_s": duration, "runs": runs}
