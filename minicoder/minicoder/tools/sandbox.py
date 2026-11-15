"""Restricted subprocess sandbox.

Design: allow-listed interpreters/commands only, per-call timeout, output
caps, isolated cwd under memory/working/sandbox-<id>, no shell expansion
(never shell=True), environment scrubbed of secrets. Hard guarantee is
*containment of accidents*, not a security boundary against hostile code —
for that, use Docker (documented) or a VM.
"""
from __future__ import annotations
import os
import re
import subprocess
import sys
from dataclasses import dataclass
from pathlib import Path
from ..config import get_settings
from ..util import new_id, now_iso

_ALLOWED_PREFIXES = (
    ("python3",), ("python",), (sys.executable,),
    ("pytest",), ("node",), ("npm", "test"),
    ("ruff",), ("git",), ("ls",), ("cat",),
)
_FORBIDDEN = re.compile(
    r"(rm\s+-rf\s+/|mkfs|:\(\)\s*\{|dd\s+if=|>\s*/dev/|shutdown|reboot|curl\s+[^\n]*\|\s*sh|wget\s+[^\n]*\|\s*sh)")
MAX_OUTPUT = 64 * 1024


@dataclass
class SandboxResult:
    command: list[str]
    exit_code: int
    stdout: str
    stderr: str
    timed_out: bool
    duration_seconds: float
    cwd: str
    created_at: str = now_iso()


def _allowed(cmd: list[str]) -> bool:
    if not cmd:
        return False
    joined = " ".join(cmd)
    if _FORBIDDEN.search(joined):
        return False
    exe = cmd[0]
    for prefix in _ALLOWED_PREFIXES:
        if exe == prefix[0] and list(cmd[:len(prefix)]) == list(prefix):
            return True
    return False


def run_sandboxed(cmd: list[str] | str, *, timeout: float = 30.0,
                  files: dict[str, str] | None = None,
                  allow_unlisted: bool = False) -> SandboxResult:
    import time
    argv = cmd.split() if isinstance(cmd, str) else list(cmd)
    if not allow_unlisted and not _allowed(argv):
        return SandboxResult(argv, 126, "", f"command not in sandbox allowlist: {argv[:1]!r}", False, 0.0, "")
    settings = get_settings()
    work = settings.working_dir / f"sandbox-{new_id('run')}"
    work.mkdir(parents=True, exist_ok=True)
    for name, content in (files or {}).items():
        target = (work / name).resolve()
        if not str(target).startswith(str(work.resolve())):
            return SandboxResult(argv, 126, "", "file escapes sandbox root — rejected", False, 0.0, str(work))
        target.parent.mkdir(parents=True, exist_ok=True)
        target.write_text(content, encoding="utf-8")
    env = {"PATH": os.environ.get("PATH", "/usr/bin"), "LANG": "C.UTF-8",
           "PYTHONDONTWRITEBYTECODE": "1", "HOME": str(work)}
    t0 = time.time()
    timed_out = False
    try:
        proc = subprocess.run(argv, cwd=str(work), env=env, timeout=timeout,
                              stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True)
        code, out, err = proc.returncode, proc.stdout, proc.stderr
    except subprocess.TimeoutExpired as e:
        timed_out = True
        code, out, err = 124, (e.stdout or "") if isinstance(e.stdout, str) else "", "TIMEOUT expired"
    duration = time.time() - t0
    return SandboxResult(argv, code, out[:MAX_OUTPUT], err[:MAX_OUTPUT], timed_out,
                         round(duration, 3), str(work))
