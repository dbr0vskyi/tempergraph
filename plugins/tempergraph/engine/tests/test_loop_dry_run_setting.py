"""The loop's dry run as a run setting `run.loop_dry_run` (LFS-B1, LFS-AC1, CON-AC1, EVT-AC11, PRO-AC7)."""

from __future__ import annotations

import json
import os
from pathlib import Path
from typing import Any

import pytest

from tempergraph.catalog import Catalog
from tempergraph.improve import promotion as pro
from tempergraph.settings import CATALOG, ConfigFiles, SettingError, options_snapshot, resolve, rows_json

from .conftest import hash_tree
from .fixtures.workflows import two_step
from .test_cli import cli, happy
from .test_run import DRAFT, REVIEW, judge, verdict_block

KEY = "run.loop_dry_run"


def go(sp: Any, flags: dict[str, Any] | None = None, profiles: tuple[str, ...] = (),
       files: ConfigFiles | None = None) -> tuple[Any, list[Any]]:
    opts, findings = options_snapshot(sp, flags or {}, profiles, files or ConfigFiles())
    return resolve(sp, opts), findings


def rows(res: Any) -> dict[str, dict[str, Any]]:
    return {r["key"]: r for r in rows_json(res)}


def started(repo: Path, task: str) -> list[dict[str, Any]]:
    log = repo / ".tempergraph" / "runs" / "demo" / task / "run.jsonl"
    return [r for r in (json.loads(x) for x in log.read_text().splitlines()) if r.get("kind") == "run_started"]


def settings_file(value: Any) -> None:
    home = Path(os.environ["TEMPERGRAPH_HOME"])
    (home / "config").mkdir(parents=True, exist_ok=True)
    (home / "config" / "settings.json").write_text(json.dumps({"schema_version": 1, "defaults": {KEY: value}}))


def test_the_key_is_in_the_catalog_with_its_layers() -> None:  # LFS-AC1
    entry = CATALOG["loop_dry_run"]
    assert entry.scopes == frozenset({"run"}) and entry.default is False
    res, findings = go(two_step())
    assert not findings and res.values[KEY] is False and KEY not in rows(res)
    res, _ = go(two_step(), {KEY: True})
    assert res.values[KEY] is True and rows(res)[KEY]["layer"] == "flag"
    res, _ = go(two_step(profiles={"dry": {KEY: True}}), profiles=("dry",))
    assert res.values[KEY] is True and rows(res)[KEY]["layer"] == "profile"
    files = ConfigFiles(user={"schema_version": 1, "defaults": {KEY: True}}, user_path=Path("/u/settings.json"))
    res, _ = go(two_step(), files=files)
    assert res.values[KEY] is True and rows(res)[KEY]["layer"] == "user:defaults"
    res, _ = go(two_step(loop_dry_run=True))
    assert res.values[KEY] is True and rows(res)[KEY]["layer"] == "workflow:default"


def test_the_key_takes_true_and_false_only() -> None:  # LFS-AC1
    check = CATALOG["loop_dry_run"].check
    assert [check(v) for v in (True, False, "true", "false")] == [True, False, True, False]
    for bad in ("maybe", 1, 0, "1", "yes"):
        with pytest.raises(SettingError) as e:
            check(bad)
        assert e.value.code == "setting_value"


def test_config_show_prints_a_set_value_with_its_layer(repo: Path) -> None:  # LFS-AC1
    code, shown, _ = cli(repo, None, "config", "show", "demo", "--set", f"{KEY}=true")
    assert code == 0 and not shown["findings"]
    row = next(r for r in shown["rows"] if r["key"] == KEY)
    assert row["value"] is True and row["layer"] == "flag"
    code, shown, _ = cli(repo, None, "config", "show", "demo")
    assert code == 0 and not any(r["key"] == KEY for r in shown["rows"])


def test_a_bad_value_is_refused_in_the_same_words_before_any_file(repo: Path) -> None:  # LFS-AC1
    ex = standin_paused()
    code, _, _ = cli(repo, ex, "run", "demo", "notes", "--task-id", "L-1")
    assert code == 3
    before = hash_tree(repo)
    seen = []
    for argv in (("run", "demo", "notes", "--check"), ("run", "demo", "notes", "--task-id", "L-2"),
                 ("resume", "demo", "L-1", "--decision", "proceed")):
        code, doc, err = cli(repo, standin_paused(), *argv, "--set", f"{KEY}=maybe")
        text = err + json.dumps(doc)
        assert code == 2 and "setting_value" in text, argv
        seen.append("'maybe' is not true or false" in text)
    assert seen == [True, True, True]
    assert hash_tree(repo) == before


def standin_paused() -> Any:
    from tempergraph.executors.standins import standin

    return standin("claude", steps=[DRAFT], judges=[judge(verdict_block("UNVERIFIABLE"))])


def test_a_workflow_declares_the_setting_on_its_default_layer() -> None:  # CON-AC1
    res, _ = go(two_step(loop_dry_run=True))
    assert rows(res)[KEY]["layer"] == "workflow:default" and rows(res)[KEY]["value"] is True
    files = ConfigFiles(project={"schema_version": 1, "overrides": [{"workflow": "demo", "set": {KEY: False}}]},
                        project_path=Path("/p/settings.json"))
    res, _ = go(two_step(loop_dry_run=True), files=files)
    assert res.values[KEY] is False and rows(res)[KEY]["layer"] == "project:overrides"
    res, _ = go(two_step())
    assert KEY not in rows(res)


def run_with(repo: Path, task: str, *argv: str, spec: Any = None) -> None:
    cat = Catalog(specs={"demo": spec or two_step()})
    code, _, err = cli(repo, happy(), "run", "demo", "notes", "--task-id", task, *argv, catalog=cat)
    assert code == 0, err


def test_run_started_holds_dry_run_from_every_source(repo: Path) -> None:  # EVT-AC11
    run_with(repo, "E-1", spec=two_step(loop_dry_run=True))
    run_with(repo, "E-2", "--set", f"{KEY}=true")
    run_with(repo, "E-3")
    run_with(repo, "E-4", "--set", f"{KEY}=false", spec=two_step(loop_dry_run=True))
    settings_file(True)
    run_with(repo, "E-5")
    assert [started(repo, t)[0].get("dry_run") for t in ("E-1", "E-2", "E-3", "E-4", "E-5")] == [
        True, True, None, None, True]


def test_a_resume_with_the_setting_false_writes_no_dry_run(repo: Path) -> None:  # EVT-AC11
    code, _, _ = cli(repo, standin_paused(), "run", "demo", "notes", "--task-id", "E-7", "--set", f"{KEY}=true")
    assert code == 3 and started(repo, "E-7")[0]["dry_run"] is True
    ex = standin_paused()
    ex.steps, ex.judges = [REVIEW], [judge()]
    code, _, err = cli(repo, ex, "resume", "demo", "E-7", "--decision", "proceed", "--set", f"{KEY}=false")
    assert code == 0, err
    first, second = started(repo, "E-7")
    assert first["dry_run"] is True and "dry_run" not in second


def test_the_real_run_count_leaves_out_a_declared_dry_run(repo: Path) -> None:  # PRO-AC7
    run_with(repo, "P-1", spec=two_step(loop_dry_run=True))
    run_with(repo, "P-2", "--set", f"{KEY}=false", spec=two_step(loop_dry_run=True))
    run_with(repo, "P-3")
    version = started(repo, "P-3")[0]["content_version"]
    got = [w.thread.thread_id for w in pro.window(repo / ".tempergraph", two_step(), version, 10)]
    assert sorted(got) == ["demo/P-2", "demo/P-3"]
