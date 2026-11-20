"""Scene schema v1: a serialisable, validated description of a simulation (see SCENE_SCHEMA.md).

Scope of schema v1 (deliberately narrow, every limit is enforced here, not silently ignored):

- one or more planes (infinite, normal + offset);
- exactly one solid sphere per run (multi-body contact is not implemented);
- contacts are explicit (body, plane, friction, restitution). A plane with no contact entry does not collide;
- gravity is a uniform vector (default standard gravity, -z);
- the sphere's initial orientation is the identity quaternion.

Mass and inertia come from ``objects.Sphere`` and ``materials.default_database``. They are not re-derived here.
"""

from __future__ import annotations

import copy
import hashlib
import json
import math
import re
from typing import Any, Dict, List, Optional

from .. import constants as C
from ..materials import default_database
from ..objects import Sphere
from .errors import OperationError

SCHEMA = "reality.scene"
SCHEMA_VERSION = 1
DEFAULT_GRAVITY = [0.0, 0.0, -C.STANDARD_GRAVITY]
_ID_RE = re.compile(r"^[A-Za-z][A-Za-z0-9_\-]{0,63}$")


# ----------------------------------------------------------------- helpers
def _vec3(value: Any, name: str) -> List[float]:
    if not isinstance(value, (list, tuple)) or len(value) != 3:
        raise OperationError("invalid_argument", f"{name} must be a list of 3 numbers")
    out = []
    for x in value:
        if isinstance(x, bool) or not isinstance(x, (int, float)) or not math.isfinite(float(x)):
            raise OperationError("invalid_argument", f"{name} must contain finite numbers")
        out.append(float(x))
    return out


def _positive(value: Any, name: str) -> float:
    if isinstance(value, bool) or not isinstance(value, (int, float)) or not math.isfinite(float(value)) \
            or float(value) <= 0.0:
        raise OperationError("invalid_argument", f"{name} must be a finite number > 0")
    return float(value)


def _check_id(value: Any, what: str) -> str:
    if not isinstance(value, str) or not _ID_RE.match(value):
        raise OperationError("invalid_argument",
                             f"{what} id must start with a letter and use letters, digits, '_' or '-' (max 64)")
    return value


def _find(items: List[Dict[str, Any]], key: str) -> Optional[Dict[str, Any]]:
    for it in items:
        if it.get("id") == key:
            return it
    return None


def new_scene(name: str, gravity: Optional[List[float]] = None) -> Dict[str, Any]:
    if not isinstance(name, str) or not name.strip() or len(name) > 120:
        raise OperationError("invalid_argument", "scene name must be a non-empty string of at most 120 characters")
    g = _vec3(gravity, "gravity") if gravity is not None else list(DEFAULT_GRAVITY)
    return {
        "schema": SCHEMA,
        "schema_version": SCHEMA_VERSION,
        "name": name,
        "environment": {"gravity": g, "units": "SI"},
        "bodies": [],
        "planes": [],
        "contacts": [],
        "random_seed": None,
    }


def _copy(scene: Dict[str, Any]) -> Dict[str, Any]:
    if not isinstance(scene, dict):
        raise OperationError("schema_error", "scene must be a JSON object")
    return copy.deepcopy(scene)


def _ensure_free(scene: Dict[str, Any], key: str) -> None:
    if _find(scene.get("bodies", []), key) or _find(scene.get("planes", []), key):
        raise OperationError("invalid_argument", f"an object with id {key!r} already exists")


def add_sphere(scene: Dict[str, Any], id: str, radius: float, material: Optional[str] = None,
               mass: Optional[float] = None, density: Optional[float] = None,
               position: Optional[List[float]] = None, velocity: Optional[List[float]] = None,
               omega: Optional[List[float]] = None) -> Dict[str, Any]:
    s = _copy(scene)
    _ensure_free(s, _check_id(id, "body"))
    body: Dict[str, Any] = {"id": id, "type": "sphere", "radius": _positive(radius, "radius")}
    given = [k for k, v in (("material", material), ("mass", mass), ("density", density)) if v is not None]
    if len(given) != 1:
        raise OperationError("invalid_argument", "give exactly one of material, mass or density for a body",
                             {"given": given})
    if material is not None:
        if not isinstance(material, str):
            raise OperationError("invalid_argument", "material must be a material name")
        if material.lower() not in default_database():
            raise OperationError("not_found", f"unknown material {material!r}",
                                 {"available": default_database().names()})
        body["material"] = material.lower()
    if mass is not None:
        body["mass"] = _positive(mass, "mass")
    if density is not None:
        body["density"] = _positive(density, "density")
    body["position"] = _vec3(position if position is not None else [0.0, 0.0, 0.0], "position")
    body["velocity"] = _vec3(velocity if velocity is not None else [0.0, 0.0, 0.0], "velocity")
    body["omega"] = _vec3(omega if omega is not None else [0.0, 0.0, 0.0], "omega")
    s["bodies"].append(body)
    return s


def add_plane(scene: Dict[str, Any], id: str, normal: Optional[List[float]] = None,
              offset: float = 0.0) -> Dict[str, Any]:
    s = _copy(scene)
    _ensure_free(s, _check_id(id, "plane"))
    n = _vec3(normal if normal is not None else [0.0, 0.0, 1.0], "normal")
    length = math.sqrt(sum(x * x for x in n))
    if length == 0.0:
        raise OperationError("invalid_argument", "plane normal must not be zero")
    if isinstance(offset, bool) or not isinstance(offset, (int, float)) or not math.isfinite(float(offset)):
        raise OperationError("invalid_argument", "offset must be a finite number")
    s["planes"].append({"id": id, "normal": n, "offset": float(offset)})
    return s


_BODY_FIELDS = ("radius", "material", "mass", "density", "position", "velocity", "omega")


def set_body(scene: Dict[str, Any], id: str, fields: Dict[str, Any]) -> Dict[str, Any]:
    s = _copy(scene)
    body = _find(s["bodies"], id)
    if body is None:
        raise OperationError("not_found", f"no body with id {id!r}", {"bodies": [b["id"] for b in s["bodies"]]})
    unknown = sorted(set(fields) - set(_BODY_FIELDS))
    if unknown:
        raise OperationError("invalid_argument", f"cannot set {unknown}; allowed: {list(_BODY_FIELDS)}")
    for key, value in fields.items():
        if key == "radius":
            body["radius"] = _positive(value, "radius")
        elif key == "material":
            if str(value).lower() not in default_database():
                raise OperationError("not_found", f"unknown material {value!r}")
            body.pop("mass", None)
            body.pop("density", None)
            body["material"] = str(value).lower()
        elif key == "mass":
            body.pop("material", None)
            body.pop("density", None)
            body["mass"] = _positive(value, "mass")
        elif key == "density":
            body.pop("material", None)
            body.pop("mass", None)
            body["density"] = _positive(value, "density")
        else:
            body[key] = _vec3(value, key)
    problems = validate(s)["errors"]
    if problems:
        raise OperationError("schema_error", "set_body would make the scene invalid", {"problems": problems})
    return s


def set_gravity(scene: Dict[str, Any], gravity: List[float]) -> Dict[str, Any]:
    s = _copy(scene)
    s["environment"]["gravity"] = _vec3(gravity, "gravity")
    return s


def set_contact(scene: Dict[str, Any], body: str, plane: str, friction: float,
                restitution: float = 0.0) -> Dict[str, Any]:
    s = _copy(scene)
    if _find(s["bodies"], body) is None:
        raise OperationError("not_found", f"no body with id {body!r}")
    if _find(s["planes"], plane) is None:
        raise OperationError("not_found", f"no plane with id {plane!r}")
    if isinstance(friction, bool) or not isinstance(friction, (int, float)) or not math.isfinite(float(friction)) \
            or float(friction) < 0.0:
        raise OperationError("invalid_argument", "friction must be a finite number >= 0")
    if isinstance(restitution, bool) or not isinstance(restitution, (int, float)) \
            or not (0.0 <= float(restitution) <= 1.0):
        raise OperationError("invalid_argument", "restitution must be a number in [0, 1]")
    entry = {"body": body, "plane": plane, "friction": float(friction), "restitution": float(restitution)}
    existing = [c for c in s["contacts"] if c["body"] == body and c["plane"] == plane]
    if existing:
        s["contacts"] = [entry if (c["body"] == body and c["plane"] == plane) else c for c in s["contacts"]]
    else:
        s["contacts"].append(entry)
    problems = validate(s)["errors"]
    if problems:
        raise OperationError("unsupported", "set_contact would make the scene invalid", {"problems": problems})
    return s


def remove(scene: Dict[str, Any], id: str) -> Dict[str, Any]:
    s = _copy(scene)
    if _find(s["bodies"], id) is None and _find(s["planes"], id) is None:
        raise OperationError("not_found", f"no body or plane with id {id!r}")
    s["bodies"] = [b for b in s["bodies"] if b["id"] != id]
    s["planes"] = [p for p in s["planes"] if p["id"] != id]
    s["contacts"] = [c for c in s["contacts"] if c["body"] != id and c["plane"] != id]
    return s


# -------------------------------------------------------------- validation
def validate(scene: Dict[str, Any]) -> Dict[str, Any]:
    """Return {"valid", "errors", "warnings"}. Never raises; use ``require_valid`` to raise."""
    errors: List[str] = []
    warnings: List[str] = []
    if not isinstance(scene, dict):
        return {"valid": False, "errors": ["scene must be a JSON object"], "warnings": []}
    if scene.get("schema_version") == 2:  # multi-body scenes: see multibody_scene.py
        from .multibody_scene import validate_v2
        return validate_v2(scene)
    if scene.get("schema") != SCHEMA:
        errors.append(f"schema must be {SCHEMA!r}")
    if scene.get("schema_version") != SCHEMA_VERSION:
        errors.append(f"unsupported: schema_version must be {SCHEMA_VERSION}")
    if not isinstance(scene.get("name"), str) or not scene.get("name"):
        errors.append("name must be a non-empty string")
    env = scene.get("environment", {})
    try:
        _vec3(env.get("gravity"), "environment.gravity")
    except OperationError as exc:
        errors.append(f"environment.gravity: {exc.message}")
    bodies = scene.get("bodies", [])
    planes = scene.get("planes", [])
    contacts = scene.get("contacts", [])
    if not isinstance(bodies, list) or not isinstance(planes, list) or not isinstance(contacts, list):
        return {"valid": False, "errors": errors + ["bodies, planes and contacts must be lists"], "warnings": []}

    seen: Dict[str, str] = {}
    for b in bodies:
        bid = b.get("id", "")
        if not isinstance(bid, str) or not _ID_RE.match(bid):
            errors.append(f"body id {bid!r} is not valid")
            continue
        if bid in seen:
            errors.append(f"duplicate id {bid!r}")
        seen[bid] = "body"
        if b.get("type") != "sphere":
            errors.append(f"unsupported: body {bid!r} has type {b.get('type')!r}; schema v1 supports 'sphere' only")
            continue
        if not _finite_pos(b.get("radius")):
            errors.append(f"body {bid!r}: radius must be a finite number > 0")
        given = [k for k in ("material", "mass", "density") if k in b]
        if len(given) != 1:
            errors.append(f"body {bid!r}: give exactly one of material, mass or density (got {given})")
        if "material" in b and str(b["material"]).lower() not in default_database():
            errors.append(f"body {bid!r}: unknown material {b['material']!r}")
        for key in ("mass", "density"):
            if key in b and not _finite_pos(b[key]):
                errors.append(f"body {bid!r}: {key} must be a finite number > 0")
        for key in ("position", "velocity", "omega"):
            try:
                _vec3(b.get(key), f"body {bid!r} {key}")
            except OperationError as exc:
                errors.append(exc.message)
    for p in planes:
        pid = p.get("id", "")
        if not isinstance(pid, str) or not _ID_RE.match(pid):
            errors.append(f"plane id {pid!r} is not valid")
            continue
        if pid in seen:
            errors.append(f"duplicate id {pid!r}")
        seen[pid] = "plane"
        try:
            n = _vec3(p.get("normal"), f"plane {pid!r} normal")
            if sum(x * x for x in n) == 0.0:
                errors.append(f"plane {pid!r}: normal must not be zero")
        except OperationError as exc:
            errors.append(exc.message)
        off = p.get("offset", 0.0)
        if isinstance(off, bool) or not isinstance(off, (int, float)) or not math.isfinite(float(off)):
            errors.append(f"plane {pid!r}: offset must be finite")
    body_ids = [b["id"] for b in bodies if isinstance(b.get("id"), str)]
    plane_ids = [p["id"] for p in planes if isinstance(p.get("id"), str)]
    if len(bodies) > 1:
        errors.append("unsupported: multi-body scenes are not implemented (see AI_CONTROL_ARCHITECTURE.md section 2.3)")
    pairs = set()
    for c in contacts:
        b, p = c.get("body"), c.get("plane")
        if b not in body_ids:
            errors.append(f"contact refers to unknown body {b!r}")
        if p not in plane_ids:
            errors.append(f"contact refers to unknown plane {p!r}")
        if (b, p) in pairs:
            errors.append(f"duplicate contact ({b!r}, {p!r})")
        pairs.add((b, p))
        f = c.get("friction")
        if isinstance(f, bool) or not isinstance(f, (int, float)) or not math.isfinite(float(f)) or f < 0:
            errors.append(f"contact ({b!r}, {p!r}): friction must be a finite number >= 0")
        e = c.get("restitution", 0.0)
        if isinstance(e, bool) or not isinstance(e, (int, float)) or not (0.0 <= float(e) <= 1.0):
            errors.append(f"contact ({b!r}, {p!r}): restitution must be in [0, 1]")
    for b in body_ids:
        bc = [c for c in contacts if c.get("body") == b]
        if len({(c.get("friction"), c.get("restitution", 0.0)) for c in bc}) > 1:
            errors.append(f"unsupported: body {b!r} has different friction or restitution per plane; "
                          "the contact solver takes one pair per body in this release")
        if not bc and planes:
            warnings.append(f"body {b!r} has no contact entry; it does not collide with any plane")
    for p in plane_ids:
        if not any(c.get("plane") == p for c in contacts) and body_ids:
            warnings.append(f"plane {p!r} has no contact entry; it does not collide with any body")
    if not bodies:
        warnings.append("scene has no bodies")
    return {"valid": not errors, "errors": errors, "warnings": warnings}


def _finite_pos(v: Any) -> bool:
    return isinstance(v, (int, float)) and not isinstance(v, bool) and math.isfinite(float(v)) and float(v) > 0


def require_valid(scene: Dict[str, Any]) -> None:
    report = validate(scene)
    if report["errors"]:
        unsupported = [e for e in report["errors"] if e.startswith("unsupported:")]
        code = "unsupported" if unsupported else "schema_error"
        raise OperationError(code, "; ".join(report["errors"]), {"problems": report["errors"]})


def scene_hash(scene: Dict[str, Any]) -> str:
    """SHA-256 of the canonical JSON text of a scene (used to bind checkpoints to their scene)."""
    text = json.dumps(scene, sort_keys=True, separators=(",", ":"), allow_nan=False)
    return hashlib.sha256(text.encode("utf-8")).hexdigest()


# ---------------------------------------------------------- derived properties
def mass_properties(body: Dict[str, Any]) -> Dict[str, Any]:
    """Mass, volume, density and principal inertia of a sphere body (derived; not stored in the scene)."""
    shape = Sphere(body["radius"])
    volume = shape.volume()
    if "material" in body:
        material = default_database().get(body["material"])
        density = material.density
        mass = density * volume
        source = f"material:{material.name}"
    elif "density" in body:
        density = float(body["density"])
        mass = density * volume
        source = "density"
    else:
        mass = float(body["mass"])
        density = mass / volume
        source = "mass"
    k = shape.principal_inertia_per_mass()
    return {
        "mass": mass,
        "volume": volume,
        "density": density,
        "density_source": source,
        "inertia_principal_body": [mass * x for x in k],
    }


def contacts_for(scene: Dict[str, Any], body_id: str) -> List[Dict[str, Any]]:
    return [c for c in scene.get("contacts", []) if c.get("body") == body_id]


def describe(scene: Dict[str, Any]) -> Dict[str, Any]:
    """Numerical summary of a scene (no images). Raises if the scene is invalid."""
    require_valid(scene)
    bodies = []
    for b in scene["bodies"]:
        props = mass_properties(b)
        bodies.append({
            "id": b["id"], "type": b["type"], "radius": b["radius"],
            "mass": props["mass"], "volume": props["volume"], "density": props["density"],
            "density_source": props["density_source"],
            "inertia_principal_body": props["inertia_principal_body"],
            "position": b["position"], "velocity": b["velocity"], "omega": b["omega"],
        })
    return {
        "name": scene["name"],
        "gravity": scene["environment"]["gravity"],
        "bodies": bodies,
        "planes": [dict(p) for p in scene["planes"]],
        "contacts": [dict(c) for c in scene["contacts"]],
        "warnings": validate(scene)["warnings"],
        "scene_sha256": scene_hash(scene),
    }
