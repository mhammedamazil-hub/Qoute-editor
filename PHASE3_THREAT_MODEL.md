# Phase 3 — Threat model

Scope: candidate code produced by acquisition, experiment tasks, evaluator fixtures, and
production memory. Assumed environment: 2 CPU / 3.9 GB, no Docker, unprivileged user namespaces
available, single interactive user.

## 1. Assets

| Asset | Why it matters |
|---|---|
| Hidden test fixtures and expected outputs | reading them converts acquisition into retrieval |
| Evaluator implementation | reading it allows target-specific overfitting; writing it fakes results |
| Production memory (`memory/brain.db`, 28 skills, provenance) | contamination or deletion destroys the retained evidence |
| Checkpoints (`memory/checkpoints/lm.pt` + baselines) | the neural baseline and rollback target |
| Benchmark reports (`datasets/learning/`) | the historical record; must not be rewritten |
| Credentials in the environment | GitHub token, any `.netrc`/`.git-credentials` |

## 2. Adversaries

1. **The synthesizer itself** — not malicious, but it enumerates thousands of programs and will
   find any capability that helps it pass, including reading the tests it is scored on.
2. **A hostile task author** — tasks and fixtures come from a generator; a fabricated family could
   try to escape at *evaluation* time.
3. **A hostile candidate** — a program that probes the filesystem, spawns processes, opens sockets,
   kills the harness, or writes to the repository.
4. **Accidental contamination** — a benchmark run promoting skills, a test writing to production
   checkpoints (this happened in Phase 2: an 8-byte file replaced `lm.pt`).

## 3. Attack surface and current state

| Surface | Phase 2 state | Phase 3 requirement |
|---|---|---|
| Candidate execution | `exec()` **in-process**, no guard (D8) | child process only, namespaced |
| Path confinement | denylist of absolute paths; relative paths bypass (D6/audit §3) | resolve CWD + realpath, allowlist, `chdir` blocked |
| Evaluator location | inside the writable repo | private root, mode 0700, outside repo |
| Fixture integrity | none | SHA-256 manifest; abort on mismatch |
| Process spawning | blocked by audit hook (verified) | also blocked by PID namespace |
| Network | blocked by audit hook (verified) | also blocked by network namespace |
| Resource limits | rlimits + timeout in `Sandbox` (verified) | same limits on every candidate run |
| Production memory | isolated by temp home for benchmark | only an explicit `--authorize-production` may write |
| Checkpoints | restored-safe after Phase 2 incident | tests must pass `target=`; verified by suite |

## 4. Controls to implement

**C1 Process boundary.** Every candidate runs via `isolation.run_candidate()`:
`unshare -Urn --mount --pid --fork --kill-child` when available, otherwise a plain subprocess with
a hardened audit hook. The harness never `exec()`s candidate code in its own process again.

**C2 Filesystem allowlist.** The guard resolves `os.path.realpath(os.path.join(os.getcwd(), target))`
before deciding, so relative paths cannot escape; `os.chdir` raises; the repository is bind-mounted
read-only in the namespace path, and writes outside the tmpfs work dir fail.

**C3 Private evaluation root.** Fixtures and reference implementations live in
`~/.local/share/nace-private` (0700). The evaluator reads them; the agent has no path to them
(they are outside the repo, and the repo's guard denies `/home` reads absolutely as well).

**C4 Hash pinning.** The manifest (`private/manifest.json`) records sha256 of every fixture and the
evaluator source. Evaluation aborts if any mismatch, so a modified evaluator cannot report a pass.

**C5 Anti-false-positive detectors.** Randomised re-evaluation on fresh draws; constant-output,
lookup-table and expected-literal detectors; environment probes recorded as failures.

**C6 Production isolation.** Phase 3 experiments run in a throwaway home
(`activate_home(tempdir)`); promotion into production requires an explicit flag, and the
experiment runner asserts the live brain row counts are unchanged before and after every run.

**C7 Budget enforcement.** Per-candidate wall clock, per-arm budget, whole-experiment budget; a run
that exceeds it is reported as `budget_exhausted`, not as a failure of the capability.

## 5. Residual risk (stated, not hidden)

* **Namespaces are not a full VM boundary.** A kernel bug, or a configuration where `unshare`
  silently degrades, leaves the audit-hook fallback, which is *not* an OS boundary. Reports state
  which mode was used.
* **The evaluator shares an OS with the agent.** Hash pinning detects modification after the fact;
  it does not prevent it during a run. True prevention needs a separate machine or a broker
  process the agent cannot signal — out of scope here, and named as a limitation.
* **Reference implementations compute expected outputs**, so an evaluator bug becomes a wrong
  "truth". Mitigated by testing the reference implementations themselves (`test_research_*`) on
  hand-checked cases before any experiment runs.
* **Randomised hidden draws can be unluckily easy or hard.** Mitigated by ≥ 5 seeds and CIs; a
  single-draw difference is never reported as an effect.

## 6. Escape test matrix (must be automated, results published)

| Test | Expected |
|---|---|
| `os.chdir("/")` then `open("etc/hostname")` | denied |
| `os.chdir(<repo>)` then `open("minicoder/learning/synth.py")` | denied |
| `open("/home/user/Qoute-editor/README.md")` | denied |
| `open(<private fixture path>)` | denied |
| `os.system`, `subprocess.Popen` | denied |
| `socket.socket`, `socket.connect` | denied |
| fork bomb (bounded) | killed by `RLIMIT_NPROC` |
| memory bomb | killed by `RLIMIT_AS`, reported not crashed |
| infinite loop | timeout, reported |
| write to repo path | denied |
| write to production DB | denied |
| `ctypes.dlopen` | denied |
| signal the harness (`os.kill`) | denied |

Any test that passes (i.e. escapes) must be reported as a security failure for that mode. The
current audit already contains two such failures for the Phase 2 guard; Phase 3 must show them
closed in the namespace mode and honestly report the fallback's status.
