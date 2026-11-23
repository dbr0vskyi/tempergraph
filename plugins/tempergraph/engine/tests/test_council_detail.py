"""The run detail shows a council: its members, rounds, changes per round, the tally and the outcome
(CNL-B10, CNL-B12, CNL-AC6, RDD-B9, EVT-B13, EVT-B15; task AC 6)."""

from __future__ import annotations

import dataclasses
from pathlib import Path
from typing import Any

from tempergraph.constants import ExitCode
from tempergraph.observe.detail import detail
from tempergraph.run import council as cn
from tempergraph.run.runner import resume
from tempergraph.store.layout import state_root_path

from .test_council_no_decision import split
from .test_council_run import NO_SLEEP, UNIT, Crew, blk, council_wf, go, recs, registry
from .test_detail import fixture_run


def attempt_of(doc: dict[str, Any], unit: str = UNIT) -> dict[str, Any]:
    (u,) = [x for x in doc["units"] if x["name"] == unit]
    return u["visits"][-1]["attempts"][-1]


def vote_two_rounds() -> Crew:
    """Three members vote ship, ship, hold in round 0; in round 1 `c` changes to ship."""
    def default(name: str, rnd: int) -> str:
        choice = "ship" if name != "c" or rnd == 1 else "hold"
        return blk(f"{name}-view", choice=choice, round=rnd, changed=(name == "c" and rnd == 1))

    return Crew(default=default)


def test_cnl_ac6_the_detail_of_a_vote_council_shows_members_rounds_changes_tally_and_outcome(repo: Path) -> None:  # CNL-AC6 (CNL-B10, CNL-B12), RDD-B9
    spec = council_wf(mode="vote", options=["ship", "hold"], chair=None, rounds=1)
    out = go(repo, spec, vote_two_rounds())
    assert out.exit_code is ExitCode.FINISHED, out.message
    doc = detail(state_root_path(repo), spec, "demo/C-1")
    assert doc is not None
    c = attempt_of(doc)["council"]
    assert c["members"] == sorted("abc", key=lambda n: cn.label_map(list("abc"), "demo/C-1/decide/1")[n])  # label order
    assert [(r["round"], r["answered"], r["spoiled"], r["missing"], r["changed"]) for r in c["rounds"]] == [
        (0, 3, 0, 0, 0), (1, 3, 0, 0, 1)]
    assert c["outcome"] == "ship"
    assert c["tally"]["mode"] == "vote" and c["tally"]["rule"] == "majority" and c["tally"]["counts"] == {"ship": 3, "hold": 0}
    assert c["tally"]["chosen_by"] == "engine"


def test_cnl_ac6_the_member_reask_and_chair_sessions_stand_in_step_with_keys_naming_the_member_and_the_round(repo: Path) -> None:  # CNL-AC6, RDD-B9
    ex = Crew(script={("a", 0): ["no block", blk("fixed")]})
    spec = council_wf(rounds=1)
    assert go(repo, spec, ex).exit_code is ExitCode.FINISHED
    doc = detail(state_root_path(repo), spec, "demo/C-1")
    assert doc is not None
    sessions = attempt_of(doc)["step"]["sessions"]
    keys = {s["session_key"]: s["kind"] for s in sessions}
    assert keys[f"{UNIT}.1.member.a.0"] == "member" and keys[f"{UNIT}.1.member_reask.a.0"] == "member_reask"
    assert keys[f"{UNIT}.1.member.c.1"] == "member" and keys[f"{UNIT}.1.chair"] == "chair"
    assert len(sessions) == 3 * 2 + 1 + 1  # six member sessions, one re-ask and the chair
    judge_keys = [s["session_key"] for s in attempt_of(doc)["judge"]["sessions"]]
    assert judge_keys == [f"{UNIT}.1.judge"]  # the judge's session stands apart from the members'


def test_cnl_ac6_the_records_the_detail_reads_are_written(repo: Path) -> None:  # CNL-AC6 (EVT-B13, EVT-B15)
    spec = council_wf(mode="vote", options=["ship", "hold"], chair=None, rounds=1)
    assert go(repo, spec, vote_two_rounds()).exit_code is ExitCode.FINISHED
    rounds, (tally,) = recs(repo, "council_round"), recs(repo, "council_tally")
    assert [r["changed"] for r in rounds] == [0, 1] and all(r["unit"] == UNIT and r["attempt"] == 1 for r in rounds)
    assert tally["outcome"] == "ship" and tally["counts"] == {"ship": 3, "hold": 0} and tally["chosen_by"] == "engine"


def test_cnl_ac6_a_persons_answer_shows_as_the_outcome_chosen_by_a_person(repo: Path) -> None:  # CNL-AC6 (CNL-B13)
    spec = council_wf(mode="vote", options=["ship", "hold"], chair=None)
    assert go(repo, spec, split(a="ship", b="hold", c="abstain")).exit_code is ExitCode.PAUSED
    paused = detail(state_root_path(repo), spec, "demo/C-1")
    assert paused is not None and attempt_of(paused)["council"]["outcome"] == "no_decision"
    out = resume(spec, "C-1", repo, registry(Crew()), settings=dataclasses.replace(NO_SLEEP, answers={"decision": "hold"}))
    assert out.exit_code is ExitCode.FINISHED
    doc = detail(state_root_path(repo), spec, "demo/C-1")
    assert doc is not None
    c = attempt_of(doc)["council"]
    assert c["outcome"] == "hold" and c["tally"]["chosen_by"] == "person"


def test_cnl_ac6_an_attempt_of_another_unit_has_no_council_key(repo: Path) -> None:  # CNL-AC6 (RDD-B9)
    doc = fixture_run(repo)  # a workflow of plain steps
    for u in doc["units"]:
        for v in u["visits"]:
            assert all("council" not in a for a in v["attempts"])
