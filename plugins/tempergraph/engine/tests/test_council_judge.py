"""The judge grades the council's decision, a switch routes on its outcome, and a chair-only retry runs the chair
alone (CNL-B4, CNL-B5, CNL-B7, CNL-B12, CNL-AC7; task AC 5)."""

from __future__ import annotations

import dataclasses
from pathlib import Path
from typing import Any

from tempergraph.api import Gate, Judge, Step, Switch
from tempergraph.constants import ExitCode
from tempergraph.contracts import FlowSpec

from .fixtures.workflows import crit
from .test_council_run import UNIT, Crew, blk, chair_text, council_wf, go, recs
from .test_run import verdict_block


def by_outcome(view: Any) -> str:
    return str(view.values.get("tally.outcome", ""))


def test_cnl_ac7_the_judge_grades_decision_with_positions_among_its_references(repo: Path) -> None:  # CNL-AC7 (CNL-B4)
    ex = Crew(chair=chair_text("a and b differ on cost"))
    out = go(repo, council_wf(), ex)
    assert out.exit_code is ExitCode.FINISHED, out.message
    (judge,) = [r for r in ex.requests if r.kind == "judge"]
    assert judge.session_key == f"{UNIT}.1.judge"
    members = {r.session_key for r in ex.requests if r.kind in ("member", "chair")}
    assert judge.session_key not in members  # a session of its own, none of the members
    references, _, rest = judge.prompt.partition("## What to grade")
    subject = rest.split("## Criteria")[0]
    assert "- decision: Synthesis." in subject and "- positions:" not in subject  # the subject is `decision` alone
    assert "### positions" in references and "a-view" in references and "Member A" in references  # a reference, under labels
    views = ex.views[judge.session_key]
    assert not {"Edit", "Write", "Bash"} & set(views.tools)  # a fresh, read-only session


def test_cnl_ac7_a_chair_answer_without_dissent_while_positions_differ_fails_the_built_in_check(repo: Path) -> None:  # CNL-AC7 (CNL-B12)
    ex = Crew(chair=[chair_text(""), chair_text("a and b differ on cost")])
    out = go(repo, council_wf(), ex)
    assert out.exit_code is ExitCode.FINISHED, out.message
    assert [r.session_key for r in ex.requests if r.kind == "judge"] == [f"{UNIT}.2.judge"]  # attempt 1 reached no judge
    verdicts = [(r["verdict"], r.get("token")) for r in recs(repo, "gate")]
    assert verdicts[0] == ("RETRY", "RETRY") and verdicts[-1][0] == "PROCEED"
    assert [k for k in ex.sessions if k.startswith(f"{UNIT}.2.member.")]  # `retry_scope: all` asks every member again


def test_a_chair_answer_that_names_dissent_passes_the_check_when_positions_agree(repo: Path) -> None:  # CNL-B12
    same = Crew(default=lambda name, rnd: blk("one view", round=rnd), chair=chair_text(""))
    assert go(repo, council_wf(), same).exit_code is ExitCode.FINISHED
    assert [r.session_key for r in same.requests if r.kind == "judge"] == [f"{UNIT}.1.judge"]


def routed_wf() -> Any:
    spec = council_wf(mode="vote", options=["ship", "hold"], chair=None)
    ok = Gate(judge=Judge(stance="V."), criteria=[crit("c-s")])
    units = {**spec.units, "route": Switch(predicate=by_outcome, arms={"ship": "shipit", "hold": "holdit"}, default="hold"),
             "shipit": Step(prompt="Ship it", tools=["read"], gate=ok),
             "holdit": Step(prompt="Hold it", tools=["read"], gate=ok)}
    return dataclasses.replace(spec, order=(UNIT, "route", "shipit", "holdit"), units=units,
                               flow={"shipit": FlowSpec(next="finalizer")})


def test_cnl_ac7_a_switch_on_the_tally_outcome_picks_its_arm_with_no_model_call(repo: Path) -> None:  # CNL-AC7 (CNL-B5)
    ex = Crew(default=lambda name, rnd: blk(f"{name}-view", choice="ship", round=rnd))
    out = go(repo, routed_wf(), ex)
    assert out.exit_code is ExitCode.FINISHED, out.message
    (pick,) = recs(repo, "route")
    assert pick["unit"] == "route" and pick["arm"] == "ship" and pick["target"] == "shipit"
    assert not [k for k in ex.sessions if k.startswith("route.")]  # the switch ran no session
    assert [k for k in ex.sessions if k.startswith("shipit.") and k.endswith(".step")]
    assert not [k for k in ex.sessions if k.startswith("holdit.")]


def test_cnl_ac7_under_retry_scope_chair_a_retry_runs_only_the_chair_with_the_judges_notes(repo: Path) -> None:  # CNL-AC7 (CNL-B7)
    ex = Crew(chair=[chair_text("a and b differ"), chair_text("a and b differ on cost")],
              judges=[verdict_block("UNMET"), verdict_block("MET")])
    out = go(repo, council_wf(retry_scope="chair"), ex)
    assert out.exit_code is ExitCode.FINISHED, out.message
    members = [k for k in ex.sessions if ".member." in k]
    assert sorted(members) == [f"{UNIT}.1.member.{n}.0" for n in "abc"]  # the second attempt asked no member
    chairs = [r for r in ex.requests if r.kind == "chair"]
    assert [r.session_key for r in chairs] == [f"{UNIT}.1.chair", f"{UNIT}.2.chair"]
    second = chairs[1].prompt
    assert "The reviewer did not accept" in second and "\n- " in second.split("The reviewer did not accept")[1]  # the notes
    assert "a-view" in second and "c-view" in second  # the members' recorded positions are reused
    assert [r.session_key for r in ex.requests if r.kind == "judge"] == [f"{UNIT}.1.judge", f"{UNIT}.2.judge"]
    rounds = recs(repo, "council_round")
    assert len(rounds) == 1  # the retry made no round of its own
    assert len(recs(repo, "council_tally")) == 1


def test_under_retry_scope_all_a_retry_runs_every_member_again(repo: Path) -> None:  # CNL-AC7 (CNL-B7)
    ex = Crew(judges=[verdict_block("UNMET"), verdict_block("MET")])
    assert go(repo, council_wf(retry_scope="all"), ex).exit_code is ExitCode.FINISHED
    assert sorted(k for k in ex.sessions if ".2.member." in k) == [f"{UNIT}.2.member.{n}.0" for n in "abc"]
