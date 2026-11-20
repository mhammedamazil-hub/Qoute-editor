"""Narrow phase: contact geometry between a sphere and a triangle, a box, a plane, and a sphere-sphere pair.

Pure functions, no solver state. Every result is a ``Contact``:

- ``normal``: unit vector pointing from the *first* shape towards the second (for a sphere against a static shape,
  from the static shape towards the sphere). The same convention as ``multibody``.
- ``point``: a point on the surface of the first shape where the contact is (world coordinates). Exception: box-box
  contacts (``box_box.py``) use the midpoint of the overlap along the normal, because the solver uses one point for
  both bodies and the midpoint is the symmetric choice.
- ``depth``: overlap along ``normal`` in metres. Positive = penetrating; ``depth > -tolerance`` counts as touching.
- ``feature``: "face", "edge" or "vertex" (triangles and boxes), or "sphere" (sphere-sphere, sphere-plane).

Degenerate inputs are handled explicitly. A zero-length normal is never divided by: a sphere centred exactly on a
triangle picks the face normal with a winding-independent sign rule (see ``_canonical_sign``), and a zero-area
triangle falls back to its three edges. Nothing returns NaN.

Relative tolerance: geometry scales are compared against ``REL_EPS * scale``, so results do not depend on whether
the coordinates are in metres or micrometres.
"""

from __future__ import annotations

import math
from dataclasses import dataclass
from typing import Optional

from ..rigidbody import Mat3, Vec3, add, cross, dot, mat_t, mat_vec, norm, scale, sub

REL_EPS = 1e-12      # relative tolerance for "zero" lengths and areas
TOUCH_TOL = 1e-9     # m; contacts with depth > -TOUCH_TOL are reported (matches contact.CONTACT_TOLERANCE)


@dataclass(frozen=True)
class Contact:
    normal: Vec3
    point: Vec3
    depth: float
    feature: str


def _canonical_sign(n: Vec3) -> Vec3:
    """Winding-independent sign choice for a normal of unknown side: first nonzero component positive."""
    for comp in (n[2], n[1], n[0]):
        if abs(comp) > REL_EPS:
            return n if comp > 0.0 else scale(n, -1.0)
    return n


def closest_point_on_segment(p: Vec3, a: Vec3, b: Vec3) -> Vec3:
    ab = sub(b, a)
    denom = dot(ab, ab)
    if denom <= 0.0:
        return a
    t = dot(sub(p, a), ab) / denom
    t = 0.0 if t < 0.0 else (1.0 if t > 1.0 else t)
    return add(a, scale(ab, t))


def closest_point_on_triangle(p: Vec3, a: Vec3, b: Vec3, c: Vec3) -> tuple:
    """Closest point of triangle abc to p, and the feature it lies on. Voronoi-region method (Ericson 2005).

    Divisions are guarded: when a denominator is zero (degenerate triangle or a point on a region boundary), the
    result is the closest of the three edges, which is always defined.
    """
    ab = sub(b, a)
    ac = sub(c, a)
    area2 = dot(cross(ab, ac), cross(ab, ac))
    scale2 = max(dot(ab, ab), dot(ac, ac), dot(sub(c, b), sub(c, b))) ** 2
    if area2 <= REL_EPS * scale2:  # zero-area triangle: edges only
        best = None
        for e0, e1 in ((a, b), (b, c), (c, a)):
            q = closest_point_on_segment(p, e0, e1)
            d2 = dot(sub(p, q), sub(p, q))
            if best is None or d2 < best[0]:
                best = (d2, q)
        return best[1], "edge"

    ap = sub(p, a)
    d1 = dot(ab, ap)
    d2 = dot(ac, ap)
    if d1 <= 0.0 and d2 <= 0.0:
        return a, "vertex"
    bp = sub(p, b)
    d3 = dot(ab, bp)
    d4 = dot(ac, bp)
    if d3 >= 0.0 and d4 <= d3:
        return b, "vertex"
    vc = d1 * d4 - d3 * d2
    if vc <= 0.0 and d1 >= 0.0 and d3 <= 0.0 and (d1 - d3) != 0.0:
        return add(a, scale(ab, d1 / (d1 - d3))), "edge"
    cp = sub(p, c)
    d5 = dot(ab, cp)
    d6 = dot(ac, cp)
    if d6 >= 0.0 and d5 <= d6:
        return c, "vertex"
    vb = d5 * d2 - d1 * d6
    if vb <= 0.0 and d2 >= 0.0 and d6 <= 0.0 and (d2 - d6) != 0.0:
        return add(a, scale(ac, d2 / (d2 - d6))), "edge"
    va = d3 * d6 - d5 * d4
    if va <= 0.0 and (d4 - d3) >= 0.0 and (d5 - d6) >= 0.0 and ((d4 - d3) + (d5 - d6)) != 0.0:
        w = (d4 - d3) / ((d4 - d3) + (d5 - d6))
        return add(b, scale(sub(c, b), w)), "edge"
    denom = va + vb + vc
    if denom == 0.0 or not math.isfinite(denom):
        return closest_point_on_triangle_edges(p, a, b, c)
    v = vb / denom
    w = vc / denom
    return add(a, add(scale(ab, v), scale(ac, w))), "face"


def closest_point_on_triangle_edges(p: Vec3, a: Vec3, b: Vec3, c: Vec3) -> tuple:
    best = None
    for e0, e1 in ((a, b), (b, c), (c, a)):
        q = closest_point_on_segment(p, e0, e1)
        d2 = dot(sub(p, q), sub(p, q))
        if best is None or d2 < best[0]:
            best = (d2, q)
    return best[1], "edge"


def sphere_triangle(center: Vec3, radius: float, a: Vec3, b: Vec3, c: Vec3,
                    prefer: Optional[Vec3] = None) -> Optional[Contact]:
    """Contact between a sphere and triangle abc (world coordinates). None when they are separated.

    ``prefer``: optional direction the sphere came from (for example, minus its velocity). It only matters when the
    sphere centre lies exactly on the triangle, where the side is otherwise undefined.
    """
    if not radius > 0.0:
        raise ValueError("sphere radius must be > 0")
    q, feature = closest_point_on_triangle(center, a, b, c)
    d = sub(center, q)
    dist = norm(d)
    tol = REL_EPS * max(radius, norm(sub(b, a)), norm(sub(c, a)), 1e-300)
    if dist > tol:
        depth = radius - dist
        if depth <= -TOUCH_TOL:
            return None
        return Contact(scale(d, 1.0 / dist), q, depth, feature)
    # centre on the triangle: the side is set by the face normal, otherwise by a perpendicular to a degenerate edge
    n_face = cross(sub(b, a), sub(c, a))
    n_len = norm(n_face)
    if n_len > REL_EPS * max(norm(sub(b, a)) * norm(sub(c, a)), 1e-300):
        n = scale(n_face, 1.0 / n_len)
        if prefer is not None and dot(n, prefer) < 0.0:
            n = scale(n, -1.0)
        elif prefer is None:
            n = _canonical_sign(n)
    else:
        n = _perpendicular_to_edge(sub(b, a) if norm(sub(b, a)) >= norm(sub(c, b)) else sub(c, b), prefer)
    return Contact(n, q, radius, feature)


def _perpendicular_to_edge(edge: Vec3, prefer: Optional[Vec3]) -> Vec3:
    e = scale(edge, 1.0 / norm(edge)) if norm(edge) > 0.0 else (1.0, 0.0, 0.0)
    base = (0.0, 0.0, 1.0) if abs(e[2]) < 0.9 else (1.0, 0.0, 0.0)
    p = cross(e, base)
    p = scale(p, 1.0 / norm(p))
    if prefer is not None and dot(p, prefer) < 0.0:
        p = scale(p, -1.0)
    elif prefer is None:
        p = _canonical_sign(p)
    return p


def sphere_box(center: Vec3, radius: float, box_centre: Vec3, box_rot: Mat3, half: Vec3) -> Optional[Contact]:
    """Contact between a sphere and a box (centre, rotation body->world, half edge lengths). Normal: box -> sphere.

    Outside: the closest point on the box and its direction. Inside (centre within the box): exit through the face
    with the least slack. Ties go to the lowest axis index, which keeps the result deterministic.
    """
    if not radius > 0.0:
        raise ValueError("sphere radius must be > 0")
    if any(not h > 0.0 for h in half):
        raise ValueError("box half extents must be > 0")
    local = mat_vec(mat_t(box_rot), sub(center, box_centre))
    clamped = tuple(max(-half[i], min(half[i], local[i])) for i in range(3))
    diff = sub(local, clamped)
    dist = norm(diff)
    if dist > 0.0:
        if dist >= radius + TOUCH_TOL:
            return None
        n_local = scale(diff, 1.0 / dist)
        p_local = clamped
        depth = radius - dist
        n_axes = sum(1 for i in range(3) if abs(diff[i]) > REL_EPS * max(half))
        feature = ("face", "edge", "vertex")[min(n_axes, 3) - 1]
    else:
        slack = [half[i] - abs(local[i]) for i in range(3)]
        i = min(range(3), key=lambda k: (slack[k], k))
        s = 1.0 if local[i] >= 0.0 else -1.0
        n_local = (0.0, 0.0, 0.0)
        n_local = tuple(s if k == i else 0.0 for k in range(3))
        p_local = tuple(s * half[i] if k == i else local[k] for k in range(3))
        depth = radius + slack[i]
        feature = "face"
    n = mat_vec(box_rot, n_local)
    p = add(box_centre, mat_vec(box_rot, p_local))
    return Contact(n, p, depth, feature)


def box_corners_plane(box_centre: Vec3, box_rot: Mat3, half: Vec3, plane_normal: Vec3,
                      plane_offset: float) -> list:
    """Corners of a box that are at or below a plane {x : n.x = offset}. Normal: the plane normal (plane -> box).

    Returns one Contact per corner with depth > -TOUCH_TOL, sorted by corner index (deterministic).
    """
    out = []
    for sx in (-1.0, 1.0):
        for sy in (-1.0, 1.0):
            for sz in (-1.0, 1.0):
                corner_local = (sx * half[0], sy * half[1], sz * half[2])
                v = add(box_centre, mat_vec(box_rot, corner_local))
                sd = dot(plane_normal, v) - plane_offset
                depth = -sd
                if depth > -TOUCH_TOL:
                    out.append(Contact(plane_normal, v, depth, "vertex"))
    return out


def sphere_plane(center: Vec3, radius: float, plane_normal: Vec3, plane_offset: float) -> Optional[Contact]:
    """Sphere against an infinite plane. ``plane_normal`` must be unit length. Normal: plane -> sphere."""
    gap = dot(plane_normal, center) - plane_offset - radius
    depth = -gap
    if depth <= -TOUCH_TOL:
        return None
    point = sub(center, scale(plane_normal, radius))
    return Contact(plane_normal, point, depth, "sphere")


def sphere_sphere(c_a: Vec3, r_a: float, c_b: Vec3, r_b: float) -> Optional[Contact]:
    """Two spheres. Normal: a -> b. Coincident centres are rejected (the normal is undefined)."""
    d = sub(c_b, c_a)
    dist = norm(d)
    depth = (r_a + r_b) - dist
    if depth <= -TOUCH_TOL:
        return None
    if dist == 0.0:
        raise ValueError("spheres have coincident centres; contact normal undefined")
    n = scale(d, 1.0 / dist)
    return Contact(n, add(c_a, scale(n, r_a)), depth, "sphere")
