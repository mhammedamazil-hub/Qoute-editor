"""Population dynamics (Phase 9, first slice): classical models with exact invariants.

These are textbook population models, not models of real organisms. They are used as
numerical benchmarks before any biological model is allowed into the engine (see brief rule 15).

Logistic growth (Verhulst 1838):  dN/dt = r N (1 - N/K).
    Analytic: N(t) = K / (1 + ((K - N0)/N0) exp(-r t)).
Lotka-Volterra predator-prey (Lotka 1925; Volterra 1926):
    dx/dt = alpha x - beta x y        (prey x)
    dy/dt = delta x y - gamma y       (predator y)
    First integral: H = delta x - gamma ln x + beta y - alpha ln y is constant on trajectories.
"""

from __future__ import annotations

import math
from typing import Callable, List, Sequence

from .integrators import integrate_rk4


def logistic_analytic(t: float, n0: float, r: float, k: float) -> float:
    if not (n0 > 0.0 and k > 0.0 and r >= 0.0 and t >= 0.0):
        raise ValueError("need n0 > 0, K > 0, r >= 0, t >= 0")
    return k / (1.0 + ((k - n0) / n0) * math.exp(-r * t))


def logistic_numeric(t_end: float, n0: float, r: float, k: float, h: float) -> float:
    def f(_t: float, y: Sequence[float]) -> List[float]:
        return [r * y[0] * (1.0 - y[0] / k)]
    return integrate_rk4(f, 0.0, [n0], t_end, h)[0]


def lotka_volterra_rhs(alpha: float, beta: float, gamma: float, delta: float) -> Callable[[float, Sequence[float]], List[float]]:
    def f(_t: float, y: Sequence[float]) -> List[float]:
        x, yy = y[0], y[1]
        return [alpha * x - beta * x * yy, delta * x * yy - gamma * yy]
    return f


def lotka_volterra_invariant(x: float, y: float, alpha: float, beta: float, gamma: float, delta: float) -> float:
    if x <= 0.0 or y <= 0.0:
        raise ValueError("populations must be > 0 for the logarithmic invariant")
    return delta * x - gamma * math.log(x) + beta * y - alpha * math.log(y)
