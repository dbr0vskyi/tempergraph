"""What an operator of runs is shown: next commands after a pause or a stop (CLI-B27), the grouped help (CLI-B28),
a selector that names no thread (CLI-B29), and a wait over several threads (DUR-B16)."""

from __future__ import annotations

from pathlib import Path

import pytest

from tempergraph.cli.main import COMMANDS, HELP_GROUPS, _parser
from tempergraph.constants import ExitCode
from tempergraph.contracts import InfraCause, SessionResult, Usage
from tempergraph.durability.status import wait_any
from tempergraph.executors.standins import standin

from .fixtures.workflows import two_step
from .test_cli import cli, happy
from .test_run import DRAFT, judge, verdict_block


def test_pause_prints_next_commands(repo: Path) -> None:
    # CLI-AC16 (CLI-B27): exit 3 names the unit's detail read and `attention`, on stderr and in `--json`
    ex = standin("claude", steps=[DRAFT], judges=[judge(verdict_block("UNVERIFIABLE"))])
    code, doc, err = cli(repo, ex, "run", "demo", "notes", "--task-id", "P-1", "--json")
    assert code == ExitCode.PAUSED, err
    lines = err.splitlines()
    resume_at = next(i for i, x in enumerate(lines) if "tempergraph resume demo P-1" in x)
    assert lines[resume_at + 1].strip() == "next: tempergraph status demo/P-1 --detail --unit draft"
    assert lines[resume_at + 2].strip() == "tempergraph attention"
    assert doc["next"] == ["tempergraph status demo/P-1 --detail --unit draft", "tempergraph attention"]
    for cmd in doc["next"]:  # each one is a read the CLI accepts
        code, _, err = cli(repo, None, *cmd.split()[1:])
        assert code == 0, (cmd, err)


def test_infra_stop_prints_next_commands(repo: Path) -> None:
    # CLI-AC16 (CLI-B27): exit 5 names the thread's detail read and its log list
    broken = SessionResult(ok=False, infra_cause=InfraCause.BROKEN_PIPE, usage=Usage())
    code, doc, err = cli(repo, standin("claude", steps=[broken] * 3), "run", "demo", "notes", "--task-id", "S-1",
                         "--json")
    assert code == ExitCode.BUDGET_OR_INFRA, err
    assert doc["next"] == ["tempergraph status demo/S-1 --detail", "tempergraph logs demo/S-1"]
    assert "next: tempergraph status demo/S-1 --detail" in err
    for cmd in doc["next"]:
        code, _, err = cli(repo, None, *cmd.split()[1:])
        assert code == 0, (cmd, err)


def test_finished_run_prints_no_next_commands(repo: Path) -> None:
    # CLI-AC16 (CLI-B27): exit 0 names none
    code, doc, err = cli(repo, happy(), "run", "demo", "notes", "--task-id", "F-1", "--json")
    assert code == 0 and doc["next"] == [] and "next:" not in err


def test_help_groups_every_verb_with_operating_first(repo: Path) -> None:
    # CLI-AC17 (CLI-B28)
    text = _parser().format_help()
    assert text.index("Operate runs:") < text.index("Inspect and improve workflows:")
    grouped = [v for _, verbs in HELP_GROUPS for v in verbs]
    assert len(grouped) == len(set(grouped))
    assert set(COMMANDS) <= set(grouped), set(COMMANDS) - set(grouped)
    for verb in COMMANDS:
        assert f"\n  {verb} " in text, verb
    operate = text[text.index("Operate runs:"):text.index("Inspect and improve workflows:")]
    for verb in ("run", "resume", "attention", "status", "wait", "logs", "events"):
        assert f"\n  {verb} " in operate, verb
    code, out, err = cli(repo, None, "help")
    assert code == 0 and out == text, err


def test_status_refuses_a_selector_that_names_no_thread(repo: Path) -> None:
    # CLI-AC18 (CLI-B29): a bare task id is refused and the matching thread is named; a workflow name is not refused
    code, doc, _ = cli(repo, None, "status", "demo")  # a workflow with no thread yet
    assert code == 0 and doc["threads"] == []
    assert cli(repo, happy(), "run", "demo", "notes", "--task-id", "T-1")[0] == 0
    code, doc, err = cli(repo, None, "status", "T-1")
    assert code == ExitCode.USAGE and doc is None
    assert "names no thread" in err and "demo/T-1" in err
    code, _, err = cli(repo, None, "status", "nothing-here")
    assert code == ExitCode.USAGE and "did you mean" not in err
    code, _, err = cli(repo, None, "facts", "T-1")
    assert code == ExitCode.USAGE and "demo/T-1" in err
    code, doc, _ = cli(repo, None, "status", "demo")
    assert code == 0 and len(doc["threads"]) == 1


def test_wait_any_returns_the_first_thread_that_is_not_running(repo: Path) -> None:
    # DUR-AC14 (DUR-B16)
    assert cli(repo, happy(), "run", "demo", "notes", "--task-id", "W-1")[0] == 0
    ex = standin("claude", steps=[DRAFT], judges=[judge(verdict_block("UNVERIFIABLE"))])
    assert cli(repo, ex, "run", "demo", "notes", "--task-id", "W-2")[0] == ExitCode.PAUSED
    code, doc, err = cli(repo, None, "wait", "demo/W-2", "demo/W-1", "--any", "--timeout", "5")
    assert code == ExitCode.PAUSED and doc["thread_id"] == "demo/W-2" and doc["state"] == "paused", err
    assert [t["thread_id"] for t in doc["threads"]] == ["demo/W-2", "demo/W-1"]
    code, _, err = cli(repo, None, "wait", "demo/W-2", "demo/W-1", "--timeout", "5")
    assert code == ExitCode.USAGE and "--any" in err


def test_wait_any_ignores_verdicts_and_times_out(repo: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    # DUR-AC14 (DUR-B16): a running thread whose verdict changes does not end the wait; the timeout does, with exit 5
    from tempergraph.durability import status as st

    spec = two_step()
    rows = iter([{"thread_id": "demo/R-1", "state": "running", "last_verdict": v} for v in ("UNMET", "MET", "MET")])
    monkeypatch.setattr(st, "row", lambda *a, **k: next(rows))
    ticks = iter(range(100))
    sigs = iter(range(100))
    monkeypatch.setattr(st, "_signature", lambda paths: (next(sigs),))
    out = wait_any(repo / ".tempergraph", [(spec, "demo/R-1")], 2.5, clock=lambda: next(ticks), sleep=lambda s: None)
    assert out.exit_code == ExitCode.BUDGET_OR_INFRA and out.reason == "timeout" and out.state == "running"
    assert out.threads == [{"thread_id": "demo/R-1", "state": "running"}]
