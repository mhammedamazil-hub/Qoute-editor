"""Weibull statistics of brittle strength (Phase 4).

The probability that a brittle body of effective volume V fails at applied stress sigma is the
two-parameter Weibull distribution (Weibull, J. Appl. Mech. 18, 293-297, 1951):

    P_f(sigma) = 1 - exp( -(V / V0) (sigma / sigma0)^m )

with Weibull modulus m (scatter), scale stress sigma0 (characteristic strength at reference
volume V0), and V0 = 1 by convention below. Because the probability is set by the largest flaw,
the median strength falls with volume as V^(-1/m): the size effect.

Fitting uses median ranks (Bernard's approximation F_i = (i - 0.3)/(n + 0.4); not yet in the
verification ledger, see LIMITATIONS.md section 8) and a linear
regression of ln(-ln(1 - F)) on ln(sigma). The fit is exact for data generated from the model,
which the validation suite checks (round trip).

What this module does NOT do: fit real glass or ceramic data (no measured data is stored in
the repository), crack growth, fatigue, or non-uniform stress fields. Those are listed in
LIMITATIONS.md. The formulas are the standard Weibull results cited above and in
SCIENCE_RESEARCH.md section 2.7.
"""

from __future__ import annotations

import math
from typing import List, Sequence, Tuple


def _check_positive(value: float, name: str) -> None:
    if not (math.isfinite(value) and value > 0.0):
        raise ValueError(f"{name} must be finite and > 0, got {value!r}")


def failure_probability(stress: float, sigma0: float, modulus: float, volume_ratio: float = 1.0) -> float:
    """P_f = 1 - exp(-volume_ratio (stress/sigma0)^m). ``volume_ratio`` = V / V0."""
    _check_positive(sigma0, "sigma0")
    _check_positive(modulus, "modulus")
    _check_positive(volume_ratio, "volume_ratio")
    if stress < 0.0:
        raise ValueError("stress must be >= 0 (tensile)")
    return -math.expm1(-volume_ratio * (stress / sigma0) ** modulus)


def stress_at_probability(p: float, sigma0: float, modulus: float, volume_ratio: float = 1.0) -> float:
    """Inverse of ``failure_probability``: the stress at which P_f = p."""
    _check_positive(sigma0, "sigma0")
    _check_positive(modulus, "modulus")
    _check_positive(volume_ratio, "volume_ratio")
    if not (0.0 <= p < 1.0):
        raise ValueError("probability must lie in [0, 1)")
    return sigma0 * (-math.log1p(-p) / volume_ratio) ** (1.0 / modulus)


def median_strength(sigma0: float, modulus: float, volume_ratio: float = 1.0) -> float:
    """Stress at 50 % failure probability, sigma_50 = sigma0 (ln 2 / (V/V0))^(1/m)."""
    return stress_at_probability(0.5, sigma0, modulus, volume_ratio)


def size_effect_ratio(volume_1: float, volume_2: float, modulus: float) -> float:
    """sigma_50(V2) / sigma_50(V1) = (V1 / V2)^(1/m)."""
    _check_positive(volume_1, "volume_1")
    _check_positive(volume_2, "volume_2")
    _check_positive(modulus, "modulus")
    return (volume_1 / volume_2) ** (1.0 / modulus)


def effective_volume(volumes: Sequence[float], stresses: Sequence[float], reference_stress: float,
                     modulus: float) -> float:
    """Discrete Weibull effective volume V_eff = sum_i V_i (sigma_i / sigma_ref)^m.

    For a uniform field sigma_i = sigma_ref this reduces to the total volume.
    """
    if len(volumes) != len(stresses):
        raise ValueError("volumes and stresses must have the same length")
    _check_positive(reference_stress, "reference_stress")
    _check_positive(modulus, "modulus")
    total = 0.0
    for v, s in zip(volumes, stresses):
        _check_positive(v, "volume element")
        if s < 0.0:
            raise ValueError("stress elements must be >= 0")
        total += v * (s / reference_stress) ** modulus
    return total


def median_ranks(n: int) -> List[float]:
    """Bernard's median-rank plotting positions F_i = (i - 0.3)/(n + 0.4), i = 1..n."""
    if n < 1:
        raise ValueError("need at least one sample")
    return [(i - 0.3) / (n + 0.4) for i in range(1, n + 1)]


def fit_weibull(strengths: Sequence[float]) -> Tuple[float, float]:
    """Estimate (modulus m, scale sigma0) from failure strengths by median-rank regression."""
    if len(strengths) < 3:
        raise ValueError("need at least three strength values to fit two parameters")
    data = sorted(float(s) for s in strengths)
    if data[0] <= 0.0:
        raise ValueError("strengths must be > 0")
    ranks = median_ranks(len(data))
    xs = [math.log(s) for s in data]
    ys = [math.log(-math.log1p(-f)) for f in ranks]
    n = len(xs)
    mx = sum(xs) / n
    my = sum(ys) / n
    sxx = sum((x - mx) ** 2 for x in xs)
    if sxx == 0.0:
        raise ValueError("strengths must not all be equal")
    slope = sum((x - mx) * (y - my) for x, y in zip(xs, ys)) / sxx
    intercept = my - slope * mx
    if slope <= 0.0:
        raise ValueError("fitted modulus is not positive: data do not look Weibull-distributed")
    modulus = slope
    sigma0 = math.exp(-intercept / slope)
    return modulus, sigma0
