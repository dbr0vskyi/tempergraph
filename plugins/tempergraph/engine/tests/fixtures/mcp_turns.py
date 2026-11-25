"""Reads the tools and the context size of every turn of a `claude` stream-json session (ECC-B24, ECC-AC19).

A leak of the account's MCP connectors shows after the servers connect, so the first turn can look clean: the
operator measured about 9,000 context tokens at every turn when isolated, and 8,800 then 174,123 when not.
No live dependency: the helper reads a list of decoded events.
"""

from __future__ import annotations

from collections.abc import Iterable, Sequence
from typing import Any

CONTEXT_LIMIT = 30_000
CONNECTOR_PREFIX = "mcp__claude_ai_"


def _context(usage: dict[str, Any]) -> int:
    return sum(int(usage.get(k) or 0) for k in ("input_tokens", "cache_read_input_tokens",
                                                "cache_creation_input_tokens"))


def turn_readings(events: Iterable[dict[str, Any]]) -> list[dict[str, Any]]:
    """One reading for each `assistant` event: its turn number, its context tokens and the tools of `system/init`."""
    tools: list[str] = []
    out: list[dict[str, Any]] = []
    for e in events:
        if e.get("type") == "system" and e.get("subtype") == "init":
            tools = [str(t) for t in e.get("tools") or []]
        elif e.get("type") == "assistant":
            usage = (e.get("message") or {}).get("usage") or {}
            out.append({"turn": len(out) + 1, "context": _context(usage), "tools": list(tools)})
    return out


def enough_turns(events: Iterable[dict[str, Any]]) -> bool:
    return len(turn_readings(events)) >= 2


def leaks(events: Iterable[dict[str, Any]], declared: Sequence[str] = (), limit: int = CONTEXT_LIMIT) -> list[str]:
    """One line for each init tool of an account connector or of an undeclared server, and for each turn over `limit`."""
    events = list(events)
    found: list[str] = []
    seen: set[str] = set()
    for e in events:
        if e.get("type") == "system" and e.get("subtype") == "init":
            for t in (str(x) for x in e.get("tools") or []):
                if t in seen or not t.startswith("mcp__"):
                    continue
                server = t.split("__")[1] if t.count("__") >= 2 else ""
                if t.startswith(CONNECTOR_PREFIX) or server not in declared:
                    seen.add(t)
                    found.append(f"init lists tool {t} of an undeclared server")
    for r in turn_readings(events):
        if r["context"] > limit:
            found.append(f"turn {r['turn']} has a context of {r['context']} tokens, over {limit}")
    return found
