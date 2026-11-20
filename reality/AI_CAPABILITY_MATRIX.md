# AI control capability matrix

Status of each item in the headless batch (brief section 3 and `AI_CONTROL_ARCHITECTURE.md` section 3).
Status values: **Implemented** (code, tests and validation evidence), **Partial**, **Not started**.

| item | status | evidence |
|---|---|---|
| Repository audit | Implemented | `AI_CONTROL_ARCHITECTURE.md` section 1 |
| Architecture document | Implemented | `AI_CONTROL_ARCHITECTURE.md` |
| One operation registry for CLI, API and MCP | Implemented | `control/operations.py`; tests in `tests/test_control.py` |
| Scene schema v1 (sphere, plane, contacts) | Implemented | `SCENE_SCHEMA.md`; `control/scene.py` |
| Scene editing (create, add, set, remove, validate, describe) | Implemented | `CLI_REFERENCE.md`; tests |
| Headless run of one sphere on planes | Implemented | `control/simulate.py`; SIM-01..03 |
| Checkpoint and resume | Implemented | SIM-03 (exact match); `test_checkpoint_resume_matches_continuous_run` |
| Parameter sweep (friction) | Implemented | `simulate.sweep_friction`; tests |
| Blender add-on: mark spheres and planes, bake physics to keyframes (Blender 5.0.1) | Implemented, headless-tested | `blender_addon/`; `tools/blender_smoke.py`; `test_blender_scene_build.py`; viewport not checked |
| Multi-body spheres, sphere-sphere and sphere-plane contacts (schema v2) | Implemented, limited | `multibody.py`, `control/multibody_scene.py`; `test_multibody.py`, `test_multibody_scene.py`; spheres only, one contact point per pair |
| Collision geometry: sphere-triangle, sphere-box, box-plane, static triangle mesh (BVH), with tests | Implemented, limited | `src/reality/collision/`, `COLLISION_GEOMETRY.md`; `test_collision_narrow.py`, `test_collision_mesh.py`; box-box and box-mesh not implemented |
| Scene schema v3 (spheres, boxes, planes, static meshes) with explicit errors and limits | Implemented, limited | `control/collision_scene.py`, `SCENE_SCHEMA.md`; `test_collision_scene.py`; no continuous collision detection |
| Collision tools: `collision.query`, `collision.validate_mesh` | Implemented | `control/operations.py`; `test_collision_scene.py` |
| Blender OBJ import and collider marking for boxes and meshes | Not started | Phase 6 of the collision milestone |
| Inspection of one body, one scene, time series, rolling onset, summary | Implemented | `control/inspection.py`; tests |
| Rolling onset from slip | Implemented, derived | least-squares fit of contact-point slip; SIM-01/02 check it against 2 v0 /(7 mu g) |
| CPU PNG preview with overlays and numerical description | Implemented | `PREVIEW_SYSTEM.md`; determinism tested |
| Run comparison | Implemented | `experiment.compare`; tests |
| Export bundle with hashes | Implemented | `export.bundle`; hashes tested |
| Resource limits and stable error codes | Implemented | `RESOURCE_LIMITS.md`; tests |
| CLI (JSON on stdout, exit codes) | Implemented | `CLI_REFERENCE.md`; subprocess tests |
| Python API (`call`, `call_json`) | Implemented | `API_REFERENCE.md`; tests |
| MCP over stdio (stdlib JSON-RPC 2.0 subset) | Implemented | `MCP_REFERENCE.md`; tests |
| Validation cases for the scene pipeline | Implemented | SIM-01, SIM-02, SIM-03 in `validation.py` |
| Multiple bodies, body-body contact | Not started | deferred (`AI_CONTROL_ARCHITECTURE.md` section 2.3) |
| Meshes (OBJ or other) | Not started | format decision pending the user |
| Atmosphere model in scenes | Not started | model decision pending the user |
| Thermal and stress fields in scenes | Not started | the core has these models separately; not wired to scenes |
| Contact force and torque output | Not started | the solver does not expose impulses per step in this release |
| GIF, scientific plots | Not started | out of scope for this batch |
| Rust core | Not started | deferred |
| Blender integration | Not started | the repository is QuoteCraft; Blender is not in the workspace |

## Physics scope of the rigid-body runner

- Solid sphere, uniform density, body frame at the centre.
- Coulomb sliding friction with one value per body-plane pair; restitution with one value per pair.
- Fixed-step explicit stepper (`contact.step_sphere`), one contact point per step, no tunnelling protection.
- Gravity uniform. No drag, no air, no rolling resistance.
- A friction value of zero gives no tangential impulse; with zero friction a rolling sphere keeps its spin.

## Limitations to state with any result

- The contact model is a single-point impulse with no tunnelling protection; large steps or fast spheres can penetrate.
  Penetration is checked against `1e-6 m` and reported.
- Rolling onset is a derived quantity (fit to slip), not a solver output.
- Results are for the model above, not for real materials in contact. Friction values are inputs, not measurements.
