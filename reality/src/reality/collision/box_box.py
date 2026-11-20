"""Box-box narrow phase: 15-axis separating axis test, face manifolds by clipping, edge contacts by closest points.

Pure functions, no solver state. The derivations and the numbered equations used in the comments are in
``BOX_BOX_MATHEMATICS.md``; the sources and what was verified from them are in ``BOX_BOX_REFERENCES.md``.

Contract (the same as ``narrow.Contact``):

- ``normal`` points from box A to box B, unit length.
- ``depth`` is the penetration along ``normal`` (positive = overlapping). Contacts with ``depth > -TOUCH_TOL`` are
  reported.
- ``feature`` is ``"face"`` (one point per surviving vertex of the clipped incident face) or ``"edge"`` (one point).
- ``point`` is the **midpoint of the overlap** along the normal (eq. 9 for faces, the midpoint of the closest pair for
  edges). It is not a point on one surface. The solver uses one point for both bodies, so the midpoint is the symmetric
  choice. This is the only contact in the kernel with that convention; ``Contact`` documents it.

Degenerate inputs are handled explicitly: near-parallel edge pairs are skipped (``PAR_SIN``), coincident centres use a
deterministic normal sign, and ties between candidate axes go to the lowest index. Nothing divides by a zero length.
"""

from __future__ import annotations

import math
import sys
from dataclasses import dataclass
from typing import List, Optional, Sequence, Tuple

from ..rigidbody import Mat3, Vec3, add, cross, dot, norm, scale, sub
from .narrow import REL_EPS, TOUCH_TOL, Contact, _canonical_sign

# Edge axes with sin(angle) below this are skipped. sqrt(eps) balances the rounding error of the normalised axis
# (about 2 eps / sin) against the error from skipping a thin facet (about sin); see BOX_BOX_MATHEMATICS.md section 2.
PAR_SIN = math.sqrt(sys.float_info.epsilon)

# A candidate edge axis must beat the best face axis by more than FACE_TIE * S to win (S = pair scale). Floating-point
# noise in a separation is about 1e-15 S, so this cannot flip between codes from rounding; see BOX_BOX_RESEARCH.md 3.3.
FACE_TIE = 1e-6


@dataclass(frozen=True)
class BoxSat:
    """Result of the 15-axis test. ``separation`` is s(u) of the winning candidate (eq. 2): positive = separated.
    ``depth = -separation`` is the penetration depth (eq. 4). ``normal`` is the winning axis oriented A -> B (eq. 5).
    ``kind`` is ``face_a``, ``face_b`` or ``edge``; ``index`` is ``(k,)`` for a face and ``(i, j)`` for an edge."""
    separated: bool
    separation: float
    depth: float
    kind: str
    index: Tuple[int, ...]
    normal: Vec3
    scale: float


def _axes(rot: Mat3) -> Tuple[Vec3, Vec3, Vec3]:
    """Body axes in world coordinates. ``rot`` maps body -> world (row-major), so axis k is column k."""
    return ((rot[0][0], rot[1][0], rot[2][0]),
            (rot[0][1], rot[1][1], rot[2][1]),
            (rot[0][2], rot[1][2], rot[2][2]))


def _support(axes: Sequence[Vec3], h: Sequence[float], u: Vec3) -> float:
    """Eq. (1): r(u) = sum_k h_k |e_k . u|."""
    return h[0] * abs(dot(axes[0], u)) + h[1] * abs(dot(axes[1], u)) + h[2] * abs(dot(axes[2], u))


def _sgn(x: float) -> float:
    return 1.0 if x >= 0.0 else -1.0


def _oriented(u: Vec3, d: Vec3, length_scale: float) -> Vec3:
    """Eq. (5): n = sgn(d . u) u, A -> B. When d . u is zero to REL_EPS * S, use the canonical sign."""
    p = dot(d, u)
    if abs(p) > REL_EPS * length_scale:
        return u if p > 0.0 else scale(u, -1.0)
    return _canonical_sign(u)


def _check_box(name: str, centre: Vec3, rot: Mat3, half: Vec3) -> None:
    vals = list(centre) + [x for row in rot for x in row] + list(half)
    if any(not math.isfinite(float(x)) for x in vals):
        raise ValueError(f"{name}: centre, rotation and half extents must be finite")
    if any(not float(h) > 0.0 for h in half):
        raise ValueError(f"{name}: box half extents must be > 0")


def box_box_sat(centre_a: Vec3, rot_a: Mat3, half_a: Vec3, centre_b: Vec3, rot_b: Mat3, half_b: Vec3) -> BoxSat:
    """Separating axis test over the 15 candidates (eqs. 1, 2, 4), with the face preference of section 2.

    Candidates in order: A0, A1, A2, B0, B1, B2, then edge pairs (i, j) in row-major order with ``sin < PAR_SIN``
    skipped. The best face candidate is the largest separation (lowest index on ties). An edge candidate wins only if
    its separation exceeds the best face separation by more than ``FACE_TIE * S``.
    """
    _check_box("box A", centre_a, rot_a, half_a)
    _check_box("box B", centre_b, rot_b, half_b)
    A = _axes(rot_a)
    B = _axes(rot_b)
    d = sub(centre_b, centre_a)
    length_scale = max(half_a) + max(half_b)

    def sep(u: Vec3) -> float:                              # eq. (2)
        return abs(dot(d, u)) - _support(A, half_a, u) - _support(B, half_b, u)

    best_face = None   # (s, kind, index, axis)
    for k in range(3):
        s = sep(A[k])
        if best_face is None or s > best_face[0]:
            best_face = (s, "face_a", (k,), A[k])
    for k in range(3):
        s = sep(B[k])
        if s > best_face[0]:
            best_face = (s, "face_b", (k,), B[k])

    best_edge = None
    for i in range(3):
        for j in range(3):
            x = cross(A[i], B[j])
            nx = norm(x)
            if not nx >= PAR_SIN:   # also catches NaN
                continue
            u = scale(x, 1.0 / nx)
            s = sep(u)
            if best_edge is None or s > best_edge[0]:
                best_edge = (s, "edge", (i, j), u)

    win = best_face
    if best_edge is not None and best_edge[0] - best_face[0] > FACE_TIE * length_scale:
        win = best_edge
    s_win, kind, index, axis = win
    return BoxSat(separated=s_win > TOUCH_TOL, separation=s_win, depth=-s_win, kind=kind, index=index,
                  normal=_oriented(axis, d, length_scale), scale=length_scale)


def _clip(poly: List[Vec3], g) -> List[Vec3]:
    """Sutherland-Hodgman clip of a convex polygon to {g(x) <= 0} for affine g. Crossings are interpolated (section 4.2)."""
    out: List[Vec3] = []
    n = len(poly)
    for idx in range(n):
        p = poly[idx]
        q = poly[(idx + 1) % n]
        gp = g(p)
        gq = g(q)
        if gp <= 0.0:
            out.append(p)
        if (gp < 0.0 < gq) or (gq < 0.0 < gp):
            t = gp / (gp - gq)
            out.append(add(p, scale(sub(q, p), t)))
    return out


def _face_contacts(sat: BoxSat, centre_a: Vec3, axes_a, half_a, centre_b: Vec3, axes_b, half_b) -> Tuple[List[Contact], Vec3]:
    n = sat.normal
    if sat.kind == "face_a":
        r_c, r_ax, r_h, i_c, i_ax, i_h = centre_a, axes_a, half_a, centre_b, axes_b, half_b
        nu = n
    else:
        r_c, r_ax, r_h, i_c, i_ax, i_h = centre_b, axes_b, half_b, centre_a, axes_a, half_a
        nu = scale(n, -1.0)
    k = sat.index[0]

    # Incident face (eq. 7): the face of I whose axis is most aligned with nu, lowest index on ties. Its outward normal
    # mu points back toward the reference box.
    m = max(range(3), key=lambda j: (abs(dot(nu, i_ax[j])), -j))
    mu = scale(i_ax[m], -_sgn(dot(nu, i_ax[m])))
    o1, o2 = [j for j in range(3) if j != m]
    # Corners of that face (eq. 8), in cyclic order so that the polygon is well formed for clipping.
    face_c = add(i_c, scale(mu, i_h[m]))
    poly = []
    for s1, s2 in ((-1.0, -1.0), (-1.0, 1.0), (1.0, 1.0), (1.0, -1.0)):
        poly.append(add(add(face_c, scale(i_ax[o1], s1 * i_h[o1])), scale(i_ax[o2], s2 * i_h[o2])))

    # Clip against the four side planes of the reference face footprint (section 4.2).
    p_ax, q_ax = [j for j in range(3) if j != k]
    for ax in (p_ax, q_ax):
        for sg in (1.0, -1.0):
            poly = _clip(poly, lambda x, ax=ax, sg=sg: sg * dot(sub(x, r_c), r_ax[ax]) - r_h[ax])
            if not poly:
                return [], (0.0, 0.0, 0.0)

    # Depth of each vertex below the reference face plane (eq. after 8), keep touching or penetrating points, merge
    # duplicates produced at polygon corners, and take the midpoint (eq. 9).
    length_scale = sat.scale
    # Friction anchor: the centroid of the midpoints of the whole clipped patch, before the touching filter. The
    # filter depends on tiny depths, so the set of kept corners can be asymmetric about the box centre; anchoring on
    # that set would put friction off the centre and create spurious yaw (see BOX_BOX_RESEARCH.md section 6).
    mids = [add(x, scale(nu, 0.5 * (r_h[k] - dot(sub(x, r_c), nu)))) for x in poly]
    anchor = scale(tuple(sum(m[i] for m in mids) for i in range(3)), 1.0 / len(mids))
    out: List[Contact] = []
    for x in poly:
        depth = r_h[k] - dot(sub(x, r_c), nu)
        if not depth >= -TOUCH_TOL:
            continue
        point = add(x, scale(nu, 0.5 * depth))
        if any(norm(sub(point, c.point)) < REL_EPS * length_scale for c in out):
            continue
        out.append(Contact(n, point, depth, "face"))
    return out, anchor


def _edge_contact(sat: BoxSat, centre_a: Vec3, axes_a, half_a, centre_b: Vec3, axes_b, half_b) -> Optional[Contact]:
    i, j = sat.index
    n = sat.normal
    # Supporting edge of A: parallel to axis i, at the corner that faces the normal (eq. in section 4.4).
    p0 = centre_a
    for k in range(3):
        if k != i:
            p0 = add(p0, scale(axes_a[k], _sgn(dot(n, axes_a[k])) * half_a[k]))
    # Supporting edge of B: parallel to axis j, at the corner that faces -n.
    q0 = centre_b
    for k in range(3):
        if k != j:
            q0 = add(q0, scale(axes_b[k], -_sgn(dot(n, axes_b[k])) * half_b[k]))

    u = axes_a[i]
    v = axes_b[j]
    w0 = sub(p0, q0)
    b = dot(u, v)
    denom = 1.0 - b * b
    dd = dot(u, w0)
    ee = dot(v, w0)
    ha = half_a[i]
    hb = half_b[j]

    def clamp(x: float, lim: float) -> float:
        return max(-lim, min(lim, x))

    # Minimise |w0 + s u - t v|^2 over the rectangle [-ha, ha] x [-hb, hb]. The minimum of this convex quadratic is at
    # the interior critical point or on one of the four sides (section 4.4). Candidates are evaluated in a fixed order.
    cands: List[Tuple[float, float]] = []
    if denom > 0.0:
        s = (b * ee - dd) / denom
        t = (ee - b * dd) / denom
        if abs(s) <= ha and abs(t) <= hb:
            cands.append((s, t))
    for s_fix in (-ha, ha):
        cands.append((s_fix, clamp(ee + b * s_fix, hb)))
    for t_fix in (-hb, hb):
        cands.append((clamp(b * t_fix - dd, ha), t_fix))

    def gap2(st: Tuple[float, float]) -> float:
        g = add(w0, sub(scale(u, st[0]), scale(v, st[1])))
        return dot(g, g)

    s, t = min(cands, key=gap2)
    p_star = add(p0, scale(u, s))
    q_star = add(q0, scale(v, t))
    point = scale(add(p_star, q_star), 0.5)
    return Contact(n, point, sat.depth, "edge")


def box_box_manifold(centre_a: Vec3, rot_a: Mat3, half_a: Vec3,
                     centre_b: Vec3, rot_b: Mat3, half_b: Vec3) -> Tuple[List[Contact], Optional[Vec3]]:
    """Contacts plus the friction anchor point. The anchor is None for an edge contact (its single point is the anchor)
    and for separated boxes; for a face manifold it is the centroid of the whole clipped patch (see ``_face_contacts``)."""
    sat = box_box_sat(centre_a, rot_a, half_a, centre_b, rot_b, half_b)
    if sat.separated:
        return [], None
    axes_a = _axes(rot_a)
    axes_b = _axes(rot_b)
    if sat.kind == "edge":
        ct = _edge_contact(sat, centre_a, axes_a, half_a, centre_b, axes_b, half_b)
        return ([] if ct is None else [ct]), None
    cts, anchor = _face_contacts(sat, centre_a, axes_a, half_a, centre_b, axes_b, half_b)
    return cts, anchor


def box_box_contacts(centre_a: Vec3, rot_a: Mat3, half_a: Vec3,
                     centre_b: Vec3, rot_b: Mat3, half_b: Vec3) -> List[Contact]:
    """All contacts between two oriented boxes. Empty if they are separated along any candidate axis.

    The result is a face manifold (1 to 8 points, ``feature == "face"``) or a single edge contact (``feature ==
    "edge"``). Normal: A -> B. See the module docstring for the conventions.
    """
    return box_box_manifold(centre_a, rot_a, half_a, centre_b, rot_b, half_b)[0]
