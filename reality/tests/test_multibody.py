"""Tests for reality.multibody (sphere-sphere and sphere-plane sequential impulses).

Anchors:
- one sphere on one plane must reproduce contact.step_sphere (same predict-detect-resolve order);
- pair impulses conserve linear momentum exactly;
- an elastic head-on collision of equal masses swaps velocities;
- Newton's cradle transfers the full speed to the far ball.
"""

import math

import pytest

from reality import contact as CT
from reality import multibody as MB
from reality import rigidbody as RB

G = (0.0, 0.0, -9.80665)


def _kernel_run(mass, radius, pos, vel, omega, e, mu, duration, dt):
    inertia = (0.4 * mass * radius * radius,) * 3
    body = RB.RigidBody(mass, inertia, position=tuple(pos), velocity=tuple(vel), omega=tuple(omega))
    plane = CT.Plane((0.0, 0.0, 1.0), 0.0)
    for _ in range(round(duration / dt)):
        CT.step_sphere(body, dt, G, radius, [plane], restitution=e, friction=mu)
    return body.position, body.velocity, body.quaternion, body.omega


def _multi_run(mass, radius, pos, vel, omega, e, mu, duration, dt):
    s = MB.Sphere("b", mass, radius, tuple(pos), tuple(vel), omega_body=tuple(omega))
    planes = [CT.Plane((0.0, 0.0, 1.0), 0.0)]
    contacts = [MB.PlaneContact(0, 0, mu, e)]
    for _ in range(round(duration / dt)):
        MB.step_bodies([s], planes, contacts, dt, G)
    return s.position, s.velocity, s.quaternion, s.omega_body


def _max_diff(a, b):
    return max(abs(x - y) for x, y in zip(a, b))


@pytest.mark.parametrize("case", [
    # bouncing, no spin
    dict(pos=(0.0, 0.0, 1.0), vel=(0.0, 0.0, 0.0), omega=(0.0, 0.0, 0.0), e=0.7, mu=0.2, duration=2.0),
    # sliding then rolling onset, zero restitution
    dict(pos=(0.0, 0.0, 0.05), vel=(2.0, 0.0, 0.0), omega=(0.0, 0.0, 0.0), e=0.0, mu=0.1, duration=1.5),
    # oblique impact with spin about all axes
    dict(pos=(0.0, 0.0, 0.3), vel=(1.0, 0.5, 0.0), omega=(0.2, -3.0, 1.0), e=0.5, mu=0.4, duration=1.0),
])
def test_single_sphere_matches_step_sphere(case):
    mass, radius, dt = 4.0, 0.05, 1e-4
    ref = _kernel_run(mass, radius, case["pos"], case["vel"], case["omega"], case["e"], case["mu"],
                      case["duration"], dt)
    got = _multi_run(mass, radius, case["pos"], case["vel"], case["omega"], case["e"], case["mu"],
                     case["duration"], dt)
    for a, b in zip(ref, got):
        assert _max_diff(a, b) < 1e-9


def test_pair_collision_conserves_momentum_and_energy_and_swaps_velocities():
    m, R, h = 2.0, 0.05, 1e-4
    a = MB.Sphere("a", m, R, (0.0, 0.0, 0.0), (1.0, 0.0, 0.0))
    b = MB.Sphere("b", m, R, (0.5, 0.0, 0.0), (-1.0, 0.0, 0.0))
    p0 = MB.total_momentum([a, b])
    k0 = MB.total_kinetic_energy([a, b])
    contacts = [MB.PairContact(0, 1, 0.0, 1.0)]
    for _ in range(round(0.5 / h)):
        MB.step_bodies([a, b], [], contacts, h, (0.0, 0.0, 0.0))
    p1 = MB.total_momentum([a, b])
    k1 = MB.total_kinetic_energy([a, b])
    assert _max_diff(p0, p1) < 1e-12
    assert abs(k1 - k0) / k0 < 1e-9
    assert a.velocity[0] == pytest.approx(-1.0, abs=1e-6)
    assert b.velocity[0] == pytest.approx(1.0, abs=1e-6)


def test_newtons_cradle_transfers_speed_to_far_ball():
    m, R, h = 2.0, 0.05, 1e-4
    bodies = [
        MB.Sphere("a", m, R, (0.0, 0.0, 0.0), (2.0, 0.0, 0.0)),
        MB.Sphere("b", m, R, (0.101, 0.0, 0.0)),
        MB.Sphere("c", m, R, (0.202, 0.0, 0.0)),
    ]
    contacts = [MB.PairContact(0, 1, 0.0, 1.0), MB.PairContact(1, 2, 0.0, 1.0)]
    for _ in range(round(0.5 / h)):
        MB.step_bodies(bodies, [], contacts, h, (0.0, 0.0, 0.0))
    vx = [b.velocity[0] for b in bodies]
    assert vx[0] == pytest.approx(0.0, abs=1e-6)
    assert vx[1] == pytest.approx(0.0, abs=1e-6)
    assert vx[2] == pytest.approx(2.0, abs=1e-6)


def test_two_sphere_stack_rests_on_floor():
    m, R, dt = 2.0, 0.05, 1e-4
    bodies = [
        MB.Sphere("bottom", m, R, (0.0, 0.0, R)),
        MB.Sphere("top", m, R, (0.0, 0.0, 3 * R + 1e-3)),
    ]
    planes = [CT.Plane((0.0, 0.0, 1.0), 0.0)]
    contacts = [MB.PlaneContact(0, 0, 0.5, 0.0), MB.PlaneContact(1, 0, 0.5, 0.0), MB.PairContact(0, 1, 0.5, 0.0)]
    max_pen = 0.0
    for _ in range(round(2.0 / dt)):
        info = MB.step_bodies(bodies, planes, contacts, dt, G, iterations=32)
        max_pen = max(max_pen, info.max_penetration)
    assert bodies[0].position[2] == pytest.approx(R, abs=1e-6)
    assert bodies[1].position[2] == pytest.approx(3 * R, abs=1e-6)
    assert max_pen < 1e-6
    assert abs(bodies[1].velocity[2]) < 1e-6


def test_coincident_centres_are_rejected():
    R = 0.05
    a = MB.Sphere("a", 1.0, R, (0.0, 0.0, 0.0))
    b = MB.Sphere("b", 1.0, R, (0.0, 0.0, 0.0))
    with pytest.raises(ValueError, match="coincident"):
        MB.step_bodies([a, b], [], [MB.PairContact(0, 1, 0.0, 0.0)], 1e-4, (0.0, 0.0, 0.0))


def test_isotropic_inertia_and_kinetic_energy():
    s = MB.Sphere("s", 3.0, 0.2, (0.0, 0.0, 0.0), (1.0, 0.0, 0.0), omega_body=(0.0, 0.0, 2.0))
    assert s.inertia == pytest.approx(0.4 * 3.0 * 0.2 * 0.2)
    expected = 0.5 * 3.0 * 1.0 + 0.5 * s.inertia * 4.0
    assert s.kinetic_energy() == pytest.approx(expected)
    assert math.isfinite(s.inv_mass)
