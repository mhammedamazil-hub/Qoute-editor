# Generalization Report (Phase 4)

- seed: 41 · tasks per axis: 2 · fingerprint: `9aa90b06d3bb34c9`
- baseline: frozen library (`library_frozen.json`, a9bbfce5ee3e561b) — never updated by this run
- leakage check: **clean**

| axis | tasks | frozen baseline | system | lift |
|---|---|---|---|---|
| unseen_family | 2 | 0.000 | 0.000 | +0.000 |
| larger_input | 2 | 1.000 | 1.000 | +0.000 |
| shifted_distribution | 2 | 1.000 | 1.000 | +0.000 |
| representation_shift | 2 | 1.000 | 1.000 | +0.000 |
| multi_step | 2 | 0.500 | 0.500 | +0.000 |
| combination | 2 | 0.000 | 0.500 | +0.500 |
| adversarial | 2 | 0.500 | 0.500 | +0.000 |

**Mean across axes:** baseline 0.571 → system 0.643 on 14 tasks.

## Per-task results

| axis | task | baseline | system | note |
|---|---|---|---|---|
| unseen_family | `group_sum_s41_00` | fail | fail | acquisition exhausted |
| unseen_family | `rename_keys_s41_01` | fail | fail | acquisition exhausted |
| larger_input | `running_total_s41_00` | pass | pass | reused acquired program |
| larger_input | `sum_even_s41_01` | pass | pass | reused acquired program |
| shifted_distribution | `running_total_s41_00` | pass | pass | reused acquired program |
| shifted_distribution | `sum_even_s41_01` | pass | pass | reused acquired program |
| representation_shift | `running_total_s41_00` | pass | pass | reused acquired program |
| representation_shift | `sum_even_s41_01` | pass | pass | reused acquired program |
| multi_step | `scale_then_running_s41_00` | pass | pass | reused acquired program |
| multi_step | `even_then_scale_s41_01` | fail | fail | reused acquired program |
| combination | `combo_s41_00` | fail | fail | acquired in 200 candidates |
| combination | `combo_s41_01` | fail | pass | acquired in 200 candidates |
| adversarial | `adversarial_scale_s41_00` | pass | pass | reused acquired program |
| adversarial | `impossible_network_4_s41_01` | fail | fail | reused acquired program |

## Limits

- Hypothesis search is bounded by the candidate grammar; an axis where both arms fail says the grammar is short, not that the task is impossible.
- `representation_shift` changes wording only; it does not test a second human language.
- Boundary draws are sampled, not exhaustive.
- The frozen baseline is a snapshot of the library, not a retrained model.
