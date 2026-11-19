"""Headless CPU preview of a simulation frame (see PREVIEW_SYSTEM.md).

Method: orthographic ray casting, one ray per pixel, against the analytic sphere and the infinite plane(s). No mesh,
no GPU, no desktop. Shading is Lambert with one fixed light. Overlays are drawn as 2D lines on top:

- yellow arrow: velocity of the sphere centre (length scaled to the run's maximum speed);
- red arrow: gravity force m g (length scaled to m g);
- cyan disc: contact point, when the sphere touches a plane in that frame.

An image is a picture for visual checks only. Every number in it is also returned in ``description``, because an
image cannot carry exact values.
"""

from __future__ import annotations

import base64
import hashlib
import math
import os
from typing import Any, Dict, List, Optional

from . import scene as S
from .errors import OperationError
from .raster import Color, draw_line, encode_png, fill_disc, new_buffer
from .resources import ResourceLimits

BG_TOP: Color = (28, 32, 44)
BG_BOTTOM: Color = (62, 72, 90)
SPHERE_BASE = (70, 130, 200)
TILE_A = (190, 190, 180)
TILE_B = (120, 120, 115)
VELOCITY_COLOR: Color = (255, 200, 0)
GRAVITY_COLOR: Color = (255, 80, 80)
CONTACT_COLOR: Color = (0, 220, 220)
ARROW_FRACTION = 0.3  # arrow length as a fraction of the view half-height, at the run's reference magnitude


def _unit(v):
    n = math.sqrt(sum(x * x for x in v))
    if n == 0.0:
        raise ValueError("zero-length vector")
    return (v[0] / n, v[1] / n, v[2] / n)


def _cross(a, b):
    return (a[1] * b[2] - a[2] * b[1], a[2] * b[0] - a[0] * b[2], a[0] * b[1] - a[1] * b[0])


def _dot(a, b):
    return a[0] * b[0] + a[1] * b[1] + a[2] * b[2]


def camera_basis(azimuth_deg: float, elevation_deg: float):
    """Forward (into the scene), right and up unit vectors for an orthographic camera."""
    az, el = math.radians(azimuth_deg), math.radians(elevation_deg)
    to_camera = (math.cos(el) * math.cos(az), math.cos(el) * math.sin(az), math.sin(el))
    forward = (-to_camera[0], -to_camera[1], -to_camera[2])
    right = _unit(_cross(forward, (0.0, 0.0, 1.0)))
    up = _cross(right, forward)
    return forward, right, up


def _run_bounds(result: Dict[str, Any], body_ids: List[str]):
    lo = [math.inf] * 3
    hi = [-math.inf] * 3
    for rec in result["records"]:
        for bid in body_ids:
            p = rec["bodies"][bid]["position"]
            for i in range(3):
                lo[i] = min(lo[i], p[i])
                hi[i] = max(hi[i], p[i])
    return lo, hi


def render_frame(result: Dict[str, Any], index: int = -1, width: int = 480, height: int = 320,
                 azimuth_deg: float = -35.0, elevation_deg: float = 20.0,
                 show_velocity: bool = True, show_gravity: bool = True, show_contacts: bool = True,
                 out_path: Optional[str] = None, include_base64: bool = False,
                 limits: Optional[Dict[str, Any]] = None) -> Dict[str, Any]:
    lim = ResourceLimits.from_dict(limits)
    for name, v in (("width", width), ("height", height)):
        if isinstance(v, bool) or not isinstance(v, int) or v < 16:
            raise OperationError("invalid_argument", f"{name} must be an integer >= 16")
        if v > lim.max_image_side:
            raise OperationError("resource_limit", f"{name} {v} exceeds max_image_side={lim.max_image_side}",
                                 {"limit": "max_image_side", "value": lim.max_image_side})
    if width * height > lim.max_pixels:
        raise OperationError("resource_limit", f"{width}x{height} exceeds max_pixels={lim.max_pixels}",
                             {"limit": "max_pixels", "value": lim.max_pixels, "requested": width * height})
    for name, v in (("azimuth_deg", azimuth_deg), ("elevation_deg", elevation_deg)):
        if isinstance(v, bool) or not isinstance(v, (int, float)) or not math.isfinite(float(v)):
            raise OperationError("invalid_argument", f"{name} must be a finite number")
    if not -89.0 <= elevation_deg <= 89.0:
        raise OperationError("invalid_argument", "elevation_deg must lie in [-89, 89]")

    recs = result.get("records")
    if not recs:
        raise OperationError("not_found", "result has no records")
    n = len(recs)
    idx = index if index >= 0 else n + index
    if not 0 <= idx < n:
        raise OperationError("invalid_argument", f"index {index} is outside 0..{n - 1}")
    rec = recs[idx]
    body_ids = list(result["bodies"])
    body = result["scene"]["bodies"][0]
    radius = body["radius"]
    planes = result["scene"]["planes"]
    body_id = body_ids[0]
    props = S.mass_properties(body)

    # View extent is fixed by the whole run so that frames of one run are directly comparable.
    lo, hi = _run_bounds(result, body_ids)
    centre = [(lo[i] + hi[i]) / 2.0 for i in range(3)]
    half_diag = math.sqrt(sum((hi[i] - lo[i]) ** 2 for i in range(3))) / 2.0
    view_r = max(half_diag + radius, 2.0 * radius) * 1.25
    c = tuple(centre)
    forward, right, up = camera_basis(azimuth_deg, elevation_deg)
    half_h = view_r
    half_w = view_r * width / height
    plane_limit = 3.0 * view_r
    light = _unit((0.4 * right[0] + 0.7 * up[0] - 0.6 * forward[0],
                   0.4 * right[1] + 0.7 * up[1] - 0.6 * forward[1],
                   0.4 * right[2] + 0.7 * up[2] - 0.6 * forward[2]))
    origin_back = 4.0 * view_r

    sphere_c = tuple(rec["bodies"][body_id]["position"])
    buf = new_buffer(width, height)
    plane_data = []
    for p in planes:
        nrm = _unit(p["normal"])
        # Two in-plane axes for the checkerboard.
        helper = (1.0, 0.0, 0.0) if abs(nrm[0]) < 0.9 else (0.0, 1.0, 0.0)
        e1 = _unit(_cross(nrm, helper))
        e2 = _cross(nrm, e1)
        plane_data.append((nrm, p["offset"], e1, e2))
    tile = max(view_r / 6.0, 1e-12)
    inv_w, inv_h = 2.0 / width, 2.0 / height
    for py in range(height):
        sy = (1.0 - (py + 0.5) * inv_h) * half_h
        top_t = py / height
        bg = (int(BG_TOP[0] + (BG_BOTTOM[0] - BG_TOP[0]) * top_t),
              int(BG_TOP[1] + (BG_BOTTOM[1] - BG_TOP[1]) * top_t),
              int(BG_TOP[2] + (BG_BOTTOM[2] - BG_TOP[2]) * top_t))
        row = py * width * 3
        for px in range(width):
            sx = ((px + 0.5) * inv_w - 1.0) * half_w
            o = (c[0] + sx * right[0] + sy * up[0] - origin_back * forward[0],
                 c[1] + sx * right[1] + sy * up[1] - origin_back * forward[1],
                 c[2] + sx * right[2] + sy * up[2] - origin_back * forward[2])
            best_t = math.inf
            colour = bg
            # sphere
            oc = (o[0] - sphere_c[0], o[1] - sphere_c[1], o[2] - sphere_c[2])
            b = oc[0] * forward[0] + oc[1] * forward[1] + oc[2] * forward[2]
            disc = b * b - (oc[0] ** 2 + oc[1] ** 2 + oc[2] ** 2 - radius * radius)
            if disc >= 0.0:
                t = -b - math.sqrt(disc)
                if t > 0.0 and t < best_t:
                    best_t = t
                    hit = (o[0] + t * forward[0], o[1] + t * forward[1], o[2] + t * forward[2])
                    nrm_s = ((hit[0] - sphere_c[0]) / radius, (hit[1] - sphere_c[1]) / radius,
                             (hit[2] - sphere_c[2]) / radius)
                    lam = 0.3 + 0.7 * max(0.0, _dot(nrm_s, light))
                    colour = (int(SPHERE_BASE[0] * lam), int(SPHERE_BASE[1] * lam), int(SPHERE_BASE[2] * lam))
            # planes
            for nrm, off, e1, e2 in plane_data:
                denom = _dot(nrm, forward)
                if abs(denom) < 1e-12:
                    continue
                t = (off - _dot(nrm, o)) / denom
                if 0.0 < t < best_t:
                    hit = (o[0] + t * forward[0], o[1] + t * forward[1], o[2] + t * forward[2])
                    rel = (hit[0] - c[0], hit[1] - c[1], hit[2] - c[2])
                    if math.sqrt(sum(x * x for x in rel)) > plane_limit:
                        continue
                    best_t = t
                    u1 = _dot(hit, e1) / tile
                    u2 = _dot(hit, e2) / tile
                    parity = (math.floor(u1) + math.floor(u2)) % 2
                    base = TILE_A if parity == 0 else TILE_B
                    lam = 0.35 + 0.65 * max(0.0, abs(_dot(nrm, light)))
                    colour = (int(base[0] * lam), int(base[1] * lam), int(base[2] * lam))
            buf[row + px * 3] = colour[0]
            buf[row + px * 3 + 1] = colour[1]
            buf[row + px * 3 + 2] = colour[2]

    def project(p):
        rel = (p[0] - c[0], p[1] - c[1], p[2] - c[2])
        x = (_dot(rel, right) / half_w + 1.0) * 0.5 * width
        y = (1.0 - _dot(rel, up) / half_h) * 0.5 * height
        return x, y

    # overlays
    st = rec["bodies"][body_id]
    v = st["velocity"]
    speed = math.sqrt(_dot(v, v))
    max_speed = max(math.sqrt(_dot(r["bodies"][body_id]["velocity"], r["bodies"][body_id]["velocity"]))
                    for r in recs)
    weight = props["mass"] * math.sqrt(sum(x * x for x in result["scene"]["environment"]["gravity"]))
    v_scale = (ARROW_FRACTION * half_h / max_speed) if max_speed > 0 else 0.0
    g_scale = (ARROW_FRACTION * half_h / weight) if weight > 0 else 0.0
    g_vec = result["scene"]["environment"]["gravity"]
    x0, y0 = project(sphere_c)
    arrows = []
    if show_velocity and speed > 0.0 and v_scale > 0.0:
        tip = tuple(sphere_c[i] + v[i] * v_scale for i in range(3))
        arrows.append(("velocity", VELOCITY_COLOR, project(tip)))
    if show_gravity and weight > 0.0:
        tip = tuple(sphere_c[i] + g_vec[i] * props["mass"] * g_scale for i in range(3))
        arrows.append(("gravity_force", GRAVITY_COLOR, project(tip)))
    for _, col, (x1, y1) in arrows:
        draw_line(buf, width, height, x0, y0, x1, y1, col, thickness=2)
        ang = math.atan2(y1 - y0, x1 - x0)
        for da in (math.radians(150), math.radians(-150)):
            draw_line(buf, width, height, x1, y1, x1 + 7 * math.cos(ang + da), y1 + 7 * math.sin(ang + da),
                      col, thickness=2)
    contact_px = None
    if show_contacts and st["contacts"]:
        pl = next(p for p in planes if p["id"] == st["contacts"][0])
        nh = _unit(pl["normal"])
        cp = tuple(sphere_c[i] - radius * nh[i] for i in range(3))
        contact_px = project(cp)
        fill_disc(buf, width, height, contact_px[0], contact_px[1], 4.0, CONTACT_COLOR)
    sphere_px_radius = radius / (2.0 * half_h) * height

    png = encode_png(width, height, buf)
    digest = hashlib.sha256(png).hexdigest()
    path_out = None
    if out_path is not None:
        if not isinstance(out_path, str) or not out_path.lower().endswith(".png"):
            raise OperationError("invalid_argument", "out_path must end in .png")
        parent = os.path.dirname(os.path.abspath(out_path))
        os.makedirs(parent, exist_ok=True)
        with open(out_path, "wb") as fh:
            fh.write(png)
        path_out = out_path
    description = {
        "frame": {"index": idx, "time_s": rec["t"], "contacts": st["contacts"],
                  "position_m": st["position"], "velocity_m_s": st["velocity"],
                  "speed_m_s": speed},
        "image": {"width_px": width, "height_px": height,
                  "metres_per_pixel": 2.0 * half_h / height,
                  "projection": "orthographic", "azimuth_deg": azimuth_deg, "elevation_deg": elevation_deg,
                  "view_forward": list(forward), "view_right": list(right), "view_up": list(up),
                  "view_centre_m": list(c), "view_half_height_m": half_h},
        "projected": {body_id: {"centre_px": [x0, y0], "radius_px": sphere_px_radius}},
        "planes": [{"id": p["id"], "normal": p["normal"], "offset": p["offset"]} for p in planes],
        "overlays": {
            "velocity_arrow": {"colour_rgb": list(VELOCITY_COLOR), "shown": bool(arrows) and any(a[0] == "velocity" for a in arrows),
                               "metres_per_second_per_metre": (1.0 / v_scale) if v_scale > 0 else None,
                               "reference_speed_m_s": max_speed},
            "gravity_arrow": {"colour_rgb": list(GRAVITY_COLOR), "shown": any(a[0] == "gravity_force" for a in arrows),
                              "newton_per_metre": (1.0 / g_scale) if g_scale > 0 else None,
                              "reference_force_N": weight},
            "contact_marker": {"colour_rgb": list(CONTACT_COLOR), "shown": contact_px is not None,
                               "centre_px": list(contact_px) if contact_px else None},
        },
        "legend": "yellow arrow = velocity; red arrow = gravity force m g; cyan disc = contact point; "
                  "checkerboard = plane; blue sphere = body",
        "png_sha256": digest,
        "png_bytes": len(png),
        "out_path": path_out,
    }
    out: Dict[str, Any] = {"description": description}
    if include_base64 or out_path is None:
        out["png_base64"] = base64.b64encode(png).decode("ascii")
        out["mime_type"] = "image/png"
    return out
