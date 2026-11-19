"""Unit tests for the Phase 4 (Weibull), Phase 7 (hydrostatics), Phase 8 (2D conduction),
and Phase 9 (population) first slices."""


import pytest

from reality import biology as B
from reality import constants as C
from reality import hydrostatics as H
from reality import thermal2d as T
from reality import weibull as W


# ---------------------------------------------------------------- Weibull
def test_failure_probability_is_monotone_and_bounded():
    ps = [W.failure_probability(s, 100.0, 5.0) for s in (0.0, 50.0, 100.0, 150.0, 300.0)]
    assert ps[0] == 0.0
    assert all(a < b for a, b in zip(ps, ps[1:]))
    assert all(0.0 <= p <= 1.0 for p in ps)  # saturates to 1.0 at (300/100)^5 = 243 in float


def test_stress_at_probability_inverts_failure_probability():
    for p in (0.01, 0.1, 0.5, 0.9):
        s = W.stress_at_probability(p, 200.0, 12.0, volume_ratio=3.0)
        assert W.failure_probability(s, 200.0, 12.0, volume_ratio=3.0) == pytest.approx(p, rel=1e-12)


def test_larger_volume_fails_at_lower_stress():
    assert W.median_strength(100.0, 8.0, 10.0) < W.median_strength(100.0, 8.0, 1.0)


def test_size_effect_is_symmetric_under_swap():
    r = W.size_effect_ratio(1.0, 4.0, 6.0)
    assert r * W.size_effect_ratio(4.0, 1.0, 6.0) == pytest.approx(1.0, rel=1e-14)


@pytest.mark.parametrize("call", [
    lambda: W.failure_probability(1.0, 0.0, 5.0),
    lambda: W.failure_probability(1.0, 1.0, -1.0),
    lambda: W.failure_probability(-1.0, 1.0, 5.0),
    lambda: W.stress_at_probability(1.0, 1.0, 5.0),
    lambda: W.stress_at_probability(-0.1, 1.0, 5.0),
    lambda: W.median_ranks(0),
    lambda: W.fit_weibull([1.0, 2.0]),
    lambda: W.fit_weibull([3.0, 3.0, 3.0]),
    lambda: W.effective_volume([1.0], [1.0, 2.0], 1.0, 5.0),
    lambda: W.effective_volume([1.0], [-1.0], 1.0, 5.0),
])
def test_weibull_rejects_invalid_input(call):
    with pytest.raises(ValueError):
        call()


def test_median_ranks_are_strictly_increasing_inside_unit_interval():
    f = W.median_ranks(10)
    assert all(0.0 < a < b < 1.0 for a, b in zip(f, f[1:]))


# ---------------------------------------------------------------- hydrostatics
def test_pressure_is_linear_in_depth():
    p1 = H.pressure_at_depth(1.0, 1000.0)
    p2 = H.pressure_at_depth(2.0, 1000.0)
    assert (p2 - C.P_ATM) == pytest.approx(2.0 * (p1 - C.P_ATM))


def test_archimedes_force_equals_displaced_weight():
    assert H.buoyant_force(1000.0, 0.5) == pytest.approx(1000.0 * C.STANDARD_GRAVITY * 0.5)


def test_floating_fraction_is_capped_for_sinking_bodies():
    assert H.floating_submerged_fraction(2000.0, 1000.0) == 1.0


def test_apparent_weight_of_neutrally_buoyant_body_is_zero():
    m, rho = 2.0, 500.0
    v = m / rho
    assert H.apparent_weight(m, rho, v) == pytest.approx(0.0, abs=1e-12)


@pytest.mark.parametrize("call", [
    lambda: H.pressure_at_depth(-1.0, 1000.0),
    lambda: H.pressure_at_depth(1.0, 0.0),
    lambda: H.buoyant_force(1000.0, -1.0),
    lambda: H.floating_submerged_fraction(0.0, 1000.0),
    lambda: H.apparent_weight(0.0, 1000.0, 1.0),
])
def test_hydrostatics_rejects_invalid_input(call):
    with pytest.raises(ValueError):
        call()


# ---------------------------------------------------------------- 2D conduction
def test_2d_solver_decays_the_mode():
    t_mid = T.solve_square(15, 0.01, 1.0, 2.0)
    t_end = T.solve_square(15, 0.01, 1.0, 4.0)
    peak_mid = max(abs(v) for row in t_mid for v in row)
    peak_end = max(abs(v) for row in t_end for v in row)
    assert peak_end < peak_mid < 1.0


def test_2d_solver_is_symmetric_under_x_y_swap():
    field = T.solve_square(11, 0.02, 1.0, 1.0)
    for j in range(11):
        for i in range(11):
            assert field[j][i] == pytest.approx(field[i][j], abs=1e-12)


def test_2d_solver_rejects_unstable_fourier_number():
    with pytest.raises(ValueError):
        T.solve_square(5, 1.0, 1.0, 1.0, fo_target=0.3)


def test_analytic_field_is_zero_at_boundary_neighbours_scale():
    ana = T.analytic_field(5, 1.0, 1.0, 0.0)
    assert ana[2][2] == pytest.approx(1.0)  # centre of the sine mode at t = 0


# ---------------------------------------------------------------- population
def test_logistic_converges_to_carrying_capacity():
    assert B.logistic_analytic(200.0, 0.5, 1.0, 10.0) == pytest.approx(10.0, rel=1e-9)


def test_logistic_rejects_bad_inputs():
    with pytest.raises(ValueError):
        B.logistic_analytic(1.0, 0.0, 1.0, 10.0)


def test_lotka_volterra_invariant_rejects_non_positive_population():
    with pytest.raises(ValueError):
        B.lotka_volterra_invariant(0.0, 1.0, 1.0, 1.0, 1.0, 1.0)


def test_lotka_volterra_equilibrium_is_stationary():
    alpha, beta, gamma, delta = 1.0, 0.5, 0.75, 0.25
    f = B.lotka_volterra_rhs(alpha, beta, gamma, delta)
    x_eq, y_eq = gamma / delta, alpha / beta
    assert f(0.0, [x_eq, y_eq]) == pytest.approx([0.0, 0.0], abs=1e-15)
