# Phase 3 — Independent audit of the Phase 2 system

Read-only audit performed at commit `f078f41` on branch `arena/70420343-qoute-editor`.
Nothing in this document is inferred from Phase 2's own write-ups: every row below was
re-measured in this environment, and where a Phase 2 claim did not survive, it is marked failed.

Environment: 2 CPUs, 3.9 GB RAM, no GPU, 9.0 GB free disk, Python 3.11.2, torch 2.15.0,
no Docker, unprivileged user namespaces available (`unshare -Ur` succeeds).

## 1. Claims, re-measured

| Phase 2 claim | Status | Independent measurement |
|---|---|---|
| 87 tests passing | **verified** | `pytest minicoder/tests` → 87 passed in 84.62 s |
| ruff clean | **verified** | `ruff check minicoder/` → All checks passed |
| benchmark 20/22 | **verified** | re-run → 20/22, first-attempt 20/22, 14.16 s, failures `run_length_encode`, `caesar` |
| replay 4/4 | **conditionally true** | 4/4 only when the process CWD is the install root; from any other directory → **0/4** (defect D6) |
| generalisation 3/3 | **verified within its definition** | one scaled variant per editor task; see gap G10 |
| acceptance 8/8 | **conditionally true** | 8/8 from the install root; **6/8** from `/tmp` (checks 2 and 4 fail, same root cause as D6) |
| six neural variants, no exact-match gain | **verified in Phase 2 run** | report `neural_study_latest.json`: curriculum CE −12 %, exact-match 0.000, holdout 0.000 |
| production memory untouched by benchmark | **verified** | isolated-home redirect; live brain holds 1 experiment, 1 learned skill |

Database (live production memory, untouched by this audit): 26 tables, `schema_meta` 3 rows,
28 skills, 4 skill dependencies, 1 experiment, 1 hypothesis, 1 attempt, 1 candidate,
4 skill replays, 74 episodes, 53 embeddings, 3627 provenance events, 3 sleep cycles.
The seven experiment-learning tables named in the brief are all present
(`experiments`, `hypotheses`, `attempts`, `skill_candidates`, `skill_replays`, `skills`,
`skill_dependencies`), plus `provenance_events`.

## 2. Defects found

**D6 — fresh-process replay depends on the working directory.** `LearningLoop._replay_in_subprocess`
sets `PYTHONPATH = CONFIG.install_root() if hasattr(CONFIG, "install_root") else "."`.
`Config` has no `install_root`, so the value is always `"."` — the process CWD. Run from the
repository it imports, anywhere else it does not, and the failure is reported only as a lower
replay count. Consequences measured: benchmark `replay 0/4` from `/tmp`; acceptance 6/8 from
`/tmp`, with checks 2 and 4 failing. This is a verification path that silently reports
"not passed" when the real fault is "could not run".

**D7 — the search oracle and the scoring oracle are the same object.** `synth.synth_task` passes
`task.tests` into `EnumerativeSynthesizer.synthesize`, whose `_probe` executes the candidate and
then executes those very assertions. A candidate is therefore selected because it satisfies the
tests that later "verify" it. Nothing in Path 2 separates development assertions from hidden
evaluation assertions. This is the most serious scientific weakness in the system.

**D8 — candidate code runs inside the harness process, with no confinement.** `_probe` runs
`exec(compile(program, "<candidate>", "exec"), ns)` in-process, after `os.chdir(tmp)`. No audit
hook, no rlimits, no subprocess. Thousands of candidates per task execute with the harness's own
privileges; `os.chdir` is process-global, so a candidate also changes the CWD of anything else
running concurrently in that process.

## 3. Security findings

Phase 2's guard is a PEP 578 audit hook. It is not an OS boundary, and this audit demonstrates
three concrete results.

| Probe | Result |
|---|---|
| `os.chdir("/")` then `open("etc/hostname")` | **escaped** — read `e2b.local` |
| `os.chdir(<repo>/minicoder/learning)` then `open("benchmark.py")` | **escaped** — read the evaluator's own source |
| `open("/home/user/Qoute-editor/README.md")` (absolute) | blocked (`PermissionError`) |
| `os.system(...)` | blocked |
| `socket.socket()` | blocked |

The guard denies only *absolute* paths, so any relative path after a `chdir` bypasses it. Read
access is sufficient to establish write access by the same route, because the hook does not
distinguish modes. The practical consequence: **candidate code can read and therefore modify the
evaluator and hidden fixtures**, which AC7 forbids.

Available but unused: `unshare` exists (`unshare -Ur echo` succeeds), so a mount/PID/network
namespace with a read-only bind of the repository and a tmpfs work directory is achievable
without Docker. Docker itself is not installed, and `Sandbox` already reports that.

## 4. Scientific-methodology gaps

| # | Gap | Consequence |
|---|---|---|
| G1 | Dev assertions and hidden assertions are the same (D7) | acquisitions may be test-fitted, not capable |
| G2 | 22 hand-authored tasks, authored by the same person who wrote the solver | distribution is not independent of the system |
| G3 | No blind generation, no private evaluation set, no task-generation hash | tasks can drift toward what the solver can do |
| G4 | No control arms (A–F), no ablations | 20/22 has no counterfactual; cannot attribute success to a component |
| G5 | No seeds, no confidence intervals, no sample-size discipline | rates from 15–22 tasks are reported as if exact |
| G6 | Reports omit commit hash, generator and evaluator versions, and hardware detail | results are not independently reproducible from the artifact |
| G7 | "Generalisation" is one scaled variant per task | near-distribution at best; no OOD, no cross-tool, no cross-domain |
| G8 | No retention schedule (restart, 1/3/10 consolidation cycles) | "retained" means "replayed once" |
| G9 | No meta-learning measurement | unaddressed |
| G10 | Evaluator lives in the agent-writable repository | evaluator integrity is asserted, not enforced |
| G11 | No false-positive / hardcoded-output detection | a program could special-case inputs and pass |

## 5. What is genuinely good and must be preserved

* The four-state separation (hypothesis / attempt / verified execution / promoted skill) is
  enforced in `ledger.py` and tested; promotion refuses without replay.
* Sandbox rlimits (`RLIMIT_AS/CPU/NOFILE/FSIZE/NPROC`), wall-clock timeouts and output caps work.
* The audit hook correctly blocks process spawning and sockets today.
* Benchmark isolation (`write_latest`, throwaway home) keeps evaluation out of production memory.
* Sleep consolidation with contradiction handling, dependency tracking and replay retention.
* Safeguards: baseline registry with SHA-256 manifests, regression tolerances, rollback verified
  at `val_ce 5.5893 → 379.99 → 5.5893`.
* Provenance is a closed vocabulary and every promotion writes to it.

## 6. Consequences for Phase 3

Phase 3 therefore cannot simply add tasks. To answer the research question honestly it must
first build the thing Phase 2 lacked — **a hidden-test evaluator that the agent cannot read,
cannot write and cannot infer** — and then run acquisition against it with control arms. Without
that, any new score would inherit G1 and mean nothing.

Order of work is fixed by that dependency:

1. evaluator isolation + subprocess candidate execution + relative-path escape fix (D7, D8, D6);
2. blind task generator with provenance hashes and a private test set;
3. control arms and seeded experiment runner with CIs;
4. acquisition, transfer, retention and meta-learning experiments;
5. neural investigation on the same hardware;
6. research dashboard view;
7. full verification, then documentation.

Gaps G1–G11 are tracked to acceptance criteria in `PHASE3_ACCEPTANCE.md`; those that cannot be
closed on this hardware or in this sandbox are named there as limitations rather than dropped.
