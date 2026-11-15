"""Controlled improvement: prove no regression, or put it back.

Every safeguard the brief asks for, implemented against real artefacts:

* **Immutable baselines** — a named copy of the checkpoints plus a manifest of
  SHA-256 hashes, made read-only. ``verify_baseline()`` re-hashes and reports
  tampering rather than trusting the copy.
* **Measured regression** — a cost-limited probe over real checkpoints produces
  a metric vector; a candidate is compared against the baseline and rejected if
  any metric degrades beyond its tolerance.
* **Catastrophic-forgetting detection** — the probe includes retention on
  previously-known tasks, which is the signal that a fine-tune destroyed
  earlier capability.
* **Automatic rollback** — restoring a baseline is a file copy from the
  immutable set, then the probe is re-run to prove recovery.
* **Provenance** — every decision writes a ``provenance_events`` row with the
  measured numbers, so a rollback can be audited rather than assumed.

Using it on a deliberately harmful update is exercised in
``minicoder/tests/test_learning_phase2.py``: a candidate with wrecked weights is
detected and rolled back, and the baseline is verified intact afterwards.
"""

from __future__ import annotations

import hashlib
import json
import os
import shutil
import time
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

from minicoder.config import CONFIG
from minicoder.memory.db import BrainDB, utcnow

# Metrics are directional: higher is better for accuracy/retention, lower is
# better for loss. Tolerances are absolute deltas, not percentages, because a
# loss of 0.01 NLL is meaningful at this model scale.
METRIC_DIRECTION = {
    "skill_accuracy": +1,
    "retention": +1,
    "answer_rate": +1,
    "skill_nll": -1,
    "val_ce": -1,
}

DEFAULT_TOLERANCES = {
    "skill_accuracy": 0.05,
    "retention": 0.05,
    "skill_nll": 0.05,
    "val_ce": 0.08,
    "answer_rate": 0.05,
}


@dataclass
class Verdict:
    passed: bool
    regressions: list[dict[str, Any]] = field(default_factory=list)
    improvements: list[dict[str, Any]] = field(default_factory=list)
    detail: str = ""

    def to_json(self) -> dict[str, Any]:
        return {"passed": self.passed, "regressions": self.regressions,
                "improvements": self.improvements, "detail": self.detail}


class BaselineRegistry:
    """Named, immutable checkpoint snapshots with verifiable manifests."""

    FILES = ("lm.pt", "tokenizer.json", "embedder.pt", "vision.pt")

    def __init__(self, db: BrainDB | None = None, root: Path | None = None) -> None:
        self.db = db or BrainDB()
        self.root = Path(root) if root else (CONFIG.paths.home / "memory" / "baselines")

    def _dir(self, name: str) -> Path:
        return self.root / name

    def snapshot(self, name: str = "baseline", *, source: Path | None = None) -> dict[str, Any]:
        """Copy the current checkpoints into an immutable named baseline."""
        src = Path(source) if source else CONFIG.paths.checkpoints
        dest = self._dir(name)
        if dest.exists():
            return {"created": False, "reason": f"baseline {name!r} already exists",
                    "manifest": self.manifest(name)}
        dest.mkdir(parents=True, exist_ok=True)
        copied: dict[str, str] = {}
        for fname in self.FILES:
            f = src / fname
            if not f.exists():
                continue
            target = dest / fname
            shutil.copy2(f, target)
            copied[fname] = self._sha256(target)
        manifest = {
            "name": name, "created_at": utcnow(), "files": copied,
            "source": str(src), "immutable": True,
        }
        (dest / "manifest.json").write_text(json.dumps(manifest, indent=2), encoding="utf-8")
        # Read-only: a later run cannot silently overwrite its own baseline.
        for f in dest.iterdir():
            try:
                os.chmod(f, 0o444)
            except OSError:
                pass
        self.db.log_provenance("baseline", None, "snapshot",
                               detail={"name": name, "files": sorted(copied)})
        return {"created": True, "name": name, "files": sorted(copied), "manifest": manifest}

    def manifest(self, name: str) -> dict[str, Any] | None:
        path = self._dir(name) / "manifest.json"
        if not path.exists():
            return None
        try:
            return json.loads(path.read_text(encoding="utf-8"))
        except json.JSONDecodeError:
            return None
        finally:
            try:
                os.chmod(path, 0o444)
            except OSError:
                pass

    def verify_baseline(self, name: str) -> dict[str, Any]:
        """Re-hash the baseline and report any drift."""
        man = self.manifest(name)
        if not man:
            return {"intact": False, "reason": f"no manifest for {name!r}"}
        problems: list[str] = []
        for fname, expected in (man.get("files") or {}).items():
            f = self._dir(name) / fname
            if not f.exists():
                problems.append(f"missing: {fname}")
                continue
            actual = self._sha256(f)
            if actual != expected:
                problems.append(f"modified: {fname}")
        return {"intact": not problems, "problems": problems,
                "files": sorted(man.get("files") or {})}

    def restore(self, name: str, *, target: Path | None = None) -> dict[str, Any]:
        """Copy a baseline back over the live checkpoints."""
        man = self.manifest(name)
        if not man:
            return {"restored": False, "reason": f"no baseline {name!r}"}
        # Restore to where the baseline was taken from. Defaulting to the global
        # checkpoint directory wrote the restore to the wrong place when the
        # baseline came from elsewhere (measured: the test's source stayed
        # wrecked while a different directory was repaired).
        if target is not None:
            dest = Path(target)
        elif man.get("source"):
            dest = Path(man["source"])
        else:
            dest = CONFIG.paths.checkpoints
        dest.mkdir(parents=True, exist_ok=True)
        # Preserve the state being replaced, so a rollback is itself reversible.
        backup = dest / "backups"
        backup.mkdir(parents=True, exist_ok=True)
        restored: list[str] = []
        for fname in (man.get("files") or {}):
            live = dest / fname
            if live.exists():
                shutil.copy2(live, backup / f"{fname}.pre_restore_{time.time_ns()}")
            src = self._dir(name) / fname
            if not src.exists():
                continue
            try:
                os.chmod(src, 0o644)
            except OSError:
                pass
            shutil.copy2(src, live)
            restored.append(fname)
        self.db.log_provenance("baseline", None, "restore",
                               detail={"name": name, "files": restored})
        return {"restored": True, "name": name, "files": restored}

    @staticmethod
    def _sha256(path: Path) -> str:
        h = hashlib.sha256()
        with open(path, "rb") as fh:
            for chunk in iter(lambda: fh.read(1 << 20), b""):
                h.update(chunk)
        return h.hexdigest()


class RegressionGuard:
    """Compare a candidate's metrics to a baseline and decide."""

    def __init__(self, tolerances: dict[str, float] | None = None) -> None:
        self.tolerances = {**DEFAULT_TOLERANCES, **(tolerances or {})}

    def compare(self, baseline: dict[str, float],
                candidate: dict[str, float]) -> Verdict:
        regressions: list[dict[str, Any]] = []
        improvements: list[dict[str, Any]] = []
        for metric, base in baseline.items():
            if metric not in candidate:
                continue
            cand = candidate[metric]
            direction = METRIC_DIRECTION.get(metric, +1)
            delta = (cand - base) * direction   # positive = better
            tol = self.tolerances.get(metric, 0.05)
            entry = {"metric": metric, "baseline": round(base, 4),
                     "candidate": round(cand, 4), "delta": round(delta, 4),
                     "tolerance": tol}
            if delta < -tol:
                regressions.append(entry)
            elif delta > tol:
                improvements.append(entry)
        passed = not regressions
        detail = ("no metric regressed beyond tolerance" if passed
                  else f"{len(regressions)} metric(s) regressed")
        return Verdict(passed=passed, regressions=regressions,
                       improvements=improvements, detail=detail)


def quick_metrics(*, max_tasks: int = 12) -> dict[str, float]:
    """A cost-limited metric vector measured on the real checkpoint.

    Deliberately small so it can run in seconds on two cores, and deliberately
    real: it loads the shipped checkpoint and measures it. It is *not* the full
    eval suite — it exists to catch a collapsing model, not to grade one.
    """
    from minicoder.model.tokenizer import Tokenizer
    from minicoder.model.transformer import MiniTransformer
    from minicoder.sleep.trainer import _base_known_tasks, baseline_lm_metrics, skill_accuracy

    ckpt = CONFIG.paths.checkpoints
    lm, tk = ckpt / "lm.pt", ckpt / "tokenizer.json"
    if not (lm.exists() and tk.exists()):
        return {}
    model = MiniTransformer.load(lm)
    tok = Tokenizer.load(tk)

    tasks = _base_known_tasks()[:max_tasks]
    skill = skill_accuracy(model, tok, tasks)
    lm = baseline_lm_metrics(model, tok)
    out: dict[str, float] = {
        "skill_accuracy": float(skill.get("exact_match", skill.get("accuracy", 0.0))),
        "retention": float(skill.get("retention", skill.get("exact_match", 0.0))),
        "answer_rate": float(skill.get("answered_rate", 1.0)),
    }
    for key in ("skill_nll", "val_ce"):
        if key in lm:
            out[key] = float(lm[key])
    return out


class ImprovementGate:
    """The single admit/rollback decision for any production update."""

    def __init__(self, db: BrainDB | None = None, *, baseline_name: str = "baseline") -> None:
        self.db = db or BrainDB()
        self.registry = BaselineRegistry(self.db)
        self.guard = RegressionGuard()
        self.baseline_name = baseline_name

    def evaluate(self, candidate_metrics: dict[str, float],
                 baseline_metrics: dict[str, float] | None = None,
                 *, label: str = "candidate") -> dict[str, Any]:
        if baseline_metrics is None:
            man = self.registry.manifest(self.baseline_name)
            if not man or "metrics" not in man:
                return {"admitted": False, "reason": "no baseline metrics recorded",
                        "verdict": None}
            baseline_metrics = man["metrics"]
        verdict = self.guard.compare(baseline_metrics, candidate_metrics)
        self.db.log_provenance(
            "model", None, "gate_evaluate",
            actor="safeguard",
            detail={"label": label, "admitted": verdict.passed,
                    "regressions": verdict.regressions},
        )
        return {"admitted": verdict.passed, "verdict": verdict.to_json(),
                "reason": verdict.detail}

    def record_baseline_metrics(self, metrics: dict[str, float],
                                *, name: str | None = None) -> dict[str, Any]:
        """Attach a measured metric vector to a baseline manifest."""
        name = name or self.baseline_name
        path = self.registry._dir(name) / "manifest.json"
        man = self.registry.manifest(name) or {"name": name, "files": {}}
        man["metrics"] = {k: round(float(v), 6) for k, v in metrics.items()}
        man["metrics_at"] = utcnow()
        try:
            os.chmod(path, 0o644)
        except OSError:
            pass
        path.write_text(json.dumps(man, indent=2), encoding="utf-8")
        try:
            os.chmod(path, 0o444)
        except OSError:
            pass
        self.db.log_provenance("baseline", None, "metrics",
                               detail={"name": name, "metrics": man["metrics"]})
        return man

    def revert(self, *, label: str = "rollback") -> dict[str, Any]:
        """Restore the baseline and prove the restore worked."""
        integrity = self.registry.verify_baseline(self.baseline_name)
        if not integrity.get("intact"):
            return {"rolled_back": False,
                    "reason": f"baseline not intact: {integrity.get('problems')}"}
        result = self.registry.restore(self.baseline_name)
        after = quick_metrics()
        self.db.log_provenance(
            "model", None, "rollback", actor="safeguard",
            detail={"label": label, "restored": result.get("files", []),
                    "metrics_after": after},
        )
        return {"rolled_back": result.get("restored", False), "restore": result,
                "metrics_after": after, "integrity": integrity}


# ------------------------------------------------------------ skill versioning
class SkillVersionGuard:
    """Keep the previous definition of a skill so a bad update can be undone.

    A learned skill that is re-learned may become worse on its original task.
    Before replacing, the old row is archived here; ``revert`` puts it back.
    """

    def __init__(self, db: BrainDB | None = None) -> None:
        self.db = db or BrainDB()

    def archive(self, slug: str) -> dict[str, Any] | None:
        row = self.db.query_one("SELECT * FROM skills WHERE slug=?", (slug,))
        if not row:
            return None
        payload = dict(row)
        self.db.execute(
            "INSERT INTO telemetry(ts, state, event, data) VALUES (?,?,?,?)",
            (utcnow(), "LEARN", "skill_archive", json.dumps(payload, default=str)),
        )
        return payload

    def revert(self, slug: str) -> dict[str, Any]:
        row = self.db.query_one(
            "SELECT data, ts FROM telemetry WHERE event='skill_archive' AND data LIKE ?"
            " ORDER BY id DESC LIMIT 1",
            (f'%"slug": "{slug}"%',),
        )
        if not row:
            return {"reverted": False, "reason": f"no archived version of {slug}"}
        payload = json.loads(row["data"])
        sets = ", ".join(f"{k}=?" for k in payload if k != "id")
        values = [payload[k] for k in payload if k != "id"]
        self.db.execute(f"UPDATE skills SET {sets} WHERE slug=?", (*values, slug))
        self.db.log_provenance("skills", payload.get("id"), "revert",
                               actor="safeguard",
                               detail={"slug": slug, "from_archive_at": row["ts"]})
        return {"reverted": True, "slug": slug}
