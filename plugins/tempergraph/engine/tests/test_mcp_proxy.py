"""The judge's filtering MCP proxy, its private configuration and the operator's MCP definitions (ECC-B3, ECC-B15;
ECC-AC7, ECC-AC8; SEC-B12, WSP-B5, SEC-AC5)."""

from __future__ import annotations

import json
import os
import stat
import subprocess
import sys
from pathlib import Path
from typing import Any

import pytest

from tempergraph.contracts import EventSink, SessionRequest, ViewSet
from tempergraph.executors import mcpconfig
from tempergraph.executors.binding import BindingTable
from tempergraph.executors.claude import ClaudeExecutor

from .fixtures import streams as S

STANDIN_MCP = Path(__file__).with_name("fixtures") / "standin_mcp.py"
SECRET = "SECRET-TOKEN-5d1e"


class ProxyClient:
    """Talks newline-delimited JSON-RPC to a filtering proxy that fronts the stand-in MCP server."""

    def __init__(self, allow: list[str], calls: Path, tmp_path: Path) -> None:
        env = {**os.environ, "STANDIN_MCP_CALLS": str(calls)}
        argv = [sys.executable, "-m", "tempergraph.executors.mcpproxy"]
        for name in allow:
            argv += ["--allow", name]
        argv += ["--", sys.executable, str(STANDIN_MCP)]
        self.proc = subprocess.Popen(argv, stdin=subprocess.PIPE, stdout=subprocess.PIPE, stderr=subprocess.DEVNULL,
                                     env=env, cwd=tmp_path, text=True)
        self.n = 0

    def ask(self, method: str, params: dict[str, Any] | None = None) -> dict[str, Any]:
        self.n += 1
        assert self.proc.stdin is not None and self.proc.stdout is not None
        self.proc.stdin.write(json.dumps({"jsonrpc": "2.0", "id": self.n, "method": method,
                                          "params": params or {}}) + "\n")
        self.proc.stdin.flush()
        msg: dict[str, Any] = json.loads(self.proc.stdout.readline())
        assert msg["id"] == self.n
        return msg

    def close(self) -> None:
        assert self.proc.stdin is not None
        self.proc.stdin.close()
        self.proc.wait(timeout=10)


@pytest.fixture
def proxy(tmp_path: Path):  # type: ignore[no-untyped-def]
    calls = tmp_path / "calls.jsonl"
    made: list[ProxyClient] = []

    def start(allow: list[str]) -> tuple[ProxyClient, Path]:
        c = ProxyClient(allow, calls, tmp_path)
        made.append(c)
        c.ask("initialize", {"protocolVersion": "2024-11-05", "capabilities": {}, "clientInfo": {"name": "t"}})
        return c, calls

    yield start
    for c in made:
        if c.proc.poll() is None:
            c.proc.kill()


def test_ecc_ac7_proxy_lists_only_the_viewed_tools(proxy) -> None:  # type: ignore[no-untyped-def]
    c, _ = proxy(["get_issue"])
    names = [t["name"] for t in c.ask("tools/list")["result"]["tools"]]
    assert names == ["get_issue"]  # `update_issue` and `get_comments` are not offered
    c.close()


def test_ecc_ac7_proxy_refuses_a_tool_it_was_not_given_without_reaching_the_server(proxy) -> None:  # type: ignore[no-untyped-def]
    c, calls = proxy(["get_issue"])
    refused = c.ask("tools/call", {"name": "update_issue", "arguments": {"id": 1}})
    assert "error" in refused and "result" not in refused
    assert not calls.exists()  # the write tool never reached the server
    ok = c.ask("tools/call", {"name": "get_issue", "arguments": {"id": 1}})
    assert ok["result"]["content"][0]["text"] == "called get_issue"
    recorded = [json.loads(line)["name"] for line in calls.read_text().splitlines()]
    assert recorded == ["get_issue"]
    c.close()


def test_ecc_ac7_proxy_offers_the_tools_capability_only(proxy) -> None:  # type: ignore[no-untyped-def]
    c, calls = proxy(["get_issue"])
    assert "error" in c.ask("resources/list")  # a server's resources and prompts are not part of a view
    assert "error" in c.ask("prompts/list")
    assert not calls.exists()
    c.close()


# -- the private configuration (ECC-B3, SEC-B12, WSP-B5, SEC-AC5) -------------------------------------------


def servers_for(tmp_path: Path, **extra: Any) -> dict[str, Any]:
    entry = {"command": sys.executable, "args": [str(STANDIN_MCP)], "env": {"API_TOKEN": SECRET}}
    return {"tracker": dict(entry), "wiki": dict(entry), **extra}


def test_ecc_ac7_config_lists_one_proxy_per_viewed_server(tmp_path: Path) -> None:
    viewed = mcpconfig.viewed_servers(["Read", "mcp__tracker__get_issue", "mcp__tracker__get_comments",
                                       "mcp__wiki__get_page"])
    assert viewed == {"tracker": ("get_issue", "get_comments"), "wiki": ("get_page",)}
    cfg = mcpconfig.build_config(viewed, servers_for(tmp_path))["mcpServers"]
    assert sorted(cfg) == ["tracker", "wiki"]  # exactly one proxy per viewed server
    for name, allowed in viewed.items():
        args = cfg[name]["args"]
        assert args[:2] == ["-m", "tempergraph.executors.mcpproxy"]
        offered = [args[i + 1] for i, a in enumerate(args) if a == "--allow"]
        assert offered == list(allowed)  # only the viewed tools of that server


def test_ecc_ac7_private_config_is_owner_only_and_removed_on_every_exit(tmp_path: Path) -> None:
    base = tmp_path / "scratch"
    base.mkdir()
    viewed = {"tracker": ("get_issue",)}
    with mcpconfig.private_config(viewed, servers_for(tmp_path), base) as path:
        folder = path.parent
        assert stat.S_IMODE(folder.stat().st_mode) == 0o700 and folder.parent == base
        assert stat.S_IMODE(path.stat().st_mode) == 0o600
        assert SECRET in path.read_text()  # the server's own environment is in the private file only
    assert not folder.exists()  # a normal end
    with pytest.raises(RuntimeError), mcpconfig.private_config(viewed, servers_for(tmp_path), base) as path:
        folder = path.parent
        raise RuntimeError("boom")
    assert not folder.exists()  # an exception
    assert list(base.iterdir()) == []


def _operator(tmp_path: Path, monkeypatch: pytest.MonkeyPatch, servers: dict[str, Any]) -> None:
    home = tmp_path / "userhome"
    home.mkdir(exist_ok=True)
    (home / ".claude.json").write_text(json.dumps({"mcpServers": servers}))
    monkeypatch.setenv("HOME", str(home))
    monkeypatch.delenv("CLAUDE_CONFIG_DIR", raising=False)


def test_ecc_ac7_judge_launch_failure_leaves_no_config_and_leaks_nothing(tmp_path: Path,
                                                                         monkeypatch: pytest.MonkeyPatch) -> None:
    _operator(tmp_path, monkeypatch, servers_for(tmp_path))
    rec = tmp_path / "rec.json"
    S.fake_claude(tmp_path, monkeypatch, {"record": str(rec), "exit": 1, "lines": [S.init()]})
    scratch = tmp_path / "state" / "scratch"
    scratch.mkdir(parents=True)
    sdir = tmp_path / "state" / "runs" / "wf" / "t1" / "sessions" / "j.1.judge"
    ex = ClaudeExecutor(bindings=BindingTable())
    r = SessionRequest(kind="judge", prompt="Judge it.", workdir=tmp_path, alias="large", session_key="j.1.judge",
                       session_dir=sdir)
    res = ex.run_judge(r, ViewSet(tools=("Read", "mcp__tracker__get_issue")), EventSink())
    seen = json.loads(rec.read_text())
    cfg_path = seen["argv"][seen["argv"].index("--mcp-config") + 1]  # the CLI itself is told where it is
    assert not Path(cfg_path).exists()  # removed after a failed launch
    assert list(scratch.iterdir()) == []
    recorded = json.dumps([list(res.argv), res.error_kind, str(res.infra_cause)])
    assert cfg_path not in recorded and SECRET not in recorded and Path(cfg_path).parent.name not in recorded
    assert "--mcp-config" in res.argv  # the flag stays; its value is not kept


# -- the operator's MCP configuration (ECC-B15, SEC-B3) ----------------------------------------------------


def test_ecc_ac7_operator_servers_are_read_from_user_scope(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    _operator(tmp_path, monkeypatch, {
        "tracker": {"command": "tracker-mcp", "args": ["--stdio"]},  # no `type`: a stdio server
        "wiki": {"type": "stdio", "command": "wiki-mcp"},
        "cloud": {"type": "http", "url": "https://mcp.example.test/mcp"},
        "legacy": {"type": "sse", "url": "https://mcp.example.test/sse"},
        "odd": {"url": "https://mcp.example.test/x"},
    })
    servers = mcpconfig.operator_servers(tmp_path)
    assert mcpconfig.classify("tracker", servers) == "proxiable" and servers["tracker"]["command"] == "tracker-mcp"
    assert mcpconfig.classify("wiki", servers) == "proxiable"
    assert mcpconfig.classify("absent", servers) == "missing"
    for remote in ("cloud", "legacy", "odd"):
        assert mcpconfig.classify(remote, servers) == "remote"  # defined by a URL


def test_ecc_ac7_a_repository_mcp_json_is_never_the_operators_configuration(tmp_path: Path,
                                                                              monkeypatch: pytest.MonkeyPatch) -> None:
    _operator(tmp_path, monkeypatch, {})
    (tmp_path / ".mcp.json").write_text(json.dumps({"mcpServers": {"repo": {"command": "evil"}}}))  # SEC-B3
    servers = mcpconfig.operator_servers(tmp_path)
    assert mcpconfig.classify("repo", servers) == "missing"


def test_ecc_ac7_operator_configuration_follows_the_config_folder(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    folder = tmp_path / "cfg"
    folder.mkdir()
    (folder / ".claude.json").write_text(json.dumps({"mcpServers": {"tracker": {"command": "t"}}}))
    monkeypatch.setenv("CLAUDE_CONFIG_DIR", str(folder))
    assert mcpconfig.classify("tracker", mcpconfig.operator_servers(tmp_path)) == "proxiable"


def test_ecc_ac7_unreadable_operator_configuration_defines_nothing(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    home = tmp_path / "userhome"
    home.mkdir()
    (home / ".claude.json").write_text("{not json")
    monkeypatch.setenv("HOME", str(home))
    monkeypatch.delenv("CLAUDE_CONFIG_DIR", raising=False)
    assert mcpconfig.operator_servers(tmp_path) == {}
