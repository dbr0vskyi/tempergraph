"""Stages of a run, `promote-check` and the promotion stamp (PRO-B7, PRO-B4, PRO-B10, PRO-AC1 to AC-4, AC-6)."""

from __future__ import annotations

import dataclasses
import io
import json
from pathlib import Path
from typing import Any

import pytest

from tempergraph.api import Gate, Step, Workflow
from tempergraph.catalog import Catalog
from tempergraph.cli.main import main
from tempergraph.executors.registry import Registry, default_registry
from tempergraph.improve import promotion as pro
from tempergraph.package.loader import load_package
from tempergraph.run.log import RunLog
from tempergraph.store.layout import run_dir, state_root_path

from .conftest import hash_tree
from .fixtures.packages import minimal_package
from .fixtures.workflows import crit, draft_check, named, two_step
from .test_supervision_report import record

PERSON: tuple[dict[str, str], bool] = ({}, True)
PIPELINE: tuple[dict[str, str], bool] = ({"CI": "true"}, False)


def checked(**fields: Any) -> Any:
    """A workflow whose one gate is a check: no judge binding to calibrate, so P4 holds with nothing scored."""
    c = dataclasses.replace(crit("c-file"), verified_by="check")
    spec = Workflow(order=["draft"], units={"draft": Step(
        prompt="Draft {request}", tools=["read", "write"], produces={"notes": "file"},
        gate=Gate(check=draft_check, criteria=[c]), **fields.pop("step", {}))})
    return dataclasses.replace(named(spec), **fields)


def run(root: Path, task: str, *, wf: str = "demo", version: str = "0.1.0", content: str | None = None,
        origin: str = "cli", request: str | None = None, verdicts: tuple[str, ...] = ("PROCEED",),
        exit_code: int = 0, sup: dict[str, Any] | None = None, escapes: int = 0, cost: float = 1.0,
        dry_run: bool = False, rerun_of: dict[str, Any] | None = None, climbed: bool = False,
        arm: str | None = None) -> None:
    log = RunLog(run_dir(root, wf, task) / "run.jsonl")
    log.write("run_started", workflow_version=version, origin=origin, caller={"kind": "person"},
              **({"content_version": content} if content else {}), **({"dry_run": True} if dry_run else {}),
              **({"rerun_of": rerun_of} if rerun_of else {}))
    log.write("task", chars=10, request=request if request is not None else f"request {task}")
    if arm:
        log.write("route", unit="pick", arm=arm)
    for i, v in enumerate(verdicts, 1):
        log.write("agent_run", unit="draft", attempt=i, session_kind="step" if i == 1 else "retry", executor="claude",
                  usage={"estimated_cost_usd": cost}, **({"ladder": {"rung": 1}} if climbed and i > 1 else {}))
        log.write("gate", unit="draft", verdict=v)
    for _ in range(escapes):  # a criterion that passed a gate and was later found unmet (OBS-B15)
        log.write("judgement", unit="draft", statuses=[{"id": "c1", "status": "MET"}])
        log.write("gate", unit="draft", verdict="PROCEED")
        log.write("judgement", unit="draft", statuses=[{"id": "c1", "status": "UNMET"}])
    if sup is not None:
        log.write("supervision", **{k: v for k, v in sup.items() if k != "kind"})
    log.write("run_exit", exit_code=exit_code, cost={"reported": 0, "estimated": cost, "estimated_only": 0})


def good(**extra: Any) -> dict[str, Any]:
    return record("observer", **{"supervision_share": 0.02, **extra})


def window_of(root: Path, n: int = 10, **each: Any) -> None:
    for i in range(n):
        run(root, f"t{i:02d}", **{"request": f"request {i % 4}", "sup": good(), **each})


def rows(rep: pro.Report) -> dict[str, dict[str, Any]]:
    return {c["id"]: c for c in rep.criteria}


def cli(cwd: Path, *argv: str, catalog: Catalog | None = None, signals: Any = PERSON) -> tuple[int, Any, str]:
    out, err = io.StringIO(), io.StringIO()
    code = main(list(argv), catalog=catalog, registry=default_registry() if catalog is None else Registry(),
                cwd=cwd, out=out, err=err, signals=signals)
    text = out.getvalue()
    try:
        return code, json.loads(text) if text.strip() else None, err.getvalue()
    except ValueError:
        return code, text, err.getvalue()


# -- PRO-B9: the criteria ---------------------------------------------------------------------------------------


def test_every_row_met(repo: Path) -> None:
    """PRO-B1 for `local-stable`: every measured row is met and the reported rows carry their numbers."""
    root = state_root_path(repo)
    window_of(root)
    rep = pro.check(checked(), root, to="local-stable")
    got = rows(rep)
    assert rep.met and rep.exit_code == 0, rep.criteria
    assert got["P1"]["value"] == 10 and got["P2"]["value"] == 1.0 and got["P3"]["value"] == 0
    assert got["P5.undesigned"]["value"] == 0 and got["P5.share"]["value"] == 0.02
    assert got["P6"]["verdict"] == "reported" and got["P6"]["value"] == 1.0
    assert {c["verdict"] for c in rep.criteria} == {"met", "reported"}
    assert all("bar" in c and "value" in c for c in rep.criteria)


FAILING: list[tuple[str, dict[str, Any], str]] = [
    ("P1", {"n": 9}, "not_met"),
    ("P1", {"request": "the same request"}, "not_met"),
    ("P2", {"verdicts": ("RETRY", "PROCEED")}, "not_met"),
    ("P5.undesigned", {"sup": good(rescue={"person": 2})}, "not_met"),
    ("P5.unattended", {"sup": record("consultant", supervision_share=0.02)}, "not_met"),
    ("P5.share", {"sup": good(supervision_share=0.5)}, "not_met"),
    ("P5.share", {"sup": good(supervision_share=None)}, "unmeasured"),
    ("P5.callers", {"sup": good(unknown=1)}, "not_met"),
]


@pytest.mark.parametrize(("pid", "change", "verdict"), FAILING, ids=[f"{p}-{v}-{i}" for i, (p, _, v) in enumerate(FAILING)])
def test_each_criterion_fails_alone(repo: Path, pid: str, change: dict[str, Any], verdict: str) -> None:
    """PRO-AC3: a fixture where the criterion alone fails; its row names the number and the bar."""
    root = state_root_path(repo)
    change = dict(change)
    window_of(root, change.pop("n", 10), **change)
    rep = pro.check(checked(), root, to="local-stable")
    bad = {c["id"]: c["verdict"] for c in rep.criteria if c["verdict"] not in ("met", "reported")}
    assert bad == {pid: verdict}, rep.criteria
    assert rep.exit_code == 6 and rows(rep)[pid]["bar"]
    if verdict == "not_met":
        assert rows(rep)[pid]["value"] is not None


def test_gate_escapes_fail_alone(repo: Path) -> None:
    root = state_root_path(repo)
    window_of(root, 9)
    run(root, "t99", request="request 1", sup=good(), escapes=3)
    rep = pro.check(checked(), root, to="local-stable")
    assert {c["id"] for c in rep.criteria if c["verdict"] == "not_met"} == {"P3"}
    assert rows(rep)["P3"]["value"] == 3 and rows(rep)["P3"]["bar"] == "<= 2"


def test_an_unscored_judge_fails_p4_alone(repo: Path) -> None:
    root = state_root_path(repo)
    window_of(root)
    rep = pro.check(named(two_step()), root, to="local-stable")
    assert {c["id"] for c in rep.criteria if c["verdict"] == "not_met"} == {"P4"}
    assert "draft: unscored" in rows(rep)["P4"]["detail"] and rows(rep)["P4"]["bar"] == "2 of 2 gates"


def test_a_run_without_a_supervision_record_is_unmeasured(repo: Path) -> None:
    """PRO-B2: missing data is `unmeasured`, never a pass."""
    root = state_root_path(repo)
    window_of(root, 9)
    run(root, "t99", request="request 1")
    got = rows(pro.check(checked(), root, to="local-stable"))
    assert got["P5.undesigned"]["verdict"] == got["P5.unattended"]["verdict"] == "unmeasured"
    assert "1 of 10 runs have no supervision record" in got["P5.undesigned"]["detail"]


def test_no_run_means_every_measured_row_is_unmeasured(repo: Path) -> None:
    """PRO-B6, PRO-B10, PRO-B9."""
    rep = pro.check(checked(), state_root_path(repo), to="local-stable")
    assert rep.exit_code == 6
    assert {c["verdict"] for c in rep.criteria} == {"unmeasured", "reported"}


# -- PRO-B8: the window ------------------------------------------------------------------------------------------


def test_window_takes_the_last_finished_runs_of_this_version(repo: Path) -> None:
    root = state_root_path(repo)
    window_of(root, 12)
    run(root, "x-trial", origin="trial", sup=good())
    run(root, "x-evals", origin="evals", sup=good())
    run(root, "x-dry", dry_run=True, sup=good())
    run(root, "x-old", version="0.0.9", sup=good())
    run(root, "x-paused", exit_code=3, sup=good())
    run(root, "x-rerun", origin="rerun", rerun_of={"thread_id": "demo/x-trial", "origin": "trial"}, sup=good())
    run(root, "x-other", wf="other", sup=good())
    spec = checked()
    assert [w.thread.thread_id for w in pro.window(root, spec, "0.1.0", 10)] == [f"demo/t{i:02d}" for i in range(2, 12)]
    assert pro.check(spec, root, to="local-stable", size=4).window["runs"] == 4
    with pytest.raises(pro.PromotionRefused):
        pro.check(spec, root, to="local-stable", size=0)


def test_window_restarts_after_an_escape_when_the_bar_is_zero(repo: Path) -> None:
    root = state_root_path(repo)
    window_of(root, 4)
    run(root, "t04", sup=good(), escapes=1)
    run(root, "t05", sup=good())
    spec = checked()
    assert len(pro.window(root, spec, "0.1.0", 10)) == 6
    assert [w.thread.thread_id for w in pro.window(root, spec, "0.1.0", 10, restart_on_escape=True)] == ["demo/t05"]


def test_reported_rows_show_ladders_escalations_and_arms(repo: Path) -> None:
    """P9 to P11 are reported for `local-stable`; a ladder that never climbed is `ladder_unseen`."""
    root = state_root_path(repo)
    window_of(root, 9, arm="light")
    run(root, "t99", request="request 1", sup=good(), arm="full")
    (root / "ledger.jsonl").write_text("".join(json.dumps(r) + "\n" for r in (
        {"kind": "escalation", "workflow": "demo", "unit": "draft", "thread_id": "demo/t00", "passed": True},
        {"kind": "escalation", "workflow": "demo", "unit": "draft", "thread_id": "demo/t01", "passed": False},
        {"kind": "escalation", "workflow": "demo", "unit": "draft", "thread_id": "demo/outside", "passed": True})))
    spec = checked(step={"effort_ladder": ["low", "high"]})
    rep = pro.check(spec, root, to="local-stable")
    assert rep.met
    assert rep.ladder_seen["draft"]["ladder_unseen"] and "ladder_unseen: draft" in rows(rep)["P10"]["detail"]
    assert rep.escalation_covered["draft"]["attempts"] == 2 and rep.escalation_covered["draft"]["passed"] == 1
    assert rep.arms_covered == {"pick": {"full": 1, "light": 9}}


def test_a_climbed_attempt_is_seen_and_stays_out_of_the_yield(repo: Path) -> None:
    root = state_root_path(repo)
    window_of(root, 9)
    run(root, "t99", request="request 1", sup=good(), verdicts=("RETRY", "PROCEED"), climbed=True)
    rep = pro.check(checked(step={"effort_ladder": ["low", "high"]}), root, to="local-stable")
    assert rep.ladder_seen["draft"] == {"attempts": 11, "climbed": 1, "share": 0.0909}
    assert rows(rep)["P2"]["value"] == 0.9


# -- the verb: read-only, exit codes, refusals --------------------------------------------------------------------


def test_verb_is_read_only_and_exits_by_the_verdict(repo: Path) -> None:
    """PRO-AC2 (OVR-B15): without `--stamp` nothing is created or changed."""
    root = state_root_path(repo)
    cat = Catalog(specs={"demo": checked()})
    window_of(root, 9)
    before = hash_tree(repo)
    code, doc, _ = cli(repo, "promote-check", "demo", "--to", "local-stable", "--json", catalog=cat)
    assert code == 6 and doc["met"] is False and doc["window"]["runs"] == 9
    run(root, "t99", request="request 1", sup=good())
    before = hash_tree(repo)
    code, doc, _ = cli(repo, "promote-check", "demo", "--to", "local-stable", "--json", catalog=cat)
    assert code == 0 and doc["met"] is True and doc["stamped"] is False
    code, text, _ = cli(repo, "promote-check", "demo", "--to", "local-stable", catalog=cat)
    assert code == 0 and "every criterion met" in text and "P5.unattended" in text
    assert hash_tree(repo) == before


def test_pipeline_is_not_in_this_release(repo: Path) -> None:
    """PRO-AC6."""
    cat = Catalog(specs={"demo": checked()})
    code, _, err = cli(repo, "promote-check", "demo", "--to", "pipeline", catalog=cat)
    assert code == 2 and "not_in_release" in err
    code, _, err = cli(repo, "promote-check", "demo", "--to", "local-stable", "--executor", "agent-sdk", catalog=cat)
    assert code == 2 and "not_in_release" in err
    window_of(state_root_path(repo))
    code, _, err = cli(repo, "promote-check", "demo", "--to", "local-stable", "--stamp", catalog=cat,
                       signals=PIPELINE)
    assert code == 2 and "not_in_release" in err


# -- PRO-B10: the stamp --------------------------------------------------------------------------------------------


@pytest.fixture
def package(tmp_path: Path, repo: Path, monkeypatch: pytest.MonkeyPatch) -> tuple[Path, Any, Path]:
    """A package with ten good runs of its current version. Its judges have no scores here, so the P4 row is
    stubbed met; P4 itself is tested above."""
    pkg = minimal_package(tmp_path / "src")
    lp = load_package(pkg)
    root = state_root_path(repo)
    window_of(root, wf="release-notes", content=lp.workflow_version)
    monkeypatch.setattr(pro, "_judges", lambda spec, root: {
        "row": pro._row("P4", "judges", 1, "1 of 1 gates", True), "bindings": {"draft": {"alias": "medium"}}})
    return pkg, lp.spec, root


def test_stamp_is_written_only_when_every_row_is_met(package: tuple[Path, Any, Path]) -> None:
    """PRO-B1, PRO-B2."""
    pkg, spec, root = package
    person = {"kind": "person", "decided_by": "person", "relay": "direct"}
    rep = pro.stamp(spec, pro.check(spec, root, to="local-stable", size=4), person)  # too few runs
    assert not rep.stamped and not (pkg / "promotion.json").exists()
    rep = pro.stamp(spec, pro.check(spec, root, to="local-stable"), person)
    doc = json.loads((pkg / "promotion.json").read_text())
    entry = doc["stamps"]["local-stable"]
    assert rep.stamped and entry["workflow_version"] == load_package(pkg).workflow_version
    assert entry["stage"] == "local-stable" and entry["executor"] == "claude" and entry["caller"]["kind"] == "person"
    assert {c["id"] for c in entry["criteria"]} >= {"P1", "P2", "P3", "P4", "P6", "P11"}
    assert {"ladder_seen", "escalation_covered", "arms_covered", "alias_bindings", "stamped_at"} <= set(entry)
    assert pro.stamped(spec, "local-stable") and not pro.stamped(spec, "pipeline")


def test_stamp_needs_a_person_and_a_source_package(package: tuple[Path, Any, Path], tmp_path: Path,
                                                   monkeypatch: pytest.MonkeyPatch) -> None:
    pkg, spec, root = package
    rep = pro.check(spec, root, to="local-stable")
    with pytest.raises(pro.PromotionRefused, match="needs a person"):
        pro.stamp(spec, rep, {"kind": "agent", "decided_by": "agent", "relay": "claimed"})
    with pytest.raises(pro.PromotionRefused, match="not_in_release"):
        pro.stamp(spec, rep, {"kind": "pipeline", "decided_by": "pipeline"})
    with pytest.raises(pro.PromotionRefused, match="only a workflow package"):
        pro.stamp(checked(), rep, {"kind": "person", "decided_by": "person"})
    monkeypatch.setenv("CLAUDE_CONFIG_DIR", str(tmp_path / "cfg"))  # PRO-B6, PRO-B10, PRO-B9: an installed copy
    installed = tmp_path / "cfg" / "plugins" / "cache" / "release-notes"
    with pytest.raises(pro.PromotionRefused, match="installed copy"):
        pro.stamp(dataclasses.replace(spec, package_root=installed), rep, {"kind": "person", "decided_by": "person"})
    assert not (pkg / "promotion.json").exists()


def test_a_content_change_voids_the_stamp(package: tuple[Path, Any, Path]) -> None:
    """PRO-AC4, PRO-B4: the new version is unstamped and its window starts empty."""
    pkg, spec, root = package
    pro.stamp(spec, pro.check(spec, root, to="local-stable"), {"kind": "person", "decided_by": "person"})
    (pkg / "README.md").write_text("# release-notes\n\nA new readme.\n")  # outside the content digest
    (pkg / "stamp.json").write_text("{}")
    assert pro.stamped(spec, "local-stable")
    (pkg / "prompts" / "draft.md").write_text("Write better release notes for {request} into notes.md.\n")
    assert not pro.stamped(spec, "local-stable")
    rep = pro.check(load_package(pkg).spec, root, to="local-stable")
    assert rep.window["runs"] == 0 and rep.window["stamp"]["local-stable"]["state"] == "void"
    assert rep.exit_code == 6


def test_an_unreadable_stamp_file_is_no_stamp(package: tuple[Path, Any, Path]) -> None:
    """PRO-B6, PRO-B10, PRO-B9."""
    pkg, spec, root = package
    (pkg / "promotion.json").write_text("{not json")
    assert not pro.stamped(spec, "local-stable")
    assert "unreadable" in pro.check(spec, root, to="local-stable").window["stamp"]["warning"]


# -- PRO-B7, PRO-B4: the stage of a run ------------------------------------------------------------------------------------


def test_stage_of_a_run() -> None:
    assert pro.stage_of(checked()) == ("local-dev", False)
    assert pro.stage_of(checked(improvement_mode="stable"), {"kind": "person"}) == ("local-stable", False)
    assert pro.stage_of(checked(improvement_mode="stable"), {"kind": "pipeline"}) == ("local-stable", True)


def test_a_run_records_its_stage(repo: Path) -> None:
    """PRO-B7, PRO-B4: the stage is on `settings_resolved` and the ledger row; a pipeline caller runs unpromoted."""
    from tempergraph.run.events import records

    from .test_cli import cli as run_cli
    from .test_cli import happy

    cat = Catalog(specs={"demo": dataclasses.replace(two_step(), improvement_mode="stable")})
    assert run_cli(repo, happy(), "run", "demo", "notes", "--task-id", "t1", catalog=cat)[0] == 0
    root = state_root_path(repo)
    recs = list(records(run_dir(root, "demo", "t1") / "run.jsonl"))
    settled = next(r for r in recs if r["kind"] == "settings_resolved")
    assert settled["stage"] == "local-stable" and "unpromoted_pipeline" not in settled
    assert next(r for r in recs if r["kind"] == "run_started")["content_version"] == "0.1.0"
    row = [json.loads(ln) for ln in (root / "ledger.jsonl").read_text().splitlines()]
    assert [r["stage"] for r in row if r.get("kind") == "run_segment"] == ["local-stable"]
    run_cli(repo, happy(), "run", "demo", "notes", "--task-id", "t2", catalog=cat, signals=PIPELINE)
    recs = list(records(run_dir(root, "demo", "t2") / "run.jsonl"))
    assert next(r for r in recs if r["kind"] == "settings_resolved")["unpromoted_pipeline"] is True
