"""Run events for observers (EVT-B1–B7, EVT-AC1–AC-6): the envelope, session_opened, the activity journal,
tool input summaries, the `events` verb and in-process observers."""

from __future__ import annotations

import json
import os
import threading
import time
from pathlib import Path
from typing import Any

import pytest

from tempergraph.constants import ExitCode
from tempergraph.contracts import Event, Usage
from tempergraph.docs import iter_jsonl
from tempergraph.executors.capabilities import CLAUDE
from tempergraph.executors.claude import parse_line
from tempergraph.executors.standins import standin
from tempergraph.executors.summary import capability_of, input_summary
from tempergraph.run import events as evmod
from tempergraph.run import runner as runnermod
from tempergraph.run.events import ObserverHub, follow, narrate, records
from tempergraph.run.log import LiveSink, RunLog, split_session_key
from tempergraph.run.runner import resume
from tempergraph.store.layout import run_dir, state_root_path

from .conftest import hash_tree
from .fixtures import streams as S
from .fixtures.workflows import two_step
from .test_cli import cli
from .test_run import DRAFT, NO_SLEEP, REVIEW, go, judge, registry, verdict_block

ENVELOPE = ("seq", "ts", "kind", "thread_id", "segment", "unit", "item", "attempt", "session_key")
CANARY = "sk-ant-CANARY0123456789abcdef"


def log_path(repo: Path, task: str = "T-1") -> Path:
    return run_dir(state_root_path(repo), "demo", task) / "run.jsonl"


# -- envelope and sequence (EVT-B8, EVT-B9, AC-1, AC-2, B2) ----------------------------------------------------


def test_every_record_carries_the_envelope(repo: Path) -> None:
    ex = standin("claude", steps=[DRAFT, DRAFT, REVIEW], judges=[judge(verdict_block("UNMET")), judge(), judge()])
    assert go(repo, ex).exit_code is ExitCode.FINISHED
    recs = records(log_path(repo))
    assert recs, "no records"
    for r in recs:
        assert all(k in r for k in ENVELOPE), (r["kind"], [k for k in ENVELOPE if k not in r])
        assert r["thread_id"] == "demo/T-1" and r["segment"] == 0
    kinds = {r["kind"] for r in recs}
    assert {"run_started", "unit_entered", "session_opened", "check", "judgement", "gate", "run_exit"} <= kinds
    gate = next(r for r in recs if r["kind"] == "gate")
    assert gate["unit"] == "draft" and "route_target" in gate
    att = next(r for r in recs if r["kind"] == "attempt_start" and r["session_key"] == "draft.2.retry")
    assert (att["unit"], att["attempt"]) == ("draft", 2)
    # an old reader that knows only the OBS-B7, OBS-B1, OBS-B8, OBS-B9 kinds reads the same file and skips the rest (OVR-B14)
    counts: dict[str, int] = {}
    old = list(iter_jsonl(log_path(repo), frozenset({"run_started", "agent_run", "gate", "run_exit"}), counts))
    assert old and counts.get("unknown_kinds", 0) > 0 and counts.get("unparsable", 0) == 0


def test_seq_continues_across_three_resumes(repo: Path) -> None:
    esc = judge(verdict_block("UNVERIFIABLE"))
    ex = standin("claude", steps=[DRAFT], judges=[esc])
    assert go(repo, ex).exit_code is ExitCode.PAUSED
    for _ in range(2):  # retry the escalated attempt and escalate again
        ex.steps, ex.judges = [DRAFT], [esc]
        assert resume(two_step(), "T-1", repo, registry(ex), decision="retry",
                      settings=NO_SLEEP).exit_code is ExitCode.PAUSED
    ex.steps, ex.judges = [REVIEW], [judge()]
    assert resume(two_step(), "T-1", repo, registry(ex), decision="proceed",
                  settings=NO_SLEEP).exit_code is ExitCode.FINISHED
    recs = records(log_path(repo))
    seqs = [r["seq"] for r in recs]
    assert seqs == sorted(set(seqs)) and seqs == list(range(1, len(seqs) + 1))  # EVT-AC2
    starts = [r for r in recs if r["kind"] == "run_started"]
    assert [r["segment"] for r in starts] == [0, 1, 2, 3]
    for s in starts[1:]:  # EVT-B2: a resume's first run-started record continues from the last seq
        prev = recs[s["seq"] - 2]  # the segment's last record: its run_exit, or the finding_recorded after it
        assert prev["kind"] in ("run_exit", "finding_recorded") and prev["segment"] == s["segment"] - 1
        assert any(r["kind"] == "run_exit" and r["segment"] == s["segment"] - 1 for r in recs)
    assert {r["segment"] for r in recs if r["seq"] > starts[-1]["seq"]} == {3}


def test_seq_continues_after_a_cut_off_attempt(tmp_path: Path) -> None:
    path = tmp_path / "runs" / "demo" / "T-9" / "run.jsonl"
    log = RunLog(path)
    log.write("run_started")
    log.write("attempt_start", session_key="draft.1.step", kind="step")
    with open(path, "a", encoding="utf-8") as fh:
        fh.write('{"kind": "agent_run", "seq": 3, "ts"')  # the process died mid-line
    again = RunLog(path)
    again.write("run_started")
    recs = records(path)
    assert [r["seq"] for r in recs] == [1, 2, 3] and recs[-1]["segment"] == 1


@pytest.mark.parametrize(("key", "expected"), [
    ("plan.2.judge", ("plan", None, 2)), ("code.p3.1.judge_reask.2", ("code", "p3", 1)),
    ("draft.1.step", ("draft", None, 1)), ("odd", (None, None, None))])
def test_split_session_key(key: str, expected: tuple[Any, ...]) -> None:
    assert split_session_key(key) == expected


# -- session_opened and the journal (EVT-B1, EVT-B17, EVT-B18, EVT-B7, EVT-B19, EVT-B20) -----------------------------------------------------


def test_a_session_is_visible_with_its_transcript_locator(repo: Path) -> None:
    from tempergraph.contracts import ToolCall
    from tempergraph.executors.standins import answer

    step = answer("Wrote notes.md\nARTIFACT notes: notes.md", session_id="s-draft", tools=("Read", "Bash"))
    step.tool_calls = [ToolCall(name="Read", ok=True, call_id="c1"), ToolCall(name="Bash", ok=True, call_id="c2")]
    ex = standin("claude", steps=[step, REVIEW], judges=[judge(), judge()])
    assert go(repo, ex).exit_code is ExitCode.FINISHED
    recs = records(log_path(repo))
    opened = next(r for r in recs if r["kind"] == "session_opened" and r["session_key"] == "draft.1.step")
    assert opened["session_id"] == "s-draft" and opened["session_kind"] == "step"
    assert opened["transcript"]["engine"].endswith("sessions/draft.1.step/raw.jsonl")
    assert opened["transcript"]["native"] is None  # P-CC-7 not run
    assert opened["seq"] < next(r["seq"] for r in recs if r["kind"] == "agent_run")
    journal = evmod.activity(log_path(repo).parent / "sessions" / "draft.1.step" / "activity.jsonl")
    evs = [ln["ev"] for ln in journal]
    assert evs.count("tool_started") == 2 and evs.count("tool_finished") == 2
    assert [ln["n"] for ln in journal] == list(range(1, len(journal) + 1))
    assert all("duration_s" in ln for ln in journal if ln["ev"] == "tool_finished")
    assert not (log_path(repo).parent / "sessions" / "draft.1.step" / "live.json").exists()  # removed at end


def _sink(tmp_path: Path, **kw: Any) -> tuple[LiveSink, list[dict[str, Any]]]:
    opened: list[dict[str, Any]] = []
    clock = iter(float(x) for x in range(10**6))  # a second per event, so every event refreshes the live file
    return LiveSink(tmp_path / "s", clock=lambda: next(clock), opened=opened.append, **kw), opened


def test_live_file_and_journal_while_running(tmp_path: Path) -> None:
    sink, opened = _sink(tmp_path)
    sink.push(Event(kind="session_started", data={"session_id": "s1", "model": "m"}, ts=0.1))
    sink.push(Event(kind="tool_started", data={"name": "Grep", "call_id": "a", "capability": "search",
                                               "input_summary": "TODO"}, ts=0.5))
    sink.flush()
    live = json.loads((tmp_path / "s" / "live.json").read_text())
    assert live["open_tool"]["name"] == "Grep" and live["open_tool"]["capability"] == "search"
    assert live["open_tool"]["started_at"] and opened == [{"session_id": "s1", "model": "m"}]
    sink.push(Event(kind="tool_finished", data={"call_id": "a", "ok": True}, ts=2.0))
    sink.push(Event(kind="result", data={"ok": True, "usage": Usage(input_tokens=10, output_tokens=5, turns=2)},
                    ts=2.5))
    live = json.loads((tmp_path / "s" / "live.json").read_text())
    assert live["open_tool"] is None and live["recent"] == [
        {"name": "Grep", "input_summary": "TODO", "ok": True, "duration_s": 1.5}]
    assert live["tokens_so_far"] == 15 and live["turns_so_far"] == 2
    sink.close()
    assert not (tmp_path / "s" / "live.json").exists()


def test_tool_inputs_off_hides_every_summary(tmp_path: Path) -> None:  # EVT-B6
    sink, _ = _sink(tmp_path, tool_inputs=False)
    sink.push(Event(kind="tool_started", data={"name": "Bash", "call_id": "a", "input_summary": "make test"}))
    sink.flush()
    live = json.loads((tmp_path / "s" / "live.json").read_text())
    assert live["open_tool"]["input_summary"] is None
    sink.close()
    line = evmod.activity(tmp_path / "s" / "activity.jsonl")[0]
    assert line["input_summary"] is None


def test_journal_cap_keeps_tool_lines(tmp_path: Path) -> None:  # EVT-B7
    sink, _ = _sink(tmp_path)
    tools = 0
    for i in range(30_000):
        if i % 300 == 0:
            sink.push(Event(kind="tool_started", data={"name": "Read", "call_id": f"c{i}"}, ts=i / 100))
            sink.push(Event(kind="tool_finished", data={"call_id": f"c{i}", "ok": True}, ts=i / 100))
            tools += 2
        else:
            sink.push(Event(kind="model_delta" if i % 3 else "text", data={"chars": 3, "last_line": "x"}, ts=i / 100))
    sink.close()
    lines = evmod.activity(tmp_path / "s" / "activity.jsonl")
    assert len(lines) <= 20_000
    assert sum(1 for ln in lines if ln["ev"] in ("tool_started", "tool_finished")) == tools
    assert lines[-1]["ev"] == "truncated" and set(lines[-1]["dropped"]) <= {"model_delta", "text"}
    assert sum(lines[-1]["dropped"].values()) + len(lines) - 1 == 30_000 + tools - 100  # every event counted


def test_journal_write_failure_is_contained(tmp_path: Path) -> None:
    blocker = tmp_path / "s"
    blocker.write_text("not a folder")  # the session folder cannot be created
    sink = LiveSink(blocker)
    sink.push(Event(kind="tool_started", data={"name": "Read", "call_id": "a"}))
    sink.flush()
    sink.close()
    assert sink.disabled and sink.failures >= 1


# -- tool input summaries (EVT-B21, B4, AC-3) ------------------------------------------------------------


def _summary(name: str, inp: dict[str, Any], workdir: Path) -> Any:
    line = json.dumps(S.tool_use(name, "c1", inp=inp)).encode()
    (ev,) = parse_line(line, workdir=workdir)
    return ev.data


def test_shell_summary_and_the_b4_table(tmp_path: Path) -> None:
    ws = tmp_path / "ws"
    d = _summary("Bash", {"command": "pytest -q tests/api", "cwd": str(ws / "svc")}, ws)
    assert (d["name"], d["capability"], d["input_summary"]) == ("Bash", "shell", "pytest -q tests/api (in svc)")
    d = _summary("Bash", {"command": "export TOKEN=sk-ant-abcdefghijklmnop && make test"}, ws)
    assert d["input_summary"] == "export TOKEN=[redacted] && make test"
    d = _summary("Read", {"file_path": "/etc/passwd"}, ws)
    assert d["input_summary"] == "<outside workspace>"
    heredoc = "cat <<EOF\n" + "x" * 600 + "\nEOF"
    d = _summary("Bash", {"command": heredoc}, ws)
    assert len(d["input_summary"]) == 200 and d["input_summary"].endswith("…")


@pytest.mark.parametrize(("tool", "inp", "expected"), [
    ("Read", {"file_path": "{ws}/src/app.py"}, "src/app.py"),
    ("Edit", {"file_path": "{ws}/README.md", "old_string": "a", "new_string": "b"}, "README.md"),
    ("Write", {"file_path": "../outside.txt"}, "<outside workspace>"),
    ("Glob", {"pattern": "**/*.py"}, "**/*.py"),
    ("Grep", {"pattern": "def main"}, "def main"),
    ("WebFetch", {"url": "https://docs.example.com/a/b?q=1", "prompt": "summarise"}, "docs.example.com"),
    ("WebSearch", {"query": "secret plans"}, "query"),
    ("Agent", {"subagent_type": "Explore", "prompt": "look"}, "Explore"),
    ("mcp__github__get_issue", {"number": 1}, "github/get_issue"),
    ("Mystery", {"x": 1}, None),
])
def test_summary_per_capability(tmp_path: Path, tool: str, inp: dict[str, Any], expected: Any) -> None:
    ws = tmp_path / "ws"
    inp = {k: v.replace("{ws}", str(ws)) if isinstance(v, str) else v for k, v in inp.items()}
    assert _summary(tool, inp, ws)["input_summary"] == expected


def test_every_declared_tool_has_a_capability() -> None:
    for cap, names in CLAUDE.tool_map.items():
        for name in names:
            if "{" not in name and not cap.endswith(":*"):
                assert capability_of(CLAUDE, name) == cap
    assert input_summary("shell", "Bash", {"command": "ls"}, None) == "ls"


# -- the canary (EVT-AC4) -----------------------------------------------------------------------------------


def test_tool_inputs_only_in_journals_and_live_files(tmp_path: Path) -> None:
    log = RunLog(tmp_path / "runs" / "demo" / "T-1" / "run.jsonl")
    log.write("run_started")
    sdir = tmp_path / "runs" / "demo" / "T-1" / "sessions" / "draft.1.step"
    from tempergraph.contracts import SessionRequest
    from tempergraph.run.log import session_sink

    req = SessionRequest(kind="step", prompt="p", workdir=tmp_path, alias="inherit", session_key="draft.1.step",
                         session_dir=sdir)
    sink = session_sink(log, req, "claude")
    ticks = iter(float(x) for x in range(100))
    sink.clock = lambda: next(ticks)
    sink.push(Event(kind="session_started", data={"session_id": "s1"}))
    planted = "PLANTED-INPUT-7781"
    line = json.dumps(S.tool_use("Bash", "c1", inp={"command": f"echo {planted} {CANARY}"})).encode()
    for ev in parse_line(line, workdir=tmp_path):
        sink.push(ev)
    sink.flush()
    live_text = (sdir / "live.json").read_text()
    sink.close()
    log.write("run_exit", exit_code=0)
    run_text = log.path.read_text()
    journal_text = (sdir / "activity.jsonl").read_text()
    assert planted not in run_text and planted in journal_text and planted in live_text
    for text in (run_text, journal_text, live_text):
        assert CANARY not in text


# -- in-process observers (EVT-B22, EVT-B23, EVT-B24, EVT-B5, EVT-AC5) -----------------------------------------------------------------


class Recorder:
    def __init__(self, name: str = "rec", fail_at: int | None = None, fail_activity: bool = False) -> None:
        self.name = name
        self.fail_at = fail_at
        self.fail_activity = fail_activity
        self.seen: list[dict[str, Any]] = []
        self.lines: list[tuple[str, dict[str, Any]]] = []

    def on_record(self, record: dict[str, Any]) -> None:
        self.seen.append(record)
        if self.fail_at is not None and len(self.seen) == self.fail_at:
            raise RuntimeError("observer broke")

    def on_activity(self, session_key: str, line: dict[str, Any]) -> None:
        self.lines.append((session_key, line))
        if self.fail_activity:
            raise ValueError("activity broke")


def _with_observers(monkeypatch: pytest.MonkeyPatch, observers_: list[Any]) -> list[ObserverHub]:
    hubs: list[ObserverHub] = []

    class Observed(RunLog):
        def __init__(self, path: Path, observers: Any = None) -> None:
            hub = ObserverHub(observers_)
            hubs.append(hub)
            super().__init__(path, observers=hub)

    monkeypatch.setattr(runnermod, "RunLog", Observed)
    return hubs


@pytest.mark.parametrize("which", ["record", "activity"])
def test_a_failing_observer_leaves_the_run_unchanged(repo: Path, monkeypatch: pytest.MonkeyPatch, which: str) -> None:
    # EVT-AC5 (EVT-B5)
    broken = Recorder("broken", fail_at=3) if which == "record" else Recorder("broken", fail_activity=True)
    good = Recorder("good")
    hubs = _with_observers(monkeypatch, [broken, good])
    ex = standin("claude", steps=[DRAFT, REVIEW], judges=[judge(), judge()])
    assert go(repo, ex).exit_code is ExitCode.FINISHED
    for h in hubs:
        h.close()
    recs = records(log_path(repo))
    errors = [r for r in recs if r["kind"] == "engine_error" and r.get("scope") == "observer"]
    assert len(errors) == 1 and errors[0]["observer"] == "broken"
    assert good.seen and good.lines  # the other observer saw records and activity lines
    assert [r["seq"] for r in good.seen if r["kind"] != "engine_error"][:3] == sorted(
        [r["seq"] for r in good.seen if r["kind"] != "engine_error"][:3])


def test_a_full_queue_drops_and_counts() -> None:  # EVT-AC5 (EVT-B23: a queue of 1 000)
    gate = threading.Event()

    class Slow(Recorder):
        def on_record(self, record: dict[str, Any]) -> None:
            gate.wait(5)

    hub = ObserverHub([Slow("slow")])
    for i in range(evmod.QUEUE_SIZE + 50):
        hub.on_record({"seq": i})
    gate.set()
    stats = hub.close()
    assert stats["slow"]["dropped"] >= 49 and not stats["slow"]["disabled"]


def test_register_observers_reports_missing_names() -> None:  # EVT-AC5
    found, missing = evmod.register_observers(names=("not-installed",))
    assert found == [] and missing == ["not-installed"]


class Threaded(Recorder):
    """Notes the name of the thread each call runs on."""

    def __init__(self, name: str = "rec", fail_at: int | None = None) -> None:
        super().__init__(name, fail_at=fail_at)
        self.threads: set[str] = set()

    def on_record(self, record: dict[str, Any]) -> None:
        self.threads.add(threading.current_thread().name)
        super().on_record(record)

    def on_activity(self, session_key: str, line: dict[str, Any]) -> None:
        self.threads.add(threading.current_thread().name)
        super().on_activity(session_key, line)


class FakeEntryPoint:
    def __init__(self, name: str, obj: Any) -> None:
        self.name = name
        self.obj = obj

    def load(self) -> Any:
        return self.obj


def _install(monkeypatch: pytest.MonkeyPatch, tmp_path: Path, installed: dict[str, Any], named: list[str]) -> list[str]:
    """Register fixture observers under the entry-point group and name some of them in the operator config."""
    groups: list[str] = []

    def fake(group: str) -> list[FakeEntryPoint]:
        groups.append(group)
        return [FakeEntryPoint(n, o) for n, o in installed.items()] if group == "tempergraph.observers" else []

    monkeypatch.setattr(evmod, "entry_points", fake)
    cfg = Path(os.environ["TEMPERGRAPH_HOME"]) / "config"
    cfg.mkdir(parents=True, exist_ok=True)
    (cfg / "settings.json").write_text(json.dumps({"schema_version": 1, "observe": {"observers": named}}))
    return groups


def _wait(cond: Any, timeout_s: float = 10.0) -> bool:
    end = time.monotonic() + timeout_s
    while time.monotonic() < end:
        if cond():
            return True
        time.sleep(0.02)
    return bool(cond())


def test_observers_load_from_the_entry_point_group_and_see_every_line(repo: Path, tmp_path: Path,
                                                                     monkeypatch: pytest.MonkeyPatch) -> None:
    # EVT-AC5 (EVT-B23): loaded only from the group, only the named ones, each on its own thread
    named, other = Threaded("named"), Threaded("other")
    groups = _install(monkeypatch, tmp_path, {"named": named, "other": other}, ["named"])
    assert go(repo, standin("claude", steps=[DRAFT, REVIEW], judges=[judge(), judge()])).exit_code is ExitCode.FINISHED
    assert set(groups) == {"tempergraph.observers"}
    sessions = log_path(repo).parent / "sessions"
    journal = sum(len(p.read_text().splitlines()) for p in sessions.glob("*/activity.jsonl"))
    assert journal > 0
    _wait(lambda: len(named.lines) == journal)
    assert len(named.lines) == journal  # every activity line, after it was written
    assert _wait(lambda: any(r["kind"] == "run_exit" for r in named.seen)), [r["kind"] for r in named.seen]
    logged = records(log_path(repo))
    first = next(r["seq"] for r in logged if r["kind"] == "run_started")
    last = next(r["seq"] for r in logged if r["kind"] == "run_exit")
    inside = [r["seq"] for r in logged if first <= r["seq"] <= last]  # what the segment's own writer wrote
    assert len(inside) > 5
    assert _wait(lambda: set(inside) <= {r["seq"] for r in named.seen})  # every record, after it was written
    assert {r["seq"] for r in named.seen} <= {r["seq"] for r in logged}
    assert other.seen == [] and other.lines == []  # not named: not loaded
    assert named.threads and all(t == "observer-named" for t in named.threads)
    assert threading.current_thread().name not in named.threads


def test_a_raising_observer_is_contained_and_recorded_once(repo: Path, tmp_path: Path,
                                                           monkeypatch: pytest.MonkeyPatch) -> None:
    # EVT-AC5 (EVT-B5, EVT-B25): disabled for the segment, one engine_error of scope observer, the exit unchanged
    broken, good = Threaded("broken", fail_at=3), Threaded("good")
    _install(monkeypatch, tmp_path, {"broken": broken, "good": good}, ["broken", "good"])
    out = go(repo, standin("claude", steps=[DRAFT, REVIEW], judges=[judge(), judge()]))
    assert out.exit_code is ExitCode.FINISHED
    assert _wait(lambda: any(r["kind"] == "run_exit" for r in good.seen))
    errors = [r for r in records(log_path(repo)) if r["kind"] == "engine_error" and r.get("scope") == "observer"]
    assert len(errors) == 1 and errors[0]["observer"] == "broken"
    assert len([r for r in broken.seen if r["kind"] != "engine_error"]) == 3  # nothing after the third


# -- the events verb (EVT-B22, EVT-B23, EVT-B24, B3, AC-6, EVT-B25) --------------------------------------------------------------------


def test_events_since_prints_in_order_and_creates_nothing(repo: Path) -> None:
    assert go(repo, standin("claude", steps=[DRAFT, REVIEW], judges=[judge(), judge()])).exit_code == 0
    root = state_root_path(repo)
    before = hash_tree(root)
    code, out, err = cli(repo, None, "events", "demo/T-1", "--since", "5", "--json")
    assert code == 0, err
    lines = [json.loads(ln) for ln in out.splitlines()] if isinstance(out, str) else [out]
    assert [r["seq"] for r in lines] == list(range(6, len(records(log_path(repo))) + 1))
    code, text, _ = cli(repo, None, "events", "demo/T-1", "--follow")
    assert code == 0 and isinstance(text, str) and "segment 0 exited 0" in text
    code, act, _ = cli(repo, None, "events", "demo/T-1", "--activity", "draft.1.step")
    assert code == 0
    assert hash_tree(root) == before  # read-only (OVR-B15)


def test_events_without_a_run_log_is_a_usage_error(repo: Path) -> None:
    code, _, err = cli(repo, None, "events", "demo/T-404")
    assert code == ExitCode.USAGE and "T-404" in err


def test_follow_prints_each_record_once_until_exit(tmp_path: Path) -> None:  # EVT-B3, AC-6
    path = tmp_path / "runs" / "demo" / "T-1" / "run.jsonl"
    log = RunLog(path)
    for _ in range(500):
        log.write("check", unit="draft", result="PASS")
    held = threading.Event()
    held.set()

    def writer() -> None:
        for i in range(139):
            log.write("check", unit="draft", result="PASS", n=i)
            if i % 20 == 0:
                time.sleep(0.01)
        log.write("run_exit", exit_code=3, reason="escalation")
        time.sleep(0.05)
        held.clear()

    t = threading.Thread(target=writer)
    t.start()
    got = [r["seq"] for r in follow(path, held.is_set, since=500, poll_s=0.01, timeout_s=10)]
    t.join()
    assert got == list(range(501, 641))


def test_follow_ends_on_an_orphaned_thread(tmp_path: Path) -> None:
    path = tmp_path / "runs" / "demo" / "T-1" / "run.jsonl"
    log = RunLog(path)
    log.write("run_started")
    log.write("unit_entered", unit="draft")
    got = list(follow(path, lambda: False, poll_s=0.01, timeout_s=5))
    assert [r["kind"] for r in got] == ["run_started", "unit_entered"]


def test_narrator_lines() -> None:
    assert narrate({"seq": 4, "ts": "t", "kind": "gate", "unit": "code", "attempt": 2, "verdict": "BACK",
                    "route_target": "plan"}) == "4 t gate code#2: BACK -> plan"
    assert narrate({"seq": 5, "ts": "t", "kind": "something_new"}) == "5 t something_new"
