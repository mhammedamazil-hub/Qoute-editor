# MiniCoder

A small, honest cognitive system: it chats, writes code, looks at images, remembers what it
learned, **acquires procedures it did not have before**, sleeps on it, and ships only the
improvements that survive a validation gate.

Everything in this document is a **measured** number from this repository. Nothing is
aspirational — if it is written here, `minicoder eval` produced it.

```
 4.1 GB container · 2 CPU cores · no GPU · torch 2.15.0
 language model   1,317,600 parameters (5 layers, d_model 160, seq 192, vocab 1024)
 vision tower       206,312 parameters (48px MiniViT: patch 4, d_model 96, 2 layers)
```

---

## 1. What it is

| Layer | What it does | Where |
|---|---|---|
| **Neural core** | byte-BPE tokenizer → decoder-only transformer + a MiniViT, trained from scratch on CPU | `minicoder/model/` |
| **Memory** | working, episodic, semantic (graph + vectors), procedural (skills), visual — one SQLite brain with `sqlite-vec` | `minicoder/memory/` |
| **Cognition** | intent parsing, grounded answering, metacognitive calibration, the design agent | `minicoder/cognition/` |
| **Tools** | 34 real editor tools behind a Node bridge, plus a permissioned sandbox | `minicoder/tools/` |
| **Learning** | experiments → hypotheses → attempts → verified skills, with a sealed benchmark | `minicoder/learning/` |
| **Sleep** | 8 stages: replay → consolidation → cross-modal → conflicts → **learning consolidation** → forgetting → shard compilation → dispatch | `minicoder/sleep/` |
| **Continual learning** | GitHub Actions trains a LoRA adapter, gates it, releases it | `.github/workflows/` |
| **Interfaces** | FastAPI (21 endpoints + WebSocket telemetry) and a 6-tab React dashboard | `minicoder/api/`, `minicoder/dashboard/` |

The design agent drives the **QuoteCraft** poster editor that lives in `src/`, so a request like
*"create a cinematic poster about patience at 1080x1350 with gold light"* becomes real, verifiable
editor mutations rather than a description of them.

---

## 2. Run it

```bash
python -m venv .venv && . .venv/bin/activate
pip install fastapi uvicorn pydantic sqlite-vec networkx pillow numpy scipy psutil \
            GitPython PyGithub pytest httpx pyyaml ruff tree-sitter
pip install torch --index-url https://download.pytorch.org/whl/cpu
npm install                                  # the editor + the tool bridge

export PYTHONPATH=.
python -m minicoder doctor                   # environment audit
python -m minicoder seed                     # palettes, tools, authored knowledge, code skills
python -m minicoder serve                    # http://localhost:8000  (dashboard + API)
```

The CLI:

```
init    seed    chat    act     inspect  train   sleep
eval    status  memory  skills  snapshots serve   doctor  shard
learn   benchmark acceptance neural safeguard
```

| Command | What it does |
|---|---|
| `minicoder chat "How many fonts should I use?"` | answer from verified memory, or refuse |
| `minicoder act "create a poster about patience at 1080x1350"` | plan → execute → verify on the live editor |
| `minicoder inspect shot.png` | vision pass: UI class, regions, findings, OCR |
| `minicoder sleep [--push] [--train]` | one full consolidation cycle |
| `minicoder eval [--heavy]` | benchmark suites (`--heavy` adds the ablation) |
| `minicoder shard verify <file>` | refuse unverified training data |
| `minicoder shard train <file>` | LoRA train + validation gate |
| `minicoder snapshots` | atomic DB snapshot |
| `minicoder doctor` | python, torch, checkpoints, optional tools |
| `minicoder learn --criteria ... --promote` | acquire a skill, replay it 3× in a fresh process, then admit it |
| `minicoder benchmark` | the sealed 22-task learning benchmark |
| `minicoder acceptance` | the eight Phase 2 acceptance criteria, end to end |
| `minicoder neural [--quick]` | controlled study of training changes, one variable at a time |
| `minicoder safeguard baseline/evaluate/rollback` | immutable baselines and regression-gated updates |

---

## 3. The prime directives, as executable rules

These are not documentation claims; each has a test in `minicoder/tests/test_prime_directives.py`.

1. **No unverified training data.** A skill reaches a shard only after its solution passed in the
   sandbox. `shard verify` re-checks the checksum and every row's provenance before CI trains.
2. **Provenance everywhere.** Every memory row carries a `source` from a fixed allow-list; unknown
   sources raise. Every write appends to `provenance_events`.
3. **Atomic backups.** A sleep cycle snapshots the DB *before* touching it; promotion keeps the
   previous checkpoint in `history/`.
4. **No weight updates while awake.** Training only runs inside the sleep window.
5. **Permissioned sandbox.** Network and destructive commands are refused before execution.

And one more that turned out to matter more than the rest:

6. **Never fabricate.** If retrieval has nothing relevant and the neural tower was not trained on
   the question, the answer is an explicit refusal — not a plausible sentence.

---

## 4. Ablation — what each layer actually buys

One fixed probe set, one layer switched on at a time
(`minicoder eval --heavy` → `datasets/training_runs/eval_report.json`):

| State | coding exact | design Q&A exact | refusal of unanswerable |
|---|---|---|---|
| base (neural tower only) | 0.333 | **0.00** | **0.00** |
| + memory | **1.000** | **1.000** | **1.000** |
| + sleep consolidation | 1.000 | 1.000 | 1.000 |
| + LoRA-CL (live checkpoint) | 0.333 | 1.000 | 1.000 |

Deltas: memory over base **+0.667 coding**, **+1.000 Q&A**, **+1.000 refusal**.

Read the table honestly, because the interesting part is what it admits:

- The tower alone answers **none** of the design questions and refuses **none** of the
  unanswerable ones. At 1.3M parameters it always emits something. Grounding is what makes it
  useful and honest, not scale.
- Sleep's contribution is not a higher Q&A score — it is that the knowledge **survives
  forgetting**: after every episode is archived, `qa_with_episodes_forgotten = 1.000`. Retrieval
  alone would lose those answers; consolidation moved them into semantic memory.
- LoRA-CL's contribution is measured where it belongs, in the training gate (§6), not by faking a
  higher Q&A number. Its coding accuracy equals the base tower because the adapter is folded into
  the checkpoint and no retrieval is in play in that state.

### Full suite

| Suite | Metric | Value |
|---|---|---|
| coding | indist exact / pass@1 (n=19) | **0.8947** |
| coding | indist token accuracy | 0.9990 |
| coding | holdout exact (n=6, sealed) | **0.0** |
| chat | preference retention / answered from memory | 1.0 / 1.0 |
| chat | hallucination rate / refusal rate | **0.0 / 1.0** |
| multisession | recall across a DB restart | 1.0 |
| retrieval | precision@1 / MRR | 1.0 / 1.0 |
| vision | UI-class accuracy (n=120, 8 UI classes, 48px input) | 1.0 |
| vision | OCR keyword recall | 1.0 |
| findings | detection rate / false positives | 1.0 / 0.0 |

**The holdout number is 0.0 and it stays in the table.** Six sealed tasks were never seen in
training, and a 1.3M-parameter decoder does not generalise to unseen function bodies. It reproduces
them (`0.8947` in-distribution) and it cannot invent them. That is the true capability of the
model, and hiding it would make every other number untrustworthy.

---

## 5. Sleep

One cycle, eight stages (`minicoder sleep`):

| # | Stage | Effect (a measured run) |
|---|---|---|
| 1 | Prioritised replay | pending episodes ranked by surprise, failures, corrections |
| 2 | Consolidation | episodes → semantic knowledge (**unlearnable text is skipped**) |
| 3 | Cross-modal patterns | recurring keywords across modalities → `pattern` nodes |
| 4 | Organisation | conflicts detected and resolved by status strength |
| 5 | **Learning consolidation** | solved experiments → de-duplicated, calibrated procedure nodes + skill→tool dependencies, re-replayed to measure retention |
| 6 | Forgetting | decay-aware archive, recoverable from `memory/archived/` |
| 7 | Skill compilation | verified skills → JSONL shard (**130 examples from 25 skills**) |
| 8 | GitHub dispatch + wake | push the shard, or fold in a released adapter |

Stage 5 is the one that closes the loop between doing and knowing. It reads only *solved*
experiments, refuses to overwrite a conflicting belief (the conflict is recorded instead),
calibrates confidence from the measured replay rate, and re-runs each stored procedure so
retention is a measurement rather than a claim. A measured run on the live brain:

```
extracted 1 · duplicates 0 · contradictions 0 · dependencies 4 · retention 1/1
confidence for learned_live_lantern_poster: 1.0 (3 replays, 0 failures)
second cycle:           extracted 0 · duplicates 1     ← de-duplication works
```

Consolidation only admits text that looks like a real claim. A garbage decoder output
(`"b):      ="`, observed in an early cycle) is recorded as unlearnable and never enters long-term
memory — the test `test_consolidation_skips_unlearnable_episodes` holds that line.

---

## 5b. Acquiring a skill it did not have

Everything above this section makes the system *remember* better. This section is about making
it *able* to do something new — and about proving it, because the audit
(`docs/AUDIT_PHASE2.md`) found that none of the original three skill paths acquired anything:

| Original path | What it actually did |
|---|---|
| `seed.py` | stored human-written solutions with human-written tests, plus fabricated "reasoning" |
| `agent.py` | regex keyword → fixed tool sequence; measured to extract **nothing** from novel instructions |
| `sleep._compile` | re-ran stored tests against stored solutions |

The replacement is a loop, not a template library:

```
acquire ──► hypothesis ──► plan against the LIVE tool catalogue ──► execute
   ▲                                                                  │
   └──────────── classify the failure ◄── read the real outcome ◄──────┘

solved ──► skill_candidate ──► replay 3× in a FRESH PROCESS ──► promote
                                        │
                                fail ───┴─── reject (never reaches memory)
```

A successful execution is **not** a skill. `SkillPromoter` is the only writer to procedural
memory, and it refuses anything that has not passed independent replay.

### The sealed benchmark

22 tasks across 10 categories, difficulty deliberately spread. Sealing is enforced: every task
name and assertion is checked against the training corpus before the suite will run.

| category | tasks | solved | category | tasks | solved |
|---|---|---|---|---|---|
| python | 5 | 3 | debugging | 2 | 2 |
| math | 4 | 4 | file | 2 | 2 |
| data | 4 | 4 | multistep | 1 | 1 |
| visual | 1 | 1 | tool discovery | 1 | 1 |
| new API | 1 | 1 | visual inspection | 1 | 1 |

Measured run (`minicoder benchmark`, 66.96 s, peak RSS 65 MB):

| metric | value |
|---|---|
| final success | **20/22 (90.9%)** |
| first-attempt success | 20/22 (90.9%) |
| confirmed in sandbox | 20/22 |
| replay in a fresh process | **4/4** |
| generalisation to a variant | **3/3** |
| reported failures | `run_length_encode`, `caesar` |

Those two failures are real and are not hidden: both need sequential character-level state,
which depth-3 enumeration over primitives provably cannot reach. They were retried with three
escalating strategies and still failed.

### The four states are kept apart

The report separates **memorisation** (refused by the seal), **retrieval** (answered from stored
knowledge), **adaptation** (a known procedure reused on new inputs) and **acquisition** (a
procedure that did not exist before it was searched for). Reusing a skill reports which of
`direct` / `repaired` / `reacquired` / `failed` actually happened.

### The eight acceptance criteria

`minicoder acceptance` — measured in an isolated home, 47.6 s:

| # | criterion | evidence |
|---|---|---|
| 1 | learn a genuinely unseen procedural task | model alone fails the control task (110 chars of incoherent text); synthesis solves it in 36 tested candidates; editor procedure acquired in 1 attempt |
| 2 | replay it in a fresh session | 3/3, first run in a separate interpreter |
| 3 | retain it after episodic archival | 6 episodes archived → replay 2/2 with no episodes available |
| 4 | apply it to a different variation | variant solved via targeted repair; 4:3 stress case **fails** and says so |
| 5 | reject unverified skills | promotion refused; skill absent from memory |
| 6 | detect a deliberate regression | 3 metrics caught (accuracy, retention, val CE) |
| 7 | roll back a harmful update | `val_ce` 5.59 → 380.0 → restored exactly |
| 8 | reproducible benchmark reports | two runs agree task-for-task |

Criterion 4 deserves the footnote: a 3:4 skill adapts to a scaled 3:4 canvas, but a flipped 4:3
canvas fails, because two full-width text layers cannot stack in 768 px. That is reported as a
failure rather than averaged away.

Criterion 1 carries a **counterfactual**, because a success on its own proves nothing. The same
sealed task is put to the system twice: the model alone returns 110 characters of incoherent text
and fails its tests, while the acquisition loop synthesises a program, runs it in the sandbox and
confirms it (36 candidates tested). That contrast is what makes "it learned something it did not
have" a measurement instead of a claim.

**The weaker half, stated plainly.** The editor arm's own control — the same planner with
backtracking and repair disabled, one greedy pass — also solves the poster task (5 steps, zero
backtracks). So the editor result is best read as an acquired *and retained procedure*: the search
was always capable of it. The capability the system genuinely did not have is the synthesis arm.
Saying that is more useful than the 8/8 headline.

### Does the transformer actually benefit?

`minicoder neural` — six variants, one variable at a time, same architecture, seed and
evaluation, holdout excluded from every variant:

| variant | pretrain val CE | in-dist exact | holdout exact | retention |
|---|---|---|---|---|
| baseline | 5.207 | **0.250** | 0.000 | **0.375** |
| more diversity | 5.233 | 0.083 | 0.000 | 0.125 |
| curriculum (short first) | **4.562** | 0.000 | 0.000 | 0.000 |
| 2× schedule | 4.906 | 0.250 | 0.000 | 0.250 |
| vocab 512 | 4.787 | 0.000 | 0.000 | 0.000 |
| lr 6e-3 | 5.376 | 0.167 | 0.000 | 0.250 |

The honest reading: **lower validation loss did not produce a more capable model**. Curriculum
cut pretraining CE by 12% and still scored 0.000 exact-match; several variants halved SFT loss
while losing accuracy. Holdout stayed 0.0 for every variant, which is the same conclusion the
ablation reached from a different direction.

This is why the system does not grade itself on loss.

---

## 6. Continual learning loop

```
sleep (local)  ──► shard + .sha256 ──► push to `sleep-skills`
                                          │
                       .github/workflows/continual-learning.yml
                         1. shard verify      checksum + provenance, or stop
                         2. LoRA train        rank 4, α 8, lr 5e-5, 6 epochs
                         3. validation gate   retention, skill NLL, LM CE
                         4. benchmark gate    still acquires what it acquired before
                         5. Release           only if both gates accept
                                          │
wake (local)   ◄── adapter ◄──────────────┘
```

The validation gate reads loss and retention. That is necessary but not sufficient:
a model can keep its loss and lose a capability. So a second gate replays the
committed sealed-benchmark baseline (`minicoder benchmark --no-editor --check`)
and fails the run if any task the system used to acquire no longer is. Verified
both ways — with a baseline key that no longer solves, the job exits 1 and names
the task; unmodified, it exits 0.

A measured promotion (shard `shard_20261115T145458Z`, 130 examples):

| Metric | Before | After |
|---|---|---|
| retention (base skills) | 0.875 | **0.875** |
| skill NLL | 0.8776 | **0.8449** |
| LM cross-entropy | 5.7015 | **5.6829** |
| LM perplexity | 299.31 | **293.80** |
| training loss | — | 4.2576 (84 steps) |

Gate verdict: **passed** → promoted.

Two hard-won constraints are encoded in the trainer, both from measurements that went wrong first:

- **Replay ratio ≥ 8:1 and lr ≤ 5e-5.** At lr 3e-3 with no replay, exact-match fell from 1.00 to
  0.00 — catastrophic forgetting in one run.
- **Domain guard.** A shard whose responses are not ≥50% code is refused for the code tower;
  injecting a design-only shard destroyed code accuracy even at the gentle learning rate.

---

## 7. Interfaces

**API** (`minicoder serve`) — 21 endpoints plus `/ws/telemetry`:

```
GET  /api/health  /api/status  /api/graph  /api/episodes  /api/skills
GET  /api/eval  /api/training  /api/vision  /api/vision/{vid}/image
GET  /api/sleep/reports  /api/sleep/latest
GET  /api/editor/tools  /api/editor/state  /api/export/snapshot
GET  /api/memory/search?q=…      POST /api/memory
POST /api/chat  /api/vision/inspect  /api/sleep
POST /api/editor/canvas  /api/editor/tool
WS   /ws/telemetry
```

**Dashboard** — seven tabs (Overview, Copilot, Knowledge, Memory, Vision, Training,
**Acquisition**). The Acquisition tab shows skills acquired vs awaiting verification vs rejected,
the failure taxonomy, retention sparklines per skill, benchmark results by category with the
reported failures, the eight acceptance checks, and resource/checkpoint/baseline history — all
from recorded rows, with "not run" shown where a report is missing rather than a zero. The graph view is a
hand-rolled canvas force simulation, not a charting library. Verified by a headless render harness:
`11/11` checks including a real chat round-trip.

The API reports the *answerer's* provenance. An earlier version labelled every non-acting reply
`"memory"`, which claimed evidence that did not exist for refusals.

---

## 8. Repository map

```
minicoder/
  config.py          every knob; Paths resolves against an activate_home() redirect
  data.py            25 code tasks (6 sealed), personas, UI classes, authored Q&A
  seed.py            parse the real editor catalogues, seed verified knowledge
  cli.py             the CLI
  model/             tokenizer, transformer + LoRA, training, embeddings, ViT, pipeline
  memory/            schema.sql, db.py, systems.py (5 memory systems)
  cognition/         metacognition, grounded answering, design agent
  learning/          audit → discovery → criteria → planner → synth → engine → safeguard
                     (experiments, hypotheses, attempts, skill_candidates, replay, benchmark)
  tools/             editor_bridge (Node), sandbox (permissioned), vision
  sleep/             compiler, trainer, engine, github
  eval/              suites.py
  api/app.py         FastAPI
  dashboard/         React + Vite + TypeScript
  tests/             87 tests
.github/workflows/   ci.yml, continual-learning.yml
```

---

## 9. Honest limits

- **Generalisation is the bottleneck.** 0.8947 in-distribution, 0.0 on sealed tasks. Memory and
  verification compensate; they do not make a 1.3M model reason like a large one.
- **Retrieval needs lexical help.** The trained embedder separates related from unrelated text by
  only ~0.11 cosine, so retrieval is BM25 + RRF with synonym expansion and weighted literal
  matching. Dense-only search was measurably unreliable and is not used alone.
- **Vision is fixture-bound.** 1.0 on the 8 procedurally rendered classes it was trained on; it is
  a real classifier for those, not a general screen-understanding model.
- **The `act` path depends on the Node bridge.** Without `node_modules` the agent reports
  `editor bridge unavailable` rather than pretending to have acted.
- **Acquired programs are depth-bounded.** Enumeration over primitives reaches 20 of 22 sealed
  tasks. Anything needing sequential character-level state fails, and is reported.
- **Geometric adaptation has a ceiling.** A learned 3:4 layout transfers to another 3:4 canvas via
  targeted repair; a flipped 4:3 canvas fails because the layers physically do not fit. The
  system re-acquires rather than pretending the skill transferred.
- **The planner's text heuristics are crude.** Inflection and shared-prefix matching stand in for
  stemming. They work on the current probe set; a real stemmer is the correct fix.
- **The neural study is reduced-scale.** 12 pretraining epochs and 20 SFT epochs, not the shipped
  40/40. It is a controlled comparison between variants, not a claim about the shipped model.

---

## 10. Tests

```bash
PYTHONPATH=. pytest minicoder/tests -q     # 87 passed
.venv/bin/ruff check minicoder/            # all checks passed
npm run verify                             # editor typecheck + smoke + smoke:ai + smoke:ui + build
cd minicoder/dashboard && npx vite-node scripts/render-check.tsx   # 11/11
```

`test_prime_directives.py` holds the safety invariants. `test_systems.py` covers the model, eval
isolation, CLI and API. `test_learning_phase2.py` covers the acquisition loop and is mostly about
*refusal*: sandbox escapes blocked, unverified candidates rejected, single-replay candidates
rejected, regressions caught, tampering detected.

All three run in throwaway homes, so testing never touches the live brain. That rule was learned
the hard way: a test that called `restore()` without an explicit target hit the default checkpoint
directory and wrote an 8-byte fixture over the real `lm.pt`. It was caught by four pre-existing
tests failing, restored from the automatic `pre_restore` backup, and verified back to
`0.875 / 0.875 / 5.6829`. `restore()` now defaults to the manifest's recorded origin and both
tests take the isolated `home` fixture.
