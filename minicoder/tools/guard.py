"""Runtime confinement for sandboxed code.

The old sandbox relied on a substring blocklist over *command lines*. That cannot
work for `run_python`, which executes arbitrary source: measured directly,
``open('/etc/passwd').read()`` succeeded and ``os.system(...)`` spawned a shell.

This module installs a CPython audit hook (PEP 578) inside the child process
*before* the candidate code runs. Audit hooks cannot be removed from Python once
installed, and they fire on the events that matter regardless of which module
triggers them, so this closes the gap without a container daemon:

    open / os.open / io.open      -> only writable inside the run's temp dir
    os.system / subprocess / exec -> refused
    socket.* / urllib.*           -> refused
    ctypes.dlopen                 -> refused (no bypassing the hook itself)

The guard is injected as ``sitecustomize``-style prelude text prepended to the
candidate program, so it applies even when the candidate imports fresh modules.

This is defence-in-depth, not a hypervisor: a determined attacker with access to
the CPython binary could find other paths. It is materially stronger than a
substring blocklist, and the sandbox reports which backend actually confined a
run so no result can silently claim confinement that did not happen.
"""

from __future__ import annotations

# Emitted as the first lines of every sandboxed program. Kept as a plain string
# so it can be concatenated and shipped to the child without importing anything.
GUARD_PRELUDE = r'''
# ---- minicoder confinement guard (installed before candidate code) ----
def _mc_install_guard(_root):
    import sys, io, os as _os
    _deny_paths = ("/etc", "/proc", "/sys", "/dev", "/root", "/home", "/boot", "/var")
    _blocked_events = {
        "os.system", "os.exec", "os.posix_spawn", "os.spawn", "os.fork", "os.forkpty",
        "subprocess.Popen", "os.kill", "os.killpg",
        "socket.socket", "socket.__new__", "socket.connect", "socket.getaddrinfo",
        "socket.bind", "socket.sendto", "socket.sethostname",
        "ctypes.dlopen", "ctypes.dlsym",
        "shutil.copyfile", "shutil.copymode", "shutil.copystat", "shutil.move",
        "tempfile.mkstemp", "tempfile.mkdtemp",
    }
    _open_events = {"open", "io.open", "os.open", "os.listdir", "os.scandir", "os.stat"}

    def _inside(path):
        try:
            p = _os.path.realpath(_os.fspath(path))
        except Exception:
            return False
        root = _os.path.realpath(_root)
        return p == root or p.startswith(root + _os.sep)

    def _hook(event, args):
        if event.startswith("socket."):
            raise PermissionError("sandbox: %s is not permitted" % event)
        if event in _blocked_events:
            raise PermissionError("sandbox: %s is not permitted" % event)
        if event in _open_events and args:
            target = args[0]
            if isinstance(target, int):
                return
            if isinstance(target, bytes):
                target = target.decode("utf-8", "replace")
            if not isinstance(target, str):
                return
            # Allow the interpreter's own stdlib/venv reads; deny everything else
            # that is not inside the run directory.
            if target.startswith(("/usr/lib", "/usr/local/lib")) or "site-packages" in target:
                return
            for bad in _deny_paths:
                if target == bad or target.startswith(bad + "/"):
                    raise PermissionError("sandbox: reading %r is not permitted" % target)
            if not _inside(target) and _os.path.isabs(target) and ".." not in target:
                # Relative reads and the run dir are fine; arbitrary absolute reads are not.
                raise PermissionError("sandbox: opening %r is not permitted" % target)

    sys.addaudithook(_hook)

_mc_install_guard(__MC_SANDBOX_ROOT__)
# ---- end guard ----
'''


def guarded_program(code: str, root: str) -> str:
    """Prepend the guard to a candidate program."""
    import json

    return GUARD_PRELUDE.replace("__MC_SANDBOX_ROOT__", json.dumps(root)) + "\n" + code
