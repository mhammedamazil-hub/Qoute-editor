"""Phase 3 — the private evaluation store.

Lives outside the repository (default ``~/.local/share/nace-private``, mode 0700), so the
agent's own code cannot reach it by relative path and candidate code cannot reach it at all:
in namespace mode ``/home`` is masked, and in guard mode every path outside the run
directory is refused after realpath resolution.

It holds only:
* ``salt.json`` — the secret material hidden draws are derived from;
* ``manifest.json`` — sha256 of the salt and of the evaluator sources, so tampering is
  detectable.

It deliberately does **not** hold expected outputs: those are recomputed at evaluation time
from the reference implementations in :mod:`minicoder.research.tasks`.
"""

from __future__ import annotations

import hashlib
import json
import os
import secrets
from dataclasses import dataclass
from pathlib import Path
from typing import Any

DEFAULT_ROOT = Path.home() / ".local" / "share" / "nace-private"

# Files whose integrity the manifest pins.
_PINNED = ("minicoder/research/tasks.py", "minicoder/research/evaluator.py",
           "minicoder/research/private.py")


def _sha(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


@dataclass
class PrivateStore:
    root: Path

    # ------------------------------------------------------------------ lifecycle
    @classmethod
    def open(cls, root: Path | None = None, *, create: bool = False) -> PrivateStore:
        env = os.environ.get("NACE_PRIVATE_DIR")
        path = Path(root or env or DEFAULT_ROOT).expanduser()
        store = cls(path)
        if create:
            store._create()
        return store

    def _create(self) -> None:
        self.root.mkdir(parents=True, exist_ok=True)
        os.chmod(self.root, 0o700)
        salt_file = self.root / "salt.json"
        if not salt_file.exists():
            payload = {"experiment_salt": secrets.token_hex(32), "version": 1}
            salt_file.write_text(json.dumps(payload, indent=2), encoding="utf-8")
            os.chmod(salt_file, 0o600)
        self._write_manifest()

    # ------------------------------------------------------------------ accessors
    def exists(self) -> bool:
        return (self.root / "salt.json").exists()

    def salt(self) -> str:
        data = json.loads((self.root / "salt.json").read_text(encoding="utf-8"))
        return str(data["experiment_salt"])

    def _write_manifest(self) -> None:
        repo = Path(__file__).resolve().parents[2]
        pins = {}
        for rel in _PINNED:
            path = repo / rel
            if path.exists():
                pins[rel] = _sha(path)
        manifest = {
            "salt_sha256": _sha(self.root / "salt.json"),
            "sources": pins,
            "root": str(self.root),
        }
        (self.root / "manifest.json").write_text(json.dumps(manifest, indent=2), encoding="utf-8")
        os.chmod(self.root / "manifest.json", 0o600)

    def verify(self) -> dict[str, Any]:
        """Re-hash the salt and the evaluator sources.

        Evaluation refuses to run when this fails: a modified evaluator cannot report a pass.
        """
        problems: list[str] = []
        manifest_file = self.root / "manifest.json"
        if not manifest_file.exists():
            return {"ok": False, "problems": ["manifest missing"]}
        manifest = json.loads(manifest_file.read_text(encoding="utf-8"))
        if manifest.get("salt_sha256") != _sha(self.root / "salt.json"):
            problems.append("salt changed since the manifest was written")
        repo = Path(__file__).resolve().parents[2]
        for rel, digest in manifest.get("sources", {}).items():
            path = repo / rel
            if not path.exists():
                problems.append(f"{rel} removed")
            elif _sha(path) != digest:
                problems.append(f"{rel} modified since the manifest was written")
        return {"ok": not problems, "problems": problems,
                "pinned": sorted(manifest.get("sources", {})), "root": str(self.root)}

    # ------------------------------------------------------------------ isolation check
    def repin(self) -> dict[str, Any]:
        """Re-hash the sources after an intentional change.

        Called explicitly at the start of an experiment run, so the manifest records the
        code that produced the results. A silent edit outside this path still fails verify().
        """
        self._write_manifest()
        return self.verify()

    def reachable_from(self, cwd: Path) -> bool:
        """True when ``cwd`` could address the store by a relative path (should be False)."""
        try:
            self.root.resolve().relative_to(Path(cwd).resolve())
            return True
        except ValueError:
            return False
