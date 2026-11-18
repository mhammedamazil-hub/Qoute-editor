# Phase 4 — measured results

Everything below was produced by a command in this repository, on this machine
(2 CPU, 3,939 MB, Python 3.11.2, no GPU), and every figure names the artifact it
came from. Numbers that are thin are labelled thin. Nothing here is an
extrapolation.

Machine-readable copies:

| What | File |
|---|---|
| generalization, four seeds | `datasets/research/generalization_multi_seed.json` |
| generalization, last run | `datasets/research/generalization_latest.{json,md}` |
| five sleep cycles | `datasets/research/retention5_latest.json` |
| blind benchmark (re-run) | `datasets/research/acquisition_latest.json` |
| transfer / retention / meta | `datasets/research/{transfer,retention,meta}_latest.json` |
| sleep cycle reports | `memory/sleep_logs/latest.md`, `sleep_cycles.report` |

---

## 1. Test suite

```
$ .venv/bin/python -m pytest minicoder/tests -q
133 passed, 1 skipped        (134 collected: 106 pre-existing + 27 Phase 4)
$ .venv/bin/ruff check minicoder/
All checks passed
$ cd minicoder/dashboard && npx tsc --noEmit && npx vite build
clean · 264.24 kB bundle
$ npx vite-node scripts/render-check.tsx
14/14 checks passed
```

No test was weakened or removed to make this pass. The skipped test is the
pre-existing checkpoint-dependent one.

One caveat worth recording: while the full arm benchmark was running in the
background (four CPU-hungry arms), `test_learning_loop_promotes_only_after_fresh_replay`
failed once on a timeout and passed on every subsequent run, alone and in the full
suite. It is a timing-sensitive Phase 2 test, not a Phase 4 regression, and it is
listed here rather than hidden.

---

## 2. The six Phase 3 defects, pinned

| # | Defect observed in Phase 3 | Status | Test |
|---|---|---|---|
| 1 | a question answered with a raw tool trajectory | fixed | `test_no_raw_trajectory_in_an_answer` |
| 2 | a question reached the planner and mutated the canvas | fixed | `test_a_question_never_mutates_the_canvas` |
| 3 | introspection could not see an existing sleep report | fixed | `test_introspection_reads_an_existing_sleep_report` |
| 4 | duplicate semantic nodes | fixed | `test_no_duplicate_semantic_nodes`, `test_redundancy_archives_the_weaker_copy_only` |
| 5 | empty skill examples | fixed | `test_skills_without_a_body_never_become_examples` |
| 6 | the acceptance suite wrote to production memory | fixed | `test_acceptance_cannot_write_to_production` |

Defect 6's test is adversarial on purpose: it stubs the acceptance runner so that
it *tries* to write a skill, then asserts production memory is unchanged.

---

## 3. Before / after benchmark

The blind benchmark (A–F arms, eight arms, hidden tests drawn from the private
salt) was re-run after all Phase 4 changes with the same protocol as Phase 3
(seeds 11/23/37, 24 tasks, budget 45 s).

| Arm | Before (Phase 3, `6967e7a`) | After (Phase 4) |
|---|---|---|
| A — model only, no acquisition | 0.000 | **0.000** |
| B — memory retrieval, no acquisition | 0.500 | **0.500** |
| C — acquire + reuse within a family | 0.6061 | **0.6061** |
| D — acquire + cache across tasks | 0.6061 | **0.6061** |
| E — acquire + persist in library | 0.6061 | **0.6061** |
| F1 — depth-1 search only | 0.5455 | **0.5455** |
| F2 — no binary-fragment candidates | 0.4242 | **0.4242** |
| F3 — no row-family candidates | 0.4697 | **0.4697** |

Transfer, after: near-size 32/36 = 0.889, distribution 24/28 = 0.857, edge cases
36/36 = 1.000, cross-domain 32/36 = 0.889. Retention 9/12 families, 9/9 verified
procedures still passing.

**Reading.** Phase 4 added routing, calibration, auditing and new measurements; it
did **not** change the learning result, and this table is the evidence rather than
an assurance. The bit-for-bit match is the useful part: the harness is
deterministic and the integration did not disturb it.

---

## 4. Generalization (M4)

Seven axes × 2 tasks × 4 seeds = **56 hidden evaluations**, every one against a
frozen baseline (`library_frozen.json`, hash `a9bbfce5…`, written once).

| Axis | Baseline | System | Lift |
|---|---|---|---|
| `unseen_family` — no verified program for the family | 0.000 | 0.000 | +0.000 |
| `larger_input` — hidden inputs 2–3× training size | 0.875 | 0.875 | +0.000 |
| `shifted_distribution` — boundary-heavy draws | 1.000 | 1.000 | +0.000 |
| `representation_shift` — paraphrased + distractor | 0.875 | 0.875 | +0.000 |
| `multi_step` — two operations in sequence | 0.500 | 0.500 | +0.000 |
| `combination` — composition never in the library | 0.000 | **0.500** | **+0.500** |
| `adversarial` — one solvable trap, one impossible request | 0.500 | 0.500 | +0.000 |

Per-seed overall: 0.571 → 0.643 (seeds 11, 23, 41) and 0.429 → 0.500 (seed 37).
Mean across axes: baseline **0.536**, system **0.607**.

Leakage: **clean in all four runs** — six production counters unchanged, library
hash unchanged, zero hidden identifiers found in `semantic_nodes`, `episodes`,
`skills`, `skill_candidates`.

### What this actually shows

* **One axis improves, and only on the tasks the synthesizer can solve.** The
  `combination` axis asks for dedupe → keep evens → running total, which the
  library has never seen. Baseline has no program, so it fails; the system
  acquires one from the grammar in ~200 candidates and passes. That is genuine
  generalization to an unseen composition of known operations, on 1 of 2 tasks.
* **The other six axes show retention, not learning.** Baseline and system are
  identical because the frozen library already contains the family: the numbers
  prove the learned programs survive bigger inputs, boundary draws and
  paraphrase — which is what retention means — and nothing more.
* **`unseen_family` is a measured failure.** Acquisition exhausted its budget on
  both families at every seed. `group_sum` is not solvable by the current
  candidate grammar. This is the honest limit of the approach, not a bug to be
  tuned away in the report.
* `multi_step` 0.5 and `adversarial` 0.5 are "one of two" — one composition is in
  the grammar, one is not; one adversarial task is a trap that must be refused and
  is, the other is an impossible network request that both arms decline.

---

## 5. Five-cycle retention and Adaptive Sleep 2.0 (M5)

Five consecutive sleep cycles (`memory/sleep_logs`, `datasets/research/retention5_latest.json`):

| Cycle | Rotation replays | Verified skills | Skills unusable | Usefulness | Contradictions | Abstractions | Fingerprint |
|---|---|---|---|---|---|---|---|
| 9 | 4/4 | 30 | 2 | 0.861 | 0 | +1 | `972e7b2e3ede0605` |
| 10 | 4/4 | 30 | 2 | 0.853 | 0 | +0 | `15e6b3089ee9602b` |
| 11 | 4/4 | 30 | 2 | 0.855 | 0 | +0 | `b6e20bfabf673382` |
| 12 | 4/4 | 30 | 2 | 0.855 | 0 | +0 | `b6e20bfabf673382` |
| 13 | 4/4 | 30 | 2 | 0.855 | 0 | +0 | `b6e20bfabf673382` |

* **20/20 step-level replays passed** across five cycles. Retention is measured
  each cycle, not asserted once.
* **Cycles 11–13 have identical fingerprints.** Once the memory stops changing,
  the reproducibility fingerprint stops changing too — which is what it is for.
  Different work produces a different fingerprint (cycle 9 ≠ 10 ≠ 11).
* **Abstraction converges.** Six abstractions were created in total and then the
  pass returns 0: every qualifying topic already has one. This is idempotence
  reached by the label check, not by hitting the cap of 8.
* **Two skills are verified but unusable as training examples** — their stored
  `solution` is empty. Reported every cycle rather than silently dropped.
* **Contradictions: 0 detected in the last five cycles**, after the detection rule
  was narrowed (see D6). The current corpus contains no negated restatement of a
  known fact, so the true positive count is genuinely zero.
* Every cycle keeps all **eight stages**; the analyses attach to stages 2, 4, 5, 6
  and 8.

---

## 6. Calibration (M6)

From `calibration` after the Phase 4 integration probes:

* n = 8 recorded outcomes, all `source='execution'`
* mean predicted **0.933**, mean measured **1.000**
* Brier **0.0081**, ECE **0.0672**
* one reliability bucket (0.8–1.0, n=8)

**Honest reading.** Eight samples, all from verified canvas builds, all successes.
A Brier score of 0.008 means the system's confidence was slightly *under*-stated
on those eight, not that it is well calibrated. Until the sample count and the
outcome mix grow, this number is evidence that the mechanism works, not a claim of
calibration quality.

---

## 7. Security and isolation (M7)

```
$ python -m minicoder.cli research security
  namespace  probes=11 escapes=0 []
  guard      probes=11 escapes=0 []
  escape failures: 0
```

* **22 escape probes, 0 escapes**, in both available isolation modes (Python
  `-I` namespace with `unshare`, and the audit-hook guard).
* **Explicit authorisation.** A consequential request without a grant is refused
  before planning and audited (`audit_log`, `authorized=0, allowed=0`). With the
  grant the row records `authorized=1, allowed=1, executed=<bool>`.
* **Atomic promotion.** Skill + candidate rows commit in one transaction; a
  failure leaves neither. Verified by `test_promotion_requires_three_passing_replays`.
* **Evaluation never touches production.** The blind benchmark reports
  `production_memory.unchanged: true`; generalization runs verify the same thing
  independently and found zero differences across four runs.
* **The private store stays outside the repository** (`~/.local/share/nace-private`,
  mode 0700) and is unreachable by relative path — asserted by
  `test_private_store_is_outside_the_repository`.

### Known limits of this section

* The private-store manifest pins `tasks.py`, `evaluator.py`, `private.py`. Phase 4
  modified the first two to add `scale`/`edge_only`, which — correctly — broke the
  integrity check, and the manifest was then re-pinned explicitly with
  `PrivateStore.repin()`. The manifest detects accidental and candidate-side
  tampering; it cannot detect an operator who re-pins after editing. That is stated
  here rather than claimed away.
* The sandbox boundary is the isolation modes above, not a container: there is no
  Docker on this machine and none was added.

---

## 8. Dashboard (M8)

Two new tabs, both fed by endpoints that read tables and report files:

* **Cognition** — calibration samples, Brier/ECE, reliability buckets, intent mix,
  adaptive-sleep measurements for the last cycle, and the audit trail.
* **Generalization** — the seven axes against the frozen baseline, the run's
  leakage check, and per-task results.

Missing data renders as "no report yet" with the command that produces it. No
placeholder numbers. `render-check` walks all ten tabs: **14/14 checks passed**.

---

## 9. What did not improve

* **`unseen_family` generalization is zero.** The candidate grammar cannot express
  `group_sum`. Acquisition spends its budget and returns nothing.
* **The learning result is unchanged** — 0.606 both before and after. Phase 4
  integrated the system; it did not make the learner better.
* **Calibration rests on eight samples.**
* **Contradiction detection finds nothing** in the current corpus; the mechanism is
  tested on synthetic pairs, not on a natural one.
* **Rotation retention is a weaker check than criteria-based retention** (it
  replays steps, it does not re-assert the original success criteria). Both are
  reported separately and never merged into one flattering number.
* **No claim of understanding, consciousness or general intelligence.** The system
  routes typed requests, retrieves records, measures itself against recorded
  outcomes, and says "I don't know" when it has nothing.
