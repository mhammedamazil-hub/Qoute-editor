# MiniCoder

A small, honest cognitive system: it chats, writes code, looks at images, remembers what it
learned, sleeps on it, and ships only the improvements that survive a validation gate.

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
| **Sleep** | replay → consolidation → cross-modal patterns → conflicts → forgetting → shard compilation | `minicoder/sleep/` |
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

One cycle, seven stages (`minicoder sleep`):

| # | Stage | Effect (a measured run) |
|---|---|---|
| 1 | Prioritised replay | pending episodes ranked by surprise, failures, corrections |
| 2 | Consolidation | episodes → semantic knowledge (**unlearnable text is skipped**) |
| 3 | Cross-modal patterns | recurring keywords across modalities → `pattern` nodes |
| 4 | Organisation | conflicts detected and resolved by status strength |
| 5 | Forgetting | decay-aware archive, recoverable from `memory/archived/` |
| 6 | Skill compilation | verified skills → JSONL shard (**130 examples from 25 skills**) |
| 7 | GitHub dispatch + wake | push the shard, or fold in a released adapter |

Consolidation only admits text that looks like a real claim. A garbage decoder output
(`"b):      ="`, observed in an early cycle) is recorded as unlearnable and never enters long-term
memory — the test `test_consolidation_skips_unlearnable_episodes` holds that line.

---

## 6. Continual learning loop

```
sleep (local)  ──► shard + .sha256 ──► push to `sleep-skills`
                                          │
                       .github/workflows/continual-learning.yml
                         1. shard verify      checksum + provenance, or stop
                         2. LoRA train        rank 4, α 8, lr 5e-5, 6 epochs
                         3. validation gate   retention, skill NLL, LM CE
                         4. Release           only if the gate accepts
                                          │
wake (local)   ◄── adapter ◄──────────────┘
```

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

**Dashboard** — six tabs (Chat, Graph, Memory, Overview, Training, Vision). The graph view is a
hand-rolled canvas force simulation, not a charting library. Verified by a headless render harness:
`10/10` checks including a real chat round-trip.

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
  tools/             editor_bridge (Node), sandbox (permissioned), vision
  sleep/             compiler, trainer, engine, github
  eval/              suites.py
  api/app.py         FastAPI
  dashboard/         React + Vite + TypeScript
  tests/             51 tests
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

---

## 10. Tests

```bash
PYTHONPATH=. pytest minicoder/tests -q     # 51 passed
.venv/bin/ruff check minicoder/            # all checks passed
npm run verify                             # editor typecheck + smoke + smoke:ai + smoke:ui + build
cd minicoder/dashboard && npx vite-node scripts/render-check.tsx   # 10/10
```

`test_prime_directives.py` holds the safety invariants. `test_systems.py` covers the model, eval
isolation, CLI and API. Both run in throwaway homes, so testing never touches the live brain.
