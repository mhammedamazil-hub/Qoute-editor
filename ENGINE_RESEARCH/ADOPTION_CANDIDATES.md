# ADOPTION_CANDIDATES

**No prioritised proposals (no Tier 1/2/3) and no rejections yet.** The directive asks for prioritised proposals after
Phase 7 completes. Phase 7 is committed (`6b3d324`) but not complete: `reality/BOX_BOX_STUDY.md` §7 lists open items. Tiers
would be premature, so this file lists candidates with their status and the evidence each one would need.

Nothing listed here is adopted. No code is copied from any project. The solver is not replaced by another engine's design.

| # | Candidate | Source of the idea (fact) | Reality status | Evidence needed before any change |
|---|---|---|---|---|
| 1 | Four-point manifold reduction (deepest, farthest, tangent extremes) | Rapier `src/geometry/manifold_reduction.rs`, `reduce_manifold_naive` | Reality keeps all clipped vertices (`box_box.py`) | Build it as an experiment on the box-plane and box-box paths. Measure sweeps needed to reach the tested stack spins and penetration, against the current code. Confirm the sphere regression tests still pass. Hypothesis only: it may lower the 128-sweep requirement. |
| 2 | Warm starting of contact impulses | Jolt (on by default), Rapier, ReactPhysics3D, Chipmunk2D (source facts in PHYSICS/) | Tried before (cap-10 code, 8–32 sweeps, no gain). Reverted. | `reality/BOX_BOX_STUDY.md` §1.1 says not to retry without a new hypothesis. A new one would be: warm start at 128 sweeps with the current projection. Must be stated before the run. |
| 3 | A bounding-volume broadphase (AABB tree or sweep-and-prune) | Rapier BVH, Jolt QuadTree, ReactPhysics3D DynamicAABBTree, Chipmunk2D BBTree and sweep-1D, cannon-es SAP | None; pairs are listed by the caller (O(N²)). Measured: N = 100 0.32 s/step, N = 500 62 s/step | Architecture decision (pending per `reality/BOX_BOX_STUDY.md` §7). Would need: identical contacts for identical pairs, the sphere regression, and timing at N = 100/500. |
| 4 | Continuous collision for fast, thin bodies | Jolt per-body LinearCast with its documented limits; Box2D `enableContinuous`; Rapier `dynamics/ccd` | None (`LIMITATIONS.md`) | Measure a fast thin-box case first to show that tunnelling happens in Reality's scenes. Without that, not justified. |
| 5 | Soft-contact (spring) formulation for stacks | Box2D (30 Hz, damping 10), Rapier (30 Hz, ζ 10) | Reality uses rigid contacts with position projection | Changes the solver's physics, not just its speed. Needs a full regression of sphere and box tests and the validation suite. Not recommended as a first step; recorded for completeness. |

Rejected: none so far. Re-check after Phase 7 closes.
