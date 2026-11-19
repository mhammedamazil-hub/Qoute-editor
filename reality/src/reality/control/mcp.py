"""Optional MCP adapter: the Model Context Protocol over stdio (see MCP_REFERENCE.md).

Implements the subset of JSON-RPC 2.0 that MCP clients use for tools: ``initialize``, ``ping``, ``tools/list`` and
``tools/call``. It uses only the standard library, so the core package never depends on it. Every tool is one
registry operation; tool names replace dots with underscores (``scene.add_sphere`` -> ``scene_add_sphere``).

Run with ``python -m reality.control mcp``. Messages are newline-delimited JSON on stdin and stdout; logs go to stderr.
"""

from __future__ import annotations

import json
import sys
from typing import Any, Dict, Optional

from . import operations as ops
from .. import __version__
from .errors import OperationError

PROTOCOL_VERSION = "2024-11-05"
JSONRPC_PARSE_ERROR = -32700
JSONRPC_INVALID_REQUEST = -32600
JSONRPC_METHOD_NOT_FOUND = -32601
JSONRPC_INVALID_PARAMS = -32602


def tool_name(op_name: str) -> str:
    return op_name.replace(".", "_")


def _tools() -> Dict[str, str]:
    return {tool_name(o["name"]): o["name"] for o in ops.list_operations()}


def _tool_list():
    return [{"name": tool_name(o["name"]), "description": o["description"], "inputSchema": o["input_schema"]}
            for o in ops.list_operations()]


def _text(payload: Any, is_error: bool = False) -> Dict[str, Any]:
    return {"content": [{"type": "text", "text": json.dumps(payload, sort_keys=True, allow_nan=False)}],
            "isError": is_error}


def handle(message: Dict[str, Any]) -> Optional[Dict[str, Any]]:
    """Handle one decoded JSON-RPC message. Returns the response, or None for notifications."""
    msg_id = message.get("id")
    method = message.get("method")
    if method is None:
        return _error(msg_id, JSONRPC_INVALID_REQUEST, "missing method") if msg_id is not None else None
    is_notification = "id" not in message
    try:
        if method == "initialize":
            result = {"protocolVersion": PROTOCOL_VERSION,
                      "capabilities": {"tools": {"listChanged": False}},
                      "serverInfo": {"name": "reality", "version": __version__},
                      "instructions": "PROJECT REALITY headless simulation. Start with scene_create, then "
                                      "scene_add_sphere and scene_add_plane. Read MCP_REFERENCE.md for the workflow."}
        elif method == "notifications/initialized" or method.startswith("notifications/"):
            return None
        elif method == "ping":
            result = {}
        elif method == "tools/list":
            result = {"tools": _tool_list()}
        elif method == "tools/call":
            params = message.get("params") or {}
            name = params.get("name")
            arguments = params.get("arguments") or {}
            if not isinstance(name, str) or not isinstance(arguments, dict):
                return _error(msg_id, JSONRPC_INVALID_PARAMS, "tools/call needs a string name and object arguments")
            op_name = _tools().get(name)
            if op_name is None:
                return _error(msg_id, JSONRPC_INVALID_PARAMS, f"unknown tool {name!r}")
            result = _call_tool(op_name, arguments)
        else:
            if is_notification:
                return None
            return _error(msg_id, JSONRPC_METHOD_NOT_FOUND, f"method {method!r} is not supported")
    except OperationError as exc:  # pragma: no cover - tools/call catches its own errors
        result = _text(exc.to_dict(), is_error=True)
    if is_notification:
        return None
    return {"jsonrpc": "2.0", "id": msg_id, "result": result}


def _call_tool(op_name: str, arguments: Dict[str, Any]) -> Dict[str, Any]:
    try:
        out = ops.call(op_name, arguments)
    except OperationError as exc:
        return _text(exc.to_dict(), is_error=True)
    blocks = []
    image = None
    if isinstance(out, dict) and "png_base64" in out:
        image = out.pop("png_base64")
        out.pop("mime_type", None)
    blocks.append({"type": "text", "text": json.dumps(out, sort_keys=True, allow_nan=False)})
    if image is not None:
        blocks.append({"type": "image", "data": image, "mimeType": "image/png"})
    return {"content": blocks, "isError": False}


def _error(msg_id: Any, code: int, message: str) -> Dict[str, Any]:
    return {"jsonrpc": "2.0", "id": msg_id, "error": {"code": code, "message": message}}


def serve(stdin=None, stdout=None) -> int:
    """Read messages until EOF. Returns 0 on clean shutdown."""
    stdin = stdin or sys.stdin
    stdout = stdout or sys.stdout
    for line in stdin:
        line = line.strip()
        if not line:
            continue
        try:
            message = json.loads(line)
        except json.JSONDecodeError as exc:
            response = _error(None, JSONRPC_PARSE_ERROR, f"parse error: {exc}")
        else:
            if not isinstance(message, dict):
                response = _error(None, JSONRPC_INVALID_REQUEST, "batch and non-object messages are not supported")
            else:
                response = handle(message)
        if response is not None:
            stdout.write(json.dumps(response, sort_keys=True, allow_nan=False) + "\n")
            stdout.flush()
    return 0


__all__ = ["handle", "serve", "tool_name", "PROTOCOL_VERSION"]
