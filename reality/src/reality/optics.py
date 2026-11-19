"""Geometric and wave optics at a planar dielectric interface.

Implements Snell's law, critical angle, Brewster angle, unpolarized and polarized
Fresnel reflectances for lossless dielectrics, and the Schott BK7 Sellmeier
dispersion relation (wavelength-dependent index).

This is the RGB-independent physics layer. Spectral rendering and absorbing media
(complex refractive index) are not implemented yet; see LIMITATIONS.md.
"""

from __future__ import annotations

import math
from dataclasses import dataclass
from typing import Optional

from . import constants as C


def snell_angle(n1: float, theta1: float, n2: float) -> Optional[float]:
    """Refraction angle theta2 from n1 sin(theta1) = n2 sin(theta2); None under total internal reflection."""
    if n1 <= 0 or n2 <= 0:
        raise ValueError("refractive indices must be positive")
    s = n1 * math.sin(theta1) / n2
    if abs(s) > 1.0:
        return None
    return math.asin(s)


def critical_angle(n1: float, n2: float) -> float:
    """Critical angle for total internal reflection (requires n1 > n2)."""
    if n1 <= n2:
        raise ValueError("total internal reflection requires n1 > n2")
    return math.asin(n2 / n1)


def brewster_angle(n1: float, n2: float) -> float:
    """Brewster angle, tan(theta_B) = n2 / n1: p-polarized reflectance vanishes."""
    return math.atan2(n2, n1)


@dataclass(frozen=True)
class FresnelResult:
    rs: float        # s-polarized amplitude reflection coefficient
    rp: float        # p-polarized amplitude reflection coefficient
    R_s: float       # s-polarized power reflectance
    R_p: float       # p-polarized power reflectance
    R_unpolarized: float
    total_internal_reflection: bool


def fresnel(n1: float, n2: float, theta_i: float) -> FresnelResult:
    """Fresnel equations for a lossless interface (Born & Wolf, Principles of Optics, Sec. 1.5).

    rs = (n1 cos ti - n2 cos tt) / (n1 cos ti + n2 cos tt)
    rp = (n2 cos ti - n1 cos tt) / (n2 cos ti + n1 cos tt)
    R = r^2. Under total internal reflection, R = 1 for both polarizations.
    """
    tt = snell_angle(n1, theta_i, n2)
    if tt is None:
        return FresnelResult(1.0, 1.0, 1.0, 1.0, 1.0, True)
    ci, ct = math.cos(theta_i), math.cos(tt)
    rs = (n1 * ci - n2 * ct) / (n1 * ci + n2 * ct)
    rp = (n2 * ci - n1 * ct) / (n2 * ci + n1 * ct)
    Rs, Rp = rs * rs, rp * rp
    return FresnelResult(rs, rp, Rs, Rp, 0.5 * (Rs + Rp), False)


def normal_incidence_reflectance(n1: float, n2: float) -> float:
    """R0 = ((n1 - n2)/(n1 + n2))^2. Air to glass (n=1.5) gives ~4 %."""
    return ((n1 - n2) / (n1 + n2)) ** 2


def sellmeier_bk7(wavelength_m: float) -> float:
    """Refractive index of Schott N-BK7 from its Sellmeier equation (valid ~0.3-2.5 um).

    n^2 - 1 = sum_i B_i l^2 / (l^2 - C_i), l in micrometres.
    """
    lam = wavelength_m * 1e6
    if not 0.3 <= lam <= 2.5:
        raise ValueError("BK7 Sellmeier coefficients are valid for 0.3-2.5 um")
    l2 = lam * lam
    s = 0.0
    for b, c in zip(C.BK7_B, C.BK7_C):
        s += b * l2 / (l2 - c)
    return math.sqrt(1.0 + s)
