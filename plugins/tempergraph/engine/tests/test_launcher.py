"""The session launcher (EXI-B2 to B5, B13 to B15; EXI-AC3, AC-4, AC-5, AC-10)."""

from __future__ import annotations

import json
import os
import sys
import threading
import time
from pathlib import Path
from typing import Any

import pytest

from tempergraph.contracts import EventSink
from tempergraph.executors.claude import parse_line
from tempergraph.executors.launcher import (
    LaunchSpec,
    StopRequest,
    host_speed,
    idle_action,
    launch,
)

from .fixtures import streams as S

CANARY = "CANARY-7f3a-prompt"


def spec_for(monkeypatch: pytest.MonkeyPatch, tmp_path: Path, scenario: dict[str, Any], **kw: Any) -> LaunchSpec:
    path = tmp_path / "scenario.json"
    path.write_text(json.dumps(scenario))
    monkeypatch.setenv("STANDIN_SCENARIO", str(path))  # restored after the test, whichever worker runs it
    fields: dict[str, Any] = {"argv": [sys.executable, str(S.STANDIN), "-p"], "stdin_payload": CANARY.encode(),
                              "workdir": tmp_path, "timeout_s": 30, "session_key": "draft.1.step",
                              "grace_s": 0.5}
    fields.update(kw)
    return LaunchSpec(**fields)


def alive(pid: int) -> bool:
    try:
        os.kill(pid, 0)
    except ProcessLookupError:
        return False
    # a zombie still answers signal 0; read its state where /proc exists
    stat = Path(f"/proc/{pid}/stat")
    return not (stat.exists() and stat.read_text().split()[2] == "Z")


@pytest.mark.parametrize(("age", "tool", "action"), [
    (299, False, "wait"), (301, False, "kill"), (600, True, "wait"), (901, True, "kill"),
])
def test_idle_table(age: float, tool: bool, action: str) -> None:
    assert idle_action(age, tool, 300) == action  # EXI-B4 table, EXI-AC5


def test_idle_none_never_kills() -> None:
    assert idle_action(10_000, False, None) == "wait"


def test_prompt_on_stdin_never_argv_or_env(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    rec = tmp_path / "rec.json"
    monkeypatch.setenv("TEMPERGRAPH_CALLER", "orchestrator")
    monkeypatch.setenv("TEMPERGRAPH_SUPERVISOR_TOKEN", "tok")
    spec = spec_for(monkeypatch, tmp_path, {"record": str(rec), "lines": [S.init(), S.result()]})
    out = launch(spec, parse_line, EventSink())
    seen = json.loads(rec.read_text())
    assert seen["prompt"] == CANARY
    assert all(CANARY not in a for a in seen["argv"])
    assert all(CANARY not in v for v in seen["env"].values())
    assert seen["env"]["TEMPERGRAPH_SESSION_KEY"] == "draft.1.step"
    assert "TEMPERGRAPH_CALLER" not in seen["env"] and "TEMPERGRAPH_SUPERVISOR_TOKEN" not in seen["env"]
    assert out.exit_code == 0 and out.prompt_delivered and out.stop_reason is None
    assert [e.kind for e in out.events] == ["session_started", "result"]


def test_raw_files_owner_only(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    sd = tmp_path / "sess"
    out = launch(spec_for(monkeypatch, tmp_path, {"lines": [S.init(), "not json", S.result()]}, session_dir=sd),
                 parse_line, EventSink())
    assert out.unparsable == 1 and out.lines == 3
    assert len((sd / "raw.jsonl").read_text().splitlines()) == 3
    for name in ("raw.jsonl", "stderr.log"):
        assert (sd / name).stat().st_mode & 0o777 == 0o600


@pytest.mark.skipif(os.name != "posix", reason="POSIX process groups")
def test_timeout_kills_tree_with_grandchild(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    pidfile = tmp_path / "gc.pid"
    spec = spec_for(monkeypatch, tmp_path, {"grandchild": str(pidfile), "lines": [S.init()], "hang": 60, "ignore_term": True},
                    timeout_s=1)
    t = time.monotonic()
    out = launch(spec, parse_line, EventSink())
    assert time.monotonic() - t < 10
    assert out.stop_reason == "timeout" and out.killed
    time.sleep(0.2)
    assert not alive(int(pidfile.read_text()))  # EXI-AC4


@pytest.mark.skipif(os.name != "posix", reason="POSIX process groups")
def test_signal_stop_kills_tree(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    pidfile = tmp_path / "gc.pid"
    stop = StopRequest()
    spec = spec_for(monkeypatch, tmp_path, {"grandchild": str(pidfile), "lines": [S.init()], "hang": 60})
    threading.Timer(0.8, stop.request, args=("signal",)).start()
    out = launch(spec, parse_line, EventSink(), stop=stop)
    assert out.stop_reason == "signal"
    time.sleep(0.2)
    assert not alive(int(pidfile.read_text()))


def test_graceful_stop_session_ends_by_itself(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    stop = StopRequest()
    spec = spec_for(monkeypatch, tmp_path, {"lines": [S.init()], "hang": 60, "graceful_exit": True}, grace_s=5)
    threading.Timer(0.5, stop.request).start()
    out = launch(spec, parse_line, EventSink(), stop=stop)
    assert out.stop_reason == "stop" and not out.killed  # EXI-B15 first row
    assert out.duration_s < 5


def test_graceful_stop_still_running_is_killed(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    stop = StopRequest()
    spec = spec_for(monkeypatch, tmp_path, {"lines": [S.init()], "hang": 60, "ignore_term": True}, grace_s=0.5)
    threading.Timer(0.3, stop.request).start()
    out = launch(spec, parse_line, EventSink(), stop=stop)
    assert out.stop_reason == "stop" and out.killed  # EXI-B15 second row


def test_idle_kill(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    out = launch(spec_for(monkeypatch, tmp_path, {"lines": [S.init()], "hang": 60}, idle_s=1), parse_line, EventSink())
    assert out.stop_reason == "idle"


def test_open_tool_raises_idle_floor(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    sc = {"lines": [S.init(), S.tool_use("Bash", "t1"), {"sleep": 1.6}, S.tool_result("t1"), S.result()]}
    out = launch(spec_for(monkeypatch, tmp_path, sc, idle_s=1, idle_floor_tool_s=4), parse_line, EventSink())
    assert out.stop_reason is None and out.exit_code == 0


def test_spawn_failure_does_not_raise(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    spec = spec_for(monkeypatch, tmp_path, {}, argv=[str(tmp_path / "no-such-cli"), "-p"])
    out = launch(spec, parse_line, EventSink())
    assert out.spawn_error is not None and out.exit_code is None


def test_prompt_window(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    spec = spec_for(monkeypatch, tmp_path, {"no_read": 30}, stdin_payload=b"x" * 2_000_000, prompt_window_s=0.5)
    out = launch(spec, parse_line, EventSink())
    assert out.prompt_timeout and out.stop_reason == "stop"


def test_prompt_gap_warning_with_replaced_clock(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    def clock() -> float:  # the writer thread sees time 5 s later than everyone else
        return time.monotonic() + (5.0 if threading.current_thread().name == "prompt-writer" else 0.0)

    out = launch(spec_for(monkeypatch, tmp_path, {"lines": [S.init(), S.result()]}), parse_line, EventSink(),
                 clock=clock)
    assert out.prompt_gap_s is not None and out.prompt_gap_s > 1
    assert any(w.startswith("prompt_gap") for w in out.warnings)  # EXI-B13


def test_host_speed_with_replaced_clock(tmp_path: Path) -> None:
    ticks = iter(range(0, 100, 2))
    slow = host_speed(tmp_path, clock=lambda: float(next(ticks)))
    assert slow.slow  # EXI-B14
    assert not host_speed(tmp_path).slow


@pytest.mark.skipif(os.name != "posix", reason="POSIX process groups")
def test_launcher_gives_the_group_and_resources_are_sampled(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:  # EVT-B17, EVT-B18, EVT-B7, EVT-B19
    from tempergraph.run.log import LiveSink

    sd = tmp_path / "sess"
    opened: list[dict[str, Any]] = []
    sink = LiveSink(sd, opened=opened.append)
    started = sink.process_started

    def fast(pgid: int) -> None:
        started(pgid, every_s=0.05)

    sink.process_started = fast  # type: ignore[method-assign]
    launch(spec_for(monkeypatch, tmp_path, {"lines": [S.init(), {"sleep": 0.4}, S.result()]}, session_dir=sd),
           parse_line, sink)
    sink.close()
    assert opened and isinstance(opened[0].get("pgid"), int)
    rows = [json.loads(ln) for ln in (sd / "activity.jsonl").read_text().splitlines()]
    res = [r for r in rows if r["ev"] == "resources"]
    assert res and all(r["processes"] >= 1 and r["rss_peak_kb"] > 0 and r["cpu_s"] >= 0 for r in res)


def test_resource_sample_reads_only_the_group() -> None:
    from tempergraph.run.resources import cpu_seconds, sample

    listing = " 41  1000  00:00:02\n 41   500  01:00:01.50\n 7  9999  00:00:09\n"
    assert sample(41, lambda: listing) == {"cpu_s": 3603.5, "rss_kb": 1500, "processes": 2}
    assert sample(5, lambda: listing) is None and cpu_seconds("1-00:00:00") == 86400
