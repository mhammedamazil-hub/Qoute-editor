# Phase 3 — Acceptance criteria

Each criterion is implemented as an automated check and a reproducible experiment. The status
column is filled from measured runs and is updated only by re-running, never by editing. Criteria
are not weakened to obtain a pass; a criterion that cannot be met is reported as failed.

Status legend: **demonstrated** / **partially demonstrated** / **not demonstrated** /
**inconclusive** / **failed**.

| # | Criterion | Automated evidence | Status |
|---|---|---|---|
| AC1 | ≥ 5 independently generated capabilities absent at baseline, each passing hidden tests | `research/blind_acquisition.json`: per-capability `generation_hash`, `baseline_pass_rate`, `hidden_pass` | not demonstrated |
| AC2 | every claimed acquisition has baseline + ablation controls that fail | same report, `arms` block per capability | not demonstrated |
| AC3 | ≥ 3 materially different transfer variants per capability, ≥ 1 different distribution | `research/transfer.json`, categories reported separately | not demonstrated |
| AC4 | replay after fresh process and ≥ 3 consolidation cycles | `research/retention.json` | not demonstrated |
| AC5 | ≥ 3 experiments where initial strategy fails, modification succeeds, and the answer was never given | `research/failure_driven.json` | not demonstrated |
| AC6 | measurable reduction in attempts or cost on held-out related tasks | `research/meta.json` with CI | not demonstrated |
| AC7 | isolation, evaluator protection, production isolation, resource limits | `research/security.json` escape matrix | not demonstrated |
| AC8 | separate process reproduces published results from documented seeds | `minicoder research reproduce <report>` exit 0 | not demonstrated |
| AC9 | controlled neural results published, including negative findings | `datasets/learning/neural_study_*.json` + Phase 3 study | not demonstrated |
| AC10 | all Phase 2 acceptance tests and functionality still operational | 87 tests + `minicoder acceptance` 8/8 + benchmark gate | not demonstrated |

## Definitions that decide the verdict

**AC1.** A capability counts only if all of the following hold, measured on the same record:
baseline arm hidden-pass rate 0 across seeds; acquisition arm produces a candidate; that candidate
passes **hidden** tests, not merely dev tests; the dev/hidden gap is reported. A capability whose
candidate passes dev but fails hidden is recorded as `test_fitted` and does **not** count.

**AC2.** Controls are comparable: same task record, same seeds, same budgets. An arm that fails
only because it was given less time does not support the claim, and the report records budgets.

**AC3.** Variants are generated, not hand-picked: sizes, value distributions, names, ordering,
nesting, missing values, and at least one cross-tool interface. Passing the original task again is
not a transfer result.

**AC4.** Retention is execution-based: the procedure runs in a fresh process against hidden tests
after N consolidation cycles. A database row alone is recorded as `record_present: true` and
`retained: false`.

**AC5.** "The answer was never given" is enforced structurally: the agent receives dev tests and
never the hidden set; the repair must be driven by the failure signal from the hidden evaluator's
*verdict class* (e.g. wrong type / wrong order / exception), not by its expected values.

**AC6.** Meta-learning is measured on **held-out families** that the strategy never saw. A gain that
exists only on the families used to build the strategy is reported as leakage.

**AC7.** The escape matrix in `PHASE3_THREAT_MODEL.md` §6 runs in whatever mode is available.
Namespace mode must show zero escapes. If only the audit-hook fallback is available, the result is
reported as **partially demonstrated** and explicitly described as not an OS boundary.

**AC8.** Reproduction runs from a clean shell at the recorded commit with recorded seeds, in a
separate process, and must reproduce the published per-task outcomes exactly and the published
rates within the stated CI.

**AC9.** Neural results must separate CE, exact-match, functional correctness and OOD. A CE gain
with no functional or OOD gain is recorded as "loss improved, capability did not".

**AC10.** Phase 2 numbers must be reproduced from the current tree. Note the audit finding: replay
4/4 and acceptance 8/8 required CWD = install root; Phase 3 fixes that so they hold from any
directory, and the fix is itself covered by a test.

## Honesty rules applied to the verdict

1. A criterion marked demonstrated must be reproducible by `minicoder research reproduce`.
2. If the same result can be explained by test-fitting, it is not counted, even if it is a pass.
3. Rates from < 5 seeds are described as observed, not established.
4. Any criterion whose evidence was produced by a modified evaluator is void.
5. Failed experiments stay in the report; the JSON is append-only.
