# Generalization Report (Phase 4)

- seed: 11 · tasks per axis: 1 · fingerprint: `af2acab3d786f7fb`
- baseline: frozen library (`library_frozen.json`, a9bbfce5ee3e561b) — never updated by this run
- leakage check: **clean**

| axis | tasks | frozen baseline | system | lift |
|---|---|---|---|---|
| unseen_family | 1 | 0.000 | 0.000 | +0.000 |
| larger_input | 1 | 1.000 | 1.000 | +0.000 |
| shifted_distribution | 1 | 1.000 | 1.000 | +0.000 |
| representation_shift | 1 | 1.000 | 1.000 | +0.000 |
| multi_step | 1 | 1.000 | 1.000 | +0.000 |
| combination | 1 | 0.000 | 1.000 | +1.000 |
| adversarial | 1 | 1.000 | 1.000 | +0.000 |

**Mean across axes:** baseline 0.714 → system 0.857 on 7 tasks.

## Per-task results

| axis | task | baseline | system | note |
|---|---|---|---|---|
| unseen_family | `group_sum_s11_00` | fail | fail | acquisition exhausted |
| larger_input | `abs_all_s11_00` | pass | pass | reused acquired program |
| shifted_distribution | `abs_all_s11_00` | pass | pass | reused acquired program |
| representation_shift | `abs_all_s11_00` | pass | pass | reused acquired program |
| multi_step | `scale_then_running_s11_00` | pass | pass | reused acquired program |
| combination | `combo_s11_00` | fail | pass | acquired in 200 candidates |
| adversarial | `adversarial_scale_s11_00` | pass | pass | reused acquired program |

## Limits

- Hypothesis search is bounded by the candidate grammar; an axis where both arms fail says the grammar is short, not that the task is impossible.
- `representation_shift` changes wording only; it does not test a second human language.
- Boundary draws are sampled, not exhaustive.
- The frozen baseline is a snapshot of the library, not a retrained model.
