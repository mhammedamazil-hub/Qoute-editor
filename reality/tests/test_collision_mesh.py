"""Static triangle mesh: validation, BVH structure, BVH vs brute force, contact reduction and pose."""

import math
import random

import pytest

from reality.collision import mesh as M
from reality.collision import narrow as N
from reality.rigidbody import norm


def uv_sphere(radius, n_lat, n_lon, centre=(0.0, 0.0, 0.0)):
    verts = [(centre[0], centre[1], centre[2] + radius)]
    for i in range(1, n_lat):
        th = math.pi * i / n_lat
        for j in range(n_lon):
            ph = 2 * math.pi * j / n_lon
            verts.append((centre[0] + radius * math.sin(th) * math.cos(ph),
                          centre[1] + radius * math.sin(th) * math.sin(ph),
                          centre[2] + radius * math.cos(th)))
    verts.append((centre[0], centre[1], centre[2] - radius))
    tris = []
    top, bottom = 0, len(verts) - 1
    ring = lambda i, j: 1 + (i - 1) * n_lon + (j % n_lon)  # noqa: E731
    for j in range(n_lon):
        tris.append((top, ring(1, j), ring(1, j + 1)))
    for i in range(1, n_lat - 1):
        for j in range(n_lon):
            a, b = ring(i, j), ring(i, j + 1)
            c, d = ring(i + 1, j), ring(i + 1, j + 1)
            tris.append((a, c, d))
            tris.append((a, d, b))
    for j in range(n_lon):
        tris.append((ring(n_lat - 1, j + 1), ring(n_lat - 1, j), bottom))
    return verts, tris


def random_soup(n_tris, seed):
    rng = random.Random(seed)
    verts, tris = [], []
    for t in range(n_tris):
        c = [rng.uniform(-1, 1) for _ in range(3)]
        for _ in range(3):
            verts.append(tuple(c[i] + rng.uniform(-0.1, 0.1) for i in range(3)))
        tris.append((3 * t, 3 * t + 1, 3 * t + 2))
    return verts, tris


def _key(ct):
    return (tuple(round(x, 14) for x in ct.normal), round(ct.depth, 14), ct.feature)


# ---------------------------------------------------------------- validation
def test_valid_mesh_has_no_errors():
    e, w, d = M.validate_mesh_data([[0, 0, 0], [1, 0, 0], [0, 1, 0]], [[0, 1, 2]])
    assert e == [] and w == [] and d == 0


@pytest.mark.parametrize("verts, tris, fragment", [
    ([[0, 0, 0], [1, 0, 0]], [[0, 1, 0]], "at least 3 vertices"),
    ([[0, 0, 0], [1, 0, 0], [0, 1, 0]], [], "at least 1 triangle"),
    ([[0, 0, 0], [1, 0, 0], [0, 1, 0]], [[0, 1, 3]], "outside 0..2"),
    ([[0, 0, 0], [1, 0, 0], [0, 1, 0]], [[0, 1, -1]], "outside 0..2"),
    ([[0, 0, 0], [1, 0, 0], [0, 1, 0]], [[0, 0, 1]], "repeats a vertex"),
    ([[0, 0, 0], [1, 0, 0], [0, 1, 0]], [[0, 1, True]], "three integer"),
    ([[0, 0, 0], [1, 0, 0], [0, 1, 0]], [[0, 1]], "three integer"),
    ([[0, 0, 0], [1, 0, 0], [0, math.nan, 0]], [[0, 1, 2]], "vertices[2]"),
    ([[0, 0, 0], [1, 0, 0], [0, math.inf, 0]], [[0, 1, 2]], "vertices[2]"),
    ([[0, 0, 0], [1, 0, 0], [0, 1]], [[0, 1, 2]], "vertices[2]"),
    (None, [[0, 1, 2]], "must be lists"),
])
def test_invalid_mesh_is_reported_with_a_reason(verts, tris, fragment):
    errors, _, _ = M.validate_mesh_data(verts, tris)
    assert errors, "invalid mesh was accepted"
    assert any(fragment in e for e in errors), errors


def test_mesh_limits_are_enforced_with_explicit_errors():
    verts, tris = random_soup(5, 0)
    errors, _, _ = M.validate_mesh_data([list(v) for v in verts], [list(t) for t in tris],
                                        limits={"max_vertices_per_mesh": 10, "max_triangles_per_mesh": 3,
                                                "max_total_triangles": 10, "max_meshes": 1})
    assert any("vertices exceed the limit 10" in e for e in errors)
    assert any("triangles exceed the limit 3" in e for e in errors)


def test_zero_area_triangle_is_a_warning_not_an_error():
    e, w, d = M.validate_mesh_data([[0, 0, 0], [1, 0, 0], [2, 0, 0], [0, 1, 0]],
                                   [[0, 1, 2], [0, 1, 3]])
    assert e == []
    assert d == 1
    assert any("zero-area" in x for x in w)


def test_triangle_mesh_constructor_refuses_invalid_data():
    with pytest.raises(ValueError, match="repeats a vertex"):
        M.TriangleMesh("bad", ((0, 0, 0), (1, 0, 0), (0, 1, 0)), ((0, 0, 1),))


def test_limits_are_not_placeholders():
    # provisional values must be documented as such and be positive integers
    for k, v in M.MESH_LIMITS.items():
        assert isinstance(v, int) and v > 0, k


# ---------------------------------------------------------------- BVH structure
@pytest.mark.parametrize("n_tris", [1, 3, 4, 5, 17, 256, 1000])
def test_every_triangle_appears_in_exactly_one_leaf(n_tris):
    verts, tris = random_soup(n_tris, n_tris)
    bvh = M.BVH(verts, tris)
    seen = []
    for n in range(bvh.node_count):
        if bvh.left[n] < 0:
            assert bvh.count[n] <= M.LEAF_SIZE or bvh.count[n] == n_tris
            seen.extend(bvh.order[bvh.start[n]: bvh.start[n] + bvh.count[n]])
        else:
            assert bvh.count[n] == 0
    assert sorted(seen) == list(range(n_tris))


def test_node_boxes_contain_their_triangles():
    verts, tris = random_soup(300, 5)
    bvh = M.BVH(verts, tris)
    for n in range(bvh.node_count):
        if bvh.left[n] >= 0:
            continue
        for t in bvh.order[bvh.start[n]: bvh.start[n] + bvh.count[n]]:
            for k in tris[t]:
                p = verts[k]
                for i in range(3):
                    assert bvh.bmin[n][i] - 1e-15 <= p[i] <= bvh.bmax[n][i] + 1e-15


def test_bvh_build_is_deterministic():
    verts, tris = uv_sphere(1.0, 16, 24)
    a, b = M.BVH(verts, tris), M.BVH(verts, tris)
    assert a.order == b.order and a.left == b.left and a.start == b.start


# ---------------------------------------------------------------- BVH vs brute force
def _brute(verts, tris, centre, radius, prefer=None):
    out = []
    for tri in tris:
        a, b, c = (verts[k] for k in tri)
        ct = N.sphere_triangle(centre, radius, a, b, c, prefer)
        if ct is not None:
            out.append(ct)
    return out


@pytest.mark.parametrize("name, mesh_fn", [
    ("uv_sphere_484", lambda: uv_sphere(1.0, 12, 22)),
    ("uv_sphere_8170", lambda: uv_sphere(1.0, 44, 95)),
    ("soup_400", lambda: random_soup(400, 3)),
])
def test_bvh_matches_brute_force_exactly(name, mesh_fn):
    verts, tris = mesh_fn()
    bvh = M.BVH(verts, tris)
    rng = random.Random(42)
    lo = [min(v[i] for v in verts) for i in range(3)]
    hi = [max(v[i] for v in verts) for i in range(3)]
    for _ in range(120):
        centre = tuple(rng.uniform(lo[i] - 0.2, hi[i] + 0.2) for i in range(3))
        radius = rng.uniform(0.02, 0.4)
        got = bvh.sphere_contacts(centre, radius)
        ref = _brute(verts, tris, centre, radius)
        assert sorted(map(_key, got)) == sorted(map(_key, ref)), (name, centre, radius)


def test_candidates_are_a_superset_of_all_true_hits():
    verts, tris = uv_sphere(1.0, 30, 40)
    bvh = M.BVH(verts, tris)
    rng = random.Random(9)
    for _ in range(80):
        centre = tuple(rng.uniform(-1.3, 1.3) for _ in range(3))
        radius = rng.uniform(0.01, 0.3)
        cand = set(bvh.sphere_candidates(centre, radius))
        for t, tri in enumerate(tris):
            a, b, c = (verts[k] for k in tri)
            if N.sphere_triangle(centre, radius, a, b, c) is not None:
                assert t in cand


def test_bvh_prunes_work_on_a_distant_sphere():
    verts, tris = uv_sphere(1.0, 44, 95)
    bvh = M.BVH(verts, tris)
    cand = bvh.sphere_candidates((5.0, 0.0, 0.0), 0.1)
    assert cand == []
    cand_near = bvh.sphere_candidates((1.0, 0.0, 0.0), 0.05)
    assert 0 < len(cand_near) < len(tris) // 20


# ---------------------------------------------------------------- reduction and pose
def test_sphere_resting_on_flat_floor_gets_one_contact():
    # a 2x2 m floor split into 200 triangles; a sphere sits on it
    n = 10
    verts = [(-1.0 + 2.0 * i / n, -1.0 + 2.0 * j / n, 0.0) for i in range(n + 1) for j in range(n + 1)]
    tris = []
    for i in range(n):
        for j in range(n):
            a = i * (n + 1) + j
            b, c, d = a + 1, a + (n + 1), a + (n + 1) + 1
            tris.append((a, b, d))
            tris.append((a, d, c))
    mesh = M.TriangleMesh("floor", tuple(verts), tuple(tris))
    contacts = mesh.sphere_contacts((0.31, -0.17, 0.09), 0.1)
    assert len(contacts) == 1
    assert contacts[0].normal == pytest.approx((0.0, 0.0, 1.0), abs=1e-12)
    assert contacts[0].depth == pytest.approx(0.01, abs=1e-12)
    raw = mesh.sphere_contacts_brute((0.31, -0.17, 0.09), 0.1)
    assert len(raw) > 1, "the reduction should have had several raw contacts to merge"


def test_public_mesh_contacts_equal_filtered_brute_reference():
    # the BVH path with filtering and reduction must equal: brute force, then filter, then reduce
    verts, tris = uv_sphere(1.0, 20, 30)
    mesh = M.TriangleMesh("s", tuple(verts), tuple(tris))
    rng = random.Random(21)
    for _ in range(60):
        centre = tuple(rng.uniform(-1.2, 1.2) for _ in range(3))
        radius = rng.uniform(0.02, 0.3)
        ref = M.reduce_contacts(M.drop_dominated_features(mesh.sphere_contacts_brute(centre, radius), centre))
        got = mesh.sphere_contacts(centre, radius)
        assert sorted(map(_key, got)) == sorted(map(_key, ref)), (centre, radius)


def test_dominated_seam_contact_is_removed_and_convex_edge_is_kept():
    # two coplanar triangles: the seam contact is removed because the face contact is closer
    seam = [N.Contact((0.0, 0.0, 1.0), (0.31, -0.17, 0.0), 0.01, "face"),   # projection of the centre
            N.Contact((0.316, 0.949, 0.0), (0.31, -0.2, 0.0), 0.005, "edge")]
    kept = M.drop_dominated_features(seam, (0.31, -0.17, 0.09))
    assert [c.feature for c in kept] == ["face"]
    # a convex edge with no closer face contact is kept (centre beyond the edge, no face in range)
    edge_only = [N.Contact((0.0, -0.7071, 0.7071), (0.0, 0.0, 0.0), 0.02, "edge")]
    assert M.drop_dominated_features(edge_only, (0.0, -0.08, 0.08)) == edge_only


def test_reduce_contacts_keeps_distinct_normals_and_deepest():
    a = N.Contact((0.0, 0.0, 1.0), (0, 0, 0), 0.01, "face")
    b = N.Contact((0.0, 0.0, 1.0), (0, 0, 0), 0.02, "face")
    c = N.Contact((1.0, 0.0, 0.0), (0, 0, 0), 0.005, "edge")
    out = M.reduce_contacts([a, b, c])
    assert [x.depth for x in out] == [0.02, 0.005]


def test_mesh_pose_moves_the_contact_with_the_mesh():
    verts = [(-1.0, -1.0, 0.0), (1.0, -1.0, 0.0), (1.0, 1.0, 0.0), (-1.0, 1.0, 0.0)]
    tris = [(0, 1, 2), (0, 2, 3)]
    base = M.TriangleMesh("m", tuple(verts), tuple(tris))
    # rotate 90 degrees about x, then translate
    s = math.sqrt(0.5)
    moved = M.TriangleMesh("m", tuple(verts), tuple(tris), position=(0.0, 0.0, 2.0),
                           quaternion=(s, s, 0.0, 0.0))
    c0 = base.sphere_contacts((0.2, 0.1, 0.05), 0.1)
    # the same relative position in the moved frame: rotate the local centre by Rx(90)
    local = (0.2, 0.1, 0.05)
    world = (local[0], -local[2], local[1])
    c1 = moved.sphere_contacts((world[0], world[1], world[2] + 2.0), 0.1)
    assert len(c0) == len(c1) == 1
    assert c1[0].depth == pytest.approx(c0[0].depth, abs=1e-12)
    # local +z maps to world -y under a 90 degree rotation about x, and the normal points at the sphere
    assert c1[0].normal == pytest.approx((0.0, -1.0, 0.0), abs=1e-12)
    assert norm(c1[0].normal) == pytest.approx(1.0, abs=1e-12)
