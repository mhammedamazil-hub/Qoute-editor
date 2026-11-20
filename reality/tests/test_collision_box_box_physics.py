"""Box-box response (Phase 7): the general solver with box-box manifolds, checked against closed-form results.

Each analytic reference is derived in ``BOX_BOX_MATHEMATICS.md`` and written here from the formulae, not from solver
output. Where a result is a discretisation error rather than exact, the tolerance is the measured error at the stated
step size (recorded in the test's comment), not a value chosen to pass.
"""

import math

import pytest

from reality.collision import solver as SV

G0 = (0.0, 0.0, 0.0)
G = (0.0, 0.0, -9.80665)
HALF = (0.1, 0.1, 0.1)


def run(bodies, specs, steps, dt, gravity=G0, watch=None, stop=None):
    """Advance the solver. ``watch``/``stop`` allow an early stop; returns the per-step StepInfo list if asked."""
    infos = []
    for k in range(steps):
        infos.append(SV.step(bodies, specs, dt, gravity))
        if stop is not None and stop(k):
            break
    return infos


def momentum(bodies):
    return tuple(sum(b.mass * b.velocity[i] for b in bodies if not b.static) for i in range(3))


def kinetic(bodies):
    return sum(0.5 * b.mass * (b.velocity[0] ** 2 + b.velocity[1] ** 2 + b.velocity[2] ** 2)
               for b in bodies if not b.static)


def floor_box(z_top=0.0):
    # a large static box whose top face is at z = z_top
    return SV.Body("floor", "box", mass=1.0, position=(0.0, 0.0, z_top - 1.0), half=(20.0, 20.0, 1.0), static=True)


# ---------------------------------------------------------------- collisions between two dynamic boxes
def test_equal_mass_elastic_head_on_swaps_velocities_and_conserves_energy():
    # Analytic: equal masses, e = 1, head-on: v_A' = v_B and v_B' = v_A. Contact at t = 0.2 s (2000 steps).
    A = SV.Body("A", "box", mass=1.0, position=(-0.3, 0.0, 0.0), velocity=(1.0, 0.0, 0.0), half=HALF)
    B = SV.Body("B", "box", mass=1.0, position=(0.3, 0.0, 0.0), velocity=(-1.0, 0.0, 0.0), half=HALF)
    ke0 = kinetic([A, B])
    run([A, B], [SV.PairSpec("box_box", 0, 1, 0.0, 1.0)], 2500, 1e-4)
    assert A.velocity[0] == pytest.approx(-1.0, abs=1e-6)
    assert B.velocity[0] == pytest.approx(1.0, abs=1e-6)
    assert kinetic([A, B]) == pytest.approx(ke0, rel=1e-8)


def test_unequal_mass_restitution_matches_the_closed_form_and_conserves_momentum():
    # Analytic (BOX_BOX_MATHEMATICS.md, eq. 10): m1 = 2, v1 = 1; m2 = 1, v2 = -0.5; e = 0.5.
    m1, m2, v1, v2, e = 2.0, 1.0, 1.0, -0.5, 0.5
    v1f = ((m1 - e * m2) * v1 + (1 + e) * m2 * v2) / (m1 + m2)
    v2f = ((m2 - e * m1) * v2 + (1 + e) * m1 * v1) / (m1 + m2)
    A = SV.Body("A", "box", mass=m1, position=(-0.3, 0.0, 0.0), velocity=(v1, 0.0, 0.0), half=HALF)
    B = SV.Body("B", "box", mass=m2, position=(0.3, 0.0, 0.0), velocity=(v2, 0.0, 0.0), half=HALF)
    p0 = momentum([A, B])
    run([A, B], [SV.PairSpec("box_box", 0, 1, 0.0, e)], 3500, 1e-4)
    # measured at dt = 1e-4: |error| about 1e-9 m/s
    assert A.velocity[0] == pytest.approx(v1f, abs=1e-6)
    assert B.velocity[0] == pytest.approx(v2f, abs=1e-6)
    assert momentum([A, B])[0] == pytest.approx(p0[0], abs=1e-12)


def _impact_state(bodies, specs, dt, max_steps):
    """Advance until the first step in which the solver applies an impulse; return the step index."""
    body = bodies[-1]
    for k in range(max_steps):
        before = (tuple(body.velocity), tuple(body.omega_body))
        SV.step(bodies, specs, dt, G0)
        if (tuple(body.velocity), tuple(body.omega_body)) != before:
            return k
    raise AssertionError("no impact within the step budget")


@pytest.mark.parametrize("e", [0.0, 0.5])
def test_off_centre_edge_impact_matches_the_rigid_body_impulse_formula(e):
    # A box rotated 30 deg about x lands on a static floor with one edge (no face). Analytic (eqs. 11 of the
    # mathematics document): with the lever arm d = |y_w| of the lowest edge (about the centre of mass), the impulse
    # is J = (1 + e) * m_eff, m_eff = 1 / (1/m + d^2 / I_x), so v_z' = -1 + J/m and omega_x' = J * y_w / I_x.
    hx, hy, hz = 0.3, 0.2, 0.1
    m = 1.0
    th = math.radians(30.0)
    c, s = math.cos(th), math.sin(th)
    yw = -hy * c + hz * s            # lowest edge, relative to the centre, world frame
    zw = -hy * s - hz * c
    d = abs(yw)
    Ix = m * (hy * hy + hz * hz) / 3.0
    floor = floor_box(0.0)
    q = (math.cos(th / 2), math.sin(th / 2), 0.0, 0.0)
    B = SV.Body("B", "box", mass=m, position=(0.0, 0.0, -zw + 0.01), velocity=(0.0, 0.0, -1.0), quaternion=q,
                half=(hx, hy, hz))
    _impact_state([floor, B], [SV.PairSpec("box_box", 1, 0, 0.0, e)], 1e-5, 100000)
    meff = 1.0 / (1.0 / m + d * d / Ix)
    J = (1.0 + e) * meff
    assert B.velocity[2] == pytest.approx(-1.0 + J / m, abs=1e-6)
    assert B.omega_body[0] == pytest.approx(J * yw / Ix, abs=1e-6)
    assert B.velocity[0] == pytest.approx(0.0, abs=1e-9) and B.velocity[1] == pytest.approx(0.0, abs=1e-9)


def _angular_momentum(bodies, positions=None):
    """Total angular momentum about the origin: sum of I_world w + m r x v. ``positions`` overrides the centres."""
    L = [0.0, 0.0, 0.0]
    for k, b in enumerate(bodies):
        r = b.position if positions is None else positions[k]
        w = b.omega_world()
        I = _invert3(b.inv_inertia_world())
        Lb = [sum(I[i][j] * w[j] for j in range(3)) for i in range(3)]
        v, m = b.velocity, b.mass
        cr = (r[1] * v[2] * m - r[2] * v[1] * m, r[2] * v[0] * m - r[0] * v[2] * m, r[0] * v[1] * m - r[1] * v[0] * m)
        for i in range(3):
            L[i] += Lb[i] + cr[i]
    return L


def _invert3(M):
    a, b, c = M[0]
    d, e, f = M[1]
    g, h, i = M[2]
    det = a * (e * i - f * h) - b * (d * i - f * g) + c * (d * h - e * g)
    inv = [[(e * i - f * h), -(b * i - c * h), (b * f - c * e)],
           [-(d * i - f * g), (a * i - c * g), -(a * f - c * d)],
           [(d * h - e * g), -(a * h - b * g), (a * e - b * d)]]
    return [[x / det for x in row] for row in inv]


def _asymmetric_pair():
    A = SV.Body("A", "box", mass=1.5, position=(-0.35, 0.02, 0.01), velocity=(0.9, 0.1, 0.0),
                omega_body=(0.3, -0.7, 2.0), half=(0.3, 0.2, 0.1), quaternion=(0.9659258, 0.0, 0.0, 0.2588190))
    B = SV.Body("B", "box", mass=0.7, position=(0.35, -0.03, 0.04), velocity=(-0.4, 0.2, -0.1),
                omega_body=(-1.0, 0.5, 0.0), half=(0.2, 0.25, 0.15), quaternion=(0.9238795, 0.3826834, 0.0, 0.0))
    return A, B


def test_free_flight_of_an_asymmetric_box_follows_euler_equations_and_conserves_world_angular_momentum():
    # An asymmetric body precesses: omega_body changes by about 1 rad/s over 0.2 s. Reference: rigidbody.integrate, an
    # RK4 of Euler's equations with the gyroscopic term, at h = 1e-5. Measured: omega_body agrees to 3.2e-13 at dt 1e-4.
    # World angular momentum I_world w is an exact invariant of free flight; measured drift 4.8e-10 at dt 1e-4 (order dt^2).
    import reality.rigidbody as RB
    I = (1.5 * (0.2 ** 2 + 0.1 ** 2) / 3.0, 1.5 * (0.3 ** 2 + 0.1 ** 2) / 3.0, 1.5 * (0.3 ** 2 + 0.2 ** 2) / 3.0)
    wb = (2.0, -1.0, 3.0)
    ref = RB.RigidBody(mass=1.5, inertia=I, position=(0.0, 0.0, 0.0), omega=wb, quaternion=(1.0, 0.0, 0.0, 0.0))
    RB.integrate(ref, 0.0, 0.2, 1e-5)
    B = SV.Body("B", "box", mass=1.5, position=(0.0, 0.0, 0.0), omega_body=wb, half=(0.3, 0.2, 0.1))
    assert B.inertia_body == pytest.approx(I, rel=1e-12)
    L0 = _angular_momentum([B])
    for _ in range(2000):
        SV.step([B], [], 1e-4, G0)
    assert B.omega_body == pytest.approx(tuple(ref.omega), abs=1e-9)
    assert _angular_momentum([B]) == pytest.approx(L0, abs=1e-8)


def test_contact_impulses_conserve_linear_and_angular_momentum_at_the_predicted_configuration():
    # The solver takes its lever arms from the predicted positions x_pred = x + h v and applies impulses there. At those
    # positions both the linear and the angular momentum of every contact step are conserved to rounding (measured
    # 1.8e-13 and 2e-14 at dt 1e-4 and 5e-5; linear momentum 2e-16).
    dt = 1e-4
    A, B = _asymmetric_pair()
    p0 = momentum([A, B])
    specs = [SV.PairSpec("box_box", 0, 1, 0.3, 0.4)]
    contact_steps = 0
    worst_dl = 0.0
    for _ in range(int(0.5 / dt)):
        x_old = [A.position, B.position]
        v_pre = [A.velocity, B.velocity]
        x_pred = [SV.add(x_old[i], SV.scale(v_pre[i], dt)) for i in range(2)]
        L_before = _angular_momentum([A, B], x_pred)
        # the solver moves the bodies to x_pred only after the velocity impulses; capture L at x_pred before the step
        # and recompute it at the same x_pred with the post-impulse velocities
        info = SV.step([A, B], specs, dt, G0)
        if info.touching:
            contact_steps += 1
            worst_dl = max(worst_dl, max(abs(x - y) for x, y in zip(_angular_momentum([A, B], x_pred), L_before)))
    assert contact_steps >= 2
    assert momentum([A, B]) == pytest.approx(p0, abs=1e-12)
    assert worst_dl <= 1e-12


def test_end_of_step_angular_momentum_error_is_first_order_in_dt():
    # Moving with post-impulse velocity (semi-implicit) shifts the centres by h * dv between x_pred and x_new, so the
    # angular momentum evaluated at the end-of-step centres changes by O(h) per contact step. Measured (max over
    # contact steps, centres at the start of the step): 1.26e-5, 6.30e-6 for dt = 1e-4, 5e-5, a ratio of 2.00.
    def max_dl(dt):
        A, B = _asymmetric_pair()
        specs = [SV.PairSpec("box_box", 0, 1, 0.3, 0.4)]
        worst = 0.0
        for _ in range(int(0.5 / dt)):
            x_old = [A.position, B.position]
            L0 = _angular_momentum([A, B], x_old)
            info = SV.step([A, B], specs, dt, G0)
            if info.touching:
                worst = max(worst, max(abs(x - y) for x, y in zip(_angular_momentum([A, B], x_old), L0)))
        return worst

    d1 = max_dl(1e-4)
    d2 = max_dl(5e-5)
    assert d1 > 0.0 and d2 > 0.0
    assert 1.8 <= d1 / d2 <= 2.2


def test_static_box_is_not_moved_and_the_dynamic_box_reverses_at_e_one():
    S = SV.Body("S", "box", mass=1.0, position=(0.0, 0.0, 0.0), half=HALF, static=True)
    D = SV.Body("D", "box", mass=1.0, position=(-0.3, 0.0, 0.0), velocity=(1.0, 0.0, 0.0), half=HALF)
    run([S, D], [SV.PairSpec("box_box", 1, 0, 0.0, 1.0)], 2000, 1e-4)
    assert S.position == (0.0, 0.0, 0.0) and S.velocity == (0.0, 0.0, 0.0)
    assert D.velocity[0] == pytest.approx(-1.0, abs=1e-6)


def test_box_at_rest_on_a_static_box_stays_put_with_no_drift():
    floor = floor_box(0.0)
    B = SV.Body("B", "box", mass=2.0, position=(0.0, 0.0, 0.2), half=HALF)  # bottom 0.1 above the floor: falls
    infos = run([floor, B], [SV.PairSpec("box_box", 1, 0, 0.5, 0.0)], 1500, 2e-4, gravity=G)
    assert B.position[2] == pytest.approx(0.1, abs=1e-6)  # centre at the half-height above the floor (top at 0)
    assert max(abs(v) for v in B.velocity) < 1e-6
    assert max(abs(v) for v in B.omega_body) < 1e-6
    assert max(i.max_penetration for i in infos) <= 1e-6
    # the box falls onto the floor first; once resting, the contact is reported on every step (persistence)
    assert all(0 in i.touching for i in infos[-500:])


def test_box_rotated_about_z_rests_flat_without_spin():
    floor = floor_box(0.0)
    th = math.radians(30.0)
    q = (math.cos(th / 2), 0.0, 0.0, math.sin(th / 2))
    B = SV.Body("B", "box", mass=1.0, position=(0.0, 0.0, 0.2), quaternion=q, half=(0.2, 0.1, 0.1))
    run([floor, B], [SV.PairSpec("box_box", 1, 0, 0.5, 0.0)], 1500, 2e-4, gravity=G)
    assert B.position[2] == pytest.approx(0.1, abs=1e-6)
    assert max(abs(v) for v in B.omega_body) < 1e-5
    assert max(abs(v) for v in B.velocity) < 1e-5


# ---------------------------------------------------------------- friction, bounce, stacking
def test_sliding_box_decelerates_at_mu_g_and_stops_at_v2_over_2_mu_g_without_yaw():
    # Analytic: a flat box sliding on a floor with Coulomb friction mu decelerates at mu*g; stop distance
    # v^2 / (2 mu g). Measured at dt = 1e-4: relative error -4.9e-4 (about -5e-5 m; it falls linearly with dt, which is
    # the explicit-step error). Yaw must vanish (sliding in a straight line).
    mu, v0 = 0.5, 1.0
    floor = floor_box(0.0)
    B = SV.Body("B", "box", mass=2.0, position=(0.0, 0.0, 0.2), velocity=(v0, 0.0, 0.0), half=(0.3, 0.2, 0.2))
    spec = [SV.PairSpec("box_box", 1, 0, mu, 0.0)]
    steps = 0
    while abs(B.velocity[0]) > 1e-7 and steps < 40000:
        SV.step([floor, B], spec, 1e-4, G)
        steps += 1
    analytic = v0 * v0 / (2.0 * mu * 9.80665)
    assert B.position[0] == pytest.approx(analytic, rel=1e-3)
    assert abs(B.omega_body[2]) < 1e-9          # no yaw
    assert max(abs(v) for v in B.omega_body) < 1e-5


def test_bounce_peak_height_scales_with_e_squared():
    # Analytic: a flat box dropped from rest with bottom height h0 above a face and restitution e rebounds so that
    # its bottom reaches e^2 * h0. Here h0 = 1.2 m (centre at 1.4, half 0.2), so the centre peaks at 0.2 + e^2*1.2.
    # Measured at dt = 1e-4: peak 0.500378 m vs 0.5 m (error 3.8e-4 m; it falls as dt falls, 1.1e-4 m at 2.5e-5).
    e = 0.5
    floor = floor_box(0.0)
    B = SV.Body("B", "box", mass=1.0, position=(0.0, 0.0, 1.4), half=(0.2, 0.2, 0.2))
    spec = [SV.PairSpec("box_box", 1, 0, 0.0, e)]
    hit = False
    peak = 0.0
    for _ in range(12000):
        SV.step([floor, B], spec, 1e-4, G)
        if B.velocity[2] > 0.0:
            hit = True
        if hit:
            peak = max(peak, B.position[2])
            if B.velocity[2] < 0.0 and B.position[2] < 0.3:
                break
    assert hit
    assert peak == pytest.approx(0.2 + e * e * 1.2, abs=5e-4)


def test_off_centre_tilted_drop_rotates_the_box_flat_with_the_torque_sign_of_the_impulse():
    # A box tilted 5 deg about y (its top leans toward +x) lands first on its lowest bottom corner. The body x axis
    # has world z = -sin(5 deg), so that corner is the body (+a, -b) one. The impulse J along +z there gives torque
    # r x J with r = (+a, 0, -b): tau_y = -a J < 0, so omega_y < 0, which turns the top back toward vertical.
    # Assert the sign and that the tilt shrinks.
    floor = floor_box(0.0)
    th = math.radians(5.0)
    q = (math.cos(th / 2), 0.0, math.sin(th / 2), 0.0)
    B = SV.Body("B", "box", mass=1.0, position=(0.0, 0.0, 0.2), velocity=(0.0, 0.0, -0.5), quaternion=q,
                half=(0.2, 0.2, 0.1))
    spec = [SV.PairSpec("box_box", 1, 0, 0.0, 0.0)]
    tilt0 = _tilt(B)
    _run_until_contact_then(floor, B, spec, steps_after=600)
    assert B.omega_body[1] < 0.0
    assert _tilt(B) < tilt0


def _tilt(B):
    # angle between the body's z axis and world z
    # body z axis in world = third column of R; its world-z component is R[2][2] = 1 - 2(x^2 + y^2)
    _w, x, y, _z = B.quaternion
    return math.acos(max(-1.0, min(1.0, 1.0 - 2.0 * (x * x + y * y))))


def _run_until_contact_then(floor, B, spec, steps_after):
    for _ in range(20000):
        before = tuple(B.omega_body)
        SV.step([floor, B], spec, 1e-5, G0)
        if tuple(B.omega_body) != before:
            break
    for _ in range(steps_after):
        SV.step([floor, B], spec, 1e-5, G0)


def test_stack_of_two_boxes_settles_at_the_analytic_heights_with_no_penetration():
    # Analytic: lower box on the floor centre 0.2 (half 0.2); upper box on the lower centre 0.6. dt = 2e-4.
    floor = floor_box(0.0)
    lower = SV.Body("lower", "box", mass=1.0, position=(0.0, 0.0, 0.2), half=(0.2, 0.2, 0.2))
    upper = SV.Body("upper", "box", mass=1.0, position=(0.0, 0.0, 0.62), velocity=(0.0, 0.0, 0.0), half=(0.2, 0.2, 0.2))
    specs = [SV.PairSpec("box_box", 1, 0, 0.5, 0.0), SV.PairSpec("box_box", 2, 1, 0.5, 0.0)]
    infos = run([floor, lower, upper], specs, 3000, 2e-4, gravity=G)
    assert lower.position[2] == pytest.approx(0.2, abs=1e-5)
    assert upper.position[2] == pytest.approx(0.6, abs=1e-5)
    assert max(i.max_penetration for i in infos) <= 1e-6
    # both contacts persist on every step once the stack is at rest
    assert all(0 in i.touching and 1 in i.touching for i in infos[-500:])
