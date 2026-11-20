# Box–box collision: mathematics

Companion to `BOX_BOX_RESEARCH.md` (audit, sources, design) and `BOX_BOX_REFERENCES.md` (source verification). Every formula
here is derived in this document or is stated with its source. Where a fact is a standard result that is not derived here,
the text says so. Constants are listed with their derivation in `BOX_BOX_RESEARCH.md` §3.3.

---

## 1. Notation and box parametrisation

Box `X ∈ {A, B}` has:

- centre `c_X ∈ ℝ³` (the centre of mass, because the box is uniform);
- rotation `R_X = [e_X0 e_X1 e_X2]`, orthonormal columns, the body axes in world coordinates (`det R = +1`);
- half edge lengths `h_X = (h_X0, h_X1, h_X2)`, all > 0.

A point of `X` in world coordinates is `c_X + Σ_k s_k h_Xk e_Xk` with `s_k ∈ [−1, 1]`. Its vertices are the 8 choices
`s ∈ {±1}³`. Its faces are the 6 pairs `s_k = ±1`, and its edges are the 12 lines where two of the `s_k` are fixed at ±1.

Let `d = c_B − c_A`. Let `S = max_k h_Ak + max_k h_Bk`, the length scale of the pair. All tolerances below are multiples of
`S`, or the absolute `TOUCH_TOL = 1e-9 m`.

### 1.1 Support radius and separation along an axis

For a unit vector `u`, the projection of box `X` onto `u` is the interval `[c_X·u − r_X(u), c_X·u + r_X(u)]` with

    r_X(u) = Σ_k h_Xk |e_Xk · u|.            (1)

This follows from the projection of a point `c + Σ s_k h_k e_k` onto `u`, maximised over `s ∈ [−1,1]³`. Each term
contributes `h_k |e_k·u|` at most.

Define the **separation** and **overlap** along `u`:

    s(u) = |d · u| − r_A(u) − r_B(u),        o(u) = −s(u).          (2)

`s(u) > 0` means the projections are disjoint along `u`. `o(u) > 0` means they overlap by `o(u)` along `u`.

---

## 2. Separating axis test with 15 candidate axes

**Candidate set.** For two oriented boxes the candidates are (Eberly, excerpt; see `BOX_BOX_REFERENCES.md` R2):

- 3 face normals of A: `e_A0, e_A1, e_A2`;
- 3 face normals of B: `e_B0, e_B1, e_B2`;
- 9 edge cross products `L_ij = (e_Ai × e_Bj) / ‖e_Ai × e_Bj‖`, for `i, j ∈ {0,1,2}`.

**Separating axis theorem (for this case).** Two convex polyhedra are disjoint if and only if some candidate separates
them, that is `s(u) > 0` for some candidate `u`. The "if" direction is immediate from (2), since any `u` with `s(u) > 0`
gives disjoint projections. The "only if" direction is the completeness of the candidate set for polyhedra, which Eberly
states for OBBs. It is **not proven here**. It is tested numerically in §9, against an oracle that does not use this set.

**Degenerate edge axes.** If `‖e_Ai × e_Bj‖ < PAR_SIN` (the sine of the angle between the two edges), the cross product has
no reliable direction and the candidate is skipped. Two cases occur in practice: exactly parallel edges give a zero cross
product, and two candidates can coincide (in the §5.2 case, `e_A1 × e_B2 = e_A0`, so E12 duplicates A0, and `e_A2 × e_B2 = 0`
is skipped; 14 candidates remain).

`PAR_SIN = √ε ≈ 1.49e-8`, with `ε = 2.2e-16`, is chosen by balancing two errors:

- **Rounding error of the axis.** The components of `e_Ai × e_Bj` have absolute error about `2ε`. Normalising by
  `sinθ = ‖e_Ai × e_Bj‖` gives a direction error `δ ≈ 2ε / sinθ`. Moving `u` by `δ` changes `s(u)` by at most
  `(‖d‖ + Σ_X h_X) δ ≤ (√3 + 3) S δ`, since for pairs in contact range `‖d‖ ≤ ‖h_A‖ + ‖h_B‖ ≤ √3 S` and `Σ h ≤ 3 S`.
  This error **grows as the axis gets more ill-conditioned**, that is as `sinθ` falls.
- **Error from skipping.** A nearly parallel edge pair contributes a thin facet to the Minkowski difference (§3). Its length is
  of order `sinθ · S`, so the boundary of the difference without that facet differs from the true boundary by about
  `c · sinθ · S`, for a constant `c` of order one. This is an argument, not a proof, and the tests measure it (§9.1).
  This error **grows with `sinθ`**.

The two errors balance where `2ε/sinθ ≈ c · sinθ`, that is `sinθ ≈ √(2ε/c)`. The constant chosen is `√ε`. The resulting
depth error is of order `√ε · S ≈ 1.5e-8 · S`. This is **larger than `TOUCH_TOL` for `S` near 1 m**. It is a stated limit,
not hidden: it affects depth only in the near-parallel configurations where the skipped facet would have been the minimum.
The tests report the measured error at several `sinθ`.

Skipping an axis removes a candidate and cannot make a separated pair look overlapped. It can make an overlapped pair report
a slightly larger minimum overlap. The face axes stay in the set, so the pair is never lost. `PAR_SIN` applies only to edge
candidates.

**Decision rule.** Compute `s_max = max over candidates u of s(u)`, with the best candidate recorded. If `s_max > TOUCH_TOL`,
the pair is separated and returns no contact. Otherwise it is touching or penetrating, with penetration depth
`δ = −s_max ≥ −TOUCH_TOL`.

**Face preference.** A face candidate wins over an edge candidate unless the edge's separation exceeds the best face
separation by more than `FACE_TIE · S`, with `FACE_TIE = 1e-6`. The reason is in `BOX_BOX_RESEARCH.md` §3.3.

---

## 3. Penetration depth is the minimum overlap over the candidates (minimum translation)

**Claim.** Let P, Q be convex polytopes with overlapping interiors, so the origin lies in the interior of the Minkowski
difference `K = P ⊕ (−Q)`. The penetration depth, the smallest distance the origin must travel to leave `K` (the least
translation that separates P and Q), is the distance from the origin to the boundary of `K`. It equals

    δ = min over unit u of h_K(u) = min over facet normals u of K of h_K(u),          (3)

where `h_K(u) = max_{k∈K} k·u` is the support function. The second equality holds because `h_K` is linear on each cone of
the normal fan of `K`, so its minimum over the unit sphere is attained at a ray of the fan, that is a facet normal.

**Candidate set contains the facet normals of K.** The normal fan of a Minkowski sum is the common refinement of the normal
fans of its summands (a standard fact about Minkowski sums of polytopes). The rays of the common refinement are the rays of
either fan and the intersections of 2-dimensional cones of the two fans. These are the face normals of P, the face normals
of −Q, and the directions perpendicular to a pair of non-parallel edges, that is cross products of edge directions. This is
the 15-axis set of §2.

**Evaluating (3) on a candidate.** For a unit candidate `u`, `h_K(u) = h_P(u) + h_{−Q}(u)` and
`h_P(u) = c_P·u + r_P(u)`, `h_{−Q}(u) = −c_Q·u + r_Q(u)`. Hence `h_K(u) = r_A(u) + r_B(u) − d·u`. The minimum over
`u ∈ {L, −L}` of `h_K` is `r_A(L) + r_B(L) − |d·L| = o(L)`. So

    δ = min over candidates L of o(L),  with  o(L) = r_A(L) + r_B(L) − |d·L|.          (4)

Equation (4) is the basis of the implementation. It is also the **dense-direction check** of §9: sampled directions give an
upper bound on `δ`, which the SAT value must not exceed.

---

## 4. Contact generation

### 4.1 Normal orientation

The contact normal points from A to B, matching `narrow.Contact`. For a candidate axis `L` the oriented normal is

    n = σ L,   σ = sgn(d · L) for d · L ≠ 0.                                              (5)

When `d · L` is zero (for example coincident boxes, or a candidate perpendicular to the centre line), the sign is set by
`narrow._canonical_sign`: the first non-zero component is made positive. This rule does not depend on the order of the
inputs, so the result is deterministic. The depth is the same for either sign.

### 4.2 Face contact: reference face, incident face, clipping

**Owner and reference.** The best candidate is a face axis of owner `R ∈ {A, B}` with index `k`. Let `ν` be the outward
normal of R's face toward the other box `I`:

    ν = sgn(d_R · e_Rk) e_Rk,    where d_A = d and d_B = −d.                       (6)

The contact normal is `n = ν` if `R = A`, and `n = −ν` if `R = B`. Depth is `δ = o(e_Rk)` by (4).

**Incident face.** Choose the face of `I` most opposed to `ν`:

    m = argmax over j of |ν · e_Ij|,      μ = −sgn(ν · e_Im) e_Im.                      (7)

`μ` is the outward normal of that face of I. It points toward R. The 4 corners of this face are

    x_{σ} = c_I + h_Im μ + Σ_{j≠m} σ_j h_Ij e_Ij,     σ ∈ {±1}² (one entry per j ≠ m).           (8)

**Proposition 4.1 (the deepest point of I along ν is a corner of the incident face).** Let `x*` minimise `x·ν` over I. Then
`x*` is a corner of the face `μ`.

*Proof.* The minimiser of `x·ν` over a box is the vertex with coordinates `s_j = −sgn(ν·e_Ij)` in the box frame. Its
coordinate along the axis `m` is `s_m = −sgn(ν·e_Im)`, which is the face of (7), since `h_Im μ = −sgn(ν·e_Im) h_Im e_Im`.
So `x*` lies on the face `μ`, and it is one of its 4 corners. ∎

**Proposition 4.2 (depth of the deepest point equals the SAT overlap).** Let the owner be R with face axis `e_Rk` and
outward normal `ν` from (6). Let `x*` be the point of I that minimises `x·ν`. Its depth below the owner's face plane is
`δ_x* = h_Rk − (x* − c_R)·ν`. If `x*` lies over the footprint of the face (§4.3), then `δ_x* = o(e_Rk)`.

*Proof.* The minimum of `x·ν` over I is `c_I·ν − r_I(ν)` by (1). So `δ_x* = h_Rk − (c_I − c_R)·ν + r_I(ν)`. Let `d_R = c_I − c_R`
(this is `d` for R = A and `−d` for R = B). By (6), `d_R·ν = |d·e_Rk| ≥ 0`, and `r_R(e_Rk) = h_Rk`. Hence
`δ_x* = r_R(e_Rk) + r_I(e_Rk) − |d·e_Rk| = o(e_Rk)`. ∎

Proposition 4.2 is an **analytic identity** the tests check: for a face-axis minimum, the largest depth in the manifold equals
the SAT depth when the deepest corner lies over the footprint.

**Clipping.** Let `(p, q)` be the two other axes of R. The footprint of R's face is `|(x − c_R)·e_Rp| ≤ h_Rp` and
`|(x − c_R)·e_Rq| ≤ h_Rq`. Clip the polygon of (8) against these four half-planes with **Sutherland–Hodgman** (CACM 17(1), 1974,
pp. 32–42; `BOX_BOX_REFERENCES.md` R6). Clipping a point `x` against `g(x) ≤ 0` where `g` is affine: keep vertices with
`g ≤ 0`; for each edge `(x_k, x_{k+1})` whose endpoints lie strictly on opposite sides, add the crossing
`x_k + t (x_{k+1} − x_k)` with `t = g_k / (g_k − g_{k+1})`.

**Proposition 4.3 (vertex bound).** The clipped polygon has at most 8 vertices.

*Proof.* Let a convex polygon have `n` vertices and let a half-plane remove `R ≥ 1` of them. A line crosses the boundary of a
convex polygon at most twice, so the clip adds at most 2 crossing vertices, and the output has at most `n − R + 2 ≤ n + 1`
vertices. If `R = 0` the output is `n`. Starting from 4 vertices, four clips give at most 8. ∎

**Depth and contact points.** Each surviving vertex `x` has depth `δ(x) = h_Rk − (x − c_R)·ν` (the signed distance below the
owner's face plane). Keep `x` if `δ(x) ≥ −TOUCH_TOL`. The contact point is the midpoint of `x` and its projection onto the
owner's face plane:

    p(x) = x + ½ δ(x) ν.                                                                  (9)

The midpoint is used because the solver uses one point for both bodies (`BOX_BOX_RESEARCH.md` §1.4). It lies within the
overlap of the two boxes whenever `δ(x) ≥ 0`.

**Deduplication.** Vertices closer than `REL_EPS · S` are merged. The clipping can produce duplicates at polygon corners.

**No reduction.** All surviving vertices are kept. By Proposition 4.3 the count is bounded by 8, so there is no need to
drop points (`BOX_BOX_RESEARCH.md` §2.3).

### 4.3 Footprint and what is excluded

A point of I that is not over the owner's footprint is excluded by clipping. This is correct for a face contact. Such a point
is not in contact with the owner's face. If the deepest point of I is outside the footprint, the minimising axis is an edge
axis and the edge path (§4.4) applies. This is the standard limit of face-based SAT manifolds. The mathematics does not
claim more.

### 4.4 Edge contact: closest points between supporting edges

Let the winning candidate be `L = L_ij`, oriented by (5) as `n`. Both `e_Ai` and `e_Bj` are orthogonal to `L`.

**Supporting edges.** The support set of A in direction `n` is the edge parallel to `e_Ai`, at the corner with signs
`σ_k = sgn(n · e_Ak)` for `k ≠ i` (ties take +1). Its parametrisation is

    P(s) = c_A + Σ_{k≠i} σ_k h_Ak e_Ak + s e_Ai,      s ∈ [−h_Ai, h_Ai].

The support set of B in direction `−n` is the edge parallel to `e_Bj` at signs `τ_k = −sgn(n · e_Bk)` for `k ≠ j`:

    Q(t) = c_B + Σ_{k≠j} τ_k h_Bk e_Bk + t e_Bj,      t ∈ [−h_Bj, h_Bj].

Both are valid because `n ⊥ e_Ai` and `n ⊥ e_Bj`, so each supporting set is the edge itself, and the signs select its end.

**Closest points.** Let `u = e_Ai`, `v = e_Bj`, `w0 = P(0) − Q(0)`, `b = u·v`, `D = 1 − b²`, `dd = u·w0`, `ee = v·w0`. Minimising
`‖w0 + s u − t v‖²` over `s, t ∈ ℝ` gives the normal equations `dd + s − b t = 0` and `ee + b s − t = 0`, so

    s* = (b·ee − dd) / D,     t* = (ee − b·dd) / D,          (valid when D > 0).

**Constrained minimum.** The unconstrained point may lie outside `[−h_Ai, h_Ai] × [−h_Bj, h_Bj]`. The minimum of a convex
quadratic over a rectangle is attained either at the interior critical point, or on one of the four sides, where one
parameter is fixed at its bound. The implementation evaluates all candidates (interior when inside; each side with the other
parameter solved and clamped) and keeps the one with the smallest `‖P − Q‖`. This is exact.

**Contact.** The witness pair `(P*, Q*)` gives the contact point `p = (P* + Q*)/2` and depth `δ = o(L)` from (4).

**Degenerate edges.** The edge path requires `D > 0`. It is reached only with `PAR_SIN ≤ ‖u × v‖`, so
`D = ‖u × v‖² ≥ PAR_SIN²`, which is always positive in floating point. The clamped solution is well defined.

### 4.5 Summary of contact output

| Winning candidate | Feature | Points | Depth | Normal | Point |
|---|---|---|---|---|---|
| Face of R | `face` | 1 to 8 | `o(e_Rk)` at the deepest point; each point has its own depth (9) | `n` (A → B) | midpoint (9) |
| Edge `L_ij` | `edge` | 1 | `o(L_ij)` | `n` (A → B) | midpoint of closest points (§4.4) |

Points with depth below `−TOUCH_TOL` are dropped. If no point remains, the pair is not touching.

---

## 5. Analytic reference values (independent of the code under test)

These are derived by hand here, so the tests can compare against them without using the implementation.

### 5.1 Axis-aligned face–face overlap

Boxes with `e_X = identity`, half extents `h`, centres offset by `d = (d_x, 0, 0)` with `0 ≤ d_x < 2h`. The overlap along x is
`o = 2h − d_x` (by (2) with `r = h`). The contact normal is `(1, 0, 0)` and the depth is `2h − d_x`. The owner face is A's
`+x` face at `x = h`, and the incident face is B's `−x` face at `x = d_x − h`. Each vertex of the incident face has depth
`h − (d_x − h) = 2h − d_x`, and its midpoint (9) is `x = (h + (d_x − h))/2 = d_x/2`.

Concrete instance used in tests: `h = 0.5`, `d_x = 0.8`. Then `o = 0.2`, and the contact x-coordinate is `0.4`.

### 5.2 Rotated face–face overlap (the oracle probe, computed by hand)

A: centre `0`, half `(0.5, 0.5, 0.5)`, identity. B: centre `(0.9, 0.1, 0.2)`, half `(0.5, 0.5, 0.5)`, rotated by `30°` about z.

- `r_B(e_A0) = 0.5(cos 30° + sin 30°) = 0.6830127`.
- `s(e_A0) = |0.9| − 0.5 − 0.6830127 = −0.2830127`, so `o = 0.2830127`.
- Checked over the full candidate set (computed with numpy in the research session, 14 candidates after skipping the
  parallel pair A2, B2): the minimum overlap is A0 `0.283013`, then B0 `0.353590`, then A2 and B2 `0.800000`. A dense sample of
  400 000 directions gives minimum `0.284666` at roughly `(−1, 0, 0.001)`, which is above `0.283013` as (4) requires.
- Midpoint x: the A face at `x = 0.5` and the B back face at `x = 0.9 − 0.6830127 = 0.2169873`. Midpoint `0.3584936`.
- The y and z coordinates are the clipped corners of B's face within A's footprint.

The MuJoCo oracle (wheel 4.0.1) gives depth `0.28301` and midpoint x `0.3585`, consistent with the above.

### 5.3 Edge–edge contact: reference through §7

The edge-impact response for a box is the analytic result in §7. A closed-form edge–edge geometry reference is not stated
here, because one has not been derived and checked by hand. Edge–edge geometry is therefore tested against the closest-point
brute force of §9.6 and the MuJoCo oracle, and that choice is recorded here, not replaced by a guessed value.

### 5.4 Stopping distance of a sliding box (friction only)

A box slides on a horizontal plane with kinetic friction coefficient `μ` and no rotation. The friction force is `μ m g`,
so the deceleration is `a = μ g`, the stopping time is `v0/(μg)`, and the distance is `v0² / (2 μ g)`. This holds exactly
when the friction resultant acts through the centre of mass, which the symmetric four-corner patch of a face-resting box
satisfies. Tests check that the sliding distance matches this within an explicit tolerance and that ω stays zero within a
measured tolerance (the sequential-impulse solver is not exact here).

### 5.5 Restitution, central face impact

A box falls on a fixed face with speed `v0` and restitution `e`. After impact its speed is `e v0`, and the normal impulse is
`J = (1 + e) m v0`. The rotation is zero by symmetry of the four-point face contact (Proposition 5.1).

**Proposition 5.1.** Let a uniform box rest with a face parallel to a plane, with zero angular velocity, and let its four
corners `r_i` (relative to the centre of mass, in world coordinates, with `n` the plane normal) all have the same approach
speed. Then the rigid-body response is a pure translation along `n` with no change of angular velocity.

*Proof.* The rigid-body change in velocity depends only on the net normal impulse `J = Σ j_i` and the net angular impulse
`Σ r_i × j_i n`. For the corners of a rectangle, `r_i = (±a, ±b, −h)` in the body frame, so `Σ r_i = (0,0,·)` and
`Σ_i r_i,x = Σ_i r_i,y = 0`. Take the equal-impulse solution `j_i = J/4`. Then `Σ r_i × n j_i` has components about x and y
equal to `(J/4) Σ (r_i,y, −r_i,x)`, which are zero. Any other solution differs from it by a self-equilibrated impulse
`j'` with `Σ j'_i = 0` and `Σ j'_i r_i = 0` (for example `(1, −1, 1, −1)` on the four corners in order around the rectangle),
which changes no rigid-body velocity. Hence all solutions give the same rigid-body response. ∎

The tests check the restitution speed, the absence of rotation, and the self-equilibrated mode, which the sequential-impulse
solver may produce through rounding. The angular change is measured against a stated tolerance, not assumed to be zero.

### 5.6 Momentum of a central box–box collision

Two boxes with masses `m1, m2` and velocities `v1, v2`, colliding along the normal of a face with the contact at the centre of
the face, have after impact, with restitution `e`:

    v1' = [(m1 − e m2) v1 + (1 + e) m2 v2] / (m1 + m2),
    v2' = [(m2 − e m1) v2 + (1 + e) m1 v1] / (m1 + m2),          (10)

along the normal, and linear momentum `m1 v1 + m2 v2` is conserved. Formula (10) is the standard one-dimensional impulse
result for the normal component; it is derived from `Δp = j` with `v2' − v1' = −e (v2 − v1)`. Rotation is zero for a symmetric
face impact.

---

## 6. Response (integration with the existing solver)

The solver is unchanged in form (`BOX_BOX_RESEARCH.md` §1.3). For each contact `i` with normal `n`, point `p`, lever arms
`r_A = p − x_A`, `r_B = p − x_B` (from the centres of mass), and inverse inertia `I_X⁻¹ = R_X diag(I_X,body⁻¹) R_Xᵀ`:

    K_nn = 1/m_A + 1/m_B + (r_A×n)·I_A⁻¹(r_A×n) + (r_B×n)·I_B⁻¹(r_B×n),
    λ_n ← max(0, λ_n + (v_n,target − v_n) / K_nn),        v_n,target = −e v_n,0 (approaching) or 0.

Friction is the 2×2 tangential system with the Coulomb limit `‖λ_t‖ ≤ μ λ_n`. Both are the existing equations. Inertia of
the box is `I_body = m (h_y² + h_z²)/3` about x, and so on (uniform solid box).

**Linear momentum.** Every impulse is applied as `+j` to one body and `−j` to the other, so `Σ m v` is conserved by the
impulses. The position projection (step 5) changes positions only, so it leaves momentum unchanged. Therefore, with
friction and restitution, `P_total` changes only through gravity and the boundary conditions of static bodies.

**Angular momentum.** An impulse at `p` changes the total angular momentum by `r×j` on one body and `−r×j` on the other, so the
total about the origin is conserved by the contact impulses. The rotation step integrates the body's own angular velocity with an
exact quaternion increment. This does not conserve the world angular momentum exactly for an asymmetric body (Euler's
equations), so the drift is measured, not claimed to be zero.

**Energy.** `E = Σ ½ m v² + ½ ω·I_body ω + Σ m g z`. Restitution `e < 1` dissipates energy by design. For `e = 1` and no
friction, the sequential-impulse solve dissipates only through the discrete approximation, and the drift is measured.

**Static bodies.** A static body has `m⁻¹ = 0` and `I⁻¹ = 0`. Its impulses are zero by the solver's `inv_mass` and `static`
checks, so the formulas above reduce to the contact with a fixed box.

---

## 7. Analytic check for off-centre (edge) impact

For a box whose edge is the first contact, let the body axis `x` be parallel to the edge (a principal axis, so there is no
coupling), and let `d = |r × n|` be the moment arm of the normal impulse about the centre of mass, where `r` is the vector
from the centre of mass to the contact and `n` is the normal. Then `r × n` is along `x` and the normal effective mass in
(6) is

    m_eff = 1 / (1/m + d²/I_x),          I_x = m (h_y² + h_z²)/3.                       (11)

For an impact with normal speed `v0` and restitution `e`, the normal impulse is `J = (1 + e) v0 m_eff`, and the angular
velocity about the edge axis after impact is `ω_x = J d / I_x`. This is (6) evaluated for a contact on a single line of
points. For a symmetric two-corner edge contact, the two impulses are equal by symmetry, so the total is the same as for a
single contact at the edge's midpoint. Tests use it for the edge-impact response. The formula is derived here, not quoted.

---

## 8. Numerical conditioning and precision

- All arithmetic is IEEE double precision (Python `float`).
- The tolerances `TOUCH_TOL` (absolute) and `REL_EPS`, `FACE_TIE`, `PAR_SIN` (relative) are chosen in
  `BOX_BOX_RESEARCH.md` §3.3, and are checked by the tests at several scales.
- Rounding error in `s(u)` is about `ε S`, far below `TOUCH_TOL` for `S` of order 1 m. For `S` of order 1 µm the absolute
  `TOUCH_TOL = 1e-9 m` is a relative tolerance of `1e-3`. This is a documented limit, measured in the scale tests.
- Clipping divides by `g_k − g_{k+1}` only when the endpoints are strictly on opposite sides, so the divisor is nonzero.
- The closest-point division by `D` is safe because `D ≥ PAR_SIN²` (§4.4).

---

## 9. Verification identities used by the tests

1. **15-axis completeness, numerically.** For random box pairs, the SAT minimum overlap (4) is compared with a dense
   sampling of unit directions. The SAT value must not exceed the sampled minimum (it is a minimum over a subset of the
   sphere, so it can only be lower or equal) and must be within the sampling resolution. The sampling uses no SAT code.
2. **Analytic values** from §5.
3. **MuJoCo 4.0.1 oracle** (development only). Contact count, normal, depth and midpoint are compared on random and
   degenerate configurations. Differences are reported, and any difference that is not explained is a failure, not a
   tolerance to widen.
4. **Proposition 4.2** (deepest point equals SAT overlap for a face minimum).
5. **Proposition 4.3** (≤ 8 vertices), checked on random clips.
6. **Closest points** (§4.4) against a brute-force minimisation on a fine grid of `(s, t)`, for both interior and boundary
   minima.
7. **Momentum, restitution and rotation identities** of §5–7, through the solver.

---

## 10. Known approximations (stated in the docs, not hidden)

- Detection at the current orientation (`BOX_BOX_RESEARCH.md` §1.3). Fast rotation can be detected one step late.
- Absolute activation tolerance `TOUCH_TOL`.
- Face manifolds exclude points outside the footprint; the minimising edge axis handles them.
- The projection step pushes out the deepest point of each pair; this is a translation along the pair's normal.
- No warm starting, no continuous collision detection (existing limits).
