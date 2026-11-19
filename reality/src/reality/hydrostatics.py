"""Hydrostatics and buoyancy (Phase 7, first slice: no flow, no fire, no atmosphere model yet).

    p(h) = p_surface + rho g h                    hydrostatic pressure at depth h
    F_b  = rho_fluid g V_submerged                Archimedes' principle (buoyant force)
    floating: V_submerged / V = rho_object / rho_fluid   (when rho_object <= rho_fluid)
    apparent weight = m g - F_b                   weight felt by a support holding the body

Standard textbook results (e.g. White, *Fluid Mechanics*, hydrostatics chapter). Densities are
kg/m^3, depths m, g in m/s^2 (default standard gravity), pressures in Pa.
"""

from __future__ import annotations

import math

from . import constants as C


def _finite_non_negative(value: float, name: str) -> None:
    if not (math.isfinite(value) and value >= 0.0):
        raise ValueError(f"{name} must be finite and >= 0, got {value!r}")


def _finite_positive(value: float, name: str) -> None:
    if not (math.isfinite(value) and value > 0.0):
        raise ValueError(f"{name} must be finite and > 0, got {value!r}")


def pressure_at_depth(depth: float, fluid_density: float, g: float = C.STANDARD_GRAVITY,
                      p_surface: float = C.P_ATM) -> float:
    """Absolute pressure at depth below a free surface held at ``p_surface`` (Pa)."""
    _finite_non_negative(depth, "depth")
    _finite_positive(fluid_density, "fluid_density")
    _finite_positive(g, "g")
    return p_surface + fluid_density * g * depth


def buoyant_force(fluid_density: float, submerged_volume: float, g: float = C.STANDARD_GRAVITY) -> float:
    """Archimedes' buoyant force (N) on the displaced fluid volume."""
    _finite_positive(fluid_density, "fluid_density")
    _finite_non_negative(submerged_volume, "submerged_volume")
    _finite_positive(g, "g")
    return fluid_density * g * submerged_volume


def floating_submerged_fraction(object_density: float, fluid_density: float) -> float:
    """Fraction of a freely floating body's volume below the surface.

    Returns rho_object / rho_fluid when the body floats (rho_object <= rho_fluid), and 1.0 when it
    sinks (it is then fully submerged and rests on the bottom, so this is a bound, not equilibrium).
    """
    _finite_positive(object_density, "object_density")
    _finite_positive(fluid_density, "fluid_density")
    return min(1.0, object_density / fluid_density)


def apparent_weight(mass: float, fluid_density: float, submerged_volume: float,
                    g: float = C.STANDARD_GRAVITY) -> float:
    """Weight minus buoyancy (N): the force a support must carry when the body is held submerged."""
    _finite_positive(mass, "mass")
    return mass * g - buoyant_force(fluid_density, submerged_volume, g)
