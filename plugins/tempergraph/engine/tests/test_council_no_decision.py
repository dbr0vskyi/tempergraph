"""No decision, member failures and the person's answer (CNL-B13, CNL-B15, CNL-AC3; HUM-B7, HUM-B12, ASK-B8; task AC 3)."""

from __future__ import annotations

import dataclasses
from pathlib import Path
from typing import Any

from tempergraph.constants import ExitCode
from tempergraph.contracts import InfraCause, SessionResult, Usage
from tempergraph.run import council as cn
from tempergraph.run.runner import resume

from .test_council_run import NO_SLEEP, UNIT, Crew, blk, council_wf, go, recs, registry

OPTIONS = ["ship", "hold"]


def vote_wf(**fields: Any) -> Any:
    return council_wf(mode="vote", options=OPTIONS, chair=None, **fields)


def split(**choices: str) -> Crew:
    """A crew whose members each vote as `choices` says (a name to its choice)."""
    return Crew(default=lambda name, rnd: blk(f"{name}-view", choice=choices[name], round=rnd))


def test_cnl_ac3_a_vote_that_misses_its_rule_pauses_as_an_escalation_with_positions_and_tally(repo: Path) -> None:  # CNL-AC3 (CNL-B13)
    ex = split(a="ship", b="hold", c="abstain")  # one vote each way: a tie, with a valid answer from every member
    out = go(repo, vote_wf(), ex)
    assert out.exit_code is ExitCode.PAUSED, out.message
    p = out.payload
    assert p["kind"] == "escalation" and p["reason"] == "no_decision"
    assert set(p["positions"]) == {"Member A", "Member B", "Member C"}
    assert p["tally"]["outcome"] == "no_decision" and p["tally"]["counts"] == {"ship": 1, "hold": 1}
    assert "answer:decision=<option>" in p["decisions"] and p["options"] == OPTIONS
    assert not ex.of("chair")  # no decision, no rationale
    (tally,) = recs(repo, "council_tally")
    assert tally["outcome"] == "no_decision" and tally["chosen_by"] == "engine"


def test_cnl_ac3_a_person_answers_decision_and_it_is_recorded_as_chosen_by_a_person(repo: Path) -> None:  # CNL-AC3 (CNL-B13, ASK-B8)
    ex = split(a="ship", b="hold", c="abstain")
    assert go(repo, vote_wf(), ex).exit_code is ExitCode.PAUSED
    out = resume(vote_wf(), "C-1", repo, registry(Crew()), settings=dataclasses.replace(NO_SLEEP, answers={"decision": "hold"}))
    assert out.exit_code is ExitCode.FINISHED, out.message
    rows = recs(repo, "council_tally")
    assert [(r["outcome"], r["chosen_by"]) for r in rows] == [("no_decision", "engine"), ("hold", "person")]


def test_an_answer_outside_the_options_is_refused_and_the_pause_stays(repo: Path) -> None:  # CNL-AC3 (CNL-B13)
    ex = split(a="ship", b="hold", c="abstain")
    assert go(repo, vote_wf(), ex).exit_code is ExitCode.PAUSED
    for bad in ({"decision": "maybe"}, {"decision": ""}, {"other": "ship"}):
        out = resume(vote_wf(), "C-1", repo, registry(Crew()), settings=dataclasses.replace(NO_SLEEP, answers=bad))
        assert out.exit_code is ExitCode.USAGE, bad
    ok = resume(vote_wf(), "C-1", repo, registry(Crew()), settings=dataclasses.replace(NO_SLEEP, answers={"decision": "ship"}))
    assert ok.exit_code is ExitCode.FINISHED


def test_cnl_ac3_a_round_below_its_quorum_is_no_decision(repo: Path) -> None:  # CNL-AC3 (CNL-B11, CNL-B13)
    ex = Crew(script={("c", 0): ["garbled", "still garbled"]})  # the re-ask fails too: a spoiled answer
    out = go(repo, council_wf(), ex)
    assert out.exit_code is ExitCode.PAUSED and out.payload["reason"] == "no_decision", out.message
    (row,) = recs(repo, "council_round")
    assert (row["answered"], row["spoiled"], row["missing"]) == (2, 1, 0)
    assert ex.of("member_reask") == [f"{UNIT}.1.member_reask.c.0"]  # asked once more, not twice
    assert not ex.of("chair")


LABELS = cn.label_map(["a", "b", "c"], "demo/C-1/decide/1")  # the order of the first attempt of thread demo/C-1
CYCLE = ["Member A", "Member B", "Member C"]


def ranking_replies(by: Any) -> dict[tuple[str, int], list[Any]]:
    """The ranking pass of each member (the stage after the last round): `by(own label)` lists the peers' labels."""
    return {(n, 1): [lambda req, n=n: blk("ranked", ranking=by(LABELS[n]))] for n in "abc"}  # type: ignore[misc]


def test_cnl_ac3_a_tied_rank_is_no_decision_after_both_breaks(repo: Path) -> None:  # CNL-AC3 (CNL-B12, CNL-B13)
    def rotate(own: str) -> list[str]:  # A ranks B first, B ranks C first, C ranks A first: every one has one point
        i = CYCLE.index(own)
        return [CYCLE[(i + 1) % 3], CYCLE[(i + 2) % 3]]

    ex = Crew(script=ranking_replies(rotate))
    out = go(repo, council_wf(mode="rank", chair=None), ex)
    assert out.exit_code is ExitCode.PAUSED and out.payload["reason"] == "no_decision", out.message
    assert sorted(k for k in ex.sessions if k.endswith(".member.a.1") or k.endswith(".member.b.1")
                  or k.endswith(".member.c.1")) == [f"{UNIT}.1.member.{n}.1" for n in "abc"]  # one ranking pass each
    (tally,) = recs(repo, "council_tally")
    assert tally["mode"] == "rank" and tally["outcome"] == "no_decision" and tally["rule"] == "borda"
    assert out.payload["options"] == CYCLE  # a person answers with a label


def test_cnl_ac3_a_borda_winner_is_the_outcome_of_a_chairless_rank(repo: Path) -> None:  # CNL-AC3 (CNL-B12, CNL-B10)
    def favour_a(own: str) -> list[str]:
        return [x for x in CYCLE if x != own]  # everyone puts Member A first

    ex = Crew(script=ranking_replies(favour_a))
    out = go(repo, council_wf(mode="rank", chair=None), ex)
    assert out.exit_code is ExitCode.FINISHED, out.message
    (tally,) = recs(repo, "council_tally")
    assert tally["outcome"] == "Member A" and tally["counts"] == {"Member A": 2, "Member B": 1, "Member C": 0}
    assert not ex.of("chair")  # a chairless rank writes the outcome itself


def test_cnl_ac3_with_retry_the_council_runs_again_and_charges_the_retry_budget(repo: Path) -> None:  # CNL-AC3 (CNL-B13)
    script: dict[tuple[str, int], list[Any]] = {
        ("a", 0): [blk("a", choice="ship"), blk("a", choice="ship")],
        ("b", 0): [blk("b", choice="hold"), blk("b", choice="ship")],
        ("c", 0): [blk("c", choice="abstain"), blk("c", choice="ship")]}
    ex = Crew(script=script)
    out = go(repo, vote_wf(on_no_decision="retry"), ex)
    assert out.exit_code is ExitCode.FINISHED, out.message
    assert ex.of("member")[:3] == [f"{UNIT}.1.member.{n}.0" for n in "abc"]
    assert sorted(k for k in ex.sessions if ".2.member." in k) == [f"{UNIT}.2.member.{n}.0" for n in "abc"]
    budget = [r for r in recs(repo, "budget") if r["counter"] == "retries"]
    assert [r["used"] for r in budget] == [1]
    assert [r["outcome"] for r in recs(repo, "council_tally")] == ["no_decision", "ship"]


def test_cnl_ac3_with_stop_the_run_stops(repo: Path) -> None:  # CNL-AC3 (CNL-B13)
    out = go(repo, vote_wf(on_no_decision="stop"), split(a="ship", b="hold", c="abstain"))
    assert out.exit_code not in (ExitCode.FINISHED, ExitCode.PAUSED) and out.reason == "no_decision", out.message


def broken() -> SessionResult:
    return SessionResult(ok=False, infra_cause=InfraCause.BROKEN_PIPE, usage=Usage())


def test_cnl_ac3_a_member_failing_on_infrastructure_counts_missing_and_the_round_closes(repo: Path) -> None:  # CNL-AC3 (CNL-B15)
    ex = Crew(script={("c", 0): [broken()] * 3})  # every infra try of one member fails
    out = go(repo, council_wf(quorum=2), ex)
    assert out.exit_code is ExitCode.FINISHED, out.message
    (row,) = recs(repo, "council_round")
    assert (row["answered"], row["spoiled"], row["missing"]) == (2, 0, 1)
    assert ex.sessions[f"{UNIT}.1.member.c.0"] == 3  # tried three times, outside the retry budget
    assert ex.of("chair") == [f"{UNIT}.1.chair"]


def test_cnl_ac3_below_quorum_after_an_infra_failure_is_no_decision(repo: Path) -> None:  # CNL-AC3 (CNL-B15, CNL-B13)
    out = go(repo, council_wf(), Crew(script={("c", 0): [broken()] * 3}))  # the default quorum is every member
    assert out.exit_code is ExitCode.PAUSED and out.payload["reason"] == "no_decision", out.message


def test_cnl_ac3_every_member_failing_on_infrastructure_is_an_infra_failure_and_no_pause(repo: Path) -> None:  # CNL-AC3 (CNL-B15)
    ex = Crew(script={(n, 0): [broken()] * 3 for n in "abc"})
    out = go(repo, council_wf(), ex)
    assert out.exit_code is ExitCode.BUDGET_OR_INFRA and out.reason == "infra", out.message
    assert not out.payload and not ex.of("chair") and not ex.of("judge")  # no pause, no later session
