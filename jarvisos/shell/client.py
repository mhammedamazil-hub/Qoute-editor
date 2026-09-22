"""Socket client for jarvis-core (shared by shell, apps, hotkeys).

Stdlib only — safe to import anywhere, including tests.
"""
from __future__ import annotations

import json
import os
import socket


def socket_path():
    runtime = os.environ.get("XDG_RUNTIME_DIR", "")
    if runtime and os.path.isdir(runtime):
        return os.path.join(runtime, "jarvis.sock")
    return os.path.join(os.path.expanduser("~"), ".local", "share",
                        "jarvisos", "jarvis.sock")


def call(payload, timeout=120):
    """Send one request, return response dict. Never raises."""
    try:
        sock = socket.socket(socket.AF_UNIX, socket.SOCK_STREAM)
        sock.settimeout(timeout)
        sock.connect(socket_path())
        sock.sendall((json.dumps(payload) + "\n").encode())
        buf = b""
        while b"\n" not in buf:
            chunk = sock.recv(65536)
            if not chunk:
                break
            buf += chunk
        sock.close()
        return json.loads(buf.decode("utf-8", "replace"))
    except (OSError, ValueError):
        return {"ok": False, "say": "JARVIS Core is not running.",
                "offline": True}


def text_command(text, source="gui"):
    return call({"cmd": "text", "text": text, "source": source})


def confirm(token, yes):
    return call({"cmd": "confirm", "token": token, "yes": bool(yes)})


def stop():
    return call({"cmd": "stop"})


def status():
    return call({"cmd": "status"})


def stats():
    return call({"cmd": "stats"})
