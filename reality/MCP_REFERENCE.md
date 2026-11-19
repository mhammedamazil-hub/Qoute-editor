# MCP reference - stdio adapter

The MCP adapter is optional. It is part of `reality.control` but uses only the standard library, so the simulation
core and the other interfaces do not depend on it. Run it with:

```bash
PYTHONPATH=src python -m reality.control mcp
```

Messages are newline-delimited JSON-RPC 2.0 on stdin and stdout. Logs go to stderr (the adapter writes none).

## Supported methods

| method | behaviour |
|---|---|
| `initialize` | returns protocol version `2024-11-05`, the `tools` capability, server name `reality` and the package version |
| `notifications/*` | accepted, no response |
| `ping` | `{}` |
| `tools/list` | one tool per registry operation |
| `tools/call` | runs the operation; `params.name` is the tool name, `params.arguments` the operation arguments |

Anything else gets a JSON-RPC `-32601` error. Malformed JSON gets `-32700`. A wrong tool name or malformed
`tools/call` params gets `-32602`. Batch requests are refused.

## Tool names

Each tool name is the operation name with dots replaced by underscores: `scene.add_sphere` becomes `scene_add_sphere`.
The `inputSchema` of each tool is the operation's input schema, so MCP clients can validate arguments before calling.

## Results

A tool result has `content` and `isError`. For success, `content` holds one text block with the JSON result. For a
failed operation, `isError` is true and the text is the error document (`{"error": {"code", "message", "details"}}`).
When an operation returns a PNG (`preview.frame` with `include_base64`), an image block follows the text block.

Protocol errors are JSON-RPC errors; operation errors are tool results with `isError: true`. Clients should check both.

## Example session

```
-> {"jsonrpc":"2.0","id":1,"method":"initialize","params":{"protocolVersion":"2024-11-05","capabilities":{},"clientInfo":{"name":"demo","version":"0"}}}
<- {"jsonrpc":"2.0","id":1,"result":{"protocolVersion":"2024-11-05","capabilities":{"tools":{"listChanged":false}},"serverInfo":{"name":"reality","version":"0.1.0"},...}}
-> {"jsonrpc":"2.0","id":2,"method":"tools/call","params":{"name":"scene_create","arguments":{"name":"m"}}}
<- {"jsonrpc":"2.0","id":2,"result":{"content":[{"type":"text","text":"{...scene...}"}],"isError":false}}
```

A scene passed from one tool call to the next is the JSON object returned by the previous call; the server keeps no
state between calls.

## Limits

The same resource limits apply as in the CLI and API (see `RESOURCE_LIMITS.md`). A request that exceeds one returns a
`resource_limit` error. The adapter is single-threaded and handles one message at a time.

## Tests

`tests/test_control.py` covers initialize, tools/list, tools/call success and error, notifications, protocol errors and
a bad JSON line.
