# Sleep Skills — compiled, verified training shards

This directory is the **only** path by which MiniCoder's experience becomes
training data. Shards are written exclusively by the sleep engine
(`minicoder sleep`, stage 6) after the verification gate passes, and are
consumed by the `sleep_skill_training` GitHub workflow
(`.github/workflows/sleep_skill_training.yml`).

## What's in this directory

| File | What |
| --- | --- |
| `shard_20261115_130103.jsonl` | Seed shard: 30 examples compiled from **5 pytest-verified Python skills** (fibonacci, clamp, palindrome, chunk_list, merge_dedup_sorted). Provenance on every line. |
| `manifest.json` | Shard registry: per-shard example counts, SHA-256, per-skill breakdown. |

## Line schema (`TrainingExample`)

```json
{
  "id": "…16 hex…",
  "skill_id": "skill_…",
  "kind": "instruction | chain_of_thought | synthetic_variation | edge_case",
  "messages": [{"role": "user", "content": "…"}, {"role": "assistant", "content": "…"}],
  "provenance": {
    "source": "verified_execution",
    "skill_id": "skill_…",
    "verification_status": "VERIFIED",
    "verification_hash": "…64 hex SHA-256 of the gate outputs…",
    "license": "MIT",
    "synthetic": false,
    "example_hash": "…16 hex, content-addressed…",
    "compiled_at": "2026-11-15T…Z"
  }
}
```

## The contract (enforced by `minicoder/training/validate_shard.py`)

1. Every example's `verification_status` is `VERIFIED` — 100% of the gates that
   produced the skill passed (syntax + pytest in this repo).
2. `source` ∈ {verified_execution, visual_inspection, user_instruction, documentation, training_data}.
3. `license` ∈ {MIT, Apache-2.0, BSD-2-Clause, BSD-3-Clause, ISC, CC0-1.0, CC-BY-4.0}.
4. `verification_hash` is present, `example_hash` is unique per example.
5. Unverified skills are quarantined in `memory/procedural/` and **never** reach this directory.

Synthetic variations are deterministic (seeded from the skill id) surface-level
rephrasings flagged with `"synthetic": true` — never fabricated capabilities.

## Adding new shards

Sleep runs compile them automatically. To publish: merge the
`sleep/skills-*` branch (the sleep engine opens it via a throwaway worktree
when `MINICODER_GITHUB_DISPATCH=1`) or just push to `main` touching this
directory — CI then validates, trains MiniCoder-Nano from scratch, and
publishes a versioned adapter release **only if the holdout gate passes**.
