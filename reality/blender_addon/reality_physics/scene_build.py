"""Blender-independent part of the Reality add-on: body descriptions -> schema v2 scene -> keyframe samples.

Nothing here imports ``bpy``, so it is tested with the normal Python test suite. The add-on (``__init__.py``) reads
Blender objects, calls these functions and writes the results into keyframes.

Conventions (all SI, Blender's own: Z up, metres, seconds):
- positions in metres; quaternions (w, x, y, z), rotating body-frame vectors into the world frame (the same
  convention as Blender's ``rotation_quaternion``, so no conversion is needed);
- a plane is {x : n . x = offset}; its normal is normalised by the solver;
- gravity is {0, 0, -9.80665} m/s^2 by default (``reality.constants.STANDARD_GRAVITY``).

Contact coefficients. Each Blender object carries its own friction and restitution. A contact between two objects
uses the smaller of their two values. This is a modelling choice made for the add-on, not a physical law, and it is
documented in ``engine``/add-on docs as such.
"""

from __future__ import annotations

import math
import re
from typing import Any, Dict, Iterable, List, Sequence

from reality.constants import STANDARD_GRAVITY
from reality.control import multibody_scene as MBS

MAX_TIMESTEP_S = 1e-3   # the largest fixed step the add-on will use (solver is first order in the step)
DEFAULT_FRICTION = 0.5
DEFAULT_RESTITUTION = 0.0


def bake_timestep(fps: float, max_dt: float = MAX_TIMESTEP_S) -> Dict[str, float]:
    """Pick a fixed step so that every frame is a whole number of solver steps.

    Returns {"substeps", "dt"}: ``substeps`` = ceil(1 / (fps * max_dt)) and ``dt`` = 1 / (fps * substeps), so the
    frame interval 1/fps is exactly ``substeps`` steps and ``dt`` never exceeds ``max_dt``.
    """
    if not (isinstance(fps, (int, float)) and math.isfinite(fps) and fps > 0):
        raise ValueError("fps must be a positive finite number")
    if not (max_dt > 0):
        raise ValueError("max_dt must be > 0")
    substeps = max(1, math.ceil(1.0 / (fps * max_dt) - 1e-9))
    return {"substeps": substeps, "dt": 1.0 / (fps * substeps)}


def build_scene(bodies: Sequence[Dict[str, Any]], planes: Sequence[Dict[str, Any]],
                gravity: Sequence[float] = (0.0, 0.0, -STANDARD_GRAVITY), name: str = "blender") -> Dict[str, Any]:
    """Build a schema v2 scene.

    ``bodies``: {id, radius, material, position, velocity, omega, friction, restitution}.
    ``planes``: {id, normal, offset, friction, restitution}. Every body is put in contact with every plane, and
    every pair of bodies with each other, using the smaller friction and restitution of the two objects.
    """
    body_list: List[Dict[str, Any]] = []
    for b in bodies:
        body_list.append({
            "id": b["id"], "type": "sphere", "radius": float(b["radius"]), "material": b["material"],
            "position": [float(x) for x in b["position"]],
            "velocity": [float(x) for x in b["velocity"]],
            "omega": [float(x) for x in b.get("omega", (0.0, 0.0, 0.0))],
            **({"quaternion": [float(x) for x in b["quaternion"]]} if b.get("quaternion") is not None else {}),
        })
    plane_list = [{"id": p["id"], "normal": [float(x) for x in p["normal"]], "offset": float(p["offset"])}
                  for p in planes]
    contacts: List[Dict[str, Any]] = []
    for i, a in enumerate(bodies):
        for p in planes:
            contacts.append({"a": a["id"], "b": p["id"],
                             "friction": min(_f(a, "friction"), _f(p, "friction")),
                             "restitution": min(_f(a, "restitution"), _f(p, "restitution"))})
        for b in bodies[i + 1:]:
            contacts.append({"a": a["id"], "b": b["id"],
                             "friction": min(_f(a, "friction"), _f(b, "friction")),
                             "restitution": min(_f(a, "restitution"), _f(b, "restitution"))})
    return {
        "schema": "reality.scene", "schema_version": 2, "name": name,
        "environment": {"gravity": [float(x) for x in gravity]},
        "bodies": body_list, "planes": plane_list, "contacts": contacts,
    }


def _f(item: Dict[str, Any], key: str) -> float:
    default = DEFAULT_FRICTION if key == "friction" else DEFAULT_RESTITUTION
    value = item.get(key)
    return float(default if value is None else value)


def frame_samples(result: Dict[str, Any], fps: float, frame_start: int) -> List[Dict[str, Any]]:
    """Map each record of a ``reality.multibody_run`` to a Blender frame.

    Returns [{"frame", "t", "bodies": {id: {"position", "quaternion"}}}]. A record at time t lands on frame
    frame_start + round(t * fps). Each record must fall on a whole frame (``bake_timestep`` guarantees this); if it
    does not, the mismatch is an error rather than a silent rounding.
    """
    out: List[Dict[str, Any]] = []
    for rec in result["records"]:
        exact = rec["t"] * fps
        frame_offset = round(exact)
        if abs(exact - frame_offset) > 1e-6:
            raise ValueError(f"record at t={rec['t']} does not fall on a frame (fps={fps})")
        out.append({
            "frame": int(frame_start + frame_offset),
            "t": rec["t"],
            "bodies": {bid: {"position": list(b["position"]), "quaternion": list(b["quaternion"])}
                       for bid, b in rec["bodies"].items()},
        })
    return out


def bake_scene(bodies: Sequence[Dict[str, Any]], planes: Sequence[Dict[str, Any]], frames: int, fps: float,
               frame_start: int = 0, max_dt: float = MAX_TIMESTEP_S,
               gravity: Sequence[float] = (0.0, 0.0, -STANDARD_GRAVITY)) -> Dict[str, Any]:
    """Run the whole bake without Blender and return {"scene", "result", "samples", "timestep"}."""
    if not isinstance(frames, int) or frames < 1:
        raise ValueError("frames must be an integer >= 1")
    step = bake_timestep(fps, max_dt)
    scene = build_scene(bodies, planes, gravity=gravity)
    duration = frames / fps
    result = MBS.run(scene, duration, dt=step["dt"], record_interval=1.0 / fps)
    return {"scene": scene, "result": result, "samples": frame_samples(result, fps, frame_start),
            "timestep": step}


def safe_id(name: str, used: Iterable[str]) -> str:
    """Map a Blender object name (e.g. ``Sphere.001``) to a schema id: letter first, [A-Za-z0-9_-], <= 64 chars,
    unique among ``used``."""
    base = re.sub(r"[^A-Za-z0-9_\-]", "_", name)[:60]
    if not base or not base[0].isalpha():
        base = "b_" + base
    base = base[:60]
    taken = set(used)
    candidate, n = base, 1
    while candidate in taken:
        n += 1
        candidate = f"{base}_{n}"
    return candidate
