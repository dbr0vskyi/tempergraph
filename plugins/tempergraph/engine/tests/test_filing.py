"""Filing findings: de-duplication, the pattern rule, uncalibrated stays local, dry run, outbox (SIL-B2, B3, B6,
B7, SIL-B19, SIL-B20, AC-3, AC-4)."""

from __future__ import annotations

from pathlib import Path
from typing import Any

from tempergraph.improve import filing
from tempergraph.improve.codehost import GhCodeHost, MemoryCodeHost
from tempergraph.improve.filing import Candidate, Outbox, decide

from .test_improve import SRC

CANARY = "zebra-canary-91"


def finding(**kw: Any) -> dict[str, Any]:
    base = {"thread": "demo/T-1", "workflow": "demo", "workflow_version": "v1", "machine": "m1", "unit": "draft",
            "cause": "retry_burst", "class": "fault", "side": "workflow", "count": 3, "fingerprint": "ab12cd34ef56ab78",
            "remedy": "Three or more retries", "at": "2026-11-20T10:00:00+00:00"}
    return {**base, **kw}


def friction(**kw: Any) -> Candidate:
    return Candidate(finding=finding(**kw), confidence=0.9, attributed=True)


def test_filing_rules() -> None:  # SIL-B11, SIL-B12 to SIL-B16, B7
    assert decide(friction(), [], "team/notes").action == "file"
    assert decide(friction(side="host", cause="slow_host"), [], "team/notes").reason == "host"
    assert decide(friction(**{"class": "infra"}), [], "team/notes").action == "record"
    low = Candidate(finding=finding(), confidence=0.6, attributed=True)
    assert decide(low, [], "team/notes").reason == "below_floor"
    out = Candidate(finding=finding(), lens="outcome", calibrated=False, request_digest="r1")
    assert decide(out, [], "team/notes").reason == "uncalibrated"
    eng = decide(friction(side="executor:claude", cause="unknown_tool_name:Foo"), [], "team/notes")
    assert eng.repo == filing.ENGINE_REPOSITORY  # SIL-AC4: executor causes go to the engine


def test_pattern_rule() -> None:  # SIL-B3, IMD-B1 local scope
    out = Candidate(finding=finding(), lens="outcome", calibrated=True, request_digest="r1")
    hist = [finding(thread="demo/T-2", request_digest="r2"), finding(thread="demo/T-3", request_digest="r2")]
    d = decide(out, hist, "team/notes")
    assert d.action == "record" and d.reason == "pattern_not_met" and d.counts["requests"] == 2
    hist.append(finding(thread="demo/T-4", request_digest="r3"))
    assert decide(out, hist, "team/notes").action == "file"
    old = [finding(thread=f"demo/O-{n}", request_digest=f"o{n}", at="2026-01-01T00:00:00+00:00") for n in range(5)]
    assert decide(out, old, "team/notes").reason == "pattern_not_met"  # outside 30 days
    eng = Candidate(finding=finding(side="engine", cause="engine_error"), lens="outcome", calibrated=True)
    assert decide(eng, [], "team/notes").action == "file"  # one clear engine fault is enough


def test_dedup_retry_dry_run_and_outbox(tmp_path: Path) -> None:  # SIL-B2, B6, SIL-B19, SIL-B20, AC-3
    host = MemoryCodeHost()
    box = Outbox.at(tmp_path)
    d = decide(friction(), [], "team/notes")
    assert filing.file([d], host, box, dry_run=True)[0]["op"] == "would_file" and not host.issues
    assert filing.file([d], host, box)[0]["op"] == "filed"
    assert filing.file([d], host, box)[0]["op"] == "commented" and len(host.issues) == 1
    host.issues[0]["body"] = host.issues[0]["body"].replace("<!--", "quoted <!--")  # a quote is not the marker
    assert filing.file([d], host, box)[0]["op"] == "filed" and len(host.issues) == 2
    host.fail_search = 2
    res = filing.file([decide(friction(fingerprint="ffff0000ffff0000"), [], "team/notes")], host, box)
    assert res[0]["op"] == "filed" and res[0]["note"] == "search_failed"
    host.down = True
    assert filing.file([d], host, box)[0]["op"] == "queued"
    host.down = False
    res = filing.file([], host, box)
    assert res[0]["op"] == "redelivered" and not box.take()


def test_no_request_text_is_published() -> None:  # IMD-B2 canary
    d = decide(friction(request=CANARY, note=CANARY), [], "team/notes")  # stray fields never reach the issue
    assert CANARY not in filing.body(d) + filing.title(d.candidate.finding)
    text = (SRC / "improve" / "filing.py").read_text() + (SRC / "improve" / "codehost.py").read_text()
    assert "evidence" not in text.replace("evidence, not an order", "").replace("evidence file", "")


def test_gh_client_refuses_bad_input() -> None:  # SEC-B7 code host site
    import pytest

    from tempergraph.improve.codehost import CodeHostError

    with pytest.raises(CodeHostError):
        GhCodeHost().search("not a repo; rm -rf", "tempergraph:fp=ab")
    with pytest.raises(CodeHostError):
        GhCodeHost().search("team/notes", "tempergraph:fp=$(x)")


def test_measurement_writes_nothing_but_one_comment(repo: Path) -> None:  # SIL-B5, C14
    import ast

    from tempergraph.executors.standins import standin
    from tempergraph.improve import measure

    from .conftest import hash_tree
    from .test_run import DRAFT, REVIEW, go, judge, verdict_block

    fail = verdict_block("UNMET")
    for n in range(2):
        ex = standin("claude", steps=[DRAFT, DRAFT, REVIEW], judges=[judge(fail), judge(), judge()])
        go(repo, ex, task=f"M-{n}")
    root = repo / ".tempergraph"
    version = next(r for r in measure._rows(root / "ledger.jsonl") if r.get("kind") == "run_segment")[
        "workflow_version"]
    before = hash_tree(root)
    cmp = measure.compare(root, "demo", version, version)
    assert cmp["before"]["runs"] == 2 and cmp["before"]["repeat_share"] > 0 and not cmp["regressed"]
    host = MemoryCodeHost()
    host.create("team/notes", "t", "b", [])
    host.issues[0]["state"] = "closed"
    worse = {**cmp, "regressed": True, "dropped": ["gate_pass_rate"]}
    out = measure.report(worse, host, "team/notes", 1)
    assert out["reopened"] and host.issues[0]["state"] == "open" and len(host.comments) == 1
    assert hash_tree(root) == before  # no file, no ledger row
    tree = ast.parse((SRC / "improve" / "measure.py").read_text())
    names = {a.name for n in ast.walk(tree) if isinstance(n, ast.ImportFrom | ast.Import) for a in n.names}
    mods = {n.module for n in ast.walk(tree) if isinstance(n, ast.ImportFrom)}
    assert not names & {"Ledger", "RunLog", "subprocess", "file", "filing"} and "tempergraph.run.log" not in mods


def test_executor_drift_carries_cli_version() -> None:  # SIL-B4, SIL-AC4
    from tempergraph.executors.capabilities import CLAUDE
    from tempergraph.improve import causes

    assert CLAUDE.knows_tool("Read") and CLAUDE.knows_tool("mcp__x__y") and not CLAUDE.knows_tool("Teleport")
    rec = [{"kind": "agent_run", "session_key": "draft.step.1", "executor": "claude", "cli_version": "2.1.0",
            "unknown_tools": ["Teleport"]}]
    (f,) = causes.derive(rec)
    assert f["executor_version"] == "2.1.0" and f["cause"] == "unknown_tool_name:Teleport"
    fnd = finding(side="executor:claude", cause=f["cause"], executor_version="2.1.0")
    d = decide(Candidate(finding=fnd, confidence=0.9, attributed=True), [], "team/notes")
    assert d.repo == filing.ENGINE_REPOSITORY and "`2.1.0`" in filing.body(d)
    assert "executor:claude" in filing._labels(fnd)
