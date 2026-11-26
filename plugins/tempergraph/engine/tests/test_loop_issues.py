"""The loop's issues end to end, against a fake code host (ISS-AC1 to ISS-AC6, PRP-AC8, PRP-AC9, IMD-AC3; task i1).

Every test carries the criterion id of its spec and the task's `AC <n>`: AC 1 labels, body, mute, regression, `Closes`
and trial comment; AC 2 the `mute.days` record and the close-reason table; AC 3 each test that drives the fake host;
AC 4 the documents.
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import UTC, datetime, timedelta
from pathlib import Path
from typing import Any

import pytest

from tempergraph.improve import filing, params
from tempergraph.improve.codehost import CodeHostError, GhCodeHost, MemoryCodeHost
from tempergraph.improve.filing import Candidate, Outbox, decide

from .test_filing import CANARY, finding, friction

FP = "ab12cd34ef56ab78"
REPO = "team/notes"
NOW = datetime(2026, 11, 24, 12, 0, tzinfo=UTC)


def ago(days: float) -> str:
    return (NOW - timedelta(days=days)).isoformat()


# -- phase 1: the code host reads closed issues ---------------------------------------------------------------

def test_mute_days_is_a_parameter_record() -> None:  # IMD-AC3, ISS-B3; AC 2
    p = params.PARAMS["mute.days"]
    assert p.value == 30 and p.provenance == "default_no_data" and "ISS-B3" in p.source
    assert params.value("mute.days") == 30


@pytest.mark.parametrize("reason", ["not_planned", "completed", "duplicate", ""])
def test_a_closed_issue_is_read_from_the_label_list(reason: str) -> None:  # ISS-AC3, ISS-AC9; AC 1, AC 3
    host = MemoryCodeHost()
    url = host.create(REPO, "t", f"<!-- {filing.marker(FP)} -->\nbody", ["tempergraph-loop"])
    host.create(REPO, "t", f"<!-- {filing.marker('ffff0000ffff0000')} -->\nbody", ["bug"])  # not a loop issue
    assert host.loop_issues(REPO, "closed") == []  # open issues are never read as closed
    host.close(REPO, 1, reason, ago(3))
    host.close(REPO, 2, reason, ago(3))
    (got,) = host.loop_issues(REPO, "closed")
    assert got["number"] == 1 and got["url"] == url and got["state_reason"] == reason
    assert got["closed_at"] == ago(3) and filing.marker(FP) in got["body"]
    assert host.loop_issues(REPO, "open") == []  # the open list stays open-only
    host.reopen(REPO, 1)
    assert host.loop_issues(REPO, "closed") == [] and len(host.loop_issues(REPO, "open")) == 1
    assert host.issues[0]["state_reason"] in (None, "") and host.issues[0].get("closed_at") in (None, "")


def test_the_closed_read_can_fail_and_go_down() -> None:  # ISS-AC6; AC 3
    host = MemoryCodeHost(fail_closed=2)
    for _ in range(2):
        with pytest.raises(CodeHostError):
            host.loop_issues(REPO, "closed")
    assert host.loop_issues(REPO, "closed") == []
    with pytest.raises(CodeHostError):
        MemoryCodeHost(down=True).loop_issues(REPO, "closed")


def test_gh_list_read_refuses_bad_input() -> None:  # SEC-B7, ISS-B9
    with pytest.raises(CodeHostError):
        GhCodeHost().loop_issues("not a repo; rm -rf", "closed")
    with pytest.raises(CodeHostError):
        GhCodeHost().loop_issues(REPO, "all")


def filed(host: MemoryCodeHost, tmp_path: Path, cand: Candidate | None = None, **kw: Any) -> list[dict[str, Any]]:
    """Files one candidate (a friction finding by default) to `REPO` and returns the results."""
    c = cand or friction()
    return filing.file([decide(c, [], REPO)], host, Outbox.at(tmp_path), **kw)


# -- phase 2: labels and body ---------------------------------------------------------------------------------

DEFAULT = {"tempergraph-loop", "needs-triage"}


def test_default_labels_by_side(tmp_path: Path) -> None:  # ISS-AC1; AC 1, AC 3
    host = MemoryCodeHost()
    filed(host, tmp_path, friction(fingerprint="aa00000000000001"))
    filed(host, tmp_path, friction(fingerprint="aa00000000000002", side="engine", cause="engine_error"))
    filed(host, tmp_path, friction(fingerprint="aa00000000000003", side="executor:claude", cause="unknown_tool_name:X"))
    by = [set(i["labels"]) for i in host.issues]
    assert by[0] == DEFAULT | {"side:workflow"}
    assert by[1] == DEFAULT | {"side:engine"}
    assert by[2] == DEFAULT | {"executor:claude"}
    assert [i["repo"] for i in host.issues] == [REPO, filing.ENGINE_REPOSITORY, filing.ENGINE_REPOSITORY]


def test_a_workflows_declared_labels_replace_the_default_for_its_own_findings(tmp_path: Path) -> None:
    # ISS-AC1; AC 1, AC 3
    host = MemoryCodeHost()
    declared = ["triage", "bot"]
    filed(host, tmp_path, Candidate(finding=finding(fingerprint="bb00000000000001"), confidence=0.9, attributed=True,
                                    issue_labels=declared))
    filed(host, tmp_path, Candidate(finding=finding(fingerprint="bb00000000000002", side="engine", cause="engine_error"),
                                    confidence=0.9, attributed=True, issue_labels=declared))
    assert set(host.issues[0]["labels"]) == {"triage", "bot", "tempergraph-loop", "side:workflow"}
    assert "needs-triage" not in host.issues[0]["labels"]
    assert set(host.issues[1]["labels"]) == DEFAULT | {"side:engine"}  # an engine finding keeps the engine's list
    assert len(host.issues[0]["labels"]) == len(set(host.issues[0]["labels"]))  # no duplicates
    filed(host, tmp_path, Candidate(finding=finding(fingerprint="bb00000000000003", cause="check_fail:draft"),
                                    confidence=0.9, attributed=True, issue_labels=["tempergraph-loop", "x"]))
    assert host.issues[2]["labels"].count("tempergraph-loop") == 1 and "x" in host.issues[2]["labels"]


@pytest.mark.parametrize("bad", ["triage", ["triage", 3], [], ["triage", ""], {"a": 1}, 7])
def test_a_declared_value_that_is_not_a_list_of_names_leaves_the_default(tmp_path: Path, bad: Any) -> None:
    # ISS-AC1; AC 1, AC 3
    host = MemoryCodeHost()
    filed(host, tmp_path, Candidate(finding=finding(), confidence=0.9, attributed=True, issue_labels=bad))
    assert set(host.issues[0]["labels"]) == DEFAULT | {"side:workflow"}


def test_a_child_workflows_finding_takes_the_childs_own_labels(tmp_path: Path) -> None:  # ISS-AC1; AC 1, AC 3
    host = MemoryCodeHost()
    kid = finding(child="setup", parent="deliver", workflow="repo-setup", issue_repository="acme/repo-setup",
                  issue_labels=["kid-triage"])
    filing.file([decide(Candidate(finding=kid, confidence=0.9, attributed=True, issue_labels=["parent-label"]), [], REPO)],
                host, Outbox.at(tmp_path))
    assert host.issues[0]["repo"] == "acme/repo-setup"
    assert set(host.issues[0]["labels"]) == {"kid-triage", "tempergraph-loop", "side:workflow"}
    plain = finding(fingerprint="cc00000000000001", child="setup", parent="deliver", issue_repository="acme/repo-setup",
                    cause="check_fail:draft")
    filing.file([decide(Candidate(finding=plain, confidence=0.9, attributed=True, issue_labels=["parent-label"]), [],
                        REPO)], host, Outbox.at(tmp_path))
    assert set(host.issues[1]["labels"]) == DEFAULT | {"side:workflow"}  # never the parent's list


def test_a_ticket_carries_the_workflows_labels_to_the_issue(repo: Path, monkeypatch: pytest.MonkeyPatch,
                                                            tmp_path: Path) -> None:  # ISS-AC1; AC 1, AC 3
    import dataclasses
    import json

    from tempergraph.executors.standins import standin
    from tempergraph.improve import calibration, child

    from .fixtures.workflows import two_step
    from .test_loop_child import blocked_run, judge_says, tickets
    from .test_run import registry

    pkg = tmp_path / "pkg"
    pkg.mkdir()
    spec = dataclasses.replace(two_step(), package_root=pkg)
    summary = {"lenses": {"friction": False}, "fault_fingerprints": [], "outcome_fingerprints": ["abc"],
               "fingerprints": ["abc"]}
    monkeypatch.setattr(calibration, "has_score", lambda s, gate, root=None: False)

    def ticket_of(doc: Any) -> Any:
        if doc is not None:
            (pkg / "tempergraph.json").write_text(json.dumps(doc))
        p = child.hand_off(tmp_path, spec, "T-1", "demo/T-1", summary, dry_run=False, judge_executor="claude",
                           home=tmp_path / "home")
        assert p is not None
        return json.loads(p.read_text())

    assert ticket_of(None).get("issue_labels") is None  # no tempergraph.json: none declared
    assert ticket_of({"improvement": {"issue_labels": ["triage", "bot"]}})["issue_labels"] == ["triage", "bot"]
    assert ticket_of({"improvement": {}}).get("issue_labels") is None
    blocked_run(repo, "LB-1", monkeypatch)  # a ticket's labels reach the issue the loop's child files
    (t,) = tickets()
    doc = json.loads(t.read_text())
    doc.update(issue_repository=REPO, issue_labels=["triage", "bot"])
    t.write_text(json.dumps(doc))
    host = MemoryCodeHost()
    child.drain(registry=registry(standin("claude", judges=[judge_says(0.9)])), host=lambda: host)
    assert set(host.issues[0]["labels"]) == {"triage", "bot", "tempergraph-loop", "side:workflow"}


def test_a_child_owner_reads_the_childs_declared_labels(tmp_path: Path) -> None:  # ISS-AC1; AC 1, AC 3
    import json

    from tempergraph.improve import record

    from .fixtures.subworkflows import home_dir, parent_spec, register_workflow

    root = register_workflow(home_dir(), tmp_path / "pkgs", "repo-setup", issue_repository="acme/repo-setup")
    spec = parent_spec(workflow="repo-setup")
    kids = {"setup": {"workflow": "repo-setup", "workflow_version": "0.3.1"}}
    assert record._child_owner(spec, "setup", kids)["issue_labels"] is None
    doc = json.loads((root / "tempergraph.json").read_text())
    (root / "tempergraph.json").write_text(json.dumps({**doc, "improvement": {"issue_labels": ["kid"]}}))
    got = record._child_owner(spec, "setup", kids)
    assert got["issue_labels"] == ["kid"] and got["issue_repository"] == "acme/repo-setup"


SECTIONS = ["## Summary", "## Environment", "## Run", "## Steps to reproduce", "## Run log", "## Evidence",
            "## Fingerprint", "## Suggested remedy"]


def section(text: str, name: str) -> str:
    parts = text.split(name + "\n", 1)[1]
    return parts.split("\n## ", 1)[0].strip()


def test_the_body_has_its_sections_after_the_hidden_lines(tmp_path: Path) -> None:  # ISS-AC2; AC 1, AC 3
    host = MemoryCodeHost()
    f = finding(request=CANARY, note=CANARY, executor_version="2.1.0")
    filed(host, tmp_path, Candidate(finding=f, confidence=0.9, attributed=True))
    text = host.issues[0]["body"]
    lines = text.splitlines()
    assert lines[0] == f"<!-- {filing.marker(FP)} -->" and lines[1] == f"<!-- tempergraph:cause={filing.cause_key(f)} -->"
    assert text.count("<!--") == 2
    heads = [ln for ln in lines if ln.startswith("## ")]
    assert heads == SECTIONS
    for name in SECTIONS:
        assert section(text, name)  # each has text under it
    assert FP in section(text, "## Fingerprint") and "<!--" not in section(text, "## Fingerprint")
    assert "Three or more retries" in section(text, "## Suggested remedy")
    assert "retry_burst" in section(text, "## Summary") and "draft" in section(text, "## Summary")
    assert "v1" in section(text, "## Environment") and "2.1.0" in section(text, "## Environment")
    assert "count 3" in section(text, "## Evidence")
    assert CANARY not in text
    filed(host, tmp_path)  # the hidden line is still the exact match of SIL-B2: a second occurrence comments
    assert len(host.issues) == 1 and len(host.comments) == 1


def test_the_body_names_the_parent_and_the_pattern(tmp_path: Path) -> None:  # ISS-AC2; AC 1, AC 3
    host = MemoryCodeHost()
    kid = finding(child="setup", parent="deliver", issue_repository="acme/repo-setup", lens="outcome")
    hist = [finding(thread="demo/T-2", request_digest="r2"), finding(thread="demo/T-3", request_digest="r3")]
    cand = Candidate(finding=kid, lens="outcome", calibrated=True, request_digest="r1")
    filing.file([decide(cand, hist, REPO, now=NOW)], host, Outbox.at(tmp_path))
    text = host.issues[0]["body"]
    assert "deliver" in section(text, "## Summary") and "setup" in section(text, "## Summary")
    assert "requests 3" in section(text, "## Evidence") and "runs 3" in section(text, "## Evidence")
    assert [ln for ln in text.splitlines() if ln.startswith("## ")] == SECTIONS


def test_a_count_filed_issue_shows_the_pattern_figures(tmp_path: Path) -> None:  # ISS-AC11, AC 4
    def hist(*ns: int) -> list[dict[str, Any]]:
        return [finding(thread=f"demo/T-{n}", request_digest=f"r{n}") for n in ns]

    cases = {"outcome": Candidate(finding=finding(), lens="outcome", calibrated=True, request_digest="r1"),
             "friction": Candidate(finding=finding(), confidence=0.5, attributed=True, request_digest="r1")}
    for lens, cand in cases.items():
        host = MemoryCodeHost()
        d = decide(cand, hist(2, 3), REPO, now=NOW)
        assert d.action == "file" and d.reason == "pattern_met", lens
        assert [r["op"] for r in filing.file([d], host, Outbox.at(tmp_path))] == ["filed"]
        evidence = section(host.issues[0]["body"], "## Evidence")
        assert "runs 3" in evidence and "requests 3" in evidence and "machines" in evidence, lens
        d4 = decide(cand, hist(2, 3, 4), REPO, now=NOW)  # a fourth run: the "seen again" comment
        assert [r["op"] for r in filing.file([d4], host, Outbox.at(tmp_path))] == ["commented"]
        assert len(host.issues) == 1
        again = section(host.comments[0]["body"], "## Evidence")
        assert "runs 4" in again and "requests 4" in again, lens
    host = MemoryCodeHost()  # filed by confidence from one run: no figure of the pattern rule
    one = decide(Candidate(finding=finding(), confidence=0.9, attributed=True, request_digest="r1"), [], REPO, now=NOW)
    filing.file([one], host, Outbox.at(tmp_path))
    evidence = section(host.issues[0]["body"], "## Evidence")
    assert "count" in evidence and "fingerprint" in evidence
    assert not any(w in evidence for w in ("runs", "requests", "machines"))


# -- phase 3: the loop reads close reasons back ---------------------------------------------------------------

@dataclass(kw_only=True)
class FlakyCreate(MemoryCodeHost):
    """A host that reads fine and refuses to create while `fail_create` is set (the outbox path)."""

    fail_create: bool = False

    def create(self, repo: str, title: str, body: str, labels: list[str]) -> str:
        if self.fail_create:
            raise CodeHostError("unreachable")
        return super().create(repo, title, body, labels)


def closed_issue(tmp_path: Path, reason: str, days: float, host: MemoryCodeHost | None = None) -> MemoryCodeHost:
    """A host holding the loop's issue for `FP`, closed with `reason` `days` before `NOW`, and no issue open."""
    host = host or MemoryCodeHost()
    filed(host, tmp_path)
    n = len(host.issues)
    host.close(REPO, n, reason, ago(days))
    return host


def again(host: MemoryCodeHost, tmp_path: Path, **kw: Any) -> dict[str, Any]:
    (res,) = filed(host, tmp_path, now=NOW, **kw)
    return res


def test_a_close_as_not_planned_mutes_for_the_mute_days(tmp_path: Path) -> None:  # ISS-AC3; AC 1, AC 3
    host = closed_issue(tmp_path, "not_planned", 10)
    res = again(host, tmp_path)
    assert res == {"op": "muted", "url": host.issues[0]["url"], "fingerprint": FP}
    assert len(host.issues) == 1 and not host.comments  # no issue, no comment
    host = closed_issue(tmp_path, "not_planned", 31)
    res = again(host, tmp_path)
    assert res["op"] == "filed" and len(host.issues) == 2 and "regression" not in host.issues[1]["body"].lower()
    assert set(host.issues[1]["labels"]) == DEFAULT | {"side:workflow"}


def test_an_open_issue_wins_over_a_mute(tmp_path: Path) -> None:  # ISS-AC3; AC 1, AC 3
    host = closed_issue(tmp_path, "not_planned", 10)
    host.create(REPO, "t", host.issues[0]["body"], [])  # a second issue of the fingerprint, open
    res = again(host, tmp_path)
    assert res["op"] == "commented" and res["url"].startswith("https://example.test/team/notes/issues/2#")
    assert [c["number"] for c in host.comments] == [2] and len(host.issues) == 2  # one comment, no mute, no issue
    host.reopen(REPO, 1)  # a person ends a mute by reopening: the loop comments again
    assert again(host, tmp_path)["op"] == "commented"


def test_the_latest_close_decides(tmp_path: Path) -> None:  # ISS-AC3; AC 1, AC 3
    host = MemoryCodeHost()
    filed(host, tmp_path)
    host.close(REPO, 1, "completed", ago(40))
    filed(host, tmp_path, now=NOW)  # a possible regression: a second issue
    assert len(host.issues) == 2
    host.close(REPO, 2, "not_planned", ago(5))
    res = again(host, tmp_path)
    assert res["op"] == "muted" and res["url"] == host.issues[1]["url"] and len(host.issues) == 2
    host2 = MemoryCodeHost()  # the other order: a close as completed over an earlier close as not planned
    filed(host2, tmp_path)
    host2.close(REPO, 1, "not_planned", ago(40))
    filed(host2, tmp_path, now=NOW)  # 40 days: no longer muted, a new issue
    host2.close(REPO, 2, "completed", ago(5))
    res2 = again(host2, tmp_path)
    assert res2["op"] == "filed" and "possible regression" in host2.issues[2]["body"].lower()
    assert "#2" in host2.issues[2]["body"]


def open_of_fingerprint(host: MemoryCodeHost) -> list[int]:
    """The numbers of the issues of `FP` whose state is open."""
    return [i["number"] for i in host.issues if i["state"] == "open" and filing.marker(FP) in i["body"]]


def test_a_repeated_cause_keeps_one_open_issue(tmp_path: Path) -> None:  # SIL-AC3, SIL-B2, SIL-B18; AC 1, AC 3
    host = MemoryCodeHost()
    seen: list[int] = []

    def step(**kw: Any) -> str:
        op = filed(host, tmp_path, now=NOW, **kw)[0]["op"]
        seen.append(len(open_of_fingerprint(host)))
        return str(op)

    # (a) the second and third occurrence comment on the one open issue
    assert [step(), step(), step()] == ["filed", "commented", "commented"]
    assert len(host.issues) == 1 and [c["number"] for c in host.comments] == [1, 1]
    # (b) after a close as completed the new issue is the one open issue; a further occurrence comments on it
    host.close(REPO, 1, "completed", ago(3))
    assert step() == "filed" and len(host.issues) == 2 and open_of_fingerprint(host) == [2]
    assert step() == "commented" and len(host.issues) == 2 and host.comments[-1]["number"] == 2
    # (c) a close as not planned past the mute opens a new issue, again the only open one
    host.close(REPO, 2, "not_planned", ago(40))
    assert step() == "filed" and len(host.issues) == 3 and open_of_fingerprint(host) == [3]
    assert step() == "commented" and len(host.issues) == 3
    assert max(seen) == 1 and min(seen) == 1  # never two open issues, never none after an occurrence


def test_the_mute_length_is_the_parameter_record(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    # ISS-AC3, IMD-AC3; AC 2, AC 3
    host = closed_issue(tmp_path, "not_planned", 10)
    assert again(host, tmp_path)["op"] == "muted"
    monkeypatch.setitem(params.PARAMS, "mute.days", params.Param(name="mute.days", value=5, source="ISS-B3"))
    assert again(host, tmp_path)["op"] == "filed"  # a 10-day close is older than a 5-day mute
    host = closed_issue(tmp_path, "not_planned", 30)
    monkeypatch.setitem(params.PARAMS, "mute.days", params.Param(name="mute.days", value=30, source="ISS-B3"))
    assert again(host, tmp_path)["op"] == "filed"  # 30 days or more files


@pytest.mark.parametrize("days", [10, 200])
def test_a_close_as_completed_links_a_possible_regression(tmp_path: Path, days: int) -> None:  # ISS-AC4; AC 1, AC 3
    host = closed_issue(tmp_path, "completed", days)
    res = again(host, tmp_path)
    assert res["op"] == "filed" and len(host.issues) == 2
    new = host.issues[1]
    assert set(new["labels"]) == DEFAULT | {"side:workflow"}
    summary = section(new["body"], "## Summary")
    assert "#1" in summary and "possible regression" in summary.lower()
    assert "regression" not in host.issues[0]["body"].lower() and not host.comments  # the closed issue is left alone
    assert [ln for ln in new["body"].splitlines() if ln.startswith("## ")] == SECTIONS
    res2 = again(host, tmp_path)  # the next occurrence comments on the new issue; no third issue
    assert res2["op"] == "commented" and res2["url"].endswith("issues/2#c1") and len(host.issues) == 2
    assert [c["number"] for c in host.comments] == [2]


def test_a_close_as_duplicate_mutes_as_not_planned_does(tmp_path: Path) -> None:  # ISS-AC3, ISS-AC5; AC 4
    host = closed_issue(tmp_path, "duplicate", 10)
    res = again(host, tmp_path)
    assert res == {"op": "muted", "url": host.issues[0]["url"], "fingerprint": FP}
    assert len(host.issues) == 1 and not host.comments
    old = closed_issue(tmp_path / "old", "duplicate", 40)
    assert again(old, tmp_path / "old")["op"] == "filed" and len(old.issues) == 2


def _day(n: int) -> datetime:
    return NOW + timedelta(days=n)


def _count(day: datetime, results: list[dict[str, Any]]) -> dict[tuple[str, int], int]:
    """The comments among `results` (each tagged `_day`) that were sent on `day`'s UTC date."""
    out: dict[tuple[str, int], int] = {}
    for r in results:
        if r.get("op") == "commented" and r["_day"] == day.date():
            key = (str(r["repo"]), int(r["number"]))
            out[key] = out.get(key, 0) + 1
    return out


def test_seen_again_comments_are_bounded_per_issue_per_day(  # ISS-AC12; AC 3
        tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    host = MemoryCodeHost()
    filed(host, tmp_path, now=NOW)
    sent: list[dict[str, Any]] = []

    def step(now: datetime, dry_run: bool = False) -> dict[str, Any]:
        (res,) = filed(host, tmp_path, now=now, dry_run=dry_run, comments_today=_count(now, sent))
        sent.append({**res, "_day": now.date()})
        return res

    first = step(NOW)
    assert first["op"] == "commented"
    for _ in range(2):
        capped = step(NOW)
        assert capped["op"] == "comment_capped" and capped["number"] == 1 and capped["repo"] == REPO
        assert "body" not in capped and "text" not in capped and "url" not in capped
    assert len(host.comments) == 1 and len(host.issues) == 1  # no issue opens in place of a comment
    assert step(_day(1))["op"] == "commented" and len(host.comments) == 2  # the next UTC day
    monkeypatch.setitem(params.PARAMS, "seen_again.max_per_issue_per_day",
                        params.Param(name="seen_again.max_per_issue_per_day", value=2, source="ISS-B13"))
    sent.clear()
    assert [step(_day(2))["op"] for _ in range(3)] == ["commented", "commented", "comment_capped"]
    (dry,) = filed(host, tmp_path, now=NOW, dry_run=True, comments_today={(REPO, 1): 9})
    assert dry["op"] == "would_file"  # a dry run is never capped
    fresh = MemoryCodeHost()
    (new,) = filed(fresh, tmp_path / "fresh", now=NOW, comments_today={(REPO, 1): 9})
    assert new["op"] == "filed"  # a new issue is never capped


@pytest.mark.parametrize("reason", ["reopened", ""])
def test_a_reason_the_loop_does_not_read_changes_nothing(tmp_path: Path, reason: str) -> None:  # ISS-AC5; AC 1, AC 3
    host = closed_issue(tmp_path, reason, 3)
    res = again(host, tmp_path)
    assert res["op"] == "filed" and len(host.issues) == 2 and not host.comments
    assert "regression" not in host.issues[1]["body"].lower() and "note" not in res


def test_a_failed_search_of_closed_issues_files_a_plain_issue(tmp_path: Path) -> None:  # ISS-AC6; AC 1, AC 3
    host = closed_issue(tmp_path, "completed", 3)
    host.fail_closed = 2
    res = again(host, tmp_path)
    assert res["op"] == "filed" and res["note"] == "closed_search_failed" and len(host.issues) == 2
    assert "regression" not in host.issues[1]["body"].lower()
    host = closed_issue(tmp_path, "not_planned", 10)
    host.fail_closed = 1  # one failure: retried, then the close reason applies
    assert again(host, tmp_path)["op"] == "muted" and len(host.issues) == 1


def test_a_failed_search_of_open_issues_reads_no_closed_issue(tmp_path: Path) -> None:  # ISS-AC6, SIL-B2; AC 1, AC 3
    host = closed_issue(tmp_path, "not_planned", 10)
    host.fail_search = 2
    host.fail_closed = 5  # would be consumed if the closed read ran
    res = again(host, tmp_path)
    assert res["op"] == "filed" and res["note"] == "search_failed" and host.fail_closed == 5


def test_a_dry_run_and_the_outbox_are_unchanged(tmp_path: Path) -> None:  # ISS-AC6, SIL-B6, SIL-B19; AC 1, AC 3
    host = closed_issue(tmp_path, "not_planned", 10)
    host.fail_closed = 9
    (res,) = filed(host, tmp_path, dry_run=True, now=NOW)
    assert res["op"] == "would_file" and host.fail_closed == 9 and len(host.issues) == 1
    host = closed_issue(tmp_path, "completed", 10)
    box = Outbox.at(tmp_path / "box")
    flaky = FlakyCreate(issues=host.issues, fail_create=True)
    (queued,) = filing.file([decide(friction(), [], REPO)], flaky, box, now=NOW)
    assert queued["op"] == "queued"
    flaky.fail_create = False
    (redelivered,) = filing.file([], flaky, box)
    assert redelivered["op"] == "redelivered"
    assert "possible regression" in flaky.issues[1]["body"].lower()  # the body it was queued with


def test_a_muted_result_is_recorded_and_not_counted_as_filed(repo: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    # ISS-AC3; AC 1, AC 3
    import json

    from tempergraph.executors.standins import standin
    from tempergraph.improve import child, loop_summary

    from .test_loop_child import blocked_run, judge_says, tickets
    from .test_run import registry

    host = MemoryCodeHost()

    def one(task: str) -> dict[str, Any]:
        blocked_run(repo, task, monkeypatch)
        (t,) = tickets()
        doc = json.loads(t.read_text())
        t.write_text(json.dumps({**doc, "issue_repository": REPO}))
        (out,) = child.drain(registry=registry(standin("claude", judges=[judge_says(0.9)])), host=lambda: host)
        return out

    assert [r["op"] for r in one("M-1")["results"] if r["op"] != "recorded"] == ["filed"]
    host.close(REPO, 1, "not_planned", (datetime.now(UTC) - timedelta(days=10)).isoformat())
    out = one("M-2")
    assert [r["op"] for r in out["results"] if r["op"] != "recorded"] == ["muted"] and len(host.issues) == 1
    root = repo / ".tempergraph"
    log = [json.loads(ln) for ln in child.loop_log(root, "demo", "M-2").read_text().splitlines()]
    (muted,) = [r for r in log if r["kind"] == "loop_result" and r.get("op") == "muted"]
    assert muted["url"] == host.issues[0]["url"] and not [r for r in log if r["kind"] == "issue_filed"]
    assert [r for r in log if r["kind"] == "loop_summary"][0]["filed"] == 0
    assert {"filed", "commented"} == loop_summary.FILED_OPS


def test_gh_list_read_lowers_the_reason_and_skips_pull_requests(monkeypatch: pytest.MonkeyPatch) -> None:
    # ISS-B3, ISS-AC9
    import json

    seen: list[list[str]] = []
    rows = [{"number": 4, "html_url": "u", "body": "b", "state_reason": "NOT_PLANNED", "closed_at": "2026-11-01T00:00:00Z"},
            {"number": 5, "html_url": "v", "body": None, "state_reason": None, "closed_at": None},
            {"number": 6, "html_url": "w", "body": "pr", "pull_request": {"url": "x"}}]

    def fake(self: GhCodeHost, args: list[str], payload: Any = None) -> str:
        seen.append(args)
        return "\n".join(json.dumps(r) for r in rows) + "\n"

    monkeypatch.setattr(GhCodeHost, "_run", fake)
    got = GhCodeHost().loop_issues(REPO, "closed")
    assert [g["number"] for g in got] == [4, 5]  # a pull request is not an issue
    assert [g["state_reason"] for g in got] == ["not_planned", ""] and got[0]["closed_at"] == "2026-11-01T00:00:00Z"
    args = seen[0]
    assert "search" not in " ".join(args) and "issue" not in args  # the REST list, never the search index or GraphQL
    assert f"repos/{REPO}/issues" in args and "state=closed" in args and "labels=tempergraph-loop" in args
    assert "--paginate" in args


# -- phase 5: the documents say what is built -----------------------------------------------------------------

def test_the_documents_say_what_is_built_and_l17_has_a_case_not_run() -> None:  # AC 4, task i1
    from .conftest import DOCS, REPO_ROOT

    runbook = (DOCS / "plans" / "live-checks.plan.md").read_text(encoding="utf-8")
    row = next(ln for ln in runbook.splitlines() if ln.startswith("| L-17 | Filing through"))
    assert "not planned" in row and "muted" in row and "ISS-AC3" in row
    result = next(ln for ln in runbook.splitlines() if ln.startswith("| L-17 | 20"))
    assert "not planned" in result and "not run" in result
    contributing = (REPO_ROOT / "CONTRIBUTING.md").read_text(encoding="utf-8")
    assert "reads close reasons (#1)" not in contributing and "#1 tracks making the loop read" not in contributing
    assert "needs-triage" in contributing.split("### 5.4", 1)[1] and "Closes #<n>" in contributing.split("### 5.4", 1)[1]
    guide = (DOCS / "guides" / "improving-workflows.guide.md").read_text(encoding="utf-8")
    for word in ("issue_labels", "## Summary", "not planned", "possible regression", "Closes #<n>"):
        assert word in guide


# -- phase 4: a finished trial leaves one comment on each issue of its cluster ---------------------------------

MINE = "https://example.test/acme/release-notes/issues/7"
OTHER = "https://example.test/dbr0vskyi/tempergraph/issues/3"
MARKER_LINE = "<!-- tg-agent: kind=result agent=loop -->"


@pytest.fixture
def pkg(repo: Path) -> Path:
    from .fixtures.packages import minimal_package
    from .test_proposals import git

    root = minimal_package(repo / "workflows")
    git(repo, "add", "-A")
    git(repo, "commit", "-q", "-m", "package")
    return root


def trialled(repo: Path, pkg: Path, issues: list[str]) -> tuple[Path, Any, dict[str, Any]]:
    """A person's proposal on a cluster holding `issues`, trialled on fake arms: 9 wins, 1 loss, 4 ties."""
    from tempergraph.improve import proposals as prp
    from tempergraph.improve import trials as trl
    from tempergraph.package.loader import load
    from tempergraph.store.layout import state_root_path

    from .test_proposals import CLUSTER, PROMPT, RULE, cases, fake_runner, patch

    cases(pkg, 14)
    root, spec = state_root_path(repo), load(pkg)
    rec = prp.record(root, spec, {**CLUSTER, "issues": issues}, patch(pkg, {"prompts/draft.md": PROMPT}),
                     author="person", rule=RULE)
    a = [0] * 14
    a[9] = 1
    out = trl.trial(root, spec, rec["proposal_id"], fake_runner({"A": a, "B": [1] * 9 + [0] + [0] * 4}))
    assert out["decision"] == "shown_better"
    return root, spec, out


def test_a_trial_result_is_one_agent_comment_on_each_issue(repo: Path, pkg: Path) -> None:  # PRP-AC9; AC 1, AC 3
    from tempergraph.improve import trials as trl

    root, _spec, out = trialled(repo, pkg, [MINE, OTHER])
    out["pairs"][0]["case"] = CANARY  # run text never reaches the comment
    out["note"] = CANARY
    host = MemoryCodeHost()
    trl.comment_result(root, out, host, autonomy="file")
    assert [(c["repo"], c["number"]) for c in host.comments] == [("acme/release-notes", 7), ("dbr0vskyi/tempergraph", 3)]
    text = host.comments[0]["body"]
    lines = text.splitlines()
    assert lines[0] == MARKER_LINE and lines[-1] == "_Generated by [Claude Code](https://claude.ai/code)_"
    assert "shown_better" in text and "9 wins, 1 losses, 4 ties" in text and "Guards:" in text
    assert out["trial_id"] in text and CANARY not in text
    assert host.comments[1]["body"] == text
    for decision, reason in (("not_shown", "too_few_pairs"), ("regressed", "losses"), ("aborted", "cap_reached")):
        more = MemoryCodeHost()  # every decision comments, not only a win
        trl.comment_result(root, {**out, "decision": decision, "reason": reason}, more, autonomy="trial")
        assert len(more.comments) == 2 and decision in more.comments[0]["body"] and reason in more.comments[0]["body"]


@pytest.mark.parametrize("level", ["record", "off"])
def test_no_comment_at_autonomy_record(repo: Path, pkg: Path, level: str) -> None:  # PRP-AC9; AC 1, AC 3
    from tempergraph.improve import trials as trl

    root, _spec, out = trialled(repo, pkg, [MINE])
    host = MemoryCodeHost(down=True)  # any call would raise
    trl.comment_result(root, out, host, autonomy=level)
    assert not Outbox.at(root).path.exists()
    up = MemoryCodeHost()
    trl.comment_result(root, out, up, autonomy="propose")
    assert len(up.comments) == 1
    no_issue = trialled_no_issue(root, out)
    trl.comment_result(root, no_issue, up, autonomy="file")
    assert len(up.comments) == 1  # a cluster with no issue has nothing to comment on


def trialled_no_issue(root: Path, out: dict[str, Any]) -> dict[str, Any]:
    from tempergraph.improve import proposals as prp

    rec = prp.load_proposal(root, out["proposal_id"])
    rec["cluster"] = {**rec["cluster"], "issues": []}
    prp.save(root, rec)
    return out


def test_a_down_host_queues_the_comment_and_keeps_the_decision(repo: Path, pkg: Path) -> None:
    # PRP-AC9, SIL-B19; AC 1, AC 3
    from tempergraph.improve import trials as trl

    root, _spec, out = trialled(repo, pkg, [MINE, OTHER])
    trl.comment_result(root, out, MemoryCodeHost(down=True), autonomy="file")
    assert trl.load_trial(root, out["trial_id"])["decision"] == "shown_better"
    assert len(Outbox.at(root).path.read_text().splitlines()) == 2
    host = MemoryCodeHost()
    results = filing.file([], host, Outbox.at(root))
    assert [r["op"] for r in results] == ["redelivered", "redelivered"] and len(host.comments) == 2
    assert host.comments[0]["body"].splitlines()[0] == MARKER_LINE


def test_improve_trial_leaves_the_comment(repo: Path, pkg: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    # PRP-AC9; AC 1, AC 3
    from tempergraph.catalog import Catalog
    from tempergraph.cli import improve as cli_improve
    from tempergraph.improve import proposals as prp
    from tempergraph.improve.codehost import MemoryCodeHost as Host
    from tempergraph.package.loader import load
    from tempergraph.store.layout import state_root_path

    from .test_cli import cli
    from .test_proposals import CLUSTER, PROMPT, RULE, cases, fake_runner, patch

    cases(pkg, 14)
    root, spec = state_root_path(repo), load(pkg)
    rec = prp.record(root, spec, {**CLUSTER, "issues": [MINE]}, patch(pkg, {"prompts/draft.md": PROMPT}),
                     author="person", rule=RULE)
    a = [0] * 14
    a[9] = 1
    host = Host()
    monkeypatch.setattr(cli_improve, "_host", lambda: host)
    monkeypatch.setattr(cli_improve, "_arm_runner", lambda env: fake_runner({"A": a, "B": [1] * 9 + [0] + [0] * 4}))
    monkeypatch.delenv("TEMPERGRAPH_AUTONOMY", raising=False)
    code, doc, err = cli(repo, None, "improve", "trial", rec["proposal_id"], "--json",
                         catalog=Catalog(specs={spec.name: spec}))
    assert code == 0, err
    assert doc["decision"] == "shown_better"
    assert [(c["repo"], c["number"]) for c in host.comments] == [("acme/release-notes", 7)]
    assert host.comments[0]["body"].splitlines()[0] == MARKER_LINE and doc["trial_id"] in host.comments[0]["body"]
    monkeypatch.setenv("TEMPERGRAPH_AUTONOMY", "record")  # the machine lowers the level: no comment
    rec2 = prp.record(root, spec, {**CLUSTER, "issues": [MINE]}, patch(pkg, {"prompts/draft.md": PROMPT + "\n"}),
                      author="person", rule=RULE)
    code, doc, err = cli(repo, None, "improve", "trial", rec2["proposal_id"], "--json",
                         catalog=Catalog(specs={spec.name: spec}))
    assert code == 0, err
    assert len(host.comments) == 1
