"""Heat transfer: lumped capacitance, 1D conduction and phase-change energy balance.

Equations are in ``reality/PHYSICS_MODELS.md``. The conduction solver is explicit
(FTCS) and therefore conditionally stable: it requires the Fourier number
Fo = alpha * dt / dx^2 <= 1/2. ``conduction_1d_explicit`` enforces this.
"""

from __future__ import annotations

import math
from typing import List, Sequence, Tuple

from . import constants as C


# ------------------------------------------------------------ lumped capacitance ---
def biot_number(h: float, volume: float, area: float, k: float) -> float:
    """Bi = h L_c / k with characteristic length L_c = V / A."""
    if min(h, volume, area, k) < 0 or area == 0 or k == 0:
        raise ValueError("invalid geometry or conductivity")
    return h * (volume / area) / k


def lumped_cooling(
    t: float, t0: float, t_env: float, h: float, area: float, mass: float, cp: float
) -> float:
    """Temperature of a spatially uniform body: T(t) = T_inf + (T0 - T_inf) exp(-h A t / (m c_p)).

    Valid only when Bi = h L_c / k << 0.1 (the caller should check ``biot_number``).
    """
    tau = mass * cp / (h * area)
    return t_env + (t0 - t_env) * math.exp(-t / tau)


# ------------------------------------------------------------- 1D conduction ---
def fourier_number(alpha: float, dt: float, dx: float) -> float:
    return alpha * dt / (dx * dx)


def conduction_1d_explicit(
    temps: Sequence[float],
    alpha: float,
    dx: float,
    dt: float,
    n_steps: int,
    t_left: float,
    t_right: float,
) -> List[float]:
    """FTCS solution of T_t = alpha T_xx with Dirichlet boundaries T(0)=t_left, T(L)=t_right.

    Raises ``ValueError`` if the explicit stability limit Fo <= 1/2 is violated.
    """
    fo = fourier_number(alpha, dt, dx)
    if fo > 0.5 + 1e-12:
        raise ValueError(f"explicit scheme unstable: Fo = {fo:.4f} > 0.5; reduce dt")
    T = list(temps)
    T[0], T[-1] = t_left, t_right
    n = len(T)
    for _ in range(n_steps):
        new = T[:]
        for i in range(1, n - 1):
            new[i] = T[i] + fo * (T[i + 1] - 2.0 * T[i] + T[i - 1])
        T = new
    return T


def slab_dirichlet_analytic(x: float, t: float, length: float, alpha: float, t0: float, ts: float, n_terms: int = 401) -> float:
    """Exact solution of a slab with uniform initial temperature T0 and both faces held at Ts.

    theta = (T - Ts)/(T0 - Ts) = sum_{n odd} 4/(n pi) sin(n pi x/L) exp(-(n pi/L)^2 alpha t)
    (Carslaw & Jaeger, Conduction of Heat in Solids, 2nd ed., Sec. 2.4; Incropera Sec. 5.5).
    """
    if t <= 0:
        return t0
    s = 0.0
    for k in range(n_terms):
        n = 2 * k + 1
        s += (4.0 / (n * math.pi)) * math.sin(n * math.pi * x / length) * math.exp(
            -((n * math.pi / length) ** 2) * alpha * t
        )
    return ts + (t0 - ts) * s


# --------------------------------------------------- phase change: ice and hot metal ---
def metal_on_ice_equilibrium(
    m_metal: float,
    c_metal: float,
    t_metal: float,
    m_ice: float,
    latent_heat: float = C.LATENT_HEAT_FUSION_WATER,
    c_water: float = C.C_WATER_DEFAULT,
) -> Tuple[float, float]:
    """Final temperature (degC) and melted ice mass (kg) when a metal at t_metal (degC)
    is brought into contact with ice at 0 degC. Adiabatic, perfect contact, no container.

    Case A - metal cools to 0 degC and only part of the ice melts:
        m_melt = m_metal c_metal t_metal / L,  valid when m_melt <= m_ice.
    Case B - all ice melts; final T_f from the energy balance
        m_metal c_metal (t_metal - T_f) = m_ice L + m_ice c_water T_f  =>
        T_f = (m_metal c_metal t_metal - m_ice L) / (m_metal c_metal + m_ice c_water).
    """
    if min(m_metal, c_metal, m_ice, latent_heat, c_water) < 0:
        raise ValueError("masses, heat capacities and latent heat must be non-negative")
    if t_metal <= 0.0:
        return t_metal, 0.0  # no heat flows from a metal at or below 0 degC
    q_avail = m_metal * c_metal * t_metal
    if latent_heat == 0.0:
        raise ValueError("latent heat must be positive for melting")
    if q_avail <= m_ice * latent_heat:
        return 0.0, q_avail / latent_heat
    t_final = (q_avail - m_ice * latent_heat) / (m_metal * c_metal + m_ice * c_water)
    return t_final, m_ice


def stefan_boltzmann_power(emissivity: float, area: float, t_kelvin: float, t_env_kelvin: float = 0.0) -> float:
    """Net radiative exchange P = e sigma A (T^4 - T_env^4) (Incropera Eq. 12.3)."""
    if not 0.0 <= emissivity <= 1.0:
        raise ValueError("emissivity must be in [0, 1]")
    return emissivity * C.SIGMA_SB * area * (t_kelvin ** 4 - t_env_kelvin ** 4)
