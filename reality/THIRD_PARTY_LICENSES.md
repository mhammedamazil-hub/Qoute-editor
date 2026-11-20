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
| Mantaflow | `extern/mantaflow/LICENSE` (Apache License 2.0, "Copyright 2018, the mantaflow team"); the Blender wrapper `intern/mantaflow/CMakeLists.txt` carries `SPDX-License-Identifier: GPL-2.0-or-later` | Apache-2.0 (upstream core); GPL-2.0-or-later (Blender wrapper) | Smoke and fire prototypes (Phase 7). |
| Cycles renderer kernels | `intern/cycles/kernel/types.h` | Apache-2.0 | Light transport reuse (Phase 5). |
| Taichi MPM (MLS-MPM reference, `yuanming-hu/taichi_mpm`) | web reference only, not cloned | MIT (LICENSE file in the repository, checked in Phase 1) | Reference for the material-point method (Phase 4 / Phase 7). Not copied. |

## 4. Scientific data sources (cited, not copied)

Values in `reality/src/reality/materials.py` and `constants.py` are representative figures taken from the cited
handbooks or datasheets. Facts and measured constants are not copyrightable, but the source of each value is
recorded in the code so it can be audited. Where a web page was used, it is listed in `SCIENCE_RESEARCH.md`.

## 5. Components considered but not yet used

These were identified in the research (`SCIENCE_RESEARCH.md`) and are **not** included in this repository. Licenses were checked against the sources listed in `SCIENCE_RESEARCH.md` §10 during Phase 1. A component may only be added after its licence is compatible with the project's licence (§6), and the addition is recorded here.

### 5.1 Verified licences

| Component | Candidate use | Licence (verified) | Source checked | Compatibility note |
|---|---|---|---|---|
| Blender Python module `bpy` 5.0.1 (PyPI wheel) | Headless smoke test only (`tools/blender_smoke.py`); not bundled | GPL-3.0 (wheel `METADATA`); Blender core source headers say GPL-2.0-or-later (§5.2). The two differ. | pypi.org wheel METADATA | Copyleft. Check before distributing any add-on that imports `bpy`. |
| Meep | FDTD electromagnetics and optics reference | GPL-2.0 | github.com/NanoComp/meep | Copyleft; linking would make the combined work GPL-2.0 |
| OpenFOAM | CFD and conjugate heat transfer | GPL-3.0 | openfoam.org; github.com/openfoam/openfoam-dev | Copyleft; use only as an external process |
| FEniCS dolfinx | FEM for heat, phase change, fracture | LGPL-3.0 with GPL-3.0 components (COPYING.LESSER, COPYING) | github.com/FEniCS/dolfinx | LGPL allows linking; GPL components apply to some files. Check per file before use |
| pyroomacoustics | Room acoustics and beamforming reference | MIT | github.com/LCAV/pyroomacoustics | Permissive |
| Cantera | Thermochemistry and kinetics | BSD-3-Clause | github.com/Cantera/cantera; anaconda.org/Cantera/cantera | Permissive |
| RDKit | Cheminformatics | BSD-3-Clause | github.com/rdkit/rdkit | Permissive |
| COPASI | Biochemical network simulation | Artistic-2.0 (copasi.org). The Fedora package metadata lists Artistic-2.0 AND GPL-3.0-or-later AND BSD-3-Clause | copasi.org; packages.fedoraproject.org | Licence depends on packaging; read each release's own licence |
| NEURON | Biophysical neuron models | BSD-3-Clause | github.com/neuronsimulator/nrn | Permissive |
| OpenSim | Musculoskeletal dynamics reference | Apache-2.0 | github.com/opensim-org/opensim-core | Permissive |
| Project Chrono | Multibody and deformable dynamics | BSD-3-Clause | github.com/projectchrono/chrono | Permissive |
| OpenSees | Structural and geotechnical FEM | University of California licence: non-commercial educational, research and non-profit use; commercial use needs permission | casrai.org/guides/opensees; opensees.berkeley.edu | **Not open source.** Must not be bundled in a commercial product |
| MuJoCo | Articulated-body physics reference | Apache-2.0 | github.com/google-deepmind/mujoco | Permissive |
| Pinocchio | Rigid-body algorithms with analytic derivatives | BSD-2-Clause | github.com/stack-of-tasks/pinocchio | Permissive |
| Box2D | 2D physics engine reference | MIT | github.com/erincatto/box2d | Permissive |
| ngspice | Circuit simulation | BSD-3-Clause | ngspice.sourceforge.io; en.wikipedia.org/wiki/Ngspice | Permissive |
| SU2 | CFD and multiphysics | LGPL-2.1 | github.com/su2code/su2 | LGPL; linking allowed under its terms |
| Palabos | Lattice Boltzmann CFD | AGPL-3.0 | github.com/omalaspinas/palabos; cfdflow.com | **Network copyleft.** A hosted service using it must offer source |
| pbrt-v4 | Spectral physically based rendering reference | Apache-2.0 | github.com/mmp/pbrt-v4 | Permissive |
| Taichi MPM (MLS-MPM reference solver) | Material point method | MIT | github.com/yuanming-hu/taichi_mpm (LICENSE file) | Permissive |
| Eigen | Linear algebra for implicit solvers | MPL-2.0. Some third-party files are BSD or LGPL; `EIGEN_MPL2_ONLY` excludes LGPL code at build time | gitlab.com/libeigen/eigen (COPYING.README) | MPL-2.0 is file-level copyleft. Define `EIGEN_MPL2_ONLY` if LGPL code must be excluded |
| OpenVDB | Sparse volumes | Apache-2.0 from v12.0 (2024); MPL-2.0 before that | github.com/AcademySoftwareFoundation/openvdb; phoronix.com (relicensing news) | **Depends on version.** The version vendored in Blender was not checked |

### 5.2 Blender-linked components (checked)

Blender does not contain the OpenVDB or Eigen library sources. Its build scripts download pinned versions. The checks
below use the pinned version, not the upstream default branch.

| Component | Pinned in Blender (commit 69f2f845) | Licence found | Source checked |
|---|---|---|---|
| OpenVDB | 13.0.0 (`build_files/build_environment/cmake/versions.cmake`, line 433) | **Apache-2.0** (the LICENSE file at tag v13.0.0) | `github.com/AcademySoftwareFoundation/openvdb`, tag v13.0.0, `LICENSE`, read through the GitHub API |
| Eigen | Commit `8a1083e9bf41b91fdea6546681f806154efdc25a`, 2025-11-24 (`versions.cmake`, line 1496) | **MPL-2.0** for most files. Some files are BSD or other MPL2-compatible licences | `COPYING.README` at that commit, read from the eigenteam git mirror (same SHA) |
| Blender wrapper `intern/openvdb` | Blender source | GPL-2.0-or-later (SPDX headers in `openvdb_capi.cc`, `openvdb_fwd.hh`) | Blender clone |
| Blender wrapper `intern/eigen` | Blender source | GPL-2.0-or-later (SPDX header in `eigen_capi.h`) | Blender clone |

Consequences: OpenVDB 13.0.0 is permissive, and the Blender wrapper is GPL-2.0-or-later. Eigen is file-level MPL-2.0.
Set `EIGEN_MPL2_ONLY` if an LGPL-free build is required. A future version bump must repeat these checks.

## 6. Project license

No license file is present in this repository at the time of writing. The `reality/` code is original work written for
this project and does not copy any third-party source. A license must be chosen before any distribution. If the
engine is built into Blender, the combined work must follow Blender's GPL-2.0-or-later terms.
