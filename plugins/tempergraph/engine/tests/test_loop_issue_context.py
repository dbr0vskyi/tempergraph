"""One issue per cause and the context a loop issue carries (ISS-AC7 to ISS-AC10), against a fake code host."""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any

import pytest

from tempergraph.constants import ENGINE_VERSION
from tempergraph.improve import filing, issue_context
from tempergraph.improve.codehost import MemoryCodeHost
from tempergraph.improve.filing import Candidate, Outbox, decide

from .test_filing import CANARY, finding
from .test_loop_issues import NOW, REPO, ago, section

RECORDS: list[dict[str, Any]] = [
    {"kind": "run_started", "ts": "2026-11-25T04:00:00+00:00", "engine_version": "0.3.0", "workflow_version": "v1",
     "unit": "", "label": CANARY},
    {"kind": "task", "ts": "2026-11-25T04:00:01+00:00", "unit": "", "request": f"Write the notes {CANARY}"},
    {"kind": "attempt_start", "ts": "2026-11-25T04:00:02+00:00", "unit": "plan", "attempt": 1, "alias": "opus",
     "executor": "claude", "session_key": "plan.step.1"},
    {"kind": "session_opened", "ts": "2026-11-25T04:00:03+00:00", "unit": "plan", "model": "claude-opus-4-5",
     "transcript": f"/home/someone/{CANARY}.jsonl"},
    {"kind": "agent_run", "ts": "2026-11-25T04:01:00+00:00", "unit": "plan", "attempt": 1, "executor": "claude",
     "cli_version": "2.1.330", "ok": True, "duration_s": 61.5, "usage": {"reported_cost_usd": 0.42},
     "changed_paths": [f"{CANARY}.md", "b.md"], "session_key": "plan.step.1", "error_kind": f"broke {CANARY}"},
    {"kind": "check", "ts": "2026-11-25T04:01:01+00:00", "unit": "plan", "attempt": 1, "result": "fail",
     "notes": f"pytest said {CANARY}", "evidence": CANARY},
    {"kind": "judgement", "ts": "2026-11-25T04:01:30+00:00", "unit": "plan", "attempt": 1, "blockers": ["c-file"],
     "statuses": {"c-file": "UNMET"}, "confidence": 0.8, "gap": f"the judge wrote {CANARY}"},
    {"kind": "agent_run", "ts": "2026-11-25T04:02:00+00:00", "unit": "draft", "attempt": 1, "executor": "claude",
     "cli_version": "2.1.330", "ok": True},
    {"kind": "run_exit", "ts": "2026-11-25T04:03:00+00:00", "unit": "", "exit_code": 0, "reason": "finished",
     "cost_so_far": 1.25},
]


def cand(unit: str, fp: str, cause: str = "judge_unread_pass", **kw: Any) -> Candidate:
    return Candidate(finding=finding(unit=unit, fingerprint=fp, cause=cause, thread="demo/T-9", **kw), confidence=0.9,
                     attributed=True, records=RECORDS, mode="dev", judge_executor="claude")


def file_all(host: MemoryCodeHost, tmp_path: Path, *cs: Candidate) -> list[dict[str, Any]]:
    return filing.file([decide(c, [], REPO) for c in cs], host, Outbox.at(tmp_path), now=NOW)


def test_one_cause_at_three_units_opens_one_issue(tmp_path: Path) -> None:  # ISS-AC7
    host = MemoryCodeHost()
    res = file_all(host, tmp_path, cand("plan", "a" * 16), cand("expand", "b" * 16), cand("phase", "c" * 16))
    assert len(host.issues) == 1 and not host.comments
    assert [r["op"] for r in res] == ["filed", "grouped", "grouped"] and {r["url"] for r in res} == {host.issues[0]["url"]}
    issue = host.issues[0]
    assert issue["title"] == "[loop] demo: judge_unread_pass"  # the cause, not one unit
    summary = section(issue["body"], "## Summary")
    assert "`plan`" in summary and "`expand`" in summary and "`phase`" in summary
    for fp in ("a" * 16, "b" * 16, "c" * 16):
        assert f"<!-- {filing.marker(fp)} -->" in issue["body"].splitlines()
    # a fourth unit of the same cause in a later run comments on that issue
    (again,) = file_all(host, tmp_path, cand("code", "d" * 16))
    assert again["op"] == "commented" and len(host.issues) == 1 and host.comments[0]["number"] == 1
    assert "`code`" in host.comments[0]["body"]
    # another cause opens its own issue
    (other,) = file_all(host, tmp_path, cand("phase", "e" * 16, cause="check_fail:phase"))
    assert other["op"] == "filed" and len(host.issues) == 2


def test_an_issue_with_only_a_fingerprint_line_still_takes_its_comments(tmp_path: Path) -> None:  # ISS-AC7, SIL-B2
    host = MemoryCodeHost()
    host.create(REPO, "old", f"<!-- {filing.marker('a' * 16)} -->\nbody", ["tempergraph-loop"])  # filed before ISS-B7
    (res,) = file_all(host, tmp_path, cand("plan", "a" * 16))
    assert res["op"] == "commented" and len(host.issues) == 1
    (other_unit,) = file_all(host, tmp_path, cand("expand", "b" * 16))  # no cause line: another unit files once
    assert other_unit["op"] == "filed" and len(host.issues) == 2


def test_a_cause_closed_as_not_planned_is_muted_at_every_unit(tmp_path: Path) -> None:  # ISS-AC7, ISS-B3
    host = MemoryCodeHost()
    file_all(host, tmp_path, cand("plan", "a" * 16))
    host.close(REPO, 1, "not_planned", ago(5))
    res = file_all(host, tmp_path, cand("expand", "b" * 16), cand("phase", "c" * 16))
    assert [r["op"] for r in res] == ["muted", "muted"] and len(host.issues) == 1 and not host.comments


def test_the_open_and_closed_lists_are_read_once_per_repository(tmp_path: Path) -> None:  # ISS-AC9
    calls: list[str] = []

    class Counting(MemoryCodeHost):
        def loop_issues(self, repo: str, state: str) -> list[dict[str, Any]]:
            calls.append(state)
            return super().loop_issues(repo, state)

    host = Counting()
    file_all(host, tmp_path, cand("plan", "a" * 16), cand("plan", "b" * 16, cause="check_fail:plan"),
             cand("plan", "c" * 16, cause="retry_burst"))
    assert calls == ["open", "closed"] and len(host.issues) == 3
    # an issue the loop has just opened is found by the next filing: no search index stands between them
    calls.clear()
    (res,) = file_all(host, tmp_path, cand("plan", "a" * 16))
    assert res["op"] == "commented" and calls == ["open"]


def test_the_body_carries_environment_run_steps_and_log(tmp_path: Path) -> None:  # ISS-AC8, ISS-AC10
    host = MemoryCodeHost()
    file_all(host, tmp_path, cand("plan", "a" * 16, executor_version="2.1.330"))
    text = host.issues[0]["body"]
    env = section(text, "## Environment")
    for want in ("0.3.0", ENGINE_VERSION, "v1", "claude", "2.1.330", "claude-opus-4-5", "opus", "dev", "Python"):
        assert want in env, want
    run = section(text, "## Run")
    for want in ("demo/T-9", "Exit code: `0`", "finished", "1.25", "plan` 1", "0.42", "m1"):
        assert want in run, want
    steps = section(text, "## Steps to reproduce")
    assert "tempergraph status demo/T-9 --detail --unit plan" in steps
    assert "tempergraph logs demo/T-9 --kind run" in steps
    assert "tempergraph rerun demo demo/T-9 --from plan --check" in steps
    log = section(text, "## Run log")
    assert "run_started" in log and "run_exit" in log and "agent_run unit=plan" in log
    assert "cli_version=2.1.330" in log and "cost_usd=0.42" in log and "changed_paths=2" in log
    assert "blockers=c-file" in log and "statuses=c-file:UNMET" in log and "result=fail" in log
    assert "unit=draft" not in log  # another unit's records are not shown
    assert CANARY not in text  # request, notes, evidence, gap, transcript, paths and free text never reach it
    assert [ln for ln in text.splitlines() if ln.startswith("## ")][-1] == "## Suggested remedy"


def test_a_seen_again_comment_carries_the_same_context(tmp_path: Path) -> None:  # ISS-AC8, SIL-B2
    host = MemoryCodeHost()
    file_all(host, tmp_path, cand("plan", "a" * 16))
    file_all(host, tmp_path, cand("plan", "a" * 16))
    body = host.comments[0]["body"]
    heads = [ln for ln in body.splitlines() if ln.startswith("## ")]
    assert heads == ["## Environment", "## Run", "## Steps to reproduce", "## Run log", "## Evidence"]
    assert "Seen again" in body and "0.3.0" in body and "agent_run unit=plan" in body and CANARY not in body


def test_the_log_shows_at_most_forty_lines_and_says_how_many_it_left_out() -> None:  # ISS-AC10
    many = [RECORDS[0]] + [{"kind": "attempt_start", "ts": f"2026-11-25T04:{n // 60:02d}:{n % 60:02d}", "unit": "plan",
                            "attempt": n} for n in range(55)]
    lines, left = issue_context.log_lines(many, ["plan"])
    assert len(lines) == issue_context.LOG_LINES == 40 and left == 16
    assert "attempt=54" in lines[-1]
    host_ctx = issue_context.build(many, [finding(unit="plan")])
    assert host_ctx["log_left_out"] == 16


@pytest.mark.parametrize("value", [f"two words {CANARY}", "/a/path", "x" * 65, {"k": "a b"}, [f"{CANARY} y"]])
def test_a_value_that_is_not_an_id_enum_or_number_is_left_out(value: Any) -> None:  # ISS-AC10, SIL-AC2
    rec = [{"kind": "run_started", "ts": "t"}, {"kind": "agent_run", "unit": "plan", "reason": value, "model": value}]
    (_, line), _ = issue_context.log_lines(rec, ["plan"])
    assert "reason=" not in line and "model=" not in line


def test_a_loop_child_files_an_issue_with_the_runs_context(repo: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    # ISS-AC8, ISS-AC10: end to end through the loop's child
    from tempergraph.executors.standins import standin
    from tempergraph.improve import child

    from .test_loop_child import blocked_run, judge_says, tickets
    from .test_run import registry

    blocked_run(repo, "CX-1", monkeypatch)
    (t,) = tickets()
    doc = json.loads(t.read_text())
    t.write_text(json.dumps({**doc, "issue_repository": REPO}))
    host = MemoryCodeHost()
    child.drain(registry=registry(standin("claude", judges=[judge_says(0.9)])), host=lambda: host)
    (issue,) = host.issues
    text = issue["body"]
    assert ENGINE_VERSION in section(text, "## Environment")
    assert "demo/CX-1" in section(text, "## Run") and "tempergraph status demo/CX-1" in text
    assert "attempt_start unit=draft" in section(text, "## Run log") and "run_exit" in section(text, "## Run log")
    assert "Release 1.2 notes" not in text  # no request text
