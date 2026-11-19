# AI_CONTROL_ARCHITECTURE - PROJECT REALITY

This document records (1) the audit of the repository before the AI-control work, (2) the architecture decided from
that audit, and (3) what is deferred. It is the reference for every interface added in this batch. Status words follow
`DEVELOPMENT_ROADMAP.md`: **Done** means implemented, tested and validated. Anything else is named as partial or not
started.

## 1. Repository audit (state at commit 8cbb83f)

### 1.1 What exists and is trustworthy

| Area | Module(s) | State | Evidence |
|---|---|---|---|
| SI units with dimension checks | `units.py` | Done | `tests/test_units.py`; `Q` rejects mixed dimensions |
| Material database (18 materials) | `materials.py`, `constants.py` | Done as a database; values are handbook figures | `MATERIAL_DATABASE.md`, `tests/test_materials.py` |
| Physical object shapes and inertia | `objects.py` | Done for uniform solids (sphere, box, cylinder); no orientation | OBJ-01..08, `tests/test_objects.py`, `tests/test_physical_object_api.py` |
| Rigid body rotation | `rigidbody.py` | Done for one body; inertia is an input | RB-01..05, `tests/test_rigidbody_contact.py` |
| Sphere-plane contact | `contact.py` | Done for one sphere and infinite planes; one coefficient pair per call | CON-01..07 |
| Gravity, mechanics, heat, optics, acoustics, fracture, beams | `gravity.py`, `mechanics.py`, `thermal.py`, `optics.py`, `acoustics.py`, `fracture.py`, `structures.py` | Done as tested kernels, each with analytic validation | 76 validation cases, all passing |
| Weibull, hydrostatics, 2D conduction, population benchmarks | `weibull.py`, `hydrostatics.py`, `thermal2d.py`, `biology.py` | First slices; each tested | WEIB, HYD, THER-06, BIO cases |
| Validation registry | `validation.py` | Done; 76 cases | `tools/run_validation.py` regenerates `VALIDATION_REPORT.md` |
| Research ledger | `SCIENCE_RESEARCH.md` §10 | 38 entries; Phase 1 still Partial | `tests/test_research_gate.py` |

Test status at this commit: 248 pytest tests passing. The test environment is Python 3.11.2 with pytest and pyflakes
only. There is no numpy and no Pillow. `cargo` is not installed.

### 1.2 Deficiencies that block AI control

1. **No operation layer.** Every capability is a Python function call. An agent can only use it by writing Python
   against internal modules. Nothing is discoverable, typed or returned as JSON.
2. **No serialisable scene.** Bodies, planes and coefficients exist only as Python objects built in code. There is no
   file format, no schema version and no validation of user input at a boundary.
3. **Object model not connected to dynamics.** `PhysicalObject` (shape, material, mass, inertia) and `RigidBody`
   (state, inertia) are separate. Any scene bridge must not duplicate the mass and inertia formulas.
4. **Contact coefficients are not per pair.** `step_sphere` takes one `friction` and one `restitution` for all planes it
   is given. A scene with two planes of different friction cannot be represented correctly without changing the solver.
5. **No run record.** Nothing records configuration, numerical parameters, package version, Python version or the
   random seed. The kernel has no stochastic component, so the seed is "not applicable", but that must be stated.
6. **No measurement interface.** Forces and torques are not exposed by the contact solver. The solver returns only the
   list of touching planes, not impulses. Anything reported as a force must be derived and labelled as derived.
7. **No image output.** No renderer, no PNG encoder, no way for a vision model to inspect a state.
8. **No resource controls.** There are no step limits, wall-clock limits, memory budget, cancellation or checkpoints.
9. **Validation metadata is incomplete for the brief.** `ValidationCase` has id, domain, solver, description, kind,
   reference, reference source and tolerance. It does not have physical model, initial conditions, parameters, measured
   and error fields in a common report, or known limitations. Existing cases must keep working unchanged.
10. **No integration tests.** The suite has unit tests and the registry test. No test drives the code through an
    interface boundary.

### 1.3 Things that must not change

- Every physical convention in the kernel: SI units, gravity sign (-z), quaternion order (w, x, y, z), inertia in the
  body frame, friction as a Coulomb coefficient, restitution as a coefficient of restitution.
- All scientific references, ledger entries and validation tolerances. New tolerances are added, not loosened.
- Existing module APIs. New code calls them and does not change their behaviour.

## 2. Architecture decision

### 2.1 Shape

```
  CLI (argparse)  ──┐
  Python API      ──┼──►  operation registry  (reality/control/operations.py)
  MCP (stdio JSON) ─┘          │  one implementation per operation, JSON in / JSON out
                               ▼
        control/scene.py       scene schema v1, validation, creation, edits
        control/simulate.py    run, checkpoint, resume, sweep (headless)
        control/inspection.py  per-body and per-scene observation, supported fields only
        control/preview.py     CPU rasteriser, PNG encoder, numerical description
        control/resources.py   limits, memory reporting, deadlines
                               ▼
        physics kernel (unchanged): objects, materials, rigidbody, contact, validation
```

Rules:

1. The three interfaces are adapters. They parse their input, call `operations.call(name, args)`, and render the result.
   None of them contains physics or defaults that differ from the others.
2. Operations take and return plain JSON-compatible dictionaries. Scene edits are pure: a scene in, a scene out. The
   CLI reads and writes files. The library never writes files unless the operation's purpose is to write a file
   (preview output path, export bundle).
3. Errors are `OperationError(code, message, details)`. The codes are stable strings: `invalid_argument`, `schema_error`,
   `unsupported`, `resource_limit`, `invalid_state`, `not_found`.
4. Outputs are deterministic. Floats are written with `repr`, object keys are sorted, and no wall-clock values appear in
   numerical results. Timing and memory numbers appear only in a separate `diagnostics` block.
5. Nothing in `control/` is imported by the physics kernel. The dependency is one way.
6. The MCP adapter imports only the standard library. Importing `reality` must not import MCP code.

### 2.2 Decisions and why

| Question | Decision | Reason |
|---|---|---|
| Implementation language | **Python for this batch.** Rust is deferred. | `cargo` is not installed here. The kernel runs at about 20,000 sphere-plane steps per second on the target machine (measured), which is enough for the small scenes in this batch. No benchmark yet shows Python as the bottleneck. Rust will be reconsidered only with a measured bottleneck, recorded in `RESOURCE_LIMITS.md`. |
| Scene and command format | JSON with an integer `schema_version`. The validator is written in the project (no `jsonschema`). | Human-readable, diffable, stdlib-only. The schema is documented in `SCENE_SCHEMA.md`. |
| Image output | Pure-Python rasteriser and PNG writer (`zlib`, `struct`). | No Pillow or numpy, and no GPU or desktop. An AI vision model can open PNG directly. |
| GIF output | **Not implemented.** | Not needed for the acceptance workflow. Listed as a gap. |
| MCP | Hand-written stdio JSON-RPC 2.0 subset: `initialize`, `ping`, `tools/list`, `tools/call`. Optional module. | The protocol subset is small. No SDK dependency, so the core stays dependency-free. |
| Dependencies | None added. `pyproject.toml` `dependencies` stays empty. | Brief section 10. |
| Threads | Single thread. Declared as `threads: 1` in the resource report. | Pure Python does not benefit from threads here; the GIL prevents it. Multiprocess sweeps are a later option. |
| Random seed | Recorded as `null` with reason `no stochastic component`. | The kernel is deterministic. A seed field is kept in the schema so that future stochastic models can use it. |
| Contact coefficients | Per contact entry (body, plane). The slice allows **one body**. All contacts of that body must share one friction and one restitution value, or the scene is rejected. | This is the honest limit of `step_sphere`. Per-pair coefficients for several bodies need a solver change, which is deferred. |
| Forces and torques | Gravity force is exact (m g). Contact force is **not reported** in this batch. | The solver does not expose impulses. Deriving a force from momentum change would be a finite-difference estimate and must be labelled as such. Reporting it now would fabricate a measurement. |

### 2.3 Unresolved decisions (needs user input)

1. **Mesh import format.** Brief item 5 asks for meshes. No mesh format has been chosen. Options: Wavefront OBJ (text, simple, stdlib-readable) or a glTF subset. Recommendation: OBJ, triangles only, with a face-count limit. Not implemented in this batch.
2. **Multi-body contact.** Needs a multi-body solver or a sequential-impulse loop over bodies. This is a larger change to `contact.py`. Not started.
3. **Atmosphere and environmental conditions.** Brief item 5 asks for atmospheric conditions. `hydrostatics.py` has pressure at depth but no atmosphere model. Not started.

## 3. Scope of this batch

Implemented in this batch (see `CLI_REFERENCE.md`, `API_REFERENCE.md`, `MCP_REFERENCE.md`, `SCENE_SCHEMA.md`,
`PREVIEW_SYSTEM.md`, `RESOURCE_LIMITS.md`, `AI_AGENT_GUIDE.md`, `AI_CAPABILITY_MATRIX.md` for the status of each
item):

- Operation registry shared by CLI, API and MCP.
- Scene schema v1: create, add sphere and plane, set body fields, set gravity, set contact, remove, validate, describe.
- Headless run of one sphere on planes, with checkpoint and resume, and friction sweeps.
- Inspection of one body and of a whole scene at one record, and of time series.
- PNG preview of one frame, with velocity and gravity arrows and the contact point. Numerical description returned
  with the image.
- Comparison of two runs. Export bundle (scene, run, preview, report).
- Validation cases SIM-01 and SIM-02 that run through the scene pipeline and check slide-to-roll time against an analytic
  result.

Not in this batch: meshes, multi-body contact, atmosphere, thermal and stress fields in the scene, GIF, scientific
plots, and the Rust core.
