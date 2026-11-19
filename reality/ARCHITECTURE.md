# ARCHITECTURE - PROJECT REALITY

Status: **architecture v0.1**. The Python kernel is implemented and validated. The Blender
integration is designed here, with real Blender source paths, but **not yet built or modified**.

## 1. Phase 0: Blender source acquisition and inventory

### 1.1 What was cloned, and how

| Item | Value |
|---|---|
| Upstream | `blender/blender` on GitHub (the official mirror of `projects.blender.org/blender/blender`) |
| Commit inspected | `69f2f845e71836859f7e050095f10a4e6b8d5985` (`Fix #166213 : glTF Fix no UVMap export`) |
| Clone | `git clone --depth 1 --single-branch https://github.com/blender/blender.git` |
| Size | 446 MB on disk including an 87 MB shallow `.git`; 20,962 files outside `.git` (measured in Phase 1 at this commit) |
| Location | `/tmp/blender-src` (outside this repository, deliberately) |

Notes:

- The sandbox only allows outbound access to `github.com`, `codeload.github.com`, `api.github.com`,
  `registry.npmjs.org`, `pypi.org` and `files.pythonhosted.org`. `projects.blender.org` is not on that list,
  so the GitHub mirror was used. It is the same tree.
- The clone is **not** committed to this repository. Vendoring 446 MB of GPL source into the repo would break the
  artifact budget, and it is not needed to reference the code. Blender's git submodules (`lib/`, the precompiled
  libraries) were not fetched; building Blender needs them, see §6.
- The source is re-creatable with the command above. Every path below was checked against that commit.

### 1.2 License facts (verified in the clone)

| Component | Path | License (SPDX header or file) |
|---|---|---|
| Blender core (rigid body, soft body, fluid wrapper, implicit solver) | `source/blender/blenkernel/intern/*.cc`, `source/blender/simulation/intern/` | `GPL-2.0-or-later` |
| Bullet 3 (rigid-body backend) | `extern/bullet2/` (`README.blender`: "License: SPDX:Zlib") | Zlib |
| Mantaflow (fluid solver) | `extern/mantaflow/LICENSE`, `intern/mantaflow/` | Apache-2.0 (upstream LICENSE); the Blender wrapper `intern/mantaflow/CMakeLists.txt` is `GPL-2.0-or-later` |
| Cycles kernel | `intern/cycles/kernel/types.h` | `Apache-2.0` |

Consequence: any code that is **linked into or derived from** Blender's GPL core must be GPL-2.0-or-later. The
`reality` Python package here is written from first principles and does not include Blender code, so its license
is independent; see `THIRD_PARTY_LICENSES.md`.

## 2. Blender's physics and simulation architecture (what exists)

### 2.1 Subsystem inventory

| Area | Real location in the clone | What it does | Reuse decision |
|---|---|---|---|
| Rigid bodies | `source/blender/blenkernel/intern/rigidbody.cc`, `intern/rigidbody/rb_bullet_api.cpp` | Builds a Bullet `btDiscreteDynamicsWorld` via `RB_dworld_new(scene->physics_settings.gravity)`; sequential-impulse solver | **Reuse** as the baseline rigid-body backend. Add continuous collision and a material-driven contact model at the boundary |
| Soft bodies | `source/blender/blenkernel/intern/softbody.cc` | Mass-spring soft bodies | **Reuse**; add a proper elastic model later |
| Cloth | `source/blender/blenkernel/intern/cloth.cc`, `source/blender/simulation/SIM_mass_spring.h`, `simulation/intern/implicit_eigen.cc`, `implicit_blender.cc`, `ConstrainedConjugateGradient.h` | Implicit mass-spring cloth (Baraff & Witkin style) with Eigen | **Reuse** as the implicit-solver reference; material stiffness must come from the physical material model |
| Fluids (legacy) | `source/blender/blenkernel/intern/fluid.cc`, `intern/mantaflow/intern/manta_fluid_API.cpp`, `extern/mantaflow/` | Eulerian smoke/liquid via Mantaflow (Python-scriptable C++ solver) | **Reuse** for smoke/fire prototypes (Phase 7); needs physical combustion and buoyancy models |
| Particles | `source/blender/blenkernel/intern/particle_system.cc`, `particle.cc`, `particle_distribute.cc` | Hair and emitter particle systems | Reuse for emission; physics-driven particles need a new solver |
| Dynamic paint | `source/blender/blenkernel/intern/dynamicpaint.cc` | Surface-based paint and wetness simulation | Candidate for surface-thermal/moisture coupling |
| Point cache | `source/blender/blenkernel/intern/pointcache.cc` | Frame-cached simulation state on disk | Reuse for deterministic replay (Phase 11) |
| Geometry sets | `source/blender/blenkernel/intern/geometry_set.cc`, `geometry_component_mesh.cc`, `geometry_component_volume.cc`, `volume_grid.cc` | Typed geometry containers used by Geometry Nodes | Carrier for per-point physical attributes (mass, temperature, stress) |
| Geometry Nodes simulation / bake | `source/blender/nodes/geometry/nodes/node_geo_simulation.cc`, `node_geo_bake.cc`; `source/blender/blenkernel/intern/bake_geometry_nodes_modifier.cc` | Simulation zones and baking | Reuse as the time-stepping host for custom solvers |
| Mesh/BVH | `source/blender/blenkernel/intern/bvh.cc`, `bvhutils.cc`, `pbvh.cc` | BVH acceleration for ray casts and collision queries | Reuse for broad-phase queries |
| Depsgraph | `source/blender/depsgraph/intern/` (`DEG_depsgraph.hh`, `DEG_depsgraph_physics.hh`) | Dependency graph that schedules evaluation | Host the new solvers as depsgraph physics nodes |
| Scene gravity | `source/blender/makesdna/DNA_scene_types.h` (`PhysicsSettings`: `float gravity[3] = {0, 0, -9.81}`) | One global gravity vector per scene | **Replace** with a gravity-field model (`reality.gravity`): uniform, point-mass, N-body |
| Units | `source/blender/blenkernel/intern/unit.cc`, `scale_length` in `DNA_scene_types.h` | Display-unit system and length scale | Reuse display; physics must work in SI internally |
| Cycles (path tracer) | `intern/cycles/kernel/integrator/`, `intern/cycles/kernel/closure/` (`bsdf_*.h`, `volume_henyey_greenstein.h`, `volume_rayleigh.h`), `intern/cycles/device/{cpu,cuda,hip,metal,optix,oneapi,hiprt}` | Physically based path tracing with multiple device backends, MNEE caustics (`integrator/mnee.h`) | Reuse for light transport (Phase 5). The kernels are RGB-based, and no spectral transport pipeline was identified in this pass |
| EEVEE / draw | `source/blender/draw/engines/eevee/`, `source/blender/draw/` | Real-time rasterization renderer | Reuse for interactive preview |
| GPU abstraction | `source/blender/gpu/` (`GPU_compute.hh`, `GPU_ray_tracing.hh`, `GPU_shader.hh`) | Vulkan/Metal/OpenGL abstraction with compute | Target for GPU solver kernels (Phase 11) |
| Threads / tasks | `source/blender/blenlib/BLI_task.hh` | Task-parallel loops | Target for CPU multithreading |
| Python API | `source/blender/python/` (`bpy*.cc`), `scripts/startup/bl_ui/properties_physics_*.py` | `bpy` module and physics UI panels (rigid body, cloth, soft body, fluid, dynamic paint, geometry-nodes physics) | Host for the editor UI and inspectors (Phase 12) |
| DNA / RNA | `source/blender/makesdna/`, `source/blender/makesrna/` | Data model and Python property generation | Add `PhysicalMaterial` and solver settings through DNA/RNA |
| Tests | `tests/python/` (337 files), `source/blender/blenkernel/intern/*_test.cc`, `intern/cycles/test/` | Python and C++ regression tests | Model for `reality/tests` and in-Blender tests |
| Animation | `source/blender/animrig/`, `source/blender/blenkernel/intern/anim_sys.cc`, `action.cc`, `nla.cc` | Keyframes, drivers, NLA | Reuse for scripted environmental changes |

### 2.2 Architectural facts that drive the design

1. **Physics is a set of independent solvers attached to the depsgraph.** There is no single unified solver. Each
   subsystem owns its state and cache. Cross-system coupling (heat to fracture to sound, Phase 10) therefore needs
   an explicit coupling layer. It cannot be assumed to emerge.
2. **Gravity is global and hard-coded in DNA** (`PhysicsSettings.gravity`). A universal engine needs position-dependent
   and multi-body gravity, so the field must become a replaceable object.
3. **Material in Blender is a shading description** (node tree, BSDF parameters). It has no density, elastic
   modulus, toughness or thermal properties. The physical material layer (`reality.materials`) must be added beside
   it, not merged into the shader nodes.
4. **Cycles is an RGB path tracer** on the kernels inspected. Spectral and wavelength-dependent transport (Phase 5)
   is a substantial addition and is not started.
5. **Rigid-body contact uses Bullet's discrete solver** with a sequential-impulse constraint solver. Continuous
   collision detection (for fast glass shards) is a planned extension.

## 3. Target architecture (layers)

```
 +--------------------------------------------------------------------------+
 |  Editor / UI  (Blender Python: bl_ui panels, inspectors, graphs)          |  Phase 12
 +--------------------------------------------------------------------------+
 |  Coupling & scheduler (interaction graph, fidelity levels, determinism)   |  Phase 10/11
 +------------+-----------+-----------+-----------+-----------+-------------+
 | Mechanics  | Fracture  | Thermal   | Optics    | Acoustics | Fluids/Fire |  Phase 3-8
 +------------+-----------+-----------+-----------+-----------+-------------+
 |  Physical object model: materials, geometry, gravity field, units (SI)    |  Phase 2/3  <-- reality/ (implemented)
 +--------------------------------------------------------------------------+
 |  Numerics: integrators, FD/FV, linear solvers, root finding, dim. algebra |  reality/ (implemented, Python)
 +--------------------------------------------------------------------------+
 |  Blender host: depsgraph, DNA/RNA, Cycles, EEVEE, GPU, BLI tasks, bake    |  upstream Blender (reused)
 +--------------------------------------------------------------------------+
```

### 3.1 What is implemented now (`reality/src/reality/`)

| Module | Layer | Role |
|---|---|---|
| `units.py` | Numerics / object model | SI dimension vectors with rational exponents; dimension-checked `Q` type |
| `constants.py` | Object model | Constants with provenance (CODATA 2018, IAU/IERS, US Standard Atmosphere) |
| `materials.py` | Object model | `Material` with physical validation, `MaterialDatabase`, 18 built-in materials |
| `objects.py` | Object model | `PhysicalObject` (sphere, box, cylinder): mass, centre of mass, principal and parallel-axis inertia, weight, kinetic energy, heat capacity, melting state |
| `gravity.py` | Object model | `UniformGravity`, `GravityBody`, `PointMassGravity`, planetary presets |
| `integrators.py` | Numerics | RK4 and velocity Verlet |
| `mechanics.py` | Mechanics | Free fall with drag, projectile, pendulum (exact elliptic period), 1D collisions with restitution, Kepler orbits |
| `thermal.py` | Thermal | Lumped capacitance, explicit 1D conduction with stability check, metal-on-ice energy balance, radiation |
| `optics.py` | Optics | Snell, critical and Brewster angles, Fresnel, BK7 Sellmeier dispersion |
| `acoustics.py` | Acoustics | Wave speed, impedance, reflection and transmission, Doppler, resonances, SPL |
| `fracture.py` | Failure | LEFM (K_I, critical flaw, Griffith energy) for brittle solids, yield for ductile metals, `assess()` |
| `structures.py` | Structures | Euler-Bernoulli cantilever: deflection, root stress, first natural frequency |
| `validation.py` | Validation | 45 cases with references, tolerances and sources |

### 3.2 Interfaces between layers

- **Materials to solvers:** solvers take raw SI floats or `Q` quantities. Public APIs that receive a `Material`
  read the properties through `Material.q(name)`, which checks dimension and presence.
- **Gravity to mechanics:** every mechanics solver takes an acceleration callable, so `UniformGravity`,
  `PointMassGravity` and any future field are interchangeable.
- **Solver to solver (Phase 10):** planned as a coupling graph whose edges carry physical quantities
  (for example, a fracture solver publishes fragment kinetic energy and fracture surface area to the acoustics
  and thermal solvers). Not yet implemented.

## 4. Integration plan into Blender (planned, not started)

Blender integration needs a full build of Blender with its `lib/` precompiled libraries, which were not available
in this sandbox. The plan is staged so that each step can be built and tested alone:

1. **Phase B1, Python add-on:** an add-on in a new directory that imports `reality`, creates `PhysicalMaterial`
   objects as Blender ID-less settings stored in object custom properties, and runs the validation suite from
   Blender's Python console. No engine change, so no full build is needed. (Feasible with a stock Blender 4.x
   or 5.x install.)
2. **Phase B2, C++ port of the hot kernels:** `reality` kernels (integrators, conduction stencil, collision
   broad-phase) ported to C++ under `source/blender/blenkernel/intern/reality_*.cc` with the same unit tests.
   Each port is compared against the Python reference using the validation cases.
3. **Phase B3, DNA/RNA:** `PhysicalMaterial` and solver settings as DNA structs (`makesdna`) with RNA properties
   (`makesrna`), so they save in `.blend` files and appear in Python and the UI.
4. **Phase B4, depsgraph solver node:** a physics node that steps the coupling graph, using the point cache
   (`pointcache.cc`) for deterministic replay.
5. **Phase B5, GPU:** compute kernels through `GPU_compute.hh` for large fields.

Blender's build configuration lives in the clone's `build_files/` directory and its `README.md`; the precompiled
libraries come from the `lib/` submodules. Those are the starting points for the later build step.

## 5. Upstream modification record

| Date | Area | Change | Upstream file touched | Status |
|---|---|---|---|---|
| 2026-11-19 | none | No change to Blender source. Blender was studied only; the clone is not in this repository | none | - |

When Blender source is first modified, each change must be listed here with the upstream file, the reason, and the
commit that introduced it, so that upstream merges stay manageable.

## 6. Build and toolchain

| Need | Status in this sandbox |
|---|---|
| Python 3.11 | Available (used for `reality`) |
| pytest | Installed in an external virtualenv (`/tmp/reality-venv`), not in the repo |
| Blender source | Shallow clone at `/tmp/blender-src` (not persisted) |
| Blender build (CMake, compilers, `lib/` submodules, OpenVDB, OpenSubdiv, etc.) | **Not attempted.** Needs a larger machine (Blender's own docs recommend substantial RAM and disk for a build) and the `lib/` submodules |

## 7. Design rules carried forward

1. Preserve Blender's behaviour: new systems are added beside existing ones, and existing defaults stay unchanged.
2. No physical quantity without a unit. Every public API either takes `Q` or documents SI units.
3. Every solver has a validation case in `reality/src/reality/validation.py` before it is called validated.
4. Accuracy/performance trade-offs are explicit parameters (step size, grid spacing, fidelity level). Nothing
   is silently reduced.
