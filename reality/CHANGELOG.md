# CHANGELOG - PROJECT REALITY

All notable changes to `reality/`. The format follows Keep a Changelog. Blender upstream changes are listed
separately in `ARCHITECTURE.md` §5 (none so far).

## [Unreleased]

### Added (Phase 7: box-box contacts)
- Box-box contacts in the kernel (`src/reality/collision/box_box.py`): 15-axis separating-axis test (two face sets and
  nine edge pairs), contact manifolds by Sutherland–Hodgman clipping of the incident face, edge–edge contacts by closest
  points, and a canonical sign for the normal. Rotated boxes are supported. Up to 8 contact points per pair (not reduced).
  Schema v3 accepts box-box; box-mesh is still refused with `unsupported`.
- Solver wiring (`collision/solver.py`): box-box pairs in `PairSpec`, friction and restitution at each contact point, and
  at least 128 sweeps for steps containing a box pair (`BOX_MANIFOLD_ITERATIONS`, measured; 64 was too few for the
  two-box friction stack and the frictionless four-box stack, `BOX_BOX_STUDY.md` §1).
- Tests: `tests/test_collision_box_box.py` (14, geometry against a dense 20,000-direction reference),
  `tests/test_collision_box_box_physics.py` (14, free flight, rest, stacks, impacts), and
  `tests/test_collision_box_box_edge_cases.py` (8, nearly parallel, grazing, mass ratio 1000:1, falling, 20 m/s impact,
  quaternion over 20,000 steps, identical boxes, three-box impact at the bake step).
- Blender add-on: 13 new headless checks in `tools/blender_smoke.py` (rotated box, two sizes, three-box stack, dynamic on
  static). 47 checks in total, all passing under bpy 5.0.1.
- `tools/box_sweep_study.py`, `tools/angular_residual_study.py`, `tools/box_stress.py`: the measurement scripts behind
  `BOX_BOX_STUDY.md`.
- `BOX_BOX_STUDY.md`, `BOX_BOX_MATHEMATICS.md`, `BOX_BOX_RESEARCH.md`, `BOX_BOX_REFERENCES.md`: research, derivations,
  measured results and limits.

### Fixed (Phase 7)
- Free rotation of a box dropped the gyroscopic term. A box with ω_body (2, −1, 3) over 0.2 s differed from the
  Euler-equation reference by 1.04 rad/s. Now 3e-13 rad/s (`_free_rotation_rates`).
- Projection cap: `PROJECTION_PASSES` was 10. A three-box impact at the 24 fps bake timestep left 1.3e-6 m of
  penetration and was refused by the 1e-6 m check. The cap is now 40 (measured: 16 passes → 5.9e-7 m, 40 → 5.9e-10 m).
  Passes repeat only while a pair is deeper than `PROJECTION_TOL`, so converged steps are unchanged. Sphere regression
  tests and the CLI sphere run are unchanged.
- Solver docstring: the step order (rotate before project) and the pass description now match the code.
- Sweep count: `BOX_MANIFOLD_ITERATIONS` raised from 64 to 128. At 64 sweeps the two-box friction stack still spins at
  5.3e-3 rad/s (1.0e-8 at 128), and a frictionless four-box stack at 4.9e-2 rad/s (1.6e-11 at 128). Cost: the pile10
  scene runs at 33 steps/s instead of 59 at 64 sweeps (`BOX_BOX_STUDY.md` §1, §4).

### Changed (Phase 7)
- `rigidbody.quat_norm` is the quaternion norm. `rigidbody.norm` and `rigidbody.dot` still sum three components only; do
  not use them on quaternions. They were not changed in this phase; their other callers were not audited.

### Known limits (Phase 7; measured, see `BOX_BOX_STUDY.md` §7 and `LIMITATIONS.md` §5b)
- Frictionless four-box stack: its spin decays with sweeps (4.9e-2 rad/s at 64, 1.6e-11 at 128, 5e-18 at 256). A
  four-box stack WITH friction still spins at about 2e-2 rad/s at 256 sweeps. Open.
- Projection depends on the order in which contacts are listed, and can stall near 1e-6 m in a 10-box tower (measured at
  64 sweeps). Open. The 128-sweep setting brings the column10 peak under the limit (7.06e-7 m).
- pile10 (3 spheres, 7 random boxes) is not settled after 3 s (spin 8.5 rad/s). Open.
- No broad phase: N = 500 takes about 62 s per step (128 sweeps, cap 40); N = 100 takes 0.32 s per step. These were
  timed for a few steps, not simulated for long runs.
- Angular momentum of internal contacts is conserved at the predicted positions to rounding; at the start-of-step centres
  the residual is first order in dt.
- Warm starting was tried, gave mixed results and was not adopted.

### Added
- Schema v2 accepts a `meshes` list (approved change): static triangle meshes with sphere-mesh contacts, run on the
  collision solver and returning `reality.collision_run`. v2 without meshes is unchanged. The sphere solver refuses
  meshes explicitly. 11 tests in `tests/test_v2_meshes.py`.
- Blender add-on Phase 6 (version 0.3.0): "Mark as collider" with sphere, box (dynamic or static) and static triangle-mesh
  shapes; OBJ import through the add-on's operator; bake through the headless kernel (`scene_build.build_any`,
  `run_scene`), with static bodies and meshes not keyed. Refusals with reasons: mirrored or sheared objects, off-centre
  origins, unapplied modifiers, box-box and box-mesh. 15 Blender-free tests in `tests/test_blender_colliders.py`
  (includes the float32-to-double quaternion fix) and 18 new checks in `tools/blender_smoke.py` (32 in total under bpy 5.0.1).
- Collision geometry (`src/reality/collision/`, `COLLISION_GEOMETRY.md`): sphere-triangle (Voronoi closest point, edge,
  vertex and degenerate cases), sphere-box, box-plane (corner contacts), sphere-plane, sphere-sphere. Static triangle
  meshes with validation, a median-split BVH (checked against brute force), and per-cluster contact reduction.
  Tests: 32 narrow, 35 mesh, 19 solver, 46 scene, 13 result-path. Box-box and box-mesh are not implemented; scenes with them are refused with `unsupported`.
- General solver `collision/solver.py` (tensor inertia, box bodies, static bodies, Coulomb friction). It reproduces the
  existing sphere solver: a single sphere matches `contact.step_sphere` below 1e-11 and the two-sphere stack within 2.6e-10 m.
  `multibody.step_bodies` and `contact.step_sphere` are unchanged.
- Scene schema v3 (`control/collision_scene.py`, `SCENE_SCHEMA.md`): spheres, boxes, planes and static meshes, with
  explicit validation reasons, resource limits and cancellation. Result document `reality.collision_run` v1. Dispatched
  by `simulate.multibody` on `schema_version`. v1 and v2 are unchanged.
- Operations `collision.query` (contacts at the initial state) and `collision.validate_mesh` (mesh rules and BVH size).
  Operation count is now 25.
- `tools/collision_benchmark.py` and `COLLISION_BENCHMARK.json`: measured mesh build, memory, query and solver throughput.
- `optional quaternion` documented for schema v2 in `SCENE_SCHEMA.md`.
- Multi-body sequential-impulse solver (`src/reality/multibody.py`): sphere-sphere and sphere-plane contacts with
  restitution and a Coulomb friction cone. One sphere on one plane matches `contact.step_sphere` to 2e-12 over
  three scenarios, including spin (`tests/test_multibody.py`). Momentum is conserved to machine precision by pair impulses (0 measured in the head-on test).
  The head-on collision and Newton's cradle checks match the textbook results.
- Scene schema v2 (`src/reality/control/multibody_scene.py`, `SCENE_SCHEMA.md`): several bodies, planes and
  per-contact coefficients. Operation `simulate.multibody` (`reality.multibody_run` v1). v1 is unchanged. 22 tests in
  `tests/test_multibody_scene.py`. Optional per-body `quaternion` (default identity).
- Blender add-on `blender_addon/reality_physics/` (Blender 5.0.1 only, tested headless): marks spheres and planes,
  runs the v2 solver, and bakes location and rotation keyframes. OBJ import through Blender's own importer. Core in
  `scene_build.py` (no `bpy`; 14 tests). Headless smoke test `tools/blender_smoke.py` passes under `bpy` 5.0.1.
  The viewport panel is not checked on screen. See `blender_addon/README.md`.
- `engine/` (outside the Python package): a browser real-time runtime for `reality.scene` v1. TypeScript port of the
  sphere-contact stepper, verified against the Python kernel's recorded trajectories (position and velocity identical,
  spin within 7e-16), three.js viewer, transport and live contact controls. 24 engine tests and a Python sync test
  (`tests/test_engine_assets.py`). Not a finished game engine; see `engine/README.md` for the scope.
- `tools/export_engine_assets.py`: generates the engine's material table and reference trajectories from the kernel.
- Headless AI control layer (`src/reality/control/`): one operation registry (22 operations) behind a CLI
  (`python -m reality.control`), a Python API (`reality.control.api`) and a stdlib MCP stdio adapter. Includes JSON scene
  schema v1 (one sphere, infinite planes, contacts), scene editing, headless runs with checkpoint and resume, friction
  sweeps, inspection (body, scene, series, rolling onset, summary), run comparison, a pure-Python PNG preview with
  numerical description, export bundles with SHA-256, resource limits and stable error codes. Documents:
  `AI_CONTROL_ARCHITECTURE.md`, `CLI_REFERENCE.md`, `API_REFERENCE.md`, `MCP_REFERENCE.md`, `SCENE_SCHEMA.md`,
  `PREVIEW_SYSTEM.md`, `RESOURCE_LIMITS.md`, `AI_AGENT_GUIDE.md`, `AI_CAPABILITY_MATRIX.md`. Tests `tests/test_control.py` (40).
- Validation SIM-01, SIM-02 (slide-to-roll time of a steel sphere against 2 v0 / (7 mu g), through the scene pipeline) and
  SIM-03 (checkpoint restart reproduces the continuous run). Validation cases now 79. Cases gained optional metadata
  fields `model`, `initial_conditions` and `limitations` (empty for earlier cases).
- Phase 3: `rigidbody.py` (single 3D rigid body: quaternion attitude, body-frame Euler equations, RK4 with
  renormalisation, kinetic energy, angular momentum) and `contact.py` (sphere on infinite planes: impulse contact with
  restitution, Coulomb friction with sticking and sliding, penetration projection). Validation RB-01..05 and CON-01..07.
- Phase 4: `weibull.py` (two-parameter Weibull failure probability, inverse, median strength, size effect, effective
  volume, median-rank fit). Validation WEIB-01..05.
- Phase 7 first slice: `hydrostatics.py` (hydrostatic pressure, buoyant force, floating fraction, apparent weight).
  Validation HYD-01..03.
- Phase 8: `thermal2d.py` (explicit 2D conduction on a square with Dirichlet walls, with an analytic sine-mode
  reference). Validation THER-06.
- Phase 9 benchmarks: `biology.py` (logistic growth; Lotka-Volterra with exact first integral). Validation BIO-01..02.
  No biological system is modelled.
- Phase 2 completion: `tests/test_physical_object_api.py` (17 tests) covering validation errors, shape dimension errors, weight,
  kinetic energy, `above_melting_point` (None, True, False), and inertia about a point matching principal inertia.
  The existing `tests/test_objects.py` (20 tests, from the Phase 2 slice commit) is kept unchanged.
- Research gate: `test_ledger_row_count_matches_its_numbering` pins the verification ledger to its stated count.
- `LIMITATIONS.md` §8: sources used by Phases 2-9 that are not yet in the verification ledger.
- Phase 1 (scientific research) closed: `SCIENCE_RESEARCH.md` with every `[verify]` item resolved, DOIs added where
  confirmed, a verification ledger (§10), and Weibull statistics for flaw populations. Gate test:
  `tests/test_research_gate.py`.
- `THIRD_PARTY_LICENSES.md` §5: licences verified for Meep, OpenFOAM, FEniCS, pyroomacoustics, Cantera, RDKit,
  COPASI, NEURON, OpenSim, Chrono, OpenSees, MuJoCo, Pinocchio, Box2D, ngspice, SU2, Palabos, pbrt-v4, Taichi MPM,
  Eigen and OpenVDB (OpenVDB depends on version).
- Phase 2 first slice: `objects.py` (`PhysicalObject` for sphere, box and cylinder: mass, centre of mass,
  principal and parallel-axis inertia, weight, kinetic energy, heat capacity, melting state) with validation cases
  OBJ-01..08 and `tests/test_objects.py`. `units.MOMENT_OF_INERTIA` added.
- `constants.py`: Schott N-BK7 mechanical constants (E, nu, density) stored separately from the soda-lime `glass` row.

### Fixed
- Blender, present in the committed add-on (`71ca683`) and found in this milestone: a marked sphere with a non-identity
  rotation sent a float32 quaternion. Its norm error (2.8e-9 for a rotation of 0.3 rad about (1, 2, 0.5)) is above the
  kernel's 1e-9 tolerance, so the bake was refused with "quaternion must be a unit quaternion". Quaternions are now
  normalised in double precision (`scene_build.unit_quaternion`). The smoke test used no rotation, so it did not catch this.
- Blender: a sphere whose origin is off its geometric centre would be simulated from the origin while its visible geometry
  sat elsewhere, with no warning. It is now refused, with the reason given.
- Ghost contacts on internal edges: a sphere over the seam of a flat mesh received a sideways contact. Edge and vertex
  contacts dominated by a strictly closer face contact are now dropped (`mesh.drop_dominated_features`).
- `preview.frame` and `inspect.*` no longer fail with `KeyError: 'bodies'` on v2 results. They accept v2 and v3
  results; rolling onset reports `available: false` for them. Schema v1 output is unchanged (byte-identical PNG).

### Corrected
- Phase 1 was marked Done too early. Its roadmap entry said "37 entries" (the ledger has 38) and "licences checked" (§5.2
  still has two open items). It is now Partial.
- `contact.py` docstring claimed Baraff and Catto were in SCIENCE_RESEARCH.md. They are not; the docstring now says so.
- OpenSees was previously listed as BSD. It is a University of California non-commercial licence.
- The `glass` material row is soda-lime glass; its source and uncertainty fields now say so, and BK7 is labelled
  as a different glass.
- Test count: 121 at v0.1.0 was 45 validation cases, 2 registry structural tests and 74 unit tests (not 76 unit tests).
- Blender size measured at commit 69f2f845: 446 MB on disk including an 87 MB shallow `.git`; 20,962 files
  outside `.git`; `tests/python` has 337 files (earlier figures 20,968 and 144 were wrong).

## [0.1.0] - 2026-11-19

### Added
- Phase 0: shallow clone and inventory of Blender (commit `69f2f845e71836859f7e050095f10a4e6b8d5985`), with
  real source paths and license checks recorded in `ARCHITECTURE.md`.
- `units.py`: SI dimension algebra with rational exponents and a dimension-checked quantity type `Q`.
- `constants.py`: physical constants with their sources (CODATA 2018, IERS 2010, IAU, US Standard Atmosphere,
  Schott BK7 Sellmeier coefficients).
- `materials.py`: `Material` model with physical validation rules, `MaterialDatabase` with custom-material support,
  and 18 built-in materials (water, air, iron, steel, aluminum, copper, gold, silver, diamond, glass, wood,
  concrete, rubber, HDPE, sand, soil, ice, cortical bone).
- `gravity.py`: uniform, point-mass and N-body gravity; Earth, Moon and Mars presets.
- `integrators.py`: RK4 and velocity Verlet.
- `mechanics.py`: quadratic-drag free fall, projectile, large-amplitude pendulum (exact elliptic period),
  1D collision with restitution, Kepler orbits.
- `thermal.py`: lumped capacitance, explicit 1D conduction with a stability check, metal-on-ice energy balance,
  radiative exchange.
- `optics.py`: Snell's law, critical and Brewster angles, Fresnel reflectance (s, p, unpolarized), BK7 dispersion.
- `acoustics.py`: speed of sound, impedance, normal-incidence reflection and transmission, Doppler, resonances, SPL.
- `fracture.py`: linear-elastic fracture (K_I, critical flaw, Griffith energy) and yield criteria, with `assess()`
  choosing the governing mode from the material's behaviour.
- `structures.py`: Euler-Bernoulli cantilever deflection, root stress and first natural frequency.
- `validation.py`: 45 validation cases (mechanics, gravity, thermal, optics, acoustics, fracture, structures,
  materials), each with a reference, source, tolerance and kind.
- Tests: units, materials, mechanics, gravity and thermal, optics/acoustics/fracture/structures, and a parametrised
  registry test that asserts every validation case. The 121 tests at v0.1.0 were 45 parametrised validation cases, 2 registry structural tests and 74 unit and regression tests (corrected in Phase 1; the earlier split of 76 unit tests counted the 2 structural tests twice).
- Tools: `tools/run_validation.py` (writes `VALIDATION_REPORT.md`), `tools/benchmark.py` (writes
  `PERFORMANCE_REPORT.md`), `tools/export_materials.py` (writes `MATERIAL_DATABASE.md`).
- Example: `examples/material_failure_table.py` (the same stress gives different outcomes for glass and steel).
- Documentation: README, SCIENCE_RESEARCH, ARCHITECTURE, PHYSICS_MODELS, MATERIAL_DATABASE, NUMERICAL_METHODS,
  VALIDATION_REPORT, PERFORMANCE_REPORT, THIRD_PARTY_LICENSES, DEVELOPMENT_ROADMAP, LIMITATIONS, CHANGELOG.

### Fixed during development (found by the test suite)
- `ln cosh` cancellation for small arguments in the drag free-fall analytic solution (distance error 4e-6). Replaced by
  a stable `log1p` form.
- Cantilever double integration used a one-sided sum with an O(dx) bias (error 1.9e-4). Replaced by a trapezoidal rule
  (error 1.6e-8).
- Cantilever frequency reference used L^2 instead of L^3 in the denominator (a test-side error, corrected).
- Orbit period check ended 1.9e-4 s short of one period because the step count was rounded (test-side; the step is now exact).
- Pendulum series check used 5 terms at 1 rad; truncation error (1.4e-6) is now avoided by checking at 0.5 rad.

### Not included (explicitly)
- Blender build or modification; GPU or multithreaded solvers; fluids, fire, chemistry, biology; spectral rendering;
  editor UI; experimental validation datasets. See `LIMITATIONS.md` and `DEVELOPMENT_ROADMAP.md`.
