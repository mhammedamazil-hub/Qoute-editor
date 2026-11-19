import math

import pytest

from reality import constants as C
from reality import gravity as G
from reality import thermal as T


def test_uniform_field_is_constant_everywhere():
    f = G.UniformGravity((0.0, -1.62, 0.0))
    assert f.acceleration((0, 0, 0)) == f.acceleration((100.0, -5.0, 3.0))


def test_point_mass_inverse_square():
    b = G.GravityBody("b", 1.0, 0.1)
    a1 = math.sqrt(sum(x * x for x in b.acceleration((2.0, 0.0, 0.0))))
    a2 = math.sqrt(sum(x * x for x in b.acceleration((4.0, 0.0, 0.0))))
    assert a1 / a2 == pytest.approx(4.0, rel=1e-12)


def test_point_mass_at_centre_is_rejected():
    with pytest.raises(ValueError):
        G.GravityBody("b", 1.0, 0.1).acceleration((0.0, 0.0, 0.0))


def test_gravity_from_mass_uses_codata_g():
    assert G.gm_from_mass(1.0) == C.G_NEWTON


def test_orbital_period_kepler_third_law():
    # Earth-Moon-like check: circular orbit at 384,400 km around Earth.
    T_moon = G.orbital_period_circular(C.GM_EARTH, 3.844e8)
    assert T_moon / 86400.0 == pytest.approx(27.3, rel=0.01)


def test_circular_speed_consistent_with_period():
    gm, r = C.GM_EARTH, 7.0e6
    v = G.circular_speed(gm, r)
    assert 2 * math.pi * r / v == pytest.approx(G.orbital_period_circular(gm, r), rel=1e-12)


def test_sum_of_uniform_and_point_fields():
    field = G.acceleration_sum([G.UniformGravity((0.0, -9.8, 0.0)), G.surface_field(G.earth())], (0, 0, 0))
    assert field[1] == pytest.approx(-9.8 - G.earth().surface_gravity(), rel=1e-12)


def test_biot_number_small_for_metal_block():
    # Aluminium-like block, h = 25 W/m^2K, L_c = 0.01 m, k = 167 W/mK -> Bi << 0.1.
    bi = T.biot_number(25.0, 1e-6, 1e-4, 167.0)
    assert bi < 0.1


def test_biot_rejects_zero_area():
    with pytest.raises(ValueError):
        T.biot_number(1.0, 1.0, 0.0, 1.0)


def test_explicit_conduction_rejects_unstable_time_step():
    with pytest.raises(ValueError):
        # Fo = alpha dt / dx^2 = 1e-5 * 10 / 1e-4 = 1.0 > 0.5
        T.conduction_1d_explicit([0.0] * 5, alpha=1e-5, dx=0.01, dt=10.0, n_steps=1, t_left=1.0, t_right=0.0)


def test_conduction_keeps_boundaries_and_stays_bounded():
    temps = [20.0] * 21
    out = T.conduction_1d_explicit(temps, alpha=1e-5, dx=0.01, dt=0.4 * (0.01 ** 2) / 1e-5,  # Fo = 0.4
                                   n_steps=200, t_left=100.0, t_right=20.0)
    assert out[0] == 100.0 and out[-1] == 20.0
    assert all(20.0 - 1e-9 <= v <= 100.0 + 1e-9 for v in out)  # maximum principle


def test_ice_full_melt_returns_positive_final_temperature():
    t_f, melted = T.metal_on_ice_equilibrium(1.0, 449.0, 800.0, 0.1)
    assert t_f > 0 and melted == pytest.approx(0.1)


def test_metal_below_zero_does_not_melt_ice():
    assert T.metal_on_ice_equilibrium(1.0, 449.0, -20.0, 0.5) == (-20.0, 0.0)


def test_stefan_boltzmann_rejects_bad_emissivity():
    with pytest.raises(ValueError):
        T.stefan_boltzmann_power(1.5, 1.0, 300.0)
