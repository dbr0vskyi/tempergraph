"""Ask units, event waits and their deadlines (ASK-B5 to ASK-B9, HUM-B4, FLX-B8)."""

from __future__ import annotations

import dataclasses
import json
from datetime import UTC, datetime, timedelta
from pathlib import Path
from typing import Any

from tempergraph.api import Ask, Gate, Judge, Question, Routing, Script, Step, Wait, Workflow
from tempergraph.constants import ExitCode
from tempergraph.durability.status import row
from tempergraph.executors.standins import answer, standin
from tempergraph.model.validate import errors, validate
from tempergraph.run import asking
from tempergraph.run.runner import RunSettings, resume, start
from tempergraph.store.layout import run_dir, state_root_path

from .fixtures.workflows import crit, named
from .test_run import MET, registry

NO_SLEEP = RunSettings(sleep=lambda s: None)
PLAN = answer("Planned.", session_id="s-plan")
JUDGE = answer(MET, tools=("Read",), session_id="j")
CAPS = {"claude": standin("claude").capabilities()}


def approved(value: str) -> bool:
    return value in ("yes", "no")


def ticket_ok(answers: dict[str, Any]) -> list[str]:
    return [] if str(answers.get("ticket", "")).startswith("PRJ-") else ["ticket must start with PRJ-"]


def write_questions(ctx: Any) -> dict[str, str]:
    (ctx.workdir / "questions.md").write_text("- scope: Which service is in scope?\n- owner: Who owns it?\n")
    return {"open_questions": "questions.md"}


def write_bad_questions(ctx: Any) -> dict[str, str]:
    (ctx.workdir / "questions.md").write_text("no list here\n")
    return {"open_questions": "questions.md"}


def plan_step(prompt: str = "Plan for {request}") -> Any:
    return Step(prompt=prompt, tools=["read"], gate=Gate(judge=Judge(stance="V."), criteria=[crit("c1")]))


def asking_wf(**ask: Any) -> Any:
    qs = [Question("env", "Which environment?", kind="choice", choices=["staging", "prod"]),
          Question("ticket", "Which ticket?"),
          Question("notify", "Notify the channel?", kind="bool", required=False, default=False)]
    units = {"details": Ask(questions=qs, **ask), "plan": plan_step()}
    return named(Workflow(order=["details", "plan"], units=units, issue_repository="acme/x",
                          routing=Routing(description="Ask, then plan")))


def waiting_wf(**wait: Any) -> Any:
    units = {"signoff": Wait(event="approved", check=approved, **wait), "plan": plan_step(),
             "manual": plan_step("Write the manual brief for {request}")}
    return named(Workflow(order=["signoff", "plan", "manual"], units=units, issue_repository="acme/x",
                          routing=Routing(description="Wait, then plan")))


def ex() -> Any:
    return standin("claude", steps=[PLAN, PLAN], judges=[JUDGE, JUDGE])


def begin(repo: Path, spec: Any, e: Any = None, task: str = "A-1") -> Any:
    return start(spec, task, {"request": "x"}, repo, registry(e or ex()), NO_SLEEP)


def again(repo: Path, spec: Any, e: Any = None, task: str = "A-1", decision: str | None = None, **kw: Any) -> Any:
    return resume(spec, task, repo, registry(e or ex()), decision=decision,
                  settings=dataclasses.replace(NO_SLEEP, **kw))


def recs(repo: Path, kind: str, task: str = "A-1") -> list[dict[str, Any]]:
    p = run_dir(state_root_path(repo), "demo", task) / "run.jsonl"
    return [r for r in map(json.loads, p.read_text().splitlines()) if r["kind"] == kind]


def answers_file(repo: Path, task: str = "A-1") -> dict[str, Any]:
    return json.loads(asking.answers_path(run_dir(state_root_path(repo), "demo", task), "details").read_text())


# -- the ask unit ---------------------------------------------------------------------------------------


def test_an_ask_pauses_with_its_questions_and_no_session(repo: Path) -> None:
    e = ex()
    out = begin(repo, asking_wf(), e)
    assert out.exit_code is ExitCode.PAUSED and out.payload["kind"] == "input", out.message
    assert [q["name"] for q in out.payload["questions"]] == ["env", "ticket", "notify"]
    assert out.payload["questions"][0]["choices"] == ["staging", "prod"]
    assert "answer:<name>=<value>" in out.payload["resume"] and e.calls == []


def test_typed_answers_follow_the_table(repo: Path) -> None:  # ASK-B1, ASK-AC1
    spec = asking_wf()
    begin(repo, spec)
    bad = again(repo, spec, answers={"env": "dev"})
    assert bad.exit_code is ExitCode.USAGE and "staging, prod" in bad.message
    assert not asking.answers_path(run_dir(state_root_path(repo), "demo", "A-1"), "details").exists()
    part = again(repo, spec, answers={"env": "staging"})
    assert part.exit_code is ExitCode.PAUSED and part.payload["missing"] == ["ticket"]
    assert answers_file(repo)["answers"] == {"env": "staging"}
    early = again(repo, spec, decision="proceed")
    assert early.exit_code is ExitCode.USAGE and "ticket" in early.message
    done = again(repo, spec, decision="proceed", answers={"ticket": "PRJ-12"})
    assert done.exit_code is ExitCode.FINISHED, done.message
    assert answers_file(repo) == {"schema_version": 1, "unit": "details", "complete": True,
                                  "answers": {"env": "staging", "ticket": "PRJ-12", "notify": False}}


def test_a_complete_set_continues_without_proceed_and_stop_ends_the_run(repo: Path) -> None:
    spec = asking_wf()
    begin(repo, spec)
    done = again(repo, spec, answers={"env": "prod", "ticket": "PRJ-1"})
    assert done.exit_code is ExitCode.FINISHED, done.message
    begin(repo, spec, task="A-2")
    stop = again(repo, spec, task="A-2", decision="stop")
    assert stop.exit_code is ExitCode.STOPPED


def test_a_refused_word_and_an_unknown_question(repo: Path) -> None:
    spec = asking_wf()
    begin(repo, spec)
    assert again(repo, spec, decision="retry").exit_code is ExitCode.USAGE
    assert again(repo, spec, answers={"colour": "red"}).exit_code is ExitCode.USAGE
    assert again(repo, spec).reason == "decision_missing"


def test_the_authors_check_keeps_the_run_asking(repo: Path) -> None:
    spec = asking_wf(check=ticket_ok)
    begin(repo, spec)
    held = again(repo, spec, answers={"env": "prod", "ticket": "12"})
    assert held.exit_code is ExitCode.PAUSED and held.payload["check_problems"] == ["ticket must start with PRJ-"]
    assert again(repo, spec, answers={"ticket": "PRJ-12"}).exit_code is ExitCode.FINISHED


def test_answers_reach_later_steps_as_an_artifact_and_values(repo: Path) -> None:  # ASK-B3
    spec = asking_wf()
    spec = dataclasses.replace(spec, units={**spec.units, "plan": plan_step("Plan {request} from {answers}")})
    assert not errors(validate(spec, CAPS))
    e = ex()
    begin(repo, spec, e)
    again(repo, spec, e, answers={"env": "prod", "ticket": "PRJ-1"})
    step = next(c for c in e.calls if c.kind == "step")
    path = asking.answers_path(run_dir(state_root_path(repo), "demo", "A-1"), "details")
    assert str(path) in step.request.prompt


def test_questions_come_from_a_list_an_earlier_step_wrote(repo: Path) -> None:  # ASK-B2
    def wf(call: Any) -> Any:
        units = {"discover": Script(call=call, produces={"open_questions": "file"}, gate=Gate()),
                 "details": Ask(questions_from="open_questions"), "plan": plan_step()}
        return named(Workflow(order=["discover", "details", "plan"], units=units, issue_repository="acme/x",
                              routing=Routing(description="Ask what discovery left open")))

    out = begin(repo, wf(write_questions))
    assert out.exit_code is ExitCode.PAUSED and [q["name"] for q in out.payload["questions"]] == ["scope", "owner"]
    bad = begin(repo, wf(write_bad_questions), task="A-2")
    assert bad.exit_code is ExitCode.STOPPED and bad.reason == "ask" and recs(repo, "pause", "A-2") == []


def test_a_question_list_is_json_or_markdown_and_at_most_twenty() -> None:
    got = asking.from_list('[{"name": "env", "text": "Where?", "kind": "choice", "choices": ["a", "b"]}]')
    assert got[0].kind == "choice" and got[0].choices == ("a", "b")
    many = "\n".join(f"- q{i}: Question {i}?" for i in range(21))
    for text in (many, "[{\"name\": \"x\"}]", "- Bad Name: what?"):
        try:
            asking.from_list(text)
        except asking.AskFault:
            continue
        raise AssertionError(text)


def test_every_answer_kind_is_validated() -> None:
    def q(kind: str, **kw: Any) -> Any:
        return Question("a", "A?", kind=kind, **kw)

    assert asking.parse(q("number"), "12") == 12 and asking.parse(q("number"), "1.5") == 1.5
    assert asking.parse(q("bool"), "yes") is True and asking.parse(q("bool"), "no") is False
    assert asking.parse(q("choices", choices=["a", "b", "c"]), "a, c") == ["a", "c"]
    assert asking.parse(q("url"), "https://example.invalid/x") == "https://example.invalid/x"
    assert asking.parse(q("file"), "docs/a.md") == "docs/a.md"
    for kind, raw in (("number", "many"), ("bool", "perhaps"), ("url", "ftp://x"), ("file", "../x"),
                      ("file", "/etc/passwd"), ("text", " ")):
        try:
            asking.parse(q(kind), raw)
        except asking.AnswerRefused:
            continue
        raise AssertionError((kind, raw))


def test_partial_answers_survive_a_new_process_and_show_in_status(repo: Path) -> None:  # ASK-AC2, ASK-B4
    spec = asking_wf()
    begin(repo, spec)
    again(repo, spec, answers={"env": "staging"})
    r = row(state_root_path(repo), spec, "demo/A-1")
    (gate,) = r["pending_gates"]
    assert r["state"] == "paused" and (gate["kind"], gate["questions"], gate["unanswered"]) == ("input", 3, 1)
    assert [x["answered"] for x in recs(repo, "answers")] == [["env"]]
    assert again(repo, spec, answers={"ticket": "PRJ-9"}).exit_code is ExitCode.FINISHED
    assert answers_file(repo)["answers"]["env"] == "staging"


def test_validation_refuses_a_malformed_ask() -> None:  # ASK-AC3 for the placements this release has
    def codes(unit: Any, order: list[str] | None = None) -> set[str]:
        units = {"details": unit, "plan": plan_step()}
        spec = named(Workflow(order=order or ["details", "plan"], units=units, issue_repository="acme/x",
                              routing=Routing(description="x")))
        return {f.code for f in errors(validate(spec, CAPS))}

    assert "ask-invalid" in codes(Ask())
    assert "ask-invalid" in codes(Ask(questions=[Question("a", "A?")], questions_from="list"))
    assert "ask-from-unknown" in codes(Ask(questions_from="nothing"))
    assert "ask-question-invalid" in codes(Ask(questions=[Question("a", "A?", kind="choice")]))
    assert "person-unit-judge" in codes(Ask(questions=[Question("a", "A?")],
                                            gate=Gate(judge=Judge(stance="V."), criteria=[crit("c")])))
    assert "deadline-target-not-forward" in codes(Ask(questions=[Question("a", "A?")], deadline_s=5,
                                                     on_deadline="details"))
    assert "deadline-invalid" in codes(Ask(questions=[Question("a", "A?")], deadline_s=0))
    assert not codes(Ask(questions=[Question("a", "A?")], deadline_s=5, on_deadline="plan"))


# -- the wait unit --------------------------------------------------------------------------------------


def test_a_wait_is_not_passable_by_word(repo: Path) -> None:  # HUM-B4, CMP-AC3 (CMP-B14 wait)
    spec = waiting_wf()
    e = ex()
    out = begin(repo, spec, e)
    assert out.exit_code is ExitCode.PAUSED and out.payload["kind"] == "event_wait" and e.calls == []
    assert out.payload["resume"].endswith("--decision event:approved=<value>")
    for word in ("proceed", "retry", "event:approved=maybe", "event:merged=yes"):
        refused = again(repo, spec, e, decision=word)
        assert refused.exit_code is ExitCode.USAGE, word
    assert e.calls == [] and recs(repo, "human") == []
    done = again(repo, spec, e, decision="event:approved=yes")
    assert done.exit_code is ExitCode.FINISHED, done.message


def test_a_wait_needs_a_check_and_takes_no_judge() -> None:  # WFM-B4
    spec = waiting_wf()
    assert not errors(validate(spec, CAPS))
    judged = dataclasses.replace(spec.units["signoff"], gate=Gate(judge=Judge(stance="V."), criteria=[crit("c")]))
    spec = dataclasses.replace(spec, units={**spec.units, "signoff": judged})
    assert "person-unit-judge" in {f.code for f in errors(validate(spec, CAPS))}


# -- deadlines ------------------------------------------------------------------------------------------


def _expire(repo: Path, task: str = "A-1") -> None:
    """Move the pause's deadline into the past, as two days going by would."""
    import sqlite3

    from tempergraph.durability import engine_file

    db = engine_file.checkpoint_of(state_root_path(repo), "demo", task)
    past = (datetime.now(UTC) - timedelta(days=1)).isoformat(timespec="seconds")
    con = sqlite3.connect(db)
    try:
        for table, col in (("writes", "value"), ("checkpoints", "checkpoint")):
            for rowid, blob in con.execute(f"select rowid, {col} from {table}").fetchall():  # noqa: S608
                if isinstance(blob, bytes) and b"deadline_at" in blob:
                    start = blob.index(b"deadline_at")
                    at = blob.index(b"20", start)
                    con.execute(f"update {table} set {col} = ? where rowid = ?",  # noqa: S608
                                (blob[:at] + past.encode() + blob[at + len(past):], rowid))
        con.commit()
    finally:
        con.close()


def test_a_deadline_is_applied_only_on_request_and_only_when_passed(repo: Path) -> None:  # FLX-B3
    spec = waiting_wf(deadline_s=86400, on_deadline="escalate")
    out = begin(repo, spec)
    assert out.payload["deadline_at"] and out.payload["on_deadline"] == "escalate"
    (gate,) = row(state_root_path(repo), spec, "demo/A-1")["pending_gates"]
    assert gate["overdue"] is False
    early = again(repo, spec, apply_deadline=True)
    assert early.exit_code is ExitCode.USAGE and early.reason == "deadline_not_passed"
    _expire(repo)
    (gate,) = row(state_root_path(repo), spec, "demo/A-1")["pending_gates"]
    assert gate["overdue"] is True and gate["kind"] == "event_wait"  # nothing changes until it is applied
    esc = again(repo, spec, apply_deadline=True)
    assert esc.exit_code is ExitCode.PAUSED and esc.payload["kind"] == "escalation", esc.message
    assert esc.payload["reason"] == "deadline"
    done = again(repo, spec, decision="proceed")  # a person answers the escalation with the usual decisions
    assert done.exit_code is ExitCode.FINISHED, done.message


def test_a_deadline_can_stop_or_go_forward(repo: Path) -> None:
    stop = waiting_wf(deadline_s=60, on_deadline="stop")
    begin(repo, stop)
    _expire(repo)
    out = again(repo, stop, apply_deadline=True)
    assert out.exit_code is ExitCode.STOPPED and out.reason == "deadline"
    fwd = waiting_wf(deadline_s=60, on_deadline="manual")
    e = ex()
    begin(repo, fwd, e, task="A-2")
    _expire(repo, "A-2")
    out = again(repo, fwd, e, task="A-2", apply_deadline=True)
    assert out.exit_code is ExitCode.FINISHED, out.message
    assert [r["unit"] for r in recs(repo, "unit_entered", "A-2")] == ["signoff", "manual"]


def test_apply_deadline_without_a_deadline_is_refused(repo: Path) -> None:  # FLX-B6, FLX-B8
    spec = waiting_wf()
    begin(repo, spec)
    out = again(repo, spec, apply_deadline=True)
    assert out.exit_code is ExitCode.USAGE and recs(repo, "human") == []
