"""Phase 7 (P6) box-box stress runs. Writes a JSON report; prints one line per scene.

Usage (from the reality/ directory):  python tools/box_stress.py OUT.json [scene ...]
Scenes: pile10, column10, wall10, pile100, timing (pile100 takes about 25 min; pile100 is not in the default set). Every number is measured by this script in this run. Scenes are seeded
(random.Random(7)) so runs are reproducible. Pairs are listed exhaustively (no broad phase), which is the current
solver's limit; the timing scene reports the cost of that limit.
"""
import json
import math
import random
import sys
import time

sys.path.insert(0, "src")
import reality.collision.solver as SV  # noqa: E402

G = (0.0, 0.0, -9.80665)


def quat_random(rng):
    # uniform random unit quaternion (Shoemake 1992): uniform over SO(3)
    u1, u2, u3 = rng.random(), rng.random(), rng.random()
    return (math.sqrt(1 - u1) * math.sin(2 * math.pi * u2), math.sqrt(1 - u1) * math.cos(2 * math.pi * u2),
            math.sqrt(u1) * math.sin(2 * math.pi * u3), math.sqrt(u1) * math.cos(2 * math.pi * u3))


def floor():
    return SV.Body("floor", "box", mass=1.0, static=True, position=(0.0, 0.0, -1.0), half=(10.0, 10.0, 1.0))


def pile100():
    # 100 boxes on a 10 x 10 grid (spacing 0.25 m, half 0.1 m), random orientations, random heights 0.5 to 1.5 m, and
    # random initial velocities (each component uniform in [-1, 1] m/s) so that neighbours approach and collide.
    # Without the velocities the boxes fall together, have no relative velocity, and no impulse is applied (a free-fall
    # run: the first version of this scene, measured zero spin, is recorded in BOX_BOX_RUNS.txt section I).
    rng = random.Random(5)
    bodies = [floor()]
    for i in range(100):
        x = (i % 10 - 4.5) * 0.25
        y = (i // 10 - 4.5) * 0.25
        v = tuple(rng.uniform(-1.0, 1.0) for _ in range(3))
        bodies.append(SV.Body(f"b{i}", "box", mass=1.0, position=(x, y, rng.uniform(0.5, 1.5)),
                              velocity=v, half=(0.1, 0.1, 0.1), quaternion=quat_random(rng)))
    specs = all_pairs(bodies, 0.5, 0.0)
    return bodies, specs


def all_pairs(bodies, friction, restitution):
    specs = []
    for i in range(len(bodies)):
        for j in range(i + 1, len(bodies)):
            a, b = bodies[i], bodies[j]
            if a.static and b.static:
                continue
            ka, kb = a.kind, b.kind
            if ka == "box" and kb == "box":
                specs.append(SV.PairSpec("box_box", i, j, friction, restitution))
            elif ka == "sphere" and kb == "sphere":
                specs.append(SV.PairSpec("sphere_sphere", i, j, friction, restitution))
            elif ka == "box" and kb == "sphere":
                specs.append(SV.PairSpec("sphere_box", i, j, friction, restitution))
            else:
                specs.append(SV.PairSpec("sphere_box", j, i, friction, restitution))
    return specs


def energy(bodies):
    ke = sum(b.kinetic_energy() for b in bodies)
    pe = sum(b.mass * (-G[2]) * b.position[2] for b in bodies if not b.static)
    return ke + pe


def run_scene(name, bodies, specs, dt, T, track_from):
    steps = int(round(T / dt))
    max_pen_all = 0.0
    max_pen_tail = 0.0
    contact_pair_steps = 0
    tail_steps = 0
    nonfinite = 0
    t0 = time.time()
    e_start = None
    for k in range(steps):
        try:
            info = SV.step(bodies, specs, dt, G)
        except (ValueError, ZeroDivisionError, OverflowError) as exc:  # a real failure: recorded, not hidden
            return {"name": name, "error": repr(exc), "failed_at_step": k}
        if e_start is None:
            e_start = energy(bodies)
        ok = all(math.isfinite(x) for b in bodies for x in b.position + b.velocity + b.omega_body)
        if not ok:
            nonfinite += 1
            break
        max_pen_all = max(max_pen_all, info.max_penetration)
        contact_pair_steps += len(info.touching)
        if k >= track_from:
            max_pen_tail = max(max_pen_tail, info.max_penetration)
            tail_steps += 1
    wall = time.time() - t0
    dyn = [b for b in bodies if not b.static]
    res = {
        "name": name, "bodies": len(dyn), "pairs_listed": len(specs), "dt": dt, "steps": steps,
        "wall_s": wall, "steps_per_s": steps / wall if wall > 0 else None,
        "max_penetration_all_m": max_pen_all, "max_penetration_tail_m": max_pen_tail,
        "mean_active_pairs_per_step": contact_pair_steps / max(1, steps),
        "nonfinite_steps": nonfinite,
        "max_speed_final_m_s": max(math.sqrt(sum(x * x for x in b.velocity)) for b in dyn),
        "max_spin_final_rad_s": max(math.sqrt(sum(x * x for x in b.omega_world())) for b in dyn),
        "energy_start_J": e_start, "energy_end_J": energy(bodies),
        "energy_end_over_start": energy(bodies) / e_start if e_start else None,
    }
    return res


def pile10():
    rng = random.Random(7)
    bodies = [floor()]
    for i in range(10):
        if i < 3:
            r = rng.uniform(0.06, 0.1)
            bodies.append(SV.Body(f"s{i}", "sphere", mass=rng.uniform(0.5, 2.0), radius=r,
                                  position=(rng.uniform(-0.4, 0.4), rng.uniform(-0.4, 0.4), rng.uniform(0.6, 1.4))))
        else:
            half = tuple(rng.uniform(0.05, 0.15) for _ in range(3))
            bodies.append(SV.Body(f"b{i}", "box", mass=rng.uniform(0.5, 2.0), half=half,
                                  position=(rng.uniform(-0.4, 0.4), rng.uniform(-0.4, 0.4), rng.uniform(0.6, 1.4)),
                                  quaternion=quat_random(rng)))
    specs = all_pairs(bodies, 0.5, 0.1)  # includes the static floor (index 0) with every dynamic body
    return bodies, specs


def column10():
    f = floor()
    boxes = [SV.Body(f"b{i}", "box", mass=1.0, position=(0.0, 0.0, 0.1 + 0.2 * i + (0.005 if i else 0.0)),
                     half=(0.1, 0.1, 0.1)) for i in range(10)]
    bodies = [f] + boxes
    specs = [SV.PairSpec("box_box", i + 1, i, 0.5, 0.0) for i in range(1, 10)] + [SV.PairSpec("box_box", 1, 0, 0.5, 0.0)]
    return bodies, specs, boxes


def wall10():
    # ten boxes fired at 10 m/s at a fixed wall (static box, half 0.05 in x at x = 0); restitution 0.5
    wall = SV.Body("wall", "box", mass=1.0, static=True, position=(0.0, 0.0, 0.5), half=(0.05, 5.0, 5.0))
    rng = random.Random(11)
    bodies = [wall]
    for i in range(10):
        bodies.append(SV.Body(f"b{i}", "box", mass=1.0, position=(-2.0, rng.uniform(-0.6, 0.6), 0.2 + 0.25 * i),
                              velocity=(10.0, 0.0, 0.0), half=(0.1, 0.1, 0.1)))
    specs = [SV.PairSpec("box_box", i, 0, 0.0, 0.5) for i in range(1, 11)]
    specs += [SV.PairSpec("box_box", i, j, 0.0, 0.5) for i in range(1, 11) for j in range(i + 1, 11)]
    return bodies, specs


def timing(n, steps):
    rng = random.Random(3)
    bodies = [floor()]
    for i in range(n):
        bodies.append(SV.Body(f"b{i}", "box", mass=1.0, position=(rng.uniform(-3, 3), rng.uniform(-3, 3), 0.5 + 0.3 * (i % 7)),
                              half=(0.1, 0.1, 0.1), quaternion=quat_random(rng)))
    specs = all_pairs(bodies, 0.5, 0.0)
    t0 = time.time()
    for _ in range(steps):
        SV.step(bodies, specs, 1e-4, G)
    wall = time.time() - t0
    return {"name": f"timing_n{n}", "bodies": n, "pairs_listed": len(specs), "steps_timed": steps,
            "wall_s": wall, "s_per_step": wall / steps}


def main():
    out_path = sys.argv[1]
    want = sys.argv[2:] or ["pile10", "column10", "wall10", "timing"]  # pile100 is run explicitly
    results = []
    if "pile10" in want:
        bodies, specs = pile10()
        results.append(run_scene("pile10", bodies, specs, 2e-4, 3.0, track_from=int(2.0 / 2e-4)))
    if "column10" in want:
        bodies, specs, _ = column10()
        results.append(run_scene("column10", bodies, specs, 1e-4, 2.0, track_from=int(1.5 / 1e-4)))
    if "wall10" in want:
        bodies, specs = wall10()
        results.append(run_scene("wall10", bodies, specs, 1e-4, 1.0, track_from=int(0.9 / 1e-4)))
    if "pile100" in want:
        bodies, specs = pile100()
        results.append(run_scene("pile100", bodies, specs, 1e-4, 0.25, track_from=int(0.2 / 1e-4)))
    if "timing" in want:
        results.append(timing(100, 20))
        results.append(timing(500, 2))
    with open(out_path, "w") as fh:
        json.dump(results, fh, indent=1)
    for r in results:
        print(json.dumps({k: (round(v, 9) if isinstance(v, float) else v) for k, v in r.items()}), flush=True)


if __name__ == "__main__":
    main()
