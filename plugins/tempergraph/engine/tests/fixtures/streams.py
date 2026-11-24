"""Claude Code stream-json lines in the shapes R-001 records, and a fake `claude` on PATH."""

from __future__ import annotations

import json
import os
import stat
import sys
from pathlib import Path
from typing import Any

import pytest

STANDIN = Path(__file__).with_name("standin_cli.py")


def init(session_id: str = "s-1", tools: tuple[str, ...] = ("Read", "Grep", "Glob"), **kw: Any) -> dict[str, Any]:
    return {"type": "system", "subtype": "init", "session_id": session_id, "model": "claude-sonnet",
            "tools": list(tools), "claude_code_version": "2.1.329", "mcp_servers": kw.get("mcp_servers", []),
            "plugin_errors": kw.get("plugin_errors", [])}


def tool_use(name: str, call_id: str, parent: str | None = None, inp: dict[str, Any] | None = None
             ) -> dict[str, Any]:
    return {"type": "assistant", "parent_tool_use_id": parent,
            "message": {"content": [{"type": "tool_use", "id": call_id, "name": name, "input": inp or {}}]}}


def tool_result(call_id: str, is_error: bool = False) -> dict[str, Any]:
    return {"type": "user", "message": {"content": [{"type": "tool_result", "tool_use_id": call_id,
                                                      "is_error": is_error, "content": "x"}]}}


def text(t: str) -> dict[str, Any]:
    return {"type": "assistant", "parent_tool_use_id": None, "message": {"content": [{"type": "text", "text": t}]}}


def delta(t: str) -> dict[str, Any]:
    return {"type": "stream_event", "event": {"type": "content_block_delta", "delta": {"type": "text_delta", "text": t}}}


def retry(category: str) -> dict[str, Any]:
    return {"type": "system", "subtype": "api_retry", "attempt": 1, "error": category}


def rate_limit_event(status: str, resets_at: int | None = None, error_code: str | None = None) -> dict[str, Any]:
    """A `rate_limit_event` line in the shape of the recorded one (ECC-B17)."""
    info: dict[str, Any] = {"status": status}
    if resets_at is not None:
        info["resetsAt"] = resets_at
    if error_code is not None:
        info["errorCode"] = error_code
    return {"type": "rate_limit_event", "rate_limit_info": info, "session_id": "s-1"}


def denied(name: str) -> dict[str, Any]:
    return {"type": "system", "subtype": "permission_denied", "tool_name": name}


def result(text_: str = "done\nARTIFACT notes: notes.md", *, subtype: str = "success", is_error: bool = False,
           cost: float | None = 0.12, session_id: str = "s-1", **kw: Any) -> dict[str, Any]:
    r: dict[str, Any] = {"type": "result", "subtype": subtype, "is_error": is_error, "result": text_,
                         "session_id": session_id, "num_turns": 3,
                         "usage": {"input_tokens": 1200, "output_tokens": 300, "cache_read_input_tokens": 800,
                                   "cache_creation_input_tokens": 40},
                         "modelUsage": {"claude-sonnet": {"inputTokens": 1200, "outputTokens": 300,
                                                          "costUSD": cost}}}
    if cost is not None:
        r["total_cost_usd"] = cost
    r.update(kw)
    return r


def lines(*msgs: dict[str, Any]) -> list[bytes]:
    return [json.dumps(m).encode() + b"\n" for m in msgs]


def fake_claude(tmp_path: Path, monkeypatch: pytest.MonkeyPatch, scenario: dict[str, Any]) -> Path:
    """Put a `claude` stand-in first on PATH, driven by ``scenario``; returns the scenario path."""
    bindir = tmp_path / "bin"
    bindir.mkdir(exist_ok=True)
    exe = bindir / "claude"
    exe.write_text(f"#!{sys.executable}\nimport runpy, sys\nsys.argv[0] = {str(STANDIN)!r}\n"
                   f"runpy.run_path({str(STANDIN)!r}, run_name='__main__')\n")
    exe.chmod(exe.stat().st_mode | stat.S_IEXEC)
    path = tmp_path / "scenario.json"
    path.write_text(json.dumps(scenario))
    monkeypatch.setenv("PATH", f"{bindir}{os.pathsep}{os.environ.get('PATH', '')}")
    monkeypatch.setenv("STANDIN_SCENARIO", str(path))
    return path


def set_scenario(path: Path, scenario: dict[str, Any]) -> None:
    path.write_text(json.dumps(scenario))
