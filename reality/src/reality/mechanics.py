"""Classical particle mechanics: free fall, drag, projectiles, pendulum, collisions, orbits.

Each solver is paired with an analytic or textbook reference in ``validation.py``.
Equations and assumptions are documented in ``reality/PHYSICS_MODELS.md``.
"""

from __future__ import annotations

import math
from typing import List, Sequence, Tuple

from . import constants as C
from .integrators import integrate_rk4, velocity_verlet_step


# ----------------------------------------------------------------- free fall ---
def quadratic_drag_coefficient(density_fluid: float, drag_coeff: float, area: float) -> float:
    """k in F_drag = k v^2, k = 1/2 rho C_d A (kg/m). Standard fluid-drag model."""
    if min(density_fluid, drag_coeff, area) < 0:
        raise ValueError("density, drag coefficient and area must be non-negative")
    return 0.5 * density_fluid * drag_coeff * area


def terminal_velocity(mass: float, g: float, k: float) -> float:
    """Quadratic-drag terminal speed v_t = sqrt(m g / k)."""
    if k <= 0:
        raise ValueError("drag coefficient k must be positive for a terminal velocity")
    return math.sqrt(mass * g / k)


def log_cosh(x: float) -> float:
    """Numerically stable ln(cosh x).

    Small |x|: ln cosh x = log1p(2 sinh^2(x/2)), avoiding the cancellation of ln(cosh x)
    where cosh x rounds to 1. Large |x|: |x| - ln 2 + log1p(exp(-2|x|)), avoiding overflow.
    """
    ax = abs(x)
    if ax < 20.0:
        return math.log1p(2.0 * math.sinh(0.5 * ax) ** 2)
    return ax - math.log(2.0) + math.log1p(math.exp(-2.0 * ax))


def freefall_quadratic_drag_analytic(t: float, mass: float, g: float, k: float) -> Tuple[float, float]:
    """Exact (speed, distance fallen) at time t for a body released from rest with F_d = k v^2.

    v(t)   = v_t tanh(g t / v_t)
    y(t)   = (v_t^2 / g) ln cosh(g t / v_t)
    """
    vt = terminal_velocity(mass, g, k)
    s = g * t / vt
    return vt * math.tanh(s), (vt * vt / g) * log_cosh(s)


def freefall_quadratic_drag_numeric(
    t_end: float, mass: float, g: float, k: float, dt: float
) -> Tuple[float, float]:
    """Numerically integrate the same problem with RK4. Returns (speed, distance fallen)."""

    def f(_t: float, y: List[float]) -> List[float]:
        v, _s = y
        # Downward positive. Drag opposes motion: a = g - (k/m) v |v|.
        return [g - (k / mass) * v * abs(v), v]

    v, s = integrate_rk4(f, 0.0, [0.0, 0.0], t_end, dt)
    return v, s


# --------------------------------------------------------------- projectile ---
def projectile_no_drag(v0: float, angle_rad: float, g: float, t: float) -> Tuple[float, float]:
    """Position (x, y) of a projectile launched from the origin with no air drag."""
    vx = v0 * math.cos(angle_rad)
    vy = v0 * math.sin(angle_rad)
    return vx * t, vy * t - 0.5 * g * t * t


def projectile_range_no_drag(v0: float, angle_rad: float, g: float) -> float:
    """Horizontal range on level ground: R = v0^2 sin(2 theta) / g."""
    return v0 * v0 * math.sin(2.0 * angle_rad) / g


def projectile_max_height_no_drag(v0: float, angle_rad: float, g: float) -> float:
    return (v0 * math.sin(angle_rad)) ** 2 / (2.0 * g)


def projectile_numeric(
    v0: float, angle_rad: float, g: float, dt: float
) -> Tuple[float, float, float]:
    """Velocity-Verlet integration of a drag-free projectile.

    Returns (range, max height, time of flight). Time of flight and range are found by
    linear interpolation at the ground crossing.
    """
    x = [0.0, 0.0]
    v = [v0 * math.cos(angle_rad), v0 * math.sin(angle_rad)]

    def accel(_x: Sequence[float]) -> List[float]:
        return [0.0, -g]

    t = 0.0
    h_max = 0.0
    while True:
        x_new, v_new = velocity_verlet_step(accel, x, v, dt)
        t_new = t + dt
        h_max = max(h_max, x_new[1])
        if x_new[1] <= 0.0 and t > 0.0:
            frac = x[1] / (x[1] - x_new[1]) if x[1] != x_new[1] else 0.0
            tof = t + frac * dt
            rng = x[0] + frac * (x_new[0] - x[0])
            return rng, h_max, tof
        x, v, t = x_new, v_new, t_new
        if t > 1e6:
            raise RuntimeError("projectile did not land")


# ------------------------------------------------------------------ pendulum ---
def agm(a: float, b: float, tol: float = 1e-15) -> float:
    """Arithmetic-geometric mean (used for the complete elliptic integral K)."""
    for _ in range(200):
        a1, b1 = 0.5 * (a + b), math.sqrt(a * b)
        if abs(a1 - b1) <= tol * a1:
            return a1
        a, b = a1, b1
    return a


def complete_elliptic_k(m: float) -> float:
    """Complete elliptic integral of the first kind K(m), parameter m = k^2, via the AGM.

    K(m) = pi / (2 AGM(1, sqrt(1 - m))).  Abramowitz & Stegun 17.6.
    """
    if not 0.0 <= m < 1.0:
        raise ValueError("m must be in [0, 1)")
    return math.pi / (2.0 * agm(1.0, math.sqrt(1.0 - m)))


def pendulum_period_exact(length: float, g: float, amplitude_rad: float) -> float:
    """Exact period of a simple pendulum: T = 4 K(k) / omega0, k = sin(theta0/2).

    Landau & Lifshitz, Mechanics, Sec. 48.
    """
    if not 0.0 <= amplitude_rad < math.pi:
        raise ValueError("amplitude must be in [0, pi)")
    omega0 = math.sqrt(g / length)
    k = math.sin(0.5 * amplitude_rad)
    return 4.0 * complete_elliptic_k(k * k) / omega0


def pendulum_period_small_angle(length: float, g: float) -> float:
    return 2.0 * math.pi * math.sqrt(length / g)


def pendulum_period_numeric(length: float, g: float, amplitude_rad: float, dt: float) -> float:
    """Period measured from RK4 integration: time between two successive upward zero crossings
    of theta (after the first half-period), linearly interpolated. Used to validate the exact formula.
    """

    def f(_t: float, y: List[float]) -> List[float]:
        th, om = y
        return [om, -(g / length) * math.sin(th)]

    th, om = amplitude_rad, 0.0
    t = 0.0
    crossings: List[float] = []
    prev_th = th
    while len(crossings) < 2:
        y_new = integrate_rk4(f, t, [th, om], t + dt, dt)
        t_new = t + dt
        th_new = y_new[0]
        if prev_th > 0.0 and th_new <= 0.0 and t > 0:
            frac = prev_th / (prev_th - th_new)
            crossings.append(t + frac * dt)
        prev_th = th_new
        th, om, t = y_new[0], y_new[1], t_new
        if t > 1e4:
            raise RuntimeError("pendulum did not oscillate")
    # Two successive downward crossings of zero are one full period.
    return crossings[1] - crossings[0]


# ----------------------------------------------------------------- collisions ---
def collide_1d(m1: float, v1: float, m2: float, v2: float, restitution: float = 1.0) -> Tuple[float, float]:
    """Central 1D collision with coefficient of restitution e (0 <= e <= 1).

    Momentum is conserved exactly; the relative velocity satisfies v2' - v1' = -e (v2 - v1).
    e = 1 is elastic (kinetic energy conserved), e = 0 is perfectly inelastic.
    """
    if m1 <= 0 or m2 <= 0:
        raise ValueError("masses must be positive")
    if not 0.0 <= restitution <= 1.0:
        raise ValueError("restitution must be in [0, 1]")
    p = m1 * v1 + m2 * v2
    v1p = (p - m2 * restitution * (v1 - v2)) / (m1 + m2)
    v2p = v1p + restitution * (v1 - v2)
    return v1p, v2p


def kinetic_energy(m: float, v: float) -> float:
    return 0.5 * m * v * v


# -------------------------------------------------------------------- orbits ---
def kepler_orbit_verlet(
    gm: float, r0: Sequence[float], v0: Sequence[float], dt: float, n_steps: int
) -> Tuple[List[List[float]], List[List[float]]]:
    """Integrate a two-body orbit with velocity Verlet. Returns (positions, velocities) histories."""

    def accel(x: Sequence[float]) -> List[float]:
        r = math.sqrt(x[0] * x[0] + x[1] * x[1])
        k = -gm / (r ** 3)
        return [k * x[0], k * x[1]]

    xs, vs = [list(r0)], [list(v0)]
    x, v = list(r0), list(v0)
    for _ in range(n_steps):
        x, v = velocity_verlet_step(accel, x, v, dt)
        xs.append(x)
        vs.append(v)
    return xs, vs


def kepler_energy(gm: float, x: Sequence[float], v: Sequence[float]) -> float:
    """Specific orbital energy E/m = v^2/2 - GM/r."""
    r = math.sqrt(x[0] * x[0] + x[1] * x[1])
    return 0.5 * (v[0] * v[0] + v[1] * v[1]) - gm / r


def kepler_angular_momentum(x: Sequence[float], v: Sequence[float]) -> float:
    """Specific angular momentum h = x * v_y - y * v_x (z-component)."""
    return x[0] * v[1] - x[1] * v[0]


# Re-export for convenience.
G_NEWTON = C.G_NEWTON
