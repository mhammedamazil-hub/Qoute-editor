import math

import pytest

from reality import acoustics as A
from reality import fracture as F
from reality import optics as O
from reality import structures as S
from reality.materials import default_database

DB = default_database()


# ------------------------------------------------------------------- optics ---
def test_snell_total_internal_reflection_returns_none():
    assert O.snell_angle(1.5, math.radians(60), 1.0) is None


def test_critical_angle_requires_n1_greater_than_n2():
    with pytest.raises(ValueError):
        O.critical_angle(1.0, 1.5)


def test_fresnel_total_internal_reflection_flags_and_R_one():
    r = O.fresnel(1.5, 1.0, math.radians(60))
    assert r.total_internal_reflection and r.R_unpolarized == 1.0


def test_fresnel_grazing_incidence_reflects_everything():
    r = O.fresnel(1.0, 1.5, math.radians(89.999))
    assert r.R_unpolarized > 0.99


def test_fresnel_s_and_p_differ_off_normal():
    r = O.fresnel(1.0, 1.5, math.radians(45))
    assert r.R_s > r.R_p > 0


def test_sellmeier_rejects_out_of_range_wavelength():
    with pytest.raises(ValueError):
        O.sellmeier_bk7(0.1e-6)


def test_normal_reflectance_symmetric_in_indices():
    assert O.normal_incidence_reflectance(1.0, 1.5) == pytest.approx(O.normal_incidence_reflectance(1.5, 1.0))


def test_dispersion_normal_blue_higher_than_red():
    # Normal dispersion: index decreases with wavelength in the visible.
    assert O.sellmeier_bk7(486.1e-9) > O.sellmeier_bk7(656.3e-9)


def test_glass_index_in_database_matches_optics_scale():
    n = DB.get("glass").refractive_index
    assert 1.5 < n < 1.55


# ---------------------------------------------------------------- acoustics ---
def test_wave_speed_increases_with_temperature():
    assert A.speed_of_sound_ideal_gas(313.15) > A.speed_of_sound_ideal_gas(273.15)


def test_wave_speed_from_modulus_for_water_order_of_magnitude():
    c = A.speed_of_sound_from_modulus(2.2e9, 998.0)
    assert 1400 < c < 1600


def test_acoustic_impedance_water_much_larger_than_air():
    za = A.acoustic_impedance(1.204, 343.0)
    zw = A.acoustic_impedance(998.0, 1482.0)
    assert zw / za > 3000


def test_doppler_receding_source_lowers_pitch():
    assert A.doppler_frequency(1000.0, 343.0, 0.0, -30.0) < 1000.0


def test_doppler_rejects_supersonic_source():
    with pytest.raises(ValueError):
        A.doppler_frequency(1000.0, 343.0, 0.0, 400.0)


def test_pipe_harmonics_are_odd_multiples():
    f1 = A.closed_open_pipe_frequency(1, 1.0, 340.0)
    assert A.closed_open_pipe_frequency(2, 1.0, 340.0) == pytest.approx(3 * f1)


def test_string_second_harmonic_is_double_fundamental():
    assert A.string_frequency(2, 0.65, 100.0, 0.0005) == pytest.approx(2 * A.string_frequency(1, 0.65, 100.0, 0.0005))


def test_spl_rejects_nonpositive_pressure():
    with pytest.raises(ValueError):
        A.sound_pressure_level_db(0.0)


# ----------------------------------------------------------------- fracture ---
def test_brittle_glass_fails_at_small_flaw_high_stress():
    glass = DB.get("glass")
    a = F.assess(glass, applied_stress=120e6, flaw_half_length=20e-6)
    assert a.failed and a.mode == "fracture"
    assert a.critical_stress_flaw == pytest.approx(F.fracture_stress(glass.fracture_toughness, 20e-6))


def test_glass_survives_small_stress_for_small_flaw():
    glass = DB.get("glass")
    a = F.assess(glass, applied_stress=10e6, flaw_half_length=10e-6)
    assert not a.failed and a.safety_factor > 1


def test_steel_yields_not_fractures_at_moderate_stress():
    steel = DB.get("steel")
    a = F.assess(steel, applied_stress=400e6, flaw_half_length=1e-3)
    assert a.failed and a.mode == "yield"


def test_brittle_assessment_requires_flaw():
    with pytest.raises(ValueError):
        F.assess(DB.get("glass"), 10e6, flaw_half_length=0.0)


def test_elastomer_has_no_failure_model_here():
    with pytest.raises(ValueError):
        F.assess(DB.get("rubber"), 1e6, flaw_half_length=1e-3)


def test_stress_intensity_scales_with_sqrt_flaw():
    k1 = F.stress_intensity(100e6, 1e-4)
    k2 = F.stress_intensity(100e6, 4e-4)
    assert k2 / k1 == pytest.approx(2.0)


def test_griffith_energy_plane_strain_is_smaller_than_plane_stress():
    g_ps = F.griffith_energy_release_rate(0.75e6, 72e9, 0.2, plane_strain=False)
    g_pe = F.griffith_energy_release_rate(0.75e6, 72e9, 0.2, plane_strain=True)
    assert g_pe < g_ps


# ---------------------------------------------------------------- structures ---
def test_cantilever_tip_deflection_scales_with_cube_of_length():
    d1 = S.cantilever_tip_deflection(10.0, 1.0, 200e9, 1e-6)
    d2 = S.cantilever_tip_deflection(10.0, 2.0, 200e9, 1e-6)
    assert d2 / d1 == pytest.approx(8.0)


def test_cantilever_root_stress_formula():
    I = S.rectangular_second_moment(0.02, 0.01)
    assert S.cantilever_root_bending_stress(100.0, 0.5, 0.005, I) == pytest.approx(100.0 * 0.5 * 0.005 / I)


def test_rectangle_inertia_rejects_nonpositive_dimensions():
    with pytest.raises(ValueError):
        S.rectangular_second_moment(0.0, 0.01)


def test_double_integration_converges_to_analytic_with_refinement():
    f, L, E, I = 10.0, 0.5, 200e9, 1.6667e-9
    ana = S.cantilever_tip_deflection(f, L, E, I)
    coarse = abs(S.cantilever_deflection_by_double_integration(f, L, E, I, n=50) - ana)
    fine = abs(S.cantilever_deflection_by_double_integration(f, L, E, I, n=2000) - ana)
    assert fine < coarse
