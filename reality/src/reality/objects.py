"""Physical object model (Phase 2, first slice).

A ``PhysicalObject`` is a rigid shape made of one material, with a thermal state
and a translational state. From the shape and the material density the module
computes, in SI units with dimension checks:

* volume and mass (uniform density),
* centre of mass (the geometric centre, because density is uniform),
* principal moments of inertia about the centre of mass (body frame),
* the inertia tensor about any other point in the body frame (parallel-axis theorem),
* weight, kinetic energy and heat capacity.

Not implemented (see ``reality/LIMITATIONS.md``): orientation or 3D rotation
dynamics, composite or non-uniform density, temperature-dependent properties,
anisotropic materials and contact. The shapes are the three closed-form solids
below; their formulas are standard textbook results, not new equations.

Conventions: the local frame origin is the geometric centre of the shape. Shape
axes are the principal axes. Positions in metres, velocities in m/s.
"""

from __future__ import annotations

import math
from dataclasses import dataclass
from typing import List, Optional, Tuple, Union

from . import constants as C
from . import units as U
from .materials import Material

Vec3 = Tuple[float, float, float]
Matrix3 = Tuple[Tuple[U.Q, U.Q, U.Q], Tuple[U.Q, U.Q, U.Q], Tuple[U.Q, U.Q, U.Q]]


def _positive(value: float, name: str) -> float:
    v = float(value)
    if not math.isfinite(v) or v <= 0.0:
        raise ValueError(f"{name} must be a finite positive length in metres, got {value!r}")
    return v


def _vec3(value, name: str) -> Vec3:
    if len(value) != 3:
        raise ValueError(f"{name} must have 3 components")
    out = tuple(float(x) for x in value)
    if not all(math.isfinite(x) for x in out):
        raise ValueError(f"{name} must be finite")
    return out  # type: ignore[return-value]


@dataclass(frozen=True)
class Sphere:
    """Solid sphere of radius ``radius`` (m)."""

    radius: float

    def __post_init__(self) -> None:
        object.__setattr__(self, "radius", _positive(self.radius, "radius"))

    def volume(self) -> float:
        return 4.0 / 3.0 * math.pi * self.radius ** 3

    def principal_inertia_per_mass(self) -> Vec3:
        # I = (2/5) m r^2 about any axis through the centre (uniform solid sphere).
        k = 0.4 * self.radius ** 2
        return (k, k, k)


@dataclass(frozen=True)
class Box:
    """Solid rectangular box with full edge lengths ``size = (a, b, c)`` in metres."""

    size: Tuple[float, float, float]

    def __post_init__(self) -> None:
        if len(self.size) != 3:
            raise ValueError("size must have 3 edge lengths")
        object.__setattr__(self, "size", tuple(_positive(s, "size edge") for s in self.size))

    def volume(self) -> float:
        a, b, c = self.size
        return a * b * c

    def principal_inertia_per_mass(self) -> Vec3:
        # I_x = m (b^2 + c^2) / 12 and cyclic permutations.
        a, b, c = self.size
        return ((b * b + c * c) / 12.0, (a * a + c * c) / 12.0, (a * a + b * b) / 12.0)


@dataclass(frozen=True)
class Cylinder:
    """Solid circular cylinder: radius ``radius`` (m), height ``height`` (m), axis along z."""

    radius: float
    height: float

    def __post_init__(self) -> None:
        object.__setattr__(self, "radius", _positive(self.radius, "radius"))
        object.__setattr__(self, "height", _positive(self.height, "height"))

    def volume(self) -> float:
        return math.pi * self.radius ** 2 * self.height

    def principal_inertia_per_mass(self) -> Vec3:
        # Transverse: I = m (3 r^2 + h^2) / 12. Axial: I_z = m r^2 / 2.
        r, h = self.radius, self.height
        transverse = (3.0 * r * r + h * h) / 12.0
        return (transverse, transverse, 0.5 * r * r)


Shape = Union[Sphere, Box, Cylinder]


@dataclass
class PhysicalObject:
    """A rigid, uniform-density object with a thermal and translational state."""

    name: str
    shape: Shape
    material: Material
    temperature: float = 293.15          # K (20 degC)
    position: Vec3 = (0.0, 0.0, 0.0)     # m, world frame
    velocity: Vec3 = (0.0, 0.0, 0.0)     # m/s, world frame

    def __post_init__(self) -> None:
        self.position = _vec3(self.position, "position")
        self.velocity = _vec3(self.velocity, "velocity")
        self.temperature = float(self.temperature)
        errs = self.validate()
        if errs:
            raise ValueError(f"invalid object {self.name!r}: " + "; ".join(errs))

    # ------------------------------------------------------------- validity
    def validate(self) -> List[str]:
        """Return a list of consistency errors (empty means valid)."""
        errs: List[str] = []
        if not math.isfinite(self.temperature) or not self.temperature > 0.0:
            errs.append(f"temperature must be a finite positive kelvin value, got {self.temperature!r}")
        errs.extend(f"material: {e}" for e in self.material.validate())
        return errs

    # ----------------------------------------------------------- properties
    def volume(self) -> U.Q:
        return U.q(self.shape.volume(), U.VOLUME)

    def mass(self) -> U.Q:
        """Mass = density x volume (uniform density)."""
        return U.q(self.material.density * self.shape.volume(), U.MASS)

    def centre_of_mass(self) -> Vec3:
        """Centre of mass in the local frame. For uniform density it is the geometric centre."""
        return (0.0, 0.0, 0.0)

    def principal_inertia(self) -> Tuple[U.Q, U.Q, U.Q]:
        """Principal moments of inertia about the centre of mass (kg m^2), body frame."""
        m = self.material.density * self.shape.volume()
        ix, iy, iz = self.shape.principal_inertia_per_mass()
        return (U.q(m * ix, U.MOMENT_OF_INERTIA),
                U.q(m * iy, U.MOMENT_OF_INERTIA),
                U.q(m * iz, U.MOMENT_OF_INERTIA))

    def inertia_about_point(self, point: Vec3) -> Matrix3:
        """Inertia tensor about ``point`` (body frame, metres from the centre of mass).

        Parallel-axis theorem for a body with principal axes aligned with the frame:
        I' = I_cm + m (|d|^2 E - d d^T), where d is the offset of the new point.
        """
        d = _vec3(point, "point")
        m = self.material.density * self.shape.volume()
        diag = self.shape.principal_inertia_per_mass()
        dd = sum(x * x for x in d)
        rows = []
        for i in range(3):
            row = []
            for j in range(3):
                val = m * ((diag[i] if i == j else 0.0) + (dd if i == j else 0.0) - d[i] * d[j])
                row.append(U.q(val, U.MOMENT_OF_INERTIA))
            rows.append(tuple(row))
        return (rows[0], rows[1], rows[2])  # type: ignore[return-value]

    def weight(self, g: float = C.STANDARD_GRAVITY) -> U.Q:
        """Weight m g (N). ``g`` in m/s^2, default standard gravity."""
        return U.q(self.material.density * self.shape.volume() * float(g), U.FORCE)

    def kinetic_energy(self) -> U.Q:
        """Translational kinetic energy 1/2 m |v|^2 (J)."""
        v2 = sum(x * x for x in self.velocity)
        return U.q(0.5 * self.material.density * self.shape.volume() * v2, U.ENERGY)

    def heat_capacity(self) -> U.Q:
        """Heat capacity m c_p (J/K), uniform temperature."""
        return U.q(self.material.density * self.shape.volume() * self.material.specific_heat,
                   U.ENERGY / U.TEMPERATURE)

    def above_melting_point(self) -> Optional[bool]:
        """True/False against the material melting point, or None if no melting point is stored."""
        tm = self.material.melting_temperature
        if tm is None:
            return None
        return self.temperature >= tm
