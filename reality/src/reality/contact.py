"""Rigid contact between a sphere and infinite planes (Phase 3).

Model: impulse-based, one contact point at a time, in the style of sequential-impulse
solvers (Baraff, SIGGRAPH 1989; Catto, GDC 2006). Neither source is yet in the SCIENCE_RESEARCH.md
verification ledger; see LIMITATIONS.md section 8.

Per time step h for a sphere of radius R and a plane {x : n . x = offset}:
  1. predict:  v <- v + g h,  x_pred <- x + v h
  2. detect:   gap = n . x_pred - offset - R; contact if gap < contact tolerance
  3. resolve (only if approaching, n . v_c < 0, at the contact point c = x - R n):
     a. normal impulse  J_n = -(1 + e) v_n / K_nn           (restitution e)
     b. tangential impulse J_t solving K_t J_t = -v_t        (sticking), clamped by
        the Coulomb cone |J_t| <= mu J_n; if the clamp is active the friction impulse
        is kinetic: J_t = -mu J_n (v_t / |v_t|)              (sliding)
     K is the 2x2 (or 1x1) effective-mass matrix of the contact point, including the
     rotational inertia of the body.
  4. move:     x <- x_pred (projected back onto the plane if penetrating),
               orientation <- exact rotation for the post-impulse angular velocity.

The sphere's inertia is isotropic, so K has the standard closed forms
K_nn = 1/m and K_tt = 1/m + R^2/I, with I the sphere's moment of inertia.

Limits: one contact point per body per step; planes only; no contact-manifold
reduction, no stacking-stability guarantees, no continuous collision detection.
A fast body can tunnel through a thin obstacle. Those are listed in LIMITATIONS.md.
"""

from __future__ import annotations

import math
from dataclasses import dataclass
from typing import List, Sequence, Tuple

from .rigidbody import (
    RigidBody, Vec3, add, cross, dot, mat_vec, norm, quat_mul, quat_normalize,
    quat_rotation_increment, scale, sub,
)

CONTACT_TOLERANCE = 1e-9  # m; gaps below this count as touching


@dataclass(frozen=True)
class Plane:
    """Half-space boundary {x : n . x = offset}; the free side is n . x > offset."""

    normal: Vec3
    offset: float = 0.0

    def __post_init__(self) -> None:
        n = norm(self.normal)
        if not (math.isfinite(n) and n > 0.0):
            raise ValueError("plane normal must be finite and non-zero")
        object.__setattr__(self, "normal", scale(self.normal, 1.0 / n))


def _tangent_basis(n: Vec3) -> Tuple[Vec3, Vec3]:
    # Pick the coordinate axis least aligned with n, then orthogonalise.
    a = (1.0, 0.0, 0.0) if abs(n[0]) < 0.9 else (0.0, 1.0, 0.0)
    t1 = cross(n, a)
    t1 = scale(t1, 1.0 / norm(t1))
    t2 = cross(n, t1)
    return t1, t2


def _apply_impulse(body: RigidBody, impulse: Vec3, r_c: Vec3, inv_i_world) -> None:
    """Change velocity and angular velocity of ``body`` by a contact impulse at offset r_c."""
    body.velocity = add(body.velocity, scale(impulse, 1.0 / body.mass))
    d_omega_world = mat_vec(inv_i_world, cross(r_c, impulse))
    omega_world = add(body.angular_velocity_world(), d_omega_world)
    # Store back in the body frame: omega_body = R^T omega_world.
    r = body.rotation()
    rt = tuple(tuple(r[j][i] for j in range(3)) for i in range(3))
    body.omega = mat_vec(rt, omega_world)  # type: ignore[assignment]


def _effective_mass(body: RigidBody, a: Vec3, b: Vec3, r_c: Vec3, inv_i_world) -> float:
    """a . (velocity change at the contact point per unit impulse along b)."""
    dv = add(scale(b, 1.0 / body.mass), cross(mat_vec(inv_i_world, cross(r_c, b)), r_c))
    return dot(a, dv)


def _resolve_plane(body: RigidBody, plane: Plane, radius: float, restitution: float,
                   friction: float, inv_i_world) -> None:
    n = plane.normal
    r_c = scale(n, -radius)  # from centre of mass to the contact point
    v_c = body.point_velocity(r_c)
    v_n = dot(v_c, n)
    if v_n >= 0.0:
        return  # separating or sliding without approach: no impulse
    k_nn = _effective_mass(body, n, n, r_c, inv_i_world)
    j_n = -(1.0 + restitution) * v_n / k_nn
    _apply_impulse(body, scale(n, j_n), r_c, inv_i_world)

    # Tangential (friction) impulse.
    v_c = body.point_velocity(r_c)
    v_t_vec = sub(v_c, scale(n, dot(v_c, n)))
    t1, t2 = _tangent_basis(n)
    vt = (dot(v_t_vec, t1), dot(v_t_vec, t2))
    k11 = _effective_mass(body, t1, t1, r_c, inv_i_world)
    k12 = _effective_mass(body, t1, t2, r_c, inv_i_world)
    k21 = _effective_mass(body, t2, t1, r_c, inv_i_world)
    k22 = _effective_mass(body, t2, t2, r_c, inv_i_world)
    det = k11 * k22 - k12 * k21
    if vt[0] == 0.0 and vt[1] == 0.0:
        return
    j1 = -(k22 * vt[0] - k12 * vt[1]) / det
    j2 = -(-k21 * vt[0] + k11 * vt[1]) / det
    max_friction = friction * j_n
    if math.hypot(j1, j2) <= max_friction:
        jt = add(scale(t1, j1), scale(t2, j2))  # sticking
    else:
        speed = math.hypot(vt[0], vt[1])
        jt = scale(add(scale(t1, vt[0]), scale(t2, vt[1])), -max_friction / speed)  # sliding
    _apply_impulse(body, jt, r_c, inv_i_world)


def step_sphere(body: RigidBody, h: float, gravity: Vec3, radius: float, planes: Sequence[Plane],
                restitution: float = 0.0, friction: float = 0.0) -> List[int]:
    """Advance a sphere under gravity and plane contacts by one time step h.

    ``body`` must have isotropic inertia equal to 2/5 m R^2 (a solid sphere). Returns the
    indices of the planes that were in contact in this step.
    """
    if not h > 0.0:
        raise ValueError("time step must be > 0")
    if not radius > 0.0:
        raise ValueError("radius must be > 0")
    if not (0.0 <= restitution <= 1.0):
        raise ValueError("restitution must lie in [0, 1]")
    if friction < 0.0:
        raise ValueError("friction must be >= 0")
    expected = 0.4 * body.mass * radius * radius
    if not all(math.isclose(i, expected, rel_tol=1e-9) for i in body.inertia):
        raise ValueError("step_sphere requires a solid sphere: inertia must equal 2/5 m R^2 about each axis")

    # 1. predict (contact detection uses the predicted position)
    x_old = body.position
    body.velocity = add(body.velocity, scale(gravity, h))
    x_pred = add(x_old, scale(body.velocity, h))

    # 2. detect contacts from the predicted gaps
    touching = [idx for idx, plane in enumerate(planes)
                if dot(plane.normal, x_pred) - plane.offset - radius < CONTACT_TOLERANCE]

    # 3. resolve impulses in plane order
    for idx in touching:
        _resolve_plane(body, planes[idx], radius, restitution, friction, body.inverse_inertia_world())

    # 4. move with the post-impulse velocity, then project out residual penetration
    x_new = add(x_old, scale(body.velocity, h))
    for idx in touching:
        plane = planes[idx]
        gap = dot(plane.normal, x_new) - plane.offset - radius
        if gap < 0.0:
            x_new = add(x_new, scale(plane.normal, -gap))
    body.position = x_new

    # 5. rotate with the post-impulse angular velocity (exact for constant omega over h)
    dq = quat_rotation_increment(body.omega, h)
    body.quaternion = quat_normalize(quat_mul(body.quaternion, dq))
    return touching
