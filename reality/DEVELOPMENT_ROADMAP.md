# DEVELOPMENT_ROADMAP - PROJECT REALITY

Phases follow the PROJECT REALITY brief (Phases 0-15). Each entry gives a status, the evidence for it, and the
next concrete step. Status words are used strictly:

- **Done** - implemented and covered by tests and validation cases, with every named gap closed.
- **Partial** - some of the phase exists and is tested; named gaps remain.
- **Not started** - no implementation in the repository.

Priority follows the brief's rule: working, validated systems before broad but incomplete features.

## Status by phase

| Phase | Title | Status | Evidence | Next step |
|---|---|---|---|---|
| 0 | Source acquisition and Blender inventory | **Done** (inventory); build **not started** | `ARCHITECTURE.md` §1-2 with real paths and licenses | Build Blender on a larger machine with `lib/` submodules |
| 1 | Scientific research | **Partial** (downgraded from Done) | `SCIENCE_RESEARCH.md`: 7 disciplines; every `[verify]` marker resolved against a primary or reputable source; §10 ledger has **38 entries**; gate `tests/test_research_gate.py` (includes a ledger-count test). Licences checked for the components in `THIRD_PARTY_LICENSES.md` §5.1. | Close `THIRD_PARTY_LICENSES.md` §5.2: confirm the licence of the Blender-vendored OpenVDB (`intern/openvdb`) and Eigen (`intern/eigen`). Add the sources listed in `LIMITATIONS.md` §8 to the ledger |
| 2 | Universal physical object system | **Partial** | `objects.py` (`PhysicalObject`: sphere, box, cylinder; mass, centre of mass, principal and parallel-axis inertia, weight, kinetic energy, heat capacity, melting state); OBJ-01..08; `tests/test_objects.py` (20 tests) and `tests/test_physical_object_api.py` (17 tests). Also `materials.py` (18 materials) and `units.py` (SI dimensions, `MOMENT_OF_INERTIA`) | Connect `PhysicalObject` to the rigid-body state (`rigidbody.py`) so that objects carry orientation. Then: composite objects, non-uniform density, temperature-dependent properties, anisotropy (wood, bone) |
| 3 | Real gravity and mechanics | **Partial** | `gravity.py` (uniform, point-mass, N-body superposition, planets); `mechanics.py`; `rigidbody.py` (single 3D body: quaternion attitude, Euler equations, RK4); `contact.py` (sphere on planes: restitution, Coulomb friction, rolling); MECH-01..15, GRAV-01..04, RB-01..05, CON-01..07; `tests/test_rigidbody_contact.py` | Multi-body contact and stacking, contact manifolds, continuous collision detection, joints, non-spherical contact shapes, deformable bodies |
| 4 | Real material destruction | **Partial** | `fracture.py` (LEFM, Griffith, yield); `weibull.py` (failure probability, size effect, effective volume, median-rank fit); FRAC-01..04, WEIB-01..05; `tests/test_phases_4_7_8_9.py` | Crack propagation, fragmentation, fatigue (Paris law), stress fields over a body, and fitting Weibull parameters to measured flaw data (none stored yet) |
| 5 | Real optics and light | **Partial** | `optics.py` (Snell, Fresnel, Brewster, BK7 dispersion); OPT-01..06 | Complex refractive index (absorption), thin film, spectral transport in Cycles |
| 6 | Real sound and acoustics | **Partial** | `acoustics.py` (impedance, reflection, Doppler, resonance); ACOU-01..06 | Impact-sound synthesis from modal analysis; propagation (FDTD) |
| 7 | Fluids, fire and atmosphere | **Partial** | `hydrostatics.py` (pressure at depth, buoyant force, floating fraction, apparent weight); HYD-01..03 | Fluid flow (Mantaflow integration, not started), atmosphere, fire |
| 8 | Heat and thermodynamics | **Partial** | `thermal.py` (lumped, 1D conduction, metal-on-ice energy balance, radiation); `thermal2d.py` (explicit 2D conduction, Dirichlet walls); THER-01..06 | 3D conduction, convection coefficient correlations, moving-boundary melting, evaporation, implicit solver |
| 9 | Biological and living systems | **Partial** (benchmarks only) | `biology.py`: logistic growth and Lotka-Volterra with an exact first integral, used as numerical benchmarks; BIO-01..02. No biological system is modelled. | Validated tissue or organism models, each with data and a validation case. The brief forbids claiming realism before then |
| 10 | Universal interaction system | **Not started** | Interface design in `ARCHITECTURE.md` §3.2 | Coupling graph: fracture → fragment kinetic energy → acoustics and thermal |
| 11 | Performance and architecture | **Partial** | `PERFORMANCE_REPORT.md` (pure-Python baseline); deterministic kernels | C++ ports of hot kernels, SIMD, GPU compute via `GPU_compute.hh`, adaptive time steps |
| 12 | User experience and editor | **Not started** | Planned as Blender Python add-on panels (`bl_ui`) | Material inspector and gravity panel as a first add-on |
| 13 | Scientific validation | **Partial** | `VALIDATION_REPORT.md`, **76 cases**, all passing; `validation.py` registry | Experimental datasets (drop tests, Hertz contact, glass fracture, sound chamber); cross-solver tests |
| 14 | Development rules | **Ongoing** | Units enforced; sources recorded per material and constant; limitations listed; `LIMITATIONS.md` §8 lists sources not yet in the ledger | Keep enforcing; add a reviewer checklist |
| 15 | Execution strategy | **Partial** | Steps A, B, C, D, E, F, G, H done; step I partly; M done for the kernel | Continue with I (cross-domain coupling), J (interactions), K (editor), L (GPU) |

## Milestones

### M-1: Foundation kernel (v0.1.0) - **Done**
- Units and dimensions, material model, gravity, mechanics, thermal, optics, acoustics, fracture, beams.
- 45 validation cases at v0.1.0, all passing. Generated reports: `VALIDATION_REPORT.md`, `PERFORMANCE_REPORT.md`, `MATERIAL_DATABASE.md`.

### M-1.1: Phases 1-4 and first slices of 7-9 (unreleased) - **Partial**
- Phase 1 status corrected to Partial (see the table): the ledger has 38 entries, and §5.2 licence items remain open.
- Phase 2 first slice: `objects.py`, OBJ-01..08.
- Phase 3: `rigidbody.py` and `contact.py`, RB-01..05 and CON-01..07.
- Phase 4: `weibull.py`, WEIB-01..05.
- Phase 7 first slice: `hydrostatics.py`, HYD-01..03.
- Phase 8: `thermal2d.py`, THER-06.
- Phase 9 benchmarks: `biology.py`, BIO-01..02.
- **76 validation cases, 0 failing.** Pytest: 248 tests, which are the 76 validation cases, 2 registry structural tests,
  7 research-gate tests, and 163 unit and regression tests (counted by `pytest --collect-only`).

### M0: Blender-hosted prototype - **Not started**
- Python add-on (no engine change) that loads `reality` and exposes material and gravity settings.
- Requires a working Blender installation. Blender itself is not built here.

### M1: Coupled demonstrator - **Not started**
- Scenario: a glass object dropped onto concrete. Impact speed from free fall with drag (M2a), contact energy from
  restitution (CON-01, M2d), fracture decision from LEFM (M6a) with a flaw population (`weibull.py`), sound from the
  impact (M5), heat from a hot object landing on ice (M3c). Each link needs a validation case first. The contact link
  is sphere-only, so a glass block cannot yet be represented.

### M2: Experimental validation - **Not started**
- Compare with published drop-test, Hertz-contact and glass-fracture data. Record measured error against each dataset.

### M3: Performance - **Not started**
- C++ ports of the kernels, multithreading via `BLI_task`, GPU compute for conduction and particle updates.

## Open research questions (tracked)

1. Which contact model gives stable stacking with restitution and friction at Blender-scale time steps. A single-point
   sequential-impulse sphere-plane model is implemented; stacking stability with several contacts is open.
2. How to pick the flaw population for a real glass object (measurement or a Weibull fit). `weibull.py` fits a
   distribution, but no measured data is in the repository yet.
3. Whether Cycles' RGB transport is sufficient for dispersion-driven effects, or whether a spectral extension is required.
4. How to couple solvers with different time steps without losing energy (sub-stepping and conservation checks).
