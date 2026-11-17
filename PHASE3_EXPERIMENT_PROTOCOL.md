# Phase 3 — Experiment protocol

The protocol is fixed before results are known, so that design cannot drift toward whatever the
system happens to do.

## 0. Common preconditions

* Commit recorded per run; working tree must be clean (`research/report.py` refuses a dirty tree
  unless `--allow-dirty`, and then marks the report `dirty: true`).
* Experiment id: `p3-<type>-<utc stamp>-<short sha>`.
* Seeds: `[11, 23, 37, 41, 53]` for all multi-seed experiments (chosen in advance, not per run).
* Generation seed: `nace-v1-<seed>`, recorded with the generator version.
* Hardware block recorded: cores, RAM, torch version, CUDA availability.
* Every run happens in a throwaway home; the runner asserts live-brain row counts are identical
  before and after. A run that changes them is a failed run, not a successful one.
* Budgets per arm: 120 s wall clock, 20 000 candidate programs, 64 MB candidate RSS.

## 1. Blind task generation

```
minicoder research generate --seed 11 --n 24 --out research/tasks_11.json
```

* 24 records per seed: 14 platform families, 3 cross-family compositions, 3 adversarial
  (misleading prompt), 2 impossible (required operation absent from the tool index), 2 near-OOD.
* Each record: `family`, `params`, `prompt`, `dev_tests`, `hidden_tests`, `generation_hash`,
  `generator_version`, `seed`, `expected_verdict`.
* Hidden tests are drawn independently from the same family with different sizes/values/names plus
  at least one edge case absent from dev tests.
* The private set (hidden tests + reference implementations) is written outside the repo and its
  manifest hashed; `research/evaluator.py` refuses to run if the hash differs.

## 2. Evaluator

```
minicoder research evaluate --candidate cand.py --record <hash>
```

Runs in a separate interpreter, out-of-repo root, hidden tests only, with the anti-false-positive
detectors of `PHASE3_RESEARCH_PLAN.md` §5. Returns a verdict class only:
`pass | wrong_type | wrong_value | wrong_order | exception | timeout | budget | cheating`.
The agent never receives expected values, only the class — this is what makes AC5's "the answer was
never given" structural.

## 3. Acquisition experiment (AC1, AC2)

```
minicoder research run --type acquisition --seed 11 --arms A,B,C,D,E,F1..F7
```

For each task record and each arm: observe → plan → execute → evaluate → diagnose → repair →
verify (fresh process, hidden tests) → record. Promotion is disabled in research runs by default
(`--authorize-production` required to write production memory; AC2 uses the isolated home).

Per record and arm we record: attempts, seconds, tool calls, candidates, dev pass, hidden pass,
verdict class sequence, and whether the accepted candidate was `test_fitted`.

A capability is claimed only when: arm A hidden-pass is 0 across all seeds, and arm E hidden-pass
is 1 for that record, with the accepted candidate passing **freshly generated** hidden inputs.

## 4. Transfer experiment (AC3)

For every ACI-claimed capability, generate variants automatically:
4 sizes, 4 distributions, 3 naming conventions, 3 structures (list/dict/nested), 3 orderings,
1 missing-value policy, 1 cross-tool interface, 1 cross-domain restatement.
Report pass rate per category; categories are never pooled into one "generalisation" number.

## 5. Retention experiment (AC4)

Schedule: T0 immediately; T1 after restart (new process, re-opened DB); T3 after 3 sleep cycles;
T10 after 10 sleep cycles; TX after 3 unrelated acquisitions. At each point run the procedure
against hidden tests and record `executed`, `passed`, `record_present`, latency and any dependency
loss (`skill_dependencies` resolved before and after).

## 6. Failure-driven experiment (AC5)

Select records where arm E's first strategy fails. Record the initial plan, the verdict class, the
diagnosis, the modification and the outcome. Three or more such chains with a successful
modification are required. For each chain, an audit note records that the expected values were
never available to the agent (verdict class only).

## 7. Meta-learning experiment (AC6)

Two phases on disjoint family sets: *experience* families and *held-out* families. Measure attempts
and candidates on the held-out set at experience level 0, 1, 2, 4 (i.e. after 0, 3, 6, 12 prior
acquisitions). Report mean attempts with 95 % bootstrap CI; a reduction counts only if the CI
excludes the level-0 mean and the effect does not vanish on held-out families.

## 8. Neural experiment (AC9)

Six variants, same architecture (d_model 160, 5 layers, vocab 1024), same seeds, holdout excluded
from training. Additions over Phase 2: tool-trace SFT, retrieval-augmented prompts, symbolic
assist. Measure CE, exact-match, functional correctness (sandbox), OOD. Each variant ≈ 5 min on
2 CPUs; six variants per study is the practical ceiling and is stated in the report.

## 9. Security experiment (AC7)

Run the escape matrix of `PHASE3_THREAT_MODEL.md` §6 in both modes (namespace, fallback), plus
production-isolation and evaluator-tamper checks. Produce `research/security.json` with one row per
test, mode, result and the raw output.

## 10. Reproduction (AC8)

```
minicoder research reproduce research/blind_acquisition_p3-....json
```

Re-generates tasks from the recorded seeds, re-evaluates the recorded candidate programs against
freshly computed hidden expectations, and compares per-task outcomes. Exit 0 only on an exact
match of per-task verdicts.

## 11. Reporting and statistics

* 5 seeds per configuration; per-seed raw values always stored.
* Mean with 95 % bootstrap CI (10 000 resamples, percentile method).
* n < 5 → "observed, not established".
* Reports are append-only JSON + generated markdown; the markdown is regenerated from JSON.
* Every report carries: commit, generator/evaluator versions and hashes, seeds, hardware, arms,
  budgets, failures, resource use, reproduction command.

## 12. Stop conditions (declared in advance)

* If two consecutive seeds show the evaluator disagreeing with its own reference implementation
  (self-test failure), the experiment halts and the harness is treated as broken, not the system.
* If any arm modifies production memory, the run is void.
* If the hidden-test pass rate for accepted candidates is below their dev pass rate by more than
  20 percentage points, the finding is recorded as test-fitting and AC1 fails for those records.
