"""Stable mode's daily cap and the loop's own proposals and trials (SIL §4, PRP §2.1, PRP-B8; plan T12.8)."""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any

import pytest

from tempergraph.executors.standins import standin
from tempergraph.improve import autonomy, child
from tempergraph.improve import proposals as prp
from tempergraph.improve import trials as trl
from tempergraph.improve.codehost import MemoryCodeHost
from tempergraph.store.layout import now_iso

from .test_loop_child import blocked_run, judge_says, tickets
from .test_run import registry


def ledger(root: Path, *rows: dict[str, Any]) -> None:
    root.mkdir(parents=True, exist_ok=True)
    with (root / "ledger.jsonl").open("a") as fh:
        for r in rows:
            fh.write(json.dumps({"ts": now_iso(), **r}) + "\n")


def test_day_spend_and_room(tmp_path: Path) -> None:
    ledger(tmp_path, {"kind": "loop", "workflow": "demo", "cost": {"reported": 30.0, "estimated_only": 5.0}},
           {"kind": "loop", "workflow": "other", "cost": {"reported": 99.0}},
           {"kind": "loop", "workflow": "demo", "ts": "2020-01-01T00:00:00Z", "cost": {"reported": 99.0}})
    (tmp_path / "improve" / "proposals").mkdir(parents=True)
    (tmp_path / "improve" / "proposals" / "p.json").write_text(json.dumps(
        {"workflow": "demo", "author": "loop", "at": now_iso(), "spend": {"reported": 2.0}}))
    assert autonomy.day_spend(tmp_path, "demo") == 37.0
    t = {"workflow": "demo", "mode": "stable", "daily_cap_usd": 50}
    assert autonomy.room(t, tmp_path) == 13.0
    assert autonomy.room({**t, "mode": "dev"}, tmp_path) is None  # dev mode is not capped
    assert autonomy.daily_cap("stable", None) == 50 and autonomy.daily_cap("stable", 10) == 10
    assert autonomy.daily_cap("dev", 10) is None  # dev mode has no daily limit


def test_daily_cap_from_the_workflow_and_the_command_line(repo: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    import dataclasses

    from .fixtures.workflows import two_step
    from .test_run import DRAFT, REVIEW, judge, verdict_block

    monkeypatch.setenv("TEMPERGRAPH_LOOP", "detached")
    monkeypatch.setattr("tempergraph.detach.start", lambda *a, **k: True)
    from tempergraph.run.runner import RunSettings, start

    spec = dataclasses.replace(two_step(), improvement_mode="stable", daily_cap_usd=12.0)
    fail = verdict_block("UNMET")

    def go(task: str, flags: dict[str, Any]) -> dict[str, Any]:
        for t in tickets():
            t.unlink()
        ex = standin("claude", steps=[DRAFT, DRAFT, REVIEW], judges=[judge(fail), judge(), judge()])
        start(spec, task, {"request": "notes"}, repo, registry(ex), RunSettings(sleep=lambda s: None, flags=flags))
        return json.loads(tickets()[0].read_text())

    assert go("C-1", {})["daily_cap_usd"] == 12.0  # the workflow's
    assert go("C-2", {"run.daily_cap_usd": 3})["daily_cap_usd"] == 3  # the command line's, a flag


def stable_ticket(repo: Path, task: str, monkeypatch: pytest.MonkeyPatch, **extra: Any) -> Path:
    blocked_run(repo, task, monkeypatch)
    t = tickets()[0]
    doc = json.loads(t.read_text())
    doc.update({"mode": "stable", "issue_repository": "team/notes", "review": "off", **extra})
    t.write_text(json.dumps(doc))
    return t


def test_daily_cap_skips_the_judges_and_records(repo: Path, monkeypatch: pytest.MonkeyPatch) -> None:  # SIL §4
    stable_ticket(repo, "A-1", monkeypatch)
    root = repo / ".tempergraph"
    ledger(root, {"kind": "loop", "workflow": "demo", "cost": {"reported": 50.0}})
    ex = standin("claude")  # no scripted judge: a judge session would fail the test
    (out,) = child.drain(registry=registry(ex), host=MemoryCodeHost)
    assert not ex.calls and all(r["op"] == "recorded" for r in out["results"])
    log = [json.loads(ln) for ln in child.loop_log(root, "demo", "A-1").read_text().splitlines()]
    assert {"kind": "loop_skipped", "step": "judges", "reason": "daily_cap"}.items() <= next(
        r for r in log if r["kind"] == "loop_skipped").items()


def test_autonomy_record_files_nothing(repo: Path, monkeypatch: pytest.MonkeyPatch) -> None:  # PRP §2.1
    stable_ticket(repo, "A-2", monkeypatch, autonomy="record")
    host = MemoryCodeHost(down=True)  # any call would raise
    (out,) = child.drain(registry=registry(standin("claude", judges=[judge_says(0.9)])), host=lambda: host)
    assert out["results"] and {r["reason"] for r in out["results"]} == {"autonomy_record"} and not host.issues


def test_the_loop_proposes_only_in_stable_mode_and_once_a_day(repo: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    stable_ticket(repo, "A-3", monkeypatch, autonomy="propose", package_root=None)
    t = json.loads(tickets()[0].read_text())
    log = repo / "loop.jsonl"
    assert autonomy.act({**t, "mode": "dev"}, None, None, log)["proposal"] is None
    assert autonomy.act(t, None, None, log)["proposal"] is None  # no package root
    assert autonomy.act({**t, "package_root": "x", "dry_run": True}, None, None, log)["proposal"] is None
    reasons = [json.loads(ln)["reason"] for ln in log.read_text().splitlines()]
    assert reasons == ["no_package", "dry_run"]


def _fake(monkeypatch: pytest.MonkeyPatch, decision: str | None) -> list[str]:
    opened: list[str] = []
    monkeypatch.setattr("tempergraph.package.loader.load", lambda p: __import__(
        "tests.fixtures.workflows", fromlist=["two_step"]).two_step())
    monkeypatch.setattr(prp, "propose", lambda root, spec, cl, ex: {
        "proposal_id": "p1", "state": "drafted", "workflow": "demo", "cluster": cl, "at": now_iso(),
        "spend": {"reported": 1.0}})
    monkeypatch.setattr(prp, "open_pr", lambda root, spec, pid, host: opened.append(pid) or {"pull_request": "u"})
    if decision is not None:
        monkeypatch.setattr(trl, "trial", lambda root, spec, pid, run_arm, **kw: {
            "trial_id": "t1", "decision": decision, "workflow": "demo", "at": now_iso(), "spend": {"total": 3.0},
            "cap": kw.get("cap_usd")})
    return opened


@pytest.mark.parametrize(("level", "decision", "prs"), [("propose", None, 1), ("trial", "shown_better", 1),
                                                         ("trial", "not_shown", 0)])
def test_propose_and_trial_levels(repo: Path, monkeypatch: pytest.MonkeyPatch, level: str, decision: str | None,
                                  prs: int) -> None:  # PRP §2.1, PRP-B8
    stable_ticket(repo, f"A-{level}-{decision}", monkeypatch, autonomy=level, package_root=str(repo))
    t = json.loads(tickets()[0].read_text())
    opened = _fake(monkeypatch, decision)
    root = repo / ".tempergraph"
    out = autonomy.act(t, registry(standin("claude")), MemoryCodeHost(), root / "l.jsonl")
    assert out["proposal"] == "p1" and len(opened) == prs
    saved = prp.load_proposal(root, "p1")
    assert saved["author"] == "loop"
    if decision:
        assert out["trial"] == "t1" and trl.load_trial(root, "t1")["author"] == "loop"
    assert autonomy.act(t, registry(standin("claude")), MemoryCodeHost(), root / "l.jsonl")["proposal"] is None
    assert "one_per_day" in (root / "l.jsonl").read_text()
    assert autonomy.day_spend(root, "demo") >= 1.0


def test_report_loop(repo: Path, monkeypatch: pytest.MonkeyPatch) -> None:  # IMD §2.4, IMD-AC-4 shape
    from tempergraph.improve import loop_report

    from .test_cli import cli

    blocked_run(repo, "R-1", monkeypatch)
    child.drain(registry=registry(standin("claude", judges=[judge_says(0.9)])), host=MemoryCodeHost)
    root = repo / ".tempergraph"
    (root / "improve" / "trials").mkdir(parents=True, exist_ok=True)
    (root / "improve" / "trials" / "t.json").write_text(json.dumps(
        {"workflow": "demo", "decision": "shown_better", "at": now_iso(), "spend": {"total": 4.0}}))
    doc = loop_report.report(root, ["demo"], None, lambda w: ["reliable", "unmeasured"])
    (w,) = doc["workflows"]
    assert w["funnel"]["findings"] >= 1 and w["funnel"]["clusters"] >= 1 and w["funnel"]["trials"] == 1
    assert w["funnel"]["shown_better"] == 1 and w["funnel"]["merged"] is None
    assert w["loop_spend"]["trials"]["estimated"] == 4.0 and w["loop_spend"]["children"]["reported"] > 0
    assert w["issue_precision"]["value"] is None and w["issue_precision"]["not_derived"]
    assert w["label_coverage"] == {"reliable": 0.5, "unmeasured": 0.5, "unreliable": 0.0}
    assert {p["name"] for p in doc["params"]} >= {"stable.daily_cap_usd"}
    code, out, _ = cli(repo, None, "report", "--loop", "all", "--json")
    assert code == 0 and out["workflows"][0]["workflow"] == "demo"
    code, out, _ = cli(repo, None, "report", "--loop")
    assert code == 0 and "loop report" in out and "not derived" in out


def test_outcome_lens_starts_no_judge_of_its_own(tmp_path: Path) -> None:  # OUT-AC-6
    from tempergraph.improve.record import findings_path
    from tempergraph.run.log import Ledger

    p = findings_path(tmp_path, "demo", "O-1")
    p.parent.mkdir(parents=True, exist_ok=True)
    f = {"kind": "finding", "thread": "demo/O-1", "unit": "outcome", "cause": "outcome_unmet:c1", "class": "fault",
         "side": "workflow", "count": 1, "fingerprint": "f1", "lens": "outcome", "at": now_iso()}
    p.write_text(json.dumps({"schema_version": 1, "thread": "demo/O-1", "findings": [f]}))
    Ledger(path=tmp_path / "ledger.jsonl")
    t = {"ticket_id": "x", "thread": "demo/O-1", "workflow": "demo", "task_id": "O-1", "state_root": str(tmp_path),
         "mode": "dev", "dry_run": False, "executor": "claude", "fingerprints": ["f1"], "issue_repository": "a/b",
         "lenses": {"friction": False, "outcome": True}, "outcome_calibrated": False, "review": "off"}
    loop_ex = standin("claude")  # no scripted judge: any loop session would fail here
    out = child.process(t, registry(loop_ex), MemoryCodeHost())
    assert not loop_ex.calls and [r["op"] for r in out["results"]] == ["recorded"]
