"""SI dimensional algebra and a minimal dimensioned-quantity type.

Every physical quantity used by PROJECT REALITY carries a dimension vector over the
SI base dimensions (M, L, T, I, Theta, N, J). Exponents are rationals so that
quantities such as fracture toughness (Pa*sqrt(m)) are representable exactly.
Arithmetic between quantities checks dimensions and raises ``DimensionError`` on
mismatch, which is how unit errors are caught at API boundaries.
"""

from __future__ import annotations

import math
from dataclasses import dataclass
from fractions import Fraction
from typing import Iterable

BASE_SYMBOLS = ("M", "L", "T", "I", "Theta", "N", "J")


class DimensionError(TypeError):
    """Raised when quantities with incompatible dimensions are combined."""


@dataclass(frozen=True)
class Dim:
    """Exponent vector over (M, L, T, I, Theta, N, J)."""

    exps: tuple

    def __post_init__(self) -> None:
        if len(self.exps) != len(BASE_SYMBOLS):
            raise ValueError("dimension vector must have 7 entries")
        object.__setattr__(self, "exps", tuple(Fraction(e) for e in self.exps))

    def __mul__(self, other: "Dim") -> "Dim":
        return Dim(tuple(a + b for a, b in zip(self.exps, other.exps)))

    def __truediv__(self, other: "Dim") -> "Dim":
        return Dim(tuple(a - b for a, b in zip(self.exps, other.exps)))

    def __pow__(self, power) -> "Dim":
        p = Fraction(power)
        return Dim(tuple(a * p for a in self.exps))

    @property
    def is_dimensionless(self) -> bool:
        return all(e == 0 for e in self.exps)

    def __str__(self) -> str:
        parts = []
        for sym, e in zip(BASE_SYMBOLS, self.exps):
            if e == 0:
                continue
            parts.append(sym if e == 1 else f"{sym}^{e}")
        return " ".join(parts) if parts else "1"


def _d(M=0, L=0, T=0, I=0, Theta=0, N=0, J=0) -> Dim:
    return Dim((M, L, T, I, Theta, N, J))


DIMENSIONLESS = _d()
MASS = _d(M=1)
LENGTH = _d(L=1)
TIME = _d(T=1)
TEMPERATURE = _d(Theta=1)
AMOUNT = _d(N=1)
CURRENT = _d(I=1)
AREA = LENGTH ** 2
VOLUME = LENGTH ** 3
FREQUENCY = TIME ** -1
VELOCITY = LENGTH / TIME
ACCELERATION = LENGTH / TIME ** 2
MOMENTUM = MASS * VELOCITY
ANGULAR_MOMENTUM = MASS * LENGTH ** 2 / TIME
MOMENT_OF_INERTIA = MASS * LENGTH ** 2                     # kg m^2
FORCE = MASS * ACCELERATION
TORQUE = FORCE * LENGTH
ENERGY = FORCE * LENGTH
POWER = ENERGY / TIME
PRESSURE = FORCE / AREA                                    # Pa; also stress and Young's modulus
DENSITY = MASS / VOLUME
DYNAMIC_VISCOSITY = PRESSURE * TIME                        # Pa*s
SPECIFIC_HEAT = ENERGY / (MASS * TEMPERATURE)              # J/(kg K)
THERMAL_CONDUCTIVITY = POWER / (LENGTH * TEMPERATURE)      # W/(m K)
HEAT_TRANSFER_COEFF = POWER / (AREA * TEMPERATURE)         # W/(m^2 K)
THERMAL_DIFFUSIVITY = LENGTH ** 2 / TIME                   # m^2/s
LATENT_HEAT = ENERGY / MASS                                # J/kg
FRACTURE_TOUGHNESS = PRESSURE * LENGTH ** Fraction(1, 2)   # Pa*sqrt(m)
ACOUSTIC_IMPEDANCE = PRESSURE * TIME / LENGTH              # Pa*s/m (rho*c)
GRAVITATIONAL_PARAMETER = VOLUME / TIME ** 2               # GM, m^3/s^2
SURFACE_ENERGY = ENERGY / AREA                             # J/m^2


@dataclass(frozen=True)
class Q:
    """A floating-point SI value tagged with its dimension."""

    value: float
    dim: Dim

    def _require_same(self, other: "Q", op: str) -> None:
        if self.dim != other.dim:
            raise DimensionError(f"cannot {op} [{self.dim}] and [{other.dim}]")

    def __add__(self, other: "Q") -> "Q":
        self._require_same(other, "add")
        return Q(self.value + other.value, self.dim)

    def __sub__(self, other: "Q") -> "Q":
        self._require_same(other, "subtract")
        return Q(self.value - other.value, self.dim)

    def __mul__(self, other):
        if isinstance(other, Q):
            return Q(self.value * other.value, self.dim * other.dim)
        return Q(self.value * other, self.dim)

    __rmul__ = __mul__

    def __truediv__(self, other):
        if isinstance(other, Q):
            return Q(self.value / other.value, self.dim / other.dim)
        return Q(self.value / other, self.dim)

    def __neg__(self) -> "Q":
        return Q(-self.value, self.dim)

    def __str__(self) -> str:
        return f"{self.value:.6g} [{self.dim}]"

    def to(self, expected: Dim, name: str = "value") -> float:
        """Return the raw SI value after asserting the expected dimension."""
        require_dim(self, expected, name)
        return self.value


def require_dim(q: Q, expected: Dim, name: str = "value") -> None:
    """Raise ``DimensionError`` unless ``q`` is a Q with the expected dimension."""
    if not isinstance(q, Q):
        raise DimensionError(f"{name} must be a Q (dimensioned quantity), got {type(q).__name__}")
    if q.dim != expected:
        raise DimensionError(f"{name} has dimension [{q.dim}], expected [{expected}]")


def q(value: float, dim: Dim) -> Q:
    return Q(float(value), dim)


def check_finite(values: Iterable[float], name: str = "values") -> None:
    """Raise ``ValueError`` if any value is NaN or infinite."""
    for v in values:
        if not math.isfinite(v):
            raise ValueError(f"{name} contains a non-finite value: {v!r}")
