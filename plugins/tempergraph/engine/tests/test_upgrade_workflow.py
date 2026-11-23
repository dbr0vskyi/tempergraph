"""The built-in upgrade workflow (UWF-B6, UWF-B5, UWF-B7, UWF-B12, UWF-B13, UWF-B3, B5, UWF-AC1 to AC-4) on scripted executors."""

from __future__ import annotations

import dataclasses
import io
import json
from pathlib import Path
from types import SimpleNamespace
from typing import Any

import pytest

from tempergraph.builtin import upgrade as uwf
from tempergraph.catalog import from_registry
from tempergraph.cli.main import main
from tempergraph.constants import ExitCode
from tempergraph.contracts import SessionRequest, SessionResult
from tempergraph.executors.standins import answer, standin
from tempergraph.model.validate import errors, validate
from tempergraph.package import upgrade as up
from tempergraph.run.runner import RunSettings, resume

from .conftest import hash_tree
from .test_run import judge, registry, verdict_block
from .test_stamp import caps
from .test_upgrade import BRIEF, ENGINE, MODEL_LIST, branch_pkg, git, source

NO_SLEEP = RunSettings(sleep=lambda s: None)
MET = verdict_block(*["MET"] * 8)
PERSON = {"kind": "person"}


def test_it_validates_and_is_found_by_its_flag() -> None:  # UWF-AC1
    spec = uwf.workflow()
    assert errors(validate(spec, caps())) == []
    assert spec.builtin and uwf.is_upgrade(spec)
    assert uwf.is_upgrade(dataclasses.replace(spec, name="something-else"))  # the flag, not the name
    assert not uwf.is_upgrade(dataclasses.replace(spec, builtin=True))
    assert list(spec.order) == ["resolve", "draft_answer", "adjust"]
    for unit in ("draft_answer", "adjust"):
        u = spec.units[unit]
        assert u.map.mode == "sequential" and u.step.model == "large" and u.gate.judge.model == "medium"
        assert "network" not in u.step.tools and u.gate.retry_budget == 2 and u.gate.on_budget_spent == "ask"
    assert spec.units["draft_answer"].gate.approval and not spec.units["adjust"].gate.approval
    cat = from_registry()
    assert uwf.is_upgrade(cat.specs["upgrade"])  # registered after every package


def test_a_direct_start_is_refused(repo: Path) -> None:  # UWF-B5
    out, err = io.StringIO(), io.StringIO()
    code = main(["run", "upgrade", "release-notes-0.2.0"], cwd=repo, out=out, err=err, signals=({}, True))
    assert code == 2 and "tempergraph upgrade <workflow>" in err.getvalue()
    assert not (repo / ".tempergraph" / "runs").exists()


# -- UWF-B12, UWF-B13: the check of each item --------------------------------------------------------------------------


@pytest.fixture
def branch(repo: Path, tmp_path: Path) -> SimpleNamespace:
    """An upgrade stopped before its assist run, with the run's inputs written."""
    pkg, folder = source(repo, tmp_path, model='["small", "medium", "large"]', prompt="As of TODAY.\n",
                         entries={"0.2.0": [MODEL_LIST, BRIEF]})
    jobs: list[up.Assist] = []

    def hold(a: up.Assist) -> dict[str, Any]:
        jobs.append(a)
        uwf.write_inputs(a)
        return {"exit_code": 3, "items": {}}

    rep = up.upgrade(pkg, caps(), engine=ENGINE, folder=folder, assist=hold)
    assert rep.exit_code == 3
    return SimpleNamespace(pkg=pkg, folder=folder, rep=rep, job=jobs[0], work=Path(rep.worktree),
                           new=branch_pkg(rep))


def check(b: SimpleNamespace, unit: str = "adjust", item: str = "E0-2-0-2") -> Any:
    return uwf.item_check(SimpleNamespace(unit=unit, workdir=b.work, item=item, attempt=1))


def fix(b: SimpleNamespace) -> None:
    prompt = b.new / "prompts" / "draft.md"
    prompt.write_text(prompt.read_text().replace("TODAY", "{task_id}"))


def failed(got: Any) -> list[str]:
    assert got.result == "FAIL"
    return [f.criterion for f in got.findings if f.status == "fail"]


def test_the_item_check_passes_a_clean_edit(branch: SimpleNamespace) -> None:
    # WUP-AC7 (WUP-B3, WUP-B15): an assisted edit gated by its rules and a judge
    ctx = json.loads((branch.work / uwf.ITEMS_DIR / "context.json").read_text())
    assert ctx["package"] == "release-notes" and sorted(ctx["items"]) == ["E0-2-0-1-owner-1", "E0-2-0-2"]
    assert json.loads((branch.work / uwf.ITEMS_DIR / "assisted_items.json").read_text())[0]["id"] == "E0-2-0-2"
    fix(branch)
    got = check(branch)
    assert got.result == "PASS" and {f.criterion for f in got.findings} == {
        "uwf-scope", "uwf-loads", "uwf-proof", "uwf-fixtures"}


def test_scope_fails_alone(branch: SimpleNamespace) -> None:  # UWF-AC2, AC-4
    fix(branch)
    (branch.work / "README.md").write_text("also rewritten\n")
    assert failed(check(branch)) == ["uwf-scope"]


def test_a_protected_path_fails_adjust_and_not_the_owner(branch: SimpleNamespace) -> None:  # UWF-B4
    fix(branch)
    path = branch.new / "outcome.json"
    path.write_text(path.read_text() + "\n")
    got = check(branch)
    assert failed(got) == ["uwf-scope"] and "protected path" in got.evidence
    owner = check(branch, unit="draft_answer", item="E0-2-0-1-owner-1")
    assert owner.result == "PASS"  # the owner's own item may touch it, and the approval decides
    assert check(branch).result == "PASS"  # what an owner item changed is not held against a later item


def test_load_fails_alone(branch: SimpleNamespace) -> None:
    fix(branch)
    decl = branch.new / "workflow" / "release_notes" / "__init__.py"
    decl.write_text(decl.read_text().replace('tools=["read", "write"]', 'tools=["read", "teleport"]'))
    assert failed(check(branch)) == ["uwf-loads"]
    decl.write_text("raise RuntimeError('x')\n")
    assert failed(check(branch)) == ["uwf-loads"]


def test_proof_fails_alone(branch: SimpleNamespace) -> None:
    got = check(branch)  # nothing edited: the entry's rule still hits
    assert failed(got) == ["uwf-proof"] and "prompts/draft.md" in got.evidence


def test_fixtures_fail_alone(branch: SimpleNamespace) -> None:
    fix(branch)
    (branch.new / "evals" / "checks" / "draft" / "must-pass" / "notes.md").write_text("# Added\n")
    assert failed(check(branch)) == ["uwf-fixtures"]


# -- the run: UWF-B3 -------------------------------------------------------------------------------------------


def edits(change: Any) -> Any:
    def reply(req: SessionRequest) -> SessionResult:
        change(req)
        return answer("Edited.\nARTIFACT change_note: made the smallest edit", session_id="s")
    return reply


def escalate(req: SessionRequest) -> None:
    decl = req.workdir / "release-notes" / "workflow" / "release_notes" / "__init__.py"
    decl.write_text(decl.read_text().replace("from tempergraph.api import Gate,", "from tempergraph.api import Escalation, Gate,")
                    .replace('model="small",', 'model="small", escalation=Escalation(to="medium"),'))


def today(req: SessionRequest) -> None:
    prompt = req.workdir / "release-notes" / "prompts" / "draft.md"
    prompt.write_text(prompt.read_text().replace("TODAY", "{task_id}"))


def started(repo: Path, tmp_path: Path, ex: Any) -> tuple[Path, Path, up.Report, Any]:
    pkg, folder = source(repo, tmp_path, model='["small", "medium", "large"]', prompt="As of TODAY.\n",
                         entries={"0.2.0": [MODEL_LIST, BRIEF]})

    def assist(a: up.Assist) -> dict[str, Any]:
        return uwf.assist(a, registry(ex), caller=PERSON, settings=NO_SLEEP)

    rep = up.upgrade(pkg, caps(), engine=ENGINE, folder=folder, assist=assist, cap_usd=4.0)
    return pkg, folder, rep, assist


def test_the_owner_proceeds_and_the_model_adjusts(repo: Path, tmp_path: Path) -> None:
    # WUP-AC7 (WUP-B3, WUP-B4, WUP-B15): an owner pause and an assisted edit gated by a judge
    ex = standin("claude", steps=[edits(escalate)], judges=[judge(MET)])
    pkg, folder, rep, assist = started(repo, tmp_path, ex)
    before = hash_tree(pkg)
    head = git(repo, "rev-parse", "HEAD")
    assert rep.exit_code == 3, rep.assist
    assert rep.assist["thread_id"] == "upgrade/release-notes-0.2.0"  # the approval pause
    first = ex.calls[0].request
    assert "choose an `escalation.to`, or none" in first.prompt and "Question for the owner" in first.prompt
    assert first.workdir == Path(rep.worktree) and "Protected paths" in first.prompt
    spec = uwf.workflow()
    ex.steps, ex.judges = [edits(today)], [judge(MET)]
    out = resume(spec, rep.upgrade_id, Path(rep.worktree), registry(ex), decision="proceed", settings=NO_SLEEP)
    assert out.exit_code is ExitCode.FINISHED, out.message
    assert "Replace TODAY with the run's date key" in ex.calls[-2].request.prompt
    done = up.upgrade(pkg, caps(), engine=ENGINE, folder=folder, assist=assist, continue_id=rep.upgrade_id, stamp=True)
    assert done.exit_code == 0, [v.__dict__ for v in done.checks]
    states = {i.item_id: (i.state, i.by) for i in done.items}
    assert states == {"E0.2.0-1": ("done", "transform"), "E0.2.0-2": ("done", "model"),
                      "E0.2.0-1/owner-1": ("answered", "person")}
    assert done.shares["share"] == {"transform": 0.333, "model": 0.333, "person": 0.333}
    assert [c["entry"] for c in done.commits][:2] == ["E0.2.0-1", "assist"]
    assert not (Path(done.worktree) / uwf.ITEMS_DIR).exists() and git(Path(done.worktree), "status", "--porcelain") == ""
    assert git(repo, "rev-parse", "HEAD") == head and git(repo, "status", "--porcelain") == ""
    assert hash_tree(pkg) == before  # UWF-AC4: nothing outside the branch's package changed
    text = (branch_pkg(done) / "workflow" / "release_notes" / "__init__.py").read_text()
    assert 'escalation=Escalation(to="medium")' in text and done.stamp is not None


def test_the_owner_retries_then_stops(repo: Path, tmp_path: Path) -> None:
    ex = standin("claude", steps=[edits(escalate)], judges=[judge(MET)])
    pkg, folder, rep, assist = started(repo, tmp_path, ex)
    assert rep.exit_code == 3
    spec = uwf.workflow()
    ex.steps, ex.judges = [edits(lambda req: None)], [judge(MET)]
    again = resume(spec, rep.upgrade_id, Path(rep.worktree), registry(ex), decision="retry",
                   feedback="keep it without an escalation", settings=NO_SLEEP)
    assert again.exit_code is ExitCode.PAUSED  # a new draft, the same question
    assert "keep it without an escalation" in ex.calls[-2].request.prompt
    held = up.upgrade(pkg, caps(), engine=ENGINE, folder=folder, assist=assist, continue_id=rep.upgrade_id)
    assert held.exit_code == 3 and next(i for i in held.items if i.action == "owner").state == "pending"
    resume(spec, rep.upgrade_id, Path(rep.worktree), registry(ex), decision="stop", settings=NO_SLEEP)
    ended = up.upgrade(pkg, caps(), engine=ENGINE, folder=folder, assist=assist, continue_id=rep.upgrade_id)
    owner = next(i for i in ended.items if i.action == "owner")
    assert (owner.state, owner.by) == ("skipped", "person") and "stopped by the owner" in owner.reason
    assert ended.exit_code in (4, 5) and ended.stamp is None  # the assisted item never ran: it stays pending
    assert next(i for i in ended.items if i.item_id == "E0.2.0-2").state == "pending"
