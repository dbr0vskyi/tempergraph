"""Escapes counted from reruns, `changes_requested` reviews and follow-up commits on files the run wrote (OUT-B19, OUT-B26)."""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any

from tempergraph.catalog import Catalog

from .test_cli import cli
from .test_run import with_outcome_spec


def outcome(verdict: str, criteria: list[dict[str, Any]] | None = None, revision: int = 1) -> dict[str, Any]:
    return {"revision": revision, "verdict": verdict, "criteria": criteria or [], "intermediate": [], "later": []}


def segment(wf: str, task: str, verdict: str = "met", criteria: list[dict[str, Any]] | None = None,
            revision: int = 1) -> dict[str, Any]:
    return {"kind": "run_segment", "workflow": wf, "thread_id": f"{wf}/{task}", "ts": "2999-01-01T00:00:00+00:00",
            "outcome": outcome(verdict, criteria, revision)}


def later(wf: str, task: str, **entry: Any) -> dict[str, Any]:
    body = {"state": "open", "reviews": {}, "comments": 0, "commits": 0, "files": 0, **entry}
    return {"kind": "outcome_later", "workflow": wf, "thread_id": f"{wf}/{task}", "ts": "2999-01-01T00:00:00+00:00",
            "entry": body}


def test_a_met_run_sent_back_or_followed_up_is_an_escape(repo: Path) -> None:
    """OUT-AC10 (OUT-B19, OUT-B26), AC 3: rerun, `changes_requested` and a follow-up commit on a written file are
    escapes; a met run with none, and an unmet run with a review, are not."""
    spec = with_outcome_spec()
    wf = spec.name
    rows = [segment(wf, "E-1"), segment(wf, "E-2"), segment(wf, "E-3"), segment(wf, "E-4"),
            segment(wf, "E-5", "unmet"),
            {"kind": "intervention", "workflow": wf, "thread_id": f"{wf}/E-1", "cause": "rerun",
             "ts": "2999-01-01T00:00:00+00:00"},
            later(wf, "E-2", reviews={"changes_requested": 1}),
            later(wf, "E-3", commits=1, files=1),
            later(wf, "E-4", reviews={"approved": 1}, comments=2, commits=1, files=0),
            later(wf, "E-5", reviews={"changes_requested": 1})]
    root = repo / ".tempergraph"
    root.mkdir(exist_ok=True)
    (root / "ledger.jsonl").write_text("".join(json.dumps(r) + "\n" for r in rows), encoding="utf-8")
    cat = Catalog(specs={wf: spec})
    code, doc, err = cli(repo, None, "outcome", "show", wf, "--runs", catalog=cat)
    assert code == 0, err
    assert doc["runs"][0]["escapes"] == 3
    code, doc, err = cli(repo, None, "outcome", "candidates", wf, "--window", "30", catalog=cat)
    assert code == 0, err
    (esc,) = [c for c in doc["candidates"] if c["signal"] == "escape"]
    assert esc["threads"] == [f"{wf}/E-1", f"{wf}/E-2", f"{wf}/E-3"]


def test_outcome_show_prints_the_unverified_share_and_no_zero_for_an_unmeasured_figure(repo: Path) -> None:
    """OUT-AC4 (OUT-B18, OUT-B19), AC 3. Scope: `outcome show` only; `report`, the run detail document and the audit
    do not print the unverified share and this change does not touch them."""
    spec = with_outcome_spec()
    wf = spec.name
    weak = [{"id": "c1", "class": "judge", "status": "not_verified", "severity": "blocker", "trust": "unverified"}]
    ok = [{"id": "c1", "class": "judge", "status": "met", "severity": "blocker", "trust": "calibrated"}]
    rows = [segment(wf, "A-1", "met", weak, revision=1), segment(wf, "A-2", "met", ok, revision=1),
            segment(wf, "B-1", "not_reached", revision=2), segment(wf, "B-2", "not_reached", revision=2),
            segment(wf, "C-1", "unmet", ok, revision=3),
            segment(wf, "D-1", "met", ok, revision=4), later(wf, "D-1", reviews={"changes_requested": 1})]
    root = repo / ".tempergraph"
    root.mkdir(exist_ok=True)
    (root / "ledger.jsonl").write_text("".join(json.dumps(r) + "\n" for r in rows), encoding="utf-8")
    code, doc, err = cli(repo, None, "outcome", "show", wf, "--runs", catalog=Catalog(specs={wf: spec}))
    assert code == 0, err
    rev = {r["revision"]: r for r in doc["runs"]}
    assert rev[1]["unverified_share"] == 0.5 and rev[1]["weak_blockers"] == ["c1"]
    assert (rev[2]["met_rate"], rev[2]["escape_rate"], rev[2]["unverified_share"]) == (None, None, None)
    assert rev[3]["escape_rate"] is None and rev[3]["met_rate"] == 0.0 and rev[3]["unverified_share"] == 0.0
    assert rev[4]["escapes"] == 1 and rev[4]["escape_rate"] == 1.0
    assert rev[2]["sign_off"]["per_run"] is None
