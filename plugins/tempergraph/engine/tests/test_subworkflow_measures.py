"""A sub-workflow child's outcome record counts in the child's measures with `origin: subworkflow:<parent>`, and stays
outside the child's promotion window (SWF-B9, SWF-AC1; task AC 3; OUT-B18, OUT-B19, PRO-B8, PRO-B9)."""

from __future__ import annotations

from pathlib import Path

from tempergraph.catalog import Catalog
from tempergraph.constants import ExitCode
from tempergraph.improve import promotion as pro
from tempergraph.model import subworkflow
from tempergraph.run.runner import ledger_rows
from tempergraph.store.layout import state_root_path

from .fixtures.subworkflows import home_dir, register_workflow
from .test_cli import cli
from .test_promotion import checked, good, rows, run, window_of
from .test_subworkflow_run import go, happy, parent


def test_the_childs_record_from_inside_a_parent_counts_in_its_measures_with_its_origin(
        tmp_path: Path, repo: Path) -> None:  # SWF-AC1, AC 3
    register_workflow(home_dir(), tmp_path / "pkgs", "child", version="0.3.1", produces=["overview"])
    out = go(repo, happy(), parent())
    assert out.exit_code is ExitCode.FINISHED, out.message
    root = state_root_path(repo)
    kid = [r for r in ledger_rows(root) if r.get("kind") == "child_outcome"]
    assert len(kid) == 1
    assert (kid[0]["workflow"], kid[0]["workflow_version"], kid[0]["parent"], kid[0]["thread_id"], kid[0]["child"]) == (
        "child", "0.3.1", "deliver", "deliver/T-1", "setup")
    assert kid[0]["outcome"]["origin"] == "subworkflow:deliver" and kid[0]["outcome"]["verdict"] == "met"
    child = subworkflow.read_child("child")
    assert isinstance(child, subworkflow.Child)
    code, doc, err = cli(repo, None, "outcome", "show", "child", "--runs", catalog=Catalog(specs={"child": child.spec}))
    assert code == 0, err
    (rev,) = doc["runs"]
    assert rev["n"] == 1 and rev["reached"] == 1 and rev["met_rate"] == 1.0
    # the parent's own measures are its own run's record, not the child's
    code, doc, err = cli(repo, None, "outcome", "show", "deliver", "--runs",
                         catalog=Catalog(specs={"deliver": parent()}))
    assert [r["workflow"] for r in ledger_rows(root) if r.get("kind") == "run_segment"] == ["deliver"]
    assert sorted(p.name for p in (root / "runs").iterdir()) == ["deliver"]  # no folder of the child's own


def test_ten_records_of_the_child_from_inside_a_parent_leave_its_window_empty(repo: Path) -> None:  # SWF-AC1, AC 3
    root = state_root_path(repo)
    window_of(root, 10, origin="subworkflow:deliver")  # ten records of `demo` run for a parent, none of its own
    for i in range(10):
        with (root / "ledger.jsonl").open("a") as fh:
            fh.write('{"kind": "child_outcome", "workflow": "demo", "parent": "deliver", "child": "setup", '
                     f'"thread_id": "deliver/T-{i}", "outcome": {{"verdict": "met", "revision": 1, '
                     '"origin": "subworkflow:deliver", "criteria": []}}\n')
    rep = pro.check(checked(), root, to="local-stable")
    assert rows(rep)["P1"]["verdict"] == "unmeasured" and rows(rep)["P1"]["value"] is None
    for i in range(10):  # ten runs of its own: the window holds those, and only those
        run(root, f"own-{i:02d}", request=f"request {i % 4}", sup=good())
    assert len(pro.window(root, checked(), "0.1.0", 10)) == 10
    assert rows(pro.check(checked(), root, to="local-stable"))["P1"]["value"] == 10
