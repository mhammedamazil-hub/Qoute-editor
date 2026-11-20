# NUMERICAL_METHODS - PROJECT REALITY

Choices of numerical method, their order of accuracy, stability limits, error sources, and how each limit is
enforced in code. The principle is: accuracy and performance trade-offs are explicit parameters, never hidden.

## 1. Time integration

### 1.1 Classical Runge-Kutta 4 (`integrators.rk4_step`, `integrate_rk4`)
- **Problem class:** general non-stiff ODE y' = f(t, y).
- **Order:** local error O(h^5), global O(h^4). The global error ratio when h is halved is ~16. This is tested
  (`test_rk4_exact_for_exponential_decay_order`).
- **Stability:** conditionally stable; the step must satisfy h |lambda| <~ 2.8 for real negative lambda.
- **Energy behaviour:** not symplectic. For conservative systems energy drifts slowly. Use Verlet for those.
- **Used by:** quadratic-drag free fall, pendulum (validated against the exact period), lumped cooling.

### 1.2 Velocity Verlet (`integrators.velocity_verlet_step`)
- **Problem class:** second-order conservative system x'' = a(x).
- **Order:** global O(h^2); symplectic and time-reversible.
- **Energy:** bounded oscillation of the energy error (no secular drift). Verified on harmonic oscillator
  (`test_verlet_conserves_harmonic_energy_boundedly`) and on Kepler orbits (MECH-14, MECH-15).
- **Exact for constant acceleration:** projectile trajectories are reproduced exactly; the remaining errors
  (MECH-04 6e-8, MECH-05 1e-8) come from the landing interpolation.
- **Used by:** Kepler orbits, projectile.

### 1.3 Time-step selection
- Orbits: dt = 1e-3 for a unit-period orbit (about 6283 steps per period). Period error 2e-6 (MECH-13).
- Pendulum (RK4): dt = 2e-3 for a 2 s period, period error 4e-10 (MECH-08).
- Conduction: dt set by the stability limit (see section 2).

## 2. Spatial discretisation: 1D conduction (`thermal.conduction_1d_explicit`)

- **Scheme:** FTCS, forward Euler in time, second-order central differences in space.
  T_i^{n+1} = T_i^n + Fo (T_{i+1}^n - 2 T_i^n + T_{i-1}^n), Fo = alpha dt / dx^2.
- **Order:** O(dt, dx^2).
- **Stability:** von Neumann analysis gives Fo <= 1/2. The solver raises `ValueError` when Fo > 0.5 (with a
  1e-12 tolerance). This is an error, not a silent clamp.
- **Maximum principle:** with Fo <= 1/2, the scheme preserves bounds (tested with boundary 100 degC and
  interior 20 degC).
- **Accuracy:** at Fo = 0.4 and 41 nodes, max |theta - theta_exact| = 1.6e-5 (THER-02). The temporal error at Fo = 0.4
  dominates the spatial error; this was not separated further.
- **Cost:** O(N) per step, N cells. Measured 1.2e7 cell-updates/s for N = 101 and 1001 on this machine
  (`PERFORMANCE_REPORT.md`).
- **Upgrade path:** Crank-Nicolson or backward Euler (unconditionally stable) for large dt; tridiagonal solver (Thomas
  algorithm) for each step.

## 3. Phase change: energy balance (`thermal.metal_on_ice_equilibrium`)

- **Method:** closed-form energy balance. No time stepping.
- **Assumptions:** no heat loss, adiabatic, isothermal ice at 0 degC, uniform metal temperature (lumped).
- **Conservation check:** THER-04 verifies m_m c_m (T_m - T_f) = m_i (L + c_w T_f) to 1e-16 relative residual.
- **Upgrade path:** enthalpy method on a spatial grid (fixed-grid Stefan problem, Voller & Prakash 1987 [verify]).

## 4. Root finding and special functions

- **Complete elliptic integral K(m):** arithmetic-geometric mean. Converges quadratically; 4-5 iterations
  to double precision for m < 1. Verified against the A&S Table 17.1 value K(0.5) = 1.8540746773013719
  (`test_complete_elliptic_k_known_values`).
- **Numerical cancellation:** ln cosh(x) for small x is computed as log1p(2 sinh^2(x/2)) to avoid the loss of
  precision in ln(1 + x^2/2). This was a real bug caught by the test suite (free-fall distance was off by 4e-6).

## 5. Spatial discretisation: beams (`structures.cantilever_deflection_by_double_integration`)

- **Method:** trapezoidal rule applied twice to the curvature kappa = M/(EI) with clamped boundary conditions.
- **Order:** O(dx^2). Verified by convergence check (`test_double_integration_converges_to_analytic_with_refinement`)
  and the STRU-01 case (error 1.6e-8 with 4000 cells).
- **Lesson recorded:** an earlier version used a one-sided cell sum, which gave an O(dx) bias (error 1.9e-4). The
  trapezoidal version fixed it.

## 6. Quadrature in validation

- Trapezoid and midpoint rules are used only where stated. Quadrature error is included in each case's tolerance.

## 7. Floating-point policy

- All computations are IEEE-754 double precision, pure Python floats.
- Tolerances are relative (or absolute when the reference is zero) and documented per case in `VALIDATION_REPORT.md`.
- `units.check_finite` raises on NaN or infinity; it is intended for solver inputs and outputs.

## 8. Determinism

- The pure-Python kernels are deterministic for identical inputs (no randomness, no threading).
- Cross-platform bit-exactness is not guaranteed for transcendental functions (libm differences). Validation
  tolerances are chosen well above that level.

## 9. Known numerical limitations

| Area | Limitation | Plan |
|---|---|---|
| Free fall | RK4 with fixed step; step must resolve g t / v_t dynamics | Adaptive step control (Dormand-Prince) |
| Contact | No contact solver yet, so no stiff-contact stability analysis | Sequential impulses with restitution and friction, then CCD |
| Conduction | Explicit only; dt limited to Fo <= 1/2 | Implicit solver for large dt |
| Orbits | Verlet with fixed dt; close encounters need smaller dt | Adaptive or regularised (Kustaanheimo-Stiefel) integrators |
| Beams | Closed-form and trapezoidal only; no FEM | Finite-element beams, Timoshenko shear |
| Acoustics | No spatial propagation solver | FDTD on a staggered grid |

## 10. Collision and contact (general solver)

- Predict, detect at predicted positions, then sequential impulses with Coulomb friction (per-contact 2x2 tangential
  block), then the exact rotation, then position projection (repeated to `PROJECTION_TOL` 1e-12 m, at most 40 passes;
  the cap was 10 until a three-box impact at the bake step needed more, see `BOX_BOX_STUDY.md` §5). Box-containing steps
  use at least 128 sweeps (`BOX_MANIFOLD_ITERATIONS`, measured in `BOX_BOX_STUDY.md` §1). The order matches the existing
  sphere solver, so the two agree (section 5 of `COLLISION_GEOMETRY.md`: below 1e-11 for single bodies and pairs, 2.6e-10 m for a
  two-sphere stack).
- Contact normals point from `a` to `b`. Edge and vertex contacts dominated by a strictly closer face contact are removed
  (internal-edge handling). Normals within cos > 0.999 are merged per contact cluster. The threshold is a modelling
  choice, not a measured constant.
- Closest point on a triangle: Voronoi-region method. The test checks 3,000 random triangles over 1e-6 to 1e3 m scales
  against brute force (asserted relative error below 1e-12). An earlier inline check of 4,000 cases measured 8.5e-16.
- Mesh BVH: median split, leaf size 4. Agreement with brute force as a set of contacts, rounded to 14 decimals, on the
  test meshes (section 7 of `COLLISION_GEOMETRY.md`).
- First-order accuracy: the first-rebound apex error of an elastic bounce is about 4.4 dt metres (4.43e-3 m at dt 1e-3,
  4.43e-4 m at 1e-4, 4.43e-5 m at 1e-5).
- No continuous collision detection, no warm starting (tried; not adopted, `BOX_BOX_STUDY.md` §1.1). Tunnelling is not detected.
- Quaternion update: rotation is exact for the post-impulse body-frame angular velocity, including the gyroscopic
  term. A missing gyroscopic term was found and fixed in Phase 7 (free-flight error 1.04 rad/s before, 3e-13 after,
  `BOX_BOX_STUDY.md` §2). `rigidbody.norm` and `rigidbody.dot` sum three components only; use `rigidbody.quat_norm` for quaternions.
