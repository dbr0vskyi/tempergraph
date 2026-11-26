"""The outcome record and the outcome measures (OUT-B18, OUT-B19, OUT-B20, OUT-B21, OUT-B7, PKG, OUT (moved))."""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any

import pytest

from tempergraph.catalog import Catalog
from tempergraph.constants import ExitCode
from tempergraph.executors.standins import standin
from tempergraph.run.outcome_record import verdict

from .conftest import hash_tree
from .test_cli import cli
from .test_run import (
    DRAFT,
    MET,
    NO_SLEEP,
    REVIEW,
    go,
    judge,
    records,
    registry,
    verdict_block,
    with_outcome_spec,
)

MET2 = verdict_block("MET", "MET")


def c(status: str, cls: str = "judge", severity: str = "blocker") -> dict[str, Any]:
    return {"status": status, "class": cls, "severity": severity}


@pytest.mark.parametrize(("rows", "want"), [
    ([c("MET"), c("signed", "person")], "met"),
    ([c("MET"), c("UNMET", severity="warning")], "met_with_open"),
    ([c("MET"), c("not_verified", "none")], "met_with_open"),
    ([c("PARTIAL"), c("UNVERIFIABLE")], "unmet"),
    ([c("MET"), c("UNVERIFIABLE")], "needs_person"),
    ([c("MET"), c("not_judged", "person")], "needs_person"),
    ([c("MET"), c("declined", "person")], "unmet"),
])
def test_verdict_rules(rows: list[dict[str, Any]], want: str) -> None:  # OUT-B18, OUT-B19
    assert verdict(rows) == want
    assert verdict(rows, reached=False) == "not_reached"


def ledger(repo: Path) -> list[dict[str, Any]]:
    return [json.loads(x) for x in (repo / ".tempergraph" / "ledger.jsonl").read_text().splitlines()]


def test_a_finished_run_records_its_outcome(repo: Path) -> None:
    spec = with_outcome_spec()
    ex = standin("claude", steps=[DRAFT, REVIEW], judges=[judge(MET2), judge(MET), judge(MET, sid="o")])
    assert go(repo, ex, spec, task="O-1").exit_code is ExitCode.FINISHED
    rec = [r for r in records(repo, "O-1") if r["kind"] == "outcome"]
    assert len(rec) == 1 and rec[0]["verdict"] == "met" and rec[0]["revision"] == 1
    crit = rec[0]["criteria"][0]
    assert crit["id"] == "rn-complete" and crit["status"] == "MET" and crit["trust"] == "uncalibrated"
    assert {(i["unit"], i["id"]) for i in rec[0]["intermediate"]} >= {("draft", "rn-faithful"), ("review", "rv-ok")}
    seg = [r for r in ledger(repo) if r["kind"] == "run_segment"]
    assert seg[-1]["outcome"]["verdict"] == "met"


def test_sign_off_is_graded_by_its_caller(repo: Path) -> None:  # OUT-B4
    spec = with_outcome_spec("person")
    ex = standin("claude", steps=[DRAFT, REVIEW], judges=[judge(MET2), judge(MET)])
    assert go(repo, ex, spec, task="O-2").exit_code is ExitCode.PAUSED
    assert [r for r in ledger(repo) if r["kind"] == "run_segment"][-1]["outcome"]["verdict"] == "needs_person"
    from tempergraph.run.runner import resume

    caller = {"kind": "person", "confidence": "observed"}
    import dataclasses

    out = resume(spec, "O-2", repo, registry(ex), decision="proceed",
                 settings=dataclasses.replace(NO_SLEEP, caller=caller))
    assert out.exit_code is ExitCode.FINISHED, out.message
    rec = [r for r in records(repo, "O-2") if r["kind"] == "outcome"][-1]
    assert rec["verdict"] == "met" and rec["criteria"][0]["status"] == "signed"
    assert rec["criteria"][0]["grader"]["kind"] == "person" and rec["criteria"][0]["trust"] == "human"


def test_a_run_that_ends_before_the_gate_is_not_reached(repo: Path) -> None:
    spec = with_outcome_spec()
    ex = standin("claude", steps=[DRAFT], judges=[judge(verdict_block("UNVERIFIABLE", "MET"))])
    assert go(repo, ex, spec, task="O-3").exit_code is ExitCode.PAUSED
    assert not [r for r in records(repo, "O-3") if r["kind"] == "outcome"]
    assert [r for r in ledger(repo) if r["kind"] == "run_segment"][-1]["outcome"]["verdict"] == "not_reached"


def test_out_ac10_what_counts_as_an_escape_and_the_escape_rate(repo: Path) -> None:
    # OUT-AC10, OUT-B19, OUT-B26, task AC 7: the ledger rows are the engine's own, from `go` and `rerun`
    from tempergraph.run.outcome_record import _latest, escape_threads, measures

    spec = with_outcome_spec()
    cat = Catalog(specs={"demo": spec})
    for task in ("X-1", "X-2", "X-3"):
        ex = standin("claude", steps=[DRAFT, REVIEW], judges=[judge(MET2), judge(MET), judge(MET, sid="o")])
        code, _, err = cli(repo, ex, "run", "demo", "notes", "--task-id", task, catalog=cat)
        assert code == 0, err
    ex = standin("claude", steps=[REVIEW], judges=[judge(MET), judge(MET, sid="o")])
    code, _, err = cli(repo, ex, "rerun", "demo", "X-1", "--from", "review", catalog=cat)
    assert code == 0, err
    rows = ledger(repo)
    reruns = {r["thread_id"] for r in rows if r.get("kind") == "intervention" and r.get("cause") == "rerun"}
    assert reruns == {"demo/X-1"}
    latest = _latest(rows, "demo")
    assert {t: r["outcome"]["verdict"] for t, r in latest.items()} == {
        "demo/X-1": "met", "demo/X-2": "met", "demo/X-3": "met", "demo/X-1~r1": "met"}  # the rerun is its own thread

    def labelled(**verdicts: str) -> dict[str, dict[str, Any]]:
        return {t: {**r, "outcome": {**r["outcome"], "verdict": verdicts.get(t.split("/")[1].replace("-", "_"),
                                                                           r["outcome"]["verdict"])}}
                for t, r in latest.items()}

    later = [{"kind": "outcome_later", "thread_id": "demo/X-2", "entry": {"reviews": {"changes_requested": 1}}},
             {"kind": "outcome_later", "thread_id": "demo/X-3", "entry": {"reviews": {}, "files": 2}}]
    # a rerun counts a `met` run
    assert escape_threads(latest, rows + later, reruns) == {"demo/X-1", "demo/X-2", "demo/X-3"}
    assert escape_threads(latest, rows, reruns) == {"demo/X-1"}
    # a `met_with_open` run is an escape by a rerun only, never by a change request or a follow-up commit on a file
    open_ = labelled(X_1="met_with_open", X_2="met_with_open", X_3="met_with_open")
    assert escape_threads(open_, rows + later, reruns) == {"demo/X-1"}
    # the escape rate counts `met_with_open` runs in its denominator (OUT-B19)
    ledger_path = repo / ".tempergraph" / "ledger.jsonl"
    ledger_path.write_text("".join(json.dumps(r) + "\n" for r in [*rows, *later]), encoding="utf-8")
    (rev,) = measures(spec, ledger_path)["revisions"]
    assert rev["n"] == 4 and rev["escapes"] == 3 and rev["escape_rate"] == 0.75
    relabelled = [({**r, "outcome": {**r["outcome"], "verdict": "met_with_open"}}
                   if r.get("kind") == "run_segment" and r.get("thread_id") == "demo/X-3" else r)
                  for r in [*rows, *later]]
    ledger_path.write_text("".join(json.dumps(r) + "\n" for r in relabelled), encoding="utf-8")
    (rev,) = measures(spec, ledger_path)["revisions"]
    assert rev["met_rate"] == 1.0 and rev["escapes"] == 2 and rev["escape_rate"] == 0.5


def test_outcome_show_and_candidates(repo: Path) -> None:  # OUT-B18, OUT-B19, OUT-B20, OUT-B21, C13
    spec = with_outcome_spec()
    cat = Catalog(specs={"demo": spec})
    for task in ("O-4", "O-5"):
        ex = standin("claude", steps=[DRAFT, REVIEW], judges=[judge(MET2), judge(MET), judge(MET, sid="o")])
        code, _, err = cli(repo, ex, "run", "demo", "notes", "--task-id", task, catalog=cat)
        assert code == 0, err
    ex = standin("claude", steps=[REVIEW], judges=[judge(MET), judge(MET, sid="o")])
    code, _, err = cli(repo, ex, "rerun", "demo", "O-4", "--from", "review", catalog=cat)
    assert code == 0, err
    before = hash_tree(repo / ".tempergraph")
    code, doc, _ = cli(repo, None, "outcome", "show", "demo", "--runs", catalog=cat)
    # OUT-B13, OUT-B14 via run/outcome_trust: counts per trust over every criterion, final and intermediate; no
    # check has fixtures and no judge is calibrated, so all four are uncalibrated and nothing is covered
    assert code == 0 and doc["outcome"]["trust_profile"] == {"uncalibrated": 4}
    assert [c["covered"] for c in doc["outcome"]["coverage"]] == [False]
    rev = doc["runs"][0]
    assert rev["revision"] == 1 and rev["n"] == 3 and rev["met_rate"] == 1.0
    assert rev["escapes"] == 1 and rev["weak_blockers"] == ["rn-complete"] and rev["corrected"] is None
    assert rev["upstream_agreement"]["rn-complete"]["n"] == 3
    code, doc, _ = cli(repo, None, "outcome", "candidates", "demo", "--window", "30", catalog=cat)
    assert code == 0 and [x["signal"] for x in doc["candidates"]] == ["escape"]
    assert doc["candidates"][0]["threads"] == ["demo/O-4"]
    assert hash_tree(repo / ".tempergraph") == before
    code, _, err = cli(repo, None, "outcome", "show", "demo", "--runs", "soon", catalog=cat)
    assert code == 2 and "expected all" in err
