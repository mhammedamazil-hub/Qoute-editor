# PHYSICS_MODELS - PROJECT REALITY

For each implemented model: governing equation, assumptions, validity limits, numerical method, and the
validation cases that check it (IDs match `VALIDATION_REPORT.md`). All quantities are SI unless stated.

A model is listed as **validated** only if its validation cases pass. The validation status table is
generated in `VALIDATION_REPORT.md`.

---

## M1. Newtonian point-mass gravity (`gravity.py`)

- **Equation:** a(x) = - sum_i GM_i (x - x_i) / |x - x_i|^3. GM is the gravitational parameter (m^3/s^2).
- **Other fields:** uniform field g (constant vector), and superposition of bodies. Gravity is a per-simulation
  object, not a global constant.
- **Surface gravity:** g_s = GM / R^2 for a body of mean radius R.
- **Assumptions:** Newtonian (weak field, speeds << c). Bodies are spherically symmetric (outside the body the
  field of a sphere equals that of a point mass). A point inside a body is not supported (raises an error).
- **Limits:** no general relativity, no tidal or rotational bulge, no non-spherical gravity (J2 etc.).
- **Data:** GM_Earth = 3.986004418e14 m^3/s^2 (IERS 2010), R_Earth = 6.371008771e6 m (IAU 2015 mean);
  Moon and Mars parameters are approximate (see `constants.py`).
- **Validation:** GRAV-01 (Earth 9.8202 m/s^2), GRAV-02 (Moon 1.62), GRAV-03 (Mars 3.71 at 1 % tolerance because the
  model uses the mean radius), GRAV-04 (superposition symmetry).

## M2. Rigid-particle dynamics and drag (`mechanics.py`)

### M2a. Free fall with quadratic drag
- **Equation:** m dv/dt = m g - k v |v|, with k = (1/2) rho C_d A.
- **Terminal speed:** v_t = sqrt(m g / k).
- **Analytic solution:** v(t) = v_t tanh(g t / v_t); y(t) = (v_t^2 / g) ln cosh(g t / v_t).
- **Numerical method:** RK4 on the (v, y) system.
- **Numerical note:** ln cosh x is evaluated as log1p(2 sinh^2(x/2)) for small |x|. The naive form loses about
  5 significant digits when x is ~1e-5 (found by the test suite; see CHANGELOG).
- **Assumptions:** point mass, constant C_d (no Reynolds-number dependence), constant fluid density, no buoyancy,
  no lift, no spin. Valid for Re >~ 1e3 where C_d is roughly constant (sphere C_d ~ 0.47).
- **Validation:** MECH-01, MECH-02, MECH-03.

### M2b. Projectile (no drag)
- **Equation:** x = v0 cos(th) t; y = v0 sin(th) t - g t^2/2. Range R = v0^2 sin(2 th)/g; H = v0^2 sin^2(th)/(2g).
- **Numerical method:** velocity Verlet (exact for constant acceleration), landing by linear interpolation.
- **Assumptions:** flat ground, no drag. Drag would require M2a with a horizontal component.
- **Validation:** MECH-04, MECH-05.

### M2c. Simple pendulum (large amplitude)
- **Equation:** theta'' = -(g/L) sin(theta).
- **Exact period:** T = 4 K(k)/omega0 with k = sin(theta0/2) and K the complete elliptic integral of the first kind
  (Landau & Lifshitz, Sec. 48). K is evaluated with the arithmetic-geometric mean K(m) = pi / (2 AGM(1, sqrt(1-m))).
- **Series check:** T/T0 = 1 + th^2/16 + 11 th^4/3072 + 173 th^6/737280 + 22931 th^8/1321205760 + ...
- **Validation:** MECH-06 (small-angle limit), MECH-07 (series, 0.5 rad), MECH-08 (RK4 vs exact at 1 rad).
- **Note:** at 1 rad the 5-term series truncation error is 1.4e-6, so the series check is done at 0.5 rad, where the
  truncation error is 1.4e-9. This is documented in the validation case.

### M2d. Central collision with restitution
- **Equations:** momentum m1 v1 + m2 v2 conserved; relative velocity v2' - v1' = -e (v2 - v1).
- **Energy loss:** Delta E = mu (1 - e^2) (v1 - v2)^2 / 2 with mu = m1 m2 / (m1 + m2).
- **Assumptions:** central (1D) impact, instantaneous, constant e per contact. Restitution e is a contact-pair property,
  not a material property.
- **Validation:** MECH-09 (equal-mass swap), MECH-10 (momentum), MECH-11 (elastic energy), MECH-12 (energy loss formula).

### M2e. Two-body orbits
- **Equation:** r'' = -GM r / |r|^3. Specific energy E = v^2/2 - GM/r; angular momentum h = x v_y - y v_x.
- **Numerical method:** velocity Verlet (symplectic, 2nd order).
- **Validation:** MECH-13 (circular period), MECH-14 (bounded energy drift over ~6.7 orbits), MECH-15 (angular momentum).

## M3. Heat transfer (`thermal.py`)

### M3a. Lumped capacitance
- **Equation:** m c dT/dt = -h A (T - T_inf). Solution T(t) = T_inf + (T0 - T_inf) exp(-t h A / (m c)).
- **Validity:** Bi = h (V/A) / k << 0.1. `biot_number()` computes Bi; the caller must check it.
- **Validation:** THER-01 (analytic vs independent RK4 integration of the ODE).

### M3b. 1D transient conduction
- **Equation:** dT/dt = alpha d^2T/dx^2, alpha = k / (rho c).
- **Numerical method:** explicit FTCS. Stable for Fo = alpha dt/dx^2 <= 1/2; the solver raises if violated.
- **Boundary conditions:** Dirichlet on both faces.
- **Analytic reference:** theta = (T - Ts)/(T0 - Ts) = sum_{n odd} (4/(n pi)) sin(n pi x/L) exp(-(n pi/L)^2 alpha t).
- **Validation:** THER-02 (max theta error 1.6e-5 at Fo = 0.4, 41 nodes; tolerance 1e-3).

### M3c. Metal on ice (latent-heat energy balance)
- **Equations:** adiabatic, perfect contact, ice at 0 degC, no container.
  - Partial melt (metal ends at 0 degC): m_melt = m_m c_m T_m / L, valid when m_melt <= m_i.
  - Full melt: T_f = (m_m c_m T_m - m_i L) / (m_m c_m + m_i c_w).
- **Validation:** THER-03 (partial melt value), THER-04 (energy residual for full melt).
- **Limits:** no heat loss to surroundings, no spatial temperature gradient, no supercooling, no evaporation. A spatial
  Stefan (moving-boundary) solver is required for realistic melt rate and shape (roadmap).

### M3d. Thermal radiation
- **Equation:** P = e sigma A (T^4 - T_env^4), sigma exact in SI 2019.
- **Validation:** THER-05 (300 K blackbody, 459.3 W/m^2).

## M4. Optics at a planar dielectric interface (`optics.py`)

- **Snell's law:** n1 sin(th1) = n2 sin(th2). Total internal reflection when the right-hand side exceeds 1.
- **Fresnel (lossless):** rs = (n1 cos ti - n2 cos tt)/(n1 cos ti + n2 cos tt); rp = (n2 cos ti - n1 cos tt)/(n2 cos ti + n1 cos tt);
  R = |r|^2.
- **Brewster:** tan(th_B) = n2/n1 gives Rp = 0.
- **Dispersion:** Schott N-BK7 Sellmeier coefficients (`constants.py`), valid 0.3-2.5 um.
- **Assumptions:** planar, isotropic, non-magnetic, lossless (real n), monochromatic, no surface roughness, no
  thin-film interference.
- **Validation:** OPT-01 to OPT-06.
- **Not modelled:** absorption (complex index), scattering, polarisation transfer through media, diffraction, thin film.

## M5. Linear acoustics (`acoustics.py`)

- **Wave speed:** c = sqrt(gamma R T / M) for ideal gases; c = sqrt(K/rho) for plane waves in a fluid.
- **Impedance:** Z = rho c.
- **Normal-incidence intensity coefficients:** R = ((Z2 - Z1)/(Z2 + Z1))^2, T = 4 Z1 Z2/(Z1+Z2)^2, R + T = 1.
- **Doppler:** f' = f (c + v_o) / (c - v_s), sign convention documented in the code.
- **Resonances:** closed-open pipe f_n = (2n - 1) c/(4L); fixed-fixed string f_n = (n/2L) sqrt(T/mu).
- **Assumptions:** linear (small amplitude), homogeneous medium, plane waves, no absorption, no dispersion.
- **Validation:** ACOU-01 to ACOU-06.
- **Not modelled:** propagation (FDTD), reverberation, modal synthesis, nonlinear shock.

## M6. Material failure (`fracture.py`)

### M6a. Linear-elastic fracture (brittle solids)
- **Stress intensity:** K_I = Y sigma sqrt(pi a), a = half-length of an internal flaw; Y = 1 for a centre crack
  in an infinite plate (a geometry factor must be supplied for other specimens).
- **Failure:** K_I >= K_Ic. Critical stress sigma_c = K_Ic / (Y sqrt(pi a)). Critical flaw a_c = (1/pi)(K_Ic/(Y sigma))^2.
- **Griffith energy:** G = K_I^2 / E' (E' = E in plane stress, E/(1-nu^2) in plane strain). Effective surface energy
  gamma = G/2.
- **Assumptions:** linear-elastic, small-scale yielding, single flaw, quasi-static loading, uniaxial tension.
  Real glass strength is governed by the largest flaw in a population, so a single-flaw model is an estimate.
- **Validation:** FRAC-01 (133.8 MPa for a 10 um flaw), FRAC-02 (round trip), FRAC-03 (Griffith energy 3.9 J/m^2 for glass),
  FRAC-04 (glass fractures and steel survives the same case).

### M6b. Yield (ductile metals and plastics)
- **Criterion:** uniaxial sigma >= sigma_y (von Mises reduces to |sigma| under uniaxial stress).
- **Assumptions:** no hardening, no strain-rate effect, no triaxiality effect, no fatigue.
- **Limit:** only the first yield event is predicted. Plastic flow, necking and fracture of ductile metals are not
  modelled.

### M6c. Not covered
Elastomers (rubber) and granular media (sand, soil) have no failure model in this release. `assess()` raises an error for them
instead of returning a guess.

## M7. Euler-Bernoulli beams (`structures.py`)

- **Equation:** E I w'''' = q(x), linear small-deflection theory, plane sections remain plane.
- **Cantilever tip load:** delta = F L^3/(3 E I); root bending stress sigma = F L c/I; I = b h^3/12 for a rectangle.
- **First natural frequency:** omega_1 = (beta_1 L)^2 sqrt(E I/(m' L^4)), beta_1 L = 1.8751040687.
- **Validation:** STRU-01 (double integration of curvature vs closed form, trapezoidal, 4000 cells: error 1.6e-8),
  STRU-02 (frequency constant 3.516015), STRU-03 (section inertia).
- **Assumptions:** slender beam (L/h >~ 10), linear elastic, small slope, no shear deformation, no damping.
- **Not modelled:** Timoshenko (shear) beams, plates, shells, torsion, buckling, contact.

## M9. Physical objects (`objects.py`, Phase 2 first slice)

A `PhysicalObject` is a rigid, uniform-density solid (sphere, box or cylinder) with a material, a temperature and a
translational state. Everything below is in SI units and dimension-checked.

- **Mass and volume:** m = rho V, with V = (4/3) pi r^3 (sphere), a b c (box), pi r^2 h (cylinder).
- **Centre of mass:** the geometric centre of the shape, because density is uniform. Composite objects are not implemented.
- **Principal moments of inertia about the centre of mass** (body frame, shape axes):
  - sphere: I = (2/5) m r^2 about any axis through the centre;
  - box: I_x = m (b^2 + c^2)/12 and cyclic permutations;
  - cylinder: transverse I = m (3 r^2 + h^2)/12, axial I_z = m r^2 / 2.
  These are standard centroidal results (Beer & Johnston, *Vector Mechanics for Engineers*, Appendix / moment-of-inertia tables).
- **Inertia about another point:** parallel-axis theorem, I' = I_cm + m (|d|^2 E - d d^T). The trace identity
  tr(I') = tr(I_cm) + 2 m |d|^2 is tested.
- **Weight:** m g with standard gravity g = 9.80665 m/s^2 (or a supplied g).
- **Kinetic energy:** (1/2) m |v|^2 (translation only).
- **Heat capacity:** m c_p (J/K), assuming a uniform temperature.
- **Melting state:** compares the object temperature with the material melting temperature, if one is stored.
- **Validation:** OBJ-01..08 (`validation.py`): mass, sphere/box/cylinder inertia, the surface-point parallel-axis value
  (7/5 m r^2), weight of ice, and heat capacity of water. Unit tests: `reality/tests/test_objects.py`.
- **Not covered:** orientation and 3D rotation dynamics, non-uniform density, temperature-dependent properties,
  anisotropy, and contact (see `LIMITATIONS.md`).

## M8. Dimensional validation (`units.py`, `materials.py`)

- Quantities carry SI dimension vectors with rational exponents. Addition and assignment across dimensions raise
  `DimensionError`. Example: `Q(0.75e6, FRACTURE_TOUGHNESS)` is Pa*sqrt(m), so it cannot be added to a stress.
- Material properties are validated against physical ranges (positive density, Poisson ratio in (-1, 0.5),
  brittle solids must define K_Ic, ductile metals must define yield strength, and so on).
- **Validation:** MAT-01 (all built-in materials valid), MAT-02 (fracture toughness dimension bound); unit tests in
  `reality/tests/test_units.py`.

## M10. Rigid-body rotation (`rigidbody.py`, Phase 3)

State: centre of mass position x, velocity v, unit quaternion q (body to world), body angular velocity omega_b,
principal inertias I = (I1, I2, I3) about the body axes.

- **Equations of motion (body frame):** Euler's equations  I1 omega1' = (I2 - I3) omega2 omega3 + tau1, and cyclic.
- **Attitude:** q' = (1/2) q (x) (0, omega_b). Integrated by RK4; renormalised after every step.
- **Exact torque-free increment:** for constant omega, q <- q (x) exp(omega h / 2), with the quaternion exponential.
- **Invariants checked:** kinetic energy T = (1/2) sum I_i omega_i^2 and |L| with L_i = I_i omega_i are conserved for
  torque-free motion.
- **Symmetric top precession:** I1 = I2, torque-free, omega1 = omega1(0) cos(Omega t), Omega = (I3 - I1) omega3 / I1.
  Validated as RB-01 (period), RB-02..03 (conservation), RB-05 (quaternion norm). RB-04 checks omega = tau t / I
  under a torque along a principal axis.
- **Limitation:** one body, no joints. Inertia is input; `PhysicalObject` does not yet carry orientation.

## M11. Sphere-plane contact (`contact.py`, Phase 3)

Per step h, for a solid sphere of radius R on the plane {x : n.x = d}:

1. Predict v <- v + g h; x_pred = x + v h.
2. Contact if n.x_pred - d - R < 1e-9 m.
3. Normal impulse J_n = -(1 + e) v_n / K_nn, with K_nn = 1/m for a sphere (isotropic inertia, contact offset along n).
4. Friction: K_t J_t = -v_t (sticking). If |J_t| > mu J_n, use kinetic friction J_t = -mu J_n v_t/|v_t|.
5. Move with the post-impulse velocity, project out any normal penetration, then rotate with the post-impulse omega.

Analytic references (standard textbook results for a solid sphere):

- **Restitution:** rebound speed e v, apex height e^2 h (CON-01, relative tolerance 5e-3 at dt = 1e-4 s; measured
  1.3e-3).
- **Rolling down a plane at angle theta, no slip:** a = (5/7) g sin theta (CON-02, measured error 5e-15).
- **Frictionless slide:** a = g sin theta (CON-03).
- **Kinetic-friction slide:** a = g (sin theta - mu cos theta) (CON-04). Slip persists when mu < (2/7) tan theta.
- **Slide-to-roll on a horizontal floor:** v_final = (5/7) v0 with zero slip (CON-07).
- **Rolling constraint:** the contact-point velocity is zero when rolling (CON-05).

Limits: one contact point, planes only, no continuous collision detection, no contact-pair coefficient database.
Those are in `LIMITATIONS.md` §2.

## M12. Brittle failure statistics (`weibull.py`, Phase 4)

- **Failure probability (Weibull 1951):** P_f = 1 - exp(-(V/V0)(sigma/sigma0)^m). Ledger entry 8.
- **Median strength:** sigma_50 = sigma0 (ln 2 / (V/V0))^(1/m). Strength falls with volume as V^(-1/m) (size effect;
  WEIB-02).
- **Effective volume:** V_eff = sum V_i (sigma_i / sigma_ref)^m. Reduces to total volume for a uniform field (WEIB-05).
- **Fit:** median ranks F_i = (i - 0.3)/(n + 0.4) (Bernard's approximation, not yet in the ledger), then linear
  regression of ln(-ln(1 - F)) on ln(sigma). Round trips on model-generated data recover m and sigma0 to 1e-9 (WEIB-03..04).

## M13. Hydrostatics (`hydrostatics.py`, Phase 7)

- **Pressure at depth:** p = p_surface + rho g h (linear in depth; HYD-01 at 10 m of water).
- **Buoyancy (Archimedes):** F_b = rho_fluid g V_submerged.
- **Floating fraction:** rho_object / rho_fluid for a body that floats (HYD-02, ice in water: 0.9187). A body that sinks is
  capped at 1, which is a bound, not an equilibrium.
- **Apparent weight:** m g - F_b (HYD-03, fully submerged steel sphere: 1 - rho_w/rho_s).

Static only. No flow, no compressibility, no free-surface dynamics.

## M14. Explicit 2D conduction (`thermal2d.py`, Phase 8)

- **Equation:** dT/dt = alpha (T_xx + T_yy) on [0, L]^2, T = 0 on the edges.
- **Scheme:** FTCS, dt = Fo dx^2 / alpha with Fo <= 1/4 (the 2D explicit stability limit).
- **Reference:** T = exp(-2 pi^2 alpha t / L^2) sin(pi x/L) sin(pi y/L). The test case uses N = 31 interior nodes,
  alpha = 0.01 m^2/s, t = 5 s. The max relative error is 1.1e-3 (THER-06, tolerance 5e-3).

## M15. Population benchmarks (`biology.py`, Phase 9)

These are textbook population models. They are numerical benchmarks, not biological models.

- **Logistic (Verhulst):** dN/dt = r N (1 - N/K). Closed form N(t) = K / (1 + ((K - N0)/N0) e^(-rt)). RK4 agrees
  with it to 1.5e-11 relative (BIO-01).
- **Lotka-Volterra:** dx/dt = alpha x - beta x y, dy/dt = delta x y - gamma y. First integral
  H = delta x - gamma ln x + beta y - alpha ln y is constant. Relative drift over 40 time units: 1.6e-15 (BIO-02).

