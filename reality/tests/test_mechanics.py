import math

import pytest

from reality import constants as C
from reality import mechanics as M
from reality.integrators import integrate_rk4, velocity_verlet_step


def test_rk4_exact_for_exponential_decay_order():
    # y' = -y, y(0) = 1 -> exp(-t). RK4 global error should drop ~16x when h halves.
    f = lambda t, y: [-y[0]]
    e1 = abs(integrate_rk4(f, 0.0, [1.0], 1.0, 0.1)[0] - math.exp(-1))
    e2 = abs(integrate_rk4(f, 0.0, [1.0], 1.0, 0.05)[0] - math.exp(-1))
    assert 12 < e1 / e2 < 20


def test_rk4_step_rejects_nonpositive_step():
    with pytest.raises(ValueError):
        integrate_rk4(lambda t, y: y, 0.0, [1.0], 1.0, 0.0)


def test_verlet_conserves_harmonic_energy_boundedly():
    k = 4.0
    accel = lambda x: [-k * x[0]]
    x, v = [1.0], [0.0]
    e0 = 0.5 * v[0] ** 2 + 0.5 * k * x[0] ** 2
    worst = 0.0
    for _ in range(20000):
        x, v = velocity_verlet_step(accel, x, v, 0.01)
        worst = max(worst, abs(0.5 * v[0] ** 2 + 0.5 * k * x[0] ** 2 - e0) / e0)
    assert worst < 1e-3


def test_drag_coefficient_formula():
    assert M.quadratic_drag_coefficient(1.2, 0.5, 2.0) == pytest.approx(0.6)


def test_terminal_velocity_requires_positive_drag():
    with pytest.raises(ValueError):
        M.terminal_velocity(1.0, 9.8, 0.0)


def test_freefall_no_drag_limit_matches_gt():
    # Very small k: v ~ g t and distance ~ g t^2 / 2 for short times.
    v, s = M.freefall_quadratic_drag_analytic(2.0, 1.0, 9.81, 1e-12)
    assert v == pytest.approx(9.81 * 2.0, rel=1e-6)
    assert s == pytest.approx(0.5 * 9.81 * 4.0, rel=1e-6)


def test_projectile_height_matches_numeric_peak():
    rng, h, tof = M.projectile_numeric(15.0, math.radians(45), C.STANDARD_GRAVITY, 1e-3)
    assert h == pytest.approx(M.projectile_max_height_no_drag(15.0, math.radians(45), C.STANDARD_GRAVITY), rel=1e-5)
    assert tof == pytest.approx(2 * 15.0 * math.sin(math.radians(45)) / C.STANDARD_GRAVITY, rel=1e-5)


def test_log_cosh_stable_for_tiny_arguments():
    # ln cosh x ~ x^2/2 - x^4/12 for small x; naive log(cosh x) would lose all digits here.
    x = 1e-6
    assert M.log_cosh(x) == pytest.approx(x * x / 2, rel=1e-12)
    # Large-argument branch agrees with the direct formula where both are representable.
    assert M.log_cosh(25.0) == pytest.approx(25.0 - math.log(2.0), rel=1e-12)


def test_complete_elliptic_k_known_values():
    # K(0) = pi/2 ; K(0.5) = 1.8540746773013719 (A&S Table 17.1)
    assert M.complete_elliptic_k(0.0) == pytest.approx(math.pi / 2, rel=1e-14)
    assert M.complete_elliptic_k(0.5) == pytest.approx(1.8540746773013719, rel=1e-12)


def test_pendulum_exact_period_increases_with_amplitude():
    t1 = M.pendulum_period_exact(1.0, C.STANDARD_GRAVITY, 0.2)
    t2 = M.pendulum_period_exact(1.0, C.STANDARD_GRAVITY, 1.0)
    assert t2 > t1 > M.pendulum_period_small_angle(1.0, C.STANDARD_GRAVITY)


def test_pendulum_rejects_invalid_amplitude():
    with pytest.raises(ValueError):
        M.pendulum_period_exact(1.0, 9.8, math.pi)


def test_collision_rejects_bad_inputs():
    with pytest.raises(ValueError):
        M.collide_1d(0.0, 1.0, 1.0, 0.0)
    with pytest.raises(ValueError):
        M.collide_1d(1.0, 1.0, 1.0, 0.0, restitution=1.5)


def test_perfectly_inelastic_collision_shares_velocity():
    v1, v2 = M.collide_1d(1.0, 4.0, 3.0, 0.0, 0.0)
    assert v1 == pytest.approx(v2)
    assert v1 == pytest.approx(1.0)  # (1*4)/(1+3)


def test_kepler_energy_and_momentum_helpers():
    e = M.kepler_energy(1.0, [1.0, 0.0], [0.0, 1.0])
    assert e == pytest.approx(-0.5)
    assert M.kepler_angular_momentum([1.0, 0.0], [0.0, 1.0]) == pytest.approx(1.0)
