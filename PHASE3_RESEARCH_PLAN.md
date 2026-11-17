# Phase 3 — Research plan

Status: design. Implementation follows `docs/AUDIT_PHASE3.md`, whose gaps are referenced as G1–G11.

## 1. Hypothesis under test

> NACE can independently acquire an executable capability that it demonstrably lacks before an
> experiment, retain it across processes and consolidation, and transfer it to unfamiliar
> problems without ever receiving the solution.

Four facts must be established separately, and the failure of any one is reported as such:

| Fact | Operational test |
|---|---|
| F1 absence | the same task, same budget, is solved at rate ≈ 0 by the baseline arm, before acquisition |
| F2 acquisition | a recorded search/failure/repair process produces a candidate that the **hidden** evaluator accepts |
| F3 verification | fresh-process replay against hidden tests, independent of the acquisition process |
| F4 transfer | ≥ 3 materially different variants pass, ≥ 1 from a different input distribution |

A capability counts only if F1 and F2 hold **against hidden tests**. F1 alone is not enough
(the task may be unsolvable), F2 alone is not enough (the baseline may already solve it).

## 2. Why Phase 2 cannot answer it

G1: the synthesizer searches against the same assertions that score it, so "solved" may mean
"fitted". Phase 3 therefore makes the evaluator the primary instrument, and the agent's view of
the task strictly smaller than the evaluator's.

## 3. Architecture to build (additive; nothing in `minicoder/learning/` is replaced)

```
minicoder/research/
  tasks.py        blind generator: distributions → TaskRecord {dev tests, HIDDEN tests, hash}
  private.py      private evaluation set, out-of-repo root, hash-pinned at load
  isolation.py    candidate execution: namespace-isolated subprocess (unshare) or hardened fallback
  evaluator.py    hidden-test evaluator; runs out-of-repo; refuses if fixtures changed
  arms.py         control arms A–F over one task record
  experiment.py   seeded runner, per-arm budget accounting, CI computation, report writer
  retention.py    replay schedule across restarts and consolidation cycles
  meta.py         learning-efficiency measurements on held-out related tasks
  report.py       machine-readable reports with commit, versions, seeds, hardware, CIs
```

CLI: `minicoder research generate|evaluate|run|retention|meta|report`. Existing `minicoder
learn|benchmark|acceptance|safeguard|neural|sleep` keep working unchanged.

## 4. Blind generation (G2, G3, G11)

Tasks are generated from **distributions over program families**, not from templates with new
names. Each family defines: input type, operations, constraints, a reference implementation used
only to compute hidden expected outputs, and a difficulty dial.

* Randomised per task: sizes, element types, ordering, field/parameter names, missing-value policy,
  nesting depth, and the composition of two to three families (e.g. "filter even, then group by a
  renamed key, then sort descending").
* Generation is seeded (`nace-v1-<seed>`) and the seed set is written into the report.
* Every record carries `generation_hash = sha256(canonical(task, dev_tests, hidden_tests, seed))`
  and the generator version string. Changing the generator changes the hash.
* The **dev tests are visible** to the agent. The **hidden tests** are generated from the *same
  family* with **different draws** — different sizes, values, names and at least one edge case the
  dev tests do not contain. This is what makes test-fitting detectable rather than assumed absent.
* Impossible and adversarial records are included deliberately: families that require operations
  the tool index does not expose (measured as expected-fail), and misleading prompts where the
  stated intent conflicts with the hidden assertions (a system that trusts the prompt over the
  tests must fail these).

## 5. Independent evaluator (G10)

* Fixtures and evaluator live under a private root **outside the repository**
  (`~/.local/share/nace-private`, mode 0700), never in a directory the agent can chdir into.
* The evaluator process starts from a clean interpreter, loads fixtures by hash, and re-computes
  every expected output from the family's reference implementation at evaluation time — a stored
  expected value cannot drift into a stored answer key.
* If a fixture hash does not match the manifest, the run aborts instead of scoring.
* Anti-false-positive checks, run for every accepted candidate:
  1. **randomised re-evaluation** — evaluate on freshly generated hidden inputs, not the ones used
     during acquisition;
  2. **constant-output detector** — the program must not return the same value for all inputs;
  3. **lookup detector** — no dict/table keyed on whole inputs, no literals equal to expected
     outputs, no reads of anything outside the run directory;
  4. **environment probes** — attempts to read the repo, the private root or `/etc` are recorded
     as failures, not merely blocked.

## 6. Isolation (G1, G10, AC7)

`isolation.py` runs candidate code only in a child process, never via `exec()` in the harness:

1. preferred: `unshare -Urn` (mount+PID+network+user namespace), repo bind-mounted **read-only**,
   a tmpfs work directory, `RLIMIT_AS/CPU/NOFILE/FSIZE/NPROC`, wall-clock timeout, no network;
2. fallback when namespaces are unavailable: subprocess with a strengthened audit hook that
   resolves **relative** paths against the CWD before allowing them (closing the demonstrated
   bypass), `chdir` blocked entirely, plus the same rlimits;
3. the fallback is reported as *weaker* in every report; it is never described as an OS boundary.

The `exec()`-based `_probe` path is retained only for the Phase 2 benchmark (preserved behaviour)
and is not used by any Phase 3 experiment.

## 7. Control arms (G4)

All arms see the same task record, the same seeds, the same wall-clock and candidate budgets.

| Arm | Memory | Tool index | Planning | Synthesis | Repair | Consolidation | Replay |
|---|---|---|---|---|---|---|---|
| A baseline | none | none | none | none | no | no | no |
| B memory only | retrieve | none | none | none | no | no | no |
| C discovery only | none | yes | yes | no | no | **no** | no |
| D acquisition, no consolidation | none | yes | yes | yes | yes | **no** | no |
| E full | yes | yes | yes | yes | yes | yes | yes |
| F1–F7 ablations | E minus one component | | | | | | |

A is implemented as "the model and the tool index are present, no learning loop": it may call
tools directly and may answer from memory, and it is measured, not assumed, to fail new tasks.
B/C/D are switches on the existing `LearningLoop`, not forks of it.

## 8. Metrics

Per arm and per task: initial success, final success, attempts, acquisition seconds, tool calls,
candidates tested, peak RSS, hidden-test pass rate, dev-test pass rate (the gap between the two is
the test-fitting signal), transfer rate by category, retention at each interval, regression rate,
false-positive rate.

Statistics: ≥ 5 seeds per configuration; report mean with 95 % bootstrap CI (10 000 resamples) and
the raw per-seed values. With n = 20 tasks and 5 seeds, a difference is described as *observed*
unless the CI excludes zero; otherwise it is *inconclusive*. No p-values from 15 samples.

## 9. Transfer taxonomy (G7)

In-distribution (same family, same parameters), near (same family, different sizes/names), OOD
(different data distribution or nesting), cross-tool (equivalent operations exposed under a
different interface), cross-domain (the invariant applied to a different problem type). Each is
reported separately and never pooled.

## 10. Retention (G8)

Immediately, after 1 restart (fresh process), after 3 and 10 consolidation cycles, and after
intervening unrelated learning. Retention means the procedure **executes and passes hidden tests**;
a surviving database row is not retention and is recorded separately as `record_present`.

## 11. Meta-learning (G9)

On held-out families: does the system reduce attempts or candidate count relative to a fixed
baseline strategy as it accumulates experience? Measurements are behavioural (attempts, tool
calls, candidates, seconds), never self-reported reasoning. A reduction that appears only on the
tasks used to build the strategy is reported as training-set leakage, not meta-learning.

## 12. Neural investigation (G5, AC9)

Continue `minicoder neural` with the Phase 2 harness: same architecture, fixed seeds, holdout
excluded. Add: tool-trace SFT vs plain SFT, curriculum vs uniform, retrieval-augmented vs not,
and a symbolic/neural complementarity arm. Report CE, exact-match, functional correctness and OOD
separately; a CE improvement with zero functional change is reported as a failure to translate.
On 2 CPUs a 12-epoch 1.3 M-parameter run costs ≈ 5 minutes per variant; six variants per study is
the practical ceiling, so effects smaller than the seed variance will be labelled inconclusive
rather than claimed.

## 13. Reporting (G5, G6)

Every report: experiment id, git commit, generator and evaluator versions and hashes, seeds,
hardware, config, per-arm raw values, CIs, failures, resource use, and the exact command to
reproduce. Reports are append-only; a re-run writes a new file. `research/report.py` regenerates
the markdown from JSON, never the reverse.

## 14. What would make this phase fail

Declared in advance so it cannot be rationalised later: if no capability meets F1–F4 against
hidden tests with a baseline control, the honest answer is "nothing acquired", and that will be
the headline. If the hidden-test pass rate for accepted candidates is materially below their dev
pass rate, the finding is that acquisition was test-fitting, and it will be reported as such.
