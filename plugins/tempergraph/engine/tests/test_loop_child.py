"""The loop child: hand-off ticket, detached start, friction judge, filing (SIL-B1, B2, B6; T12.1.5)."""

from __future__ import annotations

import dataclasses
import json
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

import pytest

from tempergraph import detach
from tempergraph.constants import ExitCode
from tempergraph.executors.standins import answer, standin
from tempergraph.improve import child, filing
from tempergraph.improve.codehost import MemoryCodeHost
from tempergraph.improve.record import read_findings
from tempergraph.store.layout import home_path

from .fixtures.workflows import two_step
from .test_run import DRAFT, REVIEW, go, judge, registry, verdict_block


def blocked_run(repo: Path, task: str, monkeypatch: pytest.MonkeyPatch, **kw: Any) -> None:
    """A run that finishes after one blocked attempt: a `judge_blocked` workflow fault at a final exit."""
    monkeypatch.setenv("TEMPERGRAPH_LOOP", "detached")
    monkeypatch.setattr(detach, "start", lambda *a, **k: True)  # the child is started by drain() below
    fail = verdict_block("UNMET")
    ex = standin("claude", steps=[DRAFT, DRAFT, REVIEW], judges=[judge(fail), judge(), judge()])
    assert go(repo, ex, task=task, **kw).exit_code is ExitCode.FINISHED


def judge_says(fp_conf: float, attributed: bool = True) -> Any:
    def reply(req: Any) -> Any:
        fps = [ln.split("`")[1] for ln in req.prompt.splitlines() if ln.startswith("- `") and "cause" in ln]
        rows = [{"fingerprint": fp, "attributed": attributed, "confidence": fp_conf} for fp in fps]
        assert "Release 1.2 notes" not in req.prompt  # metadata only: no request text reaches the judge
        assert req.alias == child.ALIAS and req.timeout_s == child.TIMEOUT_S
        return answer("```json\n" + json.dumps({"findings": rows}) + "\n```", session_id="loop")
    return reply


def tickets() -> list[Path]:
    return sorted(child.tickets_dir(home_path()).glob("*.json"))


def test_ticket_then_judged_filing(repo: Path, monkeypatch: pytest.MonkeyPatch) -> None:  # SIL-B1, B2
    blocked_run(repo, "L-1", monkeypatch)
    (t,) = tickets()
    doc = json.loads(t.read_text())
    assert doc["thread"] == "demo/L-1" and doc["fingerprints"] and doc["lenses"]["friction"]
    assert "Release 1.2 notes" not in t.read_text()
    host = MemoryCodeHost()
    ex = standin("claude", judges=[judge_says(0.9)])
    root = repo / ".tempergraph"
    spec_repo = "team/notes"
    doc["issue_repository"] = spec_repo
    t.write_text(json.dumps(doc))
    (out,) = child.drain(registry=registry(ex), host=lambda: host)
    assert [r["op"] for r in out["results"] if r["op"] != "recorded"] == ["filed"]
    assert host.issues[0]["repo"] == spec_repo and filing.marker(doc["fingerprints"][0]) in host.issues[0]["body"]
    assert not tickets()  # claimed and removed
    log = [json.loads(ln) for ln in child.loop_log(root, "demo", "L-1").read_text().splitlines()]
    assert [r["kind"] for r in log][:2] == ["loop_started", "loop_judged"] and "issue_filed" in [r["kind"] for r in log]
    assert any(r.get("kind") == "loop" for r in map(json.loads, (root / "ledger.jsonl").read_text().splitlines()))
    summary = [r for r in log if r["kind"] == "loop_summary"]  # SIL-AC14: one, written when the child ends
    assert len(summary) == 1 and log[-1] is summary[0]
    assert summary[0]["recorded"] == len(read_findings(root, "demo", "L-1"))
    assert summary[0]["filed"] == len([r for r in out["results"] if r["op"] in ("filed", "commented")]) == 1
    assert summary[0]["top"] == [] and summary[0]["thread"] == "demo/L-1"
    blocked_run(repo, "L-2", monkeypatch)  # the same cause again: a comment, never a second issue
    d2 = json.loads(tickets()[0].read_text())
    d2["issue_repository"] = spec_repo
    tickets()[0].write_text(json.dumps(d2))
    (out2,) = child.drain(registry=registry(standin("claude", judges=[judge_says(0.9)])), host=lambda: host)
    assert len(host.issues) == 1 and [r["op"] for r in out2["results"] if r["op"] != "recorded"] == ["commented"]


def test_loop_started_names_the_fingerprints_it_covered(repo: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    # SIL-AC21, AC 1
    blocked_run(repo, "L-6", monkeypatch)
    (t,) = tickets()
    fps = sorted(json.loads(t.read_text())["fingerprints"])
    assert fps
    child.drain(registry=registry(standin("claude", judges=[judge_says(0.9)])), host=lambda: MemoryCodeHost())
    log = [json.loads(ln) for ln in child.loop_log(repo / ".tempergraph", "demo", "L-6").read_text().splitlines()]
    (started,) = [r for r in log if r["kind"] == "loop_started"]
    assert started["fingerprints"] == fps


def test_low_confidence_or_unparsed_is_recorded(repo: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    blocked_run(repo, "L-3", monkeypatch)
    host = MemoryCodeHost()
    (out,) = child.drain(registry=registry(standin("claude", judges=[judge_says(0.4)])), host=lambda: host)
    assert {r["reason"] for r in out["results"]} <= {"below_floor", "no_repository", "designed"} and not host.issues
    blocked_run(repo, "L-4", monkeypatch)
    (out,) = child.drain(registry=registry(standin("claude", judges=[answer("no block")])), host=lambda: host)
    assert all(r["op"] == "recorded" for r in out["results"]) and not host.issues


def test_dry_run_files_nothing(repo: Path, monkeypatch: pytest.MonkeyPatch) -> None:  # SIL-B6
    blocked_run(repo, "L-5", monkeypatch, dry_run=True)
    d = json.loads(tickets()[0].read_text())
    assert d["dry_run"] is True
    d["issue_repository"] = "team/notes"
    tickets()[0].write_text(json.dumps(d))
    host = MemoryCodeHost(down=True)  # any call would raise
    (out,) = child.drain(registry=registry(standin("claude", judges=[judge_says(0.9)])), host=lambda: host)
    assert "would_file" in {r["op"] for r in out["results"]} and not host.issues


def test_no_ticket_without_a_fault_and_off_switch(repo: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("TEMPERGRAPH_LOOP", "detached")
    started: list[tuple[str, ...]] = []
    monkeypatch.setattr(detach, "start", lambda m, w, h: started.append((m, *w)) or True)
    ex = standin("claude", steps=[DRAFT, REVIEW], judges=[judge(), judge()])
    quiet = dataclasses.replace(two_step(), session_review="off")  # a dev run's session review is a ticket too
    assert go(repo, ex, spec=quiet, task="L-6").exit_code is ExitCode.FINISHED
    assert not tickets() and not started
    blocked_run(repo, "L-7", monkeypatch)
    monkeypatch.setenv("TEMPERGRAPH_LOOP", "off")
    ex = standin("claude", steps=[DRAFT, DRAFT, REVIEW], judges=[judge(verdict_block("UNMET")), judge(), judge()])
    n = len(tickets())
    assert go(repo, ex, task="L-8").exit_code is ExitCode.FINISHED and len(tickets()) == n


def test_detached_site_is_constant() -> None:  # SEC-B7
    assert detach.DETACHED["tempergraph.improve.child"] == (("drain",),)
    assert child.main(["other"]) == 2


def test_a_failing_ticket_never_stops_the_next(repo: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    folder = child.tickets_dir(home_path())
    folder.mkdir(parents=True, exist_ok=True)
    (folder / "bad.json").write_text("{nope")
    out = child.drain(registry=registry(standin("claude")), host=MemoryCodeHost)
    assert out == [{"ticket": "bad", "error": "JSONDecodeError"}] and not list(folder.iterdir())


def outcome_ticket(root: Path, n: int, calibrated: bool) -> dict[str, Any]:
    from tempergraph.improve import record

    fp = record.fingerprint("workflow", "demo", "outcome_unmet:c-1", "outcome")
    f = {"kind": "finding", "thread": f"demo/O-{n}", "workflow": "demo", "unit": "outcome", "lens": "outcome",
         "cause": "outcome_unmet:c-1", "class": "fault", "side": "workflow", "count": 1, "remedy": "r",
         "fingerprint": fp, "at": datetime.now(UTC).isoformat(timespec="seconds"), "request_digest": f"r{n}", "machine": "m"}
    path = record.findings_path(root, "demo", f"O-{n}")
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps({"schema_version": 1, "thread": f"demo/O-{n}", "findings": [f]}))
    return {"ticket_id": f"t{n}", "thread": f"demo/O-{n}", "workflow": "demo", "task_id": f"O-{n}",
            "state_root": str(root), "issue_repository": "team/notes", "dry_run": False, "executor": "claude",
            "fingerprints": [fp], "lenses": {"friction": False, "outcome": True}, "outcome_calibrated": calibrated}


def test_outcome_lens_files_only_when_calibrated_and_patterned(tmp_path: Path) -> None:  # SIL-B3, B7
    root = tmp_path / ".tempergraph"
    host = MemoryCodeHost()
    reg = registry(standin("claude"))  # no session is scripted: the outcome gate's judge already graded it
    out = child.process(outcome_ticket(root, 1, calibrated=False), reg, host)
    assert [r["reason"] for r in out["results"]] == ["uncalibrated"] and not host.issues
    out = child.process(outcome_ticket(root, 2, calibrated=True), reg, host)
    assert [r["reason"] for r in out["results"]] == ["pattern_not_met"] and not host.issues  # two runs so far
    out = child.process(outcome_ticket(root, 3, calibrated=True), reg, host)
    assert [r["op"] for r in out["results"]] == ["filed"] and host.issues[0]["repo"] == "team/notes"
    out = child.process(outcome_ticket(root, 4, calibrated=True), reg, host)
    assert [r["op"] for r in out["results"]] == ["commented"] and len(host.issues) == 1


def test_hand_off_carries_calibration(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    from tempergraph.improve import calibration

    from .fixtures.workflows import two_step

    monkeypatch.setattr(calibration, "has_score", lambda spec, gate, root=None: gate == "outcome")
    summary = {"lenses": {"friction": False}, "fault_fingerprints": [], "outcome_fingerprints": ["abc"],
               "fingerprints": ["abc"]}
    p = child.hand_off(tmp_path, two_step(), "T-1", "demo/T-1", summary, dry_run=False, judge_executor="claude",
                       home=tmp_path / "home")
    assert p is not None and json.loads(p.read_text())["outcome_calibrated"] is True
    none = {"lenses": {"friction": True}, "fault_fingerprints": [], "outcome_fingerprints": [], "fingerprints": []}
    quiet = dataclasses.replace(two_step(), session_review="off")  # else a dev run's review writes a ticket
    assert child.hand_off(tmp_path, quiet, "T-2", "demo/T-2", none, dry_run=False, judge_executor="claude",
                          home=tmp_path / "home") is None
