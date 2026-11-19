# CHANGELOG - PROJECT REALITY

All notable changes to `reality/`. The format follows Keep a Changelog. Blender upstream changes are listed
separately in `ARCHITECTURE.md` §5 (none so far).

## [Unreleased]

### Added
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

### Corrected
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
