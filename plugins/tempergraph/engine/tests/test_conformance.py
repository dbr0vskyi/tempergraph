"""The executor conformance suite (EXI-B11; EXI-AC3, AC-4, AC-6, AC-9; ADR-0091 item 2).

Each of the four declared capability sets runs through the real launcher against the recorded CLI
stand-in, plus the scripted stand-ins the engine's own tests use. Release 1 ships `claude` only, so the
three other sets are proven here until their adapters ship and re-run this suite.
"""

from __future__ import annotations

import json
import os
import sys
import threading
import time
from dataclasses import replace
from pathlib import Path
from typing import Any

import pytest

from tempergraph.constants import EXECUTOR_NAMES
from tempergraph.contracts import (
    Capabilities,
    EventSink,
    InfraCause,
    ProbeReport,
    SessionRequest,
    SessionResult,
    Usage,
    ViewSet,
)
from tempergraph.executors.capabilities import DECLARED, tool_names
from tempergraph.executors.claude import classify, parse_line
from tempergraph.executors.launcher import LaunchSpec, StopRequest, launch
from tempergraph.executors.session import build_result, summarize
from tempergraph.executors.standins import answer, standin

from .fixtures import streams as S
from .test_launcher import alive

CANARY = "CANARY-conformance-91c2"
# slow_host is assigned by the gate from the host-speed record (BUD-B1, BUD-B11), never by an executor.
EXECUTOR_CAUSES = [c for c in InfraCause if c is not InfraCause.SLOW_HOST]


class CliStandin:
    """A CLI-shaped executor over the recorded stand-in, carrying one declared capability set."""

    def __init__(self, caps: Capabilities, scenario: Path, *, argv0: str | None = None, grace_s: float = 0.3,
                 stop: StopRequest | None = None) -> None:
        self.caps, self.scenario, self.grace_s, self.stop = caps, scenario, grace_s, stop
        self.name = caps.name
        self.argv0 = argv0

    def capabilities(self) -> Capabilities:
        return self.caps

    def probe(self) -> ProbeReport:
        return ProbeReport(ok=True, version="2.1.329")

    def run_step(self, req: SessionRequest, sink: EventSink) -> SessionResult:
        argv = [self.argv0 or sys.executable, str(S.STANDIN), "-p", "--model", req.alias]
        spec = LaunchSpec(argv=argv, stdin_payload=req.prompt.encode(), workdir=req.workdir,
                          timeout_s=req.timeout_s, idle_s=req.idle_s, session_key=req.session_key,
                          env_overlay={"STANDIN_SCENARIO": str(self.scenario)}, grace_s=self.grace_s,
                          prompt_window_s=1.0)
        raw = launch(spec, parse_line, sink, stop=self.stop)
        s = summarize(raw.events, raw.duration_s)
        infra, kind = classify(raw, s)
        res = build_result(raw, s, cli_version="2.1.329", argv=argv, applied=(), infra=infra, error_kind=kind,
                           ok=s.result is not None and bool(s.result.get("ok")))
        if not self.caps.reports_cost:
            res.usage.reported_cost_usd = None
        return res

    def run_judge(self, req: SessionRequest, views: ViewSet, sink: EventSink) -> SessionResult:
        return self.run_step(req, sink)


def request(tmp_path: Path, **kw: Any) -> SessionRequest:
    fields: dict[str, Any] = {"kind": "step", "prompt": CANARY, "workdir": tmp_path, "alias": "medium",
                              "session_key": "u.1.step", "timeout_s": 30}
    fields.update(kw)
    return SessionRequest(**fields)


def scenario(tmp_path: Path, sc: dict[str, Any]) -> Path:
    p = tmp_path / "scenario.json"
    p.write_text(json.dumps(sc))
    return p


CAPS = pytest.mark.parametrize("name", EXECUTOR_NAMES)


@CAPS
def test_prompt_on_stdin_and_list_argv(name: str, tmp_path: Path) -> None:
    rec = tmp_path / "rec.json"
    ex = CliStandin(DECLARED[name], scenario(tmp_path, {"record": str(rec), "lines": [S.init(), S.result()]}))
    res = ex.run_step(request(tmp_path), EventSink())
    seen = json.loads(rec.read_text())
    assert res.ok and seen["prompt"] == CANARY
    assert isinstance(res.argv, tuple) and all(isinstance(a, str) for a in res.argv)
    assert all(CANARY not in a for a in seen["argv"]) and all(CANARY not in v for v in seen["env"].values())


@CAPS
def test_declared_tools_reported_in_order(name: str, tmp_path: Path) -> None:
    caps = DECLARED[name]
    names = [tool_names(caps, cap)[0] for cap in caps.tool_map if "*" not in cap]
    names.append(tool_names(caps, "mcp:tracker/get_issue")[0])
    lines: list[Any] = [S.init(tools=tuple(names))]
    for i, n in enumerate(names):
        lines += [S.tool_use(n, f"t{i}"), S.tool_result(f"t{i}")]
    lines.append(S.result())
    res = CliStandin(caps, scenario(tmp_path, {"lines": lines})).run_step(request(tmp_path), EventSink())
    assert [c.name for c in res.tool_calls] == names
    assert res.tools_at_start == tuple(names)
    assert caps.maps("mcp:tracker/get_issue")


@CAPS
@pytest.mark.skipif(os.name != "posix", reason="POSIX process groups")
def test_timeout_and_signal_kill_the_tree(name: str, tmp_path: Path) -> None:
    for how in ("timeout", "signal"):
        pid = tmp_path / f"{how}.pid"
        stop = StopRequest()
        ex = CliStandin(DECLARED[name], scenario(tmp_path, {"grandchild": str(pid), "lines": [S.init()],
                                                            "hang": 60, "ignore_term": True}), stop=stop)
        if how == "signal":
            threading.Timer(0.5, stop.request, args=("signal",)).start()
        res = ex.run_step(request(tmp_path, timeout_s=1 if how == "timeout" else 30), EventSink())
        assert res.partial and not res.ok
        assert res.timed_out is (how == "timeout")
        time.sleep(0.2)
        assert not alive(int(pid.read_text()))  # EXI-AC4


CAUSE_SCENARIOS: dict[InfraCause, dict[str, Any]] = {
    InfraCause.SPAWN_FAILED: {"argv0": "/nonexistent/cli"},
    InfraCause.PROMPT_NOT_DELIVERED: {"sc": {"no_read": 20}, "prompt": "x" * 2_000_000},
    InfraCause.NO_OUTPUT: {"sc": {"exit": 1}},
    InfraCause.NO_RESULT: {"sc": {"lines": [S.init()], "exit": 1}},
    InfraCause.BROKEN_PIPE: {"sc": {"close_stdin": True}, "prompt": "x" * 2_000_000},
    InfraCause.CONNECTION: {"sc": {"lines": [S.init(), S.retry("connection_error")], "exit": 1}},
    InfraCause.OUT_OF_MEMORY: {"sc": {"lines": [S.init()], "kill_self": True}},
    InfraCause.REQUEST_TIMED_OUT: {"sc": {"lines": [S.init(), S.result("Request timed out", is_error=True,
                                                                       subtype="error_during_execution")]}},
    InfraCause.THROTTLED: {"sc": {"lines": [S.init(), S.retry("rate_limit")], "exit": 1}},
}


def test_every_executor_cause_has_a_scenario() -> None:
    # BUD-AC1: every cause rule an executor assigns has a fixture scenario, run on every executor below
    assert set(CAUSE_SCENARIOS) == set(EXECUTOR_CAUSES)


@CAPS
@pytest.mark.parametrize("cause", EXECUTOR_CAUSES, ids=str)
def test_no_raise_on_every_infra_cause(name: str, cause: InfraCause, tmp_path: Path) -> None:
    # BUD-AC1: each cause rule is tested on every executor's fixtures (this runs every cause on every executor)
    case = CAUSE_SCENARIOS[cause]
    ex = CliStandin(DECLARED[name], scenario(tmp_path, case.get("sc", {})), argv0=case.get("argv0"))
    res = ex.run_step(request(tmp_path, prompt=case.get("prompt", CANARY)), EventSink())  # never raises (EXI-B6)
    assert not res.ok and res.infra_cause is cause  # EXI-AC6
    if cause is not InfraCause.REQUEST_TIMED_OUT:  # no result event: usage is unknown, never 0
        assert res.usage.reported_cost_usd is None and res.usage.input_tokens is None


@CAPS
def test_cost_reported_only_where_declared(name: str, tmp_path: Path) -> None:
    caps = DECLARED[name]
    res = CliStandin(caps, scenario(tmp_path, {"lines": [S.init(), S.result(cost=0.5)]})).run_step(
        request(tmp_path), EventSink())
    assert res.usage.reported_cost_usd == (0.5 if caps.reports_cost else None)
    assert res.usage.input_tokens == 1200


@CAPS
def test_tck_ac6_each_declared_set_names_the_credential_kinds_it_can_use_unattended(name: str) -> None:  # TCK-AC6
    kinds = DECLARED[name].unattended_credentials
    assert kinds and kinds <= {"api_key", "cloud", "oauth_token", "interactive_login"}
    assert "api_key" in kinds  # every executor can run unattended on a key in the operator's profile (TCK-B18)


@CAPS
def test_scripted_standin_carries_the_declared_set(name: str, tmp_path: Path) -> None:
    ex = standin(name, steps=[answer("done", tools=["x"], cost=0.2)])
    sink = EventSink()
    res = ex.run_step(request(tmp_path), sink)
    assert ex.capabilities() == replace(DECLARED[name], version="standin")
    assert res.usage.reported_cost_usd == (0.2 if DECLARED[name].reports_cost else None)
    assert [e.kind for e in sink.events] == ["session_started", "tool_started", "tool_finished", "result"]
    assert isinstance(res.usage, Usage) and ex.calls[0].request.prompt == CANARY
