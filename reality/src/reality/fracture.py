"""Material-aware failure: linear-elastic fracture mechanics (brittle) and yield (ductile).

Brittle solids (glass, ceramics, concrete, ice) fail by crack propagation. The critical
stress depends on the largest flaw and on fracture toughness K_Ic, not only on yield:

    K_I = Y sigma sqrt(pi a)             (Irwin 1957 stress intensity, Y geometry factor)
    failure when K_I >= K_Ic
    sigma_c(a) = K_Ic / (Y sqrt(pi a))
    a_c(sigma) = (1/pi) (K_Ic / (Y sigma))^2

Ductile metals fail first by yield (sigma >= sigma_y) and then by plastic flow. The
``assess`` function reports both and the governing mode, so the same applied stress
can produce different outcomes for glass and steel.

Griffith (1921) energy balance: G = K_I^2 / E' with E' = E (plane stress) or
E/(1 - nu^2) (plane strain); crack growth when G >= 2 gamma_s.
"""

from __future__ import annotations

import math
from dataclasses import dataclass
from typing import Optional

from .materials import Material


def stress_intensity(stress: float, flaw_half_length: float, geometry_factor: float = 1.0) -> float:
    """K_I = Y sigma sqrt(pi a), Pa*sqrt(m). a is the half-length of an internal crack."""
    if flaw_half_length < 0:
        raise ValueError("flaw size must be non-negative")
    return geometry_factor * stress * math.sqrt(math.pi * flaw_half_length)


def fracture_stress(k_ic: float, flaw_half_length: float, geometry_factor: float = 1.0) -> float:
    """Applied stress that makes K_I reach K_Ic for a flaw of half-length a."""
    if flaw_half_length <= 0:
        raise ValueError("flaw size must be positive")
    return k_ic / (geometry_factor * math.sqrt(math.pi * flaw_half_length))


def critical_flaw_size(k_ic: float, stress: float, geometry_factor: float = 1.0) -> float:
    """Largest flaw (half-length, m) that survives an applied stress."""
    if stress <= 0:
        raise ValueError("stress must be positive")
    return (1.0 / math.pi) * (k_ic / (geometry_factor * stress)) ** 2


def griffith_energy_release_rate(k_i: float, youngs_modulus: float, poisson_ratio: float, plane_strain: bool = False) -> float:
    """G = K_I^2 / E' in J/m^2."""
    e_eff = youngs_modulus / (1.0 - poisson_ratio ** 2) if plane_strain else youngs_modulus
    return k_i * k_i / e_eff


def griffith_surface_energy(k_ic: float, youngs_modulus: float, poisson_ratio: float, plane_strain: bool = False) -> float:
    """Effective surface energy gamma_s = G_c / 2 in J/m^2 (Griffith criterion)."""
    return 0.5 * griffith_energy_release_rate(k_ic, youngs_modulus, poisson_ratio, plane_strain)


@dataclass(frozen=True)
class FailureAssessment:
    material: str
    behavior: str
    applied_stress: float            # Pa, uniaxial tensile
    flaw_half_length: float          # m
    critical_stress_flaw: Optional[float]   # Pa, LEFM critical stress for this flaw (brittle)
    yield_strength: Optional[float]          # Pa (ductile)
    safety_factor: Optional[float]
    failed: bool
    mode: str                        # "fracture", "yield" or "none"


def assess(material: Material, applied_stress: float, flaw_half_length: float = 0.0,
           geometry_factor: float = 1.0) -> FailureAssessment:
    """Predict whether a uniaxial tensile stress fails a material.

    Brittle: failure if K_I >= K_Ic for the given flaw. A zero-size flaw is not allowed for
    brittle materials because it implies infinite strength; a nominal flaw must be supplied.
    Ductile: failure if sigma >= sigma_y (von Mises reduces to |sigma| for uniaxial stress).
    """
    if applied_stress < 0:
        applied_stress = -applied_stress  # tension and compression magnitudes treated symmetrically here
    if material.behavior == "brittle":
        if material.fracture_toughness is None:
            raise ValueError(f"{material.name} is brittle but has no fracture toughness")
        if flaw_half_length <= 0:
            raise ValueError("brittle assessment requires a positive flaw size")
        sc = fracture_stress(material.fracture_toughness, flaw_half_length, geometry_factor)
        sf = sc / applied_stress if applied_stress > 0 else None
        failed = applied_stress >= sc
        return FailureAssessment(material.name, material.behavior, applied_stress, flaw_half_length,
                                 sc, None, sf, failed, "fracture" if failed else "none")
    if material.behavior in ("ductile",):
        sy = material.yield_strength
        if sy is None:
            raise ValueError(f"{material.name} is ductile but has no yield strength")
        sf = sy / applied_stress if applied_stress > 0 else None
        failed = applied_stress >= sy
        return FailureAssessment(material.name, material.behavior, applied_stress, flaw_half_length,
                                 None, sy, sf, failed, "yield" if failed else "none")
    raise ValueError(
        f"no fracture/yield model for behavior {material.behavior!r}; "
        "elastomers and granular media need dedicated constitutive models"
    )
