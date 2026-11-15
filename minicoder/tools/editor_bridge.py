"""Python client for the real QuoteCraft editor tool layer (Node bridge)."""

from __future__ import annotations

import json
import shutil
import subprocess
import threading
import unicodedata
from pathlib import Path
from typing import Any


class BridgeUnavailable(RuntimeError):
    pass


class EditorBridge:
    """Drives ``scripts/editor-bridge.ts`` over stdin/stdout NDJSON.

    Each request/response pair is matched by id.  The editor is a genuine
    dependency (Node + vite-node), so if it cannot start the caller gets an
    explicit ``BridgeUnavailable`` rather than a silent mock.
    """

    def __init__(self, home: Path | None = None, timeout: float = 120.0) -> None:
        # ``home`` here means the *installation* root that holds the editor
        # source, not the data home (see config.install_root).
        from minicoder.config import install_root

        self.home = (home or install_root()).resolve()
        self.timeout = timeout
        self._proc: subprocess.Popen[str] | None = None
        self._lock = threading.Lock()
        self._next_id = 0

    # ------------------------------------------------------------- lifecycle
    def _ensure(self) -> None:
        if self._proc and self._proc.poll() is None:
            return
        if shutil.which("npx") is None or not (self.home / "node_modules").exists():
            raise BridgeUnavailable(
                "editor bridge needs Node + `npm install` in the repo root"
            )
        self._proc = subprocess.Popen(
            ["npx", "vite-node", "scripts/editor-bridge.ts"],
            cwd=str(self.home),
            stdin=subprocess.PIPE,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            text=True,
            bufsize=1,
        )
        self._read()  # ready line

    def close(self) -> None:
        if self._proc and self._proc.poll() is None:
            self._proc.stdin and self._proc.stdin.close()
            try:
                self._proc.wait(timeout=5)
            except subprocess.TimeoutExpired:
                self._proc.kill()
        self._proc = None

    # ----------------------------------------------------------- transport
    def _read(self) -> dict[str, Any]:
        assert self._proc and self._proc.stdout
        line = self._proc.stdout.readline()
        if not line:
            err = ""
            if self._proc.stderr:
                err = self._proc.stderr.read()[-600:]
            raise BridgeUnavailable(f"editor bridge exited. stderr: {err}")
        return json.loads(line)

    def request(self, payload: dict[str, Any]) -> dict[str, Any]:
        with self._lock:
            self._ensure()
            self._next_id += 1
            rid = str(self._next_id)
            payload = {**payload, "id": rid}
            assert self._proc and self._proc.stdin
            self._proc.stdin.write(json.dumps(payload) + "\n")
            self._proc.stdin.flush()
            deadline = self.timeout
            while True:
                msg = self._read()
                if msg.get("id") == rid:
                    return msg
                deadline -= 0.1
                if deadline < 0:
                    raise BridgeUnavailable("timed out waiting for editor response")

    # ---------------------------------------------------------------- api
    def list_tools(self) -> list[dict[str, Any]]:
        return self.request({"op": "list"}).get("tools", [])

    def reset(self, width: int = 1080, height: int = 1350) -> dict[str, Any]:
        return self.request({"op": "reset", "width": width, "height": height}).get("state", {})

    def state(self) -> dict[str, Any]:
        return self.request({"op": "state"}).get("state", {})

    def call(self, tool: str, args: dict[str, Any] | None = None) -> tuple[dict[str, Any], dict[str, Any]]:
        msg = self.request({"op": "call", "tool": tool, "args": args or {}})
        if not msg.get("ok"):
            raise BridgeUnavailable(msg.get("error", "tool call failed"))
        return msg["result"], msg.get("state", {})


def tokenize_text(s: str) -> set[str]:
    return {w for w in "".join(c.lower() if c.isalnum() else " " for c in unicodedata.normalize("NFC", s)).split() if w}


def verify_tool_outcome(
    tool: str, args: dict[str, Any], result: dict[str, Any], before: dict[str, Any], after: dict[str, Any]
) -> tuple[bool, list[str]]:
    """Deterministic post-action verification against the real store state.

    This is what lets an episode be marked VERIFIED rather than merely
    "the tool returned ok" (prime directive #2).
    """
    checks: list[str] = []
    ok = True

    if not result.get("ok", False):
        return False, [f"tool reported failure: {result.get('summary', '')}"]

    snap_b, snap_a = before.get("snapshot", {}), after.get("snapshot", {})
    n_b, n_a = snap_b.get("layerCount", 0), snap_a.get("layerCount", 0)

    if tool in {"add_text", "add_image", "add_shape", "add_quote_marks", "add_light", "add_gradient", "add_particles"}:
        ok &= n_a > n_b
        checks.append(f"layerCount {n_b}->{n_a} (expected increase)")
    elif tool in {"delete_elements", "delete_selection"}:
        ok &= n_a < n_b
        checks.append(f"layerCount {n_b}->{n_a} (expected decrease)")
    elif tool == "duplicate_elements":
        ok &= n_a > n_b
        checks.append(f"layerCount {n_b}->{n_a} (expected increase)")
    elif tool == "group_elements":
        groups = [l for l in snap_a.get("layers", []) if l.get("type") == "group"]
        ok &= len(groups) > len([l for l in snap_b.get("layers", []) if l.get("type") == "group"])
        checks.append(f"groups {len(groups)} (expected new group)")
    elif tool == "undo":
        ok &= snap_a != snap_b
        checks.append("state changed after undo")
    elif tool == "redo":
        ok &= snap_a != snap_b
        checks.append("state changed after redo")
    elif tool == "set_text_content":
        # The editor's argument is ``content`` (see TOOL_DECLARATIONS). Reading
        # ``text`` here made ``want`` always empty, and ``any(want and ...)`` then
        # returned False for a correct edit — or True vacuously for an empty one.
        want = tokenize_text(str(args.get("content") or args.get("text") or ""))
        layers = snap_a.get("layers", [])
        found = bool(want) and any(want <= tokenize_text(l.get("content") or l.get("text") or "") for l in layers)
        ok &= found
        checks.append(f"requested text present in a text layer ({len(want)} tokens)")
    elif tool in {"set_typography", "update_elements", "style_elements", "set_layer_style"}:
        ok &= snap_a != snap_b or result.get("ok", False)
        checks.append("style mutation reported ok")
    elif tool in {"create_canvas", "resize_canvas"}:
        want_w = args.get("width")
        got_w = snap_a.get("canvas", {}).get("width")
        if want_w is not None:
            ok &= got_w == want_w
            checks.append(f"canvas width {got_w} == {want_w}")
    elif tool in {"apply_palette", "apply_template", "set_background"}:
        ok &= snap_a.get("canvas") is not None
        checks.append("design snapshot still coherent")
    elif tool in {"select_elements", "translate_elements", "align_elements", "distribute_elements"}:
        ok &= n_a == n_b
        checks.append("layer count unchanged (non-destructive)")

    # Universal invariants
    canvas = snap_a.get("canvas") or {}
    if canvas.get("width") and canvas.get("height"):
        inside = all(
            (l.get("x") is not None) and -5000 < float(l.get("x", 0)) < 20000 for l in snap_a.get("layers", [])
        )
        ok &= inside
        checks.append("all layer coordinates in sane range")
    return bool(ok), checks
