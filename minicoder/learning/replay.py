"""Fresh-process replay: prove a stored procedure reproduces its result.

Run as ``python -m minicoder.learning.replay --stdin`` with a JSON payload on
stdin::

    {"procedure": [{"tool": ..., "args": {...}}, ...], "criteria": [...]}

Prints exactly one line, ``__REPLAY__{"passed": ..., "detail": ...}``, so the
caller can parse a verdict rather than guess from an exit code.

Why a separate process matters: an in-process replay can pass because of a warm
cache, a stale editor store, or the acquisition attempt's leftover layers. A new
interpreter with a new editor subprocess cannot. This is the difference between
"it worked once" and "it is a skill".
"""

from __future__ import annotations

import json
import sys


def main(argv: list[str] | None = None) -> int:
    args = argv if argv is not None else sys.argv[1:]
    payload_text = sys.stdin.read() if "--stdin" in args else "{}"
    try:
        payload = json.loads(payload_text or "{}")
    except json.JSONDecodeError as exc:
        print(f"__REPLAY__{json.dumps({'passed': False, 'detail': f'bad payload: {exc}'})}")
        return 2

    procedure = payload.get("procedure") or []
    criteria = payload.get("criteria") or []
    if not procedure or not criteria:
        print("__REPLAY__" + json.dumps({"passed": False,
                                         "detail": "need a procedure and at least one criterion"}))
        return 2

    from minicoder.learning.criteria import EditorState, evaluate_editor_criteria
    from minicoder.security import internal_context
    from minicoder.tools.editor_bridge import EditorBridge

    bridge = EditorBridge(auth=internal_context("learning.replay"))
    try:
        bridge._ensure()
        bridge.call("new_project", {})
        for step in procedure:
            result, _ = bridge.call(step["tool"], step.get("args") or {})
            if isinstance(result, dict) and result.get("ok") is False:
                print("__REPLAY__" + json.dumps({
                    "passed": False,
                    "detail": f"{step['tool']} failed: {result.get('error') or result.get('summary')}",
                }))
                return 0
        _, raw = bridge.call("get_app_state", {})
        state = EditorState.from_snapshot(raw.get("snapshot") or {})
        results = evaluate_editor_criteria(criteria, state)
        failed = [r for r in results if not r.passed]
        print("__REPLAY__" + json.dumps({
            "passed": not failed,
            "detail": "; ".join(f"{r.criterion}: {r.detail}" for r in failed)[:400]
                      or "all criteria passed",
            "criteria": [r.to_json() for r in results],
        }))
        return 0
    except Exception as exc:
        print("__REPLAY__" + json.dumps({"passed": False, "detail": f"replay error: {exc}"}))
        return 0
    finally:
        try:
            bridge.close()
        except Exception:
            pass


if __name__ == "__main__":
    raise SystemExit(main())
