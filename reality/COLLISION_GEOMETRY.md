# Collision geometry (PROJECT REALITY, milestone "collision geometry foundation")

Status: all phases implemented. Box-box and box-mesh contacts are not implemented; they are refused by validation with a
stated reason. Phase 6 (Blender) is headless-tested and checked under `bpy` 5.0.1 (section 11); the viewport is not checked.

## 0. Audit (before implementation)

Checked on 2026-11-20 (sandbox clock, UTC; the session date given was 2026-11-19) in `/home/user/Qoute-editor`, branch `arena/7257ca22-qoute-editor`, before any code was written.

| Item | Finding (verified by command, not from notes) |
|---|---|
| HEAD / tree | `71ca683`, equal to `origin/arena/7257ca22-qoute-editor`. Working tree clean. |
| Test baseline | `pytest tests`: 337 passed (about 33 s). |
| Hardware | 2 CPU cores, 3.9 GB RAM, Python 3.11.2. Pure Python only. |
| Collision primitives | Sphere (body). Infinite plane (`contact.Plane`). Nothing else. `objects.Box` is a mass-property shape, not a collider. No box collider, triangle or mesh anywhere in `src/reality`. |
| Contact generation | Hard-coded per type in `multibody._build` (plane and pair contacts), with detection at predicted positions and projection by sphere-specific formulas. One contact point per pair or plane. |
| Solver assumptions | Sequential impulses (`multibody.step_bodies`). Scalar inertia per sphere, so no tensor inertia. No warm starting. No continuous collision detection. |
| Scene schemas | v1: one sphere, planes. v2: several spheres, planes, per-contact coefficients; `type` must be `"sphere"`; optional unit quaternion. |
| Blender add-on | Marks spheres and planes only; bakes from the v2 solver. No box or mesh colliders, no static flag. Tested headless under `bpy` 5.0.1. (Phase 6 extends this; see section 11.) |
| Known defect found in audit | `preview.frame` and `inspect.*` raise a bare `KeyError: 'bodies'` on v2 results. Fixed in this milestone (section 6). |
| Speed baseline (pure Python, dt 1e-4, 0.2 s) | 1 sphere: 22,120 steps/s. 4 spheres: 5,742. 8 spheres: 3,098. This was measured in the audit with its own workload and is not directly comparable with the benchmark in section 7. |

Conclusion of the audit: the sphere physics is validated and is kept as it is. A general narrow phase, a generalised
contact representation and tensor inertia for boxes were needed. The existing sphere solver is not replaced: a
separate general step (`collision/solver.py`) is added, and it reproduces the existing sphere results (section 5).

## 1. Architecture

Modules under `src/reality/collision/` (the layers are separate):

1. **Narrow phase** (`narrow.py`): pure functions, no solver state. `Contact(normal, point, depth, feature)`.
   Closest point on a segment and a triangle; sphere-triangle; sphere-box; box corners against a plane;
   sphere-plane; sphere-sphere.
2. **Mesh** (`mesh.py`): `validate_mesh_data` (explicit errors, never raises), `TriangleMesh` (own pose, validated on
   construction), `BVH` (axis-aligned, median split on the longest axis, leaf size 4), `drop_dominated_features` and
   `reduce_contacts` (section 3). `MESH_LIMITS` are resource limits.
3. **Solver** (`solver.py`): `Body` (sphere or box, tensor inertia, optional static), `PairSpec` (one listed pair),
   `step` (sequential impulses with Coulomb friction, then position projection), momentum and energy helpers.
4. **Scene** (`control/collision_scene.py`): schema v3 validation with explicit reasons, the run loop, resource
   limits, cancellation, and the reproducible result document `reality.collision_run` v1.
5. **Operations** (`control/operations.py`): `simulate.multibody` dispatches by `schema_version` (v2 to
   `multibody_scene`, v3 to `collision_scene`); `collision.query` and `collision.validate_mesh` are new.

Schema v1 (`scene.py`, `simulate.py`) and v2 (`multibody_scene.py`) are unchanged in behaviour. Their tests pass
without edits, except the registry count (section 6).

## 2. Collision conventions (explicit)

- Units: SI. Lengths in metres. Quaternions (w, x, y, z), body to world.
- A box is centred on its body frame. `half_extents = (hx, hy, hz)` are half the edge lengths along body axes.
- Box inertia (solid, uniform density): `I_x = m (hy^2 + hz^2) / 3`, checked against `objects.Box`.
- A triangle mesh is static, with its own pose. Vertex coordinates are in the mesh frame.
- A contact normal `n` points from `a` to `b`. For a static shape the normal points from the shape to the sphere
  or body. A contact is active when the depth is greater than 0.
- Depth is the overlap along `n`, in metres; positive when penetrating.
- Degenerate geometry is handled explicitly: a zero-area triangle is a warning and still gives edge contacts; a
  centre on a degenerate triangle returns a defined, finite normal (tested).
- Static bodies have infinite mass, zero velocity and zero angular velocity. A static body must not be listed with
  velocity.

## 3. Contact generation rules

- **Sphere-triangle**: closest point on the triangle by the Voronoi-region method (vertex, edge, face cases). A centre
  inside the face takes the face normal. A centre exactly on the face takes the side given by `prefer` (the
  opposite of the body's velocity, for meshes) and otherwise a winding-independent sign rule.
- **Sphere-box**: closest point on the box (clamp in the box frame). A centre inside the box exits through the
  nearest face.
- **Box-plane**: each box corner below the plane is a contact (feature `vertex`). A flat box gives four contacts.
- **Dominated features (internal edges)**: an edge or vertex contact is dropped when a face contact is strictly
  closer. This removes the spurious contacts on the seam between two coplanar triangles, which otherwise push a
  sphere sideways (found by the test, section 6). A face distance is never more than the distance to a point on the
  same face, so the rule follows from the minimum-distance principle. Convex edges with no closer face contact are
  kept.
- **Normal clusters**: contacts whose normals agree within cos > 0.999 (about 2.6 degrees) are merged, keeping the
  deepest. This is a modelling choice, not a measured constant. It bounds the number of constraints on a flat floor.

## 4. Status of each pair

| Pair | Status | Evidence |
|---|---|---|
| sphere-sphere | Implemented (general solver and existing solver) | `test_collision_solver.py` (regression against `multibody.step_bodies`) |
| sphere-plane | Implemented (general solver and existing solver) | regression against `contact.step_sphere` (1e-11) and `multibody.step_bodies` |
| sphere-triangle | Implemented | 32 narrow tests, 35 mesh tests (brute-force agreement, winding, degenerate, feature cases) |
| sphere-box | Implemented, sphere inside and outside the box | `test_collision_narrow.py` (outside checked against an exact clamp reference; inside case) |
| box-plane | Implemented, corner contacts only | `test_collision_narrow.py`; `test_collision_solver.py` (rest, friction) |
| sphere-mesh (static) | Implemented with validation, BVH, reduction and the dominance rule | `test_collision_mesh.py`; `test_collision_solver.py` (no seam drift, bounce, rest) |
| box-box | **Not implemented.** Refused by validation: "unsupported pair box-box". No axis-aligned-only shortcut exists. SAT with clipping is the expected candidate for a later milestone. | `test_collision_scene.py` |
| box-mesh | **Not implemented.** Refused by validation. | `test_collision_scene.py` |

Box-plane is a corner model. A box resting edge-on or tilted is represented by its corners below the plane. It has no
face-plane contact patch, so the contact is less accurate than a clipped manifold would give.

## 5. Numerical checks

Regression against the existing sphere solver (same initial state, same step, same constraint order):

| Scenario | Quantity | Measured worst difference | Test tolerance |
|---|---|---|---|
| single sphere vs `contact.step_sphere` (two cases) | state | 2.2e-12 | 1e-11 |
| bounce on plane | state | 0 | 1e-11 |
| oblique impact with spin on plane | state | 2.8e-13 | 1e-11 |
| head-on pair | state | 0 | 1e-11 |
| two stacked spheres, 1 s | position | 2.6e-10 m | 1e-9 m |

The stack difference comes from the order in which the projection pass visits the two contacts. It is small, and the
test records it rather than hiding it.

Physical checks (all in tests, values from the measurements in this milestone):

- Head-on equal masses (elastic): velocities swap to within 1e-9 m/s; momentum and energy conserved (relative
  energy error 1e-9 or better).
- Random frictional three-sphere collisions without gravity: total momentum change below 1e-9 over 400 steps, 12 trials.
- Box flat on a plane, dt 1e-4, 2 s: final z = 0.20000005 m against 0.2 m, residual speed 2.6e-5 m/s, residual
  angular speed 1.3e-4 rad/s.
- Sphere on a two-triangle floor over the seam (dt 1e-4, 0.4 s): lateral speed at most 5.4e-15 m/s (no ghost force).
- Elastic bounce on a mesh (restitution 1, dt 1e-4): first apex error 4.4e-4 m. The error is first order in dt:
  4.43e-3 m at dt 1e-3, 4.43e-4 m at 1e-4, 4.43e-5 m at 1e-5. The test tolerance is 1e-3 m.
- Sphere resting on a mesh with restitution 0: final centre height within 1e-6 m of the radius, speed below 1e-3 m/s.
- Box on a static sphere: settles on the apex (tolerance 2e-3 m).
- Determinism: two runs of the same scene give bitwise identical records and final state.

Penetration: the scene run stops with `invalid_state` if the penetration after a step exceeds 1e-6 m
(`PENETRATION_TOLERANCE_M` in `control/simulate.py`). The scene tests run to completion, so no test reached it.

## 6. What was fixed or found during the milestone

- **Ghost contacts on internal edges (found by the seam tests).** A sphere on a two-triangle floor received a second,
  tilted contact on the seam, which pushed it sideways. Fixed by `drop_dominated_features` (section 3). The test that
  exposed it was not weakened.
- **`preview.frame` and `inspect.*` on v2 results (audit defect).** They read a top-level `bodies` list that v2 and v3
  results do not have, and assumed one sphere and v1 contact strings. Now: body ids come from the scene; each contact
  entry is read as `plane:<id>`, `body:<id>`, `mesh:<id>` or a v1 plane id; box bodies get the box mass properties;
  static bodies report `mass_kg: null` and `gravity_force_N: null`; `inspect.rolling_onset` reports
  `available: false` with a reason for v2 and v3, since the estimate is defined for one sphere on planes only.
  The v1 path is unchanged: `preview.frame` on v1 gives a byte-identical PNG, and every existing description value is
  unchanged; only the new `overlay_body` field is added.
- **Preview scope.** `preview.frame` draws every sphere (up to `MAX_RENDER_SPHERES = 32`, a design limit, not a
  measured figure) and planes. Box and mesh scenes are refused with `unsupported`; they are not drawn incorrectly.
- **Mesh limits.** The provisional values were replaced by measured values (section 7). They are kept, because the
  measurements support them.
- **Operation count.** 25 operations (23 before, plus `collision.query` and `collision.validate_mesh`). The pinned
  count in `test_control.py` and `API_REFERENCE.md` are updated.
- **Static record shape.** Static bodies in v3 records have the same keys as dynamic ones (zero velocity and energy,
  flag `static: true`). Readers therefore need no special case.

## 7. Measured performance

Source: `COLLISION_BENCHMARK.json`, produced by `tools/collision_benchmark.py`. Machine: 2 cores, Python 3.11.2,
Linux. Build times are untraced, best of 3. Peak memory is from one separate `tracemalloc` build. Brute force is a
reference only, run on a prefix of the same 200 queries (at 200k triangles it was not run).

| Triangles | Validate | Build | Peak Python memory | BVH nodes | BVH query | Brute query | Speed-up (same queries) |
|---|---|---|---|---|---|---|---|
| 264 | 0.001 s | 0.003 s | 0.1 MB | 143 | 0.021 ms | 0.65 ms | 32x |
| 4,140 | 0.014 s | 0.055 s | 2.2 MB | 2,135 | 0.036 ms | 9.75 ms | 263x |
| 40,044 | 0.13 s | 0.66 s | 24 MB | 30,935 | 0.13 ms | 95 ms | 566x |
| 199,712 | 0.68 s | 4.28 s | 114 MB | 131,071 | 0.47 ms | not run | - |

Mesh correctness: for 120 random sphere queries on each of three meshes (a 484-triangle UV sphere, an 8,170-triangle UV
sphere and a 400-triangle random soup), the BVH and brute force return the same set of contacts. The comparison sorts the
contacts and rounds normals and depths to 14 decimal places; it is not order-sensitive (`test_bvh_matches_brute_force_exactly`).
Every triangle appears in exactly one leaf for meshes of 1, 3, 4, 5, 17, 256 and 1,000 triangles
(`test_every_triangle_appears_in_exactly_one_leaf`).

Solver throughput (fixed workloads, dt 1e-4; best of 3 runs per workload). Two benchmark runs on this machine differed
by 5 to 7 %, so these are the figures of the saved run, not precise values:

| Scene | General solver (steps/s) | Existing sphere solver (steps/s) |
|---|---|---|
| one sphere on plane | 35,796 | 46,833 |
| box on plane | 2,353 | not applicable |
| sphere on two-triangle mesh | 6,890 | not applicable |
| eight spheres (plane contacts and a chain of seven pairs), 1,000 steps | 459 | 621 |

The general solver is slower than the existing sphere solver on the same sphere scenes: about 24 % on one sphere and
about 26 % on eight. Box scenes are slow (box on plane: 2,353 steps/s) because each corner is a separate constraint.
These are pure-Python figures; a faster kernel would need a different implementation, and none is attempted here.

Resource limits (`collision.MESH_LIMITS`): 16 meshes; 200,000 vertices and 200,000 triangles per mesh; 400,000
triangles in total. They are resource caps chosen from the figures above (two meshes at the per-mesh cap build in about
9 s), not physical limits of the method.

## 8. Known bugs and limitations

- Box-box and box-mesh contacts are not implemented.
- An earlier smoke run (not saved, so its mesh and start state are unknown) reported a sphere-on-mesh minimum height of
  0.136 m against the expected 0.100 m. It was not reproduced: per-step sampling of a sphere dropped on a flat
  two-triangle floor (dt 1e-4, three runs including restitution 0.5) gives a minimum of 0.1000000 m (penetration
  at most 8.4e-8 m). The 0.136 value is therefore unexplained, not confirmed as a sampling artefact.
- Box-plane uses corner contacts only. There is no face patch, so a box resting on a face is less accurate than a
  clipped manifold would give.
- One contact per listed pair for sphere-sphere and sphere-plane; several contacts per pair for triangles and boxes.
- The dominance rule removes a feature contact when any face contact is strictly closer. This is the minimum-distance
  principle. It can remove a physically real second contact in a thin shell penetrated from both sides. Such a case
  is not tested.
- Continuous collision detection is not implemented. Fast spheres can pass through thin meshes or boxes.
- The `invalid_state` stop for penetration above 1e-6 m is implemented but no test triggers it. Tunnelling, which
  is the usual route to large penetration, leaves no penetration to detect, so this stop does not guard against it.
- No warm starting. Stacks of many bodies drift. The existing two-sphere stack test reports 4e-8 m penetration after 2 s
  (audit, `test_multibody.py`).
- Triangle mesh validation rejects a triangle that repeats a vertex index, but it does not check that the mesh is
  closed or manifold.
- The mesh build is a Python loop. Its measured time grows roughly as n log n (0.66 s at 40,044 triangles, 4.28 s at
  199,712). It is measured, not optimised.
- Schema v3 accepts static meshes only. Dynamic meshes are not supported.
- Blender: the box and mesh colliders are checked under `bpy` 5.0.1 only. Dynamic meshes are not supported (a mesh
  collider is always static). A dynamic box cannot be baked with a mesh floor (box-mesh is not implemented).
- The v2 path with meshes is spheres only, one contact point per pair; boxes and static flags need schema v3.

## 9. Research references used

- Ericson, C. (2005) *Real-Time Collision Detection*. Morgan Kaufmann (Elsevier), ISBN 1558607323. Library records give
  2004 (CRC Press) and 2005 (Elsevier). The book was identified by web search. Its content was not read in this
  milestone, so no page or section numbers are cited. The closest-point-on-triangle method and the BVH construction
  are used as standard techniques; the implementation was checked against brute force, not against the book's text.
- The internal-edge (ghost contact) problem is a known issue in mesh collision. The dominance rule here is derived in
  section 3 and tested; no external source for it was consulted in this milestone.

## 10. Next milestone (not started)

- Box-box and box-mesh: a general method (SAT with clipping for box-box), only if it can be verified against a reference.
  Not started.
- Dynamic meshes, continuous collision detection and warm starting, if the tests show they are needed. Not started.
- Continuous collision detection and warm starting, if the tests show they are needed.

## 11. Phase 6: Blender (headless core and `bpy` checks)

Scope as built: OBJ import through the add-on's operator; "Mark as collider" with sphere, box (dynamic or static) and
static triangle-mesh shapes; bake through the headless kernel; static bodies and meshes are not keyed. Blender's rigid
body world is not used. Blender remains optional for the core: the kernel and `scene_build.py` import no `bpy`.

Schema change (approved): a schema v2 document with a non-empty `meshes` list runs on the collision solver under the
v2 rules (spheres only, no `static` flag). Documents without meshes are unchanged. See `SCENE_SCHEMA.md`.

Results, measured in this milestone:

| Check | Value | Tolerance |
|---|---|---|
| Sphere rests on a mesh floor (bake, Blender step 9.9e-4 s) | centre z = 0.050003 m (radius 0.05) | 1e-4 m |
| Box rests on a plane (bake) | z = 0.100005 m (half height 0.1) | 1e-4 m |
| Rotated sphere (float32 rotation of 0.3, 0.5, 0.2 rad) | bake accepted after double-precision normalisation | 1e-9 unit tolerance |
| Float32 quaternion norm error for that rotation (Blender) | -3.0e-8 (fails 1e-9 without normalisation) | - |
| Resting offset vs step (headless, mesh floor, sphere radius 0.05) | 3.5e-6 m at 9.9e-4 s; 9.4e-8 m at 1e-4 s; 8.2e-10 m at 1e-5 s | - |
| Kernel penetration in these bakes | 0 (no positive penetration reported) | 1e-6 m |

The resting offset falls roughly with the step. At 1e-4 s it is about g dt^2 (9.8e-8 m). It is a property of the
step-wise contact model, not a measured error against an exact answer, so it is recorded as a limit.

Refusals (tested with reasons): mirrored object, off-centre origin, sheared transform, parented object, unapplied
modifiers on a mesh collider, box-mesh, box-box, static body with velocity, dynamic body without a material.

Counts: 15 Blender-free tests (`test_blender_colliders.py`), 14 existing (`test_blender_scene_build.py`), 11 v2-mesh
tests (`test_v2_meshes.py`); 34 checks in `tools/blender_smoke.py` under `bpy` 5.0.1, all passing.

Defect found and fixed in this phase: the committed add-on (`71ca683`) sent a float32 quaternion for a rotated sphere,
which the kernel rejected. Recorded in `CHANGELOG.md` (Fixed).
