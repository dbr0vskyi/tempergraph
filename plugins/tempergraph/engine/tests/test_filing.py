"""Filing findings: de-duplication, the pattern rule, uncalibrated stays local, dry run, outbox (SIL-B2, B3, B6,
B7, SIL-B19, SIL-B20, AC-3, AC-4)."""

from __future__ import annotations

from datetime import UTC, datetime
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
    assert decide(low, [], "team/notes").reason == "below_count"  # FFD-AC3
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


NOW = datetime(2026, 11, 24, 12, 0, tzinfo=UTC)


def seen(*threads: str, **kw: Any) -> list[dict[str, Any]]:
    """The fingerprint recorded in other runs: one finding per thread, each with its own request digest."""
    return [finding(thread=f"demo/{t}", request_digest=f"r-{t}", **kw) for t in threads]


def attributed(conf: float | None, ok: bool = True, earlier: tuple[bool, ...] = (), **kw: Any) -> Candidate:
    return Candidate(finding=finding(**kw), confidence=conf, attributed=ok, request_digest="r-now",
                     earlier_answers=earlier)


def test_friction_files_by_the_pattern_count_or_by_confidence() -> None:  # FFD-AC1, SIL-AC36, SIL-AC34, SIL-AC35
    hist = seen("T-2", "T-3")
    d = decide(attributed(0.5, earlier=(True, False)), hist, "team/notes", now=NOW)  # (true, false, true) files
    assert d.action == "file" and d.reason == "pattern_met" and d.counts["runs"] == 3 and d.counts["requests"] == 3
    assert d.repo == "team/notes"
    assert decide(attributed(0.5, earlier=(True,)), hist, "team/notes", now=NOW).action == "file"  # (true, true)
    assert decide(attributed(0.5, ok=True, earlier=(False,)), hist, "team/notes", now=NOW).action == "record"  # tie
    assert decide(attributed(0.5, ok=False, earlier=(True,)), hist, "team/notes", now=NOW).action == "record"
    assert decide(attributed(0.5, earlier=(False, False)), hist, "team/notes", now=NOW).reason == "not_attributed"
    one = decide(attributed(0.5), hist, "team/notes", now=NOW)  # one recorded answer, count met, below the floor
    assert one.action == "record" and one.reason == "few_answers"
    assert decide(attributed(0.8), [], "team/notes", now=NOW).action == "file"  # one answer at the floor files
    assert decide(attributed(0.5), [], "team/notes", now=NOW).action == "record"
    by_conf = decide(attributed(0.9), [], "team/notes", now=NOW)  # by confidence, with no pattern figure
    assert by_conf.action == "file" and by_conf.reason == "fault" and by_conf.counts == {}


def test_recorded_answers_reads_loop_judged_inside_the_window(tmp_path: Path) -> None:  # FFD-AC1, SIL-AC36
    import json

    def put(task: str, ts: str, *flags: bool) -> None:
        d = tmp_path / "runs" / "demo" / task
        d.mkdir(parents=True, exist_ok=True)
        rows = [{"ts": ts, "kind": "loop_judged", "answers": [
            {"fingerprint": "fp1", "attributed": f, "confidence": 0.5} for f in flags]},
                {"ts": ts, "kind": "loop_started"}]
        with open(d / "loop.jsonl", "a", encoding="utf-8") as fh:
            fh.write("not json\n" + "".join(json.dumps(r) + "\n" for r in rows))

    put("T-1", "2026-11-20T10:00:00+00:00", True)
    put("T-2", "2026-11-22T10:00:00+00:00", False)
    put("T-3", "2026-01-01T10:00:00+00:00", True)  # older than `pattern_rule.window_days`
    got = filing.recorded_answers(tmp_path, "demo", now=NOW)
    assert got == {"fp1": [True, False]}
    assert filing.recorded_answers(tmp_path / "none", "demo", now=NOW) == {}


def test_each_unfiled_friction_finding_has_one_reason() -> None:  # FFD-AC2, FFD-AC3, SIL-AC35
    hist = seen("T-2", "T-3")
    assert decide(attributed(None, ok=False), hist, "team/notes", now=NOW).reason == "not_judged"  # SIL-B35
    for conf in (0.1, 0.9):  # this exit's answer not attributed: at any confidence and any count
        assert decide(attributed(conf, ok=False), hist, "team/notes", now=NOW).reason == "not_attributed"
        assert decide(attributed(conf, ok=False), [], "team/notes", now=NOW).reason == "not_attributed"
    assert decide(attributed(0.5), hist, "team/notes", now=NOW).reason == "few_answers"
    assert decide(attributed(0.5, earlier=(False,)), hist, "team/notes", now=NOW).reason == "not_attributed"
    assert decide(attributed(0.5, earlier=(False, False)), hist, "team/notes", now=NOW).reason == "not_attributed"
    assert decide(attributed(0.5), [], "team/notes", now=NOW).reason == "below_count"
    same_request = [finding(thread=f"demo/T-{n}", request_digest="r-now") for n in (2, 3)]  # three runs, one request
    assert decide(attributed(0.5), same_request, "team/notes", now=NOW).reason == "below_count"
    old = seen("T-2", "T-3", at="2026-01-01T00:00:00+00:00")  # outside `pattern_rule.window_days`
    assert decide(attributed(0.5), old, "team/notes", now=NOW).reason == "below_count"
    reasons = {decide(attributed(c, ok=ok, earlier=e), h, "team/notes", now=NOW).reason
               for c in (None, 0.1, 0.5, 0.9) for ok in (True, False) for e in ((), (True,), (False,), (True, False))
               for h in ([], hist)}
    assert "below_floor" not in reasons


def test_a_request_counts_once_per_thread() -> None:  # SIL-AC47, SIL-AC9
    out = Candidate(finding=finding(), lens="outcome", calibrated=True, request_digest="r1")
    # two runs share a request and one holds two digests: the thread counts by the first it recorded
    hist = [finding(thread="demo/T-2", request_digest="r2"), finding(thread="demo/T-3", request_digest="r2"),
            finding(thread="demo/T-3", request_digest="r3", at="2026-11-21T10:00:00+00:00")]
    d = decide(out, hist, "team/notes", now=NOW)
    assert d.action == "record" and d.reason == "pattern_not_met" and d.counts["requests"] == 2
    three = [finding(thread=f"demo/T-{n}", request_digest=f"r{n}") for n in (2, 3)]
    assert decide(out, three, "team/notes", now=NOW).action == "file"  # three runs, three requests
    fr = attributed(0.5)
    two = [finding(thread="demo/T-2", request_digest="r-now"), finding(thread="demo/T-3", request_digest="r3"),
           finding(thread="demo/T-3", request_digest="r4", at="2026-11-21T10:00:00+00:00")]
    assert decide(fr, two, "team/notes", now=NOW).reason == "below_count"  # friction lens: 2 requests, not 4


def test_a_judged_fault_carries_the_counted_figures() -> None:  # FFD-AC4, FFD-AC5
    hist = seen("T-2", "T-3")
    cases = [attributed(0.5, earlier=(True,)), attributed(0.9), attributed(0.5), attributed(0.5, earlier=(False,)),
             attributed(0.5, ok=False), attributed(0.2)]
    for c in cases:
        d = decide(c, hist, "team/notes", now=NOW)
        assert {*d.counted} == {"runs", "requests", "machines"} and all(type(v) is int for v in d.counted.values())
    assert decide(attributed(0.9), hist, "team/notes", now=NOW).counts == {}  # by confidence: no pattern figures
    by_conf = decide(attributed(0.9), hist, "team/notes", now=NOW)
    assert "pattern " not in filing.body(by_conf)
    met = decide(attributed(0.5, earlier=(True,)), hist, "team/notes", now=NOW)
    assert met.counts and "runs 3" in filing.body(met) and "pattern " in filing.body(met)
    assert decide(attributed(None, ok=False), hist, "team/notes", now=NOW).counted == {}  # not_judged
    assert decide(attributed(0.9, **{"class": "infra"}), hist, "team/notes", now=NOW).counted == {}


def test_a_count_met_friction_finding_follows_dry_run_sides_and_dedup(tmp_path: Path) -> None:
    # SIL-AC36, SIL-AC37, SIL-AC34, AC 6
    hist = seen("T-2", "T-3")
    d = decide(attributed(0.5, earlier=(True,)), hist, "team/notes", now=NOW)
    host = MemoryCodeHost()
    res = filing.file([d], host, Outbox.at(tmp_path), dry_run=True)  # SIL-AC36
    assert [r["op"] for r in res] == ["would_file"] and not host.issues and not host.comments
    eng = decide(attributed(0.5, earlier=(True,), side="engine", cause="engine_error"),
                 seen("T-2", "T-3", side="engine", cause="engine_error"), "team/notes", now=NOW)
    ex = decide(attributed(0.5, earlier=(True,), side="executor:claude", cause="unknown_tool_name:Foo"),
                seen("T-2", "T-3", side="executor:claude", cause="unknown_tool_name:Foo"), "team/notes", now=NOW)
    assert eng.action == ex.action == "file" and eng.repo == ex.repo == filing.ENGINE_REPOSITORY  # SIL-AC37
    assert d.repo == "team/notes"
    host_side = decide(attributed(0.5, side="host", cause="slow_host"),
                       seen("T-2", "T-3", side="host", cause="slow_host"), "team/notes", now=NOW)
    assert host_side.action == "record" and host_side.reason == "host" and host_side.repo is None
    box = Outbox.at(tmp_path)
    assert filing.file([d], host, box)[0]["op"] == "filed"
    assert filing.file([d], host, box)[0]["op"] == "commented" and len(host.issues) == 1 and len(host.comments) == 1


def test_a_filed_or_commented_result_names_the_repository_and_number(tmp_path: Path) -> None:  # FFD-AC5, ISS-AC11
    d = decide(attributed(0.5, earlier=(True,)), seen("T-2", "T-3"), "team/notes", now=NOW)
    host = MemoryCodeHost()
    box = Outbox.at(tmp_path)
    (filed,) = filing.file([d], host, box)
    assert filed["op"] == "filed" and filed["repo"] == "team/notes"
    (commented,) = filing.file([d], host, box)
    assert commented["op"] == "commented" and commented["repo"] == "team/notes"
    assert commented["number"] == host.issues[0]["number"] and isinstance(commented["number"], int)


def test_dedup_retry_dry_run_and_outbox(tmp_path: Path) -> None:  # SIL-B2, B6, SIL-B19, SIL-B20, SIL-AC3
    host = MemoryCodeHost()
    box = Outbox.at(tmp_path)
    d = decide(friction(), [], "team/notes")
    assert filing.file([d], host, box, dry_run=True)[0]["op"] == "would_file" and not host.issues
    assert filing.file([d], host, box)[0]["op"] == "filed"
    assert filing.file([d], host, box)[0]["op"] == "commented" and len(host.issues) == 1
    host.issues[0]["body"] = host.issues[0]["body"].replace("<!--", "quoted <!--")  # a quote is not the marker
    assert filing.file([d], host, box)[0]["op"] == "filed" and len(host.issues) == 2
    host.fail_search = 2
    res = filing.file([decide(friction(fingerprint="ffff0000ffff0000", cause="check_fail:draft"), [], "team/notes")],
                      host, box)
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
        GhCodeHost().loop_issues("not a repo; rm -rf", "open")
    with pytest.raises(CodeHostError):
        GhCodeHost().loop_issues("team/notes", "open; rm -rf")


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
