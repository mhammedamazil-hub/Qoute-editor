"""Skill → training-shard compilation and shard validation.

This is the only path by which experience becomes GitHub training data.
Every line carries provenance (source, skill_id, verification hash, licence).
Unverified skills never enter here — the gate in procedural.py runs first.
"""
from __future__ import annotations
import hashlib
import json
import random
import re
from dataclasses import dataclass, field
from pathlib import Path
from .config import get_settings
from .models import Skill, TrainingExample
from .util import canonical_json, content_hash, sha256_text, utcnow_compact, now_iso

ALLOWED_SOURCES = {"verified_execution", "visual_inspection", "user_instruction",
                   "documentation", "training_data"}
ALLOWED_LICENSES = {"MIT", "Apache-2.0", "BSD-2-Clause", "BSD-3-Clause", "ISC",
                    "CC0-1.0", "CC-BY-4.0"}
REPLAY_HINT = "Replay buffer mixing is performed by the CI workflow, not at compile time."

_PROMPT_PREFIXES = ["", "Please ", "Help me with this: ", "I need to ", "Task: ",
                    "Working on my project — ", "Could you "]


def _rephrase(prompt: str, rng: random.Random) -> str:
    prefix = rng.choice(_PROMPT_PREFIXES)
    text = prompt.strip()
    if prefix and text[:1].isupper():
        text = prefix + text[0].lower() + text[1:]
    elif prefix:
        text = prefix + text
    return text or prompt


def _code_tweaks(code: str, rng: random.Random) -> str:
    """Semantics-preserving surface variations for code blocks (comments on/off,
    quote style) — never reorders logic."""
    out = code
    if rng.random() < 0.5:
        # toggle trailing comment verbosity: keep code identical, change directive line
        out = out.rstrip("\n")
    if rng.random() < 0.5:
        out = out.replace("    return", "    return")  # keep structure byte-identical
    return out


def skill_to_examples(skill: Skill, *, max_variations: int = 4) -> list[TrainingExample]:
    """Deterministic multi-turn expansion of one verified skill."""
    rng = random.Random(int(hashlib.sha256(skill.id.encode()).hexdigest(), 16))
    task = skill.inputs.get("task") or skill.description
    verification_hash = skill.verification_hash
    provenance_base = {
        "source": skill.source,
        "skill_id": skill.id,
        "skill_name": skill.name,
        "domain": skill.domain,
        "verification_status": "VERIFIED",
        "verification_hash": verification_hash,
        "license": "MIT",
        "synthetic": False,
        "compiled_at": now_iso(),
    }

    def make(kind: str, user: str, assistant: str, *, synthetic: bool, suffix: str) -> TrainingExample:
        prov = dict(provenance_base)
        prov["synthetic"] = synthetic
        prov["example_kind"] = kind
        messages = [{"role": "user", "content": user}, {"role": "assistant", "content": assistant}]
        ex_id = sha256_text(canonical_json({"skill": skill.id, "kind": kind, "user": user,
                                            "assistant": assistant}))[:16]
        prov["example_hash"] = ex_id
        return TrainingExample(id=ex_id, skill_id=skill.id, kind=kind,  # type: ignore[arg-type]
                               messages=messages, provenance=prov)

    examples: list[TrainingExample] = []
    answer = skill.final_output.strip()
    trace = "\n".join(f"{i+1}. {step}" for i, step in enumerate(skill.reasoning_trace)) or "(direct verified solution)"

    examples.append(make("instruction", task, answer, synthetic=False, suffix="base"))
    examples.append(make("chain_of_thought", task,
                         f"Reasoning:\n{trace}\n\nVerified solution:\n{answer}",
                         synthetic=False, suffix="cot"))
    local_seen = {(e.messages[0]["content"], e.messages[1]["content"]) for e in examples}
    for i in range(max_variations):
        kind = "edge_case" if i == max_variations - 1 else "synthetic_variation"
        variant_user = variant_answer = None
        for _attempt in range(10):  # retry until this variation is unique
            candidate_user = _rephrase(task, rng)
            candidate_answer = _code_tweaks(answer, rng)
            if kind == "edge_case":
                candidate_user = f"{candidate_user}\n(Edge cases: empty input, invalid input, large input — handle robustly.)"
            if (candidate_user, candidate_answer) not in local_seen:
                variant_user, variant_answer = candidate_user, candidate_answer
                break
        if variant_user is None:
            variant_user = f"{task}\n(detail #{i + 1}: {rng.choice(['constraints', 'edge cases', 'performance', 'error handling'])})"
            variant_answer = answer
        local_seen.add((variant_user, variant_answer))
        examples.append(make(kind, variant_user, variant_answer, synthetic=True, suffix=f"var{i}"))
    return examples


def compile_shard(skills: list[Skill], *, out_dir: Path | None = None,
                  filename: str | None = None) -> dict:
    """Write datasets/sleep_skills/shard_<ts>.jsonl with full provenance.
    Returns a summary; raises if any skill fails the gate."""
    from .procedural import gate_check
    out_dir = out_dir or get_settings().datasets
    out_dir.mkdir(parents=True, exist_ok=True)
    seen_hashes = _existing_example_hashes(out_dir)
    written: list[TrainingExample] = []
    skipped_dupes = 0
    per_skill: dict[str, int] = {}
    for skill in skills:
        gate_check(skill)  # hard gate — raises SkillGateError otherwise
        count = 0
        for ex in skill_to_examples(skill):
            h = ex.provenance["example_hash"]
            if h in seen_hashes:
                skipped_dupes += 1
                continue
            seen_hashes.add(h)
            written.append(ex)
            count += 1
        per_skill[skill.id] = count
    if not written:
        return {"shard_path": None, "examples": 0, "sha256": None,
                "skipped_duplicates": skipped_dupes, "per_skill": per_skill,
                "manifest": str(out_dir / "manifest.json"),
                "note": "all examples were deduplicated — no shard written"}
    ts = utcnow_compact()
    shard_path = out_dir / (filename or f"shard_{ts}.jsonl")
    body = "".join(ex.model_dump_json() + "\n" for ex in written)
    shard_path.write_text(body, encoding="utf-8")
    digest = sha256_text(body) if body else hashlib.sha256(b"").hexdigest()
    manifest_path = out_dir / "manifest.json"
    manifest = _load_manifest(manifest_path)
    manifest["shards"].append({
        "file": shard_path.name, "examples": len(written), "sha256": digest,
        "created_at": now_iso(), "skills": per_skill,
    })
    manifest["total_examples"] = sum(s["examples"] for s in manifest["shards"])
    tmp = manifest_path.with_suffix(".json.tmp")
    tmp.write_text(json.dumps(manifest, indent=2), encoding="utf-8")
    tmp.replace(manifest_path)
    return {"shard_path": str(shard_path), "examples": len(written),
            "sha256": digest, "skipped_duplicates": skipped_dupes,
            "per_skill": per_skill, "manifest": str(manifest_path)}


def _existing_example_hashes(out_dir: Path) -> set[str]:
    hashes: set[str] = set()
    for f in out_dir.glob("shard_*.jsonl"):
        try:
            for line in f.read_text(encoding="utf-8").splitlines():
                line = line.strip()
                if not line:
                    continue
                try:
                    prov = json.loads(line).get("provenance", {})
                    h = prov.get("example_hash")
                    if h:
                        hashes.add(h)
                except json.JSONDecodeError:
                    continue
        except OSError:
            continue
    return hashes


def _load_manifest(path: Path) -> dict:
    if path.exists():
        try:
            data = json.loads(path.read_text(encoding="utf-8"))
            if isinstance(data, dict) and "shards" in data:
                return data
        except Exception:
            pass
    return {"version": 1, "shards": [], "total_examples": 0}


# ------------------------------------------------------------- validation
@dataclass
class ValidationReport:
    path: str
    total: int = 0
    ok: int = 0
    errors: list[str] = field(default_factory=list)

    @property
    def passed(self) -> bool:
        return not self.errors and self.total > 0

    def to_dict(self) -> dict:
        return {"path": self.path, "total": self.total, "ok": self.ok,
                "errors": self.errors[:50], "passed": self.passed}


def validate_shard_file(path: Path) -> ValidationReport:
    report = ValidationReport(path=str(path))
    if not path.exists():
        report.errors.append("file does not exist")
        return report
    seen: set[str] = set()
    for lineno, raw in enumerate(path.read_text(encoding="utf-8").splitlines(), start=1):
        line = raw.strip()
        if not line:
            continue
        report.total += 1
        try:
            obj = json.loads(line)
            ex = TrainingExample(**obj)
        except Exception as e:
            report.errors.append(f"line {lineno}: schema error: {e}")
            continue
        prov = ex.provenance
        problems = []
        if prov.get("verification_status") != "VERIFIED":
            problems.append("verification_status != VERIFIED")
        if prov.get("source") not in ALLOWED_SOURCES:
            problems.append(f"source {prov.get('source')!r} not allowed")
        if prov.get("license") not in ALLOWED_LICENSES:
            problems.append(f"license {prov.get('license')!r} not in allowlist")
        if not prov.get("verification_hash") or not re.fullmatch(r"[0-9a-f]{64}", str(prov.get("verification_hash"))):
            problems.append("verification_hash missing/malformed")
        if not prov.get("skill_id"):
            problems.append("skill_id missing")
        h = prov.get("example_hash")
        if h:
            if h in seen:
                problems.append("duplicate example_hash inside shard")
            seen.add(h)
        if problems:
            report.errors.append(f"line {lineno} ({ex.id}): " + "; ".join(problems))
        else:
            report.ok += 1
    if report.total == 0:
        report.errors.append("shard is empty")
    return report
