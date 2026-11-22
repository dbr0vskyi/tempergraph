"""The judge's filtering MCP proxy (ECC-B3, ADR a-judge-reaches-an-mcp-server-only-through-the-engines-filtering-proxy).

A stdio MCP server that fronts one local MCP server of the operator's own configuration and offers only the viewed
tools of it: `tools/list` shows the allowed names, `tools/call` of any other name is answered with an error and never
forwarded, and every other request (resources, prompts, completion, logging) is refused, so what a judge can reach
is the viewed tools and nothing else. The engine never holds a connection of its own: the operator's server runs as
this process's child, with the environment its own definition gives.

Run as `python -m tempergraph.executors.mcpproxy --allow <tool> [--allow <tool> ...] -- <server command> [args]`.
Messages are newline-delimited JSON-RPC, as the stdio transport defines them.
"""

from __future__ import annotations

import contextlib
import json
import os
import select
import subprocess
import sys
import threading
from collections.abc import Mapping, Sequence
from pathlib import Path
from typing import IO, Any, TextIO

NOT_OFFERED = -32602
NOT_SUPPORTED = -32601
FORWARDED = ("initialize", "ping", "tools/list", "tools/call")


def _error(msg_id: Any, code: int, text: str) -> dict[str, Any]:
    return {"jsonrpc": "2.0", "id": msg_id, "error": {"code": code, "message": text}}


class Proxy:
    def __init__(self, allowed: Sequence[str], command: Sequence[str]) -> None:
        self.allowed = frozenset(allowed)
        self.command = list(command)
        self._out_lock = threading.Lock()
        self._lists: set[Any] = set()  # ids of forwarded `tools/list` requests, whose answers are filtered
        self._inits: set[Any] = set()

    # -- output to the client ---------------------------------------------------------------------

    def _emit(self, out: TextIO, msg: dict[str, Any]) -> None:
        with self._out_lock:
            out.write(json.dumps(msg) + "\n")
            out.flush()

    # -- client to server ---------------------------------------------------------------------------

    def _from_client(self, line: str, child_in: IO[str], out: TextIO) -> None:
        try:
            msg = json.loads(line)
        except ValueError:
            return
        if not isinstance(msg, dict):
            return
        method, msg_id = msg.get("method"), msg.get("id")
        if method is None:  # a reply to a server-initiated request: none is ever forwarded to the server
            return
        if msg_id is None:  # a notification
            if str(method).startswith("notifications/"):
                self._send(child_in, msg)
            return
        if method not in FORWARDED:
            self._emit(out, _error(msg_id, NOT_SUPPORTED, "method not offered by this view"))
            return
        if method == "tools/call":
            name = (msg.get("params") or {}).get("name")
            if name not in self.allowed:
                self._emit(out, _error(msg_id, NOT_OFFERED, "tool not offered by this view"))
                return
        elif method == "tools/list":
            self._lists.add(msg_id)
        elif method == "initialize":
            self._inits.add(msg_id)
        self._send(child_in, msg)

    @staticmethod
    def _send(child_in: IO[str], msg: dict[str, Any]) -> None:
        try:
            child_in.write(json.dumps(msg) + "\n")
            child_in.flush()
        except (BrokenPipeError, ValueError, OSError):
            pass

    # -- server to client ---------------------------------------------------------------------------

    def _from_server(self, line: str, child_in: IO[str], out: TextIO) -> None:
        try:
            msg = json.loads(line)
        except ValueError:
            return
        if not isinstance(msg, dict):
            return
        msg_id = msg.get("id")
        if "method" in msg:
            if msg_id is not None:  # a request of the server (sampling, roots): this view grants none
                self._send(child_in, _error(msg_id, NOT_SUPPORTED, "not offered by this view"))
            else:
                self._emit(out, msg)
            return
        if msg_id in self._lists and isinstance(msg.get("result"), dict):
            self._lists.discard(msg_id)
            tools = msg["result"].get("tools")
            if isinstance(tools, list):
                msg["result"]["tools"] = [t for t in tools if isinstance(t, dict) and t.get("name") in self.allowed]
        elif msg_id in self._inits and isinstance(msg.get("result"), dict):
            self._inits.discard(msg_id)
            caps = msg["result"].get("capabilities")
            if isinstance(caps, dict):  # only tools are offered
                msg["result"]["capabilities"] = {k: v for k, v in caps.items() if k == "tools"}
        self._emit(out, msg)

    # -- the loop -------------------------------------------------------------------------------------

    def run(self, stdin: TextIO, stdout: TextIO) -> int:
        try:
            child = subprocess.Popen(self.command, stdin=subprocess.PIPE, stdout=subprocess.PIPE,
                                     stderr=subprocess.DEVNULL, text=True, bufsize=1)
        except OSError:
            return 1
        assert child.stdin is not None and child.stdout is not None

        def pump() -> None:
            assert child.stdout is not None and child.stdin is not None
            for line in child.stdout:
                self._from_server(line, child.stdin, stdout)

        reader = threading.Thread(target=pump, daemon=True)
        reader.start()
        try:
            for line in stdin:
                if child.poll() is not None:
                    break
                self._from_client(line, child.stdin, stdout)
        finally:
            with contextlib.suppress(OSError):
                child.stdin.close()
            try:
                child.wait(timeout=5)
            except subprocess.TimeoutExpired:
                child.terminate()
                try:
                    child.wait(timeout=5)
                except subprocess.TimeoutExpired:
                    child.kill()
            reader.join(timeout=2)
        return 0


INIT = {"jsonrpc": "2.0", "id": 1, "method": "initialize",
        "params": {"protocolVersion": "2024-11-05", "capabilities": {},
                   "clientInfo": {"name": "tempergraph-check", "version": "0"}}}


def server_starts(entry: Mapping[str, Any], workdir: Path, timeout_s: float = 10.0) -> bool:
    """ECC-B15: True when the operator's server answers `initialize` within `timeout_s` seconds; the process is
    stopped either way. The one place besides the proxy that starts a server of the operator's configuration."""
    raw_env = entry.get("env")
    env = {**os.environ, **{str(k): str(v) for k, v in raw_env.items()}} if isinstance(raw_env, dict) else dict(os.environ)
    try:
        proc = subprocess.Popen([str(entry["command"]), *[str(a) for a in entry.get("args") or []]],
                                stdin=subprocess.PIPE, stdout=subprocess.PIPE, stderr=subprocess.DEVNULL,
                                cwd=workdir, env=env)
    except (OSError, ValueError):
        return False
    try:
        assert proc.stdin is not None and proc.stdout is not None
        try:
            proc.stdin.write((json.dumps(INIT) + "\n").encode())
            proc.stdin.flush()
        except OSError:
            return False
        ready, _, _ = select.select([proc.stdout], [], [], timeout_s)
        if not ready:
            return False
        try:
            msg = json.loads(proc.stdout.readline())
        except ValueError:
            return False
        return isinstance(msg, dict) and msg.get("id") == 1 and "result" in msg
    finally:
        with contextlib.suppress(OSError):
            proc.kill()
        with contextlib.suppress(Exception):
            proc.wait(timeout=5)


def parse(argv: Sequence[str]) -> tuple[list[str], list[str]]:
    allowed: list[str] = []
    rest = list(argv)
    command: list[str] = []
    if "--" in rest:
        i = rest.index("--")
        command, rest = rest[i + 1:], rest[:i]
    i = 0
    while i < len(rest):
        if rest[i] == "--allow" and i + 1 < len(rest):
            allowed.append(rest[i + 1])
            i += 2
        else:
            i += 1
    return allowed, command


def main(argv: Sequence[str] | None = None) -> int:
    allowed, command = parse(sys.argv[1:] if argv is None else argv)
    if not command:
        return 2
    return Proxy(allowed, command).run(sys.stdin, sys.stdout)


if __name__ == "__main__":
    raise SystemExit(main())
