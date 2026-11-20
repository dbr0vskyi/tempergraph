"""The outcome record and the outcome measures (OUT §2.5, §2.6, OUT-B7, CON §2.14)."""

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
def test_verdict_rules(rows: list[dict[str, Any]], want: str) -> None:  # OUT §2.5
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


def test_outcome_show_and_candidates(repo: Path) -> None:  # OUT §2.5, §2.6, C13
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
    # OUT §2.3 via run/outcome_trust: counts per trust over every criterion, final and intermediate; no
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
