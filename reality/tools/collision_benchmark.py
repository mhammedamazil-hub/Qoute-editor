"""Measured numbers for the collision milestone. Not part of pytest: wall-clock values are not test assertions.

Usage (from the reality/ directory, with src on the path):
    PYTHONPATH=src python tools/collision_benchmark.py > collision_benchmark.json

Reports, for the machine it runs on:
- mesh build time, peak Python memory (tracemalloc), BVH nodes, and query time for BVH and brute force;
  brute force is run only at sizes where it finishes, as a reference;
- solver throughput (steps per second) for representative scenes, and the same scenes through the
  existing sphere solver (multibody.step_bodies) for comparison.
Every number is the best of REPEATS runs of a fixed workload.
"""

import json
import math
import os
import platform
import random
import sys
import time
import tracemalloc

from reality import contact as CT
from reality import multibody as MB
from reality.collision import mesh as M
from reality.collision import solver as SV

REPEATS = 3
G = (0.0, 0.0, -9.80665)
UP = (0.0, 0.0, 1.0)


def uv_sphere(radius, n_lat, n_lon):
    verts = [(0.0, 0.0, radius)]
    for i in range(1, n_lat):
        th = math.pi * i / n_lat
        for j in range(n_lon):
            ph = 2 * math.pi * j / n_lon
            verts.append((radius * math.sin(th) * math.cos(ph), radius * math.sin(th) * math.sin(ph),
                          radius * math.cos(th)))
    verts.append((0.0, 0.0, -radius))
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


def sphere_mesh_for_triangles(n_tris):
    """A UV sphere with about n_tris triangles (2 n_lon (n_lat - 1) triangles for n_lat, n_lon)."""
    n_lon = max(3, int(round(math.sqrt(n_tris / 2.0))))
    n_lat = max(3, int(round(n_tris / (2.0 * n_lon))) + 1)
    return uv_sphere(1.0, n_lat, n_lon)


def best(fn):
    times = []
    out = None
    for _ in range(REPEATS):
        t0 = time.perf_counter()
        out = fn()
        times.append(time.perf_counter() - t0)
    return min(times), out


def bench_mesh(n_tris, brute_queries):
    verts, tris = sphere_mesh_for_triangles(n_tris)
    vl = [list(v) for v in verts]
    tl = [list(t) for t in tris]
    t_val, (errors, _, _) = best(lambda: M.validate_mesh_data(vl, tl))
    # time the build without any tracer; tracemalloc slows allocation-heavy Python several times over
    t_build, mesh = best(lambda: M.TriangleMesh("bench", tuple(verts), tuple(tris)))
    # peak memory from one separate traced build (the timing above is not taken under tracemalloc)
    tracemalloc.start()
    M.TriangleMesh("bench", tuple(verts), tuple(tris))
    _, peak = tracemalloc.get_traced_memory()
    tracemalloc.stop()
    rng = random.Random(5)
    queries = []
    for _ in range(200):
        centre = tuple(rng.uniform(-1.2, 1.2) for _ in range(3))
        queries.append((centre, rng.uniform(0.02, 0.2)))
    n_q = len(queries)
    t_bvh, _ = best(lambda: [mesh.bvh.sphere_contacts(c, r) for c, r in queries])
    row = {"triangles": len(tris), "vertices": len(verts), "validate_errors": errors,
           "validate_s": round(t_val, 4), "build_s": round(t_build, 4),
           "build_peak_python_mb": round(peak / 2 ** 20, 1), "bvh_nodes": mesh.bvh.node_count,
           "queries": n_q, "bvh_query_ms": round(1000.0 * t_bvh / n_q, 4)}
    if brute_queries:  # brute force is a reference only: run on a prefix of the same queries
        sub = queries[:brute_queries]
        t_brute, _ = best(lambda: [mesh.sphere_contacts_brute(c, r) for c, r in sub])
        t_bvh_sub, _ = best(lambda: [mesh.bvh.sphere_contacts(c, r) for c, r in sub])
        row["brute_queries"] = len(sub)
        row["brute_query_ms"] = round(1000.0 * t_brute / len(sub), 4)
        row["bvh_query_ms_same_subset"] = round(1000.0 * t_bvh_sub / len(sub), 4)
        row["speedup_same_subset"] = round(t_brute / t_bvh_sub, 1)
    return row


def run_steps(fn, steps):
    t, _ = best(fn)
    return {"steps": steps, "seconds": round(t, 4), "steps_per_second": round(steps / t, 0)}


def scene_throughput():
    h = 1e-4
    steps = 5000
    out = {}

    def single_sphere_new():
        b = SV.Body("s", "sphere", 1.0, position=(0.0, 0.0, 0.05), velocity=(0.0, 0.0, 0.0), radius=0.05)
        specs = [SV.PairSpec("sphere_plane", None, 0, 0.3, 0.5, CT.Plane(UP, 0.0))]
        for _ in range(steps):
            SV.step([b], specs, h, G)

    def single_sphere_old():
        s = MB.Sphere("s", 1.0, 0.05, (0.0, 0.0, 0.05), (0.0, 0.0, 0.0))
        for _ in range(steps):
            MB.step_bodies([s], [CT.Plane(UP, 0.0)], [MB.PlaneContact(0, 0, 0.3, 0.5)], h, G)

    def box_on_plane_new():
        b = SV.Body("b", "box", 1.0, position=(0.0, 0.0, 0.2), half=(0.1, 0.05, 0.2))
        specs = [SV.PairSpec("box_plane", None, 0, 0.3, 0.0, CT.Plane(UP, 0.0))]
        for _ in range(steps):
            SV.step([b], specs, h, G)

    floor = ((-2.0, -2.0, 0.0), (2.0, -2.0, 0.0), (2.0, 2.0, 0.0), (-2.0, 2.0, 0.0))
    mesh = M.TriangleMesh("floor", floor, ((0, 1, 2), (0, 2, 3)))

    def sphere_on_mesh_new():
        b = SV.Body("b", "sphere", 1.0, position=(0.3, -0.4, 0.1), radius=0.1)
        specs = [SV.PairSpec("sphere_mesh", None, 0, 0.3, 0.0, mesh)]
        for _ in range(steps):
            SV.step([b], specs, h, G)

    def eight_spheres_new():
        bodies = [SV.Body(f"s{i}", "sphere", 1.0, position=(i * 0.11, 0.0, 0.05), radius=0.05) for i in range(8)]
        specs = [SV.PairSpec("sphere_plane", None, i, 0.3, 0.0, CT.Plane(UP, 0.0)) for i in range(8)]
        specs += [SV.PairSpec("sphere_sphere", i, i + 1, 0.3, 0.0) for i in range(7)]
        for _ in range(steps):
            SV.step(bodies, specs, h, G)

    def eight_spheres_old():
        bodies = [MB.Sphere(f"s{i}", 1.0, 0.05, (i * 0.11, 0.0, 0.05), (0.0, 0.0, 0.0)) for i in range(8)]
        planes = [CT.Plane(UP, 0.0)]
        contacts = [MB.PlaneContact(i, 0, 0.3, 0.0) for i in range(8)]
        contacts += [MB.PairContact(i, i + 1, 0.3, 0.0) for i in range(7)]
        for _ in range(steps):
            MB.step_bodies(bodies, planes, contacts, h, G)

    out["sphere_plane"] = {"general_solver": run_steps(single_sphere_new, steps),
                           "existing_sphere_solver": run_steps(single_sphere_old, steps)}
    out["box_plane"] = {"general_solver": run_steps(box_on_plane_new, steps)}
    out["sphere_mesh_2_triangles"] = {"general_solver": run_steps(sphere_on_mesh_new, steps)}
    out["eight_spheres_plane_and_chain"] = {"general_solver": run_steps(eight_spheres_new, steps // 5),
                                            "existing_sphere_solver": run_steps(eight_spheres_old, steps // 5)}
    return out


def main():
    res = {"machine": {"python": platform.python_version(), "platform": platform.platform(),
                       "cpu_count": os.cpu_count()},
           "repeats": REPEATS, "method": "best of repeats; fixed workloads; see tools/collision_benchmark.py"}
    res["mesh"] = [
        bench_mesh(256, brute_queries=200),
        bench_mesh(4096, brute_queries=200),
        bench_mesh(40000, brute_queries=40),
        bench_mesh(200000, brute_queries=0),  # no brute force at this size: it would not finish in a bounded run
    ]
    res["solver"] = scene_throughput()
    json.dump(res, sys.stdout, indent=2)
    sys.stdout.write("\n")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
