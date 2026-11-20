"""Sweep-count study for the box-box solver. Scratch benchmark (not part of the test suite).

Measures, per scene and per sweep count, the rest-height error (or the slide stop-distance error against v^2/(2 mu g)),
the maximum penetration, contact persistence and tail spin. Writes JSON to argv[1]; optional argv[2] is a comma-separated
sweep list (default 8,16,32,64,128). Run from reality/ with the committed solver. The warm-start variant that was
measured at 8-32 sweeps (BOX_BOX_STUDY.md section 1.1) was reverted from the solver and is not in this script.
"""
import json
import math
import sys
import time

sys.path.insert(0, "src")
import reality.collision.solver as SV  # noqa: E402

G = (0.0, 0.0, -9.80665)
DT = 2e-4


def floor():
    return SV.Body("floor", "box", mass=1.0, static=True, position=(0.0, 0.0, -1.0), half=(5.0, 5.0, 1.0))


def norm(v):
    return math.sqrt(sum(x * x for x in v))




def run(bodies, specs, T, track_last):
    n = int(round(T / DT))
    max_pen = 0.0
    persist = {}
    spin_tail = 0.0
    tail_from = n - int(round(track_last / DT))
    for k in range(n):
        info = SV.step(bodies, specs, DT, G)
        max_pen = max(max_pen, info.max_penetration)
        if k >= tail_from:
            for si in range(len(specs)):
                persist[si] = persist.get(si, 0) + (si in info.touching)
            for b in bodies[1:]:
                spin_tail = max(spin_tail, norm(b.omega_world()))
    frac = {si: persist.get(si, 0) / (n - tail_from) for si in range(len(specs))}
    return max_pen, frac, spin_tail


def scene_flat():
    f = floor()
    b = SV.Body("b", "box", mass=1.0, position=(0.0, 0.0, 0.5), half=(0.3, 0.2, 0.2))
    bodies = [f, b]
    specs = [SV.PairSpec("box_box", 1, 0, 0.5, 0.0)]
    pen, frac, spin = run(bodies, specs, 1.5, 0.5)
    return {"max_pen": pen, "z_err": abs(b.position[2] - 0.2), "persist": frac[0], "tail_spin": spin}


def scene_rot_land():
    th = math.radians(30.0)
    f = floor()
    b = SV.Body("b", "box", mass=1.0, position=(0.0, 0.0, 0.5), half=(0.2, 0.1, 0.1),
                quaternion=(math.cos(th / 2), 0.0, 0.0, math.sin(th / 2)))
    specs = [SV.PairSpec("box_box", 1, 0, 0.5, 0.0)]
    pen, frac, spin = run([f, b], specs, 1.5, 0.5)
    return {"max_pen": pen, "z_err": abs(b.position[2] - 0.1), "persist": frac[0], "tail_spin": spin}


def scene_stack2():
    f = floor()
    lo = SV.Body("lo", "box", mass=1.0, position=(0.0, 0.0, 0.2), half=(0.2, 0.2, 0.2))
    up = SV.Body("up", "box", mass=1.0, position=(0.0, 0.0, 0.62), half=(0.2, 0.2, 0.2))
    specs = [SV.PairSpec("box_box", 1, 0, 0.5, 0.0), SV.PairSpec("box_box", 2, 1, 0.5, 0.0)]
    pen, frac, spin = run([f, lo, up], specs, 1.5, 0.5)
    return {"max_pen": pen, "z_err": max(abs(lo.position[2] - 0.2), abs(up.position[2] - 0.6)),
            "persist": min(frac.values()), "tail_spin": spin}


def scene_stack4():
    f = floor()
    boxes = [SV.Body(f"b{i}", "box", mass=1.0, position=(0.0, 0.0, 0.2 + 0.4 * i + (0.02 if i else 0.0)),
                     half=(0.2, 0.2, 0.2)) for i in range(4)]
    bodies = [f] + boxes
    specs = [SV.PairSpec("box_box", i + 2, i + 1, 0.5, 0.0) for i in range(3)] + [SV.PairSpec("box_box", 1, 0, 0.5, 0.0)]
    pen, frac, spin = run(bodies, specs, 2.0, 0.5)
    err = max(abs(b.position[2] - (0.2 + 0.4 * i)) for i, b in enumerate(boxes))
    return {"max_pen": pen, "z_err": err, "persist": min(frac.values()), "tail_spin": spin}


def scene_slide():
    f = floor()
    b = SV.Body("b", "box", mass=2.0, position=(0.0, 0.0, 0.2), velocity=(1.0, 0.0, 0.0), half=(0.3, 0.2, 0.2))
    specs = [SV.PairSpec("box_box", 1, 0, 0.5, 0.0)]
    pen, frac, spin = run([f, b], specs, 0.6, 0.1)
    analytic = 1.0 / (2 * 0.5 * 9.80665)
    return {"max_pen": pen, "z_err": abs(b.position[0] - analytic), "persist": frac[0], "tail_spin": spin}


def scene_mixed():
    f = floor()
    box = SV.Body("box", "box", mass=1.0, position=(0.0, 0.0, 0.2), half=(0.2, 0.2, 0.2))
    sph = SV.Body("sph", "sphere", mass=0.5, radius=0.1, position=(0.0, 0.0, 0.8))
    bodies = [f, box, sph]
    specs = [SV.PairSpec("box_box", 1, 0, 0.5, 0.0), SV.PairSpec("sphere_box", 1, 2, 0.5, 0.0)]
    pen, frac, spin = run(bodies, specs, 1.5, 0.5)
    return {"max_pen": pen, "z_err": abs(sph.position[2] - 0.5), "persist": min(frac.values()), "tail_spin": spin}


SCENES = {"flat": scene_flat, "rot_land": scene_rot_land, "stack2": scene_stack2, "stack4": scene_stack4,
          "slide": scene_slide, "mixed_sphere": scene_mixed}


def main():
    out = {}
    sweeps_list = [int(x) for x in sys.argv[2].split(",")] if len(sys.argv) > 2 else [8, 16, 32, 64, 128]
    for sweeps in sweeps_list:
        SV.BOX_MANIFOLD_ITERATIONS = sweeps
        for name, fn in SCENES.items():
            t0 = time.time()
            r = fn()
            r["wall_s"] = time.time() - t0
            out[f"{name}|{sweeps}"] = r
            print(f"{name:14s} sweeps {sweeps:3d}: max_pen {r['max_pen']:.3e}  z_err {r['z_err']:.3e}  "
                  f"persist {r['persist']:.3f}  tail_spin {r['tail_spin']:.3e}  wall {r['wall_s']:.1f}s", flush=True)
    with open(sys.argv[1], "w") as fh:
        json.dump(out, fh, indent=1)


if __name__ == "__main__":
    main()
