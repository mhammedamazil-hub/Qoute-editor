# Phase 2 Audit — what is actually there

Independent audit performed before any Phase 2 code was written. Every claim below was
reproduced in this workspace; nothing is taken from earlier development logs.

## Environment (re-verified)

| Property | Measured |
|---|---|
| CPU cores | 2 (Intel Xeon @ 2.60 GHz, AVX-512F/BW/CD/DQ) |
| RAM | 3.8 GB total, ~2 GB available |
| GPU / CUDA | none (`torch.cuda.is_available() == False`) |
| PyTorch | 2.15.0+cu132, 1 thread |
| Disk free | 9.6 GB |
| PyPI / npm / GitHub | reachable (HTTP 200) |
| huggingface.co / download.pytorch.org | **unreachable** (connection closed) |

## Baseline reproduced

| Suite | Claimed | Reproduced | Verdict |
|---|---|---|---|
| retrieval | P@1 1.0, MRR 1.0 | 1.0 / 1.0 | passes, but **circular** (below) |
| chat | retention 1.0, hallucination 0.0 | 1.0 / 0.0 | passes, but **self-seeded fixtures** |
| multisession | recall 1.0 | 1.0 | passes |
| coding (indist) | exact 0.8947 | 0.8947 | honest — model reproduces its training tasks |
| coding (holdout) | exact 0.0 | 0.0 | **honest and correctly sealed** |

Holdout sealing verified two ways: none of the six holdout task names appear in
`build_code_corpus()`, and none of their solution bodies appear in the raw training text.

## What is genuinely functional

- **Editor bridge**: 37 real tools over newline-JSON, 10.7 s startup then ~1 ms per call.
  State introspection exposes per-layer `type/x/y/w/h/text/font/size/weight/color`. This is a
  real substrate for experimentation.
- **Sandbox execution**: real subprocess execution with rlimits (AS, CPU, NOFILE, FSIZE, NPROC),
  env scrubbing, and working CPU-timeout kill.
- **Memory systems**: 5 stores in one SQLite DB with `sqlite-vec`, provenance events, atomic
  backup/restore.
- **Sleep engine**: 7 real stages, pre-cycle atomic snapshot, hash-pinned shard compilation.
- **LoRA trainer + gate**: real training, real before/after measurement, real promotion/rollback
  of checkpoint files.
- **Vision classifier**: real 206k-param MiniViT, 1.0 on its 8 rendered classes.

## What is NOT what it appears to be

These are the findings that Phase 2 had to address. They are recorded here rather than quietly
patched, because the distinction between *appearing* to learn and *learning* is the whole point.

### 1. No component ever acquires a new skill

Skill creation has exactly three paths, and none of them solves a task it did not already have
the answer to:

| Path | What it actually does |
|---|---|
| `seed.py` | Re-types **human-authored** solutions and **human-authored** tests from `data.py`, runs the tests, stores the pair. The `reasoning` list is fabrication ("Read the specification… Choose the simplest algorithm") — nothing reasoned. |
| `agent.py` | Regex lookup tables over palette/font/size keywords → a fixed tool sequence. Verified `parse_instruction` extracts **nothing** from novel phrasings ("build me something for a funeral notice", "4:5 ratio, muted, for a museum", "austere wabi-sabi composition"). |
| `sleep._compile` | "Self-practice" only re-runs stored tests against stored solutions. It can re-verify; it cannot acquire. |

There is no task decomposition, no hypothesis formation, no error-driven repair, and no
attempt tracking anywhere in the codebase (`grep first_attempt|attempts` → zero hits).

### 2. The benchmark set is circular or self-authored

- `eval_memory_retrieval` writes its own 6 documents and then queries them with probes that share
  literal words. It measures that SQLite works, not that retrieval generalises.
- `eval_chat` seeds the very facts it then asks for.
- `eval_coding` is the one honest suite: sealed holdout, 0.0, and that number is reported.

There is **no** benchmark covering file manipulation, data transformation, debugging, API usage,
multi-step operations, or tool discovery — all required by the Phase 2 brief.

### 3. The sandbox is not permissioned

Measured directly:

| Probe | Claimed | Actual |
|---|---|---|
| network | blocked | blocked **by this container's egress policy**, not by the sandbox |
| read `/etc/passwd` | blocked | **succeeds** |
| `os.system("echo …")` | blocked | **succeeds** |
| infinite loop | killed | killed (rlimit works) |

Only a substring blocklist guards `run_command`; `run_python` has no filesystem or process
confinement. This matters more in Phase 2, because an experiment engine runs far more untrusted
code than the old agent did.

### 4. Reported metrics mix states the brief requires separating

The brief requires distinguishing hypothesis / attempted solution / successful execution /
verified reusable skill. The schema has one `status` field, `used_count`, and no notion of an
attempt, a variation, a replay, or a dependency between skills.

## Consequence for Phase 2

The gap is specific and it is not "more architecture". It is the absence of a loop that:
forms a concrete plan against known tool interfaces → executes it → reads the real error →
changes the plan → verifies against independently-stated requirements → proves the procedure
replays in a fresh process → and only then promotes it.

Phase 2 builds that loop first, with an attempt record for every step, and only then expands.
