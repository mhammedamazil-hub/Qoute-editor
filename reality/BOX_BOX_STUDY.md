# Box–box study: sweep count, angular residual, edge cases, stress, Blender (Phase 7, P5–P7)

Every number here was measured by a script named in the text, in this repository, on this machine (2 cores, shared
sandbox). Nothing is taken from another project. The raw output of the cited runs is in `BOX_BOX_RUNS.txt`. Where a value
came from an earlier code state, the text says so.

Shipped setting for the final numbers: `BOX_MANIFOLD_ITERATIONS = 128`, `PROJECTION_PASSES = 40`,
`PROJECTION_TOL = 1e-12`. Earlier settings are labelled where used: 64 sweeps with cap 40, and cap 10 (§1, §4, §5).

Scripts (run from `reality/`):

- `tools/box_sweep_study.py OUT.json [sweeps]` — sweep-count study (§1). Sets the sweep count itself.
- `tools/angular_residual_study.py` — angular-momentum residual on internal contacts (§2).
- `tools/box_stress.py OUT.json [scene ...]` — stress scenes and per-step timing (§4).
- `tests/test_collision_box_box_edge_cases.py` — edge cases (§3).
- `tools/blender_smoke.py` — 47 headless `bpy` checks (§6).

---

## 1. Sweep count (Issue A)

Scenes (dt 2e-4 s, gravity −9.80665 m/s², static floor top at z = 0; definitions from `tools/box_sweep_study.py`):

| scene | setup | reference |
|---|---|---|
| flat | box 0.6×0.4×0.4 m dropped from z = 0.5 | rest centre z = 0.2 |
| rot_land | box 0.4×0.2×0.2 m rotated 30° about z, dropped from z = 0.5 | rest centre z = 0.1 |
| stack2 | two 0.4 m cubes; upper starts at z = 0.62 (0.02 m above contact) | z = 0.2, 0.6 |
| stack4 | four 0.4 m cubes; each upper one starts 0.02 m above contact | z = 0.2, 0.6, 1.0, 1.4 |
| slide | box 0.6×0.4×0.4 m, 2 kg, v = 1 m/s in x, μ = 0.5 | stop at v²/(2μg) = 0.101972 m |
| mixed_sphere | 0.4 m cube on the floor; sphere r = 0.1 m dropped onto it | sphere centre z = 0.5 |

Columns (definitions from the script): `max pen` = largest penetration over the run; `z_err` = worst rest-height error
(slide: absolute error of the stop position); `persist` = minimum over the scene's contact pairs of the fraction of steps
in the final window in which the pair is in the solver's `touching` set; `tail_spin` = largest |ω| of a moving body in
the final window. Durations: flat, rot_land, stack2, mixed_sphere 1.5 s (window 0.5 s); stack4 2.0 s (window 0.5 s);
slide 0.6 s (window 0.1 s).

**Final code** (`/tmp/sweep_final.txt`, sweep counts 8–128, projection cap 40):

| scene | sweeps | max pen (m) | z_err (m) | persist | tail_spin (rad/s) |
|---|---|---|---|---|---|
| flat | 8 | 0.0e+00 | 2.0e-07 | 1.000 | 1.3e-02 |
| flat | 16 | 0.0e+00 | 2.4e-07 | 1.000 | 2.2e-07 |
| flat | 32 | 0.0e+00 | 6.3e-08 | 1.000 | 8.1e-11 |
| flat | 64 | 0.0e+00 | 6.3e-08 | 1.000 | 1.1e-17 |
| flat | 128 | 0.0e+00 | 6.3e-08 | 1.000 | 3.0e-19 |
| rot_land | 8 | 8.9e-13 | 1.9e-07 | 1.000 | 1.4e-02 |
| rot_land | 16 | 0.0e+00 | 1.7e-07 | 1.000 | 2.9e-04 |
| rot_land | 32 | 0.0e+00 | 8.3e-08 | 1.000 | 3.1e-10 |
| rot_land | 64 | 0.0e+00 | 8.4e-08 | 1.000 | 6.6e-17 |
| rot_land | 128 | 0.0e+00 | 8.4e-08 | 1.000 | 1.2e-18 |
| stack2 | 8 | 1.0e-12 | 3.1e-07 | 0.850 | 9.9e-03 |
| stack2 | 16 | 1.0e-12 | 3.0e-07 | 0.915 | 9.4e-03 |
| stack2 | 32 | 1.0e-12 | 3.4e-07 | 0.952 | 6.7e-03 |
| stack2 | 64 | 1.0e-12 | 1.8e-07 | 1.000 | 5.3e-03 |
| stack2 | 128 | 9.9e-13 | 4.2e-09 | 1.000 | 1.0e-08 |
| stack4 | 8 | 4.2e-08 | 1.1e-06 | 0.643 | 2.4e-02 |
| stack4 | 16 | 1.8e-08 | 1.8e-06 | 0.693 | 2.6e-02 |
| stack4 | 32 | 1.1e-08 | 1.3e-06 | 0.799 | 2.4e-02 |
| stack4 | 64 | 1.1e-08 | 4.9e-07 | 0.862 | 2.7e-02 |
| stack4 | 128 | 1.1e-08 | 1.2e-06 | 0.811 | 2.3e-02 |
| slide | 8 | 0.0e+00 | 1.0e-04 | 1.000 | 4.1e-04 |
| slide | 16 | 1.0e-12 | 1.0e-04 | 1.000 | 2.2e-07 |
| slide | 32 | 1.0e-12 | 1.0e-04 | 1.000 | 8.1e-11 |
| slide | 64 | 0.0e+00 | 1.0e-04 | 1.000 | 1.1e-15 |
| slide | 128 | 0.0e+00 | 1.0e-04 | 1.000 | 1.1e-15 |
| mixed_sphere | 8 | 1.0e-12 | 2.0e-07 | 1.000 | 1.0e-02 |
| mixed_sphere | 16 | 9.4e-13 | 2.0e-07 | 1.000 | 4.9e-04 |
| mixed_sphere | 32 | 9.6e-13 | 8.5e-10 | 1.000 | 1.0e-07 |
| mixed_sphere | 64 | 6.2e-13 | 6.2e-13 | 1.000 | 4.0e-14 |
| mixed_sphere | 128 | 6.2e-13 | 6.2e-13 | 1.000 | 1.5e-16 |

Slide: the stop-distance error is 1.0e-4 m at every count (the explicit-step discretisation of friction). It was not
measured against dt in this study, so no dt-scaling is claimed.

**Earlier code** (`/tmp/sweep_base.txt`, projection cap 10, before the §5 fix). Only the stack rows changed with the cap,
so the other scenes are omitted here. Values:

| scene | sweeps | max pen (m) | persist | tail_spin (rad/s) |
|---|---|---|---|---|
| stack2 | 8 / 16 / 32 / 64 / 128 | 4.5e-9 / 3.2e-9 / 6.1e-9 / 3.8e-10 / 7.3e-11 | 0.822 / 0.936 / 0.945 / 1.000 / 1.000 | 7.5e-3 / 8.1e-3 / 6.0e-3 / 5.3e-3 / 1.0e-8 |
| stack4 | 8 / 16 / 32 / 64 / 128 | 5.8e-6 / 2.3e-6 / 1.3e-6 / 1.4e-6 / 1.3e-6 | 0.870 / 0.895 / 0.857 / 0.946 / 0.948 | 2.2e-2 / 1.9e-2 / 1.9e-2 / 1.9e-2 / 1.8e-2 |

The cap change reduced stack4 penetration by about 100× (1.3e-6 → 1.1e-8 m at 32–128 sweeps) and changed its
persistence and spin. The cap-40 numbers are the ones that describe the shipped solver.

### 1.1 Warm starting (tried, reverted)

A warm-start variant (the impulses of each box pair are carried to the next step and matched to the nearest contact
point of the same pair) was run at 8, 16 and 32 sweeps with the cap-10 code (`WARM=1`, no longer in the script; output
`/tmp/sweep_warm.txt`). Cold values are the cap-10 run.

| scene | sweeps | warm: tail_spin | warm: persist | cold: tail_spin | cold: persist |
|---|---|---|---|---|---|
| flat | 8 | 1.3e-02 | 1.000 | 1.3e-02 | 1.000 |
| flat | 16 | 1.6e-12 | 1.000 | 2.2e-07 | 1.000 |
| flat | 32 | 6.5e-23 | 1.000 | 8.1e-11 | 1.000 |
| rot_land | 8 | 1.2e-02 | 1.000 | 1.4e-02 | 1.000 |
| rot_land | 16 | 2.9e-04 | 1.000 | 2.9e-04 | 1.000 |
| rot_land | 32 | 9.1e-19 | 1.000 | 3.1e-10 | 1.000 |
| stack2 | 8 | 1.3e-02 | 0.846 | 7.5e-03 | 0.822 |
| stack2 | 16 | 5.5e-03 | 0.881 | 8.1e-03 | 0.936 |
| stack2 | 32 | 7.2e-03 | 0.986 | 6.0e-03 | 0.945 |
| stack4 | 8 | 1.8e-02 | 0.660 | 2.2e-02 | 0.870 |
| stack4 | 16 | 1.8e-02 | 0.802 | 1.9e-02 | 0.895 |
| stack4 | 32 | 1.8e-02 | 0.904 | 1.9e-02 | 0.857 |

The result is **mixed**. Warm starting removed the single-box landing spin at 16–32 sweeps, lowered the stack2 spin at 16
sweeps and raised it at 32, and gave lower persistence at 8–16 sweeps. It was reverted. It was measured only at the cap-10
code and only at 8–32 sweeps, so it is not evaluated at the shipped count. It remains open.

### 1.2 The stack spin: what the final data show

Frictionless and frictional stacks, final code unless stated:

| case | sweeps | projection | tail_spin (rad/s) | source |
|---|---|---|---|---|
| stack4, μ = 0 | 64 | on (cap 40) | 4.89e-2 | `/tmp/stack4_mu0.py` (final) |
| stack4, μ = 0 | 64 | off | 1.90e-5 | same |
| stack4, μ = 0 | 128 | on | 1.56e-11 | same; lateral drift 2.8e-9 m |
| stack4, μ = 0 | 256 | on | 5.3e-18 | same; lateral drift 3.7e-16 m |
| stack4, μ = 0.5 | 64 | on | 2.74e-2 | same |
| stack4, μ = 0.5 | 128 | on | 2.30e-2 | sweep study (§1 table) |
| stack4, μ = 0.5 | 256 | on | 2.04e-2 | same; lateral drift 4.6e-5 m |
| stack2, μ = 0.5 | 64 | on | 5.35e-3 | `/tmp/stack2_factors.py` (final) |
| stack2, μ = 0.5 | 64 | off | 1.73e-3 | same |
| stack2, μ = 0 | 64 | on or off | 1.2e-18 | same |

Reading:

- **Frictionless stacks: the spin is a sweep-convergence artefact, amplified by projection.** With μ = 0 the spin
  falls from 4.9e-2 rad/s (64 sweeps) to 1.6e-11 (128) and 5e-18 (256). With projection off it is 1.9e-5 at 64 sweeps. A
  frictionless stack has no torque source, so the spin is a residual of an unconverged velocity solve. Projection moves
  the corners, and that turns the residual into rotation. This is the interpretation the sweep dependence supports; the
  exact route from corner positions to rotation is not isolated.
- **Frictional stacks: the spin is not a sweep artefact for a four-box stack.** With μ = 0.5 the four-box stack spins at
  about 2e-2 rad/s at 128 and 256 sweeps, and its persistence is below 1 for the lower pairs. This is a separate open
  defect. It is not fixed by more sweeps, and it is not explained yet. Earlier notes (friction anchor, per-point clamping,
  `BOX_BOX_RESEARCH.md` §6) are candidate explanations, not tested here.
- **Two-box friction stack: friction spin decays with sweeps.** 5.3e-3 rad/s at 64, 1.0e-8 at 128.

### 1.3 Answers to the Issue A questions

- **Why 8, 16 and 32 are worse.** They do not converge the velocity solve. The frictionless four-box stack shows this
  most clearly: its spin decays with sweeps (§1.2). The two-box friction stack spin also decays (9.9e-3 at 8, 6.7e-3 at 32).
- **Is 64 needed?** 64 is not enough. The two-box friction stack still spins at 5.3e-3 rad/s at 64 and reaches 1.0e-8 at
  128. The frictionless four-box stack reaches 1e-11 at 128. The smallest tested count that converges both is 128.
- **Consistency across scenes.** Flat and rotated landings converge by 32 sweeps. The stacks need 128. The four-box
  stack with friction does not converge at 256 (§1.2).
- **Solver ordering, block solving, friction formulation.** Not tested in this study. Not claimed. The four-box friction
  case is the likely place to test them.
- **Warm starting and accumulated impulses.** Tested at 8–32 sweeps, mixed, not adopted (§1.1).
- **Manifold conditioning.** A four-point coplanar patch gives a load split that Gauss–Seidel converges to slowly. This is
  consistent with the frictionless convergence data, but is not measured directly.
- **Cost.** Measured wall times in the sweep study: flat 15.3 s at 64 sweeps and 22.9 s at 128 (about 1.5×); stack4
  161.7 s at 64 and 259.8 s at 128 (about 1.6×). These include the study's own overhead.

**Decision.** `BOX_MANIFOLD_ITERATIONS` is raised from 64 to 128. This is justified by the measurements above, not by
speed. Raising it does not fix the four-box friction stack, which remains an open item (§7).

## 2. Angular-momentum residual (Issue B)

`tools/angular_residual_study.py`: internal two-body contacts, no gravity, no floor. For each contact step,
`dL@x_pred` is the change in total angular momentum about the origin with the centres at the solver's predicted
positions `x_pred = x + h·v_pre` (where the solver takes its lever arms); `dL@x_start` uses the start-of-step centres.
Rerun on the final code: the values are identical to the earlier run (`BOX_BOX_RUNS.txt` §D).

| scene | dt (s) | contact steps | dL @ x_pred | dL @ x_start | max \|ΔP\| |
|---|---|---|---|---|---|
| oblique asymmetric impact | 1e-4 | 2 | 1.3e-13 | 1.3e-5 | 2e-16 |
| oblique asymmetric impact | 5e-5 | 2 | 1.6e-14 | 6.4e-6 | 2e-16 |
| oblique asymmetric impact | 2.5e-5 | 2 | 2.0e-15 | 3.2e-6 | 2e-16 |
| face offset impact (spin on B) | 1e-4 | 1 | 1.2e-17 | 1.1e-5 | 0 |
| face offset impact | 5e-5 | 1 | 6.9e-18 | 5.4e-6 | 6e-17 |
| face offset impact | 2.5e-5 | 1 | 1.2e-17 | 2.7e-6 | 0 |
| frictional pass (μ = 0.5) | 1e-4 | 74 | 2.1e-17 | 1.6e-5 | 0 |
| frictional pass | 5e-5 | 3 | 4.9e-17 | 7.9e-6 | 0 |
| frictional pass | 2.5e-5 | 197 | 1.4e-17 | 3.9e-6 | 0 |

Findings:

- At the predicted configuration the change in angular momentum is small. It is 1.3e-13 at dt 1e-4 for the oblique case,
  falling to 1.6e-14 and 2.0e-15 at dt 5e-5 and 2.5e-5. The other scenes are at 5e-17 or below. The oblique residual
  at x_pred is not exactly zero, and its dt-dependence is not explained. The impulse operator is exact about the arms the
  solver uses, so the residual is attributed to the step's other terms; this attribution is not isolated.
- At the start-of-step centres the residual is first order: about 0.13·dt (oblique), 0.11·dt (face offset) and 0.16·dt
  (frictional pass) per contact step, halving when dt halves.
- Interpretation (not isolated): the residual at the start-of-step centres comes from the semi-implicit position update.
  The solver moves the centres by h·v_post after the impulses, while its lever arms refer to x_pred = x + h·v_pre. The
  difference h·Δv per body would give an O(h) term. Moving with the start-of-step velocity was not tested, so no
  correction is claimed.
- The number of contact steps in the frictional pass is not monotonic in dt (74, 3, 197). Not investigated. The
  likely cause is the 1 nm reporting threshold on the predicted state (hypothesis, not measured). The per-step residual
  is measured on every contact step, so the residual result does not depend on the count.
- Linear momentum is conserved to rounding in every case.

Earlier, in the free flight of asymmetric bodies, a defect was found and fixed: the rotate step dropped the gyroscopic
term. A box with ω_body = (2, −1, 3) over 0.2 s differed from the Euler-equation reference by 1.04 rad/s before the fix.
After it, the difference is 3e-13 rad/s (`test_free_flight_of_an_asymmetric_box_follows_euler_equations_and_conserves_world_angular_momentum`).
World angular momentum drifts 4.8e-10, 1.2e-10 and 3.0e-11 for dt 1e-4, 5e-5, 2.5e-5 (order dt²).

---

## 3. Edge cases (P5)

`tests/test_collision_box_box_edge_cases.py` (8 tests, all passing):

| test | what it checks | measured/analytic basis |
|---|---|---|
| nearly parallel boxes | 1e-9 rad tilt matches the aligned manifold | depth within 1e-8 m; normal on x |
| grazing rim overlap | 1e-4 m rim overlap takes the minimum axis | normal ±x, depth 1e-4 m (not the 0.01 m z overlap) |
| extreme mass ratio 1000:1 | elastic head-on | v_light 1.998002, v_heavy 0.998001 m/s; momentum 1e-9; energy rel 1e-5 |
| box falls on a box | drop onto a resting box | rest centres 0.2 and 0.6 m (abs 1e-5); top spin and speed < 1e-5; penetration ≤ 1e-4 m |
| 20 m/s impact, e = 0.5 | rebound measured in the impact step | 10.098 m/s ≈ e·20.195 (asserted rel 1e-3); energy ratio 0.25 (asserted rel 2e-3) |
| quaternion over 20000 steps | spinning free flight | norm error ≤ 1e-12; orthogonality ≤ 1e-12 |
| identical stationary boxes | coincident centres | finite state, momentum 0 |
| three-box impact at the bake step | regression (see §5) | max penetration ≤ 1e-6 m; heights 0.1, 0.3, 0.5 m |

Two of the tests were first written with wrong expectations (a grazing case whose minimum axis is x, and a rebound
measured after gravity had acted). The kernel was right in both cases, and the tests were corrected. They were not
loosened.

The existing geometry file (`test_collision_box_box.py`, 14 tests) already covers faces, edges, corners, identical and
contained boxes, thin plates, tiny and large sizes, parallel axes, the 15-axis definition against dense sampling
(20,000 directions), and the stack geometry.

---

---

## 4. Stress (P6)

`tools/box_stress.py` (all pairs listed every step; no broad phase). Final setting: 128 sweeps, projection cap 40. Raw JSON
and text: `/tmp/stress_128.json`, `/tmp/stress_128.txt` (summarised verbatim in `BOX_BOX_RUNS.txt` §I). Energy is kinetic
plus gravitational potential energy, end/start.

**Final setting (128 sweeps, cap 40)**

| scene | bodies | dt, duration | steps/s | max penetration (m) | final max speed (m/s) | final max spin (rad/s) | energy end/start |
|---|---|---|---|---|---|---|---|
| pile10 (3 spheres, 7 random boxes) | 10 | 2e-4 s, 3 s | 32.9 | 0 (all steps) | 0.566 | 8.47 (not settled) | 0.115 |
| column10 (10-box tower, 5 mm gaps) | 10 | 1e-4 s, 2 s | 12.4 | 7.06e-7 (tail 3.2e-7) | 0.0077 | 0.021 | 0.9955 |
| wall10 (10 boxes at 10 m/s, e = 0.5, fixed wall) | 10 | 1e-4 s, 1 s | 345 | 0 | 11.008 (see below) | 0 | 0.405 |
| timing N = 100 (random, all pairs) | 100 | 1e-4 s, 20 steps | — | — | — | — | 0.315 s/step |
| pile100 (100 boxes, 10×10 grid, random velocities and orientations) | 100 | 1e-4 s, 0.25 s | 1.77 | 0 (all steps) | 3.39 | 10.8 (boxes tumbling) | 0.960 |
| timing N = 100 (random, all pairs) | 100 | 1e-4 s, 20 steps | — | — | — | — | 0.315 s/step |
| timing N = 500 (random, all pairs) | 500 | 1e-4 s, 2 steps | — | — | — | — | 61.5 s/step |

No non-finite states in any scene.

**Comparison with the earlier settings** (same scripts; `/tmp/stress1.json`, `/tmp/stress_final.json`, `/tmp/stress_timing.json`):

| scene / metric | 64 sweeps, cap 10 | 64 sweeps, cap 40 | 128 sweeps, cap 40 (shipped) |
|---|---|---|---|
| pile10 steps/s | 61.5 | 59.0 | 32.9 |
| pile10 max penetration | 2.56e-6 m | 2.0e-12 m | 0 |
| pile10 final spin | 8.49 rad/s | 7.31 | 8.47 |
| column10 steps/s | 26.1 | 19.2 | 12.4 |
| column10 max penetration | 2.82e-6 m | 2.60e-6 m | 7.06e-7 m |
| column10 tail penetration | 2.9e-7 m | 4.5e-7 m | 3.2e-7 m |
| column10 final spin | 1.04e-2 rad/s | 2.77e-2 | 2.09e-2 |
| wall10 steps/s | 342 | 343 | 345 |
| timing N = 100 | 0.319 s/step | 0.316 | 0.315 |
| timing N = 500 | 37.0 s/step | 61.7 | 61.5 |

Reading:

- **Penetration.** The cap change removed the pile10 penetration (2.56e-6 → 2e-12 m). The 128-sweep setting brought the
  column10 peak under the 1e-6 m limit (7.06e-7 m). At 64 sweeps the same scene peaked at 2.6e-6 m (§5.2). Neither change
  was tuned on this scene; both were measured for the reasons in §1 and §5.
- **Cost.** The sweep count costs time only where contacts exist: pile10 and column10 slow by 1.8× and 1.5×. The
  free-falling wall10 and the N = 100 timing are unchanged. The N = 500 cost comes from the cap, not the sweeps: it rose
  from 37.0 to about 61.6 s per step at 64 and at 128 sweeps alike (§5.3). The start state of that scene is not checked
  for overlap.
- **Not settled.** pile10 has zero penetration and a final speed of 0.57 m/s, but a spin of 8.5 rad/s after 3 s. It is not
  at rest. The energy ratio (0.115) shows dissipation, but the state is not a settled pile. This is an open item.
- **wall10 final speed 11.008 m/s: explained, not a defect.** The fastest box at the end has velocity (−5.0, 0, −9.23) m/s:
  a reflection of 10 m/s at e = 0.5 (−5 m/s in x) plus free fall under gravity for about 0.94 s (9.23 m/s in z). The
  speed is √(5² + 9.80665²) = 11.0077 m/s, at t = 1.0 s (`BOX_BOX_RUNS.txt` §G). The scene has no floor, so the
  energy ratio mixes falling and collision losses and is not a restitution check.
- **Energy and momenta.** Energy is not conserved, by design: the contacts are dissipative (friction, e < 1). Linear and
  angular momentum of the internal contacts are checked in §2 and in the physics tests, not in this stress table.
- **pile100 (100 boxes) runs as an impact test.** 2500 steps (0.25 s) with zero penetration at every step, no non-finite
  state, and max speed 3.39 m/s. Its first version (zero initial velocities, the grid released at rest) was free fall: the
  boxes fall together, no contact impulse is applied, and the spin is exactly zero. That version tested only contact
  detection and is recorded in `BOX_BOX_RUNS.txt` §I.1, not as an impact result. The scene now has random initial
  velocities.
- **N = 500 is not run as a full simulation.** Each step takes about 62 s, so a 1 s run (10,000 steps) would take about
  7 days. The N = 500 figure is a per-step timing only. A 500-box run needs a broad phase first (§7).
- **Cost depends on the projection passes**, not only on the pair count: pile100 with impacts runs at 1.8 steps/s and the
  free-fall version at 3.1 steps/s with the same pair count. This is consistent with more projection passes in the impact
  run. Not measured per pass.

---

## 5. Projection: the cap, the spec order, and a stall (open)

### 5.1 Defect found by the Blender test and fixed: the cap

The Blender smoke test (P7) placed two boxes on a box in free fall. The engine refused the run:
`penetration 1.299e-06 m exceeds 1e-06 m at step 289`. The refusal is explicit, not silent, but the scene is legitimate.
Measured with the same timestep (1/1008 s, the 24 fps bake) and the same three boxes:

| PROJECTION_PASSES | max penetration after the run |
|---|---|
| 10 | 1.30e-6 m (refused) |
| 12 | 1.87e-6 m (refused) |
| 16 | 5.9e-7 m |
| 20 | 1.85e-7 m |
| 24 | 5.8e-8 m |
| 32 | 5.9e-9 m |
| 40 | 5.9e-10 m (adopted) |

The cap was binding: at 10 passes the projection had not converged. The cap was raised to 40. Regression test:
`test_three_box_impact_at_the_bake_timestep_converges_under_the_penetration_limit` (fails at 10 passes, passes at 40,
checked). The cap binds only in steps that have not converged. Sphere regression tests and the CLI sphere run are
unchanged (CLI physics fields identical to the pre-Phase-7 baseline).

Effects on the other scenes (cap 40 against cap 10, both at 64 sweeps): pile10 penetration 2.6e-6 → 2.0e-12 m (§4);
stack4 penetration 1.3e-6 → 1.1e-8 m (§1); and the N = 500 timing scene 1.7× slower (§5.3).

### 5.2 Finding: the projection depends on contact order and can stall near 1e-6 m (open)

The column10 scene (10 boxes stacked with 5 mm initial gaps, dt 1e-4) peaks at 2.6e-6 m with cap 40 at 64 sweeps. Its peak
is at step 322, during the impact as the upper boxes close their gaps. At 128 sweeps the full run peaks at 7.06e-7 m (§4):
the sweep count resolved this scene. The ordering experiment below was run at 64 sweeps, and its ordering sensitivity
has not been re-measured at 128. A 400-step probe (`BOX_BOX_RUNS.txt` §F) isolates
the cause:

| configuration (first 400 steps) | worst penetration after projection |
|---|---|
| contacts listed upper-first (as the scene is written), cap 40 | 2.60e-6 m at step 322 |
| contacts listed floor-first, cap 40 | 7.24e-7 m at step 322 |
| contacts listed upper-first, cap 80 | 9.60e-7 m at step 322 |

- The projection is a Gauss–Seidel iteration over listed pairs, and the result depends on the order in which pairs are
  listed. The column10 order was my own arbitrary choice. This is a real sensitivity of the solver, not a property of the
  scene.
- Raising the cap alone does not converge it: at cap 80 the residual is still 9.6e-7 m, close to a stall rather than a
  geometric decay. This is the reason the cap cannot be the complete fix.
- The mechanism (interpretation, consistent with the data): a pair's push splits by inverse mass, so it moves the lower
  body of that pair into the pair below it by half the depth. Upward-listed pairs keep disturbing the pairs below.
- A fix would change the projection (for example bottom-up ordering, or one-sided pushes). Both change the sphere paths
  too, so they need the sphere regression tests as evidence. Not implemented in Phase 7.
- Consequence: a 10-box tower impact at the bake timestep can exceed the 1e-6 m check and be refused. The refusal is
  explicit. This is a limitation and an open defect (§7), not a silent failure.

### 5.3 Cost of the cap

The N = 500 timing scene (random boxes, all pairs listed, 2 steps) was measured with the same code except the cap:
37.9 s per step at cap 10 and 64.4 s at cap 40 (`BOX_BOX_RUNS.txt` §H). The start state of that scene is not checked for
overlap. The extra cost is consistent with more projection passes there; this is a hypothesis, not measured per pass.
The cost is recorded, not hidden.

## 6. Blender (P7)

`tools/blender_smoke.py` under `bpy` 5.0.1, headless: **47 PASS, 0 FAIL, exit 0** (34 earlier checks unchanged, 13 new
box–box checks):

- rotated box, 30° about z: bakes; rests on its face at z = 0.100008 m; quaternion norm 1.000000000.
- two boxes of different size (0.4 m on the plane, 0.2 m on top): both keyed; z = 0.200000 and 0.500000 m.
- three-box stack (two boxes dropped onto a box): z = 0.100003, 0.300004, 0.500015 m (tolerance 1e-3).
- dynamic box on a static box: static box not keyed and does not move; dynamic box at z = 0.500009 m.

The bpy-free core (`scene_build.bake_scene`) is covered by `tests/test_blender_colliders.py` and
`tests/test_blender_scene_build.py`. Those tests import the core without Blender.

---

---

## 7. Open items (status at the end of Phase 7)

1. **pile10 is not settled.** After 3 s it has spin 8.5 rad/s and speed 0.57 m/s (§4). Its penetration is zero. Not
   investigated further in Phase 7.
2. **Four-box stack with friction: spin ≈ 2e-2 rad/s, not sweep-limited.** Still 2.0e-2 rad/s at 256 sweeps (§1.2).
   The cause is not isolated. The friction anchor, per-point clamping and the corner rows are candidates
   (`BOX_BOX_RESEARCH.md` §6), not tested here.
3. **Projection order sensitivity and stall.** Measured at 64 sweeps: a 10-box tower impact can leave 2.6e-6 m (cap 40),
   above the bake check; listing the floor pair first gives 7.2e-7 m, and cap 80 gives 9.6e-7 m (§5.2). At 128 sweeps the
   column10 run peaks at 7.06e-7 m. The sensitivity is not re-measured at 128. A fix changes the projection and needs
   sphere regression evidence.
4. **Sweep cost.** 128 sweeps are needed for the tested stacks, and the box steps cost more (§4). The cost is recorded, not
   reduced.
5. **No broad phase.** Every listed pair is tested every step. Measured cost: 0.32 s per step at N = 100 and 61.5 s per
   step at N = 500 (§4). The cost is not split by phase.
6. **No continuous collision detection.** A box can pass through a thinner box within one step at high speed. Not measured.
7. **Angular momentum residual at start-of-step centres is first order in dt** (§2). At the predicted positions it is
   small (1.3e-13 for the oblique case at dt 1e-4, at most 5e-17 in the other scenes), with a dt-dependence not explained.
   No correction is claimed.
8. **Box–mesh contacts are not implemented.** Refused with `unsupported`.
9. **Warm starting** was measured only at 8–32 sweeps with the cap-10 code, with mixed results. Not evaluated at the
   shipped count.
10. **Energy in the stress tool is kinetic plus gravitational potential.** For wall10 (no floor) the end/start ratio mixes
   falling and collision losses, so it is not a restitution check.
11. **The `bpy` licence** is unresolved (`THIRD_PARTY_LICENSES.md`). The wheel says GPL-3.0; a prior note cites GPL-2.0-or-later
    source headers, not re-checked here.
