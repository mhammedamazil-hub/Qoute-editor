"""Two-dimensional transient heat conduction on a square (Phase 8, numerical solver).

Equation:  dT/dt = alpha (d2T/dx2 + d2T/dy2),  T = 0 on all four edges of [0, L]^2.
Scheme:    explicit FTCS on an N x N grid of interior nodes (spacing dx = L/(N+1)),
           dt chosen by the caller. Stability: Fo = alpha dt / dx^2 <= 1/4 (2D von Neumann limit).
Analytic reference for the initial field T(x, y, 0) = sin(pi x / L) sin(pi y / L):
           T(x, y, t) = exp(-2 pi^2 alpha t / L^2) sin(pi x / L) sin(pi y / L).

Limits: uniform material, Dirichlet boundaries only, no source terms, explicit time stepping
(dt limited by dx^2). Implicit or multigrid solvers are not yet implemented.
"""

from __future__ import annotations

import math
from typing import List


def solve_square(n_interior: int, alpha: float, length: float, t_end: float,
                 fo_target: float = 0.2) -> List[List[float]]:
    """Return the interior temperature field after t_end (list of rows, row index = y).

    ``fo_target`` sets dt = fo_target dx^2 / alpha; it must be <= 0.25 for stability.
    """
    if n_interior < 1:
        raise ValueError("need at least one interior node")
    if not (alpha > 0.0 and length > 0.0 and t_end >= 0.0):
        raise ValueError("alpha and length must be > 0, t_end >= 0")
    if not (0.0 < fo_target <= 0.25):
        raise ValueError("fo_target must be in (0, 0.25] for the explicit 2D scheme")
    dx = length / (n_interior + 1)
    dt = fo_target * dx * dx / alpha
    xs = [dx * (i + 1) for i in range(n_interior)]
    t = [[math.sin(math.pi * x / length) * math.sin(math.pi * y / length) for x in xs] for y in xs]
    steps = int(round(t_end / dt))
    dt = t_end / steps if steps > 0 else 0.0
    fo = alpha * dt / (dx * dx)
    n = n_interior
    for _ in range(steps):
        new = [[0.0] * n for _ in range(n)]
        for j in range(n):
            for i in range(n):
                left = t[j][i - 1] if i > 0 else 0.0
                right = t[j][i + 1] if i < n - 1 else 0.0
                down = t[j - 1][i] if j > 0 else 0.0
                up = t[j + 1][i] if j < n - 1 else 0.0
                c = t[j][i]
                new[j][i] = c + fo * (left + right + down + up - 4.0 * c)
        t = new
    return t


def analytic_field(n_interior: int, alpha: float, length: float, t: float) -> List[List[float]]:
    """Exact solution for the sinusoidal initial field, sampled on the same grid."""
    dx = length / (n_interior + 1)
    decay = math.exp(-2.0 * math.pi ** 2 * alpha * t / length ** 2)
    xs = [dx * (i + 1) for i in range(n_interior)]
    return [[decay * math.sin(math.pi * x / length) * math.sin(math.pi * y / length) for x in xs] for y in xs]
