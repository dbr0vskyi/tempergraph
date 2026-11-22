"""A parent's `upgrade` reads the change notes of a sub-workflow child its units run (SWF-B9, SWF-AC1; task AC 4;
VER-B17, WUP-B6, WUP-B16)."""

from __future__ import annotations

from pathlib import Path
from typing import Any

from tempergraph.package import upgrade as up

from .conftest import hash_tree
from .fixtures.packages import minimal_package, write
from .fixtures.subworkflows import home_dir, register_workflow
from .test_stamp import caps, changelogs, cli
from .test_upgrade import git

PARENT = '''
from tempergraph.api import Gate, Judge, Routing, Step, Subworkflow, Workflow, text

from .checks import draft_check


def workflow():
    return Workflow(
        order=["verify", "draft"],
        routing=Routing(description="Write release notes for the changes since the last tag"),
        issue_repository="acme/release-notes",
        units={
            "verify": Subworkflow(workflow="child", inputs={"request": "request"}, produces=["report"]),
            "draft": Step(prompt=text("prompts/draft.md"), tools=["read", "write"], produces={"notes": "file"},
                          gate=Gate(check=draft_check, judge=Judge(file="judges/draft.md", references=["notes"]))),
        },
    )
'''
RENAMED = {"id": "E2.0.0-1", "audience": "workflow", "kind": "renamed", "breaking": True, "surface": "spec_field",
           "subject": "units.work.step.produces.report",
           "detect": [{"id": "report-ref", "kind": "template_key", "match": "<unit>.report", "files": "prompts/*"}],
           "migrate": {"action": "transform", "transform": "rename_produced_key",
                       "params": {"unit": "<unit>", "from": "report", "to": "summary"}},
           "proof": ["report-ref"], "note": "The produced key `report` is now `summary`."}
ENGINE = "0.2.0"


def parent(repo: Path, tmp_path: Path, *, reference: str = "report", notes: Any = None) -> Path:
    """A parent package `deliver` whose `verify` unit runs the registered child at 2.0.0, whose change notes say it
    renamed its produced key `report` to `summary`; its `draft` prompt reads `{verify.<reference>}`."""
    root = register_workflow(home_dir(), tmp_path / "pkgs", "child", version="2.0.0", produces=["summary"])
    write(root, "changes/2.0.0.json", {"schema_version": 1, "version": "2.0.0", "entries": [notes or RENAMED]})
    pkg = minimal_package(repo, "deliver", declaration=PARENT)
    write(pkg, "prompts/draft.md", f"Write release notes for {{request}} from {{verify.{reference}}}.\n")
    return pkg


def test_the_parents_check_lists_the_childs_renamed_key_at_the_parents_reference(
        repo: Path, tmp_path: Path) -> None:  # SWF-AC1, AC 4
    pkg = parent(repo, tmp_path)
    before = hash_tree(pkg)
    code, doc, err = cli(repo, "upgrade", str(pkg), "--check")
    assert code == 0, err
    (item,) = [p for p in doc["pending"] if p["item_id"] == "verify:E2.0.0-1"]
    (hit,) = item["hits"]
    assert hit["where"] == "prompts/draft.md:1" and hit["rule"] == "report-ref" and hit["confidence"] == "high"
    assert "verify:E2.0.0-1" in doc["compatibility"]["entries"] and doc["compatibility"]["state"] == "unstamped"
    assert hash_tree(pkg) == before  # `--check` writes nothing
    # a parent that already reads the new key has nothing to do
    pkg2 = parent(repo, tmp_path / "again", reference="summary")
    code, doc, err = cli(repo, "upgrade", str(pkg2), "--check")
    assert code == 0, err
    assert [p["item_id"] for p in doc["pending"]] == []


def test_a_note_that_is_no_workflow_note_is_not_read(repo: Path, tmp_path: Path) -> None:  # SWF-AC1, AC 4
    for bad in ({**RENAMED, "audience": "operator"},  # not about what another workflow depends on
                {**RENAMED, "id": "not-an-id"},  # not an entry of the changelog's shape
                {**RENAMED, "surface": "cli"}):  # a surface a parent cannot depend on (VER-B17)
        pkg = parent(repo, tmp_path / bad["audience"] / bad["id"] / bad["surface"], notes=bad)
        code, doc, _ = cli(repo, "upgrade", str(pkg), "--check")
        assert code == 0 and doc["pending"] == [], bad
    pkg = parent(repo, tmp_path / "good")  # and the same note in its right shape is read
    assert [p["item_id"] for p in cli(repo, "upgrade", str(pkg), "--check")[1]["pending"]] == ["verify:E2.0.0-1"]


def test_the_upgrade_renames_the_key_in_the_parent_by_transform(repo: Path, tmp_path: Path) -> None:  # SWF-AC1, AC 4
    pkg = parent(repo, tmp_path)
    git(repo, "add", "-A")
    git(repo, "commit", "-q", "-m", "the parent")
    folder = changelogs(tmp_path / "changelog", {})
    rep = up.upgrade(pkg, caps(), engine=ENGINE, folder=folder, no_assist=True)
    item = next(i for i in rep.items if i.entry == "verify:E2.0.0-1")
    assert (item.action, item.state, item.by) == ("transform", "done", "transform"), rep.items
    assert item.hits[0]["where"] == "prompts/draft.md:1"
    new = Path(rep.worktree) / "deliver"
    assert (new / "prompts" / "draft.md").read_text() == "Write release notes for {request} from {verify.summary}.\n"
    assert 'produces=["summary"]' in (new / "workflow" / "deliver" / "__init__.py").read_text()
