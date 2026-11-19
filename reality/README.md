# PROJECT REALITY - Universal Reality Simulation Engine (physics foundation)

PROJECT REALITY is an effort to build a scientifically grounded simulation layer on top of Blender, where objects,
materials and environments follow the physical laws that are computable, and where every number has a unit and a
source. Visual realism is not the criterion; validation against analytic and measured references is.

**Current state (v0.1.0 plus Phases 1-4 and first slices of 7-9):** a tested, dependency-free Python physics kernel with 76 validation cases, all passing,
an 18-material database, a physical object model (mass, centre of mass, inertia, heat capacity), a 3D rigid body with sphere-plane contact, Weibull failure statistics, hydrostatics, 2D conduction, and population benchmarks. It is **not yet integrated into Blender**, and it does not yet provide an editor,
fluids, fire, chemistry, biology, or spectral light. Read [`LIMITATIONS.md`](LIMITATIONS.md) before relying on any result.

## What is in this folder

| File | Purpose |
|---|---|
| [`SCIENCE_RESEARCH.md`](SCIENCE_RESEARCH.md) | Research across 7 disciplines: equations, properties, numerics, cost, open-source options, data, validation, status |
| [`ARCHITECTURE.md`](ARCHITECTURE.md) | Blender source inventory with real paths and licenses, reuse decisions, layered design, integration plan |
| [`PHYSICS_MODELS.md`](PHYSICS_MODELS.md) | Each implemented model with equations, assumptions, limits and validation IDs |
| [`MATERIAL_DATABASE.md`](MATERIAL_DATABASE.md) | Generated material table with sources and uncertainty |
| [`NUMERICAL_METHODS.md`](NUMERICAL_METHODS.md) | Integrators, stability limits, error orders, numerical lessons |
| [`VALIDATION_REPORT.md`](VALIDATION_REPORT.md) | Generated: every validation case with reference, measured error and status |
| [`PERFORMANCE_REPORT.md`](PERFORMANCE_REPORT.md) | Generated: baseline throughput of the kernels |
| [`THIRD_PARTY_LICENSES.md`](THIRD_PARTY_LICENSES.md) | Licenses of everything studied, used or considered |
| [`DEVELOPMENT_ROADMAP.md`](DEVELOPMENT_ROADMAP.md) | Phase-by-phase status and next steps |
| [`LIMITATIONS.md`](LIMITATIONS.md) | What is not modelled and where results are approximate |
| [`CHANGELOG.md`](CHANGELOG.md) | Release history |

## Layout

```
reality/
  src/reality/        physics kernel (units, constants, materials, gravity, integrators, mechanics,
                      rigidbody, contact, objects, weibull, hydrostatics, thermal, thermal2d,
                      optics, acoustics, fracture, structures, biology, validation)
  src/reality/control/ headless AI control layer: operations, CLI, Python API, MCP adapter, scene schema, preview
  tests/              pytest suite (unit tests and a registry test that asserts every validation case)
  tools/              run_validation.py, benchmark.py, export_materials.py (regenerate the reports)
  examples/           material_failure_table.py (glass vs steel under the same stress)
  pyproject.toml      package metadata; no runtime dependencies
```

## Quick start

Requires Python 3.10 or newer. No third-party packages are needed to run the kernel. pytest is only needed for the tests.

```bash
cd reality
python3 -m venv .venv && . .venv/bin/activate      # optional
pip install pytest                                  # tests only
python -m pytest                                    # all unit tests and validation cases

# From the repository root:
PYTHONPATH=reality/src python reality/tools/run_validation.py   # regenerates VALIDATION_REPORT.md
PYTHONPATH=reality/src python reality/tools/benchmark.py         # regenerates PERFORMANCE_REPORT.md
PYTHONPATH=reality/src python reality/tools/export_materials.py  # regenerates MATERIAL_DATABASE.md
PYTHONPATH=reality/src python reality/examples/material_failure_table.py
```

The repository `.gitignore` ignores `reality/.venv/`, so a virtualenv created inside `reality/` will not be committed.

## Example

```python
from reality.materials import default_database
from reality import fracture, units as U

db = default_database()
glass, steel = db.get("glass"), db.get("steel")

# Same 100 MPa stress, same 0.1 mm flaw:
print(fracture.assess(glass, 100e6, 0.1e-3).mode)   # 'fracture'  (sigma_c ~ 42 MPa)
print(fracture.assess(steel, 100e6, 0.1e-3).mode)   # 'none'      (sigma_y = 370 MPa)

# Dimension checking:
print(glass.q("fracture_toughness"))                # 750000 [M L^-1/2 T^-2]  (Pa*sqrt(m))
```

## Headless control (CLI, Python API, MCP)

One operation registry is exposed three ways. Start with `AI_CONTROL_ARCHITECTURE.md`, then `AI_AGENT_GUIDE.md`.

```bash
PYTHONPATH=src python -m reality.control info
PYTHONPATH=src python -m reality.control simulate run scene.json --duration 3 --out run.json
PYTHONPATH=src python -m reality.control mcp        # MCP over stdio (optional)
```

Reference: `CLI_REFERENCE.md`, `API_REFERENCE.md`, `MCP_REFERENCE.md`, `SCENE_SCHEMA.md`, `PREVIEW_SYSTEM.md`,
`RESOURCE_LIMITS.md`. What is and is not implemented: `AI_CAPABILITY_MATRIX.md`.

## Design principles

1. **SI units everywhere**, with dimension checks at API boundaries (`units.py`).
2. **Every constant and material value has a source** (`constants.py`, `materials.py`).
3. **Every solver has a validation case** that compares it with an analytic, textbook, or conservation reference.
4. **Accuracy/performance trade-offs are explicit** (step size, grid spacing, stability checks that raise errors).
5. **No claims beyond evidence.** Unvalidated domains are listed as not started.

## Relationship to the rest of this repository

This folder is separate from the QuoteCraft poster editor and the MiniCoder package in the repository root. The
Blender work will live in a separate upstream checkout plus an add-on. See `ARCHITECTURE.md`.
