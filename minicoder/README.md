# MiniCoder — a compact, self-evolving cognitive intelligence core

MiniCoder is a working implementation of the "PROJECT MINICODER" blueprint: a
**learning cognitive system**, not a stateless wrapper. It combines persistent
multimodal-ready memory, a brain-inspired sleep cycle that compiles verified
skills into training datasets, and a GitHub Actions pipeline that fine-tunes a
from-scratch neural model on those datasets — all offline-first, all local,
every byte of it inspectable.

> **Honest scope statement.** This is a real, tested, working cognitive core —
> memory, metacognition, sleep, skill gating, dataset compilation, CI training
> — running on a compact **from-scratch** model (`MiniCoder-Nano`, a 170k-parameter
> byte-level neural net trained with a hand-written Adam on CPU). It is not a
> frontier LLM and does not pretend to be one. The default chat brain is
> memory-grounded and citation-carrying; cloud/local LLMs can be attached via
> opt-in env vars. No benchmark in this repo is fabricated: every number below
> was produced by running the code on this machine (2026-11-15).

## Verified, measured results (this repo, this machine)

| Check | Result |
| --- | --- |
| Unit/integration tests (`pytest` in `minicoder/`) | **36 / 36 pass** |
| Skill verification gate (syntax + pytest in a sandbox) | 5/5 demo skills VERIFIED; failing code quarantined |
| Sleep cycle (7 stages) | Runs in ~0.02 s; real replay/decay/archive/shard compile |
| Shard validation (`training/validate_shard.py`) | 30/30 examples pass schema+licence+provenance+hash gates |
| Cross-shard regression audit | 30/30 unique, 0 errors |
| Adapter training gate (`training/train_adapter.py`) | holdout perplexity **257.23 → 9.16** (−96.4 %), 600 steps, 1.5 s CPU, 170,496 params |
| Frontend | `tsc` clean; smoke/smoke:ai/smoke:ui pass; `vite build` ok (924 kB single-file PWA) |

## Architecture

```
                 ┌──────────────────────────── WAKE ───────────────────────────┐
 user ──► Brain ─┤ pre-action check (intent, retrieval, calibrated confidence) │
 (chat/api/cli)  │        │                                    │               │
                 │   answer w/ citations              clarify / tool           │
                 │        │                                    │               │
                 ▼        ▼                                    ▼               ▼
          Working Memory (capacity-limited, pinning, decay)   Tool sandbox
                 │                                             (allowlist, timeout,
        ┌────────┴─────────┬──────────────┬──────────────┐     pytest gates)
        ▼                  ▼              ▼              ▼
   Episodic           Semantic        Procedural      Visual buffer
   (SQLite-WAL+FTS5+  (NetworkX +     (YAML skills +   (dHash dedup,
    provenance)        SQLite)         gate)            stats, OCR-pluggable)
        │                  │              │              │
        └──────────┬───────┴──────────────┴──────────────┘
                   ▼
        ┌──────────────────────── SLEEP (7 stages) ─────────────────────────┐
        │ 1 replay → 2 consolidation → 3 cross-modal patterns →             │
        │ 4 conflict resolution → 5 decay+archive → 6 skill→dataset compile │
        │ → 7 GitHub dispatch (worktree+PR) + adapter check + report        │
        └─────────────────────────────┬─────────────────────────────────────┘
                                      ▼
                 datasets/sleep_skills/shard_<ts>.jsonl (VERIFIED only)
                                      ▼
   .github/workflows/sleep_skill_training.yml
   validate → train MiniCoder-Nano (from scratch, replay = all shards)
   → gate: holdout perplexity must beat baseline → publish release
                                      ▼
              next WAKE: brain reports the new adapter (manual pull)
```

Fast memory (working/episodic/semantic) is always separate from slow weights.
Weights change **only** via the sleep→CI pipeline, never during chat.

## Repository layout

```
minicoder/
├── pyproject.toml              # install: pip install -e ./minicoder  (CLI: `minicoder`)
├── minicoder/                  # the package (all offline, stdlib+pip deps only)
│   ├── config.py               #   MINICODER_HOME / datasets paths, capacities, thresholds
│   ├── models.py               #   strict Pydantic v2 schemas (episode, skill, shard line, report)
│   ├── db.py                   #   SQLite WAL + FTS5 schema, atomic backups, provenance ledger
│   ├── embeddings.py           #   from-scratch 384-d hashing embedder (L2-normalised)
│   ├── vecstore.py             #   sqlite-vec when available, NumPy cosine fallback — same file
│   ├── working_memory.py       #   capacity, priority, pinning, expiry, decay scoring
│   ├── episodic.py             #   autobiographical store + hybrid vector/FTS retrieval
│   ├── semantic.py             #   knowledge graph: NetworkX over SQLite, typed relations
│   ├── procedural.py           #   skill registry + the VERIFICATION GATE (single door)
│   ├── visual.py               #   image memory: dHash, stats, overflow/contrast heuristics, OCR hook
│   ├── llm.py                  #   pluggable providers (offline heuristic default; opt-in Gemini/GGUF)
│   ├── nano.py                 #   MiniCoder-Nano: from-scratch NumPy neural net (120-line Adam)
│   ├── sleep.py                #   the 7-stage Sleep Engine
│   ├── shard.py                #   skill → JSONL shard compiler + strict shard validator
│   ├── snapshot.py             #   one-zip brain export/import (safe-extract, merged import)
│   ├── brain.py                #   WAKE orchestrator, metacognition, telemetry events
│   ├── tools/sandbox.py        #   restricted subprocess sandbox (allowlist, no shell, timeouts)
│   ├── tools/coding.py         #   syntax gate + pytest gate (real exit codes, hashed outputs)
│   ├── api/                    #   FastAPI: REST /api/brain/* + WebSocket /ws/telemetry
│   └── cli.py                  #   `minicoder init|doctor|serve|chat|remember|search|skills|
│                               #    verify-code|sleep|report|stats|export|import|demo|eval`
├── training/                   # CI entry points used by the workflow
│   ├── validate_shard.py       #   gate 1 — schema/licence/provenance/hash audit
│   ├── train_adapter.py        #   gate 2 — train Nano from scratch; report real ppl
│   └── regression_eval.py      #   gate 3 — cross-shard dedup & integrity audit
└── tests/                      # 36 tests: WM, episodic, semantic, gate, sleep, shards, API…
datasets/sleep_skills/          # versioned, validated training shards (see its README)
.github/workflows/sleep_skill_training.yml
memory/                         # runtime brain (gitignored): brain.db, skills YAML, archives…
```

## Quickstart (fully offline after one install)

```bash
python3.11 -m venv ~/.minicoder-venv && source ~/.minicoder-venv/bin/activate
pip install -e './minicoder[vec,dev]'     # one-time; needs network only for pip

minicoder demo       # end-to-end: verify 5 skills → sleep → shard → report
minicoder doctor     # hardware + provider + memory check
minicoder serve      # 0.0.0.0:8765 — API + built PWA dashboard; open it on a
                     # phone on the same LAN for the full mobile experience
minicoder chat       # terminal chat (Ctrl-D to exit; /sleep /stats /memories)
```

Dashboard: build the frontend once (`npm run build`), then `minicoder serve`
serves it at `/` — the **Brain** button in the top bar (or `Ctrl/⌘+K → "Open
the MiniCoder Brain"`) opens the cognitive monitor: live state, WM load,
memory counts, chat with citations, skill browser, sleep trigger + report,
knowledge-graph explorer. In dev (`npm run dev`), `/api` and `/ws` are proxied
to `127.0.0.1:8765` automatically.

## The git-push boundary (nothing leaves your machine unless you say so)

- Default: sleep compiles the shard locally and reports `pending_dispatch`.
  **No git commands are run, no network is touched.**
- Opt-in: `MINICODER_GITHUB_DISPATCH=1 minicoder sleep` creates a **throwaway
  `git worktree`**, commits the shard on `sleep/skills-<ts>`, pushes, and opens
  a PR. Your working tree and current branch are never switched — the user's
  checkout is untouched no matter what fails.
- The `sleep_skill_training` workflow runs on shards pushed to `main` (or any
  PR touching `datasets/sleep_skills/`): validate → train → **gate** →
  release. The release job runs only off `main`/manual dispatch. If the
  holdout gate fails, the workflow fails loudly and **no release is
  published**. There is no configuration in which an unverified skill is
  trained on, or an unmeasured claim is printed.

## Memory & provenance contract

Every row carries `source` ∈ `{user_instruction, verified_execution,
visual_inspection, documentation, training_data, unverified_hypothesis}` + UTC
timestamp, and an audit trail in the `provenance` table. Forgetting is
decay-scored (recency × access frequency × confidence), and low-priority
episodes are **archived** to `memory/archived/archive_<ts>.jsonl` —
recoverable, never destroyed (Prime Directive 3). `minicoder export` produces
one zip (DB + skills + sleep logs + graph snapshot); `minicoder import`
merge-imports it after taking a pre-import backup.

## Security model

- The tool sandbox is a **containment mechanism for accidents**, not a boundary
  against hostile code: command allowlist (python/pytest/node/git/…), no
  `shell=True`, scrubbed environment, 30 s timeouts, 64 kB output cap, isolated
  cwd under `memory/working/sandbox-*`. For adversarial code, run in Docker/VM.
- Stored procedures are never auto-executed: sleep re-verification only re-runs
  steps whose `sandbox_retest` material is embedded in the episode metadata,
  through the same allowlist.
- The brain never executes git/gh during sleep unless `MINICODER_GITHUB_DISPATCH=1`.

## Metacognition, made measurable

- **Pre-action check** (`brain.pre_action_check`): intent classification →
  hybrid retrieval → calibrated confidence = f(retrieval score, query clarity).
  Below `clarification_threshold` (default 0.34) the brain asks a clarifying
  question instead of guessing. Every decision is logged as an episode.
- **Post-action verification**: tool/test exit codes are compared against
  expectation; failures land in episodic memory with `verification_status=FAILED`
  and feed the sleep engine's weakness-repair loop (stage 6 re-runs embedded
  retest material; passes promote FAILED→VERIFIED mechanically).

## Limitations (read me)

1. `MiniCoder-Nano` is a small, from-scratch net — its perplexity drop proves
   the pipeline learns; it does **not** make the system a general reasoner.
2. The from-scratch lexical embedder is strong on keyword overlap, weaker on
   deep paraphrase. Interface is pluggable (`embeddings.embed_text`) — drop in
   sentence-transformers later without touching call sites.
3. OCR activates only when `rapidocr-onnxruntime`/`pytesseract` is installed;
   otherwise the visual pipeline reports OCR as unavailable instead of
   inventing text.
4. Pretraining-scale corpus work (The Stack etc.) is out of scope here; the
   pipeline is the deliverable — point it at legally-clean corpora in new
   shards and the same gates, training and release flow apply.
5. GitHub-hosted CI trains CPU-bound in ~2 s for this shard size. For
   1B-class adapters you would use a self-hosted GPU runner — the workflow
   gate stays identical, only the trainer changes.

## Tests

```bash
cd minicoder
./.venv/bin/python -m pytest            # or any python with the deps
```
Covers: working-memory capacity/pinning/expiry, episodic store + retrieval +
provenance, knowledge graph, the skill gate (pass/fail/quarantine/re-verify),
shard compile/validate/dedup, all seven sleep stages end-to-end, the API
(FastAPI TestClient), snapshot export/import, the Nano trainer and CLI demo.
