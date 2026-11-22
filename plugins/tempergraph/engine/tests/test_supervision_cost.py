"""T7.6: the supervision journal, the Claude Code hooks, attribution and closing (SCO-B9 to SCO-B17, SCO-B1, B2, B5..B8,
SCO-AC1..5). P-SUP-3 (the live Claude Code payloads) is not run: the hook payloads here are the documented shape."""

from __future__ import annotations

import io
import json
import sys
import time
from datetime import UTC, datetime, timedelta
from pathlib import Path
from typing import Any

import pytest

from tempergraph.executors.standins import standin
from tempergraph.observe import supervision_cost as sco
from tempergraph.observe import supervision_report as sup
from tempergraph.store.layout import home_path, state_root_path

from .conftest import hash_tree
from .test_cli import cli
from .test_run import DRAFT, REVIEW, go, judge

CANARY = "canary-5d1c"
T0 = datetime(2026, 11, 1, 9, 0, tzinfo=UTC)
MODEL = "claude-sonnet-x"


def at(minutes: float) -> str:
    return (T0 + timedelta(minutes=minutes)).isoformat()


def usage(mid: str, minutes: float, *, inp: int = 1000, out: int = 100, cw: int = 0, tools: list[str] | None = None,
          agent: str | None = None) -> dict[str, Any]:
    return {"entry": "usage", "at": at(minutes), "message_id": mid, "agent_id": agent, "model": MODEL,
            "input_tokens": inp, "output_tokens": out, "cache_read_tokens": 0, "cache_write_tokens": cw,
            "tool_use_ids": tools or []}


def call(verb: str, minutes: float, tuid: str, target: str = "demo/T-1", *, background: bool = False,
         size: int = 400, agent: str | None = None) -> dict[str, Any]:
    return {"entry": "engine_call", "at": at(minutes), "tool_use_id": tuid, "agent_id": agent, "verb": verb,
            "targets": [target], "mutating": verb in sco.MUTATING, "background": background, "exit_code": 0,
            "duration_s": None, "output_bytes": size, "call_id": None}


def b1() -> list[dict[str, Any]]:
    """SCO-B1: two checks, a background run, a wake after 40 idle minutes, facts, a relay and a resume."""
    return [
        {"entry": "session", "at": at(0), "host": "claude-code", "host_session": "S1", "model": MODEL},
        usage("m1", 1, tools=["c1"]), call("run --check", 1.1, "c1"),
        usage("m2", 2, tools=["c2"]), call("run --check", 2.1, "c2"),
        usage("m3", 3, tools=["c3"]), call("run", 3.1, "c3", background=True),
        usage("m4", 3.5),
        usage("m5", 44, cw=95_000, tools=["c4"]), call("facts", 44.1, "c4", size=4000),
        usage("m6", 45),  # shows the pause to the person
        {"entry": "person_turn", "at": at(50), "prompt_id": None, "names": ["proceed"]},
        usage("r1", 50.3), usage("r2", 50.6),  # the agent carries the person's answer back
        usage("m7", 51, tools=["c5"]), call("resume", 51.1, "c5"),
        usage("m8", 52),
        {"entry": "end", "at": at(60), "reason": "other"},
    ]


def test_b1_categories_and_both_figures(repo: Path) -> None:  # SCO-B1, B2, AC-1
    threads, per = sco.attribute({("claude-code", "S1"): b1()})
    f = sco.figures(threads["demo/T-1"], per)
    assert f["completeness"] == "complete"
    assert f["calls"] == {"decide": 1, "relay": 2, "start": 3, "watch": 1}  # relay counts messages
    marginal = f["marginal"]["by_category"]
    assert set(marginal) == {"start", "watch", "decide", "rewake"}
    assert marginal["rewake"]["tokens"]["cache_write_tokens"] == 95_000  # its own line, in the marginal (B2)
    assert "relay" in f["turn"]["by_category"] and "relay" not in marginal
    assert f["marginal"]["total"]["estimated_usd"] < f["turn"]["total"]["estimated_usd"]
    assert f["observations"] == 1


def test_journal_close_report_and_sink(repo: Path, tmp_path: Path, monkeypatch: Any) -> None:  # SCO-B15, AC-1
    monkeypatch.setenv("TEMPERGRAPH_FLUSHER", "off")
    from .test_sinks import machine

    team = tmp_path / "share"
    team.mkdir()
    machine(monkeypatch, tmp_path, "a", team)
    go(repo, standin("claude", steps=[DRAFT, REVIEW], judges=[judge(), judge()]), task="T-1")
    lines = "\n".join(json.dumps(e) for e in b1()) + "\n"
    monkeypatch.setattr(sys, "stdin", io.StringIO(lines))
    code, doc, err = cli(repo, None, "supervision", "log", "--host", "claude-code", "--session", "S1")
    assert code == 0 and doc["appended"] == len(b1()), err
    shown = sco.show(home_path(), thread="demo/T-1")
    root = state_root_path(repo)
    code, closed, err = cli(repo, None, "supervision", "close")
    assert code == 0 and closed["closed"] == ["demo/T-1"], err
    [line] = sco.closed_for(root).values()
    assert line["marginal"] == shown["marginal"] and line["turn"] == shown["turn"]  # one attribution function
    assert cli(repo, None, "supervision", "close")[1]["closed"] == []  # nothing new: no second line
    a = sup.report(root, None)["total"]
    # the stand-in reports its cost and estimates none, so the share stays null (SUP-B10)
    assert a["supervision_cost_per_run"]["measured"] == 1 and a["supervision_share"]["measured"] == 0
    rec: dict[str, Any] = {}
    sup._join(rec, line, 0.30)
    assert rec["supervision_share"] == round(line["marginal"]["total"]["estimated_usd"]
                                             / (0.30 + line["marginal"]["total"]["estimated_usd"]), 4)
    assert a["observations_per_run"] == 1
    code, flushed, err = cli(repo, None, "stats", "flush")
    assert code == 0, err
    [rows] = list(team.glob("machines/*/supervision/*.jsonl"))
    row = json.loads(rows.read_text())
    assert row["kind"] == "supervision" and "thread_id" not in row and len(row["thread_hash"]) == 32
    assert "S1" not in rows.read_text() and row["sessions"][0]["session_hash"] != line["sessions"][0]["session_hash"]


def test_open_session_does_not_close(repo: Path) -> None:  # SCO-B15
    go(repo, standin("claude", steps=[DRAFT, REVIEW], judges=[judge(), judge()]), task="T-1")
    entries = [e for e in b1() if e["entry"] != "end"]
    sco.append(home_path(), "claude-code", "S1", entries)
    assert sco.close(home_path(), now=(T0 + timedelta(hours=2)).timestamp())["closed"] == []
    assert sco.close(home_path(), now=(T0 + timedelta(hours=26)).timestamp())["closed"] == ["demo/T-1"]


def test_unmeasured_supervisor_is_incomplete() -> None:  # SCO-B5
    entries = [{"entry": "session", "at": at(0), "host": "unknown", "host_session": "U1"}, call("resume", 1, "c1")]
    threads, per = sco.attribute({("unknown", "U1"): entries})
    f = sco.figures(threads["demo/T-1"], per)
    assert f["completeness"] == "incomplete" and f["marginal"] is None and f["turn"] is None
    assert sco.figures(None, per)["completeness"] == "none_known"


def test_other_work_and_helpers() -> None:  # SCO-B7, B8
    entries = [
        {"entry": "session", "at": at(0), "host": "claude-code", "host_session": "S2", "model": MODEL},
        usage("e1", 1, inp=50_000, out=5000), usage("e2", 2, inp=60_000, out=5000),  # an hour of code edits
        usage("h1", 10, tools=["c1"], agent="sub1"), call("logs", 10.1, "c1", agent="sub1"),
        usage("h2", 11, tools=["c2"], agent="sub1"), call("status --detail", 11.1, "c2", agent="sub1"),
        usage("h3", 12, inp=9000, agent="sub1"),
    ]
    threads, per = sco.attribute({("claude-code", "S2"): entries})
    f = sco.figures(threads["demo/T-1"], per)
    assert set(f["turn"]["by_category"]) == {"diagnose"}
    assert f["turn"]["by_category"]["diagnose"]["tokens"]["input_tokens"] == 11_000  # the helper's whole usage
    assert per[("claude-code", "S2")]["other"]["tokens"]["input_tokens"] == 110_000
    code_doc = sco.show(home_path(), session="S2")
    assert code_doc["sessions"] == []  # nothing written: attribute is pure


def test_log_refuses_free_text(repo: Path, monkeypatch: Any) -> None:  # SCO-B16, SCO-B11, SCO-B10
    bad = [{"entry": "person_turn", "at": at(1), "names": ["proceed"], "prompt": "free text"},
           {"entry": "usage", "at": at(1), "input_tokens": -1, "tool_use_ids": []},
           {"entry": "engine_call", "at": at(1), "verb": "rm -rf", "targets": [], "mutating": False,
            "background": False}]
    for e in bad:
        monkeypatch.setattr(sys, "stdin", io.StringIO(json.dumps(e) + "\n"))
        code, _, err = cli(repo, None, "supervision", "log", "--host", "agent-sdk", "--session", "A1")
        assert code == 2, err
    assert not (home_path() / "supervision").exists()


def _payloads(repo: Path, transcript: Path) -> list[tuple[str, dict[str, Any]]]:
    base = {"session_id": "S9", "cwd": str(repo), "transcript_path": str(transcript)}
    return [
        ("SessionStart", {**base, "model": MODEL}),
        ("UserPromptSubmit", {**base, "prompt": f"proceed please, {CANARY}"}),
        ("PostToolUse", {**base, "tool_name": "Bash", "tool_use_id": "toolu_1",
                         "tool_input": {"command": f"tempergraph resume demo T-1 --decision retry --feedback '{CANARY}'"},
                         "tool_response": {"stdout": f'{{"thread_id": "demo/T-1", "note": "{CANARY}"}}', "stderr": ""}}),
        ("PostToolUse", {**base, "tool_name": "Bash", "tool_input": {"command": f"echo {CANARY}"},
                         "tool_response": {"stdout": CANARY}}),
        ("Stop", base),
        ("SessionEnd", {**base, "reason": "logout"}),
    ]


def _transcript(path: Path) -> None:
    lines = [{"type": "user", "message": {"content": CANARY}},
             {"type": "assistant", "timestamp": at(1), "message": {
                 "id": "msg_1", "model": MODEL, "usage": {"input_tokens": 500, "output_tokens": 50},
                 "content": [{"type": "text", "text": CANARY}, {"type": "tool_use", "id": "toolu_1", "input": {}}]}},
             "not json"]
    path.write_text("\n".join(x if isinstance(x, str) else json.dumps(x) for x in lines) + "\n")


def test_hooks_keep_no_text(repo: Path, tmp_path: Path, monkeypatch: Any) -> None:  # SCO-AC3, SHL-B14, SHL-B15
    monkeypatch.setenv("TEMPERGRAPH_FLUSHER", "off")
    go(repo, standin("claude", steps=[DRAFT, REVIEW], judges=[judge(), judge()]), task="T-1")
    transcript = tmp_path / "t.jsonl"
    _transcript(transcript)
    for event, payload in _payloads(repo, transcript):
        monkeypatch.setattr(sys, "stdin", io.StringIO(json.dumps(payload)))
        code, out, _ = cli(repo, None, "supervision", "hook", event, signals=({}, False))
        assert code == 0 and out is None
    journal = sco.read(sco.journal_path(home_path(), "claude-code", "S9"))
    kinds = [e["entry"] for e in journal]
    assert kinds == ["session", "person_turn", "engine_call", "usage", "end"]  # the echo is not an engine call
    call_ = next(e for e in journal if e["entry"] == "engine_call")
    assert call_["verb"] == "resume" and call_["targets"] == ["demo/T-1"] and call_["mutating"] is True
    assert next(e for e in journal if e["entry"] == "usage")["skipped_lines"] == 1
    home, root = home_path(), state_root_path(repo)
    crossed = [p for p in sorted(home.rglob("*")) + sorted(root.rglob("*"))
               if p.is_file() and CANARY in p.read_text(errors="replace")]
    assert crossed == []


def test_engine_sessions_write_nothing(repo: Path, tmp_path: Path, monkeypatch: Any) -> None:  # SCO-B6, AC-5
    transcript = tmp_path / "t.jsonl"
    _transcript(transcript)
    for event, payload in _payloads(repo, transcript):
        monkeypatch.setattr(sys, "stdin", io.StringIO(json.dumps(payload)))
        assert cli(repo, None, "supervision", "hook", event, signals=({"TEMPERGRAPH_SESSION_KEY": "k"}, False))[0] == 0
    monkeypatch.setattr(sys, "stdin", io.StringIO(json.dumps(b1()[0]) + "\n"))
    assert cli(repo, None, "supervision", "log", "--host", "claude-code", "--session", "S1",
               signals=({"TEMPERGRAPH_SESSION_KEY": "k"}, False))[0] == 0
    assert not (home_path() / "supervision").exists()


@pytest.mark.parametrize("kind", ["session", "person_turn", "engine_call", "usage", "end"])
def test_hook_failure_is_safe(repo: Path, tmp_path: Path, monkeypatch: Any, kind: str) -> None:  # SCO-AC4
    transcript = tmp_path / "t.jsonl"
    _transcript(transcript)
    real = sco.append

    def broken(home: Path, host: str, session: str, entries: Any) -> int:
        entries = list(entries)
        if any(e.get("entry") == kind for e in entries):
            raise OSError("disk full")
        return real(home, host, session, entries)

    monkeypatch.setattr(sco, "append", broken)
    for event, payload in [*_payloads(repo, transcript), ("PostToolUse", "not an object"), ("Bogus", {})]:
        monkeypatch.setattr(sys, "stdin", io.StringIO(json.dumps(payload)))
        t = time.monotonic()
        code, out, err = cli(repo, None, "supervision", "hook", event)
        assert code == 0 and out is None and err == "" and time.monotonic() - t < 2.0
    monkeypatch.setattr(sys, "stdin", io.StringIO("{not json"))
    assert cli(repo, None, "supervision", "hook", "Stop")[0] == 0


def test_read_only_verbs_leave_the_journal(repo: Path, monkeypatch: Any) -> None:  # SCO-AC2, CLI-AC1
    go(repo, standin("claude", steps=[DRAFT, REVIEW], judges=[judge(), judge()]), task="T-1")
    sco.append(home_path(), "claude-code", "S1", [e for e in b1() if e["entry"] != "end"])
    home, root = home_path(), state_root_path(repo)
    before = hash_tree(home), hash_tree(root)
    for argv in (("supervision", "show", "demo/T-1", "--json"), ("supervision", "show", "--session", "S1"),
                 ("report", "--supervision", "--json"), ("status", "demo/T-1", "--detail")):
        assert cli(repo, None, *argv)[0] == 0
    assert (hash_tree(home), hash_tree(root)) == before
    code, doc, _ = cli(repo, None, "supervision", "show", "demo/T-1", "--json")
    assert doc["open"] is True and doc["calls"]["start"] == 3
    assert cli(repo, None, "supervision", "show")[0] == 2


def test_plugin_hooks_never_block() -> None:  # SHL-B14, SHL-B15, SCO-AC4
    from .conftest import ENGINE_ROOT

    doc = json.loads((ENGINE_ROOT.parent / "hooks" / "hooks.json").read_text())
    assert set(doc["hooks"]) == {"SessionStart", "UserPromptSubmit", "PostToolUse", "Stop", "SubagentStop", "SessionEnd"}
    for event, groups in doc["hooks"].items():
        for g in groups:
            for h in g["hooks"]:
                assert h["command"] == f"tempergraph supervision hook {event} >/dev/null 2>&1 || true"
                assert h["timeout"] <= 2
