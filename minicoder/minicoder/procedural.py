"""Procedural memory — the verified staging ground for neural weight updates.

A skill is VERIFIED only when 100% of its verification steps pass. Anything
else is quarantined and can NEVER reach a training shard.
"""
from __future__ import annotations
import hashlib
import json
from pathlib import Path
import yaml
from .config import get_settings
from .db import connect, log_provenance
from .models import Skill, VerificationStep, VerificationStatus
from .util import atomic_write_text, new_id, now_iso, content_hash


class SkillGateError(RuntimeError):
    """Raised when someone tries to promote an unverified skill."""


def _skill_path(skill_id: str) -> Path:
    return get_settings().procedural_dir / f"{skill_id}.yaml"


def _yaml_load(text: str) -> dict:
    return yaml.safe_load(text)


def save_skill(skill: Skill) -> Skill:
    settings = get_settings()
    settings.ensure_dirs()
    path = _skill_path(skill.id)
    atomic_write_text(path, yaml.safe_dump(skill.model_dump(mode="json"), sort_keys=False, allow_unicode=True))
    with connect() as con:
        con.execute(
            "INSERT INTO skills(id, name, domain, verification_status, confidence, path, times_used, created_at, updated_at)"
            " VALUES (?,?,?,?,?,?,0,?,?) ON CONFLICT(id) DO UPDATE SET"
            " name=excluded.name, domain=excluded.domain, verification_status=excluded.verification_status,"
            " confidence=excluded.confidence, path=excluded.path, updated_at=excluded.updated_at",
            (skill.id, skill.name, skill.domain, skill.verification_status, skill.confidence,
             str(path), skill.created_at, now_iso()),
        )
        log_provenance(con, "skill", skill.id, skill.source, f"status={skill.verification_status}")
    return skill


def load_skill(skill_id: str) -> Skill | None:
    path = _skill_path(skill_id)
    if not path.exists():
        return None
    data = _yaml_load(path.read_text(encoding="utf-8"))
    return Skill(**data)


def list_skills(*, status: str | None = None, domain: str | None = None) -> list[Skill]:
    sql, clauses, params = "SELECT id FROM skills", [], []
    if status:
        clauses.append("verification_status=?")
        params.append(status)
    if domain:
        clauses.append("domain=?")
        params.append(domain)
    if clauses:
        sql += " WHERE " + " AND ".join(clauses)
    with connect() as con:
        ids = [r["id"] for r in con.execute(sql, params).fetchall()]
    out = []
    for sid in ids:
        s = load_skill(sid)
        if s is not None:
            out.append(s)
    return out


def register_skill(*, name: str, description: str, domain: str,
                   final_output: str,
                   inputs: dict[str, str] | None = None,
                   reasoning_trace: list[str] | None = None,
                   tool_calls: list[dict] | None = None,
                   verification: list[VerificationStep] | None = None,
                   source: str = "verified_execution",
                   confidence: float = 0.6) -> Skill:
    """Create a skill and run the verification gate. The caller supplies the
    verification steps *with their observed exit codes* — the gate decides."""
    steps = verification or []
    all_passed = len(steps) > 0 and all(s.passed for s in steps)
    status = VerificationStatus.VERIFIED.value if all_passed else VerificationStatus.UNVERIFIED.value
    if steps and not all_passed:
        status = VerificationStatus.FAILED.value
    skill = Skill(
        id=new_id("skill"), name=name.strip(), description=description.strip(),
        domain=domain.strip().lower(), inputs=inputs or {},
        reasoning_trace=reasoning_trace or [], tool_calls=tool_calls or [],
        verification=steps, final_output=final_output,
        source=source, verification_status=status,
        confidence=(confidence if all_passed else min(confidence, 0.3)),
        created_at=now_iso(), updated_at=now_iso(),
    )
    return save_skill(skill)


def gate_check(skill: Skill) -> None:
    """The one door every training pipeline must walk through."""
    if skill.verification_status != VerificationStatus.VERIFIED.value:
        raise SkillGateError(
            f"Skill '{skill.name}' is {skill.verification_status}; only VERIFIED skills "
            f"may be compiled into training shards.")
    if not skill.verification:
        raise SkillGateError(f"Skill '{skill.name}' has no verification steps.")
    if not all(s.passed for s in skill.verification):
        raise SkillGateError(f"Skill '{skill.name}' has failing verification steps.")


def reverify_skill(skill: Skill, runner) -> Skill:
    """Re-run a skill's verification steps with a supplied runner callable
    (command:str -> (exit_code:int, output:str)). Previously FAILED skills
    that now pass are promoted to VERIFIED — honest, mechanical promotion."""
    new_steps: list[VerificationStep] = []
    for step in skill.verification:
        code, output = runner(step.command)
        new_steps.append(VerificationStep(
            name=step.name, command=step.command, exit_code=code,
            output_sha256=hashlib.sha256(output.encode("utf-8", errors="replace")).hexdigest(),
            passed=(code == 0),
        ))
    skill.verification = new_steps
    skill.verification_status = (
        VerificationStatus.VERIFIED.value if all(s.passed for s in new_steps)
        else VerificationStatus.FAILED.value
    )
    skill.confidence = min(1.0, skill.confidence + 0.15) if skill.verification_status == "VERIFIED" else skill.confidence
    skill.updated_at = now_iso()
    return save_skill(skill)


def mark_used(skill_id: str) -> None:
    with connect() as con:
        con.execute("UPDATE skills SET times_used=times_used+1, updated_at=? WHERE id=?",
                    (now_iso(), skill_id))


def verified_skills_since(last_sleep_iso: str | None) -> list[Skill]:
    """All currently-VERIFIED skills updated after the last sleep run."""
    out = []
    for s in list_skills(status="VERIFIED"):
        if last_sleep_iso is None or s.updated_at > last_sleep_iso:
            out.append(s)
    return out


def skill_verification_hash(skill: Skill) -> str:
    return content_hash({
        "name": skill.name, "domain": skill.domain,
        "verification": [s.model_dump() for s in skill.verification],
        "final_output": skill.final_output,
    })
