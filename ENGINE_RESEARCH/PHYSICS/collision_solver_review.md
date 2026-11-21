# Physics engines: collision, contact and solver review (targeted source)

Scope: the contact pipeline of seven physics projects from the directive's list (Box2D, Rapier, MuJoCo, ReactPhysics3D,
Jolt, cannon-es, Chipmunk2D). For each, the questions that matter to Reality's box–box work: broadphase structure,
contact manifold size and reduction, solver family and default iteration counts, warm starting, and continuous collision
detection (CCD). Reality's values are from its own code, for comparison.

## How this was done

- Source trees were downloaded as codeload tarballs of each project's default branch and read with `grep` and `sed`
  at the file and line given below. Nothing was copied into this repository (the tarballs are outside the repo, under
  `/tmp/er/src`; their commit SHAs are in `SOURCES/SOURCES.md`).
- Box2D was read at v3.2.0 (`include/box2d/base.h` lines 134–140). Its source was already in the workspace from
  Phase 7 (`/tmp/box2d_src`), and the file references below are to that tree.
- MuJoCo: the collision file was reviewed in Phase 7 (`engine_collision_box.c`, main branch at download). This
  document does not re-review MuJoCo; its entry relies on the Phase 7 notes in `reality/BOX_BOX_RESEARCH.md`.
- A value is written as a **fact** only if a file line was read. Anything not read is marked **not checked**.
- Nothing here measures performance or accuracy of the other engines. These are source facts about defaults and
  design. Any claim that one design is better needs a measurement in Reality's harness, and none is made here.

## Facts by engine

### Box2D (MIT; v3.2.0)
- Defaults (`src/types.c` lines 21–28): `contactHertz = 30`, `contactDampingRatio = 10`, `contactSpeed = 3 × lengthUnits` (3 m/s at 1 m units),
  `maximumLinearSpeed = 400 m/s`, `enableSleep = true`, `enableContinuous = true`, `restitutionIterations = 2`.
- Contact stiffness is clamped per step: `contactHertz = min(world->contactHertz, 0.125 * context->inv_h)`
  (`src/physics_world.c` line 944). The soft-contact model is therefore a spring whose frequency is bounded by the
  sub-step rate.
- Manifold: `b2Manifold` holds `points[2]` and `pointCount` in {0, 1, 2} (`include/box2d/collision.h` lines 616–619).
  Polygon manifolds are at most two points.
- CCD: `enableContinuous` is on by default at world level (above). The per-body treatment (`isBullet`) is in
  `src/body.c` / `src/body.h` / `src/physics_world.c`. Not read beyond the flag names.
- Sub-steps: passed to the world step by the caller (`physics_world.c` line 1186); no default was found in the types file.

### Rapier (Apache-2.0; master at 2026-10-10 commit `475caa3`)
- Manifold size: `MAX_MANIFOLD_POINTS` is 4 in 3D and 2 in 2D (`src/lib.rs` lines 258 and 291, under `cfg` for dim2/dim3).
  A contact constraint solves at most this many points.
- Manifold reduction: `src/geometry/manifold_reduction.rs`, `reduce_manifold_naive`. If more than 4 points, it keeps
  (1) the deepest point; (2) the point furthest from it, among points within the prediction distance; and (3) the two
  points with the most negative and most positive projection onto the tangent (`cross(AB, normal)`) of the segment
  from (1) to (2), among the points not yet selected and within the prediction distance (lines 1–75 read).
- Solver defaults (`src/dynamics/integration_parameters.rs`, `impl Default`, lines 409–429): `dt = 1/60 s`,
  `num_solver_iterations = 4`, `num_internal_pgs_iterations = 1`, `num_internal_stabilization_iterations = 1`,
  `warmstart_coefficient = 1.0`, `contact_clustering = true`, `contact_recycling = true`.
- Contact softness: `SpringCoefficients::contact_defaults()` is documented as 30 Hz with damping ratio 10 (lines 57–58),
  with the stated reason that the high damping ratio is needed for large piles and stacks.
- Warm starting: impulses from the previous step are re-applied, scaled by `warmstart_coefficient` (lines 230–236,
  324). Contact recycling carries contacts between steps (`normalized_contact_recycle_distance = 0.05`, line 427).
- CCD: `src/dynamics/ccd/` (`ccd_solver.rs`). `PhysicsWorld` holds a `CCDSolver` (`src/pipeline/physics_world.rs`
  lines 95, 113) and passes it into the step (line 165). The CCD mechanism itself was not read beyond these lines.
- Broadphase: `src/geometry/broad_phase_bvh/mod.rs` line 23, `BroadPhaseBvh`.

### Jolt (MIT; master at 2026-11-21 commit `56d4509`)
- Manifold size: `ContactConstraintManager::MaxContactPoints = 4` (`Jolt/Physics/Constraints/ContactConstraintManager.h`
  line 81). Face–face contacts are built by `ManifoldBetweenTwoFaces` (`Jolt/Physics/Collision/ManifoldBetweenTwoFaces.h`
  line 38), which clips one face against the other.
- Solver defaults (`Jolt/Physics/PhysicsSettings.h`): `mNumVelocitySteps = 10` (line 84), `mNumPositionSteps = 2` (line 87),
  `mBaumgarte = 0.2` (line 45), `mSpeculativeContactDistance = 0.02` (line 50), `mPenetrationSlop = 0.02` (line 53).
  The header states that velocity steps must be at least 2 for friction to work.
- Warm starting: `mConstraintWarmStart = true` (line 108). `PhysicsSystem.cpp` line 1414 sets the ratio passed to
  `WarmStartVelocityConstraints`: 0 when warm starting is disabled, the context value on the first step, and 1.0 on
  later steps.
- CCD: per body, `EMotionQuality::LinearCast` (`Jolt/Physics/Body/MotionQuality.h` lines 10–28). The header documents
  that this stops high-speed bodies tunnelling through thin objects, but that a body can still tunnel if it is long,
  thin and spinning fast, that time is "stolen" (the body stops at first contact and does not bounce until the next
  step), and that a body may pass through geometry when stuck. `Discrete` is the default (`Jolt/Physics/Body/BodyCreationSettings.h` line 104).
- Broadphase: `Jolt/Physics/Collision/BroadPhase/BroadPhaseQuadTree.{h,cpp}`, with `BroadPhaseBruteForce` as an
  alternative.

### ReactPhysics3D (Zlib; master at 2025-01-09 commit `7000610`)
- Manifold limits (`include/reactphysics3d/configuration.h`): `NB_MAX_CONTACT_MANIFOLDS = 4` (line 137),
  `NB_MAX_CONTACT_POINTS_IN_NARROWPHASE_INFO = 16` (line 134), `NB_MAX_POTENTIAL_CONTACT_MANIFOLDS = 64` (line 140).
  `CollisionDetectionSystem.cpp` line 1407 trims potential manifolds to `NB_MAX_CONTACT_MANIFOLDS`.
- World defaults (`include/reactphysics3d/engine/PhysicsWorld.h`, `WorldSettings()`, lines 126–132):
  `persistentContactDistanceThreshold = 0.03`, `defaultFrictionCoefficient = 0.3`, `defaultBounciness = 0.5`,
  `isSleepingEnabled = true`, `defaultVelocitySolverNbIterations = 6`, `defaultPositionSolverNbIterations = 3`.
- Warm starting: `ContactSolverSystem::warmStart()` (`src/systems/ContactSolverSystem.cpp` line 326). Persistent
  contact points are kept by `ContactPoint(…, persistentContactDistanceThreshold)` (`ContactPoint.h` line 101).
- Narrowphase: `src/collision/narrowphase/` contains SAT and GJK code. Broadphase: `src/collision/broadphase/DynamicAABBTree.cpp`.
- CCD: a case-insensitive search for "continuous collision" and "ccd" in `include/` and `src/` found nothing. Stated as
  "none found in the source searched", not as a proof of absence.

### cannon-es (MIT; master at 2024-01-06 commit `dd971c4`)
- Solver: `World.ts` line 27 `this.iterations = 10`; line 238 default solver `new GSSolver()`. Solver documentation
  (line 11) says more iterations give more correct constraints at higher cost.
- Broadphase: default `new NaiveBroadphase()` (`World.ts` line 235). `SAPBroadphase` and `GridBroadphase` are provided
  as options (`src/collision/`).
- CCD: no match for "ccd" or "continuous" under `src/`.
- Contacts: one `ContactEquation` per contact, through `src/collision` and `ContactMaterial` (not read in detail).

### Chipmunk2D (MIT; master at 2026-05-05 commit `f2f3d66`)
- Solver: `space->iterations = 10` (`src/cpSpace.c` line 131). Collision slop `collisionSlop = 0.1` (line 136).
- Manifold: `#define CP_MAX_CONTACTS_PER_ARBITER 2` (`include/chipmunk/cpArbiter.h` line 29).
- Warm starting: each contact stores accumulated normal and tangent impulses (`jnAcc`, `jtAcc`, read at
  `src/cpArbiter.c` lines 150, 166–169). The code path that reapplies them was not traced.
- Broadphase: static and dynamic shapes each have a `cpBBTree` (`src/cpSpace.c` lines 144–145). Spatial hash
  (`cpSpaceHash.c`) and 1D sweep-and-prune (`cpSweep1D.c`, declared in `include/chipmunk/cpSpatialIndex.h` lines 106–113)
  are also present.
- CCD: none found. `cpSweep1D` is a spatial index (broadphase), not a time-of-impact method.

### MuJoCo (Apache-2.0; Phase 7 review)
- Phase 7 read `src/engine/engine_collision_box.c`: 15-axis separating-axis test with support radii; face contacts by
  Sutherland–Hodgman clipping of the incident quad against four side planes, at most 8 vertices; contact at the midpoint;
  no manifold reduction. Recorded in `reality/BOX_BOX_RESEARCH.md`. Not re-read here.

## Comparison with Reality (from Reality's code)

| Property | Reality (`reality/src/reality/collision/`) | Box2D v3.2 | Rapier | Jolt | ReactPhysics3D | Chipmunk2D | cannon-es | MuJoCo (Phase 7) |
|---|---|---|---|---|---|---|---|---|
| Max points per box face manifold | All distinct clipped vertices with depth ≥ −TOUCH_TOL (`box_box.py`, `_face_contacts`, about lines 178–197); no reduction | 2 | 4 (3D) | 4 | 4 manifolds per pair | 2 | one per contact | all clipped vertices, no reduction |
| Manifold reduction | none | (polygon limit) | 4-point selection (`manifold_reduction.rs`) | clipping | trim to 4 manifolds | none | none | none |
| Solver family (as documented) | Gauss–Seidel impulses, 128 sweeps for box steps, 8 otherwise (`solver.py` lines 43–44, 317) plus a position projection pass, up to 40 (`PROJECTION_PASSES`) | soft contacts (30 Hz, ζ 10), sub-steps (`subStepCount`) | soft contacts (30 Hz, ζ 10), staged island solver | velocity steps plus position steps (`PhysicsSettings.h`) | velocity plus position iterations (`PhysicsWorld.h`) | iterative impulses (`iterations`) | GS (`GSSolver`) | constraint solver (not re-read here) |
| Default velocity iterations | 8 (sphere-only) / 128 (box steps) | caller-set sub-steps | 4 (+1 PGS, +1 stabilisation) | 10 | 6 (+3 position) | 10 | 10 | not re-read |
| Warm starting | none (tested, no gain at 8–32 sweeps; cap-10 code; `CHANGELOG.md`) | not checked | on (coefficient 1.0) | on | persistent contacts + `warmStart` | cached impulses | not checked | not checked |
| CCD | none (`box_box.py` limits) | on by default (`enableContinuous`) | module present (`dynamics/ccd`) | per-body LinearCast | none found | none found | none found | not checked |
| Broadphase | none; caller lists pairs (O(N²)) | (not read) | BVH | QuadTree | DynamicAABBTree | BBTree / hash / sweep-1D | Naive (default), SAP, Grid | (not read) |

Notes on the table:
- Iteration counts are not directly comparable. Soft-constraint engines (Box2D, Rapier) use spring coefficients, and
  Box2D takes sub-steps from the caller, so one "iteration" is not the same work as one Gauss–Seidel sweep. The solver
  names in the table are the names used in the code; the families were not classified further in this review. Reality's 128 sweeps should not be
  read as "more than the others need" without a measurement.
- "not checked" means the file was not read in this review, not that the feature is absent.

## Hypotheses (not established)

1. Reality keeps more contact points per face (up to all clipped vertices) than the engines that reduce to 2 or 4. This
   may contribute to the number of sweeps needed (`BOX_BOX_STUDY.md` §1). Not tested: a 4-point reduction in Reality's
   solver has not been built or measured.
2. Warm starting in Reality failed in an earlier test (cap-10 code, 8–32 sweeps). The other engines use it by default.
   Whether it helps at 128 sweeps and with the current projection is untested.
3. The lack of a broadphase is Reality's largest scaling cost (N = 100: 0.32 s/step; N = 500: 62 s/step, measured). A
   BVH or sweep-and-prune index would reduce pair tests, but the saving has not been measured in Reality.
4. A per-body linear cast (Jolt's approach) or a Box2D-style continuous flag might address thin, fast boxes. Reality has
   no CCD; whether one is needed for its target scenes is untested.

Each hypothesis is a candidate for a measured experiment, not a finding. See `ADOPTION_CANDIDATES.md`.

## What this review does not cover

- Friction models in detail (only defaults were read).
- Restitution handling in the other engines.
- Sleeping and island management (named in the sources, not read).
- Accuracy or stability comparisons; these need the same scenes run through each engine, which was not done.
- Performance. No timings for the other engines were taken.
