"""Phase 7 (P5) edge cases for box-box: near-parallel, grazing, mass ratio, high speed, falling onto a box, quaternion
norm over a long run, and degenerate solver inputs. Tolerances are stated next to each assertion and were measured
with the code under test (see BOX_BOX_RESEARCH.md); analytic references are independent of the solver.
"""
import math

import pytest

from reality.collision import box_box as BB
from reality.collision import solver as SV
from reality.rigidbody import quat_norm

G = (0.0, 0.0, -9.80665)
G0 = (0.0, 0.0, 0.0)


def rot_x(angle):
    c, s = math.cos(angle / 2.0), math.sin(angle / 2.0)
    return (c, s, 0.0, 0.0)


def mat_from_quat(q):
    from reality.rigidbody import quat_to_matrix
    return quat_to_matrix(q)


def floor_body():
    return SV.Body("floor", "box", mass=1.0, static=True, position=(0.0, 0.0, -1.0), half=(5.0, 5.0, 1.0))


def run(bodies, specs, steps, dt, gravity=G):
    max_pen = 0.0
    last = None
    for _ in range(steps):
        last = SV.step(bodies, specs, dt, gravity)
        max_pen = max(max_pen, last.max_penetration)
    return max_pen, last


# ------------------------------------------------------------------ geometry

def test_nearly_parallel_boxes_match_the_exactly_parallel_case():
    # A rotation of 1e-9 rad about x: every edge pair with a nonzero cross product is ill-conditioned, but the answer
    # must be the aligned answer to within the rotation (depth error is first order in the angle, here <= 1e-8 m).
    half = (0.3, 0.2, 0.2)
    aligned = BB.box_box_contacts((0.0, 0.0, 0.0), ((1, 0, 0), (0, 1, 0), (0, 0, 1)), half,
                                  (0.5, 0.05, 0.02), ((1, 0, 0), (0, 1, 0), (0, 0, 1)), half)
    th = 1e-9
    rot = ((1, 0, 0), (0, math.cos(th), -math.sin(th)), (0, math.sin(th), math.cos(th)))
    tilted = BB.box_box_contacts((0.0, 0.0, 0.0), ((1, 0, 0), (0, 1, 0), (0, 0, 1)), half,
                                 (0.5, 0.05, 0.02), rot, half)
    assert aligned and tilted
    assert len(tilted) == len(aligned)
    depth_a = max(c.depth for c in aligned)
    depth_t = max(c.depth for c in tilted)
    assert depth_t == pytest.approx(depth_a, abs=1e-8)
    # the normal stays on the x axis (the separating face axis), not an ill-conditioned edge direction
    assert all(abs(abs(c.normal[0]) - 1.0) < 1e-6 for c in tilted)


def test_grazing_overlap_on_a_rim_takes_the_minimum_axis_and_keeps_its_depth():
    # A (half 0.5) spans x, y, z in [-0.5, 0.5]. B (half 0.1) is centred at x = 0.6 - 1e-4 and z = 0.59, so it overlaps A
    # by 1e-4 m along x and by 0.01 m along z. Minimum-penetration SAT must pick x (depth 1e-4): a side-face contact on
    # the rim, not the 0.01 m top overlap. Every point must lie inside both boxes.
    I = ((1, 0, 0), (0, 1, 0), (0, 0, 1))
    half_a = (0.5, 0.5, 0.5)
    half_b = (0.1, 0.1, 0.1)
    centre_b = (0.6 - 1e-4, 0.0, 0.59)
    contacts = BB.box_box_contacts((0.0, 0.0, 0.0), I, half_a, centre_b, I, half_b)
    assert contacts, "a 1e-4 m rim overlap must still produce a contact"
    for c in contacts:
        assert c.depth == pytest.approx(1e-4, abs=1e-9)
        assert abs(abs(c.normal[0]) - 1.0) < 1e-9
        assert abs(c.point[0]) <= 0.5 + 1e-9 and abs(c.point[1]) <= 0.5 + 1e-9 and abs(c.point[2]) <= 0.5 + 1e-9


# ------------------------------------------------------------------ dynamics

def test_extreme_mass_ratio_elastic_head_on_matches_the_closed_form():
    # Heavy M = 1000 kg at +1 m/s onto light m = 1 kg at rest, e = 1. Closed form:
    # v_light = 2 M v / (M + m) = 1.998002, v_heavy = (M - m) v / (M + m) = 0.998001.
    M, m, v = 1000.0, 1.0, 1.0
    heavy = SV.Body("H", "box", mass=M, position=(-0.25, 0.0, 0.0), velocity=(v, 0.0, 0.0), half=(0.2, 0.2, 0.2))
    light = SV.Body("L", "box", mass=m, position=(0.25, 0.0, 0.0), half=(0.2, 0.2, 0.2))
    specs = [SV.PairSpec("box_box", 0, 1, 0.0, 1.0)]
    bodies = [heavy, light]
    p0 = M * v
    e0 = 0.5 * M * v * v
    max_pen, _ = run(bodies, specs, 3000, 1e-4, G0)
    assert light.velocity[0] == pytest.approx(2 * M * v / (M + m), abs=1e-3)
    assert heavy.velocity[0] == pytest.approx((M - m) * v / (M + m), abs=1e-3)
    assert heavy.mass * heavy.velocity[0] + light.mass * light.velocity[0] == pytest.approx(p0, abs=1e-9)
    e1 = 0.5 * heavy.mass * heavy.velocity[0] ** 2 + 0.5 * light.mass * light.velocity[0] ** 2
    assert e1 == pytest.approx(e0, rel=1e-5)
    assert max_pen <= 1e-6


def test_falling_box_comes_to_rest_on_a_box_at_the_analytic_height_with_no_spin():
    # Dropped from 1.0 m (centre) onto a resting box whose top is at 0.4 m: rests at centre 0.6 m, zero spin.
    f = floor_body()
    base = SV.Body("base", "box", mass=2.0, position=(0.0, 0.0, 0.2), half=(0.2, 0.2, 0.2))
    top = SV.Body("top", "box", mass=1.0, position=(0.0, 0.0, 1.0), half=(0.2, 0.2, 0.2))
    specs = [SV.PairSpec("box_box", 1, 0, 0.5, 0.0), SV.PairSpec("box_box", 2, 1, 0.5, 0.0)]
    max_pen, _ = run([f, base, top], specs, 6000, 1e-4, G)  # 0.6 s: fall (0.4 m at g) + settling
    assert base.position[2] == pytest.approx(0.2, abs=1e-5)
    assert top.position[2] == pytest.approx(0.6, abs=1e-5)
    assert max(abs(x) for x in top.omega_world()) < 1e-5
    assert max(abs(x) for x in top.velocity) < 1e-5
    assert max_pen <= 1e-4  # the impact penetration before projection (measured ~1e-6 at this drop height)


# ------------------------------------------------------------------ high speed

def test_high_speed_impact_at_20_m_s_rebounds_at_e_times_the_impact_speed():
    # 20 m/s onto a fixed floor at e = 0.5, dt = 1e-4 (2 mm per step: a contact step, not tunnelling). The rebound is
    # measured in the impact step itself, because gravity slows the rebound afterwards. Measured: pre-impact speed
    # 20.195 m/s (includes the gravity increment of the step), rebound 10.098 m/s = e * 20.195 to 5e-5 relative.
    f = floor_body()
    box = SV.Body("b", "box", mass=1.0, position=(0.0, 0.0, 0.5), velocity=(0.0, 0.0, -20.0), half=(0.1, 0.1, 0.1))
    specs = [SV.PairSpec("box_box", 1, 0, 0.0, 0.5)]
    v_pre = None
    for _ in range(3000):
        before = box.velocity[2]
        SV.step([f, box], specs, 1e-4, G)
        if box.velocity[2] > 0.0:
            v_pre = before
            break
    assert v_pre is not None, "the box must rebound"
    assert box.velocity[2] == pytest.approx(0.5 * abs(v_pre), rel=1e-3)
    assert box.velocity[2] > 0.0
    e_before = 0.5 * box.mass * v_pre ** 2
    e_after = 0.5 * box.mass * box.velocity[2] ** 2
    assert e_after / e_before == pytest.approx(0.25, rel=2e-3)


# ------------------------------------------------------------------ quaternion

def test_quaternion_stays_unit_over_a_long_spinning_free_flight():
    # 20000 steps (2 s) of free anisotropic spin: the quaternion is renormalised every step, so its norm error must
    # stay at rounding level. Measured in this test run, not assumed.
    b = SV.Body("b", "box", mass=1.0, position=(0.0, 0.0, 0.0), omega_body=(5.0, -3.0, 7.0), half=(0.3, 0.2, 0.1))
    worst = 0.0
    for _ in range(20000):
        SV.step([b], [], 1e-4, G0)
        worst = max(worst, abs(quat_norm(b.quaternion) - 1.0))
    assert worst <= 1e-12
    R = mat_from_quat(b.quaternion)
    orth = max(abs(sum(R[i][k] * R[j][k] for k in range(3)) - (1.0 if i == j else 0.0))
               for i in range(3) for j in range(3))
    assert orth <= 1e-12


# ------------------------------------------------------------------ degenerate

def test_identical_stationary_boxes_give_finite_state_and_no_momentum_change():
    # Two identical boxes at the same centre: the SAT depth is defined (twice the half extent), the normal is canonical,
    # and with zero relative velocity the state must stay finite with the total momentum unchanged.
    a = SV.Body("a", "box", mass=1.0, position=(0.0, 0.0, 0.0), half=(0.2, 0.2, 0.2))
    b = SV.Body("b", "box", mass=1.0, position=(0.0, 0.0, 0.0), half=(0.2, 0.2, 0.2))
    specs = [SV.PairSpec("box_box", 0, 1, 0.5, 0.0)]
    _, info = run([a, b], specs, 10, 1e-4, G0)
    for body in (a, b):
        assert all(math.isfinite(x) for x in body.position + body.velocity + body.omega_body)
    assert info.max_penetration >= 0.0
    assert sum(x for x in (a.velocity[0], b.velocity[0])) == pytest.approx(0.0, abs=1e-12)


def test_three_box_impact_at_the_bake_timestep_converges_under_the_penetration_limit():
    # Regression (found by the Blender smoke test, Phase 7 P7): a ground box and two boxes dropped onto it at the 24 fps
    # bake timestep (1/1008 s, 42 substeps per frame). With the old cap of 10 projection passes the run peaked at
    # 1.3e-6 m and was refused by the 1e-6 m check. The projection now converges (cap 40, measured).
    dt = 1.0 / 1008.0
    ground = SV.Body("g", "box", mass=1.0, static=True, position=(0.0, 0.0, -0.5), half=(5.0, 5.0, 0.5))
    bodies = [ground,
              SV.Body("s0", "box", mass=1.0, position=(0.0, 0.0, 0.1), half=(0.1, 0.1, 0.1)),
              SV.Body("s1", "box", mass=1.0, position=(0.0, 0.0, 0.65), half=(0.1, 0.1, 0.1)),
              SV.Body("s2", "box", mass=1.0, position=(0.0, 0.0, 0.85), half=(0.1, 0.1, 0.1))]
    specs = [SV.PairSpec("box_box", i, j, 0.5, 0.0) for i in range(4) for j in range(i + 1, 4)]
    max_pen = 0.0
    for _ in range(1210):  # 1.2 s
        max_pen = max(max_pen, SV.step(bodies, specs, dt, G).max_penetration)
    assert max_pen <= 1e-6
    assert [round(b.position[2], 3) for b in bodies[1:]] == [0.1, 0.3, 0.5]
