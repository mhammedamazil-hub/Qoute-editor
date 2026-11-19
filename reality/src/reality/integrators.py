"""Time integrators for ordinary differential equations.

* ``rk4_step`` - classical 4th-order Runge-Kutta for general y' = f(t, y).
  Local error O(h^5), global O(h^4). Not symplectic: energy drifts slowly.
* ``velocity_verlet_step`` - 2nd-order symplectic integrator for x'' = a(x).
  Global error O(h^2) but bounded energy error over long times (no secular drift
  for conservative forces), which is why it is preferred for orbits and oscillators.

Vectors are plain Python lists of floats. The code is dependency-free so it can be
ported to C++ / GPU kernels later with the same algorithmic structure.
"""

from __future__ import annotations

from typing import Callable, List, Sequence, Tuple

Derivative = Callable[[float, List[float]], List[float]]


def rk4_step(f: Derivative, t: float, y: Sequence[float], h: float) -> List[float]:
    """One classical RK4 step for y' = f(t, y)."""
    y = list(y)
    k1 = f(t, y)
    k2 = f(t + 0.5 * h, [yi + 0.5 * h * ki for yi, ki in zip(y, k1)])
    k3 = f(t + 0.5 * h, [yi + 0.5 * h * ki for yi, ki in zip(y, k2)])
    k4 = f(t + h, [yi + h * ki for yi, ki in zip(y, k3)])
    return [
        yi + (h / 6.0) * (a + 2.0 * b + 2.0 * c + d)
        for yi, a, b, c, d in zip(y, k1, k2, k3, k4)
    ]


def integrate_rk4(f: Derivative, t0: float, y0: Sequence[float], t_end: float, h: float) -> List[float]:
    """Integrate from t0 to t_end with fixed step h (the last step is shortened to hit t_end)."""
    if h <= 0:
        raise ValueError("step must be positive")
    t, y = t0, list(y0)
    while t < t_end - 1e-15:
        step = min(h, t_end - t)
        y = rk4_step(f, t, y, step)
        t += step
    return y


def velocity_verlet_step(
    accel: Callable[[Sequence[float]], Sequence[float]],
    x: Sequence[float],
    v: Sequence[float],
    h: float,
) -> Tuple[List[float], List[float]]:
    """One velocity-Verlet step for x'' = accel(x). Returns (x_new, v_new)."""
    a0 = accel(x)
    x_new = [xi + h * vi + 0.5 * h * h * ai for xi, vi, ai in zip(x, v, a0)]
    a1 = accel(x_new)
    v_new = [vi + 0.5 * h * (a + b) for vi, a, b in zip(v, a0, a1)]
    return x_new, v_new
