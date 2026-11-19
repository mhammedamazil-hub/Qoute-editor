"""Scientific validation registry.

Each ``ValidationCase`` compares a solver result with an analytic, textbook or
conservation-law reference and records the measured error and the tolerance.
The pytest suite asserts every case and ``tools/run_validation.py`` writes the
results to ``reality/VALIDATION_REPORT.md``.

A solver is only described as validated if every case that exercises it passes.
Cases are deliberately independent of the implementation where possible (an
analytic closed form, a separate numerical integration, or a conservation law).
"""

from __future__ import annotations

import functools
import math
from dataclasses import dataclass
from typing import Callable, List, Tuple

from . import acoustics, constants as C, fracture, gravity, integrators, mechanics, optics, structures, thermal
from . import units as U
from .materials import FIELD_DIMS, default_database


@dataclass(frozen=True)
class ValidationCase:
    case_id: str
    domain: str
    solver: str
    description: str
    kind: str                       # analytic | numerical-vs-analytic | conservation | textbook | database
    reference: float
    reference_source: str
    run: Callable[[], float]        # returns the measured value
    tolerance: float                # relative tolerance (absolute if reference == 0)

    def evaluate(self) -> Tuple[float, float, bool]:
        measured = self.run()
        if self.reference == 0.0:
            err = abs(measured)
            ok = err <= self.tolerance
        else:
            err = abs(measured - self.reference) / abs(self.reference)
            ok = err <= self.tolerance
        return measured, err, ok


def _rel(a: float, b: float) -> float:
    return abs(a - b) / max(abs(b), 1e-300)


# ----------------------------------------------------------- mechanics cases ---
def _freefall_speed_rk4_vs_analytic() -> float:
    m, rho, cd, r = 0.1, 1.2, 0.47, 0.05
    area = math.pi * r * r
    k = mechanics.quadratic_drag_coefficient(rho, cd, area)
    t = 3.0
    v_num, _ = mechanics.freefall_quadratic_drag_numeric(t, m, C.STANDARD_GRAVITY, k, 1e-3)
    v_ana, _ = mechanics.freefall_quadratic_drag_analytic(t, m, C.STANDARD_GRAVITY, k)
    return _rel(v_num, v_ana)


def _freefall_distance_rk4_vs_analytic() -> float:
    m, rho, cd, r = 0.1, 1.2, 0.47, 0.05
    k = mechanics.quadratic_drag_coefficient(rho, cd, math.pi * r * r)
    t = 3.0
    _, s_num = mechanics.freefall_quadratic_drag_numeric(t, m, C.STANDARD_GRAVITY, k, 1e-3)
    _, s_ana = mechanics.freefall_quadratic_drag_analytic(t, m, C.STANDARD_GRAVITY, k)
    return _rel(s_num, s_ana)


def _freefall_terminal_velocity() -> float:
    m, rho, cd, r = 0.1, 1.2, 0.47, 0.05
    k = mechanics.quadratic_drag_coefficient(rho, cd, math.pi * r * r)
    # Terminal speed should approach sqrt(mg/k); check after 30 s (tanh saturates).
    v_num, _ = mechanics.freefall_quadratic_drag_numeric(30.0, m, C.STANDARD_GRAVITY, k, 1e-2)
    return _rel(v_num, mechanics.terminal_velocity(m, C.STANDARD_GRAVITY, k))


def _projectile_range() -> float:
    v0, th = 20.0, math.radians(30.0)
    rng, _h, _t = mechanics.projectile_numeric(v0, th, C.STANDARD_GRAVITY, 1e-3)
    return _rel(rng, mechanics.projectile_range_no_drag(v0, th, C.STANDARD_GRAVITY))


def _projectile_height() -> float:
    v0, th = 20.0, math.radians(60.0)
    _r, h, _t = mechanics.projectile_numeric(v0, th, C.STANDARD_GRAVITY, 1e-3)
    return _rel(h, mechanics.projectile_max_height_no_drag(v0, th, C.STANDARD_GRAVITY))


def _pendulum_small_angle_limit() -> float:
    length = 1.0
    exact = mechanics.pendulum_period_exact(length, C.STANDARD_GRAVITY, 1e-3)
    return _rel(exact, mechanics.pendulum_period_small_angle(length, C.STANDARD_GRAVITY))


def _pendulum_large_amplitude_ratio() -> float:
    # Series (Landau & Lifshitz Sec. 48): T/T0 = 1 + th^2/16 + 11 th^4/3072 + 173 th^6/737280 + 22931 th^8/1321205760 + ...
    th = 0.5                                # series truncation error ~ 1.4e-9 here (theta^10 term)
    series = (1.0 + th ** 2 / 16 + 11 * th ** 4 / 3072 + 173 * th ** 6 / 737280
              + 22931 * th ** 8 / 1321205760)
    ratio = mechanics.pendulum_period_exact(1.0, C.STANDARD_GRAVITY, th) / mechanics.pendulum_period_small_angle(1.0, C.STANDARD_GRAVITY)
    return _rel(ratio, series)


def _pendulum_rk4_vs_exact() -> float:
    th = 1.0
    num = mechanics.pendulum_period_numeric(1.0, C.STANDARD_GRAVITY, th, 2e-3)
    ex = mechanics.pendulum_period_exact(1.0, C.STANDARD_GRAVITY, th)
    return _rel(num, ex)


def _collision_equal_masses_swap() -> float:
    v1p, v2p = mechanics.collide_1d(1.0, 2.0, 1.0, 0.0, 1.0)
    return abs(v1p - 0.0) + abs(v2p - 2.0)


def _collision_momentum() -> float:
    m1, v1, m2, v2, e = 2.0, 3.0, 0.7, -1.5, 0.6
    v1p, v2p = mechanics.collide_1d(m1, v1, m2, v2, e)
    p0 = m1 * v1 + m2 * v2
    p1 = m1 * v1p + m2 * v2p
    return abs(p1 - p0) / abs(p0)


def _collision_energy_elastic() -> float:
    m1, v1, m2, v2 = 2.0, 3.0, 0.7, -1.5
    v1p, v2p = mechanics.collide_1d(m1, v1, m2, v2, 1.0)
    e0 = mechanics.kinetic_energy(m1, v1) + mechanics.kinetic_energy(m2, v2)
    e1 = mechanics.kinetic_energy(m1, v1p) + mechanics.kinetic_energy(m2, v2p)
    return abs(e1 - e0) / e0


def _collision_energy_loss_formula() -> float:
    # Kinetic energy lost in a 1D collision: dE = mu (1 - e^2) (v1 - v2)^2 / 2, mu = m1 m2/(m1+m2).
    m1, v1, m2, v2, e = 2.0, 3.0, 0.7, -1.5, 0.6
    v1p, v2p = mechanics.collide_1d(m1, v1, m2, v2, e)
    e0 = mechanics.kinetic_energy(m1, v1) + mechanics.kinetic_energy(m2, v2)
    e1 = mechanics.kinetic_energy(m1, v1p) + mechanics.kinetic_energy(m2, v2p)
    mu = m1 * m2 / (m1 + m2)
    return _rel(e0 - e1, mu * (1 - e * e) * (v1 - v2) ** 2 / 2)


def _orbit_circular_period() -> float:
    gm, r = 1.0, 1.0
    period = 2 * math.pi * math.sqrt(r ** 3 / gm)
    n_steps = int(round(period / 1e-3))
    dt = period / n_steps                   # exact step so the integration ends at t = T
    xs, _ = mechanics.kepler_orbit_verlet(gm, [r, 0.0], [0.0, 1.0], dt, n_steps)
    x_end = xs[-1]
    # Position returns to the start after one period; return the distance error.
    return math.hypot(x_end[0] - r, x_end[1]) / r


def _orbit_energy_drift() -> float:
    gm = 1.0
    x0, v0 = [1.0, 0.0], [0.0, 1.2]         # eccentric bound orbit
    e0 = mechanics.kepler_energy(gm, x0, v0)
    n = 20000                               # t = 100 at dt = 5e-3, ~6.7 orbits (a = 1.79, T = 2 pi a^1.5 ~ 15)
    xs, vs = mechanics.kepler_orbit_verlet(gm, x0, v0, 5e-3, n)
    drift = max(abs(mechanics.kepler_energy(gm, x, v) - e0) / abs(e0) for x, v in zip(xs[::50], vs[::50]))
    return drift


def _orbit_angular_momentum() -> float:
    gm = 1.0
    x0, v0 = [1.0, 0.0], [0.0, 1.2]
    h0 = mechanics.kepler_angular_momentum(x0, v0)
    xs, vs = mechanics.kepler_orbit_verlet(gm, x0, v0, 5e-3, 20000)
    return max(abs(mechanics.kepler_angular_momentum(x, v) - h0) / abs(h0) for x, v in zip(xs[::50], vs[::50]))


# ----------------------------------------------------------------- gravity ---
def _earth_surface_gravity() -> float:
    return _rel(gravity.earth().surface_gravity(), 9.8202)


def _moon_surface_gravity() -> float:
    return _rel(gravity.moon().surface_gravity(), 1.62)


def _mars_surface_gravity() -> float:
    # Published Mars surface gravity is ~3.71 m/s^2 at the equatorial radius (3396 km).
    # The mean radius used here (3389.5 km) gives ~3.73 m/s^2; the 1 % tolerance reflects that.
    return _rel(gravity.mars().surface_gravity(), 3.71)


def _gravity_superposition() -> float:
    # Two equal bodies: field at the midpoint cancels; field 2 units away is the sum of two attractions.
    b1 = gravity.GravityBody("a", 1.0, 0.1, (-1.0, 0.0, 0.0))
    b2 = gravity.GravityBody("b", 1.0, 0.1, (1.0, 0.0, 0.0))
    field = gravity.PointMassGravity((b1, b2))
    mid = field.acceleration((0.0, 0.0, 0.0))
    return abs(mid[0]) + abs(mid[1]) + abs(mid[2])


# ----------------------------------------------------------------- thermal ---
def _lumped_cooling_vs_ode() -> float:
    h, area, mass, cp, t0, tinf = 25.0, 0.02, 0.5, 900.0, 400.0, 20.0
    t_end = 300.0
    exact = thermal.lumped_cooling(t_end, t0, tinf, h, area, mass, cp)
    k = h * area / (mass * cp)
    num = integrators.integrate_rk4(lambda _t, y: [-k * (y[0] - tinf)], 0.0, [t0], t_end, 0.05)[0]
    return _rel(num, exact)


def _conduction_vs_slab_analytic() -> float:
    length, alpha = 0.1, 1.2e-5
    n = 41
    dx = length / (n - 1)
    fo = 0.4
    dt = fo * dx * dx / alpha
    t0, ts = 300.0, 500.0
    t_final = 0.6 * length * length / alpha
    steps = int(round(t_final / dt))
    init = [t0] * n
    num = thermal.conduction_1d_explicit(init, alpha, dx, dt, steps, ts, ts)
    t_used = steps * dt
    worst = 0.0
    for i in range(1, n - 1):
        x = i * dx
        ana = thermal.slab_dirichlet_analytic(x, t_used, length, alpha, t0, ts)
        # Compare dimensionless theta = (T - Ts)/(T0 - Ts), which is O(1) and avoids divide-by-small.
        theta_num = (num[i] - ts) / (t0 - ts)
        theta_ana = (ana - ts) / (t0 - ts)
        worst = max(worst, abs(theta_num - theta_ana))
    return worst


def _ice_partial_melt() -> float:
    # 1 kg iron at 300 degC on ice: heat 449*300 J melts 134700/333550 kg of ice; metal ends at 0 degC.
    t_f, melted = thermal.metal_on_ice_equilibrium(1.0, 449.0, 300.0, 1.0)
    expected = 449.0 * 300.0 / C.LATENT_HEAT_FUSION_WATER
    return _rel(melted, expected) + abs(t_f)


def _ice_full_melt_energy_balance() -> float:
    m_m, c_m, t_m, m_i = 1.0, 449.0, 800.0, 0.1
    t_f, melted = thermal.metal_on_ice_equilibrium(m_m, c_m, t_m, m_i)
    lhs = m_m * c_m * (t_m - t_f)                       # heat released by metal
    rhs = m_i * (C.LATENT_HEAT_FUSION_WATER + C.C_WATER_DEFAULT * t_f)  # heat absorbed by ice+water
    return abs(lhs - rhs) / lhs + abs(melted - m_i) / m_i


def _stefan_boltzmann_300k() -> float:
    # sigma * T^4 at 300 K = 459.3 W/m^2 (blackbody emittance).
    p = thermal.stefan_boltzmann_power(1.0, 1.0, 300.0)
    return _rel(p, 459.27)


# ------------------------------------------------------------------ optics ---
def _snell_30deg_air_to_glass() -> float:
    th2 = optics.snell_angle(1.0, math.radians(30.0), 1.5)
    return _rel(th2, math.asin(0.5 / 1.5))


def _critical_angle_glass_air() -> float:
    return _rel(math.degrees(optics.critical_angle(1.5, 1.0)), 41.81)


def _normal_reflectance_air_glass() -> float:
    return _rel(optics.fresnel(1.0, 1.5, 0.0).R_unpolarized, 0.04)


def _brewster_zero_reflectance() -> float:
    thb = optics.brewster_angle(1.0, 1.5)
    return abs(optics.fresnel(1.0, 1.5, thb).R_p)


def _fresnel_energy_conservation_s() -> float:
    n1, n2, ti = 1.0, 1.5, math.radians(45.0)
    tt = optics.snell_angle(n1, ti, n2)
    ci, ct = math.cos(ti), math.cos(tt)
    r = optics.fresnel(n1, n2, ti)
    t_amp = 2 * n1 * ci / (n1 * ci + n2 * ct)
    T = (n2 * ct) / (n1 * ci) * t_amp * t_amp
    return abs(r.R_s + T - 1.0)


def _bk7_nd() -> float:
    return _rel(optics.sellmeier_bk7(587.56e-9), 1.5168)


# ---------------------------------------------------------------- acoustics ---
def _sound_speed_20c() -> float:
    return _rel(acoustics.speed_of_sound_ideal_gas(293.15), 343.2)


def _air_water_reflection() -> float:
    c_air = acoustics.speed_of_sound_ideal_gas(293.15)
    z_air = acoustics.acoustic_impedance(1.204, c_air)
    z_water = acoustics.acoustic_impedance(998.2, 1481.9)
    return _rel(acoustics.intensity_reflection_normal(z_air, z_water), 0.9989)


def _reflection_transmission_sum() -> float:
    z1, z2 = 413.0, 1.48e6
    return abs(acoustics.intensity_reflection_normal(z1, z2) + acoustics.intensity_transmission_normal(z1, z2) - 1.0)


def _doppler_approaching() -> float:
    f = acoustics.doppler_frequency(1000.0, 343.0, 0.0, 30.0)
    return _rel(f, 343.0 / 313.0 * 1000.0)


def _pipe_fundamental() -> float:
    return _rel(acoustics.closed_open_pipe_frequency(1, 0.5, 343.0), 171.5)


def _spl_two_pascal() -> float:
    return _rel(acoustics.sound_pressure_level_db(2.0), 100.0)


# ----------------------------------------------------------------- fracture ---
def _glass_critical_stress_10um() -> float:
    k_ic = 0.75e6
    return _rel(fracture.fracture_stress(k_ic, 10e-6), 133.8e6)


def _critical_flaw_roundtrip() -> float:
    k_ic, a = 0.75e6, 25e-6
    sc = fracture.fracture_stress(k_ic, a)
    return _rel(fracture.critical_flaw_size(k_ic, sc), a)


def _griffith_surface_energy_glass() -> float:
    gs = fracture.griffith_surface_energy(0.75e6, 72e9, 0.20)
    return _rel(gs, 3.9)


def _glass_vs_steel_outcome() -> float:
    glass = default_db().get("glass")
    steel = default_db().get("steel")
    g = fracture.assess(glass, 100e6, flaw_half_length=0.1e-3)
    s = fracture.assess(steel, 100e6, flaw_half_length=0.1e-3)
    # Expected: glass fractures (sigma_c ~ 42 MPa), steel survives (sigma_y = 370 MPa).
    return 0.0 if (g.failed and g.mode == "fracture" and not s.failed) else 1.0


# ---------------------------------------------------------------- structures ---
def _cantilever_tip_double_integration() -> float:
    f, L, E, I = 10.0, 0.5, 200e9, 1.6667e-9
    num = structures.cantilever_deflection_by_double_integration(f, L, E, I, n=4000)
    ana = structures.cantilever_tip_deflection(f, L, E, I)
    return _rel(num, ana)


def _cantilever_frequency_constant() -> float:
    # omega_1 = 3.516015 sqrt(EI/(m L^3)) (Rao, Mechanical Vibrations; Blevins, Formulas for Natural Frequency).
    E, I, m_per_len, L = 200e9, 1.6667e-9, 1.57, 0.5
    f1 = structures.cantilever_first_frequency(E, I, m_per_len, L)
    m_total = m_per_len * L
    omega_ref = 3.516015 * math.sqrt(E * I / (m_total * L ** 3))
    return _rel(2 * math.pi * f1, omega_ref)


def _rect_inertia() -> float:
    return _rel(structures.rectangular_second_moment(0.02, 0.01), 1.6667e-9)


# ------------------------------------------------------------------ database ---
@functools.lru_cache(maxsize=1)
def default_db():
    return default_database()


def _database_all_valid() -> float:
    db = default_db()
    return float(sum(len(m.validate()) for m in db))


def _database_dimension_binding() -> float:
    glass = default_db().get("glass")
    dim_ok = glass.q("fracture_toughness").dim == FIELD_DIMS["fracture_toughness"] == U.FRACTURE_TOUGHNESS
    return 0.0 if dim_ok else 1.0


# ----------------------------------------------------------- objects cases ---
def _fixture_material(density: float):
    from .materials import Material
    return Material(name="test", category="test", phase="solid", behavior="brittle",
                    density=density, specific_heat=1.0, thermal_conductivity=1.0,
                    fracture_toughness=1.0e6, source="validation fixture", uncertainty="none")


def _obj_sphere_mass() -> float:
    from . import objects as O
    obj = O.PhysicalObject("sphere", O.Sphere(0.1), _fixture_material(1000.0))
    return obj.mass().value  # kg; reference rho * 4/3 pi r^3


def _obj_sphere_inertia() -> float:
    from . import objects as O
    obj = O.PhysicalObject("sphere", O.Sphere(0.1), _fixture_material(1000.0))
    return obj.principal_inertia()[0].value  # kg m^2; reference 2/5 m r^2


def _obj_box_inertia() -> float:
    from . import objects as O
    obj = O.PhysicalObject("box", O.Box((0.2, 0.4, 0.6)), _fixture_material(2000.0))
    return obj.principal_inertia()[0].value  # about x: m (b^2 + c^2)/12


def _obj_cylinder_transverse() -> float:
    from . import objects as O
    obj = O.PhysicalObject("cyl", O.Cylinder(0.05, 0.3), _fixture_material(1500.0))
    return obj.principal_inertia()[0].value  # m (3 r^2 + h^2)/12


def _obj_cylinder_axial() -> float:
    from . import objects as O
    obj = O.PhysicalObject("cyl", O.Cylinder(0.05, 0.3), _fixture_material(1500.0))
    return obj.principal_inertia()[2].value  # m r^2 / 2


def _obj_parallel_axis_sphere() -> float:
    # Sphere inertia about a surface point, along x: I_yy = (2/5 + 1) m r^2 = 7/5 m r^2.
    from . import objects as O
    obj = O.PhysicalObject("sphere", O.Sphere(0.1), _fixture_material(1000.0))
    return obj.inertia_about_point((0.1, 0.0, 0.0))[1][1].value


def _obj_weight_ice_kg() -> float:
    # 1 m^3 of ice at standard gravity: weight / g gives the mass in kg; reference 917.
    from . import objects as O
    ice = default_database().get("ice")
    obj = O.PhysicalObject("ice", O.Box((1.0, 1.0, 1.0)), ice)
    return obj.weight().value / C.STANDARD_GRAVITY


def _obj_heat_capacity_water() -> float:
    # 1 litre of water: heat capacity in J/K from the object model (m c_p).
    from . import objects as O
    water = default_database().get("water")
    obj = O.PhysicalObject("water", O.Box((0.1, 0.1, 0.1)), water)
    return obj.heat_capacity().value


CASES: List[ValidationCase] = [
    # --- classical mechanics
    ValidationCase("MECH-01", "mechanics", "freefall (quadratic drag)", "RK4 speed vs analytic v_t tanh(gt/v_t) at t = 3 s",
                   "numerical-vs-analytic", 0.0, "Analytic solution (Newton's 2nd law, F_d = k v^2)", _freefall_speed_rk4_vs_analytic, 1e-8),
    ValidationCase("MECH-02", "mechanics", "freefall (quadratic drag)", "RK4 distance vs analytic (v_t^2/g) ln cosh(gt/v_t) at t = 3 s",
                   "numerical-vs-analytic", 0.0, "Analytic solution", _freefall_distance_rk4_vs_analytic, 1e-7),
    ValidationCase("MECH-03", "mechanics", "freefall (quadratic drag)", "Terminal speed reached after 30 s equals sqrt(mg/k)",
                   "numerical-vs-analytic", 0.0, "Terminal velocity, Newton's 2nd law", _freefall_terminal_velocity, 1e-4),
    ValidationCase("MECH-04", "mechanics", "projectile", "Range at 30 deg, v0 = 20 m/s vs v^2 sin(2th)/g",
                   "numerical-vs-analytic", 0.0, "Analytic projectile range (no drag)", _projectile_range, 1e-6),
    ValidationCase("MECH-05", "mechanics", "projectile", "Maximum height at 60 deg vs v^2 sin^2(th)/(2g)",
                   "numerical-vs-analytic", 0.0, "Analytic projectile height (no drag)", _projectile_height, 1e-6),
    ValidationCase("MECH-06", "mechanics", "pendulum", "Exact period formula tends to 2 pi sqrt(L/g) at 1 mrad",
                   "analytic", 0.0, "Small-angle limit, Landau & Lifshitz Mechanics Sec. 48", _pendulum_small_angle_limit, 1e-6),
    ValidationCase("MECH-07", "mechanics", "pendulum", "Exact period vs Landau series (5 terms) T/T0 at 0.5 rad amplitude",
                   "textbook", 0.0, "Landau & Lifshitz Mechanics Sec. 48 (series in theta_0)", _pendulum_large_amplitude_ratio, 1e-8),
    ValidationCase("MECH-08", "mechanics", "pendulum", "RK4 measured period vs exact period at 1 rad",
                   "numerical-vs-analytic", 0.0, "Exact elliptic-integral period", _pendulum_rk4_vs_exact, 1e-5),
    ValidationCase("MECH-09", "mechanics", "collision 1D", "Equal masses, elastic: velocities swap",
                   "analytic", 0.0, "Elastic collision algebra (momentum + energy)", _collision_equal_masses_swap, 1e-12),
    ValidationCase("MECH-10", "mechanics", "collision 1D", "Momentum conserved for inelastic collision (e = 0.6)",
                   "conservation", 0.0, "Linear momentum conservation", _collision_momentum, 1e-12),
    ValidationCase("MECH-11", "mechanics", "collision 1D", "Kinetic energy conserved for elastic collision",
                   "conservation", 0.0, "Energy conservation (elastic)", _collision_energy_elastic, 1e-12),
    ValidationCase("MECH-12", "mechanics", "collision 1D", "Energy loss equals mu (1 - e^2) (v1 - v2)^2 / 2",
                   "analytic", 0.0, "Coefficient-of-restitution energy balance", _collision_energy_loss_formula, 1e-9),
    ValidationCase("MECH-13", "mechanics", "orbits (Verlet)", "Circular orbit returns to start after one period (dt = 1e-3)",
                   "numerical-vs-analytic", 0.0, "Kepler's third law, T = 2 pi sqrt(r^3/GM)", _orbit_circular_period, 1e-4),
    ValidationCase("MECH-14", "mechanics", "orbits (Verlet)", "Specific energy drift over ~6.7 eccentric orbits",
                   "conservation", 0.0, "Energy conservation; Verlet is symplectic so drift stays bounded", _orbit_energy_drift, 1e-4),
    ValidationCase("MECH-15", "mechanics", "orbits (Verlet)", "Specific angular momentum drift over ~6.7 eccentric orbits",
                   "conservation", 0.0, "Angular momentum conservation for central force", _orbit_angular_momentum, 1e-8),
    # --- gravity
    ValidationCase("GRAV-01", "gravity", "point mass", "Earth surface gravity GM/R^2 vs 9.8202 m/s^2",
                   "textbook", 0.0, "IERS 2010 GM and IAU mean radius; published mean surface g", _earth_surface_gravity, 5e-4),
    ValidationCase("GRAV-02", "gravity", "point mass", "Moon surface gravity vs 1.62 m/s^2",
                   "textbook", 0.0, "Published lunar surface gravity", _moon_surface_gravity, 5e-3),
    ValidationCase("GRAV-03", "gravity", "point mass", "Mars surface gravity vs 3.71 m/s^2 (mean-radius model)",
                   "textbook", 0.0, "Published Mars surface gravity (equatorial radius); model uses mean radius", _mars_surface_gravity, 1e-2),
    ValidationCase("GRAV-04", "gravity", "N-body superposition", "Equal bodies cancel at their midpoint",
                   "analytic", 0.0, "Symmetry of Newtonian superposition", _gravity_superposition, 1e-12),
    # --- thermal
    ValidationCase("THER-01", "thermal", "lumped capacitance", "Analytic exponential cooling vs RK4 ODE integration",
                   "numerical-vs-analytic", 0.0, "Newton's law of cooling, Incropera Sec. 5.1", _lumped_cooling_vs_ode, 1e-8),
    ValidationCase("THER-02", "thermal", "1D conduction (FTCS)", "Max error in dimensionless theta vs Fourier-series slab solution (Fo = 0.4)",
                   "numerical-vs-analytic", 0.0, "Carslaw & Jaeger (1959) Sec. 2.4; Incropera Sec. 5.5", _conduction_vs_slab_analytic, 1e-3),
    ValidationCase("THER-03", "thermal", "metal on ice", "Partial melt: ice melted and final temperature (1 kg Fe, 300 degC)",
                   "analytic", 0.0, "Latent-heat energy balance (Incropera Sec. 1.x)", _ice_partial_melt, 1e-6),
    ValidationCase("THER-04", "thermal", "metal on ice", "Full melt: energy balance residual (1 kg Fe, 800 degC, 0.1 kg ice)",
                   "conservation", 0.0, "Energy conservation during melting", _ice_full_melt_energy_balance, 1e-9),
    ValidationCase("THER-05", "thermal", "radiation", "Blackbody emittance sigma T^4 at 300 K",
                   "analytic", 0.0, "Stefan-Boltzmann law (CODATA/SI sigma)", _stefan_boltzmann_300k, 1e-4),
    # --- optics
    ValidationCase("OPT-01", "optics", "Snell's law", "Refraction angle, air to glass n = 1.5 at 30 deg",
                   "analytic", 0.0, "Snell's law (Born & Wolf Sec. 1.1)", _snell_30deg_air_to_glass, 1e-12),
    ValidationCase("OPT-02", "optics", "total internal reflection", "Critical angle glass to air (degrees)",
                   "analytic", 0.0, "asin(n2/n1)", _critical_angle_glass_air, 1e-3),
    ValidationCase("OPT-03", "optics", "Fresnel", "Normal-incidence reflectance air to glass = 4 %",
                   "analytic", 0.0, "R0 = ((n1-n2)/(n1+n2))^2 (Born & Wolf Sec. 1.5)", _normal_reflectance_air_glass, 1e-12),
    ValidationCase("OPT-04", "optics", "Fresnel", "p-polarized reflectance vanishes at Brewster angle",
                   "analytic", 0.0, "Brewster condition tan th_B = n2/n1", _brewster_zero_reflectance, 1e-12),
    ValidationCase("OPT-05", "optics", "Fresnel", "s-polarized energy balance R + T = 1 at 45 deg",
                   "conservation", 0.0, "Lossless interface energy conservation", _fresnel_energy_conservation_s, 1e-12),
    ValidationCase("OPT-06", "optics", "dispersion (BK7)", "Sellmeier index at 587.56 nm vs catalogue n_d = 1.5168",
                   "textbook", 0.0, "Schott N-BK7 datasheet (n_d)", _bk7_nd, 2e-4),
    # --- acoustics
    ValidationCase("ACOU-01", "acoustics", "wave speed", "Speed of sound in air at 20 degC vs 343.2 m/s",
                   "textbook", 0.0, "US Standard Atmosphere; Kinsler et al. Table 5.x", _sound_speed_20c, 1e-3),
    ValidationCase("ACOU-02", "acoustics", "impedance", "Air to water intensity reflection = 0.9989",
                   "textbook", 0.0, "Kinsler et al. Fundamentals of Acoustics (air-water example)", _air_water_reflection, 2e-4),
    ValidationCase("ACOU-03", "acoustics", "impedance", "Reflection + transmission = 1 (intensity)",
                   "conservation", 0.0, "Energy conservation at an impedance step", _reflection_transmission_sum, 1e-9),
    ValidationCase("ACOU-04", "acoustics", "Doppler", "Approaching source at 30 m/s: f' = f c/(c - v)",
                   "analytic", 0.0, "Doppler relation", _doppler_approaching, 1e-12),
    ValidationCase("ACOU-05", "acoustics", "resonance", "Closed-open pipe fundamental, L = 0.5 m: f1 = c/4L",
                   "analytic", 0.0, "Kinsler et al. Sec. 7", _pipe_fundamental, 1e-3),
    ValidationCase("ACOU-06", "acoustics", "level", "SPL of 2 Pa rms = 100 dB re 20 uPa",
                   "analytic", 0.0, "Definition of sound pressure level", _spl_two_pascal, 1e-12),
    # --- fracture
    ValidationCase("FRAC-01", "fracture", "LEFM", "Glass, 10 um flaw: critical stress K_Ic/sqrt(pi a) = 133.8 MPa",
                   "analytic", 0.0, "Irwin (1957) stress intensity; K_Ic from DTIC ARL-TR-8187 (via Saiwei Glass)", _glass_critical_stress_10um, 1e-3),
    ValidationCase("FRAC-02", "fracture", "LEFM", "Critical flaw size inverts the critical stress (round trip)",
                   "analytic", 0.0, "Algebraic inverse of K_I = Y sigma sqrt(pi a)", _critical_flaw_roundtrip, 1e-12),
    ValidationCase("FRAC-03", "fracture", "Griffith", "Effective surface energy from K_Ic, E, nu (plane stress) = 3.9 J/m^2",
                   "analytic", 0.0, "Griffith (1921); gamma_s = K^2/(2E)", _griffith_surface_energy_glass, 1e-2),
    ValidationCase("FRAC-04", "fracture", "material-aware failure", "Same 100 MPa on a 0.1 mm flaw: glass fractures, steel survives",
                   "analytic", 0.0, "LEFM (brittle) vs yield (ductile) criteria", _glass_vs_steel_outcome, 0.0),
    # --- structures
    ValidationCase("STRU-01", "structures", "Euler-Bernoulli beam", "Cantilever tip deflection: double integration vs F L^3/(3EI)",
                   "numerical-vs-analytic", 0.0, "Timoshenko & Gere, Mechanics of Materials", _cantilever_tip_double_integration, 1e-4),
    ValidationCase("STRU-02", "structures", "Euler-Bernoulli beam", "Cantilever fundamental frequency constant 3.516015",
                   "textbook", 0.0, "Rao, Mechanical Vibrations; Blevins, Formulas for Natural Frequency", _cantilever_frequency_constant, 1e-6),
    ValidationCase("STRU-03", "structures", "Euler-Bernoulli beam", "Rectangular second moment b h^3/12",
                   "analytic", 0.0, "Standard section property", _rect_inertia, 1e-4),
    # --- database
    ValidationCase("MAT-01", "materials", "database", "All built-in materials pass physical validation (error count)",
                   "database", 0.0, "Material.validate() rules", _database_all_valid, 0.0),
    ValidationCase("MAT-02", "materials", "database", "Fracture toughness property carries the Pa*sqrt(m) dimension",
                   "database", 0.0, "Dimensional analysis (units.py)", _database_dimension_binding, 0.0),
    # --- physical objects (Phase 2)
    ValidationCase("OBJ-01", "objects", "mass", "Solid sphere mass rho*(4/3)pi r^3 (r = 0.1 m, rho = 1000 kg/m^3)",
                   "textbook", 1000.0 * 4.0 / 3.0 * math.pi * 0.1 ** 3, "Volume of a sphere; mass = density x volume",
                   _obj_sphere_mass, 1e-12),
    ValidationCase("OBJ-02", "objects", "inertia", "Solid sphere moment of inertia 2/5 m r^2 about its centre",
                   "textbook", 0.4 * (1000.0 * 4.0 / 3.0 * math.pi * 0.1 ** 3) * 0.1 ** 2,
                   "Beer & Johnston, Vector Mechanics for Engineers (solid sphere, centroidal axis)",
                   _obj_sphere_inertia, 1e-12),
    ValidationCase("OBJ-03", "objects", "inertia", "Box moment of inertia m (b^2 + c^2)/12 about the x axis",
                   "textbook", 2000.0 * 0.2 * 0.4 * 0.6 * (0.4 ** 2 + 0.6 ** 2) / 12.0,
                   "Beer & Johnston (rectangular parallelepiped, centroidal axes)", _obj_box_inertia, 1e-12),
    ValidationCase("OBJ-04", "objects", "inertia", "Cylinder transverse inertia m (3 r^2 + h^2)/12 about x",
                   "textbook", 1500.0 * math.pi * 0.05 ** 2 * 0.3 * (3 * 0.05 ** 2 + 0.3 ** 2) / 12.0,
                   "Beer & Johnston (circular cylinder, centroidal transverse axis)", _obj_cylinder_transverse, 1e-12),
    ValidationCase("OBJ-05", "objects", "inertia", "Cylinder axial inertia m r^2 / 2 about z",
                   "textbook", 1500.0 * math.pi * 0.05 ** 2 * 0.3 * 0.05 ** 2 / 2.0,
                   "Beer & Johnston (circular cylinder, centroidal axial axis)", _obj_cylinder_axial, 1e-12),
    ValidationCase("OBJ-06", "objects", "parallel axis", "Sphere inertia about a surface point, I_yy = 7/5 m r^2",
                   "textbook", 1.4 * (1000.0 * 4.0 / 3.0 * math.pi * 0.1 ** 3) * 0.1 ** 2,
                   "Parallel-axis theorem I = I_cm + m d^2, applied to a solid sphere",
                   _obj_parallel_axis_sphere, 1e-12),
    ValidationCase("OBJ-07", "objects", "weight", "Weight of 1 m^3 ice divided by g equals its density (917 kg)",
                   "textbook", 917.0, "W = m g with g = 9.80665 m/s^2 (CGPM 1901); ice density 917 kg/m^3 (Petrenko & Whitworth)",
                   _obj_weight_ice_kg, 1e-12),
    ValidationCase("OBJ-08", "objects", "heat capacity", "Heat capacity of 1 litre of water, C = rho V c_p (J/K)",
                   "textbook", 998.2e-3 * 4182.0, "C = m c_p with rho = 998.2 kg/m^3 and c_p = 4182 J/(kg K) (database values)",
                   _obj_heat_capacity_water, 1e-12),
]


def run_all() -> List[Tuple[ValidationCase, float, float, bool]]:
    results = []
    for case in CASES:
        measured, err, ok = case.evaluate()
        results.append((case, measured, err, ok))
    return results
