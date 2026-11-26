"""Harvest of judge misses and replay of judges on kept cases (LIF-B7 to LIF-B16 harvest and replay, LIF-AC5)."""

from __future__ import annotations

import json
from pathlib import Path

from tempergraph.catalog import Catalog
from tempergraph.docs import append_jsonl
from tempergraph.executors.standins import standin
from tempergraph.improve import calibration as cal
from tempergraph.improve import harvest as hv

from .test_calibration import gold, judge_ex, oracle, spec_at
from .test_cli import cli

CANARY = "CANARY-7f3a9"


def label(root: Path, thread: str, value: str, verdict: str = "PROCEED", kind: str = "override",
          criterion: str | None = None, seq: int = 12) -> None:
    append_jsonl(root / "ledger.jsonl", {"kind": "label", "schema_version": 1, "label_id": f"{thread}-{seq}-{kind}",
                                         "workflow": "demo", "thread": thread, "run_id": f"{thread}#0",
                                         "unit": "review", "attempt": 1, "gate_record": seq, "gate_verdict": verdict,
                                         "criterion_id": criterion, "label_kind": kind, "value": value,
                                         "source": "person", "request": CANARY})


def test_a_miss_becomes_a_local_candidate_without_request_text(tmp_path: Path) -> None:  # LIF-AC5
    pkg, root = tmp_path / "pkg", tmp_path / "state"
    spec = spec_at(pkg)
    label(root, "demo/T-1", "disagree", criterion="c2")
    label(root, "demo/T-1", "disagree", kind="pushback", criterion="c2")
    label(root, "demo/T-2", "disagree", verdict="RETRY", seq=30)
    label(root, "demo/T-3", "agree")
    rows = hv.harvest(root, spec, "review")
    assert [(r["thread"], r["new"]) for r in rows] == [("demo/T-1", True), ("demo/T-2", True)]
    assert rows[0]["suggested"] == [{"criterion": "c2", "expected": "UNMET"}]
    assert rows[1]["suggested"] == [{"criterion": c, "expected": "MET"} for c in ("c1", "c2", "c3")]
    case = hv.read_candidate(Path(rows[0]["path"]))
    assert (case["provenance"], case["state"], case["labels"]) == ("harvested", "candidate", [])
    assert len(case["origin"]["labels"]) == 2 and case["subject"]["produces"] == ["verdict"]
    written = [p for p in tmp_path.rglob("*") if p.is_file() and "h-" in str(p)]
    assert written and all(p.is_relative_to(root) for p in written)  # never outside the state root
    assert not any(CANARY in p.read_text() for p in written)
    assert not (pkg / "evals").exists()
    assert [r["new"] for r in hv.harvest(root, spec, "review")] == [False, False]  # idempotent


def test_an_escape_becomes_a_local_outcome_candidate_without_text(tmp_path: Path) -> None:  # LIF-AC12, AC 4
    from tempergraph.run.outcome import with_outcome

    from .test_run import with_outcome_spec

    spec = with_outcome_spec()
    wf = spec.name
    root = tmp_path / "state"
    ts = "2999-01-01T00:00:00+00:00"
    pull = {"host": "github.com", "repo": "acme/notes", "number": 7, "commit": "abc123"}
    entry = {"state": "open", "reviews": {"changes_requested": 1}, "comments": 2, "commits": 0, "files": 0}
    rows = [
        {"kind": "run_segment", "workflow": wf, "thread_id": f"{wf}/H-1", "ts": ts, "pull_request": pull,
         "request": CANARY, "outcome": {"revision": 1, "verdict": "met", "criteria": [], "intermediate": [],
                                        "later": []}},
        {"kind": "run_segment", "workflow": wf, "thread_id": f"{wf}/H-2", "ts": ts,
         "outcome": {"revision": 1, "verdict": "met", "criteria": [], "intermediate": [], "later": []}},
        {"kind": "outcome_later", "workflow": wf, "thread_id": f"{wf}/H-1", "ts": ts, "entry": entry},
    ]
    for r in rows:
        append_jsonl(root / "ledger.jsonl", r)
    out = hv.harvest(root, spec, "outcome")
    assert [(r["thread"], r["new"]) for r in out] == [(f"{wf}/H-1", True)]
    case = hv.read_candidate(Path(out[0]["path"]))
    assert case["origin"]["pull_request"] == {"host": "github.com", "repo": "acme/notes", "number": 7}
    assert case["origin"]["entry"]["reviews"] == {"changes_requested": 1}
    assert "changes_requested" in case["origin"]["signals"]
    gate = with_outcome(spec).units["outcome"].gate
    blockers = sorted(cal.judged_blockers(gate))
    assert blockers and case["suggested"] == [{"criterion": c, "expected": "UNMET"} for c in blockers]
    written = [p for p in root.rglob("*") if p.is_file() and "h-" in str(p)]
    assert written and not any(CANARY in p.read_text() for p in written)
    assert not any("h-" in str(p) for p in tmp_path.rglob("*") if not p.is_relative_to(root))
    assert [r["new"] for r in hv.harvest(root, spec, "outcome")] == [False]


def test_replay_compares_with_the_recorded_score(tmp_path: Path) -> None:  # LIF-B7 to LIF-B16 replay
    pkg, root = tmp_path / "pkg", tmp_path / "state"
    spec = spec_at(pkg)
    gold(spec, bad=2, good=2)
    cal.score(spec, "review", judge_ex(), variants=[])
    ex = judge_ex()
    rec = hv.replay(spec, root, ex)
    (g,) = rec["gates"]
    assert (g["cases"], g["agreement"], g["verdict_agreement"], g["flips"]) == (4, 1.0, 1.0, [])
    assert {c.kind for c in ex.calls} == {"judge"} and len(ex.calls) == 4
    drifted = hv.replay(spec, root, standin("claude", judges=[oracle(persuaded=True)] * 4))
    assert drifted["gates"][0]["agreement"] == 1.0  # the base subject carries no persuasion: same statuses
    flipped = hv.replay(spec, root, standin("claude", judges=[oracle(unparsed_on="BAD")] * 4))
    (g,) = flipped["gates"]
    assert g["agreement"] == 0.5 and len(g["flips"]) == 6 and g["flips"][0]["now"] == cal.DISCARDED
    capped = hv.replay(spec, root, judge_ex(), cap_usd=0.015)
    assert capped["partial"] and capped["gates"][0]["cases"] == 2
    assert len((root / "evals" / "replays.jsonl").read_text().splitlines()) == 4
    assert CANARY not in (root / "evals" / "replays.jsonl").read_text()


def test_harvest_and_replay_in_the_cli(tmp_path: Path, repo: Path) -> None:
    from tempergraph.store.layout import state_root_path

    spec = spec_at(tmp_path / "pkg")
    gold(spec, bad=1, good=1)
    cal.score(spec, "review", judge_ex(), variants=[])
    cat = Catalog(specs={"demo": spec})
    label(state_root_path(repo), "demo/T-1", "disagree")
    code, doc, _ = cli(repo, None, "evals", "harvest", "demo", "review", "--json", catalog=cat)
    assert code == 0 and len(doc["candidates"]) == 1
    code, text, _ = cli(repo, None, "evals", "harvest", "demo", "review", catalog=cat)
    assert code == 0 and "kept h-" in text and "evals label" in text
    assert cli(repo, None, "evals", "harvest", "demo", "nope", catalog=cat)[0] != 0
    code, doc, _ = cli(repo, judge_ex(), "evals", "replay", "demo", "--json", catalog=cat)
    assert code == 0 and doc["gates"][0]["agreement"] == 1.0
    assert json.loads((state_root_path(repo) / "evals" / "replays.jsonl").read_text().splitlines()[-1])["gates"]
