"""General rigid-body step for spheres and boxes against planes, triangle meshes and other bodies.

This is an extension of ``multibody.step_bodies``, not a replacement. ``multibody.step_bodies`` is unchanged and still
used by schema v2. This module handles what it cannot: box bodies (tensor inertia), contact points that come from
geometry (box corners, triangle contacts), and several contact points per pair. For spheres against planes and
spheres against spheres it follows the same algorithm: predict, detect, sequential impulses with a Coulomb cone and
restitution, move, project out penetration, rotate. A regression test checks it against ``multibody.step_bodies``.

Per step (time step h, gravity g):
  1. predict   v <- v + g h (dynamic bodies),  x_pred <- x + v h
  2. detect    narrow phase at x_pred for every listed contact pair (activated if depth > -TOUCH_TOL)
  3. solve     one constraint per contact point. Offsets r_a, r_b are taken from x_pred. Normal impulses bring the
               approach velocity to -e v_n0 (or 0). Friction is the 2x2 tangential system, clamped to mu * lambda_n.
               Effective masses use the world inverse inertia tensor I^-1 = R diag(I_body^-1) R^T.
  4. move      x <- x + v h (dynamic bodies)
  5. project   narrow phase at the new positions; for each listed pair, the deepest point is pushed out along its
               normal (split by inverse mass for body-body pairs). Two passes.
  6. rotate    exact rotation for the post-impulse body-frame angular velocity.

Box-box pairs (Phase 7, ``box_box.py``) use the same constraint and projection machinery: their contact points are
ordinary contacts, and the solver does not treat them differently.

Limits (see COLLISION_GEOMETRY.md): no warm starting, no continuous collision detection, no box-mesh pairs, detection
uses the orientation at the start of the step, and the projection pushes out only the deepest point of each pair per pass.
"""

from __future__ import annotations

import math
from dataclasses import dataclass, field
from typing import List, Optional, Sequence, Tuple

from ..contact import Plane
from ..rigidbody import (
    Mat3, Quat, Vec3, add, cross, dot, mat_t, mat_vec, norm, quat_mul, quat_normalize,
    quat_rotation_increment, quat_to_matrix, scale, sub,
)
from .box_box import box_box_contacts, box_box_manifold
from .mesh import TriangleMesh
from .narrow import TOUCH_TOL, Contact, box_corners_plane, sphere_box, sphere_plane, sphere_sphere

DEFAULT_ITERATIONS = 8
BOX_MANIFOLD_ITERATIONS = 64   # minimum sweeps for a step with a box-plane or box-box pair. Measured (dt 1e-4..2e-4):
#                               8 sweeps leave ~0.2 rad/s of spurious spin on a landing; 16 leave 3e-2 rad/s at worst;
#                               32 leave 2e-7 rad/s at worst but lose a stack contact on 38 of 500 resting steps (the
#                               1 nm reporting threshold flickers); 64 reach 1e-16 and keep every contact. The cost is
#                               ~2 ms per box-plane step (16 sweeps: ~0.9 ms). See BOX_BOX_RESEARCH.md.
PROJECTION_PASSES = 10     # cap on position-projection passes per step (stacks converge in a few)
PROJECTION_TOL = 1e-12      # m; depths below this are float rounding of positions of order 1 m (metres)
PAIR_KINDS = ("sphere_sphere", "sphere_box", "sphere_plane", "box_plane", "sphere_mesh", "box_box")


@dataclass
class Body:
    """A sphere or box. ``static`` bodies have infinite mass: they are never moved and carry zero velocity."""
    name: str
    kind: str                      # "sphere" or "box"
    mass: float                    # kg (ignored for static bodies)
    position: Vec3 = (0.0, 0.0, 0.0)
    velocity: Vec3 = (0.0, 0.0, 0.0)
    quaternion: Quat = (1.0, 0.0, 0.0, 0.0)
    omega_body: Vec3 = (0.0, 0.0, 0.0)
    radius: float = 0.0            # sphere
    half: Vec3 = (0.0, 0.0, 0.0)   # box half edge lengths along body axes
    static: bool = False
    inertia_body: Vec3 = field(init=False, default=(0.0, 0.0, 0.0))

    def __post_init__(self) -> None:
        if self.kind not in ("sphere", "box"):
            raise ValueError(f"{self.name}: kind must be 'sphere' or 'box'")
        if self.kind == "sphere":
            if not (math.isfinite(self.radius) and self.radius > 0.0):
                raise ValueError(f"{self.name}: radius must be finite and > 0")
        else:
            if any(not (math.isfinite(h) and h > 0.0) for h in self.half):
                raise ValueError(f"{self.name}: box half extents must be finite and > 0")
        if self.static:
            self.velocity = (0.0, 0.0, 0.0)
            self.omega_body = (0.0, 0.0, 0.0)
            self.inertia_body = (0.0, 0.0, 0.0)
            return
        if not (math.isfinite(self.mass) and self.mass > 0.0):
            raise ValueError(f"{self.name}: mass must be finite and > 0")
        m = self.mass
        if self.kind == "sphere":
            i = 0.4 * m * self.radius * self.radius
            self.inertia_body = (i, i, i)
        else:
            hx, hy, hz = self.half
            # solid box, full edges a = 2 hx, b = 2 hy, c = 2 hz: I_x = m (b^2 + c^2) / 12 = m (hy^2 + hz^2) / 3
            self.inertia_body = (m * (hy * hy + hz * hz) / 3.0, m * (hx * hx + hz * hz) / 3.0,
                                 m * (hx * hx + hy * hy) / 3.0)

    @property
    def inv_mass(self) -> float:
        return 0.0 if self.static else 1.0 / self.mass

    @property
    def rotation(self) -> Mat3:
        return quat_to_matrix(self.quaternion)

    def inv_inertia_world(self) -> Mat3:
        if self.static:
            return ((0.0, 0.0, 0.0), (0.0, 0.0, 0.0), (0.0, 0.0, 0.0))
        r = self.rotation
        d = [1.0 / i for i in self.inertia_body]
        # R diag(d) R^T
        return tuple(tuple(sum(r[i][k] * d[k] * r[j][k] for k in range(3)) for j in range(3)) for i in range(3))

    def omega_world(self) -> Vec3:
        return mat_vec(self.rotation, self.omega_body)

    def point_velocity(self, r: Vec3) -> Vec3:
        return add(self.velocity, cross(self.omega_world(), r))

    def kinetic_energy(self) -> float:
        if self.static:
            return 0.0
        iw = self.inertia_body
        return 0.5 * self.mass * dot(self.velocity, self.velocity) + 0.5 * sum(
            iw[k] * self.omega_body[k] ** 2 for k in range(3))


@dataclass(frozen=True)
class PairSpec:
    """One listed contact pair. ``a`` is None for a static shape (plane or mesh). Normal convention: a -> b."""
    kind: str
    a: Optional[int]
    b: int
    friction: float
    restitution: float
    shape: object = None   # Plane (sphere_plane, box_plane) or TriangleMesh (sphere_mesh)


@dataclass(frozen=True)
class StepInfo:
    touching: Tuple[int, ...]       # indices into the spec list active this step
    max_penetration: float


@dataclass
class _Con:
    spec: int
    a: Optional[int]
    b: int
    n: Vec3
    r_a: Vec3
    r_b: Vec3
    friction: float
    restitution: float
    t1: Vec3 = (0.0, 0.0, 0.0)
    t2: Vec3 = (0.0, 0.0, 0.0)
    k_nn: float = 0.0
    k_tt: Tuple[float, float, float, float] = (0.0, 0.0, 0.0, 0.0)
    vn_target: float = 0.0
    lam_n: float = 0.0
    lam_t: List[float] = field(default_factory=lambda: [0.0, 0.0])
    # Friction anchor (box-box manifolds with >= 2 points only): a tangential-only constraint at the manifold centroid
    # whose Coulomb limit is mu * (sum of the group's normal impulses). ``group`` holds the group's normal constraints.
    group: Optional[List["_Con"]] = None


def _tangent_basis(n: Vec3) -> Tuple[Vec3, Vec3]:
    base = (1.0, 0.0, 0.0) if abs(n[0]) < 0.9 else (0.0, 1.0, 0.0)
    t1 = cross(n, base)
    t1 = scale(t1, 1.0 / norm(t1))
    t2 = cross(n, t1)
    return t1, t2


def _detect(bodies: Sequence[Body], spec: PairSpec, pos: Sequence[Vec3]) -> List[Contact]:
    """Narrow phase for one spec with the given positions (orientations are the bodies' current ones)."""
    b = bodies[spec.b]
    if spec.kind == "sphere_plane":
        pl: Plane = spec.shape
        ct = sphere_plane(pos[spec.b], b.radius, pl.normal, pl.offset)
        return [] if ct is None else [ct]
    if spec.kind == "box_plane":
        pl = spec.shape
        return box_corners_plane(pos[spec.b], b.rotation, b.half, pl.normal, pl.offset)
    if spec.kind == "sphere_mesh":
        mesh: TriangleMesh = spec.shape
        prefer = None if b.velocity == (0.0, 0.0, 0.0) else scale(b.velocity, -1.0)
        return mesh.sphere_contacts(pos[spec.b], b.radius, prefer)
    if spec.kind == "sphere_sphere":
        a = bodies[spec.a]
        ct = sphere_sphere(pos[spec.a], a.radius, pos[spec.b], b.radius)
        return [] if ct is None else [ct]
    if spec.kind == "sphere_box":
        box = bodies[spec.a]
        ct = sphere_box(pos[spec.b], b.radius, pos[spec.a], box.rotation, box.half)
        return [] if ct is None else [ct]
    if spec.kind == "box_box":
        # Phase 7: 15-axis SAT, face manifolds by clipping, edge contacts. Centres from ``pos``, orientations from the
        # bodies (orientation is updated only in step 6, as for every other pair kind).
        a = bodies[spec.a]
        return box_box_contacts(pos[spec.a], a.rotation, a.half, pos[spec.b], b.rotation, b.half)
    raise ValueError(f"unknown pair kind {spec.kind!r}")


def _box_box_anchor(bodies: Sequence[Body], spec: PairSpec, pos: Sequence[Vec3]) -> Optional[Vec3]:
    """Friction anchor of a box-box pair at ``pos`` (centroid of the whole clipped patch; None for an edge contact)."""
    a = bodies[spec.a]
    b = bodies[spec.b]
    return box_box_manifold(pos[spec.a], a.rotation, a.half, pos[spec.b], b.rotation, b.half)[1]


def contacts_now(bodies: Sequence[Body], specs: Sequence[PairSpec]) -> List[Tuple[int, List[Contact]]]:
    """Narrow phase at the current positions (no time step). Returns (spec index, contacts) for each spec that
    has at least one touching contact."""
    out = []
    for si, s in enumerate(specs):
        cts = [c for c in _detect(bodies, s, [b.position for b in bodies]) if c.depth > -TOUCH_TOL]
        if cts:
            out.append((si, cts))
    return out


def _effect(c: _Con, bodies: Sequence[Body], iw: Sequence[Mat3], d: Vec3, dp: Vec3) -> float:
    """d . (change of relative normal/tangent velocity per unit impulse dp applied to b and -dp to a)."""
    # relative velocity change v_b - v_a per unit impulse dp (applied to b, and -dp to a)
    b = bodies[c.b]
    out = add(scale(dp, b.inv_mass), cross(mat_vec(iw[c.b], cross(c.r_b, dp)), c.r_b))
    if c.a is not None:
        a = bodies[c.a]
        out = add(out, add(scale(dp, a.inv_mass), cross(mat_vec(iw[c.a], cross(c.r_a, dp)), c.r_a)))
    return dot(d, out)


def _rel_velocity(c: _Con, bodies: Sequence[Body]) -> Vec3:
    vb = bodies[c.b].point_velocity(c.r_b)
    if c.a is None:
        return vb
    return sub(vb, bodies[c.a].point_velocity(c.r_a))


def _apply(c: _Con, bodies: Sequence[Body], iw: Sequence[Mat3], impulse_on_b: Vec3) -> None:
    b = bodies[c.b]
    if not b.static:
        b.velocity = add(b.velocity, scale(impulse_on_b, b.inv_mass))
        wb = add(b.omega_world(), mat_vec(iw[c.b], cross(c.r_b, impulse_on_b)))
        b.omega_body = mat_vec(mat_t(b.rotation), wb)
    if c.a is not None:
        a = bodies[c.a]
        if not a.static:
            neg = scale(impulse_on_b, -1.0)
            a.velocity = add(a.velocity, scale(neg, a.inv_mass))
            wa = add(a.omega_world(), mat_vec(iw[c.a], cross(c.r_a, neg)))
            a.omega_body = mat_vec(mat_t(a.rotation), wa)


def _gyro_rate(w: Vec3, inertia: Vec3) -> Vec3:
    """dw/dt for a torque-free body with principal inertia (body frame): -(w x I w) / I (Euler's equations)."""
    iw = (inertia[0] * w[0], inertia[1] * w[1], inertia[2] * w[2])
    g = cross(w, iw)
    return (-g[0] / inertia[0], -g[1] / inertia[1], -g[2] / inertia[2])


def _free_rotation_rates(w0: Vec3, inertia: Vec3, h: float) -> Tuple[Vec3, Vec3]:
    """Body-frame angular velocity over a torque-free step h. Returns (midpoint rate, end rate).

    Isotropic inertia has no gyroscopic term, so the rate is returned unchanged (exact). Otherwise two RK4 half-steps
    advance Euler's equations; the midpoint rate is used for the exact rotation increment (second order in h).
    Measured against a fine-step RK4 reference in BOX_BOX_RESEARCH.md (the constant-rate solver was off by ~1 rad/s).
    """
    if inertia[0] == inertia[1] == inertia[2]:
        return w0, w0
    half = 0.5 * h

    def rk4(w: Vec3, dt: float) -> Vec3:
        k1 = _gyro_rate(w, inertia)
        k2 = _gyro_rate(add(w, scale(k1, 0.5 * dt)), inertia)
        k3 = _gyro_rate(add(w, scale(k2, 0.5 * dt)), inertia)
        k4 = _gyro_rate(add(w, scale(k3, dt)), inertia)
        return tuple(w[i] + dt / 6.0 * (k1[i] + 2.0 * k2[i] + 2.0 * k3[i] + k4[i]) for i in range(3))  # type: ignore[return-value]

    w_mid = rk4(w0, half)
    w_end = rk4(w_mid, half)
    return w_mid, w_end


def step(bodies: Sequence[Body], specs: Sequence[PairSpec], h: float, gravity: Vec3,
         iterations: int = DEFAULT_ITERATIONS) -> StepInfo:
    """Advance all bodies by one step h. ``specs`` are the listed contact pairs (their order matters: it is the
    solver's constraint order)."""
    if not h > 0.0:
        raise ValueError("time step must be > 0")
    if iterations < 1:
        raise ValueError("iterations must be >= 1")
    for s in specs:
        if s.kind not in PAIR_KINDS:
            raise ValueError(f"unsupported pair kind {s.kind!r}")
        if not (0.0 <= s.restitution <= 1.0 and s.friction >= 0.0):
            raise ValueError("contact: restitution in [0, 1] and friction >= 0 required")

    # 1. predict
    x_old = [b.position for b in bodies]
    for b in bodies:
        if not b.static:
            b.velocity = add(b.velocity, scale(gravity, h))
    xpred = [add(x_old[i], scale(bodies[i].velocity, h)) for i in range(len(bodies))]

    # 2. detect
    active: List[Tuple[int, List[Contact]]] = []
    for si, s in enumerate(specs):
        cts = [c for c in _detect(bodies, s, xpred) if c.depth > -TOUCH_TOL]
        if cts:
            active.append((si, cts))

    # 3. solve. Multi-point box manifolds couple their normal constraints through the body's rotation; Gauss-Seidel
    #    needs about 64 sweeps to converge there (see BOX_MANIFOLD_ITERATIONS). Sphere-only steps keep ``iterations``.
    if any(s.kind in ("box_plane", "box_box") for s in specs):
        iterations = max(iterations, BOX_MANIFOLD_ITERATIONS)
    iw = [b.inv_inertia_world() for b in bodies]
    cons: List[_Con] = []
    for si, cts in active:
        s = specs[si]
        anchored = s.kind == "box_box" and len(cts) >= 2
        group: List[_Con] = []
        for ct in cts:
            r_a = (0.0, 0.0, 0.0) if s.a is None else sub(ct.point, xpred[s.a])
            r_b = sub(ct.point, xpred[s.b])
            # with an anchor, the per-point constraints are normal-only (friction is the anchor's)
            group.append(_Con(si, s.a, s.b, ct.normal, r_a, r_b, 0.0 if anchored else s.friction, s.restitution))
        cons.extend(group)
        if anchored:
            # One friction anchor per manifold at the centroid (see _Con.group). Per-point friction limits are not
            # used here: the rigid patch's normal impulses are indeterminate (rank 3 for 4 points), so per-point
            # limits let the uneven split create spurious yaw.
            cen = _box_box_anchor(bodies, s, xpred)
            if cen is None:
                cen = scale(tuple(sum(ct.point[i] for ct in cts) for i in range(3)), 1.0 / len(cts))
            n0 = cts[0].normal
            r_a = (0.0, 0.0, 0.0) if s.a is None else sub(cen, xpred[s.a])
            r_b = sub(cen, xpred[s.b])
            cons.append(_Con(si, s.a, s.b, n0, r_a, r_b, s.friction, s.restitution, group=group))
    for c in cons:
        c.t1, c.t2 = _tangent_basis(c.n)
        c.k_nn = _effect(c, bodies, iw, c.n, c.n)
        k11 = _effect(c, bodies, iw, c.t1, c.t1)
        k12 = _effect(c, bodies, iw, c.t1, c.t2)
        k21 = _effect(c, bodies, iw, c.t2, c.t1)
        k22 = _effect(c, bodies, iw, c.t2, c.t2)
        c.k_tt = (k11, k12, k21, k22)
    for c in cons:
        if c.group is not None:
            continue
        vn0 = dot(_rel_velocity(c, bodies), c.n)
        c.vn_target = -c.restitution * vn0 if vn0 < 0.0 else 0.0
    for _ in range(iterations):
        for c in cons:
            if c.group is None:
                vn = dot(_rel_velocity(c, bodies), c.n)
                delta = (c.vn_target - vn) / c.k_nn
                new_lam = max(0.0, c.lam_n + delta)
                d_lam = new_lam - c.lam_n
                c.lam_n = new_lam
                if d_lam != 0.0:
                    _apply(c, bodies, iw, scale(c.n, d_lam))
            else:
                c.lam_n = sum(g.lam_n for g in c.group)
            if c.friction == 0.0 or c.lam_n == 0.0:
                continue
            v = _rel_velocity(c, bodies)
            vt0 = dot(v, c.t1)
            vt1 = dot(v, c.t2)
            k11, k12, k21, k22 = c.k_tt
            det = k11 * k22 - k12 * k21
            if det == 0.0:
                continue
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
                    sc = limit / mag
                    t0 *= sc
                    t1 *= sc
            d0 = t0 - c.lam_t[0]
            d1 = t1 - c.lam_t[1]
            c.lam_t = [t0, t1]
            if d0 != 0.0 or d1 != 0.0:
                _apply(c, bodies, iw, add(scale(c.t1, d0), scale(c.t2, d1)))

    # 4. move
    for i, b in enumerate(bodies):
        if not b.static:
            b.position = add(x_old[i], scale(b.velocity, h))

    # 5. rotate (before the projection: a box's other corners move when it turns, so the final projection must run last).
    #    Asymmetric bodies precess: Euler's equations with the gyroscopic term change the body-frame angular velocity
    #    over the step. Isotropic bodies (spheres, cubes) have no such term and keep the exact constant-rate increment.
    for b in bodies:
        if not b.static:
            w_mid, w_end = _free_rotation_rates(b.omega_body, b.inertia_body, h)
            dq = quat_rotation_increment(w_mid, h)
            b.quaternion = quat_normalize(quat_mul(b.quaternion, dq))
            b.omega_body = w_end

    # 6. project out penetration. Each pass pushes out the deepest point of every listed pair. Every listed pair is
    #    checked, not only the ones active at the predicted state: a body can move into a pair that was clear. Passes
    #    repeat (at most PROJECTION_PASSES) while some pair is deeper than PROJECTION_TOL; stacks need more than two.
    for _pass in range(PROJECTION_PASSES):
        worst = 0.0
        for si in range(len(specs)):
            s = specs[si]
            deepest = None
            for ct in _detect(bodies, s, [b.position for b in bodies]):
                if deepest is None or ct.depth > deepest.depth:
                    deepest = ct
            if deepest is None or deepest.depth <= PROJECTION_TOL:
                continue
            worst = max(worst, deepest.depth)
            push = scale(deepest.normal, deepest.depth)
            if s.a is None:
                b = bodies[s.b]
                if not b.static:
                    b.position = sub(b.position, scale(push, -1.0))
            else:
                A, B = bodies[s.a], bodies[s.b]
                wsum = A.inv_mass + B.inv_mass
                if wsum == 0.0:
                    continue
                wa = A.inv_mass / wsum
                wb = 1.0 - wa
                if not A.static:
                    A.position = add(A.position, scale(push, -wa))
                if not B.static:
                    B.position = add(B.position, scale(push, wb))
        if worst == 0.0:
            break

    # penetration after the step, over every listed pair
    max_pen = 0.0
    for s in specs:
        for ct in _detect(bodies, s, [b.position for b in bodies]):
            max_pen = max(max_pen, ct.depth)
    return StepInfo(touching=tuple(si for si, _ in active), max_penetration=max(0.0, max_pen))


def total_momentum(bodies: Sequence[Body]) -> Vec3:
    p = (0.0, 0.0, 0.0)
    for b in bodies:
        if not b.static:
            p = add(p, scale(b.velocity, b.mass))
    return p


def total_kinetic_energy(bodies: Sequence[Body]) -> float:
    return sum(b.kinetic_energy() for b in bodies)
