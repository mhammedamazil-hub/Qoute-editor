# Changelog

All measured numbers below come from `datasets/training_runs/eval_report.json` and the sleep/training
reports in `memory/sleep_logs/` and `datasets/training_runs/`.

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
