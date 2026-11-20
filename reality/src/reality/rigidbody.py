"""3D rigid-body dynamics (Phase 3).

State of a rigid body:
    r   position of the centre of mass, world frame (m)
    v   velocity of the centre of mass, world frame (m/s)
    q   unit quaternion (w, x, y, z) rotating body-frame vectors into the world frame
    w   angular velocity in the body frame (rad/s)

Equations of motion (principal axes, diagonal inertia I = diag(I1, I2, I3)):
    m dv/dt = F                          Newton's second law, world frame
    dr/dt   = v
    I dw/dt + w x (I w) = tau            Euler's equations, body frame
    dq/dt   = 1/2 q (x) (0, w)           body rates to quaternion rate

``rigid_derivative`` builds the right-hand side for ``integrators.rk4_step``.
The quaternion is renormalised after every step, so its norm stays at 1 up to
rounding. The module assumes principal axes; the inertia tensor is diagonal in
the body frame, as it is for every shape in ``objects.py``.

Not implemented here: joints, constraints other than the contacts in
``contact.py``, deformable bodies, continuous collision detection.
"""

from __future__ import annotations

import math
from dataclasses import dataclass
from typing import Callable, List, Optional, Sequence, Tuple

from .integrators import rk4_step

Vec3 = Tuple[float, float, float]
Quat = Tuple[float, float, float, float]
Mat3 = Tuple[Vec3, Vec3, Vec3]


# ----------------------------------------------------------------- vectors
def add(a: Sequence[float], b: Sequence[float]) -> Vec3:
    return (a[0] + b[0], a[1] + b[1], a[2] + b[2])


def sub(a: Sequence[float], b: Sequence[float]) -> Vec3:
    return (a[0] - b[0], a[1] - b[1], a[2] - b[2])


def scale(a: Sequence[float], s: float) -> Vec3:
    return (a[0] * s, a[1] * s, a[2] * s)


def dot(a: Sequence[float], b: Sequence[float]) -> float:
    return a[0] * b[0] + a[1] * b[1] + a[2] * b[2]


def cross(a: Sequence[float], b: Sequence[float]) -> Vec3:
    return (a[1] * b[2] - a[2] * b[1], a[2] * b[0] - a[0] * b[2], a[0] * b[1] - a[1] * b[0])


def norm(a: Sequence[float]) -> float:
    return math.sqrt(dot(a, a))


def mat_vec(m: Mat3, v: Sequence[float]) -> Vec3:
    return tuple(m[i][0] * v[0] + m[i][1] * v[1] + m[i][2] * v[2] for i in range(3))  # type: ignore[return-value]


def mat_t(m: Mat3) -> Mat3:
    return tuple(tuple(m[j][i] for j in range(3)) for i in range(3))  # type: ignore[return-value]


def mat_mul(a: Mat3, b: Mat3) -> Mat3:
    return tuple(  # type: ignore[return-value]
        tuple(sum(a[i][k] * b[k][j] for k in range(3)) for j in range(3)) for i in range(3)
    )


# -------------------------------------------------------------- quaternions
def quat_mul(a: Sequence[float], b: Sequence[float]) -> Quat:
    w1, x1, y1, z1 = a
    w2, x2, y2, z2 = b
    return (
        w1 * w2 - x1 * x2 - y1 * y2 - z1 * z2,
        w1 * x2 + x1 * w2 + y1 * z2 - z1 * y2,
        w1 * y2 - x1 * z2 + y1 * w2 + z1 * x2,
        w1 * z2 + x1 * y2 - y1 * x2 + z1 * w2,
    )


def quat_norm(q: Sequence[float]) -> float:
    """Euclidean norm of a quaternion (all four components). ``norm`` above is the 3-vector norm and must not be
    used on a quaternion: it ignores the scalar part."""
    return math.sqrt(sum(c * c for c in q))


def quat_normalize(q: Sequence[float]) -> Quat:
    n = math.sqrt(sum(c * c for c in q))
    if n == 0.0 or not math.isfinite(n):
        raise ValueError("cannot normalise a zero or non-finite quaternion")
    return (q[0] / n, q[1] / n, q[2] / n, q[3] / n)


def quat_to_matrix(q: Sequence[float]) -> Mat3:
    """Rotation matrix R such that world = R @ body."""
    w, x, y, z = q
    return (
        (1 - 2 * (y * y + z * z), 2 * (x * y - w * z), 2 * (x * z + w * y)),
        (2 * (x * y + w * z), 1 - 2 * (x * x + z * z), 2 * (y * z - w * x)),
        (2 * (x * z - w * y), 2 * (y * z + w * x), 1 - 2 * (x * x + y * y)),
    )


def quat_rotation_increment(omega_body: Sequence[float], h: float) -> Quat:
    """Exact rotation over time h for a constant body-frame angular velocity."""
    w_norm = norm(omega_body)
    if w_norm == 0.0:
        return (1.0, 0.0, 0.0, 0.0)
    half = 0.5 * w_norm * h
    s = math.sin(half) / w_norm
    return (math.cos(half), omega_body[0] * s, omega_body[1] * s, omega_body[2] * s)


# ------------------------------------------------------------------- body
@dataclass
class RigidBody:
    mass: float                       # kg
    inertia: Vec3                     # principal moments (kg m^2) about body x, y, z
    position: Vec3 = (0.0, 0.0, 0.0)  # m, world
    velocity: Vec3 = (0.0, 0.0, 0.0)  # m/s, world
    quaternion: Quat = (1.0, 0.0, 0.0, 0.0)
    omega: Vec3 = (0.0, 0.0, 0.0)     # rad/s, body frame

    def __post_init__(self) -> None:
        if not (math.isfinite(self.mass) and self.mass > 0.0):
            raise ValueError(f"mass must be finite and > 0, got {self.mass!r}")
        i1, i2, i3 = (float(x) for x in self.inertia)
        if not all(math.isfinite(x) and x > 0.0 for x in (i1, i2, i3)):
            raise ValueError("principal inertias must be finite and > 0")
        # Principal moments of a physical body satisfy the triangle inequalities.
        if not (i1 <= i2 + i3 and i2 <= i1 + i3 and i3 <= i1 + i2):
            raise ValueError("principal inertias violate the triangle inequality (not a physical body)")
        self.inertia = (i1, i2, i3)
        self.position = tuple(float(x) for x in self.position)  # type: ignore[assignment]
        self.velocity = tuple(float(x) for x in self.velocity)  # type: ignore[assignment]
        self.omega = tuple(float(x) for x in self.omega)  # type: ignore[assignment]
        self.quaternion = quat_normalize(self.quaternion)
        if len(self.position) != 3 or len(self.velocity) != 3 or len(self.omega) != 3:
            raise ValueError("position, velocity and omega must have 3 components")

    # ---------------------------------------------------------- state I/O
    def to_state(self) -> List[float]:
        return list(self.position) + list(self.velocity) + list(self.quaternion) + list(self.omega)

    def set_state(self, y: Sequence[float]) -> None:
        self.position = (y[0], y[1], y[2])
        self.velocity = (y[3], y[4], y[5])
        self.quaternion = quat_normalize(y[6:10])
        self.omega = (y[10], y[11], y[12])

    # ------------------------------------------------------------ derived
    def rotation(self) -> Mat3:
        return quat_to_matrix(self.quaternion)

    def inverse_inertia_world(self) -> Mat3:
        r = self.rotation()
        inv = [1.0 / i for i in self.inertia]
        d: Mat3 = ((inv[0], 0.0, 0.0), (0.0, inv[1], 0.0), (0.0, 0.0, inv[2]))
        return mat_mul(mat_mul(r, d), mat_t(r))

    def angular_velocity_world(self) -> Vec3:
        return mat_vec(self.rotation(), self.omega)

    def angular_momentum_body(self) -> Vec3:
        return tuple(self.inertia[i] * self.omega[i] for i in range(3))  # type: ignore[return-value]

    def angular_momentum_world(self) -> Vec3:
        return mat_vec(self.rotation(), self.angular_momentum_body())

    def kinetic_energy(self) -> float:
        t_lin = 0.5 * self.mass * dot(self.velocity, self.velocity)
        t_rot = 0.5 * sum(self.inertia[i] * self.omega[i] ** 2 for i in range(3))
        return t_lin + t_rot

    def point_velocity(self, offset_world: Sequence[float]) -> Vec3:
        """Velocity of a material point at offset (world frame) from the centre of mass."""
        return add(self.velocity, cross(self.angular_velocity_world(), offset_world))


# ------------------------------------------------------------- dynamics
ForceFn = Callable[[float, Sequence[float]], Sequence[float]]  # (t, state) -> F (world, N)
TorqueFn = Callable[[float, Sequence[float]], Sequence[float]]  # (t, state) -> tau (body, N m)


def rigid_derivative(mass: float, inertia: Vec3, force: Optional[ForceFn] = None,
                     torque: Optional[TorqueFn] = None) -> Callable[[float, Sequence[float]], List[float]]:
    """Right-hand side y' = f(t, y) for the 13-component rigid-body state."""

    def f(t: float, y: Sequence[float]) -> List[float]:
        v = (y[3], y[4], y[5])
        q = (y[6], y[7], y[8], y[9])
        w = (y[10], y[11], y[12])
        big_f = force(t, y) if force is not None else (0.0, 0.0, 0.0)
        tau = torque(t, y) if torque is not None else (0.0, 0.0, 0.0)
        acc = scale(big_f, 1.0 / mass)
        iw = tuple(inertia[i] * w[i] for i in range(3))
        gyro = cross(w, iw)  # w x (I w)
        dw = tuple((tau[i] - gyro[i]) / inertia[i] for i in range(3))
        dq = quat_mul(q, (0.0, w[0], w[1], w[2]))
        dq = (0.5 * dq[0], 0.5 * dq[1], 0.5 * dq[2], 0.5 * dq[3])
        return list(v) + list(acc) + list(dq) + list(dw)

    return f


def step_rk4(body: RigidBody, t: float, h: float, force: Optional[ForceFn] = None,
             torque: Optional[TorqueFn] = None) -> None:
    """Advance ``body`` by one RK4 step of size h (quaternion renormalised afterwards)."""
    if not h > 0.0:
        raise ValueError("time step must be > 0")
    f = rigid_derivative(body.mass, body.inertia, force, torque)
    y1 = rk4_step(f, t, body.to_state(), h)
    body.set_state(y1)


def integrate(body: RigidBody, t0: float, t_end: float, h: float, force: Optional[ForceFn] = None,
              torque: Optional[TorqueFn] = None) -> float:
    """Integrate with fixed steps h from t0 to t_end (last step shortened). Returns final time."""
    t = t0
    while t < t_end - 1e-15:
        step_h = min(h, t_end - t)
        step_rk4(body, t, step_h, force, torque)
        t += step_h
    return t


def exact_free_step(body: RigidBody, h: float) -> None:
    """Exact propagation of the attitude for torque-free motion over h (for checks and testing)."""
    body.quaternion = quat_normalize(quat_mul(body.quaternion, quat_rotation_increment(body.omega, h)))
