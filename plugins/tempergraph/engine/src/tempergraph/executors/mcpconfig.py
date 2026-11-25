"""The operator's MCP servers and the judge's private proxy configuration (ECC-B3, ECC-B15, SEC-B3, SEC-B12, WSP-B5).

A judge reaches an MCP server only through the engine's filtering proxy (`mcpproxy`), which fronts a local (stdio)
server of the operator's own MCP configuration: the user scope of `.claude.json` (and the local scope the operator
set for the workspace). A repository's own `.mcp.json` grants a judge nothing (SEC-B3). A server that is not there,
one defined by a URL and one that does not start are out of reach for the attempt.

A step's private configuration instead holds the servers it declares, as the operator defines them (ECC-B19).

The private configuration holds the server's own environment values, so it lives in an owner-only folder under the
state root's scratch folder, one per session, is removed on every exit path and is named in no log or error text.
"""

from __future__ import annotations

import contextlib
import json
import os
import shutil
import sys
import tempfile
from collections.abc import Iterable, Iterator, Mapping, Sequence
from pathlib import Path
from typing import Any

import tempergraph
from tempergraph.executors.mcpproxy import server_starts

PROXY_MODULE = "tempergraph.executors.mcpproxy"
CONFIG_NAME = "mcp.json"


def claude_json_path(env: Mapping[str, str] | None = None) -> Path:
    env = os.environ if env is None else env
    folder = env.get("CLAUDE_CONFIG_DIR")
    return (Path(folder) if folder else Path.home()) / ".claude.json"


def _servers_of(block: object) -> dict[str, Any]:
    if not isinstance(block, dict):
        return {}
    return {str(k): v for k, v in block.items() if isinstance(v, dict)}


def operator_servers(workdir: Path | None = None, env: Mapping[str, str] | None = None) -> dict[str, Any]:
    """The servers the operator's own configuration defines: user scope, then the workspace's local scope. An
    unreadable file defines none."""
    try:
        data = json.loads(claude_json_path(env).read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return {}
    if not isinstance(data, dict):
        return {}
    servers: dict[str, Any] = {}
    projects = data.get("projects")
    if workdir is not None and isinstance(projects, dict):
        local = projects.get(str(workdir)) or projects.get(str(Path(workdir).resolve()))
        if isinstance(local, dict):
            servers.update(_servers_of(local.get("mcpServers")))
    servers.update(_servers_of(data.get("mcpServers")))  # user scope wins over the local one
    return servers


def classify(name: str, servers: Mapping[str, Any]) -> str:
    """`proxiable` (a stdio server with a command), `remote` (defined by a URL or a remote type) or `missing`."""
    entry = servers.get(name)
    if not isinstance(entry, dict):
        return "missing"
    kind = entry.get("type")
    if entry.get("url") or kind in ("http", "sse", "ws"):
        return "remote"
    if kind in (None, "stdio") and isinstance(entry.get("command"), str) and entry["command"]:
        return "proxiable"
    return "missing"


def viewed_servers(tool_names: Iterable[str]) -> dict[str, tuple[str, ...]]:
    """`mcp__<server>__<tool>` names grouped by server, in first-seen order."""
    grouped: dict[str, list[str]] = {}
    for name in tool_names:
        parts = name.split("__", 2)
        if len(parts) == 3 and parts[0] == "mcp" and parts[1] and parts[2]:
            grouped.setdefault(parts[1], []).append(parts[2])
    return {s: tuple(dict.fromkeys(t)) for s, t in grouped.items()}


def _proxy_entry(entry: Mapping[str, Any], allowed: Sequence[str]) -> dict[str, Any]:
    args: list[str] = ["-m", PROXY_MODULE]
    for tool in allowed:
        args += ["--allow", tool]
    args += ["--", str(entry["command"]), *[str(a) for a in entry.get("args") or []]]
    env = {str(k): str(v) for k, v in (entry.get("env") or {}).items()} if isinstance(entry.get("env"), dict) else {}
    env.setdefault("PYTHONPATH", str(Path(tempergraph.__file__).resolve().parent.parent))
    return {"command": sys.executable, "args": args, "env": env}


def declared_servers(tools: Iterable[str]) -> dict[str, tuple[str, ...]]:
    """`mcp:<server>/<tool>` capabilities of a step grouped by server, in first-seen order; others are ignored."""
    grouped: dict[str, list[str]] = {}
    for cap in tools:
        if not cap.startswith("mcp:"):
            continue
        server, sep, tool = cap[4:].partition("/")
        if sep and server and tool:
            grouped.setdefault(server, []).append(tool)
    return {s: tuple(dict.fromkeys(t)) for s, t in grouped.items()}


def build_config(viewed: Mapping[str, Sequence[str]], servers: Mapping[str, Any], *,
                 direct: bool = False) -> dict[str, Any]:
    """One proxy entry per viewed server, each offering only that server's viewed tools; with `direct` (a step,
    ECC-B19) each entry is the operator's own definition of the server."""
    if direct:
        return {"mcpServers": {name: dict(servers[name]) for name in viewed}}
    return {"mcpServers": {name: _proxy_entry(servers[name], tools) for name, tools in viewed.items()}}


@contextlib.contextmanager
def private_config(viewed: Mapping[str, Sequence[str]], servers: Mapping[str, Any], base: Path, *,
                   direct: bool = False) -> Iterator[Path]:
    """Write the private strict configuration into a new owner-only folder under `base` and remove it on every exit."""
    base.mkdir(parents=True, exist_ok=True, mode=0o700)
    folder = Path(tempfile.mkdtemp(prefix="mcp-", dir=base))
    try:
        os.chmod(folder, 0o700)
        path = folder / CONFIG_NAME
        fd = os.open(path, os.O_WRONLY | os.O_CREAT | os.O_EXCL, 0o600)
        with os.fdopen(fd, "w", encoding="utf-8") as fh:
            json.dump(build_config(viewed, servers, direct=direct), fh)
        yield path
    finally:
        shutil.rmtree(folder, ignore_errors=True)


def scratch_base(session_dir: Path | None) -> Path | None:
    """The state root's scratch folder above a session folder (WSP-B5), or nothing when there is none."""
    if session_dir is None:
        return None
    for parent in Path(session_dir).parents:
        if (parent / "scratch").is_dir():
            return parent / "scratch"
    return None


def unreachable(tool_names: Iterable[str], workdir: Path, env: Mapping[str, str] | None = None,
                timeout_s: float = 10.0) -> dict[str, str]:
    """The viewed servers with no working proxy, each with its reason: `missing`, `remote` or `start_failed`."""
    servers = operator_servers(workdir, env)
    out: dict[str, str] = {}
    for name in viewed_servers(tool_names):
        kind = classify(name, servers)
        if kind != "proxiable":
            out[name] = kind
        elif not server_starts(servers[name], workdir, timeout_s):
            out[name] = "start_failed"
    return out
