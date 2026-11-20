"""Narrow phase: sphere-triangle, sphere-box, box-plane, sphere-plane, sphere-sphere.

Reference checks use methods that are independent of the code under test:
- closest point on a triangle: brute force over vertices, edge projections and the interior plane projection;
- sphere-box distance: sampling of the box surface;
- rotations: explicit rotation matrices built here, not the library's quaternion code.
"""

import math
import random

import pytest

from reality.collision import narrow as N
from reality.rigidbody import add, cross, dot, norm, scale, sub


def _rot_z(theta):
    c, s = math.cos(theta), math.sin(theta)
    return ((c, -s, 0.0), (s, c, 0.0), (0.0, 0.0, 1.0))


def _rot_x(theta):
    c, s = math.cos(theta), math.sin(theta)
    return ((1.0, 0.0, 0.0), (0.0, c, -s), (0.0, s, c))


def _matmul(a, b):
    return tuple(tuple(sum(a[i][k] * b[k][j] for k in range(3)) for j in range(3)) for i in range(3))


def _brute_closest(p, a, b, c):
    cands = [a, b, c]
    for e0, e1 in ((a, b), (b, c), (c, a)):
        cands.append(N.closest_point_on_segment(p, e0, e1))
    n = cross(sub(b, a), sub(c, a))
    nn = dot(n, n)
    if nn > 0.0:
        t = dot(sub(p, a), n) / nn
        q = add(p, scale(n, -t))
        ab, ac, aq = sub(b, a), sub(c, a), sub(q, a)
        d00, d01, d11 = dot(ab, ab), dot(ab, ac), dot(ac, ac)
        d20, d21 = dot(aq, ab), dot(aq, ac)
        den = d00 * d11 - d01 * d01
        v = (d11 * d20 - d01 * d21) / den
        w = (d00 * d21 - d01 * d20) / den
        if v >= -1e-12 and w >= -1e-12 and v + w <= 1 + 1e-12:
            cands.append(q)
    return min(norm(sub(p, q)) for q in cands)


# ---------------------------------------------------------------- closest point on a triangle
def test_closest_point_matches_brute_force_over_many_scales():
    rng = random.Random(1)
    worst = 0.0
    for _ in range(3000):
        s = 10.0 ** rng.uniform(-6, 3)
        a, b, c = (tuple(rng.uniform(-1, 1) * s for _ in range(3)) for _ in range(3))
        p = tuple(rng.uniform(-1.5, 1.5) * s for _ in range(3))
        q, _ = N.closest_point_on_triangle(p, a, b, c)
        err = abs(norm(sub(p, q)) - _brute_closest(p, a, b, c)) / s
        worst = max(worst, err)
    assert worst < 1e-12, worst


@pytest.mark.parametrize("p, feature", [
    ((0.2, 0.2, 1.0), "face"),       # above the interior
    ((-1.0, -1.0, 0.0), "vertex"),   # beyond vertex a
    ((2.0, 0.0, 0.0), "vertex"),     # beyond vertex b
    ((0.5, -1.0, 0.0), "edge"),      # beyond edge ab
    ((0.5, 0.5, 0.0), "edge"),       # beyond edge bc (hypotenuse)
    ((-1.0, 0.5, 0.0), "edge"),      # beyond edge ca
])
def test_closest_point_feature_regions(p, feature):
    a, b, c = (0.0, 0.0, 0.0), (1.0, 0.0, 0.0), (0.0, 1.0, 0.0)
    q, f = N.closest_point_on_triangle(p, a, b, c)
    assert f == feature
    assert norm(sub(p, q)) == pytest.approx(_brute_closest(p, a, b, c), abs=1e-12)


def test_closest_point_degenerate_collinear_triangle_uses_edges():
    q, f = N.closest_point_on_triangle((0.5, 1.0, 0.0), (0.0, 0.0, 0.0), (1.0, 0.0, 0.0), (2.0, 0.0, 0.0))
    assert f == "edge"
    assert q == pytest.approx((0.5, 0.0, 0.0), abs=1e-15)


def test_closest_point_degenerate_repeated_vertex_is_defined():
    q, f = N.closest_point_on_triangle((0.0, 0.0, 2.0), (0.0, 0.0, 0.0), (0.0, 0.0, 0.0), (1.0, 0.0, 0.0))
    assert q == pytest.approx((0.0, 0.0, 0.0), abs=1e-15)
    assert f == "edge"


# ---------------------------------------------------------------- sphere-triangle
TRI = ((0.0, 0.0, 0.0), (1.0, 0.0, 0.0), (0.0, 1.0, 0.0))


def test_sphere_on_face_normal_depth_and_feature():
    ct = N.sphere_triangle((0.2, 0.2, 0.09), 0.1, *TRI)
    assert ct.feature == "face"
    assert ct.normal == pytest.approx((0.0, 0.0, 1.0), abs=1e-12)
    assert ct.depth == pytest.approx(0.01, abs=1e-12)
    assert ct.point == pytest.approx((0.2, 0.2, 0.0), abs=1e-12)


def test_sphere_touching_edge_and_vertex():
    ct = N.sphere_triangle((0.5, -0.05, 0.0), 0.1, *TRI)   # below edge ab, centre in plane
    assert ct.feature == "edge"
    assert ct.normal == pytest.approx((0.0, -1.0, 0.0), abs=1e-12)
    assert ct.depth == pytest.approx(0.1 - 0.05, abs=1e-12)
    cv = N.sphere_triangle((-0.1, -0.1, 0.0), 0.2, *TRI)    # beyond vertex a
    assert cv.feature == "vertex"
    assert norm(cv.normal) == pytest.approx(1.0, abs=1e-12)
    assert cv.normal == pytest.approx(scale((-0.1, -0.1, 0.0), 1 / norm((-0.1, -0.1, 0.0))), abs=1e-12)


def test_sphere_separated_gives_no_contact_and_touching_gives_depth_zero():
    assert N.sphere_triangle((0.2, 0.2, 0.2), 0.1, *TRI) is None
    ct = N.sphere_triangle((0.2, 0.2, 0.1), 0.1, *TRI)
    assert ct is not None and abs(ct.depth) < 1e-12


def test_sphere_from_both_sides_of_the_triangle():
    above = N.sphere_triangle((0.2, 0.2, 0.05), 0.1, *TRI)
    below = N.sphere_triangle((0.2, 0.2, -0.05), 0.1, *TRI)
    assert above.normal == pytest.approx((0.0, 0.0, 1.0), abs=1e-12)
    assert below.normal == pytest.approx((0.0, 0.0, -1.0), abs=1e-12)
    assert above.depth == pytest.approx(below.depth, abs=1e-12)


def test_reversed_winding_gives_the_same_contact():
    rng = random.Random(7)
    for _ in range(300):
        a, b, c = (tuple(rng.uniform(-1, 1) for _ in range(3)) for _ in range(3))
        p = tuple(rng.uniform(-1.5, 1.5) for _ in range(3))
        r = rng.uniform(0.01, 0.5)
        x = N.sphere_triangle(p, r, a, b, c)
        y = N.sphere_triangle(p, r, a, c, b)
        if x is None:
            assert y is None
            continue
        assert x.depth == pytest.approx(y.depth, abs=1e-12)
        assert x.normal == pytest.approx(y.normal, abs=1e-12)


def test_sphere_centred_on_face_uses_prefer_then_a_winding_free_rule():
    p = (0.2, 0.2, 0.0)
    down = N.sphere_triangle(p, 0.1, *TRI, prefer=(0.0, 0.0, -1.0))
    assert down.normal == pytest.approx((0.0, 0.0, -1.0), abs=1e-12)
    up = N.sphere_triangle(p, 0.1, *TRI, prefer=(0.0, 0.0, 1.0))
    assert up.normal == pytest.approx((0.0, 0.0, 1.0), abs=1e-12)
    # without a preferred side the answer must not depend on winding
    x = N.sphere_triangle(p, 0.1, *TRI)
    y = N.sphere_triangle(p, 0.1, TRI[0], TRI[2], TRI[1])
    assert x.normal == pytest.approx(y.normal, abs=1e-12)
    assert x.depth == pytest.approx(0.1, abs=1e-12)


def test_sphere_on_degenerate_triangle_is_defined_and_finite():
    collinear = ((0.0, 0.0, 0.0), (1.0, 0.0, 0.0), (2.0, 0.0, 0.0))
    ct = N.sphere_triangle((0.5, 0.0, 0.05), 0.1, *collinear)
    assert ct is not None and ct.feature == "edge"
    assert ct.normal == pytest.approx((0.0, 0.0, 1.0), abs=1e-9)
    assert ct.depth == pytest.approx(0.05, abs=1e-12)
    centred = N.sphere_triangle((0.5, 0.0, 0.0), 0.1, *collinear)
    assert all(math.isfinite(x) for x in centred.normal)
    assert norm(centred.normal) == pytest.approx(1.0, abs=1e-9)


def test_near_parallel_contact_is_continuous():
    # centre slightly tilted from the face normal: the normal must follow the centre, not jump
    base = N.sphere_triangle((0.3, 0.3, 0.1), 0.2, *TRI).normal
    for eps in (1e-6, 1e-9, 1e-12):
        ct = N.sphere_triangle((0.3 + eps, 0.3, 0.1), 0.2, *TRI)
        assert norm(sub(ct.normal, base)) < 10 * eps + 1e-9


@pytest.mark.parametrize("s", [1e-6, 1e-3, 1.0, 1e3])
def test_sphere_triangle_is_scale_covariant(s):
    a, b, c = (tuple(x * s for x in v) for v in TRI)
    p = (0.2 * s, 0.25 * s, 0.07 * s)
    ct = N.sphere_triangle(p, 0.1 * s, a, b, c)
    ref = N.sphere_triangle((0.2, 0.25, 0.07), 0.1, *TRI)
    assert ct.normal == pytest.approx(ref.normal, rel=1e-12, abs=1e-15)
    assert ct.depth / s == pytest.approx(ref.depth, rel=1e-10)


def test_sphere_triangle_rejects_nonpositive_radius():
    with pytest.raises(ValueError):
        N.sphere_triangle((0.0, 0.0, 0.0), 0.0, *TRI)


# ---------------------------------------------------------------- sphere-box
UNIT_HALF = (1.0, 2.0, 3.0)
I3 = ((1.0, 0.0, 0.0), (0.0, 1.0, 0.0), (0.0, 0.0, 1.0))


def test_sphere_on_box_face_edge_and_corner_features():
    face = N.sphere_box((0.0, 0.0, 3.0 + 0.4), 0.5, (0, 0, 0), I3, UNIT_HALF)
    assert face.feature == "face" and face.normal == pytest.approx((0, 0, 1), abs=1e-12)
    assert face.depth == pytest.approx(0.1, abs=1e-12)
    edge = N.sphere_box((1.0 + 0.3, 2.0 + 0.4, 0.0), 0.5, (0, 0, 0), I3, UNIT_HALF)
    assert edge.feature == "edge"
    assert edge.normal == pytest.approx(scale((0.3, 0.4, 0.0), 1 / 0.5), abs=1e-12)
    assert edge.depth == pytest.approx(0.5 - 0.5, abs=1e-12)
    corner = N.sphere_box((1.2, 2.2, 3.2), 0.5, (0, 0, 0), I3, UNIT_HALF)   # offset on all three axes
    assert corner.feature == "vertex"
    assert norm(corner.normal) == pytest.approx(1.0, abs=1e-12)


def test_sphere_inside_box_exits_through_nearest_face():
    ct = N.sphere_box((0.9, 0.0, 0.0), 0.05, (0, 0, 0), I3, UNIT_HALF)   # 0.1 from the x = 1 face
    assert ct.normal == pytest.approx((1.0, 0.0, 0.0), abs=1e-12)
    assert ct.depth == pytest.approx(0.05 + 0.1, abs=1e-12)
    assert ct.point == pytest.approx((1.0, 0.0, 0.0), abs=1e-12)


def test_sphere_box_no_contact_outside_range():
    assert N.sphere_box((0.0, 0.0, 3.6), 0.5, (0, 0, 0), I3, UNIT_HALF) is None


def test_rotated_box_contact_follows_the_rotated_face():
    rot = _matmul(_rot_z(0.7), _rot_x(0.4))
    face_normal = (rot[0][2], rot[1][2], rot[2][2])        # body +z axis in world
    centre = scale(face_normal, 3.0 + 0.4)                  # 0.4 above the face (sphere radius 0.5)
    ct = N.sphere_box(centre, 0.5, (0.0, 0.0, 0.0), rot, UNIT_HALF)
    assert ct.feature == "face"
    assert ct.normal == pytest.approx(face_normal, abs=1e-12)
    assert ct.depth == pytest.approx(0.1, abs=1e-12)


def test_sphere_box_contact_point_is_on_the_box_surface_and_is_nearest():
    rng = random.Random(11)
    rot = _matmul(_rot_z(1.1), _rot_x(-0.3))
    half = (0.5, 0.8, 0.3)
    surf = []
    for _ in range(4000):   # sampled box surface in body coordinates, then to world
        face = rng.randrange(6)
        u, v = rng.uniform(-1, 1), rng.uniform(-1, 1)
        axis = face // 2
        loc = [0.0, 0.0, 0.0]
        loc[axis] = (1 if face % 2 else -1) * half[axis]
        loc[(axis + 1) % 3] = u * half[(axis + 1) % 3]
        loc[(axis + 2) % 3] = v * half[(axis + 2) % 3]
        surf.append(tuple(sum(rot[i][k] * loc[k] for k in range(3)) for i in range(3)))
    checked_outside = 0
    for _ in range(300):
        # centres near the surface, so that a good share of cases are touching
        base_pt = surf[rng.randrange(len(surf))]
        d = [rng.gauss(0.0, 1.0) for _ in range(3)]
        dn = norm(d)
        off = rng.uniform(-0.3, 0.3)
        centre = tuple(base_pt[i] + off * d[i] / dn for i in range(3))
        r = rng.uniform(0.05, 0.4)
        local = [sum(rot[k][i] * centre[k] for k in range(3)) for i in range(3)]   # rot^T centre
        inside = all(abs(local[i]) <= half[i] for i in range(3))
        dmin = min(norm(sub(centre, s)) for s in surf)
        ct = N.sphere_box(centre, r, (0, 0, 0), rot, half)
        clamp = [max(-half[i], min(half[i], local[i])) for i in range(3)]
        exact = norm([local[i] - clamp[i] for i in range(3)]) if not inside else None
        if ct is None:
            assert exact is not None and exact > r   # outside and beyond the sphere radius
            assert dmin >= exact - 1e-12             # sampled surface points are never nearer
            continue
        assert norm(ct.normal) == pytest.approx(1.0, abs=1e-9)
        p_local = [sum(rot[k][i] * ct.point[k] for k in range(3)) for i in range(3)]
        assert all(abs(p_local[i]) <= half[i] + 1e-9 for i in range(3))            # inside the box
        assert max(abs(p_local[i]) / half[i] for i in range(3)) == pytest.approx(1.0, abs=1e-9)  # on its surface
        if not inside:
            checked_outside += 1
            dist = norm(sub(centre, ct.point))
            assert dist == pytest.approx(exact, abs=1e-9)          # exact clamp reference
            assert ct.depth == pytest.approx(r - exact, abs=1e-9)
            assert dmin >= exact - 1e-12                           # sampled surface cannot be nearer
    assert checked_outside >= 40, checked_outside


def test_sphere_box_rejects_bad_dimensions():
    with pytest.raises(ValueError):
        N.sphere_box((0, 0, 0), 0.1, (0, 0, 0), I3, (0.0, 1.0, 1.0))
    with pytest.raises(ValueError):
        N.sphere_box((0, 0, 0), 0.0, (0, 0, 0), I3, UNIT_HALF)


# ---------------------------------------------------------------- box-plane
def test_box_flat_on_plane_gives_four_face_corners_with_equal_depth():
    contacts = N.box_corners_plane((0.0, 0.0, 0.2 - 0.001), I3, (0.1, 0.05, 0.2), (0.0, 0.0, 1.0), 0.0)
    assert len(contacts) == 4
    assert all(c.normal == (0.0, 0.0, 1.0) for c in contacts)
    assert all(c.depth == pytest.approx(0.001, abs=1e-12) for c in contacts)


def test_tilted_box_touches_with_one_or_two_corners_and_none_when_above():
    rot = _rot_x(0.2)
    # lowest corner of this box is 0.206 below its centre
    above = N.box_corners_plane((0.0, 0.0, 0.25), rot, (0.1, 0.05, 0.2), (0.0, 0.0, 1.0), 0.0)
    assert above == []
    low = N.box_corners_plane((0.0, 0.0, 0.19), rot, (0.1, 0.05, 0.2), (0.0, 0.0, 1.0), 0.0)
    assert 1 <= len(low) <= 2
    for c in low:
        assert c.normal == (0.0, 0.0, 1.0)
        assert c.depth == pytest.approx(-c.point[2], abs=1e-12)


def test_box_corner_contacts_respect_plane_orientation():
    contacts = N.box_corners_plane((0.0, 0.0, 0.3), I3, (0.1, 0.1, 0.1), (0.0, 0.0, 1.0), 0.0)
    assert contacts == []                       # bottom face is 0.2 above the plane
    contacts = N.box_corners_plane((0.0, 0.0, 0.1), I3, (0.1, 0.1, 0.1), (0.0, 0.0, 1.0), 0.0)
    assert len(contacts) == 4 and all(abs(c.depth) < 1e-12 for c in contacts)


def test_sphere_plane_and_sphere_sphere_reference_cases():
    ct = N.sphere_plane((0.0, 0.0, 0.05), 0.1, (0.0, 0.0, 1.0), 0.0)
    assert ct.depth == pytest.approx(0.05, abs=1e-12)
    assert ct.point == pytest.approx((0.0, 0.0, -0.05), abs=1e-12)
    ss = N.sphere_sphere((0, 0, 0), 0.5, (0.9, 0, 0), 0.5)
    assert ss.normal == pytest.approx((1, 0, 0)) and ss.depth == pytest.approx(0.1)
    with pytest.raises(ValueError):
        N.sphere_sphere((0, 0, 0), 0.5, (0, 0, 0), 0.5)
