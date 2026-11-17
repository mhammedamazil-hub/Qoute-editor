"""Phase 3 — execution isolation for candidate code.

Phase 2 executed candidate programs with ``exec()`` inside the harness process, with no
guard, no rlimits and a process-wide ``chdir``. This module replaces that for all research
runs with a child process, and adds an operating-system boundary where the kernel allows it.

Two modes, reported honestly in every result:

``namespace``
    ``unshare -Urnm --fork --pid --kill-child`` gives a new user, mount, PID and network
    namespace. Inside it a tmpfs is mounted over ``/home``, so the repository, the production
    brain, the checkpoints and the private evaluation fixtures are not merely denied but
    *absent* from the filesystem. Verified in this environment (see docs/AUDIT_PHASE3.md).

``guard``
    A plain subprocess with a hardened PEP 578 hook: relative paths are resolved against the
    working directory before being allowed (the Phase 2 bypass), ``chdir`` is refused, and
    writes are confined to the run directory. This is a fallback, not an OS boundary, and
    results from it are labelled as weaker.

Candidate code never receives expected values: it is given *inputs*, it prints *outputs*, and
the comparison happens in the caller's process.
"""

from __future__ import annotations

import json
import os
import shutil
import subprocess
import sys
import tempfile
import time
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

# --------------------------------------------------------------------------- detection
_UNSHARE: str | None = shutil.which("unshare")


def _interpreter() -> str:
    """A Python that still exists once /home is masked.

    The project virtualenv lives under /home, so in namespace mode it is masked away.
    Candidate programs only need the standard library, and /usr/bin/python3 provides it.
    """
    exe = sys.executable
    if not exe.startswith("/home/"):
        return exe
    for candidate in ("/usr/bin/python3", "/usr/local/bin/python3"):
        if os.path.exists(candidate):
            return candidate
    return exe


def _namespace_supported() -> bool:
    """True when an unprivileged user+mount+pid+net namespace can actually be created."""
    if not _UNSHARE:
        return False
    try:
        proc = subprocess.run(
            [_UNSHARE, "-Urnm", "--fork", "--pid", "--kill-child", "sh", "-c", "true"],
            capture_output=True, text=True, timeout=20,
        )
        return proc.returncode == 0
    except (OSError, subprocess.SubprocessError):
        return False


@dataclass(frozen=True)
class Mode:
    name: str
    os_boundary: bool
    note: str


def available_modes() -> list[Mode]:
    modes = []
    if _namespace_supported():
        modes.append(Mode("namespace", True,
                          "user+mount+pid+net namespace; /home masked with tmpfs"))
    modes.append(Mode("guard", False,
                      "subprocess + hardened audit hook; not an OS boundary"))
    return modes


def preferred_mode() -> Mode:
    modes = available_modes()
    return modes[0]


# --------------------------------------------------------------------------- guard prelude
# Runs inside the child. Denies by resolved path, not by string shape, so the Phase 2
# "chdir then relative open" bypass is closed.
GUARD_PRELUDE = r'''
def _mc3_install(_root):
    import os as _os, sys as _sys
    _root = _os.path.realpath(_root)

    def _blocked(what):
        raise PermissionError("isolation: %s is not permitted" % what)

    def _resolve(target):
        if isinstance(target, bytes):
            target = target.decode("utf-8", "replace")
        if isinstance(target, int) or not isinstance(target, str):
            return None
        try:
            return _os.path.realpath(_os.path.join(_os.getcwd(), target))
        except Exception:
            return None

    def _allowed(path):
        if path is None:
            return True
        if path == _root or path.startswith(_root + _os.sep):
            return True
        # The interpreter needs its own libraries.
        return path.startswith(("/usr/lib", "/usr/local/lib", "/lib")) or "site-packages" in path

    _deny_events = {
        "os.system", "os.exec", "os.posix_spawn", "os.spawn", "os.fork", "os.forkpty",
        "subprocess.Popen", "os.kill", "os.killpg",
        "socket.socket", "socket.__new__", "socket.connect", "socket.getaddrinfo",
        "socket.bind", "socket.sendto", "socket.sethostname",
        "ctypes.dlopen", "ctypes.dlsym",
        "os.chdir", "os.chroot", "shutil.move", "shutil.copyfile",
    }
    _read_events = {"open", "io.open", "os.open", "os.listdir", "os.scandir", "os.stat"}

    def _hook(event, args):
        if event in _deny_events or event.startswith("socket."):
            _blocked(event)
        if event in _read_events and args:
            path = _resolve(args[0])
            if not _allowed(path):
                _blocked("access to %s" % path)
        if event in {"os.rename", "os.link", "os.symlink", "os.remove", "os.mkdir", "os.rmdir"} and len(args) >= 2:
            for arg in args[:2]:
                path = _resolve(arg)
                if not _allowed(path):
                    _blocked("modify %s" % path)

    _sys.addaudithook(_hook)

_mc3_install(__MC3_ROOT__)
'''

# The runner sits in the work directory, imports nothing from the project, reads a JSON
# payload, calls solve(*inputs) and prints JSON results.
RUNNER = r'''
import json, os, sys, traceback

payload_path, out_path = sys.argv[1], sys.argv[2]
with open(payload_path, encoding="utf-8") as fh:
    payload = json.load(fh)

namespace = {"__name__": "candidate", "__builtins__": __builtins__}
results = []
error = None
try:
    exec(compile(payload["code"], "<candidate>", "exec"), namespace)
    fn = namespace.get(payload.get("entry", "solve"))
    if not callable(fn):
        raise NameError("entry point %r not defined" % payload.get("entry", "solve"))
    for item in payload["inputs"]:
        args = item if isinstance(item, list) else [item]
        results.append({"ok": True, "value": fn(*args)})
except BaseException as exc:  # noqa: BLE001 - report, never propagate
    error = {"type": type(exc).__name__, "message": str(exc)[:400],
             "trace": traceback.format_exc()[-800:]}

with open(out_path, "w", encoding="utf-8") as fh:
    json.dump({"results": results, "error": error}, fh, default=repr)
'''


# --------------------------------------------------------------------------- result type
@dataclass
class RunOutcome:
    mode: str
    os_boundary: bool
    ok: bool
    values: list[Any] = field(default_factory=list)
    error: str = ""
    timed_out: bool = False
    killed_by: str = ""
    seconds: float = 0.0
    stdout: str = ""
    stderr: str = ""
    raw: dict[str, Any] = field(default_factory=dict)

    def to_json(self) -> dict[str, Any]:
        return {"mode": self.mode, "os_boundary": self.os_boundary, "ok": self.ok,
                "values": self.values, "error": self.error, "timed_out": self.timed_out,
                "killed_by": self.killed_by, "seconds": round(self.seconds, 3)}


# --------------------------------------------------------------------------- execution
def _limits(mem_mb: int, cpu_s: int) -> str:
    return (
        "import resource\n"
        f"resource.setrlimit(resource.RLIMIT_AS, ({mem_mb} << 20, {mem_mb} << 20))\n"
        f"resource.setrlimit(resource.RLIMIT_CPU, ({cpu_s}, {cpu_s}))\n"
        "resource.setrlimit(resource.RLIMIT_NOFILE, (128, 128))\n"
        "resource.setrlimit(resource.RLIMIT_FSIZE, (8 << 20, 8 << 20))\n"
        "resource.setrlimit(resource.RLIMIT_NPROC, (32, 32))\n"
    )


def run_python_isolated(code: str, inputs: list[Any], *, entry: str = "solve",
                        timeout: float = 15.0, mem_mb: int = 256,
                        mode: str | None = None) -> RunOutcome:
    """Execute ``code`` in isolation and call ``entry`` on each input.

    Returns the produced values (or the error). The caller compares them; the child never
    sees expected outputs, which is what keeps the hidden set hidden.
    """
    chosen = mode or preferred_mode().name
    tmp = Path(tempfile.mkdtemp(prefix="nace3_run_", dir="/tmp"))
    try:
        (tmp / "candidate.py").write_text(code, encoding="utf-8")
        (tmp / "runner.py").write_text(RUNNER, encoding="utf-8")
        (tmp / "payload.json").write_text(
            json.dumps({"code": code, "inputs": inputs, "entry": entry}), encoding="utf-8")

        guard = GUARD_PRELUDE.replace("__MC3_ROOT__", repr(str(tmp)))
        (tmp / "guard.py").write_text(guard, encoding="utf-8")
        (tmp / "boot.py").write_text(
            "import sys\n"
            f"sys.path.insert(0, {str(tmp)!r})\n"
            "import guard  # noqa: F401\n"
            + _limits(mem_mb, int(timeout) + 1)
            + "import runpy\n"
            f"sys.argv = [{str(tmp / 'runner.py')!r}, {str(tmp / 'payload.json')!r}, "
            f"{str(tmp / 'out.json')!r}]\n"
            f"runpy.run_path({str(tmp / 'runner.py')!r}, run_name='__main__')\n",
            encoding="utf-8")

        if chosen == "namespace":
            # /home is masked, so the repo, production memory and private fixtures are absent.
            inner = ("mount -t tmpfs tmpfs /home 2>/dev/null; "
                     f"cd {tmp} && exec {_interpreter()} {tmp}/boot.py")
            cmd = [_UNSHARE or "unshare", "-Urnm", "--fork", "--pid", "--kill-child",
                   "sh", "-c", inner]
        else:
            cmd = [_interpreter(), str(tmp / "boot.py")]

        t0 = time.time()
        try:
            proc = subprocess.run(cmd, capture_output=True, text=True, timeout=timeout,
                                  cwd=str(tmp))
        except subprocess.TimeoutExpired as exc:
            return RunOutcome(mode=chosen, os_boundary=(chosen == "namespace"), ok=False,
                              error="timeout", timed_out=True, seconds=time.time() - t0,
                              stdout=(exc.stdout or "")[-500:] if exc.stdout else "",
                              stderr=(exc.stderr or "")[-500:] if exc.stderr else "")
        elapsed = time.time() - t0

        out_file = tmp / "out.json"
        raw: dict[str, Any] = {}
        if out_file.exists():
            try:
                raw = json.loads(out_file.read_text(encoding="utf-8"))
            except json.JSONDecodeError:
                raw = {}
        if "error" in raw and raw["error"]:
            err = raw["error"]
            return RunOutcome(mode=chosen, os_boundary=(chosen == "namespace"), ok=False,
                              error=f"{err['type']}: {err['message']}", seconds=elapsed,
                              stdout=proc.stdout[-500:], stderr=proc.stderr[-800:], raw=raw)
        if not raw.get("results"):
            killed = "no result"
            return RunOutcome(mode=chosen, os_boundary=(chosen == "namespace"), ok=False,
                              error="candidate produced no result", seconds=elapsed,
                              killed_by=killed, stdout=proc.stdout[-500:],
                              stderr=proc.stderr[-800:], raw=raw)
        values = [r.get("value") for r in raw["results"]]
        return RunOutcome(mode=chosen, os_boundary=(chosen == "namespace"), ok=True,
                          values=values, seconds=elapsed, stdout=proc.stdout[-500:],
                          stderr=proc.stderr[-800:], raw=raw)
    finally:
        shutil.rmtree(tmp, ignore_errors=True)


def probe_escapes(mode: str | None = None) -> list[dict[str, Any]]:
    """Run the escape matrix and return one row per attempt.

    Each probe returns ``'ESCAPED'`` only when the forbidden action actually succeeded, and
    ``'BLOCKED'`` when it raised. ``escaped: True`` is a security failure for that mode and
    is reported as one.
    """
    probes: dict[str, str] = {
        "relative_read_etc": (
            "import os\n"
            "os.chdir('/')\n"
            "open('etc/hostname').read()\n"
            "return 'ESCAPED'\n"),
        "relative_read_repo": (
            "import os\n"
            "os.chdir('/home/user/Qoute-editor/minicoder/learning')\n"
            "open('synth.py').read()\n"
            "return 'ESCAPED'\n"),
        "absolute_read_repo": (
            "open('/home/user/Qoute-editor/README.md').read()\n"
            "return 'ESCAPED'\n"),
        "read_production_db": (
            "open('/home/user/Qoute-editor/memory/brain.db','rb').read(16)\n"
            "return 'ESCAPED'\n"),
        "spawn_process": (
            "import os\n"
            "os.system('echo hi')\n"
            "return 'ESCAPED'\n"),
        "socket": (
            "import socket\n"
            "socket.socket()\n"
            "return 'ESCAPED'\n"),
        "write_repo": (
            "open('/home/user/Qoute-editor/INJECTED.txt','w').write('x')\n"
            "return 'ESCAPED'\n"),
        "fork": (
            "import os\n"
            "os.fork()\n"
            "return 'ESCAPED'\n"),
        "kill_harness": (
            "import os, signal\n"
            "os.kill(os.getppid(), signal.SIGTERM)\n"
            "return 'ESCAPED'\n"),
    }
    rows = []
    for name, body in probes.items():
        code = ("def solve():\n"
                "    try:\n"
                + "".join("        " + line + "\n" for line in body.splitlines())
                + "    except BaseException:\n"
                  "        return 'BLOCKED'\n")
        out = run_python_isolated(code, [[]], timeout=8, mode=mode)
        escaped = bool(out.ok and out.values and out.values[0] == "ESCAPED")
        rows.append({"probe": name, "mode": out.mode, "os_boundary": out.os_boundary,
                     "escaped": escaped, "error": out.error[:160],
                     "timed_out": out.timed_out})
    # Resource-limit probes are separate: success means the limit bit.
    slow = run_python_isolated("def solve():\n    while True:\n        pass\n", [[]],
                               timeout=3, mode=mode)
    rows.append({"probe": "infinite_loop", "mode": slow.mode, "os_boundary": slow.os_boundary,
                 "escaped": not slow.timed_out, "error": slow.error[:160],
                 "timed_out": slow.timed_out})
    bomb = run_python_isolated(
        "def solve():\n    x = bytearray(900 * 1024 * 1024)\n    return 'ESCAPED'\n",
        [[]], timeout=10, mem_mb=256, mode=mode)
    rows.append({"probe": "memory_bomb", "mode": bomb.mode, "os_boundary": bomb.os_boundary,
                 "escaped": bool(bomb.ok and bomb.values and bomb.values[0] == "ESCAPED"),
                 "error": bomb.error[:160], "timed_out": bomb.timed_out})
    return rows
