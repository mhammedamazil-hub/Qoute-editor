# CHANGELOG - PROJECT REALITY

All notable changes to `reality/`. The format follows Keep a Changelog. Blender upstream changes are listed
separately in `ARCHITECTURE.md` §5 (none so far).

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
  registry test that asserts every validation case (121 tests: 76 unit and regression tests plus 45 parametrised validation cases).
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
