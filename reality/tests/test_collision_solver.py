"""General collision solver: regression against the existing sphere solver, physical checks, determinism.

The regression reference is ``reality.multibody.step_bodies`` (unchanged). The solver is not allowed to replace it;
these tests show that for sphere-plane and sphere-sphere it reproduces the same numbers.
"""

import random

import pytest

from reality import contact as CT
from reality import rigidbody as RB
from reality import multibody as MB
from reality.collision import solver as SV
from reality.collision.mesh import TriangleMesh
from reality.collision.narrow import sphere_triangle
from reality.rigidbody import norm

G = (0.0, 0.0, -9.80665)
UP = (0.0, 0.0, 1.0)


# ---------------------------------------------------------------- regression against the existing solvers
def _kernel_single(mass, radius, pos, vel, omega, e, mu, duration, dt):
    """contact.step_sphere: the single-body reference (the same call as tests/test_multibody.py)."""
    inertia = (0.4 * mass * radius * radius,) * 3
    body = RB.RigidBody(mass, inertia, position=tuple(pos), velocity=tuple(vel), omega=tuple(omega))
    plane = CT.Plane(UP, 0.0)
    for _ in range(round(duration / dt)):
        CT.step_sphere(body, dt, G, radius, [plane], restitution=e, friction=mu)
    return body.position, body.velocity, body.quaternion, body.omega


def _solver_single(mass, radius, pos, vel, omega, e, mu, duration, dt):
    body = SV.Body("s", "sphere", mass, position=tuple(pos), velocity=tuple(vel), omega_body=tuple(omega),
                   radius=radius)
    specs = [SV.PairSpec("sphere_plane", None, 0, mu, e, CT.Plane(UP, 0.0))]
    for _ in range(round(duration / dt)):
        SV.step([body], specs, dt, G)
    return body.position, body.velocity, body.quaternion, body.omega_body


@pytest.mark.parametrize("case", [
    dict(pos=(0.0, 0.0, 1.0), vel=(0.0, 0.0, 0.0), omega=(0.0, 0.0, 0.0), e=0.7, mu=0.3, duration=2.0),
    dict(pos=(0.0, 0.0, 0.3), vel=(1.0, 0.5, 0.0), omega=(0.2, -3.0, 1.0), e=0.5, mu=0.4, duration=1.0),
])
def test_single_sphere_matches_contact_step_sphere(case):
    mass, radius, dt = 4.0, 0.05, 1e-4
    ref = _kernel_single(mass, radius, case["pos"], case["vel"], case["omega"], case["e"], case["mu"],
                         case["duration"], dt)
    got = _solver_single(mass, radius, case["pos"], case["vel"], case["omega"], case["e"], case["mu"],
                         case["duration"], dt)
    worst = max(abs(a - b) for r, g in zip(ref, got) for a, b in zip(r, g))
    assert worst < 1e-11, worst


def _pair_run(old_bodies, old_planes, old_contacts, new_bodies, new_specs, t_end, h):
    """Advance the reference (multibody.step_bodies) and the solver together. Worst differences per quantity."""
    worst = {"position": 0.0, "velocity": 0.0, "quaternion": 0.0, "omega_body": 0.0}
    for _ in range(round(t_end / h)):
        MB.step_bodies(old_bodies, old_planes, old_contacts, h, G)
        SV.step(new_bodies, new_specs, h, G)
        for o, n in zip(old_bodies, new_bodies):
            for key, x, y in (("position", o.position, n.position), ("velocity", o.velocity, n.velocity),
                              ("quaternion", o.quaternion, n.quaternion),
                              ("omega_body", o.omega_body, n.omega_body)):
                worst[key] = max(worst[key], max(abs(p - q) for p, q in zip(x, y)))
    return worst


def test_bounce_on_plane_matches_multibody_reference():
    old = [MB.Sphere("a", 4.0, 0.05, (0.0, 0.0, 1.0), (0.0, 0.0, 0.0))]
    new = [SV.Body("a", "sphere", 4.0, position=(0.0, 0.0, 1.0), radius=0.05)]
    w = _pair_run(old, [CT.Plane(UP, 0.0)], [MB.PlaneContact(0, 0, 0.3, 0.7)],
                  new, [SV.PairSpec("sphere_plane", None, 0, 0.3, 0.7, CT.Plane(UP, 0.0))], 2.0, 1e-4)
    assert max(w.values()) < 1e-11, w


def test_spin_oblique_on_plane_matches_multibody_reference():
    pos, vel, om = (0.0, 0.0, 0.3), (1.0, 0.5, 0.0), (0.2, -3.0, 1.0)
    old = [MB.Sphere("a", 4.0, 0.05, pos, vel, omega_body=om)]
    new = [SV.Body("a", "sphere", 4.0, position=pos, velocity=vel, omega_body=om, radius=0.05)]
    w = _pair_run(old, [CT.Plane(UP, 0.0)], [MB.PlaneContact(0, 0, 0.4, 0.5)],
                  new, [SV.PairSpec("sphere_plane", None, 0, 0.4, 0.5, CT.Plane(UP, 0.0))], 1.0, 1e-4)
    assert max(w.values()) < 1e-11, w


def test_head_on_pair_matches_multibody_reference():
    old = [MB.Sphere("a", 2.0, 0.05, (0.0, 0.0, 0.0), (1.0, 0.0, 0.0)),
           MB.Sphere("b", 1.0, 0.05, (0.5, 0.0, 0.0), (-1.0, 0.0, 0.0))]
    new = [SV.Body("a", "sphere", 2.0, position=(0.0, 0.0, 0.0), velocity=(1.0, 0.0, 0.0), radius=0.05),
           SV.Body("b", "sphere", 1.0, position=(0.5, 0.0, 0.0), velocity=(-1.0, 0.0, 0.0), radius=0.05)]
    w = _pair_run(old, [], [MB.PairContact(0, 1, 0.2, 0.8)],
                  new, [SV.PairSpec("sphere_sphere", 0, 1, 0.2, 0.8)], 0.5, 1e-4)
    assert max(w.values()) < 1e-11, w


def test_two_stacked_spheres_match_multibody_reference_within_measured_tolerance():
    # measured in this milestone: the projection pass orders contacts slightly differently, giving a 2.6e-10 m
    # position difference after 1 s. The tolerance is set to 1e-9 m; a larger difference would be a real regression.
    def bodies_old():
        return [MB.Sphere("a", 2.0, 0.05, (0.0, 0.0, 0.05), (0.0, 0.0, 0.0)),
                MB.Sphere("b", 2.0, 0.05, (0.0, 0.0, 0.15), (0.0, 0.0, 0.0))]
    old = bodies_old()
    new = [SV.Body("a", "sphere", 2.0, position=(0.0, 0.0, 0.05), radius=0.05),
           SV.Body("b", "sphere", 2.0, position=(0.0, 0.0, 0.15), radius=0.05)]
    w = _pair_run(old, [CT.Plane(UP, 0.0)], [MB.PlaneContact(0, 0, 0.5, 0.0), MB.PlaneContact(1, 0, 0.5, 0.0),
                                             MB.PairContact(0, 1, 0.5, 0.0)],
                  new, [SV.PairSpec("sphere_plane", None, 0, 0.5, 0.0, CT.Plane(UP, 0.0)),
                        SV.PairSpec("sphere_plane", None, 1, 0.5, 0.0, CT.Plane(UP, 0.0)),
                        SV.PairSpec("sphere_sphere", 0, 1, 0.5, 0.0)], 1.0, 1e-4)
    assert w["position"] <= 1e-9, w
    assert w["velocity"] <= 1e-9, w


# ---------------------------------------------------------------- momentum, energy, rest and friction
def test_head_on_equal_masses_swap_velocities_and_conserve_momentum_and_energy():
    # centres 0.12 m apart: surfaces 0.02 m apart, so they meet at about t = 0.01 s
    a = SV.Body("a", "sphere", 1.0, position=(-0.06, 0, 0), velocity=(1, 0, 0), radius=0.05)
    b = SV.Body("b", "sphere", 1.0, position=(0.06, 0, 0), velocity=(-1, 0, 0), radius=0.05)
    p0, e0 = SV.total_momentum([a, b]), SV.total_kinetic_energy([a, b])
    specs = [SV.PairSpec("sphere_sphere", 0, 1, 0.0, 1.0)]
    reversed_seen = False
    for _ in range(3000):
        SV.step([a, b], specs, 1e-4, (0.0, 0.0, 0.0))
        reversed_seen = reversed_seen or a.velocity[0] < 0.0
    assert reversed_seen, "the spheres never collided, so the collision was not tested"
    assert a.velocity[0] == pytest.approx(-1.0, abs=1e-9)
    assert b.velocity[0] == pytest.approx(1.0, abs=1e-9)
    assert SV.total_momentum([a, b]) == pytest.approx(p0, abs=1e-12)
    assert SV.total_kinetic_energy([a, b]) == pytest.approx(e0, rel=1e-9)


def test_momentum_conserved_by_random_frictional_collisions_without_gravity():
    rng = random.Random(3)
    for trial in range(12):
        bodies = []
        for i in range(3):
            bodies.append(SV.Body(f"s{i}", "sphere", rng.uniform(0.5, 3.0),
                                  position=(i * 0.09, rng.uniform(-0.01, 0.01), rng.uniform(-0.01, 0.01)),
                                  velocity=tuple(rng.uniform(-1, 1) for _ in range(3)),
                                  omega_body=tuple(rng.uniform(-2, 2) for _ in range(3)), radius=0.05))
        specs = [SV.PairSpec("sphere_sphere", 0, 1, 0.3, 0.6), SV.PairSpec("sphere_sphere", 1, 2, 0.3, 0.6)]
        p0 = SV.total_momentum(bodies)
        for _ in range(400):
            SV.step(bodies, specs, 1e-4, (0.0, 0.0, 0.0))
        p1 = SV.total_momentum(bodies)
        assert norm((p1[0] - p0[0], p1[1] - p0[1], p1[2] - p0[2])) < 1e-9, trial


def test_box_flat_on_plane_rests_at_its_half_height():
    box = SV.Body("b", "box", 1.0, position=(0.0, 0.0, 0.2 + 0.001), half=(0.1, 0.05, 0.2))
    specs = [SV.PairSpec("box_plane", None, 0, 0.5, 0.0, CT.Plane(UP, 0.0))]
    for _ in range(20000):
        SV.step([box], specs, 1e-4, G)
    assert box.position[2] == pytest.approx(0.2, abs=1e-4)
    assert norm(box.velocity) < 1e-3
    assert norm(box.omega_body) < 1e-2


def test_box_on_static_sphere_settles_on_the_apex():
    sphere = SV.Body("s", "sphere", 1.0, position=(0.0, 0.0, 0.1), radius=0.1, static=True)
    box = SV.Body("b", "box", 0.5, position=(0.0, 0.0, 0.2 + 0.001), half=(0.05, 0.05, 0.05))
    specs = [SV.PairSpec("sphere_box", 1, 0, 0.5, 0.0)]
    bodies = [sphere, box]
    for _ in range(20000):
        SV.step(bodies, specs, 1e-4, G)
    # the box's bottom face centre is on the apex of the sphere, so the box centre is at 0.1 + 0.1 + 0.05
    assert box.position[2] == pytest.approx(0.25, abs=2e-3)
    assert sphere.position == (0.0, 0.0, 0.1)


def test_friction_stops_a_sliding_box_on_a_plane():
    box = SV.Body("b", "box", 1.0, position=(0.0, 0.0, 0.1), velocity=(2.0, 0.0, 0.0), half=(0.1, 0.1, 0.1))
    specs = [SV.PairSpec("box_plane", None, 0, 0.5, 0.0, CT.Plane(UP, 0.0))]
    for _ in range(40000):
        SV.step([box], specs, 1e-4, G)
    # Coulomb friction at the bottom corners must bring the sliding speed close to zero; the stop time is not asserted
    assert abs(box.velocity[0]) < 1e-2


def test_mesh_floor_gives_no_sideways_ghost_force_over_a_seam():
    # two coplanar triangles; a sphere dropped right over the diagonal seam must not drift sideways
    verts = ((-1.0, -1.0, 0.0), (1.0, -1.0, 0.0), (1.0, 1.0, 0.0), (-1.0, 1.0, 0.0))
    mesh = TriangleMesh("floor", verts, ((0, 1, 2), (0, 2, 3)))
    ball = SV.Body("ball", "sphere", 1.0, position=(0.2, 0.1, 0.5), radius=0.1)
    specs = [SV.PairSpec("sphere_mesh", None, 0, 0.0, 0.0, mesh)]
    worst_lateral = 0.0
    for _ in range(4000):
        SV.step([ball], specs, 1e-4, G)
        worst_lateral = max(worst_lateral, abs(ball.velocity[0]), abs(ball.velocity[1]))
    assert worst_lateral < 1e-9
    assert ball.position[2] == pytest.approx(0.1, abs=1e-6)


def test_sphere_on_mesh_bounces_with_restitution_one():
    verts = ((-2.0, -2.0, 0.0), (2.0, -2.0, 0.0), (2.0, 2.0, 0.0), (-2.0, 2.0, 0.0))
    mesh = TriangleMesh("floor", verts, ((0, 1, 2), (0, 2, 3)))
    h0 = 1.0
    ball = SV.Body("ball", "sphere", 1.0, position=(0.0, 0.0, h0 + 0.1), radius=0.1)
    specs = [SV.PairSpec("sphere_mesh", None, 0, 0.0, 1.0, mesh)]
    # phases: 0 falling, 1 rising after the impact, 2 the first apex has been reached
    phase, apex, prev_vz = 0, None, ball.velocity[2]
    for _ in range(60000):
        SV.step([ball], specs, 1e-4, G)
        vz = ball.velocity[2]
        if phase == 0 and prev_vz < 0.0 and vz > 0.0:      # impact: the velocity reverses from down to up
            phase = 1
        elif phase == 1 and prev_vz > 0.0 and vz <= 0.0:   # apex: the velocity reverses from up to down
            apex = ball.position[2]
            break
        prev_vz = vz
    assert apex is not None
    # elastic bounce from h0 (centre height h0 + r): the first apex returns to the release height.
    # Measured in this milestone at dt = 1e-4: error 4.4e-4 m, and it is first order in dt (4.4e-3 at 1e-3, 4.4e-5 at 1e-5).
    assert apex == pytest.approx(h0 + 0.1, abs=1e-3)


def test_sphere_on_mesh_rests_on_the_surface_with_zero_restitution():
    verts = ((-2.0, -2.0, 0.0), (2.0, -2.0, 0.0), (2.0, 2.0, 0.0), (-2.0, 2.0, 0.0))
    mesh = TriangleMesh("floor", verts, ((0, 1, 2), (0, 2, 3)))
    ball = SV.Body("ball", "sphere", 1.0, position=(0.3, -0.4, 0.5), radius=0.1)
    specs = [SV.PairSpec("sphere_mesh", None, 0, 0.2, 0.0, mesh)]
    for _ in range(20000):
        SV.step([ball], specs, 1e-4, G)
    assert ball.position[2] == pytest.approx(0.1, abs=1e-6)
    assert norm(ball.velocity) < 1e-3


def test_mesh_contact_matches_a_brute_force_triangle_loop_over_a_run():
    verts = ((-1.0, -1.0, 0.0), (1.0, -1.0, 0.0), (1.0, 1.0, 0.0), (-1.0, 1.0, 0.0))
    mesh = TriangleMesh("floor", verts, ((0, 1, 2), (0, 2, 3)))
    centre = (0.1, 0.05, 0.095)
    got = mesh.sphere_contacts(centre, 0.1)
    raw = mesh.sphere_contacts_brute(centre, 0.1)
    assert len(got) == 1 and got[0].feature == "face"
    assert got[0].depth == pytest.approx(max(c.depth for c in raw if c.feature == "face"), abs=1e-12)
    # every brute-force triangle contact must be a legal contact on that triangle (depth bound check)
    for tri in mesh.triangles:
        a, b, c = (mesh.vertices[k] for k in tri)
        ct = sphere_triangle(centre, 0.1, a, b, c)
        if ct is not None:
            assert ct.depth <= 0.1 + 1e-12


# ---------------------------------------------------------------- determinism and validation
def test_solver_is_bitwise_deterministic():
    def run():
        bodies = [SV.Body("a", "sphere", 2.0, position=(0, 0, 0.05), radius=0.05),
                  SV.Body("b", "sphere", 2.0, position=(0, 0, 0.15), radius=0.05)]
        specs = [SV.PairSpec("sphere_plane", None, 0, 0.5, 0.0, CT.Plane(UP, 0.0)),
                 SV.PairSpec("sphere_plane", None, 1, 0.5, 0.0, CT.Plane(UP, 0.0)),
                 SV.PairSpec("sphere_sphere", 0, 1, 0.5, 0.0)]
        for _ in range(3000):
            SV.step(bodies, specs, 1e-4, G)
        return [(b.position, b.velocity, b.quaternion) for b in bodies]
    assert run() == run()


def test_step_rejects_invalid_arguments():
    body = SV.Body("a", "sphere", 1.0, radius=0.1)
    with pytest.raises(ValueError):
        SV.step([body], [], 0.0, G)
    with pytest.raises(ValueError):
        SV.step([body], [SV.PairSpec("sphere_plane", None, 0, 0.1, 1.5, CT.Plane(UP, 0.0))], 1e-4, G)
    with pytest.raises(ValueError):
        SV.step([body], [SV.PairSpec("triangle_tri", None, 0, 0.1, 0.0)], 1e-4, G)


def test_body_rejects_bad_inputs():
    with pytest.raises(ValueError):
        SV.Body("a", "sphere", 0.0, radius=0.1)
    with pytest.raises(ValueError):
        SV.Body("a", "sphere", 1.0, radius=0.0)
    with pytest.raises(ValueError):
        SV.Body("a", "box", 1.0, half=(0.1, 0.0, 0.1))
    with pytest.raises(ValueError):
        SV.Body("a", "cylinder", 1.0, radius=0.1)


def test_box_inertia_matches_the_validated_formula():
    # I_x = m (b^2 + c^2) / 12 with full edges b = 2 hy, c = 2 hz, which is m (hy^2 + hz^2) / 3
    box = SV.Body("b", "box", 3.0, half=(0.1, 0.2, 0.3))
    assert box.inertia_body[0] == pytest.approx(3.0 * (4 * 0.04 + 4 * 0.09) / 12, rel=1e-14)
    assert box.inertia_body[1] == pytest.approx(3.0 * (4 * 0.01 + 4 * 0.09) / 12, rel=1e-14)
    assert box.inertia_body[2] == pytest.approx(3.0 * (4 * 0.01 + 4 * 0.04) / 12, rel=1e-14)
