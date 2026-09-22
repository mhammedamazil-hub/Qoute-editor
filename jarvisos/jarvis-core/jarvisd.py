#!/usr/bin/env python3
"""jarvis-core daemon: local JSON-RPC over a Unix socket.

The shell, voice loop, clap daemon, hotkeys and CLI all talk to Core
through here — one pipeline, one safety layer, one automation engine.

Protocol (newline-delimited JSON over unix socket):
  -> {"cmd":"text","text":"open blender"}      <- {"ok":true,"say":"..."}
  -> {"cmd":"confirm","token":"abc","yes":true}
  -> {"cmd":"clap","pattern":"double"}
  -> {"cmd":"stop"}            # emergency automation stop
  -> {"cmd":"status"}          # core/ai/engine state
  -> {"cmd":"stats"}           # cpu/mem/disk/battery snapshot
"""
from __future__ import annotations

import json
import os
import socket
import sys
import threading

sys.path.insert(0, "/usr/lib/jarvisos")
sys.path.insert(0, os.path.join(os.path.dirname(os.path.abspath(__file__))))

from jarvis import Core  # noqa: E402
from jarvis.system import stats as _stats  # noqa: E402


def socket_path():
    runtime = os.environ.get("XDG_RUNTIME_DIR", "")
    if runtime and os.path.isdir(runtime):
        return os.path.join(runtime, "jarvis.sock")
    base = os.path.join(os.path.expanduser("~"), ".local", "share",
                        "jarvisos")
    os.makedirs(base, exist_ok=True)
    return os.path.join(base, "jarvis.sock")


class Daemon:
    def __init__(self):
        self.core = Core()
        self.core.engine.use_real_backend()
        self.path = socket_path()

    def handle(self, req):
        cmd = str(req.get("cmd", "")).lower()
        if cmd == "text":
            res = self.core.handle_text(req.get("text", ""),
                                        source=req.get("source", "socket"))
            return {"ok": res.ok, "say": res.say,
                    "intent": res.intent.name if res.intent else "",
                    "needs_confirm": res.needs_confirm,
                    "confirm_token": res.confirm_token,
                    "confirm_question": res.confirm_question,
                    "data": res.data}
        if cmd == "confirm":
            res = self.core.confirm(req.get("token", ""),
                                    bool(req.get("yes", False)))
            return {"ok": res.ok, "say": res.say}
        if cmd == "clap":
            res = self.core.handle_clap(req.get("pattern", ""))
            return {"ok": res.ok, "say": res.say,
                    "needs_confirm": res.needs_confirm,
                    "confirm_token": res.confirm_token,
                    "confirm_question": res.confirm_question}
        if cmd == "stop":
            self.core.engine.stop()
            return {"ok": True, "say": "Automation stopped."}
        if cmd == "status":
            return {"ok": True, "say": "online",
                    "ai_configured": self.core.ai.configured,
                    "ai_providers": self.core.ai.configured_providers,
                    "engine_running": self.core.engine.running,
                    "clap_enabled": bool(self.core.config.get(
                        "gestures.clap_enabled", True))}
        if cmd == "stats":
            data = _stats.summary()
            data["cpu_percent"] = _stats.cpu_percent()
            return {"ok": True, "say": "stats", "data": data}
        return {"ok": False, "say": "unknown command '%s'" % cmd}

    def serve_forever(self):
        try:
            os.unlink(self.path)
        except OSError:
            pass
        server = socket.socket(socket.AF_UNIX, socket.SOCK_STREAM)
        server.bind(self.path)
        os.chmod(self.path, 0o600)
        server.listen(16)
        print("jarvis-core listening on %s" % self.path, flush=True)
        while True:
            conn, _ = server.accept()
            thread = threading.Thread(target=self._client, args=(conn,),
                                      daemon=True)
            thread.start()

    def _client(self, conn):
        with conn:
            try:
                buf = b""
                while True:
                    chunk = conn.recv(65536)
                    if not chunk:
                        break
                    buf += chunk
                    while b"\n" in buf:
                        line, buf = buf.split(b"\n", 1)
                        if not line.strip():
                            continue
                        try:
                            req = json.loads(line.decode("utf-8"))
                        except ValueError:
                            resp = {"ok": False,
                                    "say": "invalid JSON request"}
                        else:
                            try:
                                resp = self.handle(req)
                            except Exception as exc:  # never drop client
                                resp = {"ok": False,
                                        "say": "core error: %s" % exc}
                        conn.sendall((json.dumps(resp) + "\n").encode())
            except OSError:
                pass


def main():
    Daemon().serve_forever()


if __name__ == "__main__":
    main()
