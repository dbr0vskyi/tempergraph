"""The tally and the Borda count, by rule, with no model (CNL-B3, CNL-B10, CNL-B12, CNL-AC2, CNL-AC3; task AC 3)."""

from __future__ import annotations

import ast
from collections.abc import Mapping, Sequence
from pathlib import Path

from tempergraph.run import council as cn

OPTS = ("ship", "hold")


def ballots(**choices: str) -> dict[str, cn.Answer]:
    """`a1="ship"` is a valid ballot, `s1="spoiled"` a spoiled one, `m1="missing"` a member that sent nothing."""
    out: dict[str, cn.Answer] = {}
    for name, choice in choices.items():
        if choice == "spoiled":
            out[name] = cn.spoiled("garbled")
        elif choice == "missing":
            out[name] = cn.missing()
        else:
            out[name] = cn.Answer(status="ok", position="p", choice=choice, confidence=0.5)
    return out


def tally(votes: Mapping[str, cn.Answer], rule: str = "majority", quorum: int | None = None) -> cn.Tally:
    return cn.tally_vote(votes, options=OPTS, rule=rule, quorum=quorum, members=len(votes))


def test_cnl_ac3_three_ship_two_hold_under_majority_is_ship() -> None:  # CNL-AC3, CNL-B3
    t = tally(ballots(a="ship", b="ship", c="ship", d="hold", e="hold"))
    assert t.outcome == "ship" and t.counts == {"ship": 3, "hold": 2} and t.rule == "majority" and t.reason is None


def test_cnl_ac3_three_ship_two_hold_under_supermajority_is_no_decision() -> None:  # CNL-AC3, CNL-B3
    t = tally(ballots(a="ship", b="ship", c="ship", d="hold", e="hold"), "supermajority")
    assert t.outcome == "no_decision" and t.reason == "rule"
    four = tally(ballots(a="ship", b="ship", c="ship", d="ship", e="hold"), "supermajority")
    assert four.outcome == "ship"  # 4 of 5 is at least two thirds
    exact = tally(ballots(a="ship", b="ship", c="hold"), "supermajority")
    assert exact.outcome == "ship"  # 2 of 3 is two thirds


def test_cnl_ac3_a_tie_with_a_spoiled_ballot_is_no_decision() -> None:  # CNL-AC3, CNL-B3
    t = tally(ballots(a="ship", b="ship", c="hold", d="hold", e="spoiled"), quorum=4)
    assert t.outcome == "no_decision" and t.reason == "tie" and t.spoiled == 1 and t.votes == 4


def test_cnl_ac3_plurality_ignores_abstentions() -> None:  # CNL-AC3, CNL-B3
    t = tally(ballots(a="ship", b="ship", c="hold", d="abstain", e="abstain"), "plurality")
    assert t.outcome == "ship" and t.abstained == 2 and t.votes == 3
    assert tally(ballots(a="ship", b="hold", c="abstain"), "plurality").outcome == "no_decision"  # a tie at the top


def test_cnl_ac3_a_round_below_quorum_is_no_decision() -> None:  # CNL-AC3, CNL-B3, CNL-B13
    t = tally(ballots(a="ship", b="ship", c="ship", d="ship", e="spoiled"), quorum=5)
    assert t.outcome == "no_decision" and t.reason == "quorum" and t.counts["ship"] == 4


def test_the_default_quorum_is_every_member_and_a_missing_member_counts_against_it() -> None:  # CNL-B13, CNL-B15
    t = tally(ballots(a="ship", b="ship", c="missing"))
    assert t.outcome == "no_decision" and t.reason == "quorum" and t.missing == 1
    assert tally(ballots(a="ship", b="ship", c="missing"), quorum=2).outcome == "ship"


def test_unanimous_needs_every_vote_for_one_option_and_at_least_one_vote() -> None:  # CNL-B3
    assert tally(ballots(a="ship", b="ship", c="abstain"), "unanimous").outcome == "ship"
    assert tally(ballots(a="ship", b="ship", c="hold"), "unanimous").outcome == "no_decision"
    assert tally(ballots(a="abstain", b="abstain"), "unanimous").outcome == "no_decision"


def test_an_abstention_is_a_valid_answer_for_the_quorum_but_no_vote() -> None:  # CNL-B3
    t = tally(ballots(a="ship", b="abstain", c="abstain"), "majority")
    assert t.votes == 1 and t.outcome == "ship"  # one vote, a majority of the votes cast


def test_changed_positions_are_counted_per_round() -> None:  # CNL-B12
    a = {"x": cn.Answer(status="ok", position="p", changed=True), "y": cn.Answer(status="ok", position="p", changed=False),
         "z": cn.spoiled("")}
    assert cn.changed_count(a) == 1
    assert cn.round_counts(a, ["x", "y", "z", "w"]) == {"answered": 2, "spoiled": 1, "missing": 1, "changed": 1}


def ranked(**rows: Sequence[str]) -> dict[str, cn.Answer]:
    return {n: cn.Answer(status="ok", position="p", ranking=tuple(r), confidence=0.5) for n, r in rows.items()}


LABELS = {"a": "Member A", "b": "Member B", "c": "Member C"}


def test_cnl_b12_a_borda_count_gives_k_minus_one_points_to_the_first_of_k() -> None:  # CNL-B12, CNL-AC3
    got = ranked(a=["Member B", "Member C"], b=["Member C", "Member A"], c=["Member B", "Member A"])
    t = cn.borda(got, labels=LABELS, confidences={"a": 0.5, "b": 0.5, "c": 0.5}, quorum=3)
    points = {row["label"]: row["points"] for row in t.ranking}
    assert points == {"Member A": 0, "Member B": 2, "Member C": 1}  # two peers ranked: 1 point for first, 0 for last
    assert t.outcome == "Member B" and t.rule == "borda"
    assert [row["label"] for row in t.ranking][0] == "Member B"


def test_ties_in_points_break_by_mean_confidence() -> None:  # CNL-B12
    got = ranked(a=["Member B", "Member C"], b=["Member C", "Member A"], c=["Member A", "Member B"])
    t = cn.borda(got, labels=LABELS, confidences={"a": 0.2, "b": 0.9, "c": 0.5}, quorum=3)
    assert {r["points"] for r in t.ranking} == {1}  # a three-way tie in points
    assert t.outcome == "Member B" and [r["label"] for r in t.ranking] == ["Member B", "Member C", "Member A"]


def test_a_tie_after_both_breaks_is_no_decision() -> None:  # CNL-B13
    got = ranked(a=["Member B", "Member C"], b=["Member C", "Member A"], c=["Member A", "Member B"])
    t = cn.borda(got, labels=LABELS, confidences={"a": 0.5, "b": 0.5, "c": 0.5}, quorum=3)
    assert t.outcome == "no_decision" and t.reason == "tie"
    assert [r["label"] for r in t.ranking] == ["Member A", "Member B", "Member C"]  # shown in label order


def test_a_rank_below_quorum_is_no_decision() -> None:  # CNL-B13
    got = {**ranked(a=["Member B", "Member C"], b=["Member C", "Member A"]), "c": cn.spoiled("x")}
    t = cn.borda(got, labels=LABELS, confidences={"a": 0.5, "b": 0.5, "c": 0.5}, quorum=3)
    assert t.outcome == "no_decision" and t.reason == "quorum"


def test_a_synthesis_outcome_is_the_chairs_answer_unless_the_quorum_is_missed() -> None:  # CNL-B12
    ok = {"a": cn.Answer(status="ok", position="p"), "b": cn.Answer(status="ok", position="q")}
    assert cn.synthesis_tally(ok, quorum=None, members=2).outcome == "synthesized"
    few = {"a": ok["a"], "b": cn.missing()}
    t = cn.synthesis_tally(few, quorum=None, members=2)
    assert t.outcome == "no_decision" and t.reason == "quorum"


def test_the_artifacts_decision_positions_and_tally_are_built() -> None:  # CNL-B10
    votes = ballots(a="ship", b="ship", c="hold")
    t = tally(votes, "majority")
    labels = {"a": "Member A", "b": "Member B", "c": "Member C"}
    text = cn.decision_text("vote", t, chair_text=None)
    assert "ship" in text and "majority" in text  # a chairless vote writes the outcome itself
    assert cn.decision_text("vote", t, chair_text="The rationale.") == "The rationale."  # the chair's answer
    history = [votes, votes]
    doc = cn.positions_json(history, labels)
    assert set(doc) == {"Member A", "Member B", "Member C"}
    assert doc["Member A"]["final"]["choice"] == "ship" and len(doc["Member A"]["rounds"]) == 2
    assert cn.tally_json(t)["outcome"] == "ship"


def test_cnl_ac2_the_tally_and_borda_code_makes_no_model_call() -> None:  # CNL-AC2 (CNL-B3, CNL-B12, CNL-B5)
    src = Path(cn.__file__).read_text()
    imported: set[str] = set()
    for node in ast.walk(ast.parse(src)):
        if isinstance(node, ast.Import):
            imported |= {a.name for a in node.names}
        elif isinstance(node, ast.ImportFrom):
            imported.add(node.module or "")
    banned = ("executors", "registry", "subprocess", "anthropic", "launcher", "nodes", "contracts.Executor")
    assert not [i for i in imported if any(b in i for b in banned)], imported
    for word in ("run_step", "run_judge", "SessionRequest", "Executor", "subprocess", "requests."):
        assert word not in src, word
