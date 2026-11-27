"""Stable mode's daily cap and the loop's own proposals and trials (SIL-B19, SIL-B20, PRP-B11, PRP-B8; plan T12.8)."""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any

import pytest

from tempergraph.constants import ExitCode
from tempergraph.executors.standins import standin
from tempergraph.improve import autonomy, child
from tempergraph.improve import proposals as prp
from tempergraph.improve import trials as trl
from tempergraph.improve.codehost import MemoryCodeHost
from tempergraph.store.layout import now_iso

from .test_loop_child import blocked_run, judge_says, tickets
from .test_run import DRAFT, REVIEW, judge, registry


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


def test_daily_cap_skips_the_judges_and_records(repo: Path, monkeypatch: pytest.MonkeyPatch) -> None:  # SIL-B19, SIL-B20, SIL-AC10
    stable_ticket(repo, "A-1", monkeypatch)
    root = repo / ".tempergraph"
    ledger(root, {"kind": "loop", "workflow": "demo", "cost": {"reported": 50.0}})
    ex = standin("claude")  # no scripted judge: a judge session would fail the test
    (out,) = child.drain(registry=registry(ex), host=MemoryCodeHost)
    assert not ex.calls and all(r["op"] == "recorded" for r in out["results"])
    log = [json.loads(ln) for ln in child.loop_log(root, "demo", "A-1").read_text().splitlines()]
    assert {"kind": "loop_skipped", "step": "judges", "reason": "daily_cap"}.items() <= next(
        r for r in log if r["kind"] == "loop_skipped").items()


def test_daily_cap_leaves_a_count_met_finding_not_judged(repo: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    # SIL-AC35 (SIL-B35, SIL-B20), AC 6: the pattern count alone files nothing when the cap skipped the judge
    from tempergraph.improve import record

    stable_ticket(repo, "A-4", monkeypatch)
    root = repo / ".tempergraph"
    doc = json.loads(tickets()[0].read_text())
    mine = [f for f in record.read_findings(root, "demo", "A-4") if f.get("fingerprint") in doc["fingerprints"]]
    assert mine and all(f.get("class") == "fault" for f in mine)
    for n in range(3):  # the same fingerprints recorded in three other runs, each with its own request
        path = record.findings_path(root, "demo", f"H-{n}")
        path.parent.mkdir(parents=True, exist_ok=True)
        rows = [{**f, "thread": f"demo/H-{n}", "request_digest": f"h{n}", "at": now_iso()} for f in mine]
        path.write_text(json.dumps({"schema_version": 1, "thread": f"demo/H-{n}", "findings": rows}))
    ledger(root, {"kind": "loop", "workflow": "demo", "cost": {"reported": 50.0}})
    host = MemoryCodeHost()
    ex = standin("claude")  # no scripted judge: a judge session would fail the test
    (out,) = child.drain(registry=registry(ex), host=lambda: host)
    assert not ex.calls and not host.issues and not host.comments
    assert out["results"] and all(r["op"] == "recorded" for r in out["results"])
    assert {r["reason"] for r in out["results"]} == {"not_judged"}


def test_autonomy_record_files_nothing(repo: Path, monkeypatch: pytest.MonkeyPatch) -> None:  # PRP-B11
    stable_ticket(repo, "A-2", monkeypatch, autonomy="record")
    host = MemoryCodeHost(down=True)  # any call would raise
    (out,) = child.drain(registry=registry(standin("claude", judges=[judge_says(0.9)])), host=lambda: host)
    assert out["results"] and {r["reason"] for r in out["results"]} == {"autonomy_record"} and not host.issues


def test_prp_ac16_the_level_is_the_lowest_of_the_declared_the_machine_and_the_setting() -> None:
    # PRP-AC16 (PRP-B31): `prp.autonomy(spec, machine, setting)`
    from .fixtures.workflows import two_step

    spec = two_step()  # declares nothing: `file`
    assert prp.autonomy(spec) == "file" and prp.autonomy(spec, "record") == "record"
    assert prp.autonomy(spec, None, "record") == "record"
    assert prp.autonomy(spec, "record", "trial") == "record" and prp.autonomy(spec, "trial", "record") == "record"
    assert prp.autonomy(spec, None, "trial") == "file"  # a setting never raises the level
    assert prp.autonomy(spec, "bogus", "nonsense") == "file" and prp.autonomy(spec, None, None) == "file"


def paused_then_resumed(repo: Path, monkeypatch: pytest.MonkeyPatch, task: str, between: Any = None,
                        *argv: str, catalog: Any = None) -> dict[str, Any]:
    """A thread with one blocked attempt, paused at the next judge; `between` runs before it is resumed to its final
    exit. Returns the ticket the final exit wrote."""
    from .test_cli import cli
    from .test_run import verdict_block

    monkeypatch.setenv("TEMPERGRAPH_LOOP", "detached")
    monkeypatch.setattr("tempergraph.detach.start", lambda *a, **k: True)
    ex = standin("claude", steps=[DRAFT, DRAFT], judges=[judge(verdict_block("UNMET")),
                                                         judge(verdict_block("UNVERIFIABLE"))])
    code, _, err = cli(repo, ex, "run", "demo", "notes", "--task-id", task, catalog=catalog)
    assert code == ExitCode.PAUSED, err
    assert not tickets()  # no final exit yet
    if between is not None:
        between()
    ex.steps, ex.judges = [REVIEW], [judge()]
    code, _, err = cli(repo, ex, "resume", "demo", task, "--decision", "proceed", *argv, catalog=catalog)
    assert code == 0, err
    (t,) = tickets()
    return json.loads(t.read_text())


def write_setting(repo: Path, **values: str) -> None:
    from tempergraph.settings import config_paths
    from tempergraph.store.layout import home_path, state_root_path

    path = config_paths(state_root_path(repo), home_path())[0]
    assert path is not None
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps({"schema_version": 1, "defaults": {f"run.{k}": v for k, v in values.items()}}))


def test_prp_ac16_a_setting_written_while_the_thread_is_paused_holds_its_final_exit(
        repo: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    # PRP-AC16 (PRP-B31), RST-AC1 (RST-B20): the thread started without the setting; the file is written before the exit
    t = paused_then_resumed(repo, monkeypatch, "H-1", lambda: write_setting(repo, loop_autonomy="record"))
    assert t["autonomy"] == "record" and t["lenses"]["friction"]
    t_path = tickets()[0]
    t_path.write_text(json.dumps({**t, "issue_repository": "team/notes", "review": "off"}))
    host = MemoryCodeHost(down=True)  # any call would raise
    (out,) = child.drain(registry=registry(standin("claude", judges=[judge_says(0.9)])), host=lambda: host)
    assert out["results"] and {r["reason"] for r in out["results"]} == {"autonomy_record"}
    assert not host.issues and not host.comments


def test_prp_ac16_the_setting_is_read_again_so_a_removed_one_leaves_the_declared_level(
        repo: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    # PRP-AC16 (PRP-B31): written at the start of the thread, removed before the exit
    from tempergraph.settings import config_paths
    from tempergraph.store.layout import home_path, state_root_path

    def remove() -> None:
        path = config_paths(state_root_path(repo), home_path())[0]
        assert path is not None
        path.unlink()

    write_setting(repo, loop_autonomy="record")
    t = paused_then_resumed(repo, monkeypatch, "H-2", remove)
    assert t["autonomy"] == "file"


def test_prp_ac16_a_setting_never_raises_a_workflow_declared_at_record(repo: Path,
                                                                        monkeypatch: pytest.MonkeyPatch) -> None:
    # PRP-AC16 (PRP-B31): `trial` leaves a workflow declared at `record` at `record`
    import dataclasses

    pkg = repo / "pkg"
    pkg.mkdir()
    (pkg / "tempergraph.json").write_text(json.dumps({"improvement": {"autonomy": "record"}}))
    real = prp.autonomy  # the run's spec is no package (the preflight would refuse a bare one): only the declared level is
    monkeypatch.setattr(prp, "autonomy", lambda spec, machine=None, setting=None: real(
        dataclasses.replace(spec, package_root=pkg), machine, setting))
    t = paused_then_resumed(repo, monkeypatch, "H-3", lambda: write_setting(repo, loop_autonomy="trial"))
    assert t["autonomy"] == "record"


def test_prp_ac16_a_stops_exit_reads_the_setting_too(repo: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    # PRP-AC16 (PRP-B31, SIL-B27): the stop of a paused thread is an exit; the setting is written while it waits
    from .test_stop_at_pause import loop_on, paused_on_retries, stop
    from .test_stop_at_pause import tickets as stop_tickets

    loop_on(monkeypatch)
    ex = paused_on_retries(repo, "P-9")
    assert stop_tickets() == []
    write_setting(repo, loop_autonomy="record")
    assert stop(repo, "P-9", ex).exit_code is ExitCode.STOPPED
    (path,) = stop_tickets()
    assert json.loads(path.read_text())["autonomy"] == "record"


def test_prp_ac16_a_lost_runners_exit_reads_the_setting_too(repo: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    # PRP-AC16 (PRP-B31, SIL-B30): the exit recorded for a lost runner has no settings of its own
    from .test_lost_runner import kill, loop_on, verb
    from .test_lost_runner import tickets as lost_tickets

    loop_on(monkeypatch)
    kill(repo, "T-9")
    write_setting(repo, loop_autonomy="record")
    code, _, err = verb(repo, "status")
    assert code == 0, err
    (t,) = [x for x in lost_tickets() if x["thread"] == "demo/T-9"]
    assert t["trigger"] == "runner_lost" and t["autonomy"] == "record"


def test_the_loop_proposes_only_in_stable_mode_and_once_a_day(repo: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    stable_ticket(repo, "A-3", monkeypatch, autonomy="propose", package_root=None)
    t = json.loads(tickets()[0].read_text())
    log = repo / "loop.jsonl"
    assert autonomy.act({**t, "mode": "dev"}, None, None, log)["proposal"] is None
    assert autonomy.act(t, None, None, log)["proposal"] is None  # no package root
    assert autonomy.act({**t, "package_root": "x", "dry_run": True}, None, None, log)["proposal"] is None
    reasons = [json.loads(ln)["reason"] for ln in log.read_text().splitlines()]
    assert reasons == ["no_package", "dry_run"]


def _fake(monkeypatch: pytest.MonkeyPatch, decision: str | None, issues: list[str] | None = None) -> list[str]:
    opened: list[str] = []
    monkeypatch.setattr("tempergraph.package.loader.load", lambda p: __import__(
        "tests.fixtures.workflows", fromlist=["two_step"]).two_step())
    monkeypatch.setattr(prp, "propose", lambda root, spec, cl, ex, **kw: {
        "proposal_id": "p1", "state": "drafted", "workflow": "demo", "at": now_iso(), "spend": {"reported": 1.0},
        "cluster": cl if issues is None else {**cl, "issues": issues}})
    monkeypatch.setattr(prp, "open_pr", lambda root, spec, pid, host: opened.append(pid) or {"pull_request": "u"})
    if decision is not None:
        monkeypatch.setattr(trl, "trial", lambda root, spec, pid, run_arm, **kw: {
            "trial_id": "t1", "decision": decision, "workflow": "demo", "at": now_iso(), "spend": {"total": 3.0},
            "cap": kw.get("cap_usd"), "proposal_id": pid})
    return opened


@pytest.mark.parametrize(("level", "decision", "prs"), [("propose", None, 1), ("trial", "shown_better", 1),
                                                         ("trial", "not_shown", 0)])
def test_propose_and_trial_levels(repo: Path, monkeypatch: pytest.MonkeyPatch, level: str, decision: str | None,
                                  prs: int) -> None:  # PRP-B11, PRP-B8
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


ISSUES = ["https://example.test/acme/notes/issues/7", "https://example.test/other/repo/issues/2"]


@pytest.mark.parametrize(("level", "decision", "comments", "prs"), [("trial", "shown_better", 2, 1),
                                                                    ("trial", "not_shown", 2, 0),
                                                                    ("trial", "regressed", 2, 0),
                                                                    ("propose", None, 0, 1)])
def test_the_loops_own_trial_comments_on_its_issues(repo: Path, monkeypatch: pytest.MonkeyPatch, level: str,
                                                    decision: str | None, comments: int, prs: int) -> None:
    # PRP-AC9, PRP-AC8, PRP-B24, PRP-B25; task AC 1, AC 3
    stable_ticket(repo, f"A-c-{level}-{decision}", monkeypatch, autonomy=level, package_root=str(repo))
    t = json.loads(tickets()[0].read_text())
    real = prp.open_pr
    _fake(monkeypatch, decision, ISSUES)
    monkeypatch.setattr(prp, "open_pr", lambda root, spec, pid, host: real(root, spec, pid, host, push=False))
    host = MemoryCodeHost()
    root = repo / ".tempergraph"
    out = autonomy.act(t, registry(standin("claude")), host, root / "l.jsonl")
    assert out["proposal"] == "p1" and len(host.comments) == comments and len(host.pulls) == prs
    if comments:  # one result comment on each issue of the cluster, whatever the decision
        assert [(c["repo"], c["number"]) for c in host.comments] == [("acme/notes", 7), ("other/repo", 2)]
        assert all(c["body"].startswith("<!-- tg-agent: kind=result agent=loop -->") and decision in c["body"]
                   for c in host.comments)
    if prs:  # PRP-B24: `Closes` for the issue of the pull request's repository only
        assert host.pulls[0]["body"].count("Closes #7") == 1 and "Closes #2" not in host.pulls[0]["body"]


def test_a_failed_trial_comment_never_stops_the_pull_request(repo: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    # PRP-B25; task AC 1
    stable_ticket(repo, "A-c-fail", monkeypatch, autonomy="trial", package_root=str(repo))
    t = json.loads(tickets()[0].read_text())
    opened = _fake(monkeypatch, "shown_better", ISSUES)

    def boom(*a: Any, **k: Any) -> None:
        raise RuntimeError("no")

    monkeypatch.setattr(trl, "comment_result", boom)
    root = repo / ".tempergraph"
    out = autonomy.act(t, registry(standin("claude")), MemoryCodeHost(), root / "l.jsonl")
    assert out["pull_request"] == "u" and opened == ["p1"]
    notes = [json.loads(ln) for ln in (root / "l.jsonl").read_text().splitlines()]
    assert {"kind": "loop_skipped", "step": "trial_comment"}.items() <= next(
        n for n in notes if n.get("step") == "trial_comment").items()


def test_report_loop(repo: Path, monkeypatch: pytest.MonkeyPatch) -> None:  # IMD-B22, IMD-AC4 shape
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


def test_outcome_lens_starts_no_judge_of_its_own(tmp_path: Path) -> None:  # OUT-AC6
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


MISREAD = [("code.1.step", [("prompt_misread", "kept")])]


def third_run(repo: Path, level: str) -> tuple[Path, dict[str, Any]]:
    """Two earlier runs that kept `prompt_misread` on `code`, and a third whose review the loop child runs."""
    from tempergraph.store.layout import state_root_path

    from .test_review_repeat import build_code_run, write_reviews
    from .test_session_review import ticket

    root = state_root_path(repo)
    for task in ("V-1", "V-2"):
        write_reviews(root, task, MISREAD)
    build_code_run(root, "V-3", keys=("code.1.step",))
    t = {**ticket(root, "V-3"), "thread": "demo/V-3", "issue_repository": "team/notes", "ticket_id": "t3",
         "fingerprints": [], "lenses": {"friction": False, "outcome": False}, "dry_run": False, "units": {},
         "mode": "stable", "autonomy": level, "package_root": str(repo), "workflow_version": "0.0.0"}
    return root, t


def test_a_review_repeat_across_runs_is_proposed_on_at_propose(repo: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    # SRV-AC18 (SRV-B28, PRP-B23)
    from .test_review_repeat import kept_block

    root, t = third_run(repo, "propose")
    opened = _fake(monkeypatch, None)
    host = MemoryCodeHost()
    out = child.process(t, registry(standin("claude", judges=[kept_block()])), host)
    assert out["acted"]["proposal"] == "p1" and opened == ["p1"]
    saved = prp.load_proposal(root, "p1")["cluster"]
    assert saved["cause"] == "review_repeat:prompt_misread" and saved["unit"] == "code"
    assert not host.issues and not host.comments and out["results"] == []


def test_a_review_repeat_across_runs_is_only_listed_at_file(repo: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    # SRV-AC18 (SRV-B28, PRP-B23)
    from .test_review_repeat import kept_block

    root, t = third_run(repo, "file")
    opened = _fake(monkeypatch, None)
    host = MemoryCodeHost()
    out = child.process(t, registry(standin("claude", judges=[kept_block()])), host)
    assert out["acted"]["proposal"] is None and opened == []
    assert not (root / "improve" / "proposals").exists()
    assert not host.issues and not host.comments
    (c,) = prp.clusters(root, "demo")  # what `improve backlog` lists
    assert c["cause"] == "review_repeat:prompt_misread" and c["unit"] == "code"
