"""Sandboxed code execution (prime directive #5).

Isolation strategy, in order of preference:
1. Docker container with no network, read-only base, memory/pids/CPU caps
   (used automatically when the Docker daemon is reachable).
2. ``resource``-limited subprocess in a throwaway directory with a scrubbed
   environment, wall-clock timeout, RLIMIT_AS/CPU/NOFILE/FSIZE and output caps.

Every run is recorded with its command, exit code, duration, resource snapshot
and a content hash of the code, so results can be proven rather than asserted.
"""

from __future__ import annotations

import hashlib
import os
import resource
import shutil
import subprocess
import tempfile
import textwrap
import time
from dataclasses import asdict, dataclass, field
from pathlib import Path
from typing import Any

from minicoder.config import CONFIG

DESTRUCTIVE_PATTERNS = (
    "rm -rf /",
    "rm -rf /*",
    "mkfs",
    ":(){ :|:& };:",
    "dd if=/dev/zero of=/dev/",
    "> /dev/sda",
    "chmod -R 777 /",
    "shutdown",
    "reboot",
    "sudo ",
    "curl ",
    "wget ",
    "nc -e",
    "/etc/passwd",
    "/etc/shadow",
)


@dataclass
class RunResult:
    ok: bool
    exit_code: int
    stdout: str
    stderr: str
    duration_ms: float
    backend: str
    timed_out: bool = False
    code_sha256: str = ""
    command: list[str] = field(default_factory=list)
    truncated: bool = False

    def to_json(self) -> dict[str, Any]:
        return asdict(self)

    @property
    def output(self) -> str:
        return (self.stdout + ("\n" + self.stderr if self.stderr else "")).strip()


def _scrub_env() -> dict[str, str]:
    keep = {"PATH", "LANG", "LC_ALL", "HOME", "TMPDIR", "PYTHONHASHSEED"}
    env = {k: v for k, v in os.environ.items() if k in keep}
    env["PYTHONDONTWRITEBYTECODE"] = "1"
    env["HOME"] = "/tmp"
    return env


def _limits(mem_mb: int) -> Any:
    def apply() -> None:  # pragma: no cover - runs in child
        os.setsid()
        resource.setrlimit(resource.RLIMIT_AS, (mem_mb * 1024 * 1024, mem_mb * 1024 * 1024))
        resource.setrlimit(resource.RLIMIT_CPU, (int(CONFIG.sandbox.timeout_seconds) + 1,) * 2)
        resource.setrlimit(resource.RLIMIT_NOFILE, (128, 128))
        resource.setrlimit(resource.RLIMIT_FSIZE, (CONFIG.sandbox.max_file_bytes, CONFIG.sandbox.max_file_bytes))
        resource.setrlimit(resource.RLIMIT_NPROC, (64, 64))

    return apply


def docker_available() -> bool:
    if shutil.which("docker") is None:
        return False
    try:
        r = subprocess.run(["docker", "info"], capture_output=True, timeout=5)
        return r.returncode == 0
    except Exception:
        return False


class Sandbox:
    def __init__(self, use_docker: bool | None = None) -> None:
        self.cfg = CONFIG.sandbox
        self.use_docker = docker_available() if use_docker is None else use_docker
        self.backend = "docker" if self.use_docker else "subprocess-rlimit"

    # ----------------------------------------------------------- guards
    def check_command(self, command: list[str]) -> tuple[bool, str]:
        joined = " ".join(command)
        for pat in DESTRUCTIVE_PATTERNS:
            if pat in joined:
                return False, f"blocked by permission gate: pattern '{pat}'"
        if not self.cfg.allow_network and any(t in joined for t in ("curl ", "wget ", "pip install", "npm install")):
            return False, "network access is disabled for sandboxed runs"
        return True, "ok"

    # ------------------------------------------------------- execution
    def run_python(self, code: str, timeout: float | None = None) -> RunResult:
        code_hash = hashlib.sha256(code.encode()).hexdigest()
        tmp = Path(tempfile.mkdtemp(prefix="minicoder_sbx_"))
        script = tmp / "main.py"
        script.write_text(code, encoding="utf-8")
        try:
            if self.use_docker:
                return self._run_docker(tmp, timeout, code_hash)
            return self._run_subprocess([os.environ.get("PYTHON", "python3"), str(script)], tmp, timeout, code_hash)
        finally:
            shutil.rmtree(tmp, ignore_errors=True)

    def run_command(self, command: list[str], cwd: Path | None = None) -> RunResult:
        ok, reason = self.check_command(command)
        if not ok:
            return RunResult(False, 126, "", reason, 0.0, self.backend)
        return self._run_subprocess(command, cwd or Path(tempfile.mkdtemp(prefix="minicoder_sbx_")), None, "")

    def _run_subprocess(self, cmd: list[str], cwd: Path, timeout: float | None, code_hash: str) -> RunResult:
        t0 = time.time()
        env = _scrub_env()
        env["PYTHONPATH"] = ""
        try:
            proc = subprocess.Popen(
                cmd,
                cwd=str(cwd),
                stdout=subprocess.PIPE,
                stderr=subprocess.PIPE,
                stdin=subprocess.DEVNULL,
                env=env,
                preexec_fn=_limits(self.cfg.memory_limit_mb),
                text=True,
            )
            out, err = proc.communicate(timeout=timeout or self.cfg.timeout_seconds)
            code = proc.returncode
            timed_out = False
        except subprocess.TimeoutExpired:
            proc.kill()
            out, err = proc.communicate()
            code, timed_out = -9, True
            err = (err or "") + f"\n[eval] timed out after {timeout or self.cfg.timeout_seconds}s"
        duration = (time.time() - t0) * 1000
        truncated = False
        if len(out) > self.cfg.max_output_bytes:
            out, truncated = out[: self.cfg.max_output_bytes], True
        if len(err) > self.cfg.max_output_bytes:
            err, truncated = err[: self.cfg.max_output_bytes], True
        return RunResult(
            ok=(code == 0 and not timed_out),
            exit_code=code,
            stdout=out or "",
            stderr=err or "",
            duration_ms=round(duration, 1),
            backend=self.backend,
            timed_out=timed_out,
            code_sha256=code_hash,
            command=cmd,
            truncated=truncated,
        )

    def _run_docker(self, workdir: Path, timeout: float | None, code_hash: str) -> RunResult:
        t0 = time.time()
        cmd = [
            "docker", "run", "--rm", "--network=none",
            "--memory", f"{self.cfg.memory_limit_mb}m",
            "--pids-limit", "64", "--cpus", "1",
            "--read-only", "--tmpfs", "/tmp:size=64m",
            "-v", f"{workdir}:/work:ro", "-w", "/tmp",
            "python:3.11-slim", "python", "/work/main.py",
        ]
        try:
            proc = subprocess.run(cmd, capture_output=True, text=True, timeout=timeout or self.cfg.timeout_seconds)
            return RunResult(
                ok=proc.returncode == 0,
                exit_code=proc.returncode,
                stdout=proc.stdout[: self.cfg.max_output_bytes],
                stderr=proc.stderr[: self.cfg.max_output_bytes],
                duration_ms=round((time.time() - t0) * 1000, 1),
                backend="docker",
                code_sha256=code_hash,
                command=cmd,
            )
        except subprocess.TimeoutExpired:
            return RunResult(False, -9, "", "docker run timed out", (time.time() - t0) * 1000, "docker", True, code_hash)

    # ------------------------------------------------- verification ------------------
    def run_tests(self, solution: str, tests: str, timeout: float = 10.0) -> tuple[bool, RunResult]:
        """Deterministic verification gate: solution + assertions in one program."""
        program = textwrap.dedent(solution).strip() + "\n\n" + textwrap.dedent(tests).strip() + "\n"
        res = self.run_python(program, timeout=timeout)
        return res.ok, res


_SANDBOX: Sandbox | None = None


def sandbox() -> Sandbox:
    global _SANDBOX
    if _SANDBOX is None:
        _SANDBOX = Sandbox()
    return _SANDBOX
