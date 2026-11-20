# LIMITATIONS - PROJECT REALITY

This file lists what the current release does not do, and where its physics is only approximate. It is meant to
be read before relying on any result. The project rule is never to claim realism that has not been validated.

## 1. Scope of the current release (v0.1.0)

- **What exists:** a pure-Python, dependency-free physics kernel (`reality/src/reality/`) with 76 validation cases
  and a material database of 18 materials. Phases 2-4 and first slices of 7-9 are present (see `DEVELOPMENT_ROADMAP.md`).
- **What does not exist yet:**
  - No Blender integration. The Blender source was studied, but Blender is **not built or modified** (see `ARCHITECTURE.md` §4-6).
  - No GPU or multithreaded solver. The measured throughput is about 10^5 to 10^7 simple updates/s on a 2-core machine.
  - No editor, UI, inspectors, graphs, or visualisations.
  - No rendering. Light transport, spectral rendering and thin films are not implemented.
  - No fluids, fire or smoke solvers.
  - No chemistry (reactions, kinetics), no biology, no ecosystems.
  - No electromagnetic solver.
- Because of this, **PROJECT REALITY is not a game engine or a simulator yet**. It is the foundation layer.

## 2. Physical scope limits

| Topic | Limit |
|---|---|
| Gravity | Newtonian only. No general relativity. No J2 or other non-spherical terms. Spherical bodies only. |
| Relativity | Not modelled. Negligible at everyday speeds, but not accounted for at relativistic speeds. |
| Quantum mechanics | Not simulated. Quantum effects enter only through measured material constants. |
| Mechanics | Point masses, 1D collisions, and one 3D rigid body's rotation (`rigidbody.py`: torque-free and applied-torque cases). Multi-body: spheres only, sphere-sphere and sphere-plane contacts with one contact point each (`multibody.py`). No joints, no contact manifolds, no continuous collision detection (fast spheres can tunnel), no warm starting, so tall stacks drift. |
| Drag | Constant drag coefficient. No Reynolds-number dependence, no lift, no spin, no added mass. |
| Projectiles | No drag. |
| Pendulum | Single rigid pendulum, no damping, no driving. |
| Physical objects | Uniform-density solids only (sphere, box, cylinder). Centre of mass is the geometric centre. `objects.py` has no orientation state; the rigid-body solver (`rigidbody.py`) takes inertia as input and is not yet connected to `PhysicalObject`. No composite objects, no temperature-dependent properties, no anisotropy. |
| Contact | Sphere on infinite planes only, one contact point per step (`contact.py`), impulse-based with restitution and Coulomb friction. No contact manifolds, no stacking stability, no continuous collision detection (a fast body can tunnel through a thin obstacle), no shapes other than spheres. |
| Hydrostatics | Static fluids: pressure, buoyancy, floating fraction, apparent weight. No flow, no compressibility, no waves, no atmosphere. |
| Orbits | Two-body only (N-body superposition exists for gravity but no orbit integrator for many bodies). |
| Heat | Lumped, 1D, and explicit 2D on a uniform square with Dirichlet walls (`thermal2d.py`, Fo <= 1/4). No 3D, no convection correlations, no radiation exchange between surfaces (only a single-body emittance). |
| Phase change | Lumped energy balance only. No moving-boundary (Stefan) solver. No supercooling, no evaporation, no container heat loss. |
| Optics | Lossless dielectric interfaces only. No absorption, no scattering, no diffraction, no thin films. Dispersion only for BK7. |
| Acoustics | Linear, homogeneous media. No propagation solver, no reverberation, no sound generation from impacts yet. |
| Fracture | Single uniaxial flaw, linear-elastic. No crack growth, no fragmentation. Weibull statistics (`weibull.py`: failure probability, size effect, median-rank fit) are implemented, but no flaw-population data is stored or fitted to a real material. No dynamic fracture. |
| Ductile failure | First yield only. No hardening, plasticity, necking or fatigue. |
| Structures | Euler-Bernoulli beams and closed-form cantilever results. No plates, shells, torsion or buckling. |
| Elastomers | No hyperelastic model. Rubber uses a small-strain modulus only and is flagged as invalid beyond ~10 % strain. |
| Granular media | Sand and soil have bulk density and thermal properties only. No Mohr-Coulomb, no DEM. |
| Biology | Cortical bone is a population-average material. `biology.py` has only the logistic and Lotka-Volterra textbook models, used as numerical benchmarks. No organism, tissue, growth, or physiology model. |

## 3. Data limitations

- **Material values are representative handbook figures**, not certified measurements. Each material has a
  `source` and an `uncertainty` note. Several values (gold and silver yield strength, rubber modulus, sand and soil
  properties, wood as an isotropic approximation, ice fracture toughness) are indicative only.
- **Glass:** the `glass` row is **soda-lime** glass. Its K_Ic (0.75 MPa sqrt(m)), nu (0.20) and E (70-73 GPa, 72 used) are
  quoted from web references (see `SCIENCE_RESEARCH.md` §10). Tensile strength is flaw-limited, so the database value is a nominal
  practical figure. **Schott N-BK7** (E 82 GPa, nu 0.21) is a different glass. Its catalogue constants are kept in `constants.py`
  and are not used by the `glass` row.
- **Anisotropy:** wood and bone are orthotropic or anisotropic in reality. The database stores isotropic approximations.
- **Temperature dependence:** all properties are room-temperature values unless otherwise stated. Temperature-dependent
  properties are not yet supported in the solvers.
- **Friction and restitution** are not material properties in this model. They are coefficients of a contact pair,
  supplied by the caller to `contact.py`. No database of contact-pair coefficients exists yet.

## 4. Validation limitations

- **No experimental validation yet.** All 76 cases compare with analytic solutions, textbook constants, numerical
  references or conservation laws. Comparisons with laboratory data (drop tests, Hertz contact, glass fracture specimens, acoustic chambers) are
  planned but not done.
- **Some checks are identities.** A few `analytic` cases verify algebra (for example R + T = 1). They confirm the
  implementation of a formula, not that the formula describes a real system.
- **Input-data accuracy** is not validated. The tests check the code and the internal consistency of the
  database (physical ranges, dimensions), not that every input matches the real material.
- **Cross-solver coupling** (for example heat from metal to ice producing a fracture event) has no test yet.

## 5. Numerical limitations

- Explicit conduction requires Fo <= 1/2. The solver rejects larger steps instead of adjusting them.
- Verlet and RK4 use fixed steps. Close approaches in orbits and stiff contacts need smaller steps than are used here.
- Pure-Python floats; no extended precision. Results are double precision and deterministic for identical inputs.
- Performance is limited to small scenes (see `PERFORMANCE_REPORT.md`).
- Contact (`contact.py`) is a first-order predict-detect-resolve step. At dt = 1e-4 s the bounce apex is 1.3e-3 relative
  high (CON-01, tolerance 5e-3). The resting gap is O(g dt^2), about 1e-8 m. Both are discretisation errors, not
  penetration.
- Explicit 2D conduction (`thermal2d.py`) is second-order in space and first-order in time. Its error at N = 31 is
  1.1e-3 (THER-06).

### 5a. Blender add-on limits

- Blender 5.0.1 only, tested headlessly with the `bpy` module. The viewport panel and GL paths are not verified.
- Spheres only; no parenting of marked bodies; baking overwrites existing location and rotation keys of those bodies.
- Physics only. No gameplay systems. Blender's own rigid body world is not coordinated with the add-on.

## 6. Safety and use

- The fracture and failure criteria are **estimates for uniaxial, single-flaw loading**. They must not be used to
  decide structural safety for buildings, vehicles, pressure equipment or medical devices.
- The biological material data are population averages. They must not be used for any clinical or medical decision.

## 7. Known incorrect or approximate items (honest list)

- `materials.py` stores electrical conductivity as an SI dimension vector but does not use it in any solver yet.
- `mechanics.pendulum_period_numeric` uses a separate RK4 per step (correct, but slow for long simulations).
- `gravity.py` defaults the uniform field to standard gravity. This is a convenience value, not a claim that
  every lab has 9.80665 m/s^2 (the local value varies by about 0.5 % over Earth's surface).
- The Mars validation tolerance is 1 % because the model uses the mean radius, not the equatorial radius.
- The `CON-01` bounce tolerance (5e-3) is set by the discretisation error above. It is not a claim of model exactness.

## 8. Sources used in Phases 2-9 that are not yet in the verification ledger

The Phase 1 ledger (`SCIENCE_RESEARCH.md` §10) covers the sources cited there. The following are used by code in this
release but have **not** been checked against a primary source in this project. They must be added to the ledger, or
replaced, before the phase they support can be called Done:

- Bernard's median-rank approximation F = (i - 0.3)/(n + 0.4) (`weibull.py`).
- Baraff, "Analytical methods for dynamic simulation of non-penetrating rigid bodies", SIGGRAPH 1989, and Catto,
  "Iterative Dynamics with Temporal Coherence", GDC 2006 (`contact.py` impulse model).
- Rigid-body Euler equations and quaternion attitude update, standard mechanics textbooks (`rigidbody.py`).
- Hydrostatic pressure and Archimedes' principle, standard fluid-mechanics textbooks (`hydrostatics.py`).
- Explicit FTCS stability limit Fo <= 1/4 in 2D (von Neumann analysis; `thermal2d.py`).
- Verhulst logistic equation and Lotka-Volterra first integral (`biology.py`).

The formulas are standard. The citations, however, are not yet checked in this project, so they are not claimed as
verified.

