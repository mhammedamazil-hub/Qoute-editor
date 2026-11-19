# SCIENCE_RESEARCH - PROJECT REALITY

Phase 1 deliverable (research gate). This document records, for each scientific discipline in the project brief:

1. **Governing equations**
2. **Required physical properties**
3. **Appropriate numerical methods**
4. **Computational cost**
5. **Available open-source implementations** (with the license checked)
6. **Scientific reference datasets**
7. **Validation experiments**

plus **Status in this repository** and a **Technical conclusion** for the project.

## How sources are marked

- **[V]** The source was checked in this session. Its URL is given, and the verification ledger in §10 records what was confirmed.
- **[T]** A standard textbook or handbook edition. It is named, but the page or table was not checked online in this session.
- Nothing in this document is marked "to verify". Items that could not be confirmed were removed or downgraded to [T] or to "not evaluated".

Phase 1 is complete when the gate test in `reality/tests/test_research_gate.py` passes. The test checks that this file has no open verification markers and that every discipline has all seven fields.

---

## 1. Classical mechanics

- **Governing equations:** Newton's second law F = m a; Euler's equations for rigid rotation; torque tau = I alpha; conservation of linear momentum, angular momentum and energy; Newtonian gravity F = G m1 m2 / r^2 with G = 6.67430(15) x 10^-11 m^3 kg^-1 s^-2 [V: CODATA 2018, Tiesinga et al., Rev. Mod. Phys. 93, 025010, https://pml.nist.gov/cuu/pdf/RevModPhys.93.025010.pdf]; quadratic drag F_d = (1/2) rho C_d A v^2 [T]; Coulomb friction F_t <= mu F_n [T]; impulsive restitution e = -(v2' - v1')/(v2 - v1) [T].
- **Required properties:** mass, inertia tensor, centre of mass, drag coefficient, fluid density, and friction and restitution **per contact pair** (not per material).
- **Numerical methods:** RK4 for non-stiff ODEs; velocity Verlet for conservative systems (symplectic, bounded energy error); sequential impulses or projected Gauss-Seidel for contacts [T]; continuous collision detection (time of impact) for fast bodies [T].
- **Computational cost:** O(N) per step for integration. Broad-phase collision detection is O(N log N) with sweep-and-prune or O(N) amortised with a BVH [T].
- **Open-source implementations (license checked):**
  - Bullet Physics 3, Zlib license, vendored in Blender at `extern/bullet2` [V: Blender `README.blender`].
  - Project Chrono, BSD-3-Clause, C++ with Python and C# APIs, for rigid, deformable and granular bodies [V: https://github.com/projectchrono/chrono].
  - MuJoCo, Apache-2.0 [V: https://github.com/google-deepmind/mujoco/blob/main/README.md].
  - Pinocchio, BSD-2-Clause, rigid-body algorithms with analytical derivatives [V: https://github.com/stack-of-tasks/pinocchio].
  - Box2D, MIT, 2D engine [V: https://github.com/erincatto/box2d].
- **Reference datasets:** analytic free fall, projectile and pendulum; the elliptic-integral pendulum period [T: Landau & Lifshitz, *Mechanics*, Sec. 48]; Kepler orbits; published coefficient-of-restitution tables [T].
- **Validation experiments:** drop tests with measured rebound height (restitution); pendulum period versus amplitude; orbital periods for planetary data.
- **Status in repository:** implemented (`mechanics.py`, `integrators.py`); 15 validation cases. Rigid rotation, 3D contact and friction are not implemented.
- **Technical conclusion:** Stiff contact and stacking need implicit or sequential-impulse solvers. Restitution and friction are pair properties. Energy-conserving integrators must be used for orbits, and fixed-step RK4 is not suitable for them.

## 2. Advanced physics

### 2.1 Electromagnetism and radiation
- **Governing equations:** Maxwell's equations; Lorentz force F = q(E + v x B) [T]; Stefan-Boltzmann P = e sigma A (T^4 - T_env^4) with sigma = 5.670374419 x 10^-8 W m^-2 K^-4 (exact in SI 2019) [T: SI 2019 definition; not separately checked in this session].
- **Required properties:** permittivity, permeability, conductivity, emissivity, optical constants.
- **Numerical methods:** the Yee FDTD scheme (staggered grid, leapfrog in time) [V: Yee, K. S. (1966), IEEE Trans. Antennas Propag. 14(3), 302-307, doi:10.1109/TAP.1966.1138693]; ray or path tracing for radiative transport.
- **Computational cost:** FDTD scales as N_cells x N_steps, with the Courant limit on dt; 3D grids are memory-heavy.
- **Open-source implementations (license checked):** Meep, GPL-2.0, FDTD in 1D to 3D with Python, Scheme and C++ APIs [V: https://github.com/NanoComp/meep]. Cycles, Apache-2.0 kernels [V: Blender `intern/cycles/kernel/types.h`].
- **Reference datasets:** NIST and CRC tables of optical constants [T]; analytic plane-wave and Fresnel solutions [T].
- **Validation experiments:** Stefan-Boltzmann blackbody emittance (THER-05); Fresnel reflectance (OPT-03 to OPT-05).
- **Status in repository:** blackbody radiation implemented. No Maxwell solver.
- **Technical conclusion:** A full Maxwell solver is a separate subsystem with its own grid and time step. Meep (GPL-2.0) is suitable as a reference or external back-end, but linking it would make the combined work GPL-2.0.

### 2.2 Quantum mechanics
- **Governing equations:** Schrodinger equation i hbar d psi/dt = H psi [T]; Dirac equation for relativistic spin-1/2 [T].
- **Status and conclusion:** Quantum mechanics is **not simulated**. At the scales this engine targets, quantum effects enter through measured material constants (band gap, refractive index, thermal conductivity). Any feature that claims quantum behaviour must solve the wave equation and is out of scope for the current roadmap. This follows rule 6 of the brief: no visual approximation may stand in for a physical model.

### 2.3 Relativity
- **Governing equations:** Lorentz transformations; Einstein field equations G_mu,nu = 8 pi G / c^4 T_mu,nu [T].
- **Status and conclusion:** Newtonian gravity is used. Relativistic corrections are negligible at everyday speeds and planetary field strengths, and the limitation is recorded in `LIMITATIONS.md`. Relativistic simulation is not implemented.

### 2.4 Thermodynamics and statistical mechanics
- **Governing equations:** First law dU = dQ - dW; ideal gas pV = nRT with R = 8.314462618 J mol^-1 K^-1 (exact in SI 2019) [T]; Boltzmann entropy S = k_B ln W [T].
- **Required properties:** specific heat, latent heat, equation of state, and temperature dependence of each.
- **Numerical methods:** energy balances with latent heat (closed form); equation-of-state integration; Monte Carlo ensembles [T].
- **Computational cost:** closed-form balances are O(1); ensemble methods scale with sample count.
- **Open-source implementations (license checked):** Cantera, BSD-3-Clause, for thermochemistry and kinetics [V: https://anaconda.org/Cantera/cantera].
- **Reference datasets:** NIST Chemistry WebBook and CRC Handbook [T].
- **Validation experiments:** metal-on-ice melting energy balance (THER-03, THER-04); speed of sound from the ideal-gas relation (ACOU-01).
- **Status in repository:** latent-heat energy balance and ideal-gas relations implemented.
- **Technical conclusion:** Energy-balance models are only as good as the assumption of no heat loss. A spatial Stefan (moving-boundary) model is needed for melting rates. The enthalpy method is the standard approach, Voller & Prakash (1987) [V: doi:10.1016/0017-9310(87)90317-6].

### 2.5 Heat transfer
- **Governing equations:** Fourier's law q = -k grad T; transient conduction rho c dT/dt = div(k grad T) [T: Incropera et al.]; Newton cooling q = h (T - T_inf) [T]; lumped capacitance valid for Bi = h L_c/k < 0.1 [T].
- **Required properties:** k, c_p, rho, h, emissivity; temperature dependence where significant.
- **Numerical methods:** explicit FTCS (stable for Fo <= 1/2) [T: Carslaw & Jaeger]; implicit Crank-Nicolson or backward Euler for large dt [T]; finite volume for complex geometry [T].
- **Computational cost:** explicit O(N) per step, with dt limited by dx^2/alpha. Implicit schemes need a linear solve per step.
- **Open-source implementations (license checked):** OpenFOAM, GPL-3.0 [V: https://github.com/openfoam/openfoam-dev and https://en.wikipedia.org/wiki/OpenFOAM]. FEniCS (dolfinx), LGPL-3.0 with GPL-3.0 files [V: https://github.com/FEniCS/dolfinx].
- **Reference datasets:** Carslaw & Jaeger (1959) slab solution [T]; property tables in Incropera Table A.1 [T].
- **Validation experiments:** analytic lumped cooling (THER-01); 1D conduction against the Fourier series (THER-02).
- **Status in repository:** implemented (`thermal.py`).
- **Technical conclusion:** The explicit solver is correct and cheap but needs dt <= dx^2/(2 alpha). For large or stiff problems the solver must switch to an implicit scheme.

### 2.6 Phase transitions
- **Governing equations:** Stefan problem with latent heat L [T]; Clausius-Clapeyron dp/dT = L/(T dv) [T].
- **Numerical methods:** enthalpy method on a fixed grid (Voller & Prakash 1987 [V]); front tracking [T].
- **Open-source implementations (license checked):** Cantera (thermochemistry, BSD-3-Clause) [V]; FEniCS (LGPL-3.0 / GPL-3.0 option) [V] for custom phase-change PDEs.
- **Reference datasets:** melting and latent-heat tables (CRC) [T].
- **Validation experiments:** melting of ice in a stirred water bath (classical benchmark) [T].
- **Status in repository:** lumped latent-heat balance only.
- **Technical conclusion:** the enthalpy method is the right first target for the moving-boundary problem. It gives a fixed grid with the same conservation properties.

### 2.7 Material failure
- **Governing equations:** Irwin's stress intensity K_I = Y sigma sqrt(pi a) [V: Irwin (1957), J. Appl. Mech. 24, 361-364, cited by https://www.fracturemechanics.org/sif.html]; failure at K_I >= K_Ic [T]; Griffith energy balance G = K_I^2/E' >= 2 gamma_s [V: Griffith (1921), doi:10.1098/rsta.1921.0006, confirmed via ADS and Royal Society records]; von Mises yield for ductile metals [T]; Weibull probability of failure P_f = 1 - exp(-(sigma/sigma_0)^m) [V: Weibull (1951), J. Appl. Mech. 18, 293-297, doi:10.1115/1.4010337 via https://onlinelibrary.wiley.com/doi/10.1002/9781119850960.ch3].
- **Required properties:** E, nu, K_Ic, sigma_y, sigma_u, and a flaw-size population (characterised by the Weibull modulus m and scale sigma_0 for brittle solids).
- **Numerical methods:** finite-element continuum damage; cohesive-zone models; phase-field fracture; discrete-element fragmentation; material point method (MPM) for large deformation and fracture [V: Hu et al. (2018), ACM TOG 37(4), 150, doi:10.1145/3197517.3201293].
- **Computational cost:** FEM is O(N^1.2-1.5) with iterative solvers [T]; MPM scales with particle count and background-grid resolution [T].
- **Open-source implementations (license checked):** Taichi MPM (MLS-MPM reference solver), MIT [V: https://github.com/yuanming-hu/taichi_mpm, LICENSE file and README]. FEniCS fracture examples, LGPL-3.0 / GPL-3.0 [V].
- **Reference datasets:** soda-lime glass K_Ic = 0.75 MPa sqrt(m), nu = 0.20, E = 73 GPa, quoted from DTIC ARL-TR-8187 by [V: https://saiweiglass.com/blog/soda-lime-glass-guide/]; practical tensile strength 30-50 MPa, flaw-limited, E = 70 GPa, density 2500 kg/m^3 [V: https://www.industrialengineeringstudio.com/materials/glass]; Weibull parameters for glass from published strength tests (not yet collected).
- **Validation experiments:** three-point bending of glass specimens with known flaw size (Weibull and LEFM); Charpy and tensile tests for ductile metals [T].
- **Status in repository:** LEFM, Griffith and yield criteria for the uniaxial, single-flaw case (`fracture.py`). Crack growth, fragmentation and population statistics are not implemented.
- **Technical conclusion:** A single-flaw LEFM value is the **median**-flaw estimate, not a guaranteed strength. Real glass strength follows a Weibull distribution over the flaw population, so the model must be extended to Weibull statistics before any failure probability is quoted. Brittle and ductile materials need different criteria; the code already separates them.

### 2.8 Wave mechanics and acoustics
- **Governing equations:** wave equation p_tt = c^2 nabla^2 p [T: Kinsler et al.]; c = sqrt(gamma R T/M) for ideal gases [T]; Z = rho c [T]; normal-incidence intensity reflection R = ((Z2 - Z1)/(Z2 + Z1))^2 [T]; Doppler f' = f (c + v_o)/(c - v_s) [T].
- **Required properties:** density, bulk modulus, shear modulus, damping, absorption coefficient.
- **Numerical methods:** FDTD for wave propagation (staggered grid, same family as Yee [V]); digital waveguides; modal synthesis for vibrating bodies (modal analysis, then sums of damped sinusoids) [T]; boundary elements for radiation [T].
- **Computational cost:** FDTD scales with the grid size and the CFL-limited step; modal synthesis is cheap at runtime once the modes are computed.
- **Open-source implementations (license checked):** Pyroomacoustics, MIT, room acoustics and beamforming [V: https://github.com/LCAV/pyroomacoustics]. Cycles (Apache-2.0) is not an acoustic solver.
- **Reference datasets:** air-water impedance and reflection values in Kinsler et al. [T]; room-acoustic databases (not evaluated).
- **Validation experiments:** impedance-tube measurements of absorption coefficient [T]; pipe resonances (ACOU-05).
- **Status in repository:** linear acoustic relations implemented (`acoustics.py`). Propagation, modal synthesis and sound generation from impacts are not implemented.
- **Technical conclusion:** Impact sound is best produced by modal synthesis. The modes come from the structural solver and the sound intensity from the impact force, so acoustics depends on the mechanics and fracture modules.

### 2.9 Optics
- **Governing equations:** Snell's law n1 sin t1 = n2 sin t2 [T: Born & Wolf]; Fresnel coefficients [T]; Sellmeier dispersion n^2 = 1 + sum B_i l^2/(l^2 - C_i) [T]; thin-film interference 2 n d cos t = m lambda [T]; Beer-Lambert I = I0 exp(-alpha x) [T]; Henyey-Greenstein phase function [T].
- **Required properties:** complex refractive index n + i kappa per wavelength; surface roughness; thickness for thin films; scattering coefficient.
- **Numerical methods:** spectral path tracing; wavelength-dependent Fresnel; FDTD for diffraction [T].
- **Computational cost:** spectral path tracing multiplies sample cost by the number of wavelengths; the usual approach is hero-wavelength sampling [T].
- **Open-source implementations (license checked):** Cycles, Apache-2.0 kernels [V: Blender `intern/cycles/kernel/types.h`], RGB-based in the kernels inspected. pbrt-v4, Apache-2.0, a physically based renderer; spectral transport is the book's topic [V licence: https://github.com/mmp/pbrt-v4]. Meep (GPL-2.0), FDTD optics [V].
- **Reference datasets:** Schott N-BK7 datasheet, n_d = 1.5168, Abbe number V_d = 64.17, density 2.51 g/cm^3, E = 82.0 GPa, nu = 0.21 [V: https://abbetrex.com/glass/schott/schott-n-bk7/; BK7 is not the soda-lime glass row]; Ciddor (1996) refractive index of air [V: doi:10.1364/AO.35.001566].
- **Validation experiments:** Brewster-angle measurement; refraction through a prism (minimum-deviation method) [T].
- **Status in repository:** lossless dielectric interfaces and BK7 dispersion (`optics.py`, OPT-01..06). Absorption, scattering, diffraction and thin films are not implemented.
- **Technical conclusion:** Spectral accuracy needs a wavelength-dependent index at minimum. Pbrt-v4 (Apache-2.0) is a reasonable reference design for a spectral extension, because it is permissively licensed.

## 3. Mathematics

| Topic | Use in the engine | Method / reference | Status |
|---|---|---|---|
| Linear algebra | Stiffness, inertia, implicit solvers | Gaussian elimination, CG, Cholesky [T: Golub & Van Loan]. Eigen 3.1.1+ is MPL-2.0 [V: http://eigen.tuxfamily.org/index.php?title=Special:Export/Main_Page] | Not yet; Eigen is the planned backend |
| Calculus, vector calculus | Gradients, divergence in PDEs | Standard [T] | Used implicitly |
| ODEs | Dynamics | RK4 [T]; velocity Verlet [T]; embedded Runge-Kutta (Dormand-Prince, doi:10.1016/0771-050X(80)90013-3) [V: Dormand & Prince (1980), J. Comput. Appl. Math. 6, 19-26] | RK4 and Verlet implemented; adaptive DP45 not yet |
| PDEs | Heat, waves, elasticity | FTCS [T]; implicit schemes [T]; FEM [T]; FVM [T] | Explicit FTCS implemented |
| Numerical analysis | Error control, stability | Von Neumann stability; Lax equivalence [T] | Fo <= 1/2 check implemented |
| Tensor mathematics | Stress, strain, inertia tensor | Voigt notation, rotations [T] | Not yet |
| Probability and statistics | Flaw populations, Weibull, Monte Carlo | Weibull (1951) [V] | Weibull distribution, size effect and median-rank fit implemented (`weibull.py`); no measured flaw data fitted; Monte Carlo not implemented |
| Optimization | Calibration to data | Levenberg-Marquardt, gradient descent [T] | Not yet |
| Numerical integration | Quadrature, time integration | Trapezoid, Gauss, RK [T] | Trapezoid used in beams |
| Computational geometry | Collision, BVH, convex hulls | GJK, EPA, sweep-and-prune, BVH [T] | Blender BVH reuse planned |
| Graph theory | Coupling graph, scheduling | Topological sort [T] | Not yet |
| Fourier analysis | Spectra, modal analysis | FFT [T] | Not yet |
| Complex numbers | Complex refractive index, modal analysis | Complex arithmetic [T] | Not yet |
| Special functions | Pendulum period | Complete elliptic integral via AGM [T: Abramowitz & Stegun 17.6] | Implemented |
| FEM / FDM / FVM / BEM | Continuum mechanics, heat, fluids, acoustics | [T: Zienkiewicz; Patankar; Hughes] | Only FDM (FTCS) implemented |

**Technical conclusion:** the most used numerical building blocks (RK4, Verlet, FTCS, AGM for elliptic integrals) are implemented and tested. Implicit linear solvers, adaptive stepping and FEM are the next mathematical requirements, and they are needed for stiff contact and for 2D and 3D conduction.

## 4. Chemistry

- **Governing equations:** reaction kinetics, Arrhenius k = A exp(-Ea/RT) [T]; thermochemistry, Hess's law [T]; Fick's law of diffusion [T]; Henry's law for solubility [T]; combustion stoichiometry [T]; Nernst and Butler-Volmer equations for corrosion [T].
- **Required properties:** composition, molar mass, heat of formation, activation energies, diffusivities, solubilities, pH.
- **Numerical methods:** stiff ODE solvers (BDF, Rosenbrock) [T]; reaction-diffusion PDEs [T]; Gillespie stochastic simulation for small molecule counts [T].
- **Computational cost:** stiff kinetics needs an implicit solve per step; the cost grows with the number of species and reactions.
- **Open-source implementations (license checked):** Cantera, BSD-3-Clause, kinetics, thermochemistry and transport [V: https://anaconda.org/Cantera/cantera]. RDKit, BSD-3-Clause, cheminformatics [V: https://github.com/rdkit/rdkit].
- **Reference datasets:** NIST Chemistry WebBook [T]; CRC Handbook [T].
- **Validation experiments:** published ignition-delay and flame-speed measurements [T].
- **Status in repository:** material composition is recorded only as bulk properties. No kinetics.
- **Technical conclusion:** Chemistry should be delegated to Cantera rather than reimplemented. Only the interface (species, reaction rate, heat release) needs to be defined inside the physical-object model.

## 5. Biology

- **Scope:** cell and molecular biology, genetics, plant and animal biology, physiology, biomechanics, growth, metabolism, ecosystems, evolution, microbiology, neural systems.
- **Governing equations:** Michaelis-Menten enzyme kinetics [T]; logistic and Lotka-Volterra population models [T]; Beer-Lambert light interception in canopies [T]; Penman-Monteith evapotranspiration, FAO-56 [V: Allen, R. G. et al. (1998), FAO Irrigation and Drainage Paper 56; reviewed in https://www.sciencedirect.com/science/article/abs/pii/S0378377414002315]; Hodgkin-Huxley equations for excitable membranes [T]; Lagrangian musculoskeletal dynamics [T].
- **Required properties:** tissue stiffness (cortical bone E = 17 GPa, density 1900 kg/m^3, see `MATERIAL_DATABASE.md`), water content, nutrient concentrations, photosynthetic parameters.
- **Numerical methods:** ODE systems for metabolism; agent-based or cellular automata for growth; FEM for tissue mechanics [T].
- **Open-source implementations (license checked):** NEURON, BSD-3-Clause, for biophysically detailed neurons [V: https://github.com/neuronsimulator/nrn]. OpenSim, Apache-2.0, musculoskeletal dynamics [V: https://github.com/opensim-org/opensim-core; Delp et al. (2007), doi:10.1371/journal.pcbi.1006223]. COPASI, biochemical networks, Artistic-2.0 [V: https://copasi.org/]. Fedora package metadata lists Artistic-2.0 AND GPL-3.0-or-later AND BSD-3-Clause, so the licence must be read per release [V: packaging record].
- **Reference datasets:** population-model benchmarks [T]; published tissue data [T].
- **Validation experiments:** logistic growth against laboratory microcosm data [T]; published muscle-force measurements [T].
- **Status in repository:** not implemented. The project does not claim biological realism without validated models (brief rule 15).
- **Technical conclusion:** Biology is a long-term phase. The first step is a validated population model used as a benchmark. Musculoskeletal work can use OpenSim's Apache-2.0 models as a reference.

## 6. Earth and environmental sciences

- **Governing equations:** Terzaghi effective stress sigma' = sigma - u [T]; Darcy's law q = -(k/mu) grad p [T]; shallow-water equations [T]; Navier-Stokes for atmosphere and ocean [T]; advection-diffusion for pollutants [T]; Mohr-Coulomb failure tau = c + sigma tan(phi) [T].
- **Required properties:** permeability, porosity, cohesion, friction angle, bulk density, moisture content.
- **Numerical methods:** finite volume and finite element on structured or unstructured grids [T]; discrete element (DEM) for granular flows [T]; MPM for sand and snow [V: Hu et al. (2018), doi:10.1145/3197517.3201293].
- **Open-source implementations (license checked):** OpenFOAM, GPL-3.0 [V]; Taichi MPM, MIT [V]; SU2, LGPL-2.1, multiphysics and CFD [V: https://context7.com/su2code/su2]; Palabos, AGPL-3.0, lattice Boltzmann CFD [V: https://www.cfdflow.com/palabos-library/].
- **Reference datasets:** Lambe & Whitman, *Soil Mechanics* [T]; standard consolidation and triaxial test data [T].
- **Validation experiments:** consolidation test (Terzaghi one-dimensional consolidation has an analytic solution [T]); dam-break and sediment-transport benchmarks [T].
- **Status in repository:** soil and sand are represented only by bulk properties.
- **Technical conclusion:** Granular media are not linear elastic solids. A material model for them needs a constitutive law (Mohr-Coulomb) or a particle method (MPM/DEM). Assigning a Young's modulus to sand would be a physically incorrect shortcut, so it is intentionally absent.

## 7. Engineering sciences

Each row gives the seven required fields in the same order as the brief.

| Discipline | 1. Governing equations | 2. Required properties | 3. Numerical methods | 4. Cost | 5. Open source (license) | 6. Reference data | 7. Validation | Status |
|---|---|---|---|---|---|---|---|---|
| Mechanical | Newton, Euler; stress-strain | mass, inertia, E, nu | RK4, Verlet, FEM | O(N) to O(N^1.5) | Bullet (Zlib) [V]; Chrono (BSD-3) [V] | Timoshenko beam formulas [T] | cantilever and pendulum tests | Partial (`mechanics.py`, `structures.py`) |
| Electrical | Ohm, Kirchhoff, Maxwell | conductivity, permittivity | Modified nodal analysis; FDTD | sparse solve per step | ngspice, BSD-3-Clause [V: https://en.wikipedia.org/wiki/Ngspice] | published circuit benchmarks [T] | RC/RLC transient against analytic [T] | Not started (conductivity stored only) |
| Civil / structural | Euler-Bernoulli, Timoshenko beams; plates | E, nu, density, section | FEM; closed form | FEM sparse solve | OpenSees: University of California license, free for non-commercial use, not OSI open source [V: https://casrai.org/guides/opensees] | cantilever formulas [T] | beam tests [T] | Cantilever only |
| Aerospace | Compressible flow; orbital mechanics | GM, density, Mach | FV (SU2); Kepler/Verlet | FV: large; Kepler: O(N) | SU2, LGPL-2.1 [V]; Chrono [V] | Kepler laws [T] | orbital period, energy conservation | Orbital mechanics implemented |
| Materials | failure criteria (LEFM, yield, Weibull) | K_Ic, sigma_y, flaw population | MPM, phase field, FEM | MPM: particles x grid | Taichi MPM (MIT) [V] | glass K_Ic (see §2.7) [V] | three-point bend tests [T] | Fracture criteria implemented |
| Chemical | mass and energy balance; kinetics | enthalpies, rate constants | stiff ODE; CFD | stiff ODE: O(species^2) | Cantera (BSD-3) [V] | NIST WebBook [T] | ignition delay [T] | Not started |
| Robotics | rigid-body dynamics; kinematics | link inertias, joint limits | articulated-body algorithm | O(n) (Featherstone) [T] | Pinocchio (BSD-2) [V]; MuJoCo (Apache-2.0) [V] | standard manipulator benchmarks [T] | joint-torque tests [T] | Not started |
| Thermofluid | Navier-Stokes; energy equation | viscosity, conductivity, cp | FV; lattice Boltzmann | FV: O(N); LBM: O(N) per step | OpenFOAM (GPL-3.0) [V]; Palabos (AGPL-3.0) [V] | Ghia et al. (1982) lid-driven cavity, doi:10.1016/0021-9991(82)90058-4 [V] | cavity benchmark vs Ghia tables | Heat only |

**Technical conclusion (engineering):** For every engineering discipline, a reusable solver with a clear licence exists. The project should integrate or reference them rather than reimplement general solvers. The license constraints matter: OpenFOAM and Meep are GPL, Palabos is AGPL, OpenSees is non-commercial, while Pinocchio, Chrono, Cantera, RDKit, OpenSim, MuJoCo and pbrt-v4 are permissive.

## 8. Cross-cutting findings

1. **Choose the method to fit the physics.** Explicit schemes are cheap but conditionally stable (FTCS needs Fo <= 1/2). Symplectic integrators keep energy bounded for conservative systems. RK4 on orbits gives secular energy drift; the validation suite checks this (MECH-14).
2. **Material properties must be dimensioned and bounded.** Poisson ratio must lie in (-1, 0.5), and brittle solids need a fracture toughness.
3. **Brittle and ductile failure are different physics.** LEFM and yield give opposite outcomes for the same stress (FRAC-04). Brittle strength is a statistical property of a flaw population, which requires Weibull statistics for any failure probability.
4. **Most visual effects are not physical models.** Blender's rigid body, cloth and fluid solvers are useful, but their parameters are not all physically grounded. They are reused as solvers only after their numerics are checked against the validation cases in this repository.
5. **Licences constrain the architecture.** Blender core is GPL-2.0-or-later, so linking it constrains any Blender-hosted code. Several strong candidates (OpenFOAM, Meep, SU2, FEniCS) are copyleft. Permissive options (Chrono, Cantera, Pinocchio, RDKit, OpenSim, MuJoCo, pbrt-v4, Pyroomacoustics) are preferred for embedded use.
6. **Quantum and relativistic effects are out of scope** at the current stage.

## 9. Gaps that remain open after Phase 1

- Weibull parameters for each brittle material have not been collected from experiments.
- No experimental dataset has been downloaded and compared (drop tests, glass fracture, impedance-tube absorption).
- Elastomer hyperelastic models (Mooney-Rivlin, Ogden) are not yet chosen. Treloar (1975) is the classic source [T].
- Anisotropic models for wood and bone are not chosen.
- Benchmarks for Ghia (1982) and the Stefan problem have not been run against this code.

These gaps are tracked in `DEVELOPMENT_ROADMAP.md`.

## 10. Verification ledger

Every source marked [V] above. "Confirmed" means the statement in this document was checked against the source in this session.

| # | Source | Used for | Location | Confirmed |
|---|---|---|---|---|
| 1 | CODATA 2018, Rev. Mod. Phys. 93, 025010 (2021) | G = 6.67430(15) x 10^-11 | https://pml.nist.gov/cuu/pdf/RevModPhys.93.025010.pdf | G value and uncertainty |
| 2 | Hu et al. (2018), "A moving least squares MPM with displacement discontinuity and two-way rigid body coupling", ACM TOG 37(4), 150, doi:10.1145/3197517.3201293 | MLS-MPM | https://dl.acm.org/doi/10.1145/3197517.3201293 | Title, authors, venue, DOI |
| 3 | Taichi MPM reference implementation (MIT) | MLS-MPM code license | https://github.com/yuanming-hu/taichi_mpm | Repository LICENSE file and README state MIT |
| 4 | Soda-lime glass K_IC 0.75 MPa sqrt(m), nu 0.20, E 73 GPa (DTIC ARL-TR-8187, quoted) | §2.7 data | https://saiweiglass.com/blog/soda-lime-glass-guide/ | Values as quoted |
| 5 | Soda-lime glass tensile (flaw-limited) 30-50 MPa, E 70 GPa, density 2500 kg/m^3 | §2.7 data | https://www.industrialengineeringstudio.com/materials/glass | Values as quoted |
| 6 | Griffith (1921), Phil. Trans. R. Soc. A 221, 163-198, doi:10.1098/rsta.1921.0006 | Griffith criterion | https://doi.org/10.1098/rsta.1921.0006 | DOI and venue |
| 7 | Irwin (1957), J. Appl. Mech. 24, 361-364 | K_I definition | https://www.fracturemechanics.org/sif.html | Citation |
| 8 | Weibull (1951), J. Appl. Mech. 18, 293-297, doi:10.1115/1.4010337 | Weibull statistics | https://onlinelibrary.wiley.com/doi/10.1002/9781119850960.ch3 | Citation and DOI |
| 9 | Baraff & Witkin (1998), "Large Steps in Cloth Simulation", SIGGRAPH 98 | Implicit cloth | https://www.cs.cmu.edu/~baraff/papers/sig98.pdf | Title, venue, year (DOI not confirmed) |
| 10 | Muller et al. (2007), "Position Based Dynamics", J. Vis. Commun. Image Repr. 18(2), 109-118, doi:10.1016/j.jvcir.2007.01.005 | PBD | https://dl.acm.org/doi/10.1016/j.jvcir.2007.01.005 | Title, venue, DOI |
| 11 | Schott N-BK7: n_d 1.5168, V_d 64.17, E 82.0 GPa, nu 0.21 (BK7, not soda-lime) | OPT-06 | https://abbetrex.com/glass/schott/schott-n-bk7/ | Values as quoted |
| 12 | Ciddor (1996), Applied Optics 35, 1566-1573, doi:10.1364/AO.35.001566 | Refractive index of air | https://opg.optica.org/ao/abstract.cfm?uri=ao-35-9-1566 | Citation and DOI |
| 13 | Yee (1966), IEEE Trans. Antennas Propag. 14(3), 302-307, doi:10.1109/TAP.1966.1138693 | FDTD | citation record cited by a Scientific Research Publishing reference page | Citation and DOI |
| 14 | Voller & Prakash (1987), Int. J. Heat Mass Transfer 30(8), 1709-1719, doi:10.1016/0017-9310(87)90317-6 | Enthalpy method | https://experts.umn.edu/en/publications/a-fixed-grid-numerical-modelling-methodology-for-convection-diffu/ | Citation and DOI |
| 15 | Ghia, Ghia & Shin (1982), J. Comput. Phys. 48, 387-411, doi:10.1016/0021-9991(82)90058-4 | Cavity benchmark | https://ui.adsabs.harvard.edu/abs/1982JCoPh..48..387G/abstract | Citation and DOI |
| 16 | Dormand & Prince (1980), J. Comput. Appl. Math. 6, 19-26, doi:10.1016/0771-050X(80)90013-3 | DOPRI5 | https://en.wikipedia.org/wiki/Dormand%E2%80%93Prince_method | Citation and DOI |
| 17 | FAO-56, Allen et al. (1998) | Penman-Monteith | https://www.sciencedirect.com/science/article/abs/pii/S0378377414002315 | Citation as cited in the review |
| 18 | Meep, GPL-2.0 | License | https://github.com/NanoComp/meep | License |
| 19 | OpenFOAM, GPL-3.0 | License | https://github.com/openfoam/openfoam-dev | License |
| 20 | FEniCS dolfinx, LGPL-3.0 / GPL-3.0 | License | https://github.com/FEniCS/dolfinx | License |
| 21 | Pyroomacoustics, MIT | License | https://github.com/LCAV/pyroomacoustics | License |
| 22 | Cantera, BSD-3-Clause | License | https://anaconda.org/Cantera/cantera | License |
| 23 | RDKit, BSD-3-Clause | License | https://github.com/rdkit/rdkit | License |
| 24 | COPASI, Artistic-2.0; Artistic-2.0 AND GPL-3.0-or-later AND BSD-3-Clause (packaging) | License | https://copasi.org/ | License, with the note that packaging combines licenses |
| 25 | NEURON, BSD-3-Clause | License | https://github.com/neuronsimulator/nrn | License |
| 26 | OpenSim, Apache-2.0 | License | https://github.com/opensim-org/opensim-core | License |
| 27 | Project Chrono, BSD-3-Clause | License | https://github.com/projectchrono/chrono | License |
| 28 | OpenSees, UC license (non-commercial) | License | https://casrai.org/guides/opensees | License terms |
| 29 | SU2, LGPL-2.1 | License | https://context7.com/su2code/su2 | License |
| 30 | Pinocchio, BSD-2-Clause | License | https://github.com/stack-of-tasks/pinocchio | License |
| 31 | ngspice, BSD-3-Clause | License | https://en.wikipedia.org/wiki/Ngspice | License |
| 32 | MuJoCo, Apache-2.0 | License | https://github.com/google-deepmind/mujoco/blob/main/README.md | License |
| 33 | Box2D, MIT | License | https://github.com/erincatto/box2d | License |
| 34 | Eigen, MPL-2.0 (since 3.1.1); some third-party files BSD or LGPL, controlled by `EIGEN_MPL2_ONLY` | License | https://gitlab.com/libeigen/eigen/-/blob/master/COPYING.README | License and the MPL2-only build option |
| 35 | Palabos, AGPL-3.0 | License | https://github.com/omalaspinas/palabos | License |
| 36 | pbrt-v4, Apache-2.0 | License | https://github.com/mmp/pbrt-v4 | License |
| 37 | Mantaflow core Apache-2.0; Blender wrapper GPL-2.0-or-later | License | Blender commit 69f2f845: `extern/mantaflow/LICENSE`; `intern/mantaflow/CMakeLists.txt` SPDX header | Checked in the Blender source at that commit |
| 38 | Blender core GPL-2.0-or-later; Cycles Apache-2.0; Bullet Zlib | License | Blender clone (SPDX headers, `extern/bullet2/README.blender`) | Checked in the Blender clone |

### Corrections made in this revision

- **OpenSees** was previously listed as BSD. It is licensed under a University of California license that allows non-commercial use only, so it is **not** open source in the OSI sense.
- **Palabos** was not listed. It is AGPL-3.0 and is now recorded.
- **Meep, OpenFOAM, FEniCS, SU2, Chrono, NEURON, OpenSim, Cantera, RDKit, Pyroomacoustics, MuJoCo, Box2D, Pinocchio, ngspice, Eigen, pbrt-v4** were previously unchecked. Each licence is now confirmed from a source listed in §10.
- **COPASI** packaging metadata combines three licenses, so the license must be read per release.
- **Baraff & Witkin DOI** was not confirmed. The paper is cited by its verified CMU proceedings link.
- **Griffith, Hu et al., Dormand-Prince, Ghia, Voller & Prakash, Weibull, Yee, Ciddor, Irwin** DOIs or citations are now confirmed from search-result citation records. Full-text PDFs of these were not opened in this session.
- **Weibull** statistics were added to §2.7 as the required model for flaw populations. The previous single-flaw estimate is now described as a median-flaw estimate.
