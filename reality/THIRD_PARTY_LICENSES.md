# THIRD_PARTY_LICENSES - PROJECT REALITY

This file lists every third-party component that PROJECT REALITY studies, depends on, or may incorporate, with its
license as checked. It separates what is **used** from what is **only studied**.

## 1. Runtime dependencies of `reality/` (the Python kernel)

**None.** The `reality` package uses only the Python standard library (`math`, `dataclasses`, `fractions`, `typing`).
This is deliberate: the kernel must run inside Blender's bundled Python and in a plain interpreter without installs.

## 2. Development dependencies (not shipped)

| Component | Use | License | Notes |
|---|---|---|---|
| pytest | test runner | MIT | Installed into an external virtualenv (`/tmp/reality-venv`), not committed. |

## 3. Studied for the architecture (source inspected, nothing copied)

Blender was cloned for inspection only. **No Blender source is copied into this repository or modified.**
The license facts below were checked in the clone at commit `69f2f845e71836859f7e050095f10a4e6b8d5985`.

| Component | Where inspected | License (verified) | How it would be used later |
|---|---|---|---|
| Blender (core: rigid body, soft body, cloth, fluid wrapper, implicit solver, depsgraph, Python API) | `source/blender/**` | GPL-2.0-or-later (SPDX headers in `rigidbody.cc`, `softbody.cc`, `fluid.cc`, `implicit_eigen.cc`) | Host application for the Phase B integration. Any code that is linked into or derived from Blender's core must be GPL-2.0-or-later. |
| Bullet Physics 3 | `extern/bullet2/` (`README.blender`: "License: SPDX:Zlib") | Zlib | Blender's rigid-body backend, reused. |
| Mantaflow | `extern/mantaflow/LICENSE` (Apache License 2.0, "Copyright 2018, the mantaflow team"); `intern/mantaflow/CMakeLists.txt` (Blender wrapper, `GPL-2.0-or-later`) | Apache-2.0 (upstream), GPL-2.0-or-later (Blender wrapper) | Smoke and fire prototypes (Phase 7). |
| Cycles renderer kernels | `intern/cycles/kernel/types.h` | Apache-2.0 | Light transport reuse (Phase 5). |
| Taichi MPM (MLS-MPM reference, `yuanming-hu/taichi_mpm`) | web reference only, not cloned | MIT (per the project's README, cited in `SCIENCE_RESEARCH.md`) | Reference for the material-point method (Phase 4 / Phase 7). Not copied. |

## 4. Scientific data sources (cited, not copied)

Values in `reality/src/reality/materials.py` and `constants.py` are representative figures taken from the cited
handbooks or datasheets. Facts and measured constants are not copyrightable, but the source of each value is
recorded in the code so it can be audited. Where a web page was used, it is listed in `SCIENCE_RESEARCH.md`.

## 5. Components considered but not yet used

These were identified in the research and are **not** included. Each must be checked before inclusion.

| Component | Candidate use | License status |
|---|---|---|
| Eigen (linear algebra) | implicit solvers | Blender vendors Eigen through `intern/eigen`; upstream Eigen is MPL-2.0. Not checked in the clone. |
| OpenVDB | sparse volumes | Blender vendors it through `intern/openvdb`. Not checked in the clone. |
| Cantera, RDKit, OpenFOAM, Meep, OpenSees, Pinocchio, Pyroomacoustics, COPASI, OpenSim | references and possible back-ends | Not checked. Each is marked **[verify]** in `SCIENCE_RESEARCH.md`. |

## 6. Project license

No license file is present in this repository at the time of writing. The `reality/` code is original work written for
this project and does not copy any third-party source. A license must be chosen before any distribution. If the
engine is built into Blender, the combined work must follow Blender's GPL-2.0-or-later terms.
