"""Angular-momentum residual study for internal two-body box contacts (no external impulses).

For each scene and timestep, measures per contact step:
  dL_pred  : change of total angular momentum about the origin, with centres at the solver's predicted positions
             x_pred = x + h v_pre (the positions the solver takes its lever arms from);
  dL_start : same with centres at the start of the step (the physical configuration at the start).
Also reports linear momentum drift. Run from the reality/ directory: python tools/angular_residual_study.py
"""
import sys

sys.path.insert(0, "src")
import reality.collision.solver as SV  # noqa: E402


def inv3(M):
    a, b, c = M[0]
    d, e, f = M[1]
    g, h, i = M[2]
    det = a * (e * i - f * h) - b * (d * i - f * g) + c * (d * h - e * g)
    inv = [[(e * i - f * h), -(b * i - c * h), (b * f - c * e)],
           [-(d * i - f * g), (a * i - c * g), -(a * f - c * d)],
           [(d * h - e * g), -(a * h - b * g), (a * e - b * d)]]
    return [[x / det for x in row] for row in inv]


def L_of(bodies, positions):
    L = [0.0, 0.0, 0.0]
    for b, r in zip(bodies, positions):
        w = b.omega_world()
        I = inv3(b.inv_inertia_world())
        Lb = [sum(I[i][j] * w[j] for j in range(3)) for i in range(3)]
        v, m = b.velocity, b.mass
        cr = (r[1] * v[2] * m - r[2] * v[1] * m, r[2] * v[0] * m - r[0] * v[2] * m, r[0] * v[1] * m - r[1] * v[0] * m)
        for i in range(3):
            L[i] += Lb[i] + cr[i]
    return L


def p_of(bodies):
    return [sum(b.mass * b.velocity[i] for b in bodies) for i in range(3)]


def scenes():
    yield "oblique_asym_impact", (
        lambda: [SV.Body("A", "box", mass=1.5, position=(-0.35, 0.02, 0.01), velocity=(0.9, 0.1, 0.0),
                         omega_body=(0.3, -0.7, 2.0), half=(0.3, 0.2, 0.1), quaternion=(0.9659258, 0, 0, 0.2588190)),
                 SV.Body("B", "box", mass=0.7, position=(0.35, -0.03, 0.04), velocity=(-0.4, 0.2, -0.1),
                         omega_body=(-1.0, 0.5, 0.0), half=(0.2, 0.25, 0.15), quaternion=(0.9238795, 0.3826834, 0, 0))],
        0.5, 0.3, 0.4)
    yield "face_offset_impact", (
        lambda: [SV.Body("A", "box", mass=1.0, position=(-0.4, 0.05, 0.0), velocity=(1.0, 0.0, 0.0),
                         half=(0.2, 0.2, 0.2)),
                 SV.Body("B", "box", mass=2.0, position=(0.4, 0.0, 0.0), velocity=(-0.3, 0.0, 0.0),
                         omega_body=(0.0, 0.0, 1.5), half=(0.2, 0.2, 0.2))],
        0.5, 0.2, 0.3)
    yield "frictional_pass", (
        lambda: [SV.Body("A", "box", mass=1.0, position=(-0.3, 0.0, 0.0), velocity=(1.0, 0.0, 0.0),
                         half=(0.2, 0.2, 0.2)),
                 SV.Body("B", "box", mass=1.0, position=(0.3, 0.0, 0.0), velocity=(-1.0, 0.0, 0.0),
                         half=(0.2, 0.2, 0.2), omega_body=(0.0, 2.0, 0.0))],
        0.5, 0.0, 0.5)


def measure(make, t_end, e, mu, dt):
    bodies = make()
    specs = [SV.PairSpec("box_box", 0, 1, mu, e)]
    p0 = p_of(bodies)
    worst_pred = worst_start = 0.0
    contacts = 0
    for _ in range(int(round(t_end / dt))):
        x_old = [b.position for b in bodies]
        v_pre = [b.velocity for b in bodies]
        x_pred = [tuple(x_old[i][k] + dt * v_pre[i][k] for k in range(3)) for i in range(len(bodies))]
        Lp0 = L_of(bodies, x_pred)
        Ls0 = L_of(bodies, x_old)
        info = SV.step(bodies, specs, dt, (0.0, 0.0, 0.0))
        if info.touching:
            contacts += 1
            worst_pred = max(worst_pred, max(abs(a - b) for a, b in zip(L_of(bodies, x_pred), Lp0)))
            worst_start = max(worst_start, max(abs(a - b) for a, b in zip(L_of(bodies, x_old), Ls0)))
    dp = max(abs(a - b) for a, b in zip(p_of(bodies), p0))
    return contacts, worst_pred, worst_start, dp


def main():
    for name, (make, t_end, e, mu) in [(n, (m, t, e, mu)) for n, (m, t, e, mu) in scenes()]:
        for dt in (1e-4, 5e-5, 2.5e-5):
            contacts, wp, ws, dp = measure(make, t_end, e, mu, dt)
            print(f"{name:20s} dt {dt:8.2e} contact_steps {contacts:4d}  dL@x_pred {wp:.2e}  dL@x_start {ws:.2e}  "
                  f"max|dP| {dp:.2e}", flush=True)


if __name__ == "__main__":
    main()
