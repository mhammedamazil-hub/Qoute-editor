"""Skill -> dataset compilation (Level 3 of the continual-learning hierarchy).

Only ``VERIFIED`` skills may reach a training shard (prime directive #2). Each
skill is expanded into:

* an instruction-tuning example (prompt -> verified solution),
* a chain-of-thought example (reasoning trace included),
* N synthetic variants with renamed identifiers / altered literals to reduce
  overfitting,
* a replay-buffer share from core capabilities (anti-catastrophic-forgetting).

Every example carries full provenance: skill slug, verification hash, source,
timestamp, model/tokenizer fingerprint. The shard is written atomically and
hashed, then recorded in ``dataset_shards``.
"""

from __future__ import annotations

import hashlib
import json
import random
import re
import tempfile
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

from minicoder.config import CONFIG, VERIFIED
from minicoder.memory.db import BrainDB, sha256_file, utcnow

REPLAY_SEED_EXAMPLES: list[dict[str, str]] = [
    {"prompt": "Create a 1080x1350 portrait quote poster with generous margins.",
     "response": "create_canvas(width=1080, height=1350); add_text(content='Your quote', x=120, y=220, fontSize=72)"},
    {"prompt": "Apply the emerald luxury palette to the current design.",
     "response": "apply_palette(palette='emerald-luxury')"},
    {"prompt": "Which palette reads as premium?",
     "response": "Deep green with warm gold, or charcoal with champagne; keep the accent to hairlines."},
    {"prompt": "Explain why a flex child overflows its container.",
     "response": "A flex item's default min-width is auto, so it refuses to shrink below its content size. Set min-width:0."},
    {"prompt": "Summarise what a screenshot with a red banner at the top means.",
     "response": "An error banner: a destructive action failed and the user needs the message plus a recovery path."},
]


def _variant(solution: str, rng: random.Random, i: int) -> str:
    """Deterministic identifier/literal renaming, safe for Python snippets."""
    names = ["solve", "compute", "run", "process", "calculate", "handle", "transform"]
    replacement = names[(i + 1) % len(names)]
    out = re.sub(r"\bsolve\b", replacement, solution)
    nums = re.findall(r"\b(\d+)\b", out)
    if nums:
        n = rng.choice(nums)
        out = out.replace(n, str(max(2, int(n) + rng.choice([1, 2, 3]))), 1)
    return out


def compile_skill_examples(
    skill: dict[str, Any],
    *,
    variants: int,
    seed: int,
    replay_ratio: float,
) -> list[dict[str, Any]]:
    rng = random.Random(f"{seed}:{skill['slug']}")
    verification = json.loads(skill.get("verification") or "{}")
    if skill["status"] != VERIFIED or not verification.get("passed"):
        return []
    prompt = f"{skill['description']}\n\nTask: {skill['name']}".strip()
    reasoning = json.loads(skill.get("reasoning") or "[]")
    solution = skill.get("solution") or ""
    vhash = verification.get("hash", "")
    base = {
        "skill": skill["slug"],
        "source": "verified_execution",
        "verification_hash": vhash,
        "origin": skill.get("source", ""),
        "domain": skill.get("domain", "general"),
        "confidence": skill.get("confidence", 0.5),
    }
    examples: list[dict[str, Any]] = []

    examples.append({**base, "kind": "sft", "prompt": prompt, "response": solution,
                     "reasoning": reasoning})
    if reasoning:
        cot = "\n".join(f"{i+1}. {step}" for i, step in enumerate(reasoning))
        examples.append({**base, "kind": "cot", "prompt": prompt,
                         "response": f"Reasoning:\n{cot}\n\nSolution:\n{solution}"})
    for i in range(variants):
        v = _variant(solution, rng, i)
        examples.append({**base, "kind": "synthetic", "variant": i + 1, "prompt": prompt,
                         "response": v, "reasoning": reasoning})

    # NOTE: core-capability replay is injected ONCE per shard by ``build_shard``
    # (see ``_core_replay``), not once per skill. Per-skill replay multiplies the
    # replay share by the skill count and drowns out the new material.
    return examples


def _core_replay(replay_ratio: float) -> list[dict[str, Any]]:
    """Core-capability replay examples (anti-catastrophic-forgetting buffer)."""
    if replay_ratio <= 0:
        return []
    out = []
    for _i, r in enumerate(REPLAY_SEED_EXAMPLES):
        out.append({
            "kind": "replay", "skill": "replay_buffer", "source": "training_data",
            "verification_hash": "", "origin": "replay", "domain": "core",
            "confidence": 1.0, **r,
        })
    return out


def build_shard(
    *,
    limit_skills: int | None = None,
    db: BrainDB | None = None,
    seed: int | None = None,
    out_dir: Path | None = None,
) -> dict[str, Any]:
    """Compile all not-yet-exported verified skills into a versioned JSONL shard."""
    db = db or BrainDB()
    cfg = CONFIG.training
    seed = cfg.seed if seed is None else seed
    out_dir = (out_dir or CONFIG.paths.sleep_skills)
    out_dir.mkdir(parents=True, exist_ok=True)

    rows = db.query("SELECT * FROM skills WHERE status='VERIFIED' AND exported=0 ORDER BY id")
    skills = [dict(r) for r in rows]
    if limit_skills:
        skills = skills[:limit_skills]
    if not skills:
        return {"created": False, "reason": "no verified skills pending export", "examples": 0, "skills": 0}

    examples: list[dict[str, Any]] = []
    compiled_skills: list[int] = []
    fingerprint = ""
    tok_path = CONFIG.paths.checkpoints / "tokenizer.json"
    if tok_path.exists():
        fingerprint = hashlib.sha256(tok_path.read_bytes()).hexdigest()[:16]

    quarantined: list[str] = []
    for skill in skills:
        verification = json.loads(skill.get("verification") or "{}")
        # Provenance gate: a VERIFIED skill must carry a verification hash. If it
        # does not, it is untraceable and must not enter training data. Demote it
        # instead of aborting the whole cycle (prime directive #2 + resilience).
        if not verification.get("hash"):
            db.execute("UPDATE skills SET status='QUARANTINED', updated_at=? WHERE id=?",
                       (utcnow(), skill["id"]))
            db.log_provenance("skills", int(skill["id"]), "quarantine_no_hash",
                              detail={"slug": skill.get("slug", "")})
            quarantined.append(skill.get("slug", str(skill["id"])))
            continue
        exs = compile_skill_examples(
            skill, variants=cfg.synthetic_variants_per_skill, seed=seed, replay_ratio=cfg.replay_ratio
        )
        if not exs:
            continue
        for e in exs:
            e["created_at"] = utcnow()
            e["tokenizer_fingerprint"] = fingerprint
            e["schema_version"] = 1
        examples.extend(exs)
        compiled_skills.append(int(skill["id"]))

    # Inject the core replay buffer ONCE for the whole shard, scaled to its size.
    replay = _core_replay(cfg.replay_ratio)
    if replay and examples:
        target = max(1, int(round(len(examples) * cfg.replay_ratio / (1 - cfg.replay_ratio))))
        for e in (replay * (target // len(replay) + 1))[:target]:
            e["created_at"] = utcnow()
            e["tokenizer_fingerprint"] = fingerprint
            e["schema_version"] = 1
            examples.append(e)

    if not examples:
        return {"created": False, "reason": "no examples produced", "examples": 0, "skills": 0,
                "quarantined": quarantined}

    # Deduplicate: two skills can share a trajectory, which must not inflate the
    # dataset or poison training with repeated tokens.
    seen: set[str] = set()
    unique: list[dict[str, Any]] = []
    dropped = 0
    blank = 0
    for e in examples:
        # A lesson with an empty side is unlearnable and fails shard validation. Measured
        # in sleep cycle 4: "line 1: empty prompt/response" aborted skill compilation.
        if not str(e.get("prompt", "")).strip() or not str(e.get("response", "")).strip():
            blank += 1
            continue
        key = hashlib.sha256((e["prompt"] + "\x00" + e["response"]).encode()).hexdigest()
        if key in seen:
            dropped += 1
            continue
        seen.add(key)
        unique.append(e)
    examples = unique
    examples = unique
    validation_notes: dict[str, Any] = {"deduplicated": dropped, "blank_dropped": blank}
    if not examples:
        return {"created": False, "reason": "all examples were duplicates", "examples": 0,
                "skills": 0, "quarantined": quarantined}


    stamp = datetime.now(UTC).strftime("%Y%m%dT%H%M%SZ")
    path = out_dir / f"shard_{stamp}.jsonl"

    with tempfile.NamedTemporaryFile("w", dir=out_dir, delete=False, suffix=".tmp", encoding="utf-8") as fh:
        for e in examples:
            fh.write(json.dumps(e, ensure_ascii=False) + "\n")
        tmp = Path(fh.name)
    # Validate before publishing (Level 1 of the GitHub workflow, same code path).
    validation = validate_shard(tmp)
    if not validation["ok"]:
        tmp.unlink(missing_ok=True)
        raise ValueError(f"shard failed validation: {validation['errors'][:3]}")
    tmp.replace(path)
    digest = sha256_file(path)
    # Write the checksum sidecar next to every shard, not only when it is pushed.
    # A shard must be verifiable at the point it is created, so CI can refuse to
    # train on anything that was altered after compilation.
    path.with_suffix(path.suffix + ".sha256").write_text(
        f"{digest}  {path.name}\n", encoding="utf-8"
    )

    counts: dict[str, int] = {}
    for e in examples:
        counts[e["kind"]] = counts.get(e["kind"], 0) + 1
    meta = {
        "corpus_fingerprint": fingerprint,
        "seed": seed,
        "kinds": counts,
        "synthetic_variants_per_skill": cfg.synthetic_variants_per_skill,
        "replay_ratio": cfg.replay_ratio,
        "skills": [s for s in compiled_skills],
    }
    with db.write() as conn:
        conn.execute(
            "INSERT INTO dataset_shards(path, sha256, examples, created_at, meta) VALUES (?,?,?,?,?)",
            (str(path.relative_to(CONFIG.paths.home)), digest, len(examples), utcnow(), json.dumps(meta)),
        )
        conn.executemany("UPDATE skills SET exported=1 WHERE id=?", [(i,) for i in compiled_skills])
    db.log_provenance("dataset_shards", None, "compile",
                      detail={"path": path.name, "examples": len(examples), "sha": digest[:12]})
    return {
        "created": True,
        "path": str(path),
        "sha256": digest,
        "examples": len(examples),
        "skills": len(compiled_skills),
        "quarantined": quarantined,
        "counts": counts,
        "validation": {**validation, **validation_notes},
    }


# ------------------------------------------------------------------ checks
REQUIRED_FIELDS = {"kind", "prompt", "response", "source", "created_at", "schema_version"}
ALLOWED_KINDS = {"sft", "cot", "synthetic", "replay"}
ALLOWED_SOURCES = {"verified_execution", "training_data", "documentation", "user_instruction"}


def validate_shard(path: Path) -> dict[str, Any]:
    """Schema + provenance + verification-hash validation for a JSONL shard."""
    errors: list[str] = []
    seen: set[str] = set()
    n = 0
    duplicate = 0
    if not Path(path).exists():
        return {"ok": False, "errors": ["missing file"], "examples": 0}
    with Path(path).open("r", encoding="utf-8") as fh:
        for i, line in enumerate(fh, 1):
            line = line.strip()
            if not line:
                continue
            n += 1
            try:
                obj = json.loads(line)
            except json.JSONDecodeError as exc:
                errors.append(f"line {i}: invalid json ({exc})")
                continue
            missing = REQUIRED_FIELDS - obj.keys()
            if missing:
                errors.append(f"line {i}: missing {sorted(missing)}")
            if obj.get("kind") not in ALLOWED_KINDS:
                errors.append(f"line {i}: bad kind {obj.get('kind')!r}")
            if obj.get("source") not in ALLOWED_SOURCES:
                errors.append(f"line {i}: bad source {obj.get('source')!r}")
            if obj.get("kind") != "replay" and not obj.get("verification_hash"):
                errors.append(f"line {i}: verified example without a verification hash")
            if not str(obj.get("prompt", "")).strip() or not str(obj.get("response", "")).strip():
                errors.append(f"line {i}: empty prompt/response")
            key = hashlib.sha256((str(obj.get("prompt")) + "\x00" + str(obj.get("response"))).encode()).hexdigest()
            if key in seen:
                duplicate += 1
            seen.add(key)
    if duplicate:
        # Not fatal: the exporter deduplicates before writing. Reported so a
        # caller can see it happened.
        pass
    if n == 0:
        errors.append("empty shard")
    return {"ok": not errors, "errors": errors[:20], "examples": n, "duplicates": duplicate}


def shard_stats(path: Path) -> dict[str, Any]:
    kinds: dict[str, int] = {}
    skills: set[str] = set()
    chars = 0
    n = 0
    for line in Path(path).read_text(encoding="utf-8").splitlines():
        if not line.strip():
            continue
        obj = json.loads(line)
        n += 1
        kinds[obj["kind"]] = kinds.get(obj["kind"], 0) + 1
        skills.add(obj.get("skill", ""))
        chars += len(obj.get("prompt", "")) + len(obj.get("response", ""))
    return {"examples": n, "kinds": kinds, "skills": len(skills - {""}), "chars": chars,
            "bytes": Path(path).stat().st_size}
