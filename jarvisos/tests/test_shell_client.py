"""Socket client against a stub jarvis-core server."""
import json
import os
import socket
import sys
import threading

ROOT = os.path.join(os.path.dirname(os.path.abspath(__file__)), "..")
sys.path.insert(0, os.path.join(ROOT, "shell"))

import client  # noqa: E402


def _stub_server(path, responder):
    try:
        os.unlink(path)
    except OSError:
        pass
    server = socket.socket(socket.AF_UNIX, socket.SOCK_STREAM)
    server.bind(path)
    server.listen(1)
    server.settimeout(10)

    def _run():
        try:
            conn, _ = server.accept()
            with conn:
                data = conn.recv(65536)
                req = json.loads(data.decode())
                conn.sendall((json.dumps(responder(req)) + "\n").encode())
        except OSError:
            pass
        finally:
            server.close()

    threading.Thread(target=_run, daemon=True).start()


def test_text_command_roundtrip(tmp_path, monkeypatch):
    sock = str(tmp_path / "jarvis.sock")
    monkeypatch.setenv("XDG_RUNTIME_DIR", str(tmp_path))
    _stub_server(sock, lambda req: {"ok": True,
                                    "say": "echo:%s" % req.get("text")})
    resp = client.text_command("open blender")
    assert resp["ok"] and resp["say"] == "echo:open blender"


def test_offline_never_raises(tmp_path, monkeypatch):
    monkeypatch.setenv("XDG_RUNTIME_DIR", str(tmp_path))
    resp = client.stats()
    assert resp["offline"] is True and resp["ok"] is False
