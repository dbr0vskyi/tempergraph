"""Tool input summaries for the activity journal (EVT §2.5).

One line, scrubbed by the pattern scrubber (SEC §2.3), clipped to 200 characters, built by an executor's
translator from the tool's input. Summaries live only in the activity journal and the live progress file;
no run-log record, ledger row, stats row, finding, export or filed text carries them.
"""

from __future__ import annotations

from collections.abc import Mapping
from pathlib import Path
from typing import Any
from urllib.parse import urlsplit

from tempergraph.contracts import Capabilities
from tempergraph.security.scrub import clip

LIMIT = 200
OUTSIDE = "<outside workspace>"

# Input keys that carry the path, pattern, URL or command, in the order they are tried, across the four
# designed executors' tool shapes (Claude Code, the Agent SDK and the Messages API tool host share names;
# Antigravity uses its own capitalised keys).
_PATH_KEYS = ("file_path", "path", "notebook_path", "AbsolutePath", "TargetFile", "DirectoryPath", "SearchPath")
_PATTERN_KEYS = ("pattern", "Query", "query", "glob")
_COMMAND_KEYS = ("command", "CommandLine", "cmd")
_CWD_KEYS = ("cwd", "Cwd", "workdir")


def capability_of(caps: Capabilities, tool_name: str) -> str | None:
    """The declared capability a tool name belongs to, or None for an unknown tool."""
    for cap, names in caps.tool_map.items():
        if cap.endswith(":*"):
            continue
        if tool_name in names:
            return cap
    if tool_name.startswith("mcp__") or tool_name.startswith("mcp("):
        return "mcp"
    if tool_name in caps.tool_map.get("skill:*", ()):
        return "skill"
    return None


def _first(data: Mapping[str, Any], keys: tuple[str, ...]) -> str | None:
    for k in keys:
        v = data.get(k)
        if isinstance(v, str) and v:
            return v
    return None


def relative(path: str, workspace: Path | None) -> str:
    """A path relative to the workspace; a path outside it reads `<outside workspace>`."""
    p = Path(path)
    if not p.is_absolute():
        if ".." in p.parts:
            return OUTSIDE
        return str(p)
    if workspace is None:
        return OUTSIDE
    try:
        rel = p.resolve(strict=False).relative_to(workspace.resolve(strict=False))
    except ValueError:
        return OUTSIDE
    return str(rel) or "."


def _mcp_name(tool_name: str) -> str:
    if tool_name.startswith("mcp__"):
        server, _, tool = tool_name[5:].partition("__")
        return f"{server}/{tool}" if tool else server
    if tool_name.startswith("mcp(") and tool_name.endswith(")"):
        return tool_name[4:-1]
    return tool_name


def input_summary(capability: str | None, tool_name: str, data: Mapping[str, Any] | None,
                  workspace: Path | None = None) -> str | None:
    """EVT §2.5's table; None for an unknown capability."""
    data = data if isinstance(data, Mapping) else {}
    text: str | None
    if capability == "shell":
        cmd = _first(data, _COMMAND_KEYS)
        if cmd is None:
            return None
        cwd = _first(data, _CWD_KEYS)
        where = relative(cwd, workspace) if cwd else "."
        text = cmd if where in (".", "") else f"{cmd} (in {where})"
    elif capability in ("read", "edit", "write", "list"):
        path = _first(data, _PATH_KEYS)
        if path is None:
            pattern = _first(data, _PATTERN_KEYS) if capability == "list" else None
            return clip(pattern, LIMIT) if pattern else None
        text = relative(path, workspace)
    elif capability == "search":
        text = _first(data, _PATTERN_KEYS)
    elif capability == "web_fetch":
        url = _first(data, ("url", "Url", "URL"))
        text = (urlsplit(url).hostname or None) if url else None
    elif capability == "web_search":
        text = "query"
    elif capability == "subagent":
        text = _first(data, ("subagent_type", "agent_type", "type")) or "subagent"
    elif capability == "mcp":
        text = _mcp_name(tool_name)
    elif capability == "skill":
        text = _first(data, ("skill", "name")) or "skill"
    else:
        return None
    return clip(text, LIMIT) if text else None
