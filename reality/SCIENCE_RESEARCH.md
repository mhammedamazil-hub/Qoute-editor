# SCIENCE_RESEARCH - PROJECT REALITY

This document records the scientific foundations behind each simulation domain: governing equations, the
physical properties each model needs, the numerical methods, computational cost, existing open-source
implementations, reference data, and validation experiments. It also records what was implemented in this
iteration and what remains.

It is a **first-pass research synthesis**, not an exhaustive literature review. Sources are either
standard textbooks (named, no DOI given unless verified) or pages checked in this session (cited inline).
Anything marked **[verify]** still needs confirmation against the primary source before a scientific claim
is made from it.

Legend for each domain:

- **Equations**: governing relations.
- **Properties**: physical inputs the model needs.
- **Numerics**: method families suited to the problem.
- **Cost**: rough scaling with problem size.
- **Open source**: existing implementations to study or reuse (license checked where noted).
- **Reference data**: datasets or handbooks to validate against.
- **Validation**: experiments or analytic tests.
- **Status**: what is implemented in `reality/`.

---

## 1. Classical mechanics

- **Equations**: Newton's laws, F = m a; torque tau = I alpha; conservation of linear momentum, angular momentum and
  energy; universal gravitation F = G m1 m2 / r^2 with G = 6.67430(15) x 10^-11 m^3 kg^-1 s^-2 (CODATA 2018,
  [1](https://pmc.ncbi.nlm.nih.gov/articles/PMC9890581/)); quadratic drag F_d = (1/2) rho C_d A v^2; Coulomb
  friction F_t <= mu F_n; restitution with impulse e = -(v2' - v1')/(v2 - v1).
- **Properties**: mass, inertia tensor, centre of mass, friction (per contact pair), restitution (per contact pair),
  drag coefficient, density of the surrounding fluid.
- **Numerics**: RK4 for non-stiff ODEs; velocity Verlet (symplectic) for conservative dynamics; sequential-impulse or
  projected Gauss-Seidel for contact; continuous collision detection (time of impact) for fast bodies.
- **Cost**: O(N) per step for integration; collision detection is O(N log N) with a sweep-and-prune or BVH broad phase.
- **Open source**: Bullet Physics (Zlib license; vendored in Blender's `extern/bullet2`, verified); MuJoCo (Apache-2.0,
  for reference, not checked in this pass [verify]); Box2D (MIT, 2D reference [verify]).
- **Reference data**: analytic free fall, projectile, pendulum (elliptic-integral period, Landau & Lifshitz *Mechanics*,
  Sec. 48), Kepler orbits.
- **Validation**: implemented; 15 cases (MECH-01..15), including exact period comparisons and conservation checks.
- **Status**: implemented (`mechanics.py`, `integrators.py`). Rigid-body rotation and contact solver not yet implemented.

## 2. Advanced physics

### 2.1 Electromagnetism and radiation
- **Equations**: Maxwell's equations; Lorentz force F = q(E + v x B); Stefan-Boltzmann P = e sigma A T^4 with
  sigma = 5.670374419 x 10^-8 W m^-2 K^-4 (exact in SI 2019, CODATA 2018 [1]).
- **Properties**: permittivity, permeability, conductivity, emissivity, optical constants.
- **Numerics**: FDTD (Yee scheme) for full-wave EM; ray or path tracing for optical-scale radiation.
- **Open source**: Meep (GPL-2.0 [verify]); openEMS (GPL [verify]); Cycles in Blender (Apache-2.0 kernels, verified).
- **Validation**: Stefan-Boltzmann at 300 K (THER-05); Maxwell-based Fresnel results via Born & Wolf.
- **Status**: radiation emittance implemented; Maxwell solver not started.

### 2.2 Quantum mechanics
- **Position**: quantum effects are not simulated at the scale of this engine. Quantum-mechanical properties enter only
  through measured material constants (band gaps, refractive indices, thermal conductivity). Any feature that claims
  quantum behaviour must solve the Schrodinger or Dirac equation and is out of scope for now. This avoids the
  "visual approximation" trap the project rules forbid.
- **Status**: not implemented; documented as a limitation.

### 2.3 Relativity
- **Position**: special and general relativistic corrections are negligible below ~1e-8 of c for everyday speeds
  (Newtonian gravity is accurate for lab and planetary scales). The engine uses Newtonian gravity and documents
  the limit. Relativistic corrections are not implemented.
- **Status**: not implemented; scope limit documented in `LIMITATIONS.md`.

### 2.4 Thermodynamics and statistical mechanics
- **Equations**: first law dU = dQ - dW; ideal gas pV = nRT with R = 8.314462618 J mol^-1 K^-1 (exact in SI 2019);
  entropy S = k_B ln W; Boltzmann statistics for populations.
- **Properties**: specific heat, latent heat, equation of state.
- **Numerics**: energy balances with latent heat (implemented); equations of state; Monte Carlo for statistical
  ensembles.
- **Validation**: metal-on-ice energy balance (THER-03, THER-04); ideal-gas sound speed (ACOU-01).
- **Status**: energy balance and ideal-gas relation implemented; general equations of state not yet.

### 2.5 Heat transfer
- **Equations**: Fourier's law q = -k grad T; transient conduction rho c dT/dt = div(k grad T); Newton cooling
  q = h (T - T_inf); radiation (above). Lumped capacitance valid for Bi = h L_c / k < 0.1 (Incropera).
- **Properties**: k, c_p, rho, h, emissivity; temperature dependence where significant.
- **Numerics**: explicit FTCS (stable for Fo <= 1/2); implicit Crank-Nicolson or backward Euler for large dt; finite
  volume for complex geometry.
- **Cost**: explicit O(N) per step, time-step limited by dx^2/alpha; implicit requires a linear solve per step.
- **Open source**: OpenFOAM (GPL-3.0 [verify]) for conjugate heat transfer; FEniCS (LGPL [verify]).
- **Reference data**: Carslaw & Jaeger (1959) slab solution; Incropera Table A.1 for property values.
- **Validation**: lumped (THER-01), 1D conduction vs Fourier series (THER-02).
- **Status**: implemented (`thermal.py`).

### 2.6 Phase transitions
- **Equations**: Stefan problem for melting (moving boundary, latent heat L); Clausius-Clapeyron dp/dT = L/(T dv).
- **Numerics**: enthalpy method (fixed grid with enthalpy as the variable); front tracking.
- **Status**: latent-heat energy balance for a lumped body implemented. A spatial Stefan solver is not.

### 2.7 Material failure
- **Equations**: LEFM stress intensity K_I = Y sigma sqrt(pi a) (Irwin 1957); failure at K_I >= K_Ic; Griffith energy
  balance G = K_I^2/E' >= 2 gamma_s (Griffith 1921, DOI 10.1098/rsta.1921.0006 [verify DOI]); von Mises yield for
  ductile metals; Weibull statistics for flaw populations in glass [verify].
- **Properties**: E, nu, K_Ic, sigma_y, sigma_u, flaw population (size distribution).
- **Numerics**: finite-element continuum damage; cohesive-zone models; phase-field fracture; discrete element for
  fragmentation; material point method (MPM) for large deformation and fracture.
- **Open source**: Taichi MPM (MIT-licensed MLS-MPM reference, [2](https://github.com/yuanming-hu/taichi_mpm/blob/master/README.md));
  Hu et al. (2018), *ACM TOG* 37(4), 150, "A Moving Least Squares Material Point Method with Displacement Discontinuity
  and Two-Way Rigid Body Coupling" (SIGGRAPH 2018) [2]; FEniCS fracture tutorials.
- **Reference data**: soda-lime glass K_Ic = 0.75 MPa sqrt(m) and nu = 0.20, E = 73 GPa, density 2.49 g/cm^3 (DTIC
  ARL-TR-8187 as quoted by [3](https://saiweiglass.com/blog/soda-lime-glass-guide/)); annealed practical tensile
  strength 30-50 MPa, flaw-limited, E = 70 GPa, nu = 0.22 ([4](https://www.industrialengineeringstudio.com/materials/glass)).
- **Validation**: critical flaw round trip (FRAC-02); glass 10 um flaw critical stress 133.8 MPa (FRAC-01); Griffith
  surface energy consistency (FRAC-03); glass vs steel outcome (FRAC-04).
- **Status**: LEFM and yield criteria implemented for the **uniaxial, single-flaw** case. Crack growth, fragmentation
  and multi-flaw statistics are **not implemented**.

### 2.8 Wave mechanics and acoustics
- **Equations**: wave equation p_tt = c^2 nabla^2 p; c = sqrt(gamma R T / M) for ideal gases; Z = rho c; normal-incidence
  R = ((Z2 - Z1)/(Z2 + Z1))^2 (Kinsler et al., *Fundamentals of Acoustics*, 4th ed.); Doppler f' = f (c +- v_o)/(c -+ v_s).
- **Properties**: density, bulk modulus, shear modulus, damping, absorption coefficient.
- **Numerics**: finite-difference time-domain (FDTD) for wave propagation; digital waveguides; modal synthesis for
  vibrating objects (modal analysis of the structure, then sum of damped sinusoids); boundary element for radiation.
- **Open source**: Kinsler's references; Pyroomacoustics (MIT [verify]); OpenAcoustics-style tools [verify].
- **Validation**: speed of sound 343.2 m/s at 20 degC (ACOU-01); air-water reflection 0.9989 (ACOU-02);
  closed-open pipe resonance (ACOU-05).
- **Status**: linear acoustic relations implemented. Propagation solver and modal synthesis not started.

### 2.9 Optics
- **Equations**: Snell n1 sin t1 = n2 sin t2; Fresnel amplitude coefficients (Born & Wolf, *Principles of Optics*, Sec. 1.5);
  Sellmeier dispersion n^2 = 1 + sum B_i l^2/(l^2 - C_i); thin-film interference 2 n d cos t = m lambda; Beer-Lambert
  absorption I = I0 exp(-alpha x); Rayleigh and Henyey-Greenstein phase functions.
- **Properties**: complex refractive index n + i kappa per wavelength; roughness; thickness for thin films.
- **Numerics**: path tracing with spectral sampling; wavelength-dependent Fresnel; FDTD for diffraction.
- **Open source**: Cycles (Apache-2.0 kernels, verified; RGB-based in this pass); PBRT (BSD-style [verify]).
- **Validation**: Snell (OPT-01), critical angle (OPT-02), normal reflectance 4 % (OPT-03), Brewster zero (OPT-04),
  s-polarization energy balance (OPT-05), BK7 n_d = 1.5168 (OPT-06; Schott datasheet [verify]).
- **Status**: implemented for lossless dielectrics. Absorption (complex index), spectral rendering, thin films, and
  scattering are **not implemented**.

## 3. Mathematics

| Topic | Use in the engine | Method / reference | Status |
|---|---|---|---|
| Linear algebra | Stiffness, inertia, implicit solvers | Gaussian elimination, CG, Cholesky (Golub & Van Loan) | Not yet (Eigen is the planned backend via Blender) |
| Calculus, vector calculus | Gradients, divergence in PDEs | Standard | Used implicitly |
| ODEs | Dynamics | RK4, velocity Verlet, adaptive RK (Dormand-Prince) | RK4 and Verlet implemented |
| PDEs | Heat, waves, elasticity | FTCS, implicit schemes, FEM, FVM | Explicit FTCS implemented |
| Numerical analysis | Error control, stability | Von Neumann stability, consistency, convergence | Stability check (Fo <= 1/2) implemented |
| Tensor mathematics | Stress, strain, inertia tensor | Voigt notation, rotations | Not yet |
| Probability, statistics | Flaw populations, Monte Carlo | Weibull, Gaussian, Monte Carlo | Not yet |
| Optimization | Calibration to data | Levenberg-Marquardt, gradient descent | Not yet |
| Numerical integration | Quadrature, time integration | Trapezoid, Gauss, RK | Trapezoid used in beams |
| Computational geometry | Collision, BVH, convex hulls | GJK, EPA, sweep-and-prune, BVH | Blender BVH reuse planned |
| Graph theory | Coupling graph, scheduling | Topological sort | Not yet |
| Fourier analysis | Spectra, modal analysis | FFT | Not yet |
| Complex numbers | Complex refractive index, modal analysis | Complex arithmetic | Not yet |
| Special functions | Pendulum period | Complete elliptic integral via AGM (Abramowitz & Stegun 17.6) | Implemented |
| FEM / FDM / FVM / BEM | Continuum mechanics, heat, fluids, acoustics | Standard texts (Zienkiewicz; Patankar; Hughes) | Only FDM (FTCS) implemented |

## 4. Chemistry

- **Equations**: reaction kinetics (Arrhenius k = A exp(-Ea/RT)); thermochemistry (Hess's law, Delta H); diffusion
  (Fick's law); solubility and Henry's law; combustion stoichiometry; corrosion (Nernst and Butler-Volmer).
- **Properties**: composition, molar mass, heat of formation, activation energies, diffusivity, solubility, pH.
- **Numerics**: stiff ODE solvers (BDF, Rosenbrock) for kinetics; reaction-diffusion PDEs; Gillespie SSA for small counts.
- **Open source**: Cantera (BSD-3 [verify]) for kinetics and thermochemistry; RDKit (BSD-3 [verify]) for molecules.
- **Reference data**: NIST Chemistry WebBook; CRC Handbook of Chemistry and Physics.
- **Status**: material composition is recorded only as bulk properties. No reaction kinetics yet. Chemistry is a
  roadmap phase, not a claim.

## 5. Biology

- **Scope**: cell and molecular biology, genetics, plant and animal biology, physiology, biomechanics, growth,
  metabolism, ecosystems, evolution, microbiology, neural systems.
- **Equations**: Michaelis-Menten (enzyme kinetics); logistic and Lotka-Volterra population models; Beer-Lambert for
  leaf light interception; Penman-Monteith for evapotranspiration (FAO-56 [verify]); Hill-type dose-response;
  Hodgkin-Huxley equations for excitable membranes; musculoskeletal dynamics via Lagrangian mechanics.
- **Properties**: tissue stiffness (cortical bone E ~ 17 GPa, density 1900 kg/m^3, see `MATERIAL_DATABASE.md`),
  water content, nutrient concentrations, photosynthetic parameters.
- **Numerics**: ODE systems for metabolism; agent-based or cellular automata for growth; FEM for tissue mechanics.
- **Open source**: COPASI (Artistic-2.0 [verify]); NEURON (BSD-style [verify]) for neurons; OpenSim (Apache-2.0 [verify]) for
  musculoskeletal models; PlantFSE / L-systems literature for plant growth [verify].
- **Validation**: population-model textbook benchmarks; published tissue data. No biological simulation is implemented.
- **Status**: roadmap only. Per project rule 15, the engine does not claim biological realism without validated models.

## 6. Earth and environmental sciences

- **Equations**: Terzaghi effective stress sigma' = sigma - u; Darcy's law q = -(k/mu) grad p; shallow-water equations;
  Navier-Stokes for atmosphere and ocean; advection-diffusion for pollutants; Mohr-Coulomb failure tau = c + sigma tan(phi).
- **Properties**: permeability, porosity, cohesion, friction angle, bulk density, moisture content.
- **Numerics**: finite volume and finite element on structured or unstructured grids; Lagrangian particles for granular
  flows (DEM); MPM for sand and snow (Hu et al. 2018 [2]).
- **Open source**: OpenFOAM (GPL-3.0 [verify]); Taichi MPM examples (MIT, [2]).
- **Reference data**: Lambe & Whitman, *Soil Mechanics*; standard consolidation and triaxial tests.
- **Status**: soil and sand are represented as materials with bulk properties only. Granular mechanics and hydrology are
  not implemented.

## 7. Engineering sciences

| Discipline | Governing relations | Numerics | Open source | Reference data | Status |
|---|---|---|---|---|---|
| Mechanical | Newton, Euler, stress-strain | RK4, Verlet, FEM | Bullet (Zlib), Project Chrono [verify] | Textbook beam and vibration tests | Implemented in part (`mechanics.py`, `structures.py`) |
| Electrical | Ohm, Kirchhoff, Maxwell | MNA, FDTD | ngspice (BSD [verify]) | Standard circuit benchmarks | Not started (electrical conductivity stored only) |
| Civil / structural | Euler-Bernoulli beam, Timoshenko beam, plates | FEM, closed-form | OpenSees (BSD [verify]) | Cantilever formulas (Timoshenko & Gere) | Cantilever only |
| Aerospace | Compressible flow, orbital mechanics | FV, Kepler/Verlet | SU2 (LGPL [verify]) | Kepler orbits; circular speed | Orbital mechanics implemented |
| Materials | Failure criteria, Hall-Petch, phase diagrams | MPM, phase field, FEM | Taichi MPM ([2]) | ASM Handbook; CRC | Fracture criteria implemented |
| Chemical | Mass and energy balance, reaction kinetics | ODE, CFD | Cantera ([verify]) | NIST WebBook | Not started |
| Robotics | Rigid-body dynamics, kinematics, control | Articulated-body algorithm | Pinocchio (BSD-2 [verify]) | Standard manipulator benchmarks | Not started |
| Thermofluid | Navier-Stokes, energy equation | FV, LBM | OpenFOAM, Palabos [verify] | Ghia et al. cavity benchmark [verify] | Heat only |

## 8. Cross-cutting findings from the research

1. **Pick the method to fit the physics.** Explicit schemes are cheap but conditionally stable (FTCS Fo <= 1/2).
   Symplectic integrators preserve energy for conservative systems. Choosing RK4 for orbits gives secular energy drift,
   and this was checked directly in the validation suite.
2. **Material properties must be dimensioned and bounded.** Poisson ratio must lie in (-1, 0.5), and brittle solids
   need a fracture toughness, not only a strength. The material model enforces this.
3. **Brittle and ductile failure are different physics.** A single "strength" number cannot describe glass and steel.
   The fracture module uses LEFM for brittle solids and yield for ductile metals, and the same stress gives opposite
   outcomes (FRAC-04).
4. **Most visual effects are not physical models.** Blender's rigid body, cloth and fluid are good simulators but
   use shading-oriented or heuristic parameters in places. They are reused as solvers only after their numerics are
   checked against the validation cases in this repository.
5. **Quantum and relativistic effects are out of scope for this stage.** They would require different solvers, and
   their effects at everyday scales are negligible for the intended phenomena.

## 9. References

1. Tiesinga, E. et al. (CODATA 2018), *Reviews of Modern Physics* 93, 025010 (2021), DOI 10.1103/RevModPhys.93.025010;
   G value at [1](https://pmc.ncbi.nlm.nih.gov/articles/PMC9890581/).
2. Hu, Y. et al., "A Moving Least Squares Material Point Method with Displacement Discontinuity and Two-Way Rigid Body
   Coupling", *ACM Transactions on Graphics* 37(4), 150 (SIGGRAPH 2018); reference implementation
   [2](https://github.com/yuanming-hu/taichi_mpm/blob/master/README.md).
3. Soda-lime glass K_IC 0.75 MPa sqrt(m), E 73 GPa, nu 0.20 (DTIC ARL-TR-8187, quoted in
   [3](https://saiweiglass.com/blog/soda-lime-glass-guide/)).
4. Soda-lime glass tensile strength (flaw-limited) and density: [4](https://www.industrialengineeringstudio.com/materials/glass).
5. Griffith, A. A. (1921), "The phenomena of rupture and flow in solids", *Phil. Trans. R. Soc. A* 221, 163-198
   (DOI 10.1098/rsta.1921.0006 [verify]).
6. Irwin, G. R. (1957), "Analysis of stresses and strains near the end of a crack traversing a plate", *J. Appl. Mech.* 24.
7. Baraff, D. and Witkin, A. (1998), "Large steps in cloth simulation", SIGGRAPH 1998 [verify DOI].
8. Muller, M. et al. (2007), "Position based dynamics", *J. Visual Comm. Image Representation* 18(2) [verify DOI].
9. Landau, L. D. and Lifshitz, E. M., *Mechanics* (3rd ed.), Sec. 48 (pendulum).
10. Born, M. and Wolf, E., *Principles of Optics* (7th ed.), Secs. 1.1, 1.5.
11. Incropera, F. P. et al., *Fundamentals of Heat and Mass Transfer* (7th ed.), Chs. 1, 5, 12; Table A.1.
12. Carslaw, H. S. and Jaeger, J. C. (1959), *Conduction of Heat in Solids* (2nd ed.), Sec. 2.4.
13. Kinsler, L. E. et al., *Fundamentals of Acoustics* (4th ed.).
14. Timoshenko, S. and Gere, J., *Mechanics of Materials*; Rao, S. S., *Mechanical Vibrations*.
15. Abramowitz, M. and Stegun, I. A., *Handbook of Mathematical Functions*, Sec. 17.6 (complete elliptic integrals, AGM).
16. Lambe, T. W. and Whitman, R. V., *Soil Mechanics*; Mindess, Young and Darwin, *Concrete*; Currey, J. D., *Bones*.
17. Petrenko, V. F. and Whitworth, R. W., *Physics of Ice* (1999); Treloar, L. R. G., *The Physics of Rubber Elasticity* (1975).
18. ASM Handbook (Vols. 1, 2); CRC Handbook of Chemistry and Physics; USDA Forest Products Lab, *Wood Handbook* (FPL-GTR-190).
19. IAPWS R6-95, Release on the IAPWS Formulation 2008 for the Thermodynamic Properties of Ordinary Water Substance.
20. IERS Conventions (2010), TN36 (gravitational parameters); IAU 2015 nominal constants.
