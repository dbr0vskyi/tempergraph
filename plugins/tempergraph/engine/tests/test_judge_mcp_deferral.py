"""A judge view of an MCP server with no working proxy is out of reach for the attempt, and `claude` declares
`judge_mcp` (ECC-B15, GRD-B5, ECC-B6; ECC-AC8, ECC-AC9, GRD-AC2)."""

from __future__ import annotations

import dataclasses
import io
import json
import sys
from pathlib import Path
from typing import Any

import pytest

from tempergraph.catalog import Catalog
from tempergraph.cli.main import main
from tempergraph.contracts import ViewSet
from tempergraph.executors import mcpconfig
from tempergraph.executors.claude import ClaudeExecutor
from tempergraph.executors.registry import Registry
from tempergraph.executors.standins import ScriptedExecutor, standin
from tempergraph.run.runner import start
from tempergraph.store.layout import run_dir, state_root_path

from .fixtures.workflows import two_step
from .test_run import DRAFT, NO_SLEEP, REVIEW, judge, verdict_block

STANDIN_MCP = Path(__file__).with_name("fixtures") / "standin_mcp.py"
WORKS = {"command": sys.executable, "args": [str(STANDIN_MCP)]}
EXITS = {"command": sys.executable, "args": [str(STANDIN_MCP), "--exit-at-start"]}
REMOTE = {"type": "http", "url": "https://mcp.example.test/mcp"}
VIEW = "mcp__tracker__get_issue"
ARTIFACT = "mcp:tracker/get_issue"


class ProxiedExecutor(ScriptedExecutor):
    """A scripted `claude` that checks its judge's MCP views as the real one does (ECC-B15)."""

    def unreachable_views(self, views: ViewSet, workdir: Path) -> dict[str, str]:
        return mcpconfig.unreachable(views.tools, workdir, timeout_s=5.0)


def operator(tmp_path: Path, monkeypatch: pytest.MonkeyPatch, servers: dict[str, Any]) -> None:
    home = tmp_path / "userhome"
    home.mkdir(exist_ok=True)
    (home / ".claude.json").write_text(json.dumps({"mcpServers": servers}))
    monkeypatch.setenv("HOME", str(home))
    monkeypatch.delenv("CLAUDE_CONFIG_DIR", raising=False)


def mcp_spec() -> Any:
    """`draft` writes through the tracker's `update_issue`; its judge's view comes from the catalog."""
    spec = two_step()
    u = spec.units["draft"]
    step = dataclasses.replace(u.step, tools=("read", "write", "shell", "mcp:tracker/update_issue"))
    return dataclasses.replace(spec, units={**spec.units, "draft": dataclasses.replace(u, step=step)})


def run_it(repo: Path, answer_text: str) -> tuple[ProxiedExecutor, list[dict[str, Any]]]:
    ex = ProxiedExecutor(caps=standin("claude").caps, steps=[DRAFT, REVIEW], judges=[judge(answer_text), judge()])
    reg = Registry()
    reg.register(ex)
    start(mcp_spec(), "T-1", {"request": "Release 1.2 notes"}, repo, reg, NO_SLEEP)
    p = run_dir(state_root_path(repo), "demo", "T-1") / "run.jsonl"
    return ex, [json.loads(ln) for ln in p.read_text().splitlines()]


@pytest.mark.parametrize(("case", "servers"), [
    ("exits-at-start", {"tracker": EXITS}),
    ("missing-from-the-operators-configuration", {}),
    ("defined-by-a-url", {"tracker": REMOTE}),
])
def test_ecc_ac8_a_view_with_no_working_proxy_is_deferred_and_cannot_be_met(
        repo: Path, tmp_path: Path, monkeypatch: pytest.MonkeyPatch, case: str, servers: dict[str, Any]) -> None:
    operator(tmp_path, monkeypatch, servers)
    ex, recs = run_it(repo, verdict_block("UNVERIFIABLE"))  # a scripted judge that follows the prompt (GRD-AC2)
    judge_call = next(c for c in ex.calls if c.kind == "judge")
    assert judge_call.views is not None
    assert VIEW not in judge_call.views.tools  # no tool of `tracker` is in the judge's session
    assert not any(t.startswith("mcp__tracker") for t in judge_call.views.tools)
    assert ARTIFACT in [d.capability for d in judge_call.views.deferred]  # deferred for the attempt
    prompt = judge_call.request.prompt
    assert f"You cannot read {ARTIFACT} with your tools" in prompt  # the artifact out of reach, named in the prompt
    assert "Report UNVERIFIABLE" in prompt
    judgement = next(r for r in recs if r["kind"] == "judgement")
    assert VIEW not in judgement["views"] and ARTIFACT in [d["capability"] for d in judgement["deferred"]]
    assert [s["status"] for s in judgement["statuses"]] == ["UNVERIFIABLE"]  # never MET


def test_ecc_ac8_a_working_server_is_viewed_not_deferred(repo: Path, tmp_path: Path,
                                                         monkeypatch: pytest.MonkeyPatch) -> None:
    operator(tmp_path, monkeypatch, {"tracker": WORKS})
    ex, recs = run_it(repo, verdict_block("MET"))
    judge_call = next(c for c in ex.calls if c.kind == "judge")
    assert judge_call.views is not None
    assert VIEW in judge_call.views.tools and "mcp__tracker__update_issue" not in judge_call.views.tools  # GRD-AC6
    assert judge_call.views.deferred == ()
    assert "You cannot read" not in judge_call.request.prompt
    assert "deferred" not in next(r for r in recs if r["kind"] == "judgement")


@pytest.mark.parametrize(("case", "servers", "reason"), [
    ("exits-at-start", {"tracker": EXITS}, "start_failed"),
    ("missing", {}, "missing"),
    ("url", {"tracker": REMOTE}, "remote"),
    ("works", {"tracker": WORKS}, None),
])
def test_ecc_ac8_the_claude_executor_reports_the_servers_with_no_working_proxy(
        tmp_path: Path, monkeypatch: pytest.MonkeyPatch, case: str, servers: dict[str, Any],
        reason: str | None) -> None:
    operator(tmp_path, monkeypatch, servers)
    got = ClaudeExecutor().unreachable_views(ViewSet(tools=("Read", VIEW)), tmp_path)
    assert got == ({} if reason is None else {"tracker": reason})


# -- the declaration (ECC-B6) ---------------------------------------------------------------------------


def test_ecc_ac9_executors_declare_judge_mcp_true_for_claude(repo: Path) -> None:
    reg = Registry()
    reg.register(ClaudeExecutor())
    out = io.StringIO()
    assert main(["executors"], catalog=Catalog(), registry=reg, cwd=repo, out=out, err=io.StringIO()) == 0
    row = next(r for r in json.loads(out.getvalue())["executors"] if r["name"] == "claude")
    assert row["capabilities"]["judge_mcp"] is True
