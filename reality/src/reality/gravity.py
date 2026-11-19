"""Configurable gravity: uniform fields, point-mass bodies and multi-body superposition.

Gravity is never a hard-coded constant. A simulation chooses one of:

* ``UniformGravity`` - a constant field g (e.g. a lab on Earth, Moon or Mars surface).
* ``PointMassGravity`` - Newtonian attraction of one or more bodies, with GM and
  position, valid outside the body (or inside, for a uniform sphere, see note).

Accelerations are in m/s^2 and positions in metres. Newtonian gravity is the
weak-field, low-speed limit of General Relativity. Relativistic corrections are
not modelled and are negligible for ordinary laboratory and planetary scales;
see LIMITATIONS.md.
"""

from __future__ import annotations

import math
from dataclasses import dataclass
from typing import Iterable, Sequence, Tuple

from . import constants as C

Vec3 = Tuple[float, float, float]


def _norm(v: Sequence[float]) -> float:
    return math.sqrt(sum(x * x for x in v))


@dataclass(frozen=True)
class UniformGravity:
    """Constant gravitational acceleration vector, m/s^2 (default: Earth surface, -y up)."""

    g: Vec3 = (0.0, -C.STANDARD_GRAVITY, 0.0)

    def acceleration(self, position: Sequence[float]) -> Vec3:
        return self.g


@dataclass(frozen=True)
class GravityBody:
    """A point-mass source described by its gravitational parameter GM = G * M."""

    name: str
    gm: float                    # m^3/s^2
    radius: float                # m, mean radius (used for surface gravity)
    position: Vec3 = (0.0, 0.0, 0.0)

    def surface_gravity(self) -> float:
        """Newtonian surface gravity GM/R^2, m/s^2."""
        return self.gm / self.radius ** 2

    def acceleration(self, point: Sequence[float]) -> Vec3:
        """Gravitational acceleration at ``point`` from this body alone (outside the body)."""
        r = [point[i] - self.position[i] for i in range(3)]
        d = _norm(r)
        if d == 0.0:
            raise ValueError("point coincides with the body centre")
        k = -self.gm / d ** 3
        return (k * r[0], k * r[1], k * r[2])


@dataclass(frozen=True)
class PointMassGravity:
    """Superposition of point-mass bodies (N-body Newtonian field)."""

    bodies: Tuple[GravityBody, ...]

    def acceleration(self, point: Sequence[float]) -> Vec3:
        ax = ay = az = 0.0
        for b in self.bodies:
            gx, gy, gz = b.acceleration(point)
            ax += gx
            ay += gy
            az += gz
        return (ax, ay, az)


def gm_from_mass(mass_kg: float) -> float:
    """Gravitational parameter GM = G*M from a mass in kg (CODATA 2018 G)."""
    if mass_kg <= 0:
        raise ValueError("mass must be positive")
    return C.G_NEWTON * mass_kg


def earth() -> GravityBody:
    return GravityBody("earth", C.GM_EARTH, C.R_EARTH_MEAN)


def moon() -> GravityBody:
    return GravityBody("moon", C.GM_MOON, C.R_MOON_MEAN)


def mars() -> GravityBody:
    return GravityBody("mars", C.GM_MARS, C.R_MARS_MEAN)


def surface_field(body: GravityBody) -> UniformGravity:
    """Uniform approximation of a body's field at its surface (valid over a small lab)."""
    g = body.surface_gravity()
    return UniformGravity((0.0, -g, 0.0))


def orbital_period_circular(gm: float, r: float) -> float:
    """Period of a circular orbit of radius r about a body with parameter GM (Kepler III)."""
    if r <= 0 or gm <= 0:
        raise ValueError("gm and r must be positive")
    return 2.0 * math.pi * math.sqrt(r ** 3 / gm)


def circular_speed(gm: float, r: float) -> float:
    """Circular orbital speed v = sqrt(GM/r)."""
    return math.sqrt(gm / r)


def acceleration_sum(fields: Iterable, point: Sequence[float]) -> Vec3:
    """Sum accelerations from several gravity sources (uniform or point-mass)."""
    ax = ay = az = 0.0
    for f in fields:
        gx, gy, gz = f.acceleration(point)
        ax += gx
        ay += gy
        az += gz
    return (ax, ay, az)
