"""An agent's decision at a pause names its reason; every resume line names the option (CLI-B30, HUM-B20)."""

from __future__ import annotations

import dataclasses
import time
from pathlib import Path
from typing import Any

import pytest

from tempergraph.constants import ExitCode
from tempergraph.durability.status import resume_command as status_resume_command
from tempergraph.executors.standins import standin
from tempergraph.run.runner import resume
from tempergraph.store.layout import run_dir, state_root_path

from . import test_ask_wait as ask
from .fixtures.workflows import two_step
from .test_fallback_breakpoint import go as breakpoint_go
from .test_fallback_breakpoint import wf as breakpoint_wf
from .test_run import DRAFT, NO_SLEEP, REVIEW, go, judge, registry, verdict_block
from .test_usage_limit import _pause_payload, _plain, refused

AGENT = {"kind": "agent", "host": "claude-code", "host_session": "sess-1"}
PERSON = {"kind": "person"}
SIX = ("engine_defect", "judge_error", "environment", "plan", "request", "other")
UNVERIFIABLE = verdict_block("UNVERIFIABLE")


def on_gap(repo: Path, task: str = "T-1") -> Any:
    """A thread paused at `review` on an unresolved gap."""
    ex = standin("claude", steps=[DRAFT, REVIEW, DRAFT, REVIEW], judges=[judge(), judge(UNVERIFIABLE), judge(), judge()])
    out = go(repo, ex, task=task)
    assert out.exit_code is ExitCode.PAUSED and out.payload["unit"] == "review", out.message
    return ex


def files_of(repo: Path, task: str) -> tuple[str, str]:
    root = state_root_path(repo)
    ledger = root / "ledger.jsonl"
    log = run_dir(root, "demo", task) / "run.jsonl"
    return (ledger.read_text() if ledger.exists() else "", log.read_text())


def decide(repo: Path, ex: Any, decision: str | None, caller: dict[str, Any], task: str = "T-1", spec: Any = None,
           **kw: Any) -> Any:
    return resume(spec or two_step(), task, repo, registry(ex), decision=decision,
                  settings=dataclasses.replace(NO_SLEEP, caller=caller, **kw))


def assert_refused_for_reason(out: Any) -> None:
    assert out.exit_code is ExitCode.USAGE, out.message
    assert "--reason" in out.message and all(w in out.message for w in SIX), out.message


@pytest.mark.parametrize("word", ["proceed", "retry", "back:draft", "stop"])
def test_cli_ac19_an_agents_decision_at_a_gate_pause_needs_a_reason(repo: Path, word: str) -> None:  # CLI-AC19, AC 10
    ex = on_gap(repo)
    before = files_of(repo, "T-1")
    assert_refused_for_reason(decide(repo, ex, word, AGENT))
    assert files_of(repo, "T-1") == before  # no ledger row, no run.jsonl record
    again = decide(repo, ex, "stop", PERSON)  # the thread is still paused, so a person's decision is accepted
    assert again.exit_code is ExitCode.STOPPED, again.message


def test_cli_ac19_with_a_reason_the_agents_decision_is_accepted(repo: Path) -> None:  # CLI-AC19, AC 10
    ex = on_gap(repo)
    done = decide(repo, ex, "proceed", AGENT, operator_reason="other")
    assert done.exit_code is ExitCode.FINISHED, done.message


def test_cli_ac19_a_persons_decision_needs_no_reason(repo: Path) -> None:  # CLI-AC19, AC 10
    ex = on_gap(repo)
    done = decide(repo, ex, "proceed", PERSON)
    assert done.exit_code is ExitCode.FINISHED, done.message


def test_cli_ac19_an_agents_answer_at_an_ask_needs_a_reason(repo: Path) -> None:  # CLI-AC19, AC 10
    spec = ask.asking_wf()
    ask.begin(repo, spec)
    before = files_of(repo, "A-1")
    assert_refused_for_reason(ask.again(repo, spec, answers={"env": "prod"}, caller=AGENT))
    assert_refused_for_reason(ask.again(repo, spec, decision="stop", caller=AGENT))
    assert files_of(repo, "A-1") == before
    kept = ask.again(repo, spec, answers={"env": "prod"}, caller=AGENT, operator_reason="request")
    assert kept.exit_code is ExitCode.PAUSED, kept.message  # accepted: the ask is still open


def test_cli_ac19_an_agents_event_at_a_wait_needs_a_reason(repo: Path) -> None:  # CLI-AC19, AC 10
    spec = ask.waiting_wf()
    ask.begin(repo, spec)
    before = files_of(repo, "A-1")
    assert_refused_for_reason(ask.again(repo, spec, decision="event:approved=yes", caller=AGENT))
    assert files_of(repo, "A-1") == before
    done = ask.again(repo, spec, decision="event:approved=yes", caller=AGENT, operator_reason="other")
    assert done.exit_code is ExitCode.FINISHED, done.message


def test_cli_ac19_a_breakpoint_a_usage_limit_resume_and_a_deadline_need_no_reason(repo: Path) -> None:  # CLI-AC19, AC 10
    spec = breakpoint_wf()
    ex = standin("claude", steps=[DRAFT] * 3, judges=[judge()] * 3)
    out = breakpoint_go(repo, spec, ex, pause_before=("build",))
    assert out.exit_code is ExitCode.PAUSED and out.reason == "breakpoint", out.message
    done = resume(spec, "F-1", repo, registry(ex), decision="proceed",
                  settings=dataclasses.replace(NO_SLEEP, caller=AGENT))
    assert done.exit_code is not ExitCode.USAGE, done.message

    limited = standin("claude", steps=[refused(time.time() + 3600, error_kind="model")] * 3 + [DRAFT, REVIEW],
                      judges=[judge(), judge()])
    assert go(repo, limited, task="L-1").exit_code is ExitCode.PAUSED
    plain = resume(two_step(), "L-1", repo, registry(limited), settings=dataclasses.replace(NO_SLEEP, caller=AGENT))
    assert plain.exit_code is not ExitCode.USAGE, plain.message

    waiting = ask.waiting_wf()
    ask.begin(repo, waiting, task="W-1")
    due = ask.again(repo, waiting, task="W-1", caller=AGENT, apply_deadline=True)
    assert "--reason" not in due.message, due.message  # refused for its own reason (no deadline), not for a missing one


# ---- HUM-B20: every resume line that carries --decision names the option and the six words


def named_reason(line: str) -> bool:
    return "--reason" in line and all(w in line for w in SIX)


def test_hum_ac15_a_gate_pause_payload_names_the_reason_option(repo: Path) -> None:  # HUM-AC15, AC 10
    on_gap(repo)
    assert named_reason(_pause_payload(repo)["resume"])


def test_hum_ac15_an_ask_and_an_event_wait_payload_name_the_reason_option(repo: Path) -> None:  # HUM-AC15, AC 10
    out = ask.begin(repo, ask.asking_wf())
    assert out.payload["kind"] == "input" and named_reason(out.payload["resume"])
    waited = ask.begin(repo, ask.waiting_wf(), task="W-1")
    assert waited.payload["kind"] == "event_wait" and named_reason(waited.payload["resume"])
    assert "--decision event:approved=<value>" in waited.payload["resume"]


def test_hum_ac15_a_council_pause_payload_names_the_reason_option() -> None:  # HUM-AC15, AC 10
    from tempergraph.run import gate as gatemod

    src = Path(gatemod.__file__).read_text()
    line = next(ln for ln in src.splitlines() if "answer:decision=<option>" in ln and "resume" in ln)
    assert "--reason" in line, line  # the council's payload is built in one place; its line names the option


def test_hum_ac15_the_status_rows_name_the_reason_option() -> None:  # HUM-AC15, AC 10
    line = status_resume_command("demo", "demo/T-1", ["proceed", "retry", "stop"])
    assert named_reason(line) and "--decision <proceed|retry|stop>" in line
    assert "--reason" not in status_resume_command("demo", "demo/T-1")


def test_hum_ac15_the_lines_of_several_pending_gates_name_the_reason_option(repo: Path) -> None:  # HUM-AC15, AC 10
    from .test_map_concurrent_pauses import paused

    spec, ex, out = paused(repo)
    assert out.exit_code is ExitCode.PAUSED, out.message
    assert named_reason(out.payload["resume"])
    neither = resume(spec, "M-1", repo, registry(ex), decision="retry", settings=NO_SLEEP)
    assert neither.reason == "unit_missing" and len(neither.refusals) == 2
    assert all(named_reason(line) for line in neither.refusals), neither.refusals


def test_hum_ac15_the_usage_limit_command_names_no_decision_and_no_reason(repo: Path) -> None:  # HUM-AC15, AC 10
    ex = standin("claude", steps=[refused(time.time() + 3600, error_kind="model")] * 3, judges=[judge()])
    assert go(repo, ex).exit_code is ExitCode.PAUSED
    line = _pause_payload(repo)["resume"]
    assert "--decision" not in line and "--reason" not in line
    assert _plain(repo, ex).exit_code is ExitCode.PAUSED
