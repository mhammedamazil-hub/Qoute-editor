"""Phase 3 unit tests: rigid-body rotation and sphere-plane contact."""

import math

import pytest

from reality import contact as CT
from reality import rigidbody as RB


def test_quaternion_rotates_x_axis_to_y_axis_about_z():
    q = (math.cos(math.pi / 4), 0.0, 0.0, math.sin(math.pi / 4))  # 90 deg about z
    r = RB.quat_to_matrix(q)
    v = RB.mat_vec(r, (1.0, 0.0, 0.0))
    assert v == pytest.approx((0.0, 1.0, 0.0), abs=1e-15)


def test_rotation_matrix_is_orthonormal():
    q = RB.quat_normalize((0.3, -0.7, 0.2, 0.6))
    r = RB.quat_to_matrix(q)
    rtr = RB.mat_mul(RB.mat_t(r), r)
    for i in range(3):
        for j in range(3):
            assert rtr[i][j] == pytest.approx(1.0 if i == j else 0.0, abs=1e-14)


def test_zero_quaternion_is_rejected():
    with pytest.raises(ValueError):
        RB.quat_normalize((0.0, 0.0, 0.0, 0.0))


def test_body_rejects_non_physical_inertia_and_mass():
    with pytest.raises(ValueError):
        RB.RigidBody(1.0, (1.0, 1.0, 3.0))  # violates I3 <= I1 + I2
    with pytest.raises(ValueError):
        RB.RigidBody(0.0, (1.0, 1.0, 1.0))
    with pytest.raises(ValueError):
        RB.RigidBody(1.0, (1.0, -1.0, 1.0))


def test_free_rotation_about_principal_axis_keeps_omega():
    body = RB.RigidBody(1.0, (0.1, 0.2, 0.3), omega=(0.0, 0.0, 2.0))
    RB.integrate(body, 0.0, 5.0, 1e-2)
    assert body.omega == pytest.approx((0.0, 0.0, 2.0), abs=1e-12)


def test_rk4_step_rejects_non_positive_step():
    body = RB.RigidBody(1.0, (1.0, 1.0, 1.0))
    with pytest.raises(ValueError):
        RB.step_rk4(body, 0.0, 0.0)


def test_point_velocity_of_spinning_body():
    body = RB.RigidBody(1.0, (1.0, 1.0, 1.0), omega=(0.0, 0.0, 1.0))
    assert body.point_velocity((1.0, 0.0, 0.0)) == pytest.approx((0.0, 1.0, 0.0))


def test_angular_momentum_world_matches_body_when_unrotated():
    body = RB.RigidBody(1.0, (1.0, 2.0, 3.0), omega=(1.0, 1.0, 1.0))
    assert body.angular_momentum_world() == pytest.approx((1.0, 2.0, 3.0))


# ------------------------------------------------------------------ contact
def _sphere(radius=0.1, mass=1.0, z=None, **kw):
    i = 0.4 * mass * radius * radius
    pos = (0.0, 0.0, radius if z is None else z)
    return RB.RigidBody(mass, (i, i, i), position=pos, **kw)


def test_plane_normal_is_normalised():
    assert CT.Plane((0.0, 0.0, 5.0)).normal == pytest.approx((0.0, 0.0, 1.0))


def test_plane_rejects_zero_normal():
    with pytest.raises(ValueError):
        CT.Plane((0.0, 0.0, 0.0))


def test_step_sphere_requires_solid_sphere_inertia():
    body = RB.RigidBody(1.0, (0.1, 0.2, 0.3), position=(0.0, 0.0, 0.1))
    with pytest.raises(ValueError):
        CT.step_sphere(body, 1e-3, (0.0, 0.0, -9.8), 0.1, [CT.Plane((0.0, 0.0, 1.0))])


@pytest.mark.parametrize("kwargs", [
    dict(restitution=1.5), dict(restitution=-0.1), dict(friction=-0.2),
])
def test_step_sphere_rejects_invalid_coefficients(kwargs):
    body = _sphere()
    with pytest.raises(ValueError):
        CT.step_sphere(body, 1e-3, (0.0, 0.0, -9.8), 0.1, [CT.Plane((0.0, 0.0, 1.0))], **kwargs)


def test_resting_sphere_stays_in_contact_without_drift():
    body = _sphere()
    plane = CT.Plane((0.0, 0.0, 1.0))
    for _ in range(1000):
        CT.step_sphere(body, 1e-3, (0.0, 0.0, -9.80665), 0.1, [plane], restitution=0.0, friction=0.5)
    assert body.position[2] == pytest.approx(0.1, abs=1e-12)
    assert body.velocity == pytest.approx((0.0, 0.0, 0.0), abs=1e-12)


def test_no_restitution_stops_the_bounce():
    body = _sphere(z=1.1)
    plane = CT.Plane((0.0, 0.0, 1.0))
    for _ in range(15000):  # 1.5 s: impact at about 0.45 s, then rest
        CT.step_sphere(body, 1e-4, (0.0, 0.0, -9.80665), 0.1, [plane], restitution=0.0)
    # Resting on the plane, no rebound. The residual gap of about 1e-8 m is the O(g h^2) error
    # of the predict-then-resolve step at h = 1e-4 s (g h^2 = 1e-7 m), not penetration.
    assert body.position[2] == pytest.approx(0.1, abs=1e-6)
    assert body.velocity[2] == pytest.approx(0.0, abs=1e-9)


def test_perfect_restitution_returns_to_drop_height():
    body = _sphere(z=1.1)
    plane = CT.Plane((0.0, 0.0, 1.0))
    apex = 0.0
    bounced = False
    for _ in range(40000):
        CT.step_sphere(body, 1e-4, (0.0, 0.0, -9.80665), 0.1, [plane], restitution=1.0)
        if body.velocity[2] > 0.0:
            bounced = True
        if bounced:
            apex = max(apex, body.position[2] - 0.1)
    assert apex == pytest.approx(1.0, rel=2e-3)


def test_contact_reports_active_plane_indices():
    body = _sphere(z=0.1)
    planes = [CT.Plane((0.0, 0.0, 1.0)), CT.Plane((1.0, 0.0, 0.0), offset=-100.0)]
    active = CT.step_sphere(body, 1e-3, (0.0, 0.0, -9.80665), 0.1, planes)
    assert active == [0]


def test_friction_needs_normal_load_and_never_adds_energy():
    # Without gravity there is no normal load, so friction must not act (physically correct).
    still = _sphere(z=0.1, velocity=(2.0, 0.0, 0.0))
    for _ in range(100):
        CT.step_sphere(still, 1e-3, (0.0, 0.0, 0.0), 0.1, [CT.Plane((0.0, 0.0, 1.0))], friction=0.3)
    assert still.velocity[0] == pytest.approx(2.0)
    # With gravity, sliding friction removes energy: kinetic energy never increases.
    body = _sphere(z=0.1, velocity=(2.0, 0.0, 0.0))
    plane = CT.Plane((0.0, 0.0, 1.0))
    e_prev = body.kinetic_energy()
    for _ in range(3000):
        CT.step_sphere(body, 1e-4, (0.0, 0.0, -9.80665), 0.1, [plane], restitution=0.0, friction=0.3)
        assert body.kinetic_energy() <= e_prev * (1 + 1e-12)
        e_prev = body.kinetic_energy()
    assert body.velocity[0] < 2.0
