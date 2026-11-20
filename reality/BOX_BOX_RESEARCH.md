# Box–box collision: audit, baseline, research and design

Status: **research and design, before any code change** (Phase 7, P0–P1). Mathematics: `BOX_BOX_MATHEMATICS.md`. Sources and
their verification status: `BOX_BOX_REFERENCES.md`. Nothing in this document is a claim about the implementation; the
implementation and its measured results will be recorded in `COLLISION_GEOMETRY.md`, `NUMERICAL_METHODS.md` and
`LIMITATIONS.md` once they exist.

---

## 1. Phase 0 audit (read-only, before changes)

### 1.1 Repository state

| Item | Result |
|---|---|
| Branch | `arena/7257ca22-qoute-editor` (fixed for this session) |
| Base commit | `2fcc86d` (main). `git merge-base --is-ancestor 2fcc86d HEAD`: **ancestor, verified** |
| HEAD | `a5595bf`, equal to `origin/arena/7257ca22-qoute-editor` |
| Working tree | clean at start of audit |

### 1.2 Where box–box is currently refused

Box–box is refused by validation, not silently ignored. The refusal sites are:

- `src/reality/control/collision_scene.py`: `_UNSUPPORTED[("box", "box")]` (line ~57). The validator rejects a body–body
  contact whose kinds are `(box, box)` with `unsupported pair box-box`.
- `src/reality/collision/solver.py`: `PAIR_KINDS` lists `sphere_sphere, sphere_box, sphere_plane, box_plane, sphere_mesh`;
  there is no `box_box` kind, so `step` would raise `unsupported pair kind` if one were passed.
- `blender_addon/reality_physics/scene_build.py` and `__init__.py`: documentation says a bake needing box–box is refused. The
  refusal is the kernel's, reached through `bake_scene` → validation.
- Tests that pin the refusal (these change intentionally in Phase 7, and must be replaced by positive tests, not deleted):
  - `tests/test_collision_scene.py:127–131` (`test_box_box_is_refused_explicitly_not_ignored`)
  - `tests/test_collision_scene.py:179–182` (v3 path check that uses a box–box pair)
  - `tests/test_blender_colliders.py:113–116` (`test_box_on_box_is_refused_with_the_kernel_reason`)
- Documentation that says box–box is not implemented: `COLLISION_GEOMETRY.md` (lines 3, 87, 185, 221, 250),
  `LIMITATIONS.md` (lines 27, 88, 100), `SCENE_SCHEMA.md` (line 94), `AI_CAPABILITY_MATRIX.md` (lines 16, 18),
  `CHANGELOG.md` (lines 15, 20), `blender_addon/reality_physics/__init__.py` (line 22), `scene_build.py` (line 17).

### 1.3 Existing narrow phase and solver (what box–box must fit into)

- **Conventions** (`collision/narrow.py`): `Contact(normal, point, depth, feature)`. The normal points from the first shape
  to the second. `depth > 0` is penetration. Contacts with `depth > -TOUCH_TOL` are reported (`TOUCH_TOL = 1e-9 m`).
  `REL_EPS = 1e-12` is the relative zero for lengths and areas.
- **Box–plane** (`box_corners_plane`): one contact per corner at or below the plane, `feature = "vertex"`. This is the only
  existing box-to-flat contact. It is a corner model; it has no face manifold.
- **Sphere–box** (`sphere_box`): closest point on the box, or the least-slack face when the centre is inside. Normal is
  box → sphere.
- **Solver** (`collision/solver.py`): predict velocities and positions (`x_pred = x + v h`), detect at `x_pred` with the
  current orientation, sequential impulses with Coulomb friction and restitution over all listed contact points
  (`_effect` uses `I⁻¹ = R diag(I_body⁻¹) Rᵀ`, so angular response is included), move, project penetration, then rotate.
  - **Body–body pairs are already generic.** `_con`, `_apply`, `_effect`, `_rel_velocity` and the projection use
    `spec.a` and `spec.b` with a static check. A new pair kind only needs a `_detect` branch. The solver does not need to be
    rewritten.
  - **Projection** pushes out only the deepest point of each pair per pass, two passes. For a multi-point box manifold this
    still removes all penetration along the normal, because a translation by the deepest depth clears every shallower point.
    It is measured, not assumed, in Phase 7 tests.
  - **Detection uses the current orientation, not a predicted one.** Positions are predicted but rotation is applied only at
    step 6. A fast-spinning box can therefore be detected at a slightly stale orientation. Existing sphere–box and box–plane
    have the same limit. This is recorded as a limitation and measured in the stress tests, not changed for box–box alone.
- **Inertia** (`Body.__post_init__`): solid box, `I_x = m (h_y² + h_z²)/3`. Centre of mass is the box centre. This matches
  the mathematics and needs no change.
- **Static bodies**: `Body.static` sets `inv_mass = 0` and zero velocity and inertia, and they are never moved. A static
  box can therefore be one side of a box–box pair with no change to the solver.

### 1.4 Other findings from the audit

- `PENETRATION_TOLERANCE_M = 1e-6` (`simulate.py:27`) is the threshold for the `invalid_state` penetration check. Box–box
  must keep penetration within it, and this is tested.
- `Contact.point` is documented as "a point on the surface of the first shape". The solver uses the same point as the
  lever arm for both bodies. Box–box needs a symmetric point, so it will use the **midpoint of the overlap**. This is
  a documented convention for box–box contacts and is stated in `Contact`'s docstring when the code lands. Existing
  contacts are not changed.
- The `invalid_state` check and the solver's `max_penetration` are computed over all listed pairs, so box–box is covered
  automatically once it is a listed pair kind.

### 1.5 Baseline (measured before any change, 2026-11-20 UTC)

| Check | Command | Result |
|---|---|---|
| Full test suite | `python -m pytest tests -q` (Python 3.11.2, pytest 9.2.0 in `/tmp/testvenv`, outside the repo) | **508 passed** in 93.2 s, exit 0 |
| Static analysis | `python -m pyflakes` (pyflakes 4.1.0) on `collision/`, `control/collision_scene.py`, `rigidbody.py`, `multibody.py`, `contact.py` | **clean**, exit 0 |
| Validation | `tools/run_validation.py` | **79 cases, 0 failing**; regenerates the tracked `VALIDATION_REPORT.md`, whose only change was the timestamp, so it was restored with `git checkout` |
| Blender smoke | `LD_LIBRARY_PATH=/tmp/x11stubs /tmp/bpy-venv/bin/python tools/blender_smoke.py` (bpy 5.0.1) | **34 PASS, 0 FAIL**, `RESULT: ALL PASSED`, exit 0 |
| CLI | `scene new` → `add-sphere` → `add-plane` → `set-contact` → `simulate run --duration 3` → `inspect summary` | exit 0; sphere on plane, rolling onset **0.5827 s**, matching the recorded value |

Note on the environment: `/usr/bin/python` has no pytest or pyflakes. The tools were installed into `/tmp/testvenv`, outside the
workspace. The kernel itself has no runtime dependencies.

The test and oracle tooling for Phase 7 installs `mujoco` 4.0.1 from PyPI into the same test venv. It is a development-only
cross-check, not a dependency of the kernel or its tests (see §4.4).

### 1.6 Open items carried over from Phase 6 (not part of Phase 7)

These were listed in the Phase 6 report and remain unresolved. They are not changed by this milestone.
Add-on `bl_info` 0.2.0 versus CHANGELOG 0.3.0; `_operator_refused` ends in `and False`; `NUMERICAL_METHODS.md` not checked for Phase 6;
`schema_version` 2 for v2-with-meshes; session date versus commit date; bpy licence discrepancy (GPL-3.0 metadata vs GPL-2.0-or-later
headers); port 5180 "Engine viewer" still running (pid 2031); Ericson section numbers unverified; `SCENE_SCHEMA.md` limit wording;
COLLISION_GEOMETRY §6 verified only for three v1 preview indices.

---

## 2. Research findings (verified sources only; see `BOX_BOX_REFERENCES.md`)

### 2.1 Separating axis test for two oriented boxes

- Eberly (Geometric Tools, *Dynamic Collision Detection using Oriented Bounding Boxes*) states that two OBBs have **15
  potential separating axes**: 3 face normals of the first box, 3 of the second, and 9 generated by an edge of the first crossed
  with an edge of the second. I read this statement from a search excerpt of the PDF; the full PDF was not retrievable from the
  sandbox, so the statement is cited as an excerpt-verified claim. It is consistent with the source code of MuJoCo and Bullet
  below, which both use exactly these 15 candidates.
- MuJoCo (`src/engine/engine_collision_box.c`, `mjraw_BoxBox`, stage 1) tests the same 15 axes. It computes the support
  radius of each box along each axis from `|R_ij|` entries, and rejects the pair as soon as one axis separates it. I read this
  code and implemented nothing from it.
- Bullet (`btBoxBoxDetector.cpp`, `dBoxBox2`, derived from ODE) tests the same 15 axes with the same support formulas.
- **Consequence for the design:** the 15 axes are the candidate set. Each candidate is a unit vector, so a separation test
  along any candidate is a valid test. Degenerate candidates (parallel edges, cross product near zero) are skipped, and this
  is justified in the mathematics document.

### 2.2 Contact manifold for face–face contact: reference face, incident face, clipping

- Gregorius (Valve, GDC 2015, *Robust Contact Creation for Physics Simulations*; the slide text extracted by the fetch tool, 2 chunks, which ends before the talk's "Contact Optimizations" section) states the
  one-shot approach: detect the touching features with SAT, then **clip one feature against the side planes of the other**,
  so that all contact points of the manifold come from the clipping. The contact normal and penetration come from the
  touching features. A manifold is "stable" when the centre of mass projects inside it. The slides define a contact manifold
  as points that share a common normal, and assume a maximum of four points per manifold as an optimisation.
- Box2D v3 (`src/manifold.c`, MIT, read): for polygons, `b2FindMaxSeparation` is applied to both polygons' edge normals; the
  winning polygon is the reference; the incident edge is the edge with the smallest dot product against the reference normal;
  `b2ClipPolygons` clips the incident edge against the two side planes of the reference edge in 2D; the points are kept at
  the midpoint between the surfaces. This is the 2D analogue of the 3D method here. It is a template for the algorithm, not
  reusable code (different dimension, and it is MIT licensed, so attribution would be required if any code were copied).
- MuJoCo (read) uses the same structure in 3D: the face of the other box least aligned with the reference normal is clipped
  with Sutherland–Hodgman against the four side planes of the reference face. The clip keeps **every** vertex in the margin
  band (no reduction). The source comments give the reason: on plates with a wide patch, reducing to four points changed
  residual motion at rest by two to three orders of magnitude, because the support polygon shrinks and its subset changes
  between steps.
- Sutherland–Hodgman polygon clipping: Sutherland & Hodgman, *Reentrant Polygon Clipping*, Communications of the ACM 17(1),
  1974, pp. 32–42 (bibliographic record verified from the DBLP/SIGMOD listing; the paper text was not read).

### 2.3 Reduction of the manifold

Three practices exist in the sources read:

| Source | Practice |
|---|---|
| Gregorius (2015) | Assumes a maximum of four points per manifold, "as an optimisation", and says the reduction is shown "at the end" of the talk. The extracted text does not include that section, so the reduction method is **not verified** |
| MuJoCo (read) | Keep all clipped vertices in the band; no reduction |
| Bullet / ODE (read) | Cull to a maximum count with `cullPoints2`, a centroid-and-angle selection seeded at the deepest point. This is lossy by construction |

**Decision for this milestone:** no reduction. Clipping a quadrilateral against four half-planes adds at most one vertex per
half-plane to a convex polygon, so a face–face manifold has **at most 8 points**, by a counting argument proved in the
mathematics document. A bounded count of ≤ 8 is therefore available without any lossy selection. This satisfies "reduction
without losing accuracy" in the strongest sense: nothing is discarded. If measurements later show the 8-point count is too
costly in a stack, that is a measured decision to be made then, not now.

### 2.4 Edge–edge contact

- When the winning axis is an edge–edge axis, the contact is the closest pair of points between the two supporting edges.
  MuJoCo uses this (read): the contact point is the midpoint of the closest pair, and the depth is measured along the
  separating axis. Both are derived independently in the mathematics document.
- For the closest pair of two segments, the mathematics document gives a closed form and a clamping procedure, and argues
  for the clamping choice: minimising a convex quadratic over a rectangle is solved by checking the interior critical point
  and each of the four edges. This is exact, not sampled.
- Parallel or nearly parallel edges have no well-defined closest pair. They are excluded at the axis stage (§3.3), where the
  face axes take over.

### 2.5 Penetration, normal sign and depth

- Penetration depth for convex polyhedra is the minimum overlap over the candidate axes (the minimum translation distance;
  derived in the mathematics document from the Minkowski difference). The sign convention matches `Contact`: the normal is
  from A to B, `depth > 0` is penetration.
- The normal sign is fixed by the centre offset: `n = sgn(d·L) L`, with `d = c_B − c_A`. When `d·L` is zero (for example two
  coincident boxes), the sign is taken by the existing deterministic rule `_canonical_sign`, which is winding independent.

### 2.6 Tolerances, degenerate axes and precision

The sources disagree on the constants and none of them gives a universal value. Each constant used here is therefore stated with a derivation,
and each has a test that exercises the boundary it defines. The chosen values are listed in §3.3. None is copied from a source.

- MuJoCo's constants (`mjBOXBOX_SEPEPS`, `PAREPS`, `EDGEBIAS`, the 5 % face-substitution rule) are specific to its single-precision
  and double-precision builds and to its margin model. They are **not** adopted as values. Their **reasoning** is adopted where
  it is verified in the source.
- Bullet's ODE-derived `fudge_factor = 1.05` is a relative preference in the choice of axis: a candidate replaces the current
  best only if `s2 * 1.05 > s` (`btBoxBoxDetector.cpp`, the macro around line 363). It is a bias on the choice, not a change to
  any separation value. It is not adopted as a constant. A relative tie tolerance with a stated derivation is used instead
  (§3.3, `FACE_TIE`), because a multiplicative factor on a signed separation behaves differently for negative and positive
  values.

### 2.7 Licensing and reuse

| Source | Licence (verified) | Use here |
|---|---|---|
| MuJoCo | Apache-2.0 (`LICENSE` in the source archive read) | Algorithm understood; **no code copied**; pip package used only as a development oracle |
| Box2D | MIT (`LICENSE` read; copyright 2022 Erin Catto) | Algorithm understood; 2D only; **no code copied** |
| Bullet | zlib (`LICENSE.txt` read). `btBoxBoxDetector.cpp` header: derived from ODE, Copyright 2001–2002 Russell L. Smith, redistributed under zlib with permission | Algorithm understood; **no code copied** |
| Gregorius slides | Not a software licence; cited as a publication | Principle only |
| Eberly PDF | Not read in full; excerpt only | Statement of 15 axes only |

The implementation will be written from the mathematics document. No line of the sources above will be copied.

### 2.8 Bullet's detector and ODE's original licence

Only the Bullet copy of the ODE-derived detector was read. The original ODE licence was **not** verified and is not cited.

---

## 3. Design

### 3.1 Scope of the change (minimal, no architecture rewrite)

1. **New module** `src/reality/collision/box_box.py` (pure functions, no solver state): `box_box_sat` (the 15-axis test and the
   minimum-depth axis), and `box_box_contacts` (face manifold or edge contact, oriented A → B, midpoint point, feature
   `face` or `edge`).
2. **Solver** (`collision/solver.py`): add `"box_box"` to `PAIR_KINDS` and one branch in `_detect` that calls `box_box_contacts`.
   Nothing else in the solver changes.
3. **Validation** (`control/collision_scene.py`): remove `(box, box)` from `_UNSUPPORTED`, and add the `box_box` pair spec
   in the spec builder. Box–mesh stays refused.
4. **Blender add-on**: the kernel accepts box–box, so the bake path needs no logic change. Its refusal text and tests change
   with the kernel, and are updated (positive test replaces the refusal test). The add-on version is out of scope here.
5. **Docs and tests** as listed in the brief.

### 3.2 Things deliberately **not** done

- No replacement of the solver, no new integrator, no warm starting (existing limit), no continuous collision detection.
- No box–mesh pairs.
- No change to sphere, plane, mesh or box–plane behaviour. Regression tests keep them pinned.
- No Blender rigid-body solver is used.

### 3.3 Constants (each has a derivation and a test)

| Name | Value | Derivation | Tested by |
|---|---|---|---|
| `TOUCH_TOL` | 1e-9 m (existing) | The reporting threshold for all contacts in the kernel. Reused, not redefined | sphere/box regression |
| `REL_EPS` | 1e-12 (existing) | Relative zero for lengths and areas | degenerate-axis tests |
| `PAR_SIN` | `√ε ≈ 1.49e-8` | Skip an edge axis when `‖A_i × B_j‖ < PAR_SIN`. Two errors trade off: the rounding error of the normalised axis, about `2ε/sinθ`, grows as the axis gets ill-conditioned, and the error from skipping a thin sliver facet, about `c·sinθ·S`, grows with `sinθ`. They balance at `sinθ ≈ √(2ε/c)`, so `√ε` is chosen. The resulting depth error is of order `√ε·S`, which is **above** `TOUCH_TOL` near `S = 1 m`. This is a stated limit, not a hidden one; it appears only for near-parallel edges where the skipped facet would be the minimum | near-parallel tests at `sinθ` 1e-2, 1e-4, 1e-6, 1e-8, 0 against the dense-direction search and the oracle |
| `FACE_TIE` | 1e-6 × S | An edge axis replaces a face axis only if its separation is larger by more than `FACE_TIE·S`. Floating-point noise in a separation is about `1e-15 S`, so 1e-6 S is nine orders above noise and cannot flip between codes from rounding. It changes depth by at most `1e-6 S` (1 µm on a 1 m box) | stacking-tie test; edge-vs-face tie test |
| `DEDUP` | `REL_EPS × S` | Clipped vertices closer than this are the same point | corner-touch and tiny-box tests |

`S` is `max(hA) + max(hB)` for the pair; it is the natural length scale for the tolerances.

### 3.4 Honest limits to be stated, not hidden

- Absolute `TOUCH_TOL` (1e-9 m) is shared with the rest of the kernel. For boxes of order 1 µm this is a 1e-3 relative tolerance. The
  stress and scale tests measure where it stops being meaningful; the result is reported, not assumed.
- Detection uses the current orientation (§1.3). For fast spinning boxes this is an approximation. It is measured.
- Face manifold points that lie outside the reference footprint are excluded by clipping. This is the correct face–face
  result. An edge contact that lies outside the footprint is found only by the edge axes, as in all SAT methods.
- The projection of the solver still pushes out the deepest point only. This is correct for translation along the normal
  (§1.3), but it can overshoot a shallower point's correct position. Measured in the tests.

- **Free rotation of asymmetric bodies (fixed in this phase).** The solver's rotate step used a constant body-frame
  angular velocity, which drops the gyroscopic term `w x (I w)`. For a box with half-extents (0.3, 0.2, 0.1), `w_body` =
  (2, -1, 3) over 0.2 s, the solver stayed at (2, -1, 3) while Euler's equations give (2.179, 0.036, 3.079): an error
  of 1.04 rad/s that did not shrink with dt. Step 5 now advances `w_body` by two RK4 half-steps of Euler's equations and
  rotates by the midpoint rate. Measured: `w_body` agrees with `rigidbody.integrate` (h = 1e-5) to 3e-13 at dt 1e-4, and
  world angular momentum drifts 4.8e-10, 1.2e-10, 3.0e-11 for dt 1e-4, 5e-5, 2.5e-5 (order dt²). Isotropic bodies skip
  the correction, so the sphere and cube paths are unchanged. The `rigidbody.exact_free_step` helper has the same
  constant-rate form. It is not used by the collision solver and is outside this phase.
- **Contact impulses and the predicted configuration.** The solver takes lever arms from `x_pred = x + h v` and applies
  impulses there. At `x_pred`, both linear and angular momentum are conserved to rounding in each contact step (angular
  residual 1.8e-13 at dt 1e-4, 2e-14 at 5e-5). Measured at the start-of-step centres, the residual is first order:
  1.26e-5 and 6.3e-6 per contact step (ratio 2.00). It comes from the semi-implicit position update, which moves the
  centres by `h dv` after the impulse. This is a stated first-order error, not a bug, and it is in the limitations.
- **Update (Phase 7, final).** The value below is superseded: `BOX_MANIFOLD_ITERATIONS` = 128. Stacks need more than the
  landings tested here (`BOX_BOX_STUDY.md` §1). The text below is kept as the record of the first measurement.
- **Gauss–Seidel sweeps for box manifolds (first measurement).** `BOX_MANIFOLD_ITERATIONS` = 64. Measured landing and rest spin (dt 2e-4, 30°
  about z): 8 sweeps leave ~0.2 rad/s; 16 leave 3e-2 rad/s at worst; 32 leave 2e-7 rad/s at worst but lose a stack contact
  on 38 of 500 resting steps (the 1 nm reporting threshold flickers); 64 reach 1e-16 and keep every contact. Cost: about
  2.1 ms per box-plane step at 64 sweeps, 0.9 ms at 16 (measured). 64 was kept at that stage.

---

## 4. Verification plan (what will be measured, and how)

### 4.1 Oracles, in order of independence

1. **Analytical** (hand-derivable values): axis-aligned overlap depth `hA + hB − |d|`; a box rotated by θ about an axis, overlap
   with a 30° example worked out in the mathematics document (depth 0.283 for the case in §4.4 below).
2. **Dense direction search**: the minimum overlap over a dense set of sampled unit axes is an upper bound on the true
   minimum translation; the SAT minimum must be ≤ it, and within the sampling resolution. It uses no SAT code.
3. **MuJoCo 4.0.1** (pip, development-only): compare contact count, normal, depth and midpoint for the same geometry.
   In the probe in §4.4, MuJoCo's normal points from geom 1 to geom 2 and `dist` is negative when penetrating. This is what
   was observed, not a quoted specification; the comparison maps it onto `Contact` (normal A → B, depth positive).
4. **Physical invariants** for the response: momentum, energy (with restitution), rest and sliding behaviour.

### 4.2 Test groups (P5)

Geometry, physics, regression, Blender, stress and CLI/MCP tests, as the brief lists. The test names and expected values are
written before the implementation is run, and any test that fails is reported, not weakened.

### 4.3 Stress (P6)

Measured, not claimed. Runtime, memory, collision and contact counts, iterations, numerical error, energy drift, maximum
penetration, stability and failures, at 10, 100 and 500 boxes, and dt, mass-ratio and speed sweeps. The results will be
recorded with the commands that produced them.

### 4.4 Oracle check run during this research (not yet a test)

One pair was run through MuJoCo 4.0.1 (`mujoco.mj_forward`) to check that the oracle works before it is relied on:

- Box A: centre (0,0,0), half extents (0.5, 0.5, 0.5), identity orientation.
- Box B: centre (0.9, 0.1, 0.2), half extents (0.5, 0.5, 0.5), rotated 30° about z.
- Result: **2 contacts**, normal (1, 0, 0), `dist = −0.28301` (penetration 0.28301), contact points at
  `(0.3585, 0.283, −0.3)` and `(0.3585, 0.283, 0.5)`.
- Hand check: the x-support radius of B is `0.5(cos 30° + sin 30°) = 0.6830`, its minimum x is `0.9 − 0.6830 = 0.2170`, so
  the x-overlap with A's `x ≤ 0.5` is `0.5 − 0.2170 = 0.2830`. The contact x is the midpoint `(0.5 + 0.2170)/2 = 0.3585`. Both
  match. The z-positions `−0.3` and `0.5` are the corners of the clipped incident face within the reference footprint, as the
  clipping in §2.2 predicts.

This is the first independent value for the Phase 7 tests. It is not a test yet.

---

## 5. Open questions (to be answered by measurement, not assumed)

1. Does the existing 8-iteration sequential-impulse solver without warm starting hold a 10-box face stack at rest? The sphere
   stacks already drift; the answer is a measurement in P6.
2. Does the face-tie constant (§3.3) behave as stated on a stack of identical plates, where the face and edge codes are
   nearly tied?
3. What is the actual energy drift and penetration for a 500-box run at each dt in the sweep?
4. Does stale orientation at detection change results for high angular velocity at the chosen dt?

---

## 6. Status

- Phase 0 audit: done (§1), with baseline recorded.
- Phase 1 research: done for the sources listed in `BOX_BOX_REFERENCES.md`. Anything not verified is labelled there.
- Phase 2–4 (kernel, solver wiring, schema): done. Commits `90ae28d`, `9e30550`.
- Phase 5 (edge cases and numerics): done for the listed cases. `tests/test_collision_box_box_edge_cases.py` (8).
- Phase 6 (stress, 10 / 100 / 500 boxes): see `BOX_BOX_STUDY.md` §4 and the stress outputs. 500 boxes exceed a practical
  per-step budget without a broad phase (37 s per step), so the largest reproducible configuration is reported.
- Phase 7 (Blender): 13 new checks, 47 in total, pass under bpy 5.0.1 (`tools/blender_smoke.py`).
- Phase 8–10 (regression workflow, documentation, delivery): see `BOX_BOX_STUDY.md` and the final report.
- Open: the stack spin (§1.2 of `BOX_BOX_STUDY.md`), the two-box stack sweep count (§1), box-mesh, and the broad phase.
  Records of the status of each item are in `BOX_BOX_STUDY.md` §7.
