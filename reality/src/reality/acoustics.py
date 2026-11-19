"""Linear acoustics: wave speed, impedance, interface reflection, Doppler and resonance.

Acoustic response of a material comes from its density and bulk stiffness. Impedance
Z = rho c controls how much sound energy is reflected at an interface. These are the
linear, small-amplitude relations of Kinsler et al., Fundamentals of Acoustics (4th ed.).
"""

from __future__ import annotations

import math

from . import constants as C


def speed_of_sound_ideal_gas(temperature_k: float, gamma: float = C.GAMMA_AIR, molar_mass: float = C.M_AIR) -> float:
    """c = sqrt(gamma R T / M) for an ideal gas (Kinsler Eq. 1.x)."""
    if temperature_k <= 0:
        raise ValueError("temperature must be positive kelvin")
    return math.sqrt(gamma * C.R_GAS * temperature_k / molar_mass)


def speed_of_sound_from_modulus(bulk_modulus: float, density: float) -> float:
    """Bulk wave speed c = sqrt(K / rho) for a fluid (plane wave, no shear)."""
    if bulk_modulus <= 0 or density <= 0:
        raise ValueError("bulk modulus and density must be positive")
    return math.sqrt(bulk_modulus / density)


def acoustic_impedance(density: float, speed: float) -> float:
    """Specific acoustic impedance Z = rho c, Pa*s/m."""
    return density * speed


def intensity_reflection_normal(z1: float, z2: float) -> float:
    """Intensity reflection coefficient at normal incidence: R = ((Z2 - Z1)/(Z2 + Z1))^2."""
    return ((z2 - z1) / (z2 + z1)) ** 2


def intensity_transmission_normal(z1: float, z2: float) -> float:
    """Intensity transmission coefficient: T = 4 Z1 Z2 / (Z1 + Z2)^2 (so R + T = 1)."""
    return 4.0 * z1 * z2 / (z1 + z2) ** 2


def doppler_frequency(f_source: float, c: float, v_observer: float, v_source: float) -> float:
    """Frequency heard by a moving observer from a moving source.

    Positive v_observer means the observer moves toward the source; positive v_source means
    the source moves toward the observer. f' = f (c + v_o) / (c - v_s).
    """
    if c <= 0:
        raise ValueError("wave speed must be positive")
    if v_source >= c:
        raise ValueError("source speed must be below the wave speed (no shock model here)")
    return f_source * (c + v_observer) / (c - v_source)


def sound_pressure_level_db(p_rms: float) -> float:
    """SPL = 20 log10(p / p_ref), p_ref = 20 uPa."""
    if p_rms <= 0:
        raise ValueError("pressure must be positive")
    return 20.0 * math.log10(p_rms / C.P_REF_AIR_SOUND)


def pressure_from_intensity(intensity: float, impedance: float) -> float:
    """RMS pressure of a plane wave: p_rms = sqrt(I Z)."""
    return math.sqrt(intensity * impedance)


def closed_open_pipe_frequency(n: int, length: float, c: float) -> float:
    """Resonances of a pipe closed at one end and open at the other: f_n = (2n-1) c / (4L)."""
    if n < 1:
        raise ValueError("mode index n starts at 1")
    return (2 * n - 1) * c / (4.0 * length)


def string_frequency(n: int, length: float, tension: float, linear_density: float) -> float:
    """Fixed-fixed string: f_n = (n / 2L) sqrt(T / mu)."""
    if n < 1:
        raise ValueError("mode index n starts at 1")
    return n / (2.0 * length) * math.sqrt(tension / linear_density)
