"""Box-box geometry (Phase 7): SAT depth, normals, manifolds, and their analytic and independent references.

The references here are written independently of ``reality.collision.box_box``:

* ``ref_sat15`` evaluates the 15 separating-axis candidates directly from the definitions (A's and B's face normals,
  the normalised cross products of edge directions, skipping near-zero cross products).
* ``ref_dense_min`` is the minimum over a dense set of unit directions of the push-out distance
  ``h_A(u) + h_B(u) - |d . u|``. The kernel's depth can never be above it (it is a minimum over a superset of
  directions' values for the same function), so it is a one-sided check; ``ref_sat15`` gives the equality.
* The analytic configurations use closed forms (overlap of axis-aligned faces, a body diagonal pointing down, a
  plate overlapping by a known amount, scale invariance).

Nothing here compares against MuJoCo; that comparison is an offline tool (``tools/box_box_oracle.py``).
"""

import math
import random

import pytest

from reality.collision import box_box as BB
from reality.collision.narrow import TOUCH_TOL

IDENTITY = ((1.0, 0.0, 0.0), (0.0, 1.0, 0.0), (0.0, 0.0, 1.0))


# ---------------------------------------------------------------- helpers (independent of the kernel)
def rot_from_axes(ax, ay, az):
    """Matrix whose columns are the given unit axes."""
    return tuple(tuple((ax, ay, az)[k][i] for k in range(3)) for i in range(3))


def rot_from_quat(w, x, y, z):
    n = math.sqrt(w * w + x * x + y * y + z * z)
    w, x, y, z = w / n, x / n, y / n, z / n
    return ((1 - 2 * (y * y + z * z), 2 * (x * y - w * z), 2 * (x * z + w * y)),
            (2 * (x * y + w * z), 1 - 2 * (x * x + z * z), 2 * (y * z - w * x)),
            (2 * (x * z - w * y), 2 * (y * z + w * x), 1 - 2 * (x * x + y * y)))


def axes_of(R):
    return [tuple(R[i][k] for i in range(3)) for k in range(3)]


def dot(a, b):
    return a[0] * b[0] + a[1] * b[1] + a[2] * b[2]


def cross(a, b):
    return (a[1] * b[2] - a[2] * b[1], a[2] * b[0] - a[0] * b[2], a[0] * b[1] - a[1] * b[0])


def norm(a):
    return math.sqrt(dot(a, a))


def support_half(axes, h, u):
    return sum(h[k] * abs(dot(axes[k], u)) for k in range(3))


def push_out(cA, RA, hA, cB, RB, hB, u):
    """Overlap of the two projections on unit direction u (positive = overlapping)."""
    d = (cB[0] - cA[0], cB[1] - cA[1], cB[2] - cA[2])
    return support_half(axes_of(RA), hA, u) + support_half(axes_of(RB), hB, u) - abs(dot(d, u))


def ref_sat15(cA, RA, hA, cB, RB, hB):
    """Depth = min over the 15 candidate axes of the push-out distance (eq. 4 with the definition of the axes)."""
    aA, aB = axes_of(RA), axes_of(RB)
    cands = list(aA) + list(aB)
    for a in aA:
        for b in aB:
            c = cross(a, b)
            if norm(c) > 1e-12:
                cands.append(tuple(x / norm(c) for x in c))
    best = None
    for u in cands:
        o = push_out(cA, RA, hA, cB, RB, hB, u)
        if best is None or o < best:
            best = o
    return best


def fibonacci_sphere(n):
    pts = []
    golden = math.pi * (3.0 - math.sqrt(5.0))
    for i in range(n):
        z = 1.0 - 2.0 * (i + 0.5) / n
        r = math.sqrt(max(0.0, 1.0 - z * z))
        t = golden * i
        pts.append((r * math.cos(t), r * math.sin(t), z))
    return pts


_DIRS = fibonacci_sphere(5000)


def ref_dense_min(cA, RA, hA, cB, RB, hB):
    return min(push_out(cA, RA, hA, cB, RB, hB, u) for u in _DIRS)


def random_pose(rng, lo=0.3, hi=1.2):
    q = [rng.gauss(0, 1) for _ in range(4)]
    R = rot_from_quat(*q)
    h = tuple(rng.uniform(lo, hi) for _ in range(3))
    return R, h


def random_pair(rng):
    RA, hA = random_pose(rng)
    RB, hB = random_pose(rng)
    cA = (0.0, 0.0, 0.0)
    d = [rng.uniform(-1.6, 1.6) for _ in range(3)]
    cB = tuple(d)
    return cA, RA, hA, cB, RB, hB


def distance_to_box(p, c, R, h):
    """Euclidean distance from p to the solid box (0 inside)."""
    d = (p[0] - c[0], p[1] - c[1], p[2] - c[2])
    ax = axes_of(R)
    ex = [max(0.0, abs(dot(d, ax[k])) - h[k]) for k in range(3)]
    return norm(ex)


# ---------------------------------------------------------------- axis-aligned and separated
def test_axis_aligned_face_overlap_has_analytic_depth_normal_and_midpoints():
    cA, cB = (0.0, 0.0, 0.0), (1.8, 0.0, 0.0)
    h = (1.0, 1.0, 1.0)
    cts = BB.box_box_contacts(cA, IDENTITY, h, cB, IDENTITY, h)
    assert len(cts) == 4
    sat = BB.box_box_sat(cA, IDENTITY, h, cB, IDENTITY, h)
    assert sat.depth == pytest.approx(0.2, abs=1e-15)
    for ct in cts:
        assert ct.feature == "face"
        assert ct.depth == pytest.approx(0.2, abs=1e-12)
        assert ct.normal == pytest.approx((1.0, 0.0, 0.0), abs=1e-12)
        # midpoint of the overlap along x: between A's face (x = 1) and B's face (x = 0.8)
        assert ct.point[0] == pytest.approx(0.9, abs=1e-12)
        assert abs(ct.point[1]) <= 1.0 + 1e-12 and abs(ct.point[2]) <= 1.0 + 1e-12
    ys = sorted({round(ct.point[1], 12) for ct in cts})
    zs = sorted({round(ct.point[2], 12) for ct in cts})
    assert ys == [-1.0, 1.0] and zs == [-1.0, 1.0]


def test_separated_boxes_give_no_contacts_axis_aligned_and_rotated():
    h = (1.0, 1.0, 1.0)
    assert BB.box_box_contacts((0, 0, 0), IDENTITY, h, (2.0 + 1e-3, 0, 0), IDENTITY, h) == []
    # B turned 45 degrees about z: its half-extent along x is |cos| + |sin| = sqrt(2), so with A's half-extent 1 the
    # boxes are separated by the x axis once the centre distance exceeds 1 + sqrt(2)
    R45 = rot_from_quat(math.cos(math.pi / 8), 0.0, 0.0, math.sin(math.pi / 8))
    assert BB.box_box_contacts((0, 0, 0), IDENTITY, h, (1.0 + math.sqrt(2.0) + 0.05, 0.0, 0.0), R45, h) == []
    assert BB.box_box_contacts((0, 0, 0), IDENTITY, h, (1.0 + math.sqrt(2.0) - 0.05, 0.0, 0.0), R45, h)


def test_exact_touching_and_tiny_gaps_are_handled_at_the_tolerance():
    h = (1.0, 1.0, 1.0)
    # exactly touching faces: zero depth, reported (solver keeps depth > -TOUCH_TOL)
    touch = BB.box_box_contacts((0, 0, 0), IDENTITY, h, (2.0, 0, 0), IDENTITY, h)
    assert touch and all(abs(ct.depth) <= 1e-15 for ct in touch)
    # a separation below TOUCH_TOL is reported as touching (negative depth, kept by the solver as in contact.py);
    # a separation above it is not a contact
    near = BB.box_box_contacts((0, 0, 0), IDENTITY, h, (2.0 + 1e-10, 0, 0), IDENTITY, h)
    assert near and all(-TOUCH_TOL < ct.depth <= -1e-10 + 1e-15 for ct in near)
    assert BB.box_box_contacts((0, 0, 0), IDENTITY, h, (2.0 + 1e-6, 0, 0), IDENTITY, h) == []
    # a penetration far below the tolerance is reported, with its own depth
    pen = BB.box_box_contacts((0, 0, 0), IDENTITY, h, (2.0 - 1e-10, 0, 0), IDENTITY, h)
    assert pen and all(ct.depth == pytest.approx(1e-10, abs=1e-15) for ct in pen)
    assert TOUCH_TOL > 1e-10  # the solver's threshold is above this penetration, so it is still seen as touching


# ---------------------------------------------------------------- rotated pairs: SAT against references
def test_random_rotated_pairs_match_the_15_axis_definition_and_never_beat_dense_sampling():
    rng = random.Random(20260101)
    checked = 0
    for _ in range(300):
        cA, RA, hA, cB, RB, hB = random_pair(rng)
        sat = BB.box_box_sat(cA, RA, hA, cB, RB, hB)
        ref = ref_sat15(cA, RA, hA, cB, RB, hB)
        if ref < 0.0:
            assert sat.separated, (ref, sat)
            continue
        assert not sat.separated
        assert sat.depth == pytest.approx(ref, abs=1e-12), (sat.depth, ref)
        # one-sided check against the dense sample: the true minimum can never be above any sampled value
        assert sat.depth <= ref_dense_min(cA, RA, hA, cB, RB, hB) + 1e-12
        checked += 1
    assert checked > 60  # enough overlapping pairs to be meaningful


def test_contacts_lie_inside_both_boxes_and_normal_points_from_a_to_b():
    rng = random.Random(7)
    n_pairs = 0
    for _ in range(300):
        cA, RA, hA, cB, RB, hB = random_pair(rng)
        cts = BB.box_box_contacts(cA, RA, hA, cB, RB, hB)
        if not cts:
            continue
        n_pairs += 1
        n = cts[0].normal
        assert norm(n) == pytest.approx(1.0, abs=1e-12)
        assert dot(n, (cB[0] - cA[0], cB[1] - cA[1], cB[2] - cA[2])) >= -1e-12
        for ct in cts:
            assert ct.normal == pytest.approx(n, abs=1e-12)
            # The contact is the midpoint of a segment of length `depth`: from a point on the incident box's surface
            # to the reference plane. The segment's start is in the reference box and on the incident surface, so by
            # convexity the midpoint is within depth/2 of both boxes. (It is not always inside the incident box: an
            # oblique normal can leave it through a side face, so "inside both" is not the invariant.)
            assert distance_to_box(ct.point, cA, RA, hA) <= 0.5 * ct.depth + 1e-9
            assert distance_to_box(ct.point, cB, RB, hB) <= 0.5 * ct.depth + 1e-9
    assert n_pairs > 60


def test_edge_contact_is_chosen_by_an_edge_cross_axis_and_is_one_point_on_both_edges():
    rng = random.Random(11)
    found = 0
    for _ in range(3000):
        cA, RA, hA, cB, RB, hB = random_pair(rng)
        sat = BB.box_box_sat(cA, RA, hA, cB, RB, hB)
        if sat.separated or sat.kind != "edge":
            continue
        found += 1
        cts = BB.box_box_contacts(cA, RA, hA, cB, RB, hB)
        assert len(cts) == 1 and cts[0].feature == "edge"
        assert cts[0].depth == pytest.approx(ref_sat15(cA, RA, hA, cB, RB, hB), abs=1e-12)
        # the winning normal is parallel to some cross product of an A edge and a B edge
        aA, aB = axes_of(RA), axes_of(RB)
        ok = False
        for a in aA:
            for b in aB:
                c = cross(a, b)
                if norm(c) > 1e-6 and abs(abs(dot(c, sat.normal)) / norm(c) - 1.0) < 1e-9:
                    ok = True
        assert ok
        if found >= 25:
            break
    assert found >= 25


def test_corner_poking_into_a_face_gives_the_vertex_midpoint():
    # A: unit-half cube at the origin. B: cube of half 0.5 with a body diagonal vertical, so its lowest vertex is
    # sqrt(3) * 0.5 below its centre. Put the centre so that the vertex is 0.1 below A's top face (z = 1).
    h = (1.0, 1.0, 1.0)
    hb = (0.5, 0.5, 0.5)
    # rotation taking the body diagonal u = (1,1,1)/sqrt3 onto -z (axis-angle; axis = u x v normalised)
    u = (1 / math.sqrt(3),) * 3
    v = (0.0, 0.0, -1.0)
    ax = cross(u, v)
    sn = norm(ax)
    ax = tuple(x / sn for x in ax)
    th = math.acos(dot(u, v))
    K = ((0.0, -ax[2], ax[1]), (ax[2], 0.0, -ax[0]), (-ax[1], ax[0], 0.0))
    RB = tuple(tuple((1.0 if i == j else 0.0) + math.sin(th) * K[i][j]
                     + (1 - math.cos(th)) * sum(K[i][k] * K[k][j] for k in range(3)) for j in range(3))
               for i in range(3))
    mapped = tuple(sum(RB[i][j] * u[j] for j in range(3)) for i in range(3))
    assert mapped == pytest.approx(v, abs=1e-12)  # the body diagonal now points straight down
    vertex_offset = math.sqrt(3.0) * 0.5
    cB = (0.0, 0.0, 1.0 + vertex_offset - 0.1)
    cts = BB.box_box_contacts((0, 0, 0), IDENTITY, h, cB, RB, hb)
    sat = BB.box_box_sat((0, 0, 0), IDENTITY, h, cB, RB, hb)
    assert sat.depth == pytest.approx(0.1, abs=1e-9)
    assert ref_sat15((0, 0, 0), IDENTITY, h, cB, RB, hb) == pytest.approx(0.1, abs=1e-9)
    assert cts
    target = (0.0, 0.0, 0.95)  # midpoint of the overlap of the vertex with A's top face
    assert min(norm((ct.point[0] - target[0], ct.point[1] - target[1], ct.point[2] - target[2])) for ct in cts) \
        < 1e-7


# ---------------------------------------------------------------- degenerate, identical, containment, thin
def test_identical_boxes_have_depth_twice_the_smallest_half_extent():
    h = (1.0, 2.0, 3.0)
    cts = BB.box_box_contacts((0, 0, 0), IDENTITY, h, (0, 0, 0), IDENTITY, h)
    assert cts
    assert BB.box_box_sat((0, 0, 0), IDENTITY, h, (0, 0, 0), IDENTITY, h).depth == pytest.approx(2.0, abs=1e-12)
    for ct in cts:
        assert ct.depth == pytest.approx(2.0, abs=1e-9)
        assert distance_to_box(ct.point, (0, 0, 0), IDENTITY, h) <= 0.5 * ct.depth + 1e-9


def test_containment_depth_is_the_smaller_box_plus_the_gap_on_every_axis():
    big, small = (1.0, 1.0, 1.0), (0.5, 0.5, 0.5)
    sat = BB.box_box_sat((0, 0, 0), IDENTITY, big, (0, 0, 0), IDENTITY, small)
    assert not sat.separated
    assert sat.depth == pytest.approx(1.5, abs=1e-12)
    cts = BB.box_box_contacts((0, 0, 0), IDENTITY, big, (0, 0, 0), IDENTITY, small)
    assert cts  # contained box still reports a manifold (no silent drop)


def test_thin_plate_overlap_is_resolved_to_the_analytic_depth():
    eps = 1e-6
    h = (1.0, 1.0, 1.0)
    hp = (1.0, 1.0, eps)
    overlap = 5e-7
    cB = (0.0, 0.0, 1.0 + eps - overlap)  # plate bottom sits 5e-7 below A's top face
    sat = BB.box_box_sat((0, 0, 0), IDENTITY, h, cB, IDENTITY, hp)
    assert sat.depth == pytest.approx(overlap, rel=1e-6)
    cts = BB.box_box_contacts((0, 0, 0), IDENTITY, h, cB, IDENTITY, hp)
    assert cts and all(ct.depth == pytest.approx(overlap, rel=1e-6) for ct in cts)


@pytest.mark.parametrize("scale", [1e-6, 1e3])
def test_depth_scales_linearly_for_tiny_and_large_boxes(scale):
    rng = random.Random(3)
    checked = 0
    for _ in range(80):
        cA, RA, hA, cB, RB, hB = random_pair(rng)
        base = BB.box_box_sat(cA, RA, hA, cB, RB, hB)
        if base.separated:
            continue
        s = scale
        big = BB.box_box_sat(tuple(s * x for x in cA), RA, tuple(s * x for x in hA),
                             tuple(s * x for x in cB), RB, tuple(s * x for x in hB))
        assert not big.separated
        assert big.depth == pytest.approx(s * base.depth, rel=1e-9, abs=1e-18)
        checked += 1
    assert checked > 20


def test_parallel_axes_do_not_crash_and_match_the_exactly_parallel_case():
    h = (0.6, 0.3, 0.2)
    base = BB.box_box_sat((0, 0, 0), IDENTITY, h, (0.7, 0.2, 0.1), IDENTITY, h)
    assert not base.separated
    for angle in (1e-12, 1e-9, 1e-7):
        R = rot_from_quat(math.cos(angle / 2), math.sin(angle / 2), 0.0, 0.0)  # about x: edges stay parallel
        sat = BB.box_box_sat((0, 0, 0), IDENTITY, h, (0.7, 0.2, 0.1), R, h)
        assert not sat.separated
        assert sat.depth == pytest.approx(base.depth, abs=1e-6)
        assert BB.box_box_contacts((0, 0, 0), IDENTITY, h, (0.7, 0.2, 0.1), R, h)


def test_scene_of_box_stack_geometry_has_a_face_manifold_with_four_points():
    # two boxes stacked with the upper one 1 mm into the lower one along z. The smallest half extent is y (0.05),
    # so the overlap must be checked along z, where the upper box's bottom is 0.4 - 0.001 = 0.399 and its centre
    # 0.599. Along y the overlap would be 0.1 and along x 0.2, both larger than 1 mm.
    h = (0.1, 0.05, 0.2)
    sat = BB.box_box_sat((0, 0, 0.2), IDENTITY, h, (0.0, 0.0, 0.599), IDENTITY, h)
    assert sat.depth == pytest.approx(0.001, abs=1e-12) and sat.kind.startswith("face")
    assert sat.normal == pytest.approx((0.0, 0.0, 1.0), abs=1e-12)
    cts = BB.box_box_contacts((0, 0, 0.2), IDENTITY, h, (0.0, 0.0, 0.599), IDENTITY, h)
    assert len(cts) == 4 and all(ct.feature == "face" for ct in cts)
    assert all(ct.depth == pytest.approx(0.001, abs=1e-12) for ct in cts)
