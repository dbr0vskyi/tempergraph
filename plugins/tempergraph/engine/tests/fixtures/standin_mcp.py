"""A stand-in MCP server over stdio (newline-delimited JSON-RPC), for the judge's filtering proxy (ECC-AC7, ECC-AC8).

It offers two read tools and one write tool under the names the view catalog holds: `get_issue` and
`get_comments` read, `update_issue` writes. `--exit-at-start` makes it exit at once, as a server that cannot start
does. Every `tools/call` it receives is appended, as one JSON line, to the file named by `STANDIN_MCP_CALLS`, so a
test sees whether a call reached it. Run it as a script: `python standin_mcp.py [--exit-at-start]`.
"""

from __future__ import annotations

import json
import os
import sys

TOOLS = [
    {"name": "get_issue", "description": "Read one issue", "inputSchema": {"type": "object", "properties": {}}},
    {"name": "update_issue", "description": "Change one issue", "inputSchema": {"type": "object", "properties": {}}},
    {"name": "get_comments", "description": "Read the comments", "inputSchema": {"type": "object", "properties": {}}},
]


def reply(msg_id: object, result: object) -> None:
    sys.stdout.write(json.dumps({"jsonrpc": "2.0", "id": msg_id, "result": result}) + "\n")
    sys.stdout.flush()


def main() -> int:
    if "--exit-at-start" in sys.argv[1:]:
        return 3
    calls = os.environ.get("STANDIN_MCP_CALLS")
    for line in sys.stdin:
        try:
            msg = json.loads(line)
        except ValueError:
            continue
        method, msg_id = msg.get("method"), msg.get("id")
        if method == "initialize":
            reply(msg_id, {"protocolVersion": (msg.get("params") or {}).get("protocolVersion", "2024-11-05"),
                           "capabilities": {"tools": {}, "resources": {}, "prompts": {}},
                           "serverInfo": {"name": "standin", "version": "0"}})
        elif method == "tools/list":
            reply(msg_id, {"tools": TOOLS})
        elif method == "tools/call":
            params = msg.get("params") or {}
            if calls:
                with open(calls, "a", encoding="utf-8") as fh:
                    fh.write(json.dumps({"name": params.get("name"), "arguments": params.get("arguments")}) + "\n")
            reply(msg_id, {"content": [{"type": "text", "text": f"called {params.get('name')}"}]})
        elif method == "resources/list":
            reply(msg_id, {"resources": [{"uri": "standin://secret", "name": "secret"}]})
        elif msg_id is not None:
            reply(msg_id, {})
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
