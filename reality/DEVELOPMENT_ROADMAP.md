# DEVELOPMENT_ROADMAP - PROJECT REALITY

Phases follow the PROJECT REALITY brief (Phases 0-15). Each entry gives a status, the evidence for it, and the
next concrete step. Status words are used strictly:

- **Done** - implemented and covered by tests and validation cases.
- **Partial** - some of the phase exists and is tested; named gaps remain.
- **Not started** - no implementation in the repository.

Priority follows the brief's rule: working, validated systems before broad but incomplete features.

## Status by phase

| Phase | Title | Status | Evidence | Next step |
|---|---|---|---|---|
| 0 | Source acquisition and Blender inventory | **Done** (inventory); build **not started** | `ARCHITECTURE.md` §1-2 with real paths and licenses | Build Blender on a larger machine with `lib/` submodules |
| 1 | Scientific research | **Partial** | `SCIENCE_RESEARCH.md`, 7 disciplines, 20 references; several items marked **[verify]** | Verify all **[verify]** items against primary sources; add DOIs |
| 2 | Universal physical object system | **Partial** | `materials.py` (18 materials, validation, custom materials), `units.py` (SI dimensions); tests in `test_materials.py`, `test_units.py` | Add rigid-body inertia, centre of mass, temperature state per object; anisotropy; temperature-dependent properties |
| 3 | Real gravity and mechanics | **Partial** | `gravity.py` (uniform, point-mass, N-body superposition, planets); `mechanics.py`; MECH-01..15, GRAV-01..04 | 3D rigid-body rotation, contact with friction, CCD, joints, deformable bodies |
| 4 | Real material destruction | **Partial** | `fracture.py` (LEFM, Griffith, yield); FRAC-01..04 | Crack propagation, fragmentation, fatigue (Paris law), stress propagation in a body |
| 5 | Real optics and light | **Partial** | `optics.py` (Snell, Fresnel, Brewster, BK7 dispersion); OPT-01..06 | Complex refractive index (absorption), thin film, spectral transport in Cycles |
| 6 | Real sound and acoustics | **Partial** | `acoustics.py` (impedance, reflection, Doppler, resonance); ACOU-01..06 | Impact-sound synthesis from modal analysis; propagation (FDTD) |
| 7 | Fluids, fire and atmosphere | **Not started** | Mantaflow is identified as a reuse candidate (`ARCHITECTURE.md` §2) | Hydrostatic pressure and buoyancy first, then Mantaflow integration |
| 8 | Heat and thermodynamics | **Partial** | `thermal.py` (lumped, 1D conduction, metal-on-ice energy balance, radiation); THER-01..05 | 2D/3D conduction, convection coefficient correlations, moving-boundary melting, evaporation |
| 9 | Biological and living systems | **Not started** | Roadmap only; the brief forbids claiming realism without validated models | Start with a validated population model (logistic, Lotka-Volterra) as a benchmark |
| 10 | Universal interaction system | **Not started** | Interface design in `ARCHITECTURE.md` §3.2 | Coupling graph: fracture → fragment kinetic energy → acoustics and thermal |
| 11 | Performance and architecture | **Partial** | `PERFORMANCE_REPORT.md` (pure-Python baseline); deterministic kernels | C++ ports of hot kernels, SIMD, GPU compute via `GPU_compute.hh`, adaptive time steps |
| 12 | User experience and editor | **Not started** | Planned as Blender Python add-on panels (`bl_ui`) | Material inspector and gravity panel as a first add-on |
| 13 | Scientific validation | **Partial** | `VALIDATION_REPORT.md`, 45 cases, all passing; `validation.py` registry | Experimental datasets (drop tests, Hertz contact, glass fracture, sound chamber); cross-solver tests |
| 14 | Development rules | **Ongoing** | Units enforced; sources recorded per material and constant; limitations listed | Keep enforcing; add a reviewer checklist |
| 15 | Execution strategy | **Partial** | Steps A, B, C, D, E, F, G, H done; step I partly; M done for the kernel | Continue with I (cross-domain coupling), J (interactions), K (editor), L (GPU) |

## Milestones

### M-1: Foundation kernel (this release, v0.1.0) - **Done**
- Units and dimensions, material model, gravity, mechanics, thermal, optics, acoustics, fracture, beams.
- 45 validation cases, 0 failing; 121 pytest tests in total (76 unit and regression tests plus the 45 validation cases).
- Generated reports: `VALIDATION_REPORT.md`, `PERFORMANCE_REPORT.md`, `MATERIAL_DATABASE.md`.

### M0: Blender-hosted prototype - **Not started**
- Python add-on (no engine change) that loads `reality` and exposes material and gravity settings.
- Requires a working Blender installation. Blender itself is not built here.

### M1: Coupled demonstrator - **Not started**
- Scenario: a glass object dropped onto concrete. Impact speed from free fall with drag (M2a), contact energy from
  restitution (M2d), fracture decision from LEFM (M6a) with a flaw population, sound from the impact (M5), heat from
  a hot object landing on ice (M3c). Each link needs a validation case first.

### M2: Experimental validation - **Not started**
- Compare with published drop-test, Hertz-contact and glass-fracture data. Record measured error against each dataset.

### M3: Performance - **Not started**
- C++ ports of the kernels, multithreading via `BLI_task`, GPU compute for conduction and particle updates.

## Open research questions (tracked)

1. Which contact model gives stable stacking with restitution and friction at Blender-scale time steps (sequential
   impulses versus projected Gauss-Seidel with warm starting)?
2. How to pick the flaw population for a real glass object (measurement or a Weibull fit).
3. Whether Cycles' RGB transport is sufficient for dispersion-driven effects, or whether a spectral extension is required.
4. How to couple solvers with different time steps without losing energy (sub-stepping and conservation checks).
