"""`upgrade` beyond `--check`: transforms on a branch, verification, the finish and the record
(WUP-B14, WUP-B7, WUP-B20, WUP-B21, WUP-B2, B7, B8, B9, WUP-AC2, AC-3, AC-5, AC-6; milestone N4 on a retired model list)."""

from __future__ import annotations

import io
import json
import subprocess
from pathlib import Path
from typing import Any

import pytest

from tempergraph.cli.main import main
from tempergraph.constants import ENGINE_VERSION
from tempergraph.executors.registry import default_registry
from tempergraph.improve.codehost import MemoryCodeHost
from tempergraph.package import transforms
from tempergraph.package import upgrade as up
from tempergraph.package.loader import load_package

from .conftest import hash_tree
from .fixtures.packages import DECLARATION, minimal_package, write
from .test_stamp import caps, changelogs

ENGINE = "0.2.0"
MODEL_LIST = {"id": "E0.2.0-1", "audience": "workflow", "kind": "tightened", "breaking": True,
              "surface": "spec_field", "subject": "units.*.model",
              "detect": [{"id": "model-list", "kind": "finding", "match": "model-ladder-retired"}],
              "migrate": {"action": "transform", "transform": "model_list_to_escalation"},
              "proof": ["model-ladder-retired"], "note": "A list of models in a step's `model` is retired."}
TOOL = {"id": "E0.1.0-1", "audience": "workflow", "kind": "executor", "breaking": False, "surface": "tool_name",
        "subject": "Read", "detect": [{"id": "read-tool", "kind": "tool_ref", "match": "Read", "files": "prompts/*"}],
        "migrate": {"action": "transform", "transform": "rename_tool",
                    "params": {"executor": "claude", "from": "Read", "to": "View"}},
        "proof": ["read-tool"], "note": "The file reading tool is named View."}
UNUSED = {"id": "E0.1.0-2", "audience": "workflow", "kind": "changed", "breaking": False, "surface": "spec_field",
          "subject": "on_budget_spent", "detect": [{"kind": "field", "match": 'units.*.gate.on_budget_spent == "stop"'}],
          "migrate": {"action": "none", "reason": "informational"}, "proof": [], "note": "Not used here."}
BRIEF = {"id": "E0.2.0-2", "audience": "workflow", "kind": "behaviour", "breaking": False, "surface": "template",
         "subject": "TODAY", "detect": [{"id": "today", "kind": "text", "match": "TODAY", "files": "prompts/*"}],
         "migrate": {"action": "assisted", "instruction": "Replace TODAY with the run's date key."},
         "proof": ["today"], "note": "TODAY is no longer filled in."}


def git(cwd: Path, *args: str) -> str:
    return subprocess.run(["git", *args], cwd=cwd, check=True, capture_output=True, text=True).stdout


def source(repo: Path, tmp_path: Path, *, model: str = '["small", "medium"]', prompt: str = "Use Read first.\n",
           entries: dict[str, list[dict[str, Any]]] | None = None) -> tuple[Path, Path]:
    """A release 1 workflow with a model list, committed in a repository, and a changelog folder."""
    decl = DECLARATION.replace('tools=["read", "write"],', f'tools=["read", "write"], model={model},')
    pkg = minimal_package(repo, declaration=decl)
    write(pkg, "prompts/draft.md", "Write release notes for {request} into notes.md.\n" + prompt)
    git(repo, "add", "-A")
    git(repo, "commit", "-q", "-m", "the workflow")
    folder = changelogs(tmp_path / "changelog", entries or {"0.1.0": [TOOL, UNUSED], "0.2.0": [MODEL_LIST]})
    return pkg, folder


def run(pkg: Path, folder: Path, **kw: Any) -> up.Report:
    return up.upgrade(pkg, caps(), engine=ENGINE, folder=folder, **kw)


def branch_pkg(rep: up.Report) -> Path:
    return Path(rep.worktree) / "release-notes"


def test_transforms_only_no_session(repo: Path, tmp_path: Path) -> None:  # WUP-B2, B9, AC-2, AC-5, N4
    pkg, folder = source(repo, tmp_path)
    before = hash_tree(pkg)
    head = git(repo, "rev-parse", "HEAD")
    rep = run(pkg, folder, stamp=True, bump=True)
    assert rep.exit_code == 0, [v.__dict__ for v in rep.checks] + [rep.refused]
    assert [(i.item_id, i.action, i.state, i.by) for i in rep.items] == [
        ("E0.1.0-1", "transform", "done", "transform"), ("E0.2.0-1", "transform", "done", "transform")]
    assert rep.not_touched == ["E0.1.0-2"]
    assert [c["entry"] for c in rep.commits][:2] == ["E0.1.0-1", "E0.2.0-1"]  # oldest release first
    assert [v.state for v in rep.checks] == ["passed"] * 7 and rep.checks[2].check == "V3 proof"
    assert rep.shares["done"] == 2 and rep.shares["share"] == {"transform": 1.0, "model": 0.0, "person": 0.0}
    assert rep.assist == {} and rep.warnings == []
    # the person's checkout is never touched; the changes are commits on the upgrade's own branch
    assert hash_tree(pkg) == before and git(repo, "rev-parse", "HEAD") == head and git(repo, "status", "--porcelain") == ""
    assert rep.branch == f"tempergraph/upgrade/release-notes/{ENGINE}"
    new = branch_pkg(rep)
    text = (new / "workflow" / "release_notes" / "__init__.py").read_text()
    assert 'model="small"' in text and 'escalation=Escalation(to="medium")' in text and "Escalation, Gate" in text
    assert "Use View first." in (new / "prompts" / "draft.md").read_text()
    assert git(Path(rep.worktree), "status", "--porcelain") == ""
    log = git(repo, "log", "--format=%s", rep.branch).splitlines()
    assert log[-3] == "upgrade(release-notes): E0.1.0-1 Read" and "stamp for engine 0.2.0" in log[0]
    stamp = json.loads((new / "stamp.json").read_text())
    assert stamp["engine_version"] == ENGINE and stamp["upgrade_id"] == rep.upgrade_id
    assert {e["id"]: e["by"] for e in stamp["entries_applied"]} == {
        "E0.1.0-1": "transform", "E0.1.0-2": "none", "E0.2.0-1": "transform"}
    assert rep.proposed["requires_engine"] == ">=0.2.0,<1" and rep.proposed["level"] in ("patch", "minor")
    assert json.loads((new / ".claude-plugin" / "plugin.json").read_text())["version"] == rep.proposed["version"]
    assert load_package(new).spec.units["draft"].step.escalation.to == "medium"
    record = repo / ".tempergraph" / "upgrades" / rep.upgrade_id
    assert sorted(p.name for p in record.iterdir()) == ["baseline.json", "plan.json", "report.json"]
    saved = json.loads((record / "report.json").read_text())
    assert saved["schema_version"] == 1 and len(saved["verification"]) == 7
    assert "model-ladder-retired" in json.dumps(json.loads((record / "baseline.json").read_text())["validation"])
    assert rep.baseline_errors and "model-ladder-retired" in rep.baseline_errors[0]  # known before any change


def test_the_owner_chooses_what_no_rule_can(repo: Path, tmp_path: Path) -> None:
    pkg, folder = source(repo, tmp_path, model='["small", "medium", "large"]')
    rep = run(pkg, folder, stamp=True)
    assert rep.exit_code == 4 and rep.stamp is None and not (branch_pkg(rep) / "stamp.json").exists()
    owner = next(i for i in rep.items if i.action == "owner")
    assert owner.item_id == "E0.2.0-1/owner-1" and "escalation.to" in owner.ask and owner.state == "pending"
    assert rep.checks[-1].check == "V3 proof" and "E0.2.0-1/owner-1" in rep.checks[-1].evidence
    assert "no assist step is available" in rep.warnings[0]
    assert 'model="small"' in (branch_pkg(rep) / "workflow" / "release_notes" / "__init__.py").read_text()
    again = run(pkg, folder, stamp=True, continue_id=rep.upgrade_id)  # the person looked and goes on
    assert again.exit_code == 0 and again.stamp is not None
    owner = next(i for i in again.items if i.action == "owner")
    assert (owner.state, owner.by) == ("answered", "person")
    assert again.shares["done"] == 3 and again.shares["person"] == 1 and again.shares["transform"] == 2
    assert sum(again.shares[k] for k in ("transform", "model", "person")) == again.shares["done"]  # WUP-AC6


def weaken(rep: up.Report) -> None:
    decl = branch_pkg(rep) / "workflow" / "release_notes" / "__init__.py"
    decl.write_text(decl.read_text().replace("gate=Gate(check=draft_check,", "gate=Gate(retry_budget=9, check=draft_check,"))


def clean_upgrade(repo: Path, tmp_path: Path) -> tuple[Path, Path, up.Report]:
    pkg, folder = source(repo, tmp_path)
    rep = run(pkg, folder)
    assert rep.exit_code == 0
    return pkg, folder, rep


def failing(pkg: Path, folder: Path, rep: up.Report, check: str) -> up.Report:
    again = run(pkg, folder, stamp=True, continue_id=rep.upgrade_id)
    assert again.exit_code == 4 and again.stamp is None and not (branch_pkg(rep) / "stamp.json").exists()
    assert [v.check for v in again.checks if v.state == "failed"] == [check]
    assert again.checks[-1].check == check  # the first failure stops the list
    return again


def test_v1_fails_alone(repo: Path, tmp_path: Path) -> None:  # WUP-AC3
    pkg, folder, rep = clean_upgrade(repo, tmp_path)
    decl = branch_pkg(rep) / "workflow" / "release_notes" / "__init__.py"
    decl.write_text(decl.read_text() + "\nraise RuntimeError('broken')\n")
    failing(pkg, folder, rep, "V1 load")


def test_v2_fails_alone(repo: Path, tmp_path: Path) -> None:
    pkg, folder, rep = clean_upgrade(repo, tmp_path)
    decl = branch_pkg(rep) / "workflow" / "release_notes" / "__init__.py"
    decl.write_text(decl.read_text().replace('tools=["read", "write"]', 'tools=["read", "write", "teleport"]'))
    assert "new findings" in failing(pkg, folder, rep, "V2 validation").checks[-1].evidence


def test_v3_fails_alone(repo: Path, tmp_path: Path) -> None:
    pkg, folder, rep = clean_upgrade(repo, tmp_path)
    prompt = branch_pkg(rep) / "prompts" / "draft.md"
    prompt.write_text(prompt.read_text() + "Use Read again.\n")  # the entry's rule hits once more
    assert "E0.1.0-1" in failing(pkg, folder, rep, "V3 proof").checks[-1].evidence


def test_v4_fails_alone(repo: Path, tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:  # WUP-B5
    pkg, folder, rep = clean_upgrade(repo, tmp_path)
    real = up._audit_keys
    monkeypatch.setattr(up, "_audit_keys", lambda lp, c: [*real(lp, c), "judge-exposed-tool|draft||"])
    assert "judge-exposed-tool" in failing(pkg, folder, rep, "V4 audit").checks[-1].evidence


def test_v5_fails_alone(repo: Path, tmp_path: Path) -> None:  # WUP-B8: a weakening needs the owner
    pkg, folder, rep = clean_upgrade(repo, tmp_path)
    weaken(rep)
    got = failing(pkg, folder, rep, "V5 change classes")
    assert "weakening" in got.checks[-1].evidence and "weakening" in got.classes


def test_v5_passes_a_weakening_the_owner_answered(repo: Path, tmp_path: Path) -> None:
    pkg, folder = source(repo, tmp_path, model='["small", "large"]')
    rep = run(pkg, folder)
    assert rep.exit_code == 4
    weaken(rep)
    again = run(pkg, folder, continue_id=rep.upgrade_id)
    v5 = next(v for v in again.checks if v.check == "V5 change classes")
    assert again.exit_code == 0 and v5.state == "passed" and "approved by the owner" in v5.evidence


def test_v6_fails_alone(repo: Path, tmp_path: Path) -> None:
    pkg, folder, rep = clean_upgrade(repo, tmp_path)
    (branch_pkg(rep) / "evals" / "checks" / "draft" / "must-pass" / "notes.md").write_text("# Added\n")
    assert "must-pass" in failing(pkg, folder, rep, "V6 suites").checks[-1].evidence


def test_refusals_write_nothing(repo: Path, tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:  # WUP-B7
    pkg, folder = source(repo, tmp_path)
    monkeypatch.setenv("CLAUDE_CONFIG_DIR", str(tmp_path / "claude"))
    cached = minimal_package(tmp_path / "claude" / "plugins" / "cache" / "acme" / "release-notes")
    before = hash_tree(tmp_path)
    rep = run(cached, folder)
    assert rep.exit_code == 2 and "installed copy" in rep.refused and "Clone" in rep.refused
    loose = minimal_package(tmp_path / "loose")
    assert run(loose, folder).exit_code == 2  # not inside a git repository
    assert run(pkg, folder, continue_id="release-notes-9.9.9").exit_code == 2
    (pkg / "prompts" / "draft.md").write_text("edited and not committed\n")
    dirty = run(pkg, folder)
    assert dirty.exit_code == 2 and "uncommitted changes" in dirty.refused
    git(repo, "checkout", "-q", "--", ".")
    def kept(tree: dict[str, str]) -> dict[str, str]:
        return {k: v for k, v in tree.items() if not k.startswith(("loose", "repo/.git/"))}

    assert kept(hash_tree(tmp_path)) == kept(before)
    assert not (repo / ".tempergraph" / "upgrades").exists()
    git(repo, "branch", f"tempergraph/upgrade/release-notes/{ENGINE}")
    taken = run(pkg, folder)
    assert taken.exit_code == 2 and "--continue release-notes-0.2.0" in taken.refused


def test_a_transform_never_leaves_the_package(repo: Path, tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    pkg, folder = source(repo, tmp_path, entries={"0.1.0": [TOOL]})  # WUP-AC5

    def stray(root: Path, migrate: Any) -> transforms.Result:
        (root.parent / "README.md").write_text("rewritten by a transform\n")
        (root.parent / "stray.txt").write_text("x\n")
        return transforms.Result(changed=["../README.md"])

    monkeypatch.setattr(transforms, "apply", stray)
    rep = run(pkg, folder, no_assist=True)
    first = rep.items[0]
    assert first.state == "failed" and "outside the package" in first.reason
    assert (Path(rep.worktree) / "README.md").read_text() == "scratch\n" and not (Path(rep.worktree) / "stray.txt").exists()
    rest = rep.items[1]
    assert (rest.item_id, rest.action, rest.state) == ("E0.1.0-1/rest", "manual", "pending")  # WUP-B17, --no-assist
    assert rep.exit_code == 4 and rep.commits == [] and rep.warnings == []
    monkeypatch.undo()
    prompt = branch_pkg(rep) / "prompts" / "draft.md"
    prompt.write_text(prompt.read_text().replace("Read", "View"))  # the fix by hand
    again = run(pkg, folder, continue_id=rep.upgrade_id)
    assert again.exit_code == 0 and (again.items[1].state, again.items[1].by) == ("done", "person")


def test_assisted_items_go_to_the_assist_step(repo: Path, tmp_path: Path) -> None:  # WUP-B18, AC-6
    pkg, folder = source(repo, tmp_path, model='["small", "medium", "large"]', prompt="As of TODAY.\n",
                         entries={"0.2.0": [MODEL_LIST, BRIEF]})
    seen: list[up.Assist] = []

    def paused(a: up.Assist) -> dict[str, Any]:
        seen.append(a)
        return {"exit_code": 3, "thread_id": f"upgrade/{a.upgrade_id}", "cost_usd": 0.4, "items": {}}

    rep = run(pkg, folder, assist=paused, cap_usd=3.0, executor="claude")
    assert rep.exit_code == 3 and rep.checks == [] and rep.assist["thread_id"] == "upgrade/release-notes-0.2.0"
    a = seen[0]
    assert sorted(i.item_id for i in a.items) == ["E0.2.0-1/owner-1", "E0.2.0-2"] and a.cap_usd == 3.0
    assert a.package == branch_pkg(rep) and (a.record / "plan.json").is_file()

    def finished(a: up.Assist) -> dict[str, Any]:
        prompt = a.package / "prompts" / "draft.md"
        prompt.write_text(prompt.read_text().replace("TODAY", "{task_id}"))
        return {"exit_code": 0, "cost_usd": 0.9, "items": {"E0.2.0-2": {"state": "done", "by": "model"},
                                                           "E0.2.0-1/owner-1": {"state": "answered", "by": "person"}}}

    again = run(pkg, folder, assist=finished, continue_id=rep.upgrade_id)
    assert again.exit_code == 0, [v.__dict__ for v in again.checks]
    assert again.shares == {"done": 3, "transform": 1, "model": 1, "person": 1, "open": 0, "skipped": 0,
                            "share": {"transform": 0.333, "model": 0.333, "person": 0.333}}
    assert again.proposed["level"] == "minor" and again.assist["cost_usd"] == 0.9


def test_a_draft_pull_request_carries_the_report(repo: Path, tmp_path: Path) -> None:  # WUP-B20, WUP-B21
    pkg, folder = source(repo, tmp_path)
    remote = tmp_path / "remote.git"
    git(tmp_path, "init", "-q", "--bare", str(remote))
    git(repo, "remote", "add", "origin", str(remote))
    none = run(pkg, folder, open_pr=True)
    assert none.exit_code == 0 and none.pull_request is None and "no code host credentials" in none.warnings[0]
    host = MemoryCodeHost()
    rep = run(pkg, folder, open_pr=True, host=host, continue_id=none.upgrade_id)
    assert rep.exit_code == 0 and rep.pull_request == "https://example.test/acme/release-notes/pull/1"
    pr = host.pulls[0]
    assert pr["draft"] and pr["head"] == rep.branch and pr["labels"] == ["engine-upgrade"]
    assert "Items done: 2 (transform 2, model 0, person 0)" in pr["body"] and "V7 diagram: passed" in pr["body"]
    assert rep.branch in git(remote, "branch", "--list", rep.branch)


def test_the_verb(repo: Path, tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    pkg, folder = source(repo, tmp_path, entries={})
    out, err = io.StringIO(), io.StringIO()
    code = main(["upgrade", str(pkg), "--format", "text"], registry=default_registry(), cwd=repo, out=out, err=err,
                signals=({}, True))
    assert code == 0, err.getvalue()
    text = out.getvalue()  # WUP-B11, WUP-B17, WUP-B15, WUP-B18, WUP-B21: an error the workflow had before is not counted against V2; the report leads with it
    assert text.splitlines()[1].startswith("  before the upgrade: model-ladder-retired")
    assert "V2 validation: passed" in text and "upgrade release-notes: engine unstamped" in text
    # the shipped changelog retires the model list (a breaking entry), so the proposal is a minor version
    assert f"proposed version 0.2.0 (minor), requires_engine >={ENGINE_VERSION},<1" in text
