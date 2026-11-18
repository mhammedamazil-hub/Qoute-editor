# Changelog

All measured numbers below come from `datasets/training_runs/eval_report.json`, the sleep/training
reports in `memory/sleep_logs/` and `datasets/training_runs/`, and — for Phase 2 — the reports in
`datasets/learning/`.


## Fixes found by testing the live system

### Fixed

* **Sleep stage 2 aborted mid-consolidation.** `IntegrityError: UNIQUE constraint failed:
  semantic_nodes.kind, semantic_nodes.label` — the in-memory graph can miss a row that exists in
  the database, and the plain INSERT then aborted the stage, leaving every later stage running on
  partial memory. `_insert` is now an upsert. Cycle 5 consolidates 61 episodes and adds its node.
* **Sleep stage 7 aborted skill compilation.** `ValueError: shard failed validation: ['line 1:
  empty prompt/response']` — lessons with an empty side were written to the shard and then
  rejected. They are now dropped before writing. Cycle 5 produced 11 examples from 3 skills.
* **`minicoder acceptance` promoted into the live brain.** The suite acquires and promotes skills
  to prove promotion works; run against production memory it left `learned_acceptance_beacon`
  there. It now runs in a throwaway home unless `--live` is passed. Verified: skills 30→30,
  experiments 8→8, candidates 7→7 across a full 8/8 run.

### Known weaknesses (not fixed, measured)

* A design question can be answered with a tool sequence: "How many fonts should I use in one
  poster?" returns a raw JSON trajectory instead of the stored rule, reproducibly.
* Instruction-shaped requests are sometimes *executed* rather than answered, and incompletely:
  "build a 1080x1350 poster with headline 'Quiet'" resized the canvas and reported only that.
* The system cannot describe itself: "summarise your last sleep cycle" is refused even though the
  report is on disk.

## Phase 3 — independent capability acquisition

Research phase, additive. Nothing in `minicoder/learning/` was replaced; the Phase 2 benchmark,
acceptance suite, safeguards and dashboard keep working unchanged.

### Added

* `minicoder/research/` — blind task generator (12 parametric families, private-salt hidden draws,
  sha256 provenance), independent hidden-test evaluator with cheat detection, namespace isolation,
  control arms A–F, transfer/retention/meta measurements and a seeded experiment runner.
* `minicoder research generate|run|reproduce|security` CLI.
* `PHASE3_RESEARCH_PLAN.md`, `PHASE3_THREAT_MODEL.md`, `PHASE3_ACCEPTANCE.md`,
  `PHASE3_EXPERIMENT_PROTOCOL.md`, `docs/AUDIT_PHASE3.md`, `docs/PHASE3_RESULTS.md`.
* 18 tests (`test_research_phase3.py`).

### Measured

3 seeds × 22 scorable tasks × 8 arms. Hidden-test pass rate: baseline **0.000**, memory-only
0.500, discovery 0.606, no-consolidation 0.606, full 0.606, ablations 0.545 / 0.424 / 0.470.
Transfer: edge 1.000, near-size 0.889, cross-domain 0.889, distribution shift 0.857. Retention:
9/9 verified procedures replay in fresh processes. Reuse cuts candidates 35.4 % (180.4 → 116.5).

### Fixed

* **Fresh-process replay no longer depends on the working directory.** `PYTHONPATH` came from
  `CONFIG.install_root()`, which does not exist, so it fell back to `"."`. Benchmark replay was
  4/4 from the repo and **0/4** from `/tmp`; acceptance was 8/8 and **6/8**. Now derived from the
  package location, verified from `/tmp`.
* **The Phase 2 audit-hook bypass is closed.** `os.chdir` plus a relative path read the evaluator's
  own source and `/etc/hostname`. The research guard resolves every path and refuses `chdir`;
  the escape matrix reports 0/11 in both modes.
* **Candidate code no longer runs in the harness process.** Phase 2 `exec()`ed thousands of
  candidates in-process with no guard; research runs use namespace-isolated children.
* **A test overwrote the experiment library** with an empty one, the same class of defect as the
  Phase 2 checkpoint incident. Library paths now follow the output directory.

### Honest negatives

* Consolidation does not improve the success rate (C = D = E); it only reduces cost.
* No meta-learning: later tasks of the same family cost more (204.9 vs 180.5 candidates).
* 4 of 12 families are unreachable by the grammar, which caps acquisition at 0.606.
* AC5 (repair chains), AC6 (meta-learning) and AC9 (fresh neural study) are **not demonstrated**
  in this phase and are marked as such in `PHASE3_ACCEPTANCE.md`.

## Phase 2 — genuine skill acquisition

Every number below is in `datasets/learning/` (`benchmark_latest.json`,
`acceptance_latest.json`, `neural_study_latest.json`) or reproducible with the
command named beside it.

### Added
- **Forensic audit** (`docs/AUDIT_PHASE2.md`) performed before any code: hardware
  and network re-verified, baseline reproduced, and the three claimed skill
  sources found to be re-execution or transcription. The retrieval benchmark was
  circular and the sandbox was permissioned only in its documentation.
- **Runtime sandbox confinement** (`minicoder/tools/guard.py`): a PEP 578 audit
  hook refusing filesystem access outside the run directory, process spawning,
  sockets and `ctypes`. Guarded by default; 25/25 seed tasks still verify.
- **Schema v2** (additive): `experiments`, `hypotheses`, `attempts`,
  `skill_candidates`, `skill_replays`, `resource_samples`, `skill_dependencies`.
  A hypothesis, an attempt, a success and a skill are now different tables.
- **Learning loop** (`minicoder/learning/`): tool discovery over the live
  catalogue, a criterion DSL, a searching planner, an enumerative program
  synthesiser, an acquire→replay→promote→reuse engine, end-to-end acceptance
  runner, and reproducibility-checked reports.
- **`SOURCE_LEARNING_LOOP`** as a first-class provenance value.
- **Sealed benchmark**: 22 tasks, 10 categories, difficulty spread, sealing
  enforced by `assert_sealed()` and a test-strength audit
  (`audit_test_strength`) that rejects tasks a wrong program could satisfy.
- **Safeguards**: immutable baselines with SHA-256 manifests, a directional
  regression guard, an admit/rollback gate, and skill-version archiving.
- **Eighth sleep stage**: learning consolidation with de-duplication,
  contradiction recording, replay-calibrated confidence, temporal validity,
  skill→tool dependencies and measured retention.
- **CLI**: `learn`, `benchmark`, `acceptance`, `neural`, `safeguard`.
- **API**: `/api/learning/overview`, `/api/learning/skills`,
  `/api/learning/experiments`.
- **Dashboard**: the *Acquisition* tab.
- **33 new tests** (84 total).

### Measured
| Claim | Measurement |
|---|---|
| sealed benchmark | 20/22 final (90.9%), first-attempt 20/22, 66.96 s, peak RSS 65 MB |
| replay in a fresh process | 4/4 |
| generalisation to a variant | 3/3 |
| acceptance criteria | 8/8 in 54 s |
| deliberate regression | 0.875 → 0.0 accuracy, 5.68 → 356 NLL; caught, rolled back exactly |
| live acquisition | skill #28 promoted after 3/3 replays in a fresh interpreter |
| sleep consolidation | 1 procedure, 4 dependencies, 1/1 retained; re-run extracted 0, de-duplicated 1 |
| neural study | curriculum cut val CE 5.21 → 4.56 and still scored 0.000 exact-match |

### Fixed — silent correctness bugs (Phase 2)
- **Sandbox was not confined.** `open('/etc/passwd').read()` succeeded and
  `os.system()` spawned a shell through `run_python`; only a command-line
  substring blocklist existed.
- **The planner undid work it had not done.** A failed candidate called `undo`
  unconditionally, popping the previous *accepted* step and silently discarding
  the canvas resize.
- **Requirements were paired with the wrong results.** `zip(reqs, results)` mixed
  a priority-sorted list with a criteria-ordered one.
- **No-op steps looped to the budget.** A step that ran successfully but changed
  nothing was accepted; it repeated until the budget expired.
- **`shape='shape'`.** Argument values were invented instead of read from the
  tool's own description; discovery now extracts the real vocabulary.
- **Partial progress was invisible.** `count(shape, >=, 2)` deadlocked because one
  of two shapes counted as no progress.
- **A hardcoded filename in file search** made a solvable task report failure.
- **A temp-directory leak** exhausted the filesystem link count after a few
  thousand candidates.
- **`max()` against a zero start** discarded every negative translation, so the
  derived repair offset was always 0.
- **Single-shot repair oscillated** between overlapping and out-of-bounds; repair
  now iterates.
- **Translated every layer instead of the offenders**, pushing in-bounds layers
  out of the canvas.
- **`evaluate_lm` returned NaN** whenever the validation stream was shorter than
  `batch_size × block`, because `_batches` never emitted a trailing partial batch.
  A uniform model now scores 6.985 (≈ ln 1024), as it should.
- **Two benchmark tasks were solvable by wrong programs** (`sum()` for a count,
  `len()` for a last element). Caught by the new strength audit; both fixtures
  strengthened rather than reported as passes.

### Incident
A new test called `restore()` without an explicit target, and `restore()`
defaulted to `CONFIG.paths.checkpoints`. It wrote an 8-byte fixture over the real
`lm.pt`. Caught by four pre-existing tests failing; restored from the automatic
`pre_restore` backup and verified back to `0.875 / 0.875 / 5.5893`. `restore()`
now defaults to the manifest's recorded origin, and both tests take the isolated
`home` fixture so they cannot reach production weights.

### Known limitations (unchanged or newly measured)
- Sealed holdout generalisation is **0.0** under every training variant tried.
- Program acquisition is depth-bounded: `run_length_encode` and `caesar` fail.
- A flipped 4:3 canvas defeats geometric adaptation; reported, not hidden.

## 2026-11-15

### Added
- **CLI** (`minicoder/cli.py`): `init seed chat act inspect train sleep eval status memory skills
  snapshots serve doctor shard`.
- **Shard entry points for CI**: `minicoder shard verify` (checksum + per-row provenance, exits
  non-zero to stop a job) and `minicoder shard train` (LoRA + validation gate, JSON report).
- **GitHub Actions**: `ci.yml` (Python lint/tests, dashboard typecheck/build, editor smoke) and
  `continual-learning.yml` (verify → train → gate → Release).
- **51 tests** in `minicoder/tests/`, split between safety invariants and system behaviour.
- **Real ablation suite** (`minicoder eval --heavy`): base / +memory / +sleep / +LoRA over one
  fixed probe set.
- **Authored knowledge seeding**: the 17 curated design Q&A pairs become retrievable verified
  memory instead of relying on the decoder to recall them verbatim.
- **`config.activate_home()`**: process-wide redirect so tests and evals run in throwaway homes.
- README and this changelog.

### Fixed — silent correctness bugs
- `set_text_content` verification read `args["text"]`; the editor's parameter is `content`. It was
  comparing two empty sets, so the check could pass vacuously or fail a correct edit.
- `set_canvas_size` computed its reported height from the *old* canvas, so a successful resize
  reported "1080×1350" while the artboard became 1080×1080.
- The visual-memory `INSERT` listed 12 columns and bound 11 values; every `inspect` with
  `save_to_memory` raised `ProgrammingError`.
- LoRA promotion loaded the adapter into a *detached* model, which raised
  "adapter does not match model" on every promotion attempt.
- `eval_chat` and `eval_multisession_recall` seeded fixtures into the **live** brain, so repeated
  runs accumulated duplicate episodes and polluted real recall. Both now run isolated.
- Episodic search returned unrelated recent episodes when nothing matched, and BM25 matched on
  question scaffolding ("user", "the", "session"). Added stopwords, a claim-text gate, and an
  honest empty result.
- The relevance gate did not apply the synonym expansion the retriever used, so
  "how much margin should I leave" retrieved the right fact and then rejected it.
- Synonym expansion then over-fired (every fact matched "size" via "resolution"/"scale"); literal
  matches now outweigh synonym matches.
- Skill matching had no question stoplist, so *"who won the 1998 world championship in curling"*
  overlapped a lighting skill on "world" and was answered from it.
- The neural fallback trusted confidently-wrong output. It is now gated on intent coverage of the
  model's own training prompts (measured separation: 1.00 in-scope vs ≤0.25 off-domain).
- Sleep consolidation admitted any non-empty text, so a garbage decoder answer
  (`"b):      ="`) became a retrievable fact. Unlearnable text is now skipped.
- A question could still become poster copy ("Which palette reads as premium? is not given…").
  Copy is now scrubbed of interrogative text.
- The API labelled every non-acting reply `"memory"`, including refusals. It now reports real
  provenance.
- Shards got a `.sha256` sidecar only when pushed to GitHub; they now always get one.
- `Paths.home` ignored the active-home redirect while every derived path honoured it.

### Changed
- Promotion order is now attach → load adapter → merge → detach (was load → merge → detach).
- `run_all(skip_heavy=…)` and `minicoder eval --heavy` control whether the ablation runs.
- Fused retrieval scores are normalised so the top hit is 1.0 and scores are comparable across
  queries (they were ~0.02, which read as noise in the UI).

### Verified this session
| Check | Result |
|---|---|
| pytest | 51 passed |
| ruff | all checks passed |
| editor `npm run smoke` / `smoke:ai` / `smoke:ui` | all pass |
| dashboard `tsc --noEmit` | clean |
| dashboard build | 238.81 kB JS (73.08 kB gzip), 22.64 kB CSS |
| dashboard render harness | 10/10 |
| continual-learning gate | passed → promoted; retention 0.875 → 0.875, skill NLL 0.8776 → 0.8449, LM CE 5.7015 → 5.6829 |
| coding suite | indist 0.8947 (n=19), holdout 0.0 (n=6), token accuracy 0.999 / 0.5291 |
| chat suite | retention 1.0, hallucination 0.0, refusal 1.0 |
| vision suite | 1.0 (n=120, 8 classes), OCR recall 1.0 |
| ablation | memory over base: +0.667 coding, +1.000 Q&A, +1.000 refusal |
