# Phase 3 — measured results

Commit: `f078f41` + this phase's commits. Hardware: 2 cores, 3.9 GB RAM, no GPU, Python 3.11.2,
torch 2.15.0. Generator `nace-gen-3.0`. Seeds 11, 23, 37 (measured), 5 (memory warm-up).
Raw reports: `datasets/research/acquisition_latest.json`, `transfer_latest.json`,
`retention_latest.json`, `meta_latest.json`, `security_latest.json`.

## 1. The question

Could NACE acquire an executable capability it demonstrably lacked, retain it, and transfer it
to unfamiliar tasks without receiving the solution?

The answer is **yes for a bounded class of data-transformation procedures, with three
qualifications that matter more than the headline**: the baseline fails completely (so absence is
real), but a quarter of apparent successes are test-fitting, consolidation buys cost rather than
success, and transfer to a shifted input distribution is good but not clean.

## 2. Acquisition across control arms

66 scorable tasks per arm (3 seeds × 22; the two impossible tasks are excluded and recorded as
`expected_fail`). Hidden-test pass rate, scored by the independent evaluator:

| arm | what it is | hidden pass | rate | 95% CI | dev pass | test-fitted | mean candidates |
|---|---|---|---|---|---|---|---|
| A | model alone, no search | 0/66 | **0.000** | [0.000, 0.000] | 0 | 0 | 0 |
| B | memory only (warm-up seed 5, disjoint) | 33/66 | 0.500 | [0.38, 0.62] | — | — | 0 |
| C | discover, no retention | 40/66 | 0.606 | [0.485, 0.727] | 46 | **6** | 180.4 |
| D | acquire, no consolidation | 40/66 | 0.606 | [0.485, 0.727] | 46 | 6 | 155.4 |
| E | full | 40/66 | 0.606 | [0.485, 0.727] | 46 | 3 | 116.5 |
| F1 | no composition (depth 1) | 36/66 | 0.545 | [0.424, 0.667] | 42 | 6 | 29.8 |
| F2 | no binary operations | 28/66 | 0.424 | [0.303, 0.545] | 32 | 4 | 162.2 |
| F3 | no row operations | 31/66 | 0.470 | [0.348, 0.591] | 37 | 6 | 180.0 |

Reading it honestly:

* **Absence is real.** The model alone solved none of 66 tasks; its outputs were text, not
  programs. Every acquisition claim therefore has a live counterfactual.
* **Search is what works.** Removing composition costs 4 tasks, binary operations 12, row
  operations 9. No single component carries the result, and none is decorative.
* **Test-fitting is measurable and non-trivial.** 46 programs satisfied the visible dev tests;
  only 40 passed hidden inputs. Six apparent successes were overfitting to the examples the agent
  could see — 13 % of the dev-passing set.
* **Consolidation does not raise the success rate.** C = D = E at 0.606. It reduces search cost:
  mean candidates fall from 180.4 to 116.5 (−35.4 %), because a consolidated procedure is reused
  instead of re-discovered. That is a real effect and a smaller claim than "learning improves
  performance".
* **Memory alone is not acquisition.** B reached 0.500 by retrieving procedures learned on a
  disjoint warm-up seed. It is below the acquisition arms, but far above zero, which is the useful
  finding: for repeat families, memory gets most of the way there.

## 3. Transfer

Each stored program re-scored unchanged on variants it never saw:

| category | what changes | pass | rate |
|---|---|---|---|
| `edge_cases` | empty input, single element, duplicates | 36/36 | 1.000 |
| `near_size` | inputs larger than any dev draw (12–15 elements) | 32/36 | 0.889 |
| `cross_domain` | lists replaced by tuples | 32/36 | 0.889 |
| `distribution` | integers shifted by +1000, letters rotated | 24/28 | **0.857** |

The distribution shift costs the most, as it should: procedures that pass on one value regime
degrade on another. Nothing generalised perfectly except the trivial edge cases, so "it
generalises" is not a claim this phase earns — "it transfers to 86–89 % of unfamiliar variants in
this class" is.

## 4. Retention

* 12 families consolidated; 9 verified against hidden tests at acquisition.
* **9/9 verified procedures still pass when re-scored on their own task** in a fresh process
  (every evaluation runs in a new namespace-isolated interpreter).
* Retention is execution-based; `record_present` is reported separately and never counted.

Consolidation cycles (1/3/10 sleep cycles) were **not** run in this phase; see limitations.

## 5. Meta-learning

* Reuse cuts search cost by **35.4 %** (180.4 → 116.5 candidates, arms C vs E).
* Within arm C, a *later* task of the same family costs **more** than the first
  (204.9 vs 180.5 candidates). There is no within-arm learning curve: the search does not get
  better at searching.

So the efficiency gain comes from storing the answer, not from improving the strategy. That is
"reuse", not meta-learning, and this phase does not demonstrate meta-learning.

## 6. Isolation and security

11 probes × 2 modes, run as an automated test:

| probe | Phase 2 guard | Phase 3 `guard` | Phase 3 `namespace` |
|---|---|---|---|
| chdir then relative read of `/etc/hostname` | **escaped** | denied | denied |
| chdir then relative read of the evaluator source | **escaped** | denied | denied |
| absolute read of the repo | denied | denied | denied |
| read the production `brain.db` | not tested | denied | denied (absent) |
| `os.system`, socket, `os.kill(parent)`, fork | denied | denied | denied |
| write into the repo | not tested | denied | denied (absent) |
| infinite loop / 900 MB allocation | — | timeout / MemoryError | timeout / MemoryError |

`namespace` mode runs each candidate in `unshare -Urnm --fork --pid --kill-child` with a tmpfs
mounted over `/home`: the repository, production memory, checkpoints and private fixtures are not
denied but *absent* from that filesystem. It is the default mode. `guard` mode is the fallback and
is labelled as not an OS boundary.

The evaluator pins sha256 of itself, the generator and the private store; a modification aborts
scoring rather than producing a pass. Demonstrated accidentally in development: editing
`evaluator.py` made every subsequent evaluation return `no_result`.

Production isolation: the live brain's `skills` / `experiments` / `skill_candidates` counts are
asserted identical before and after every research run; the reports record the comparison.

## 7. What was acquired that was not there before

Per capability, the four required facts:

| capability (family) | absent at baseline | acquired by search | verified on hidden tests | transfers to ≥ 3 variants |
|---|---|---|---|---|
| `abs_all`, `scale`, `sum_even`, `running_total`, `dedupe`, `chunk`, `count_by`, `sort_by`, `scale_then_running` | arm A: fail | yes (enumerative, 2–380 candidates) | yes | yes |

Nine independent capabilities satisfy all four facts for at least three variant categories, with
the distribution-variant exception recorded in §3.

## 8. Limitations found, stated plainly

1. **Grammar-bounded.** 4 of 12 families (`rename_keys`, `group_sum`, `transpose`, `rle`) are not
   expressible in the current operation set, so the acquisition rate 0.606 is a property of the
   grammar as much as of the system. This is the honest ceiling: the system can compose operations
   it has; it cannot invent new primitives.
2. **Consolidation cycles not exercised.** Retention was measured across fresh processes, not
   across 1/3/10 sleep cycles.
3. **No repair loop.** Failure-driven modification exists only as depth ablation (F1 → depth 2);
   an explicit diagnose → modify → retest chain with recorded failure classes is not implemented.
4. **Task families are authored here.** The generator is independent of the solver and hidden
   draws use a private salt, but the families were written by the same author. This is weaker than
   a truly independent task source.
5. **Namespace is not a VM.** A kernel-level escape is out of scope; the evaluator shares an OS
   with the agent and is protected by hashing plus the absence of the filesystem in candidate
   runs.
6. **n = 3 seeds.** CIs are wide (≈ ±0.11). Differences smaller than that are reported as observed,
   not established.
