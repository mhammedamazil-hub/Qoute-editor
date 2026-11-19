"""Euler-Bernoulli beam mechanics for structural stress and deflection.

Small-deflection linear beam theory: EI w'''' = q(x). Used for structural stress and
first-mode frequency of slender bodies. Formulas are from Timoshenko & Gere, Mechanics
of Materials, and Gere & Goodno; each has a numerical cross-check in the test-suite.
"""

from __future__ import annotations

import math


def rectangular_second_moment(width: float, height: float) -> float:
    """I = b h^3 / 12 about the centroidal axis parallel to b (m^4)."""
    if width <= 0 or height <= 0:
        raise ValueError("dimensions must be positive")
    return width * height ** 3 / 12.0


def cantilever_tip_deflection(force: float, length: float, youngs_modulus: float, inertia: float) -> float:
    """Tip deflection of a cantilever under a tip load: delta = F L^3 / (3 E I)."""
    return force * length ** 3 / (3.0 * youngs_modulus * inertia)


def cantilever_root_bending_stress(force: float, length: float, c: float, inertia: float) -> float:
    """Maximum bending stress at the clamped root: sigma = M c / I with M = F L."""
    return force * length * c / inertia


def cantilever_first_frequency(youngs_modulus: float, inertia: float, mass_per_length: float, length: float) -> float:
    """Fundamental natural frequency (Hz) of a uniform cantilever.

    omega_1 = (beta_1 L)^2 sqrt(E I / (m' L^4)), beta_1 L = 1.8751040687 (root of cos x cosh x = -1).
    """
    beta_l = 1.8751040687119
    omega = beta_l ** 2 * math.sqrt(youngs_modulus * inertia / (mass_per_length * length ** 4))
    return omega / (2.0 * math.pi)


def cantilever_deflection_by_double_integration(
    force: float, length: float, youngs_modulus: float, inertia: float, n: int = 2000
) -> float:
    """Tip deflection by numerically integrating the curvature kappa = M(x)/(E I) twice.

    Trapezoidal rule on n+1 nodes (second-order accurate). Boundary conditions at the clamp:
    w(0) = 0 and w'(0) = 0. Used as an independent check of ``cantilever_tip_deflection``.
    """
    dx = length / n
    kappa = [force * (length - i * dx) / (youngs_modulus * inertia) for i in range(n + 1)]
    slope = [0.0] * (n + 1)
    defl = [0.0] * (n + 1)
    for i in range(1, n + 1):
        slope[i] = slope[i - 1] + 0.5 * dx * (kappa[i - 1] + kappa[i])
    for i in range(1, n + 1):
        defl[i] = defl[i - 1] + 0.5 * dx * (slope[i - 1] + slope[i])
    return defl[n]
