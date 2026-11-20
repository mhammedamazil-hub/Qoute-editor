"""Blender-independent part of the Reality add-on: body descriptions -> schema v2 scene -> keyframe samples.

Nothing here imports ``bpy``, so it is tested with the normal Python test suite. The add-on (``__init__.py``) reads
Blender objects, calls these functions and writes the results into keyframes.

Conventions (all SI, Blender's own: Z up, metres, seconds):
- positions in metres; quaternions (w, x, y, z), rotating body-frame vectors into the world frame (the same
  convention as Blender's ``rotation_quaternion``, so no conversion is needed);
- a plane is {x : n . x = offset}; its normal is normalised by the solver;
- gravity is {0, 0, -9.80665} m/s^2 by default (``reality.constants.STANDARD_GRAVITY``).

Scene version. A scene whose bodies are all dynamic spheres is written as schema v2 (with a ``meshes`` list when
meshes are marked). Scenes with boxes or static bodies are written as schema v3. The motion is always computed by the
headless kernel through ``simulate.multibody`` (the same entry point as the CLI and the API), never by Blender.

Colliders (Phase 6). Spheres and boxes can be dynamic or static; triangle meshes are static only. Static bodies and
meshes are not keyed: they do not move. Box-box and box-mesh contacts are not implemented in the kernel, so a bake
that needs one is refused with the kernel's reason.

Contact coefficients. Each Blender object carries its own friction and restitution. A contact between two objects
uses the smaller of their two values. This is a modelling choice made for the add-on, not a physical law, and it is
documented in ``engine``/add-on docs as such. A mesh contact uses the same rule with the mesh's own values.
"""

from __future__ import annotations

import math
import re
from typing import Any, Dict, Iterable, List, Optional, Sequence

from reality.constants import STANDARD_GRAVITY
from reality.control import operations as OPS
from reality.control import scene as S

MAX_TIMESTEP_S = 1e-3   # the largest fixed step the add-on will use (solver is first order in the step)
DEFAULT_FRICTION = 0.5
DEFAULT_RESTITUTION = 0.0


def unit_quaternion(q: Sequence[float]) -> List[float]:
    """Normalise a quaternion (w, x, y, z) in double precision.

    Blender stores rotations as float32, whose norm error (about 5e-8) is above the kernel's 1e-9 tolerance. The
    add-on passes every quaternion through here before the scene is built. A zero quaternion is an error.
    """
    values = [float(x) for x in q]
    if len(values) != 4 or not all(math.isfinite(x) for x in values):
        raise ValueError("quaternion must be four finite numbers")
    norm = math.sqrt(sum(x * x for x in values))
    if norm == 0.0:
        raise ValueError("quaternion has zero length")
    return [x / norm for x in values]


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
            "id": b["id"], "type": "sphere", "radius": float(b["radius"]),
            **({"material": b["material"]} if b.get("material") is not None else {}),
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


def frame_samples(result: Dict[str, Any], fps: float, frame_start: int,
                  ids: Optional[Iterable[str]] = None) -> List[Dict[str, Any]]:
    """Map each record of a run result to a Blender frame.

    Returns [{"frame", "t", "bodies": {id: {"position", "quaternion"}}}]. A record at time t lands on frame
    frame_start + round(t * fps). Each record must fall on a whole frame (``bake_timestep`` guarantees this); if it
    does not, the mismatch is an error rather than a silent rounding. ``ids``, when given, keeps only those bodies.
    """
    keep = None if ids is None else set(ids)
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
                       for bid, b in rec["bodies"].items() if keep is None or bid in keep},
        })
    return out


def build_any(bodies: Sequence[Dict[str, Any]], planes: Sequence[Dict[str, Any]],
              meshes: Sequence[Dict[str, Any]] = (), gravity: Sequence[float] = (0.0, 0.0, -STANDARD_GRAVITY),
              name: str = "blender") -> Dict[str, Any]:
    """Build a scene document in the lowest version that holds it.

    All bodies dynamic spheres: schema v2 (``build_scene``), plus ``meshes`` and mesh contacts when meshes are given.
    Otherwise: schema v3 with boxes, ``static`` flags and meshes.
    ``bodies``: {id, shape ("sphere" | "box", default sphere), radius | half_extents, material, position, velocity,
    omega, quaternion?, static (default False), friction, restitution}. ``meshes``: {id, vertices, triangles, position,
    quaternion?, friction, restitution}. Static bodies need no material; the kernel checks everything else.
    """
    shapes = [b.get("shape", "sphere") for b in bodies]
    statics = [bool(b.get("static", False)) for b in bodies]
    if all(s == "sphere" for s in shapes) and not any(statics):
        scene = build_scene(bodies, planes, gravity=gravity, name=name)
        if meshes:
            scene["meshes"] = [_mesh_entry(m) for m in meshes]
            for b in bodies:
                for m in meshes:
                    scene["contacts"].append({"a": b["id"], "b": m["id"],
                                              "friction": min(_f(b, "friction"), _f(m, "friction")),
                                              "restitution": min(_f(b, "restitution"), _f(m, "restitution"))})
        return scene

    body_list: List[Dict[str, Any]] = []
    for b, shape, static in zip(bodies, shapes, statics):
        entry: Dict[str, Any] = {"id": b["id"], "type": shape,
                                 "position": [float(x) for x in b["position"]],
                                 "velocity": [float(x) for x in b.get("velocity", (0.0, 0.0, 0.0))],
                                 "omega": [float(x) for x in b.get("omega", (0.0, 0.0, 0.0))]}
        if shape == "sphere":
            entry["radius"] = float(b["radius"])
        else:
            entry["half_extents"] = [float(x) for x in b["half_extents"]]
        if b.get("quaternion") is not None:
            entry["quaternion"] = [float(x) for x in b["quaternion"]]
        if static:
            entry["static"] = True
        elif b.get("material") is not None:  # a missing material is left for the kernel to report
            entry["material"] = b["material"]
        body_list.append(entry)
    plane_list = [{"id": p["id"], "normal": [float(x) for x in p["normal"]], "offset": float(p["offset"])}
                  for p in planes]
    mesh_list = [_mesh_entry(m) for m in meshes]
    contacts: List[Dict[str, Any]] = []

    def coeffs(x, y):
        return {"friction": min(_f(x, "friction"), _f(y, "friction")),
                "restitution": min(_f(x, "restitution"), _f(y, "restitution"))}

    for i, a in enumerate(bodies):
        for p in planes:  # a plane is static: a static body never contacts it
            if not statics[i]:
                contacts.append({"a": a["id"], "b": p["id"], **coeffs(a, p)})
        for m in meshes:  # a mesh is static: a static body never contacts it
            if not statics[i]:
                contacts.append({"a": a["id"], "b": m["id"], **coeffs(a, m)})
        for j in range(i + 1, len(bodies)):
            if statics[i] and statics[j]:
                continue  # two static bodies never form a contact
            b = bodies[j]
            contacts.append({"a": a["id"], "b": b["id"], **coeffs(a, b)})
    return {
        "schema": "reality.scene", "schema_version": 3, "name": name,
        "environment": {"gravity": [float(x) for x in gravity]},
        "bodies": body_list, "planes": plane_list, "meshes": mesh_list, "contacts": contacts,
    }


def _mesh_entry(m: Dict[str, Any]) -> Dict[str, Any]:
    entry: Dict[str, Any] = {"id": m["id"],
                             "vertices": [[float(x) for x in v] for v in m["vertices"]],
                             "triangles": [[int(i) for i in t] for t in m["triangles"]],
                             "position": [float(x) for x in m.get("position", (0.0, 0.0, 0.0))]}
    if m.get("quaternion") is not None:
        entry["quaternion"] = [float(x) for x in m["quaternion"]]
    return entry


def run_scene(scene: Dict[str, Any], duration: float, dt: float, record_interval: float) -> Dict[str, Any]:
    """Validate a scene document and run it through ``simulate.multibody``.

    Raises ValueError with the kernel's reasons when the scene is invalid, so the add-on reports them instead of
    running a bad scene.
    """
    check = S.validate(scene)
    if not check["valid"]:
        raise ValueError("scene is not valid: " + "; ".join(check["errors"]))
    return OPS.call("simulate.multibody", {"scene": scene, "duration": duration, "dt": dt,
                                           "record_interval": record_interval})


def bake_scene(bodies: Sequence[Dict[str, Any]], planes: Sequence[Dict[str, Any]], frames: int, fps: float,
               frame_start: int = 0, max_dt: float = MAX_TIMESTEP_S,
               gravity: Sequence[float] = (0.0, 0.0, -STANDARD_GRAVITY),
               meshes: Sequence[Dict[str, Any]] = ()) -> Dict[str, Any]:
    """Run the whole bake without Blender and return {"scene", "result", "samples", "timestep", "keyed", "static"}.

    ``samples`` cover dynamic bodies only; ``static`` lists the static bodies, which are not keyed.
    """
    if not isinstance(frames, int) or frames < 1:
        raise ValueError("frames must be an integer >= 1")
    step = bake_timestep(fps, max_dt)
    scene = build_any(bodies, planes, meshes, gravity=gravity)
    duration = frames / fps
    result = run_scene(scene, duration, dt=step["dt"], record_interval=1.0 / fps)
    keyed = [b["id"] for b in bodies if not b.get("static", False)]
    static = [b["id"] for b in bodies if b.get("static", False)]
    return {"scene": scene, "result": result, "samples": frame_samples(result, fps, frame_start, keyed),
            "timestep": step, "keyed": keyed, "static": static}


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
