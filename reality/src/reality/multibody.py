"""Multi-body contact for solid spheres: sphere-sphere and sphere-plane (PROJECT REALITY, Phase 3 extension).

Model. Each sphere is a rigid body with isotropic inertia I = 2/5 m R^2. Contacts are point contacts with a Coulomb
friction cone and a restitution coefficient, solved by projected Gauss-Seidel (sequential impulses) over all active
contacts. This is a sequential-impulse method. Its sources (Catto; Erleben) are NOT yet verified or listed in
SCIENCE_RESEARCH.md, so no citation is claimed here. Nothing here is a new equation: each impulse is the impulse that
makes the normal (or tangential) relative velocity at the contact take its target value, clamped by the normal impulse
(normal: non-negative accumulated impulse; friction: |lambda_t| <= mu lambda_n).

Per step h (same order as contact.step_sphere, which this reproduces exactly for one sphere on one plane):
  1. predict:  v <- v + g h,  x_pred <- x + v h
  2. detect:   plane gap n.x_pred - d - R < tol;  pair gap |x_b - x_a| - (R_a + R_b) < tol
  3. solve:    K iterations over contacts in list order (planes, then pairs). Normal target: -e v_n0 when approaching
               at the start of the solve, else 0. Friction: solve the 2x2 tangential system, then clamp to the cone.
  4. move:     x <- x + v h, then project out residual penetration (planes: all of the gap; pairs: split by inverse
               mass, so the lighter body moves more).
  5. rotate:   exact rotation for the post-impulse body-frame angular velocity.

Limits (also in LIMITATIONS.md): spheres only; one contact point per pair and per plane; no contact manifolds; no
continuous collision detection (a fast sphere can tunnel through a thin sphere); stacking is held by iteration count,
not by a warm start, so tall stacks drift. Momentum is conserved exactly by pair impulses; gravity and plane impulses
change momentum as expected. Energy is not conserved exactly: the discrete contact detection is first order in h.
"""

from __future__ import annotations

import math
from dataclasses import dataclass, field
from typing import List, Optional, Sequence, Tuple

from .contact import CONTACT_TOLERANCE, Plane, _tangent_basis
from .rigidbody import (
    Mat3, Quat, Vec3, add, cross, dot, mat_t, mat_vec, norm, quat_mul, quat_normalize,
    quat_rotation_increment, quat_to_matrix, scale, sub,
)

DEFAULT_ITERATIONS = 8


@dataclass
class Sphere:
    """A solid sphere. Body frame at the centre of mass; orientation quaternion body -> world."""

    name: str
    mass: float
    radius: float
    position: Vec3
    velocity: Vec3 = (0.0, 0.0, 0.0)
    quaternion: Quat = (1.0, 0.0, 0.0, 0.0)
    omega_body: Vec3 = (0.0, 0.0, 0.0)

    def __post_init__(self) -> None:
        if not (math.isfinite(self.mass) and self.mass > 0.0):
            raise ValueError(f"{self.name}: mass must be finite and > 0")
        if not (math.isfinite(self.radius) and self.radius > 0.0):
            raise ValueError(f"{self.name}: radius must be finite and > 0")

    @property
    def inertia(self) -> float:
        return 0.4 * self.mass * self.radius * self.radius

    @property
    def inv_mass(self) -> float:
        return 1.0 / self.mass

    @property
    def inv_inertia(self) -> float:
        return 1.0 / self.inertia

    def rotation(self) -> Mat3:
        return quat_to_matrix(self.quaternion)

    def omega_world(self) -> Vec3:
        return mat_vec(self.rotation(), self.omega_body)

    def point_velocity(self, offset_world: Vec3) -> Vec3:
        return add(self.velocity, cross(self.omega_world(), offset_world))

    def kinetic_energy(self) -> float:
        return 0.5 * self.mass * dot(self.velocity, self.velocity) + 0.5 * self.inertia * dot(self.omega_body, self.omega_body)


@dataclass(frozen=True)
class PlaneContact:
    """Sphere ``body`` (index) against plane ``plane`` (index into the planes list)."""

    body: int
    plane: int
    friction: float
    restitution: float


@dataclass(frozen=True)
class PairContact:
    """Sphere ``a`` against sphere ``b`` (indices). Friction and restitution are per pair."""

    a: int
    b: int
    friction: float
    restitution: float


@dataclass
class _Constraint:
    kind: str                    # "plane" or "pair"
    a: Optional[int]             # None for a plane (static side)
    b: int
    n: Vec3                      # plane: outward normal from the plane; pair: from a to b
    r_a: Vec3                    # contact offset from a's centre (zero for a plane)
    r_b: Vec3                    # contact offset from b's centre
    friction: float
    restitution: float
    t1: Vec3 = (0.0, 0.0, 0.0)
    t2: Vec3 = (0.0, 0.0, 0.0)
    k_nn: float = 0.0
    k_tt: Tuple[float, float, float, float] = (0.0, 0.0, 0.0, 0.0)  # K11, K12, K21, K22
    vn_target: float = 0.0
    lam_n: float = 0.0
    lam_t: List[float] = field(default_factory=lambda: [0.0, 0.0])


@dataclass(frozen=True)
class StepInfo:
    touching_planes: Tuple[Tuple[int, int], ...]   # (body, plane) pairs in contact this step
    touching_pairs: Tuple[Tuple[int, int], ...]    # (a, b) pairs in contact this step
    max_penetration: float                          # m, after projection


def _effect(c: _Constraint, bodies: Sequence[Sphere], d: Vec3, dp: Vec3) -> float:
    """d . (change of relative velocity at the contact per unit impulse dp, applied to b and -dp to a)."""
    b = bodies[c.b]
    out = add(scale(dp, b.inv_mass), scale(cross(cross(c.r_b, dp), c.r_b), b.inv_inertia))
    if c.a is not None:
        a = bodies[c.a]
        out = add(out, add(scale(dp, a.inv_mass), scale(cross(cross(c.r_a, dp), c.r_a), a.inv_inertia)))
    return dot(d, out)


def _rel_velocity(c: _Constraint, bodies: Sequence[Sphere]) -> Vec3:
    vb = bodies[c.b].point_velocity(c.r_b)
    if c.a is None:
        return vb
    return sub(vb, bodies[c.a].point_velocity(c.r_a))


def _apply(c: _Constraint, bodies: Sequence[Sphere], impulse_on_b: Vec3) -> None:
    """Apply impulse J to b and -J to a (if dynamic)."""
    b = bodies[c.b]
    b.velocity = add(b.velocity, scale(impulse_on_b, b.inv_mass))
    wb = add(b.omega_world(), scale(cross(c.r_b, impulse_on_b), b.inv_inertia))
    b.omega_body = mat_vec(mat_t(b.rotation()), wb)
    if c.a is not None:
        a = bodies[c.a]
        neg = scale(impulse_on_b, -1.0)
        a.velocity = add(a.velocity, scale(neg, a.inv_mass))
        wa = add(a.omega_world(), scale(cross(c.r_a, neg), a.inv_inertia))
        a.omega_body = mat_vec(mat_t(a.rotation()), wa)


def _build(bodies: Sequence[Sphere], planes: Sequence[Plane], contacts, xpred, touching_planes, touching_pairs):
    cons: List[_Constraint] = []
    for pi in touching_planes:
        pc = contacts[pi]
        body = bodies[pc.body]
        n = planes[pc.plane].normal
        r_b = scale(n, -body.radius)
        cons.append(_Constraint("plane", None, pc.body, n, (0.0, 0.0, 0.0), r_b, pc.friction, pc.restitution))
    for pi in touching_pairs:
        pc = contacts[pi]
        A, B = bodies[pc.a], bodies[pc.b]
        d = sub(xpred[pc.b], xpred[pc.a])
        dist = norm(d)
        if dist == 0.0:
            raise ValueError(f"spheres {pc.a} and {pc.b} have coincident centres; contact normal undefined")
        n = scale(d, 1.0 / dist)
        cons.append(_Constraint("pair", pc.a, pc.b, n, scale(n, A.radius), scale(n, -B.radius),
                                pc.friction, pc.restitution))
    for c in cons:
        t1, t2 = _tangent_basis(c.n)
        c.t1, c.t2 = t1, t2
        c.k_nn = _effect(c, bodies, c.n, c.n)
        k11 = _effect(c, bodies, t1, t1)
        k12 = _effect(c, bodies, t1, t2)
        k21 = _effect(c, bodies, t2, t1)
        k22 = _effect(c, bodies, t2, t2)
        c.k_tt = (k11, k12, k21, k22)
    return cons


def step_bodies(
    bodies: Sequence[Sphere],
    planes: Sequence[Plane],
    contacts: Sequence[object],
    h: float,
    gravity: Vec3,
    iterations: int = DEFAULT_ITERATIONS,
) -> StepInfo:
    """Advance all spheres by one step h. ``contacts`` is a list of PlaneContact and PairContact."""
    if not h > 0.0:
        raise ValueError("time step must be > 0")
    if iterations < 1:
        raise ValueError("iterations must be >= 1")
    for c in contacts:
        if isinstance(c, PlaneContact):
            if not (0.0 <= c.restitution <= 1.0 and c.friction >= 0.0):
                raise ValueError("plane contact: restitution in [0, 1] and friction >= 0 required")
        elif isinstance(c, PairContact):
            if not (0.0 <= c.restitution <= 1.0 and c.friction >= 0.0):
                raise ValueError("pair contact: restitution in [0, 1] and friction >= 0 required")
            if c.a == c.b:
                raise ValueError("a pair contact needs two different bodies")
        else:
            raise TypeError(f"unknown contact type {type(c).__name__}")

    # 1. predict
    x_old = [b.position for b in bodies]
    for b in bodies:
        b.velocity = add(b.velocity, scale(gravity, h))
    xpred = [add(x_old[i], scale(bodies[i].velocity, h)) for i in range(len(bodies))]

    # 2. detect
    touching_planes: List[int] = []
    touching_pairs: List[int] = []
    for ci, c in enumerate(contacts):
        if isinstance(c, PlaneContact):
            body, plane = bodies[c.body], planes[c.plane]
            if dot(plane.normal, xpred[c.body]) - plane.offset - body.radius < CONTACT_TOLERANCE:
                touching_planes.append(ci)
        else:
            A, B = bodies[c.a], bodies[c.b]
            gap = norm(sub(xpred[c.b], xpred[c.a])) - (A.radius + B.radius)
            if gap < CONTACT_TOLERANCE:
                touching_pairs.append(ci)

    # 3. solve (sequential impulses)
    cons = _build(bodies, planes, contacts, xpred, touching_planes, touching_pairs)
    for c in cons:
        vn0 = dot(_rel_velocity(c, bodies), c.n)
        c.vn_target = -c.restitution * vn0 if vn0 < 0.0 else 0.0
    for _ in range(iterations):
        for c in cons:
            # normal
            vn = dot(_rel_velocity(c, bodies), c.n)
            delta = (c.vn_target - vn) / c.k_nn
            new_lam = max(0.0, c.lam_n + delta)
            d_lam = new_lam - c.lam_n
            c.lam_n = new_lam
            if d_lam != 0.0:
                _apply(c, bodies, scale(c.n, d_lam))
            # friction
            if c.friction == 0.0 or c.lam_n == 0.0:
                continue
            v = _rel_velocity(c, bodies)
            vt0 = dot(v, c.t1)
            vt1 = dot(v, c.t2)
            k11, k12, k21, k22 = c.k_tt
            det = k11 * k22 - k12 * k21
            if det == 0.0:
                continue
            # solve K * delta = -vt
            dl0 = -(k22 * vt0 - k12 * vt1) / det
            dl1 = -(-k21 * vt0 + k11 * vt1) / det
            t0 = c.lam_t[0] + dl0
            t1 = c.lam_t[1] + dl1
            limit = c.friction * c.lam_n
            mag = math.hypot(t0, t1)
            if mag > limit:
                if mag == 0.0:
                    t0 = t1 = 0.0
                else:
                    s = limit / mag
                    t0 *= s
                    t1 *= s
            d0 = t0 - c.lam_t[0]
            d1 = t1 - c.lam_t[1]
            c.lam_t = [t0, t1]
            if d0 != 0.0 or d1 != 0.0:
                _apply(c, bodies, add(scale(c.t1, d0), scale(c.t2, d1)))

    # 4. move and project out residual penetration
    for i, b in enumerate(bodies):
        b.position = add(x_old[i], scale(b.velocity, h))
    for ci in touching_planes:
        pc = contacts[ci]
        body, plane = bodies[pc.body], planes[pc.plane]
        gap = dot(plane.normal, body.position) - plane.offset - body.radius
        if gap < 0.0:
            body.position = add(body.position, scale(plane.normal, -gap))
    for ci in touching_pairs:
        pc = contacts[ci]
        A, B = bodies[pc.a], bodies[pc.b]
        d = sub(B.position, A.position)
        dist = norm(d)
        pen = (A.radius + B.radius) - dist
        if pen > 0.0 and dist > 0.0:
            n = scale(d, 1.0 / dist)
            wa = A.inv_mass / (A.inv_mass + B.inv_mass)
            wb = 1.0 - wa
            A.position = add(A.position, scale(n, -pen * wa))
            B.position = add(B.position, scale(n, pen * wb))

    # 5. rotate
    for b in bodies:
        dq = quat_rotation_increment(b.omega_body, h)
        b.quaternion = quat_normalize(quat_mul(b.quaternion, dq))

    max_pen = 0.0
    for ci in touching_planes:
        pc = contacts[ci]
        body, plane = bodies[pc.body], planes[pc.plane]
        max_pen = max(max_pen, -(dot(plane.normal, body.position) - plane.offset - body.radius))
    for ci in touching_pairs:
        pc = contacts[ci]
        A, B = bodies[pc.a], bodies[pc.b]
        max_pen = max(max_pen, (A.radius + B.radius) - norm(sub(B.position, A.position)))
    return StepInfo(
        touching_planes=tuple((contacts[ci].body, contacts[ci].plane) for ci in touching_planes),
        touching_pairs=tuple((contacts[ci].a, contacts[ci].b) for ci in touching_pairs),
        max_penetration=max(0.0, max_pen),
    )


def total_momentum(bodies: Sequence[Sphere]) -> Vec3:
    p = (0.0, 0.0, 0.0)
    for b in bodies:
        p = add(p, scale(b.velocity, b.mass))
    return p


def total_kinetic_energy(bodies: Sequence[Sphere]) -> float:
    return sum(b.kinetic_energy() for b in bodies)
