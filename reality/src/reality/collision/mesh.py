"""Static triangle meshes: validation, a bounding-volume hierarchy (BVH) broad phase, and sphere queries.

Broad phase: an axis-aligned bounding-box BVH over triangles. It is built by median split on the longest axis of the
triangle centroids, with at most ``LEAF_SIZE`` triangles per leaf, so the build is deterministic and O(n log n) in
expectation. A sphere query visits only nodes whose box is within the sphere's radius; the surviving triangles go to
the narrow phase (``narrow.sphere_triangle``).

Brute force (every triangle against the sphere) is kept as a reference for tests and for measuring the BVH speed-up.
It is not used by the simulation.

Limits (validated; see ``MESH_LIMITS``): the number of vertices and triangles per mesh and in total, and the number of
meshes per scene. The build cost grows with triangles, so the limits are set from measurements in COLLISION_GEOMETRY.md.
"""

from __future__ import annotations

import math
from dataclasses import dataclass, field
from typing import Dict, List, Optional, Sequence, Tuple

from ..rigidbody import Mat3, Quat, Vec3, add, mat_t, mat_vec, norm, quat_to_matrix, sub
from .narrow import Contact, sphere_triangle

LEAF_SIZE = 4

# Measured on this machine (2 cores, tools/collision_benchmark.py, untraced build, best of 3): a 199,712-triangle
# UV-sphere mesh validates in 0.68 s, builds its BVH in 4.28 s with 114 MB peak Python memory, and answers a sphere
# query in 0.47 ms. Two meshes at the per-mesh limit fit the total limit: about 9 s of build time. These caps are
# resource limits chosen from those figures, not physical limits of the method.
MESH_LIMITS: Dict[str, int] = {
    "max_meshes": 16,
    "max_vertices_per_mesh": 200_000,
    "max_triangles_per_mesh": 200_000,
    "max_total_triangles": 400_000,
}


def validate_mesh_data(vertices: Sequence, triangles: Sequence, limits: Optional[Dict[str, int]] = None
                       ) -> Tuple[List[str], List[str], int]:
    """Check raw mesh data. Returns (errors, warnings, degenerate_triangle_count). Never raises.

    Errors: wrong shapes, non-finite coordinates, indices out of range, a triangle that repeats a vertex, limits.
    Warnings: zero-area triangles (kept; they still contribute edge contacts).
    """
    lim = dict(MESH_LIMITS if limits is None else limits)
    errors: List[str] = []
    warnings: List[str] = []
    if not isinstance(vertices, list) or not isinstance(triangles, list):
        return ["vertices and triangles must be lists"], warnings, 0
    if len(vertices) < 3:
        errors.append("a mesh needs at least 3 vertices")
    if len(vertices) > lim["max_vertices_per_mesh"]:
        errors.append(f"{len(vertices)} vertices exceed the limit {lim['max_vertices_per_mesh']}")
    if len(triangles) < 1:
        errors.append("a mesh needs at least 1 triangle")
    if len(triangles) > lim["max_triangles_per_mesh"]:
        errors.append(f"{len(triangles)} triangles exceed the limit {lim['max_triangles_per_mesh']}")
    bad_vertex = None
    for i, v in enumerate(vertices):
        if not (isinstance(v, list) and len(v) == 3 and all(_finite(x) for x in v)):
            bad_vertex = i
            break
    if bad_vertex is not None:
        errors.append(f"vertices[{bad_vertex}] must be three finite numbers")
    degenerate = 0
    if not errors and bad_vertex is None:
        nv = len(vertices)
        for t, tri in enumerate(triangles):
            if not (isinstance(tri, list) and len(tri) == 3 and all(isinstance(k, int) and not isinstance(k, bool)
                                                                    for k in tri)):
                errors.append(f"triangles[{t}] must be three integer vertex indices")
                break
            if any(k < 0 or k >= nv for k in tri):
                errors.append(f"triangles[{t}] indexes a vertex outside 0..{nv - 1}")
                break
            if len(set(tri)) < 3:
                errors.append(f"triangles[{t}] repeats a vertex index")
                break
            if _zero_area(vertices, tri):
                degenerate += 1
        if degenerate:
            warnings.append(f"{degenerate} zero-area triangle(s): kept, they give edge contacts only")
    return errors, warnings, degenerate


def _finite(x) -> bool:
    return isinstance(x, (int, float)) and not isinstance(x, bool) and math.isfinite(float(x))


def _zero_area(vertices, tri) -> bool:
    a, b, c = (tuple(float(x) for x in vertices[k]) for k in tri)
    ab = sub(b, a)
    ac = sub(c, a)
    cr = (ab[1] * ac[2] - ab[2] * ac[1], ab[2] * ac[0] - ab[0] * ac[2], ab[0] * ac[1] - ab[1] * ac[0])
    scale2 = max(sum(x * x for x in ab), sum(x * x for x in ac), sum(x * x for x in sub(c, b)), 1e-300) ** 2
    return sum(x * x for x in cr) <= 1e-12 * scale2


@dataclass
class TriangleMesh:
    """A static triangle mesh with its own pose. Vertices are in the mesh frame."""
    name: str
    vertices: Tuple[Vec3, ...]
    triangles: Tuple[Tuple[int, int, int], ...]
    position: Vec3 = (0.0, 0.0, 0.0)
    quaternion: Quat = (1.0, 0.0, 0.0, 0.0)
    bvh: "BVH" = field(init=False, repr=False)

    def __post_init__(self) -> None:
        errors, _, _ = validate_mesh_data([list(v) for v in self.vertices], [list(t) for t in self.triangles])
        if errors:
            raise ValueError(f"mesh {self.name!r}: " + "; ".join(errors))
        self.bvh = BVH(self.vertices, self.triangles)

    @property
    def rotation(self) -> Mat3:
        return quat_to_matrix(self.quaternion)

    def sphere_contacts(self, centre: Vec3, radius: float, prefer: Optional[Vec3] = None,
                        cluster_cos: float = 0.999) -> List[Contact]:
        """Contacts between a world-space sphere and this mesh, reduced to one per normal cluster."""
        rot = self.rotation
        local_c = mat_vec(mat_t(rot), sub(centre, self.position))
        local_pref = None if prefer is None else mat_vec(mat_t(rot), prefer)
        local = drop_dominated_features(self.bvh.sphere_contacts(local_c, radius, local_pref), local_c)
        out = []
        for ct in reduce_contacts(local, cluster_cos):
            out.append(Contact(mat_vec(rot, ct.normal), add(self.position, mat_vec(rot, ct.point)), ct.depth,
                               ct.feature))
        return out

    def sphere_contacts_brute(self, centre: Vec3, radius: float, prefer: Optional[Vec3] = None) -> List[Contact]:
        """Reference: every triangle against the sphere (no BVH). Not used by the simulation."""
        rot = self.rotation
        local_c = mat_vec(mat_t(rot), sub(centre, self.position))
        local_pref = None if prefer is None else mat_vec(mat_t(rot), prefer)
        out = []
        for tri in self.triangles:
            a, b, c = (self.vertices[k] for k in tri)
            ct = sphere_triangle(local_c, radius, a, b, c, local_pref)
            if ct is not None:
                out.append(ct)
        return out


def drop_dominated_features(contacts: Sequence[Contact], centre: Vec3, tol: float = 1e-12) -> List[Contact]:
    """Remove edge and vertex contacts that a strictly closer face contact dominates.

    This removes the internal-edge (ghost) contacts. A flat floor made of two triangles has a seam; a sphere over
    the seam touches both triangles' faces, and it also touches the seam with a tilted normal. The seam is not a
    real edge, and that tilted contact pushes the sphere sideways for no physical reason. A face contact at distance
    d_f is never farther than a point on the same face, so a face contact with d_f <= d_e always dominates an edge
    or vertex contact at d_e. Edge contacts with no closer face contact are kept, so convex edges still act.
    """
    def dist(c: Contact) -> float:
        return norm(sub(centre, c.point))

    face_dists = [dist(c) for c in contacts if c.feature == "face"]
    best_face = min(face_dists) if face_dists else None
    out: List[Contact] = []
    for c in contacts:
        if c.feature == "face":
            out.append(c)
            continue
        d_e = dist(c)
        if best_face is not None and best_face <= d_e + tol * max(1.0, d_e):
            continue
        out.append(c)
    return out


def reduce_contacts(contacts: Sequence[Contact], cluster_cos: float = 0.999) -> List[Contact]:
    """Keep one contact per cluster of nearly equal normals (deepest wins; ties keep the earlier one).

    A sphere resting on a flat mesh touches several triangles with the same normal. Without this reduction it would
    get one solver constraint per triangle. The threshold is a modelling choice (about 2.6 degrees at 0.999).
    """
    kept: List[Contact] = []
    for ct in sorted(contacts, key=lambda c: -c.depth):  # stable: equal depths keep input order
        merged = False
        for k in kept:
            if sum(x * y for x, y in zip(k.normal, ct.normal)) > cluster_cos:
                merged = True
                break
        if not merged:
            kept.append(ct)
    return kept


class BVH:
    """Axis-aligned BVH over triangles. Node arrays: bmin, bmax, left, right (-1 for a leaf), start, count."""

    def __init__(self, vertices: Sequence[Vec3], triangles: Sequence[Tuple[int, int, int]]) -> None:
        self.vertices = [tuple(float(x) for x in v) for v in vertices]
        self.triangles = [tuple(int(k) for k in t) for t in triangles]
        self.bmin: List[Vec3] = []
        self.bmax: List[Vec3] = []
        self.left: List[int] = []
        self.right: List[int] = []
        self.start: List[int] = []
        self.count: List[int] = []
        tri_min = []
        tri_max = []
        tri_cen = []
        for t in self.triangles:
            pts = [self.vertices[k] for k in t]
            tri_min.append(tuple(min(p[i] for p in pts) for i in range(3)))
            tri_max.append(tuple(max(p[i] for p in pts) for i in range(3)))
            tri_cen.append(tuple(sum(p[i] for p in pts) / 3.0 for i in range(3)))
        self.order = list(range(len(self.triangles)))
        self._tri_min = tri_min
        self._tri_max = tri_max
        self._build(0, len(self.order))

    def _build(self, lo: int, hi: int) -> int:
        """Build the subtree for order[lo:hi]; returns its node index."""
        idx = len(self.left)
        mins = [min(self._tri_min[self.order[i]][k] for i in range(lo, hi)) for k in range(3)]
        maxs = [max(self._tri_max[self.order[i]][k] for i in range(lo, hi)) for k in range(3)]
        self.bmin.append(tuple(mins))
        self.bmax.append(tuple(maxs))
        self.left.append(-1)
        self.right.append(-1)
        self.start.append(lo)
        self.count.append(hi - lo)
        if hi - lo <= LEAF_SIZE:
            return idx
        axis = max(range(3), key=lambda k: (maxs[k] - mins[k], -k))
        cen = lambda t: (self._tri_min[t][axis] + self._tri_max[t][axis]) * 0.5  # noqa: E731
        self.order[lo:hi] = sorted(self.order[lo:hi], key=lambda t: (cen(t), t))
        mid = (lo + hi) // 2
        self.left[idx] = self._build(lo, mid)
        self.right[idx] = self._build(mid, hi)
        self.count[idx] = 0
        return idx

    @property
    def node_count(self) -> int:
        return len(self.left)

    def sphere_candidates(self, centre: Vec3, radius: float) -> List[int]:
        """Triangle indices whose node boxes lie within ``radius`` of the centre (a superset of the true hits)."""
        out: List[int] = []
        r2 = radius * radius
        stack = [0]
        while stack:
            n = stack.pop()
            d2 = 0.0
            for k in range(3):
                if centre[k] < self.bmin[n][k]:
                    d2 += (self.bmin[n][k] - centre[k]) ** 2
                elif centre[k] > self.bmax[n][k]:
                    d2 += (centre[k] - self.bmax[n][k]) ** 2
            if d2 > r2:
                continue
            if self.left[n] < 0:
                out.extend(self.order[self.start[n]: self.start[n] + self.count[n]])
            else:
                stack.append(self.right[n])
                stack.append(self.left[n])
        return out

    def sphere_contacts(self, centre: Vec3, radius: float, prefer: Optional[Vec3] = None) -> List[Contact]:
        """Narrow phase over the candidates, in triangle-index order (deterministic)."""
        out = []
        for t in sorted(self.sphere_candidates(centre, radius)):
            a, b, c = (self.vertices[k] for k in self.triangles[t])
            ct = sphere_triangle(centre, radius, a, b, c, prefer)
            if ct is not None:
                out.append(ct)
        return out
