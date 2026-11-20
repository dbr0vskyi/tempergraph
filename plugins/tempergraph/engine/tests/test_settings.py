"""Run settings: catalog, layers, files, profiles and the effective spec (RST §2, B1–B11, AC-3, AC-7)."""

from __future__ import annotations

import dataclasses
import json
import os
import random
from pathlib import Path
from typing import Any

import pytest

from tempergraph.contracts import RunOptions, SettingDecl, WorkflowSpec
from tempergraph.settings import (
    ConfigFiles,
    effective_spec,
    load_files,
    options_snapshot,
    overridden_keys,
    resolve,
    rows_json,
    workflow_settings,
)

from .fixtures.workflows import two_step


def spec(**kw: Any) -> WorkflowSpec:
    s = two_step()
    units = dict(s.units)
    units["review"] = dataclasses.replace(units["review"], step=dataclasses.replace(units["review"].step,
                                                                                   timeout_s=1800, model="medium"))
    return dataclasses.replace(s, units=units, **kw)


def go(sp: WorkflowSpec, flags: dict[str, Any] | None = None, profiles: tuple[str, ...] = (),
       files: ConfigFiles | None = None) -> tuple[Any, list[Any]]:
    opts, findings = options_snapshot(sp, flags or {}, profiles, files or ConfigFiles())
    return resolve(sp, opts), findings


def row(res: Any, key: str) -> dict[str, Any]:
    return next(r for r in rows_json(res) if r["key"] == key)


def test_one_order_for_every_key() -> None:  # RST-B1
    files = ConfigFiles(user={"schema_version": 1, "defaults": {"steps.timeout_s": 900}},
                        project={"schema_version": 1, "overrides": [{"workflow": "demo",
                                                                     "set": {"draft.timeout_s": 7200}}]},
                        user_path=Path("/u/settings.json"), project_path=Path("/p/settings.json"))
    res, findings = go(spec(), {"review.idle_s": 60}, files=files)
    assert not findings
    assert res.values["draft.timeout_s"] == 7200 and row(res, "draft.timeout_s")["layer"] == "project:overrides"
    assert res.values["review.timeout_s"] == 1800 and row(res, "review.timeout_s")["layer"] == "workflow:unit"
    assert res.values["review.idle_s"] == 60 and row(res, "review.idle_s")["layer"] == "flag"
    assert res.values["judge:draft.timeout_s"] == 600  # engine: a judge never reads a step's value
    assert not any(r["key"] == "judge:draft.timeout_s" for r in rows_json(res))
    res2, _ = go(spec(), files=ConfigFiles(user=files.user, user_path=files.user_path))
    assert res2.values["draft.timeout_s"] == 900 and row(res2, "draft.timeout_s")["layer"] == "user:defaults"


def test_judges_apart() -> None:  # RST-B2
    res, _ = go(spec(), {"steps.model": "small"})
    eff = effective_spec(spec(), res)
    assert eff.units["draft"].step.model == "small"
    assert eff.units["review"].step.model == "small"  # the flag outranks the step's own model
    assert eff.units["review"].gate.judge.model == "medium"  # the step's declared model, never `small`
    assert eff.units["draft"].gate.judge.model is None  # inherit


@pytest.mark.parametrize(("key", "code"), [("draft.criteria", "not_a_setting"), ("judge:draft.tools", "not_a_setting"),
                                           ("draft.prompt", "not_a_setting"), ("drafft.model", "unknown_setting"),
                                           ("draft.member:a.model", "setting_not_for_kind"),
                                           ("draft.deadline_s", "setting_not_in_release"),
                                           ("draft.bogus", "unknown_setting"), ("run.retry_budget", "setting_not_for_kind"),
                                           ("draft.approve", "tighten_only"), ("judges.model", "setting_value"),
                                           ("draft.retry_budget", "setting_value"),
                                           ("draft.on_budget_spent", "no_fallback_target"),
                                           ("run.worktree.root", "setting_not_in_release"),
                                           ("draft.tools.add", "setting_not_built")])
def test_refusals(key: str, code: str) -> None:  # RST-B5, B6, B10, §4
    value = {"draft.approve": False, "judges.model": ["small", "large"], "draft.retry_budget": 99,
             "draft.on_budget_spent": "fallback", "run.worktree.root": "in_repo"}.get(key, "x")
    _, findings = go(spec(), {key: value})
    assert [f.code for f in findings] == [code], findings
    if code == "unknown_setting" and key.startswith("drafft"):
        assert "draft" in findings[0].message


def test_tighten_only_from_a_file() -> None:  # RST-B6
    files = ConfigFiles(project={"schema_version": 1, "overrides": [{"workflow": "*", "set": {"draft.approve": False}}]})
    _, findings = go(spec(), files=files)
    assert [f.code for f in findings] == ["tighten_only"]
    res, _ = go(spec(), {"draft.approve": True})
    assert effective_spec(spec(), res).units["draft"].gate.approval is True


def test_workflow_settings_and_text_scrubbed() -> None:  # RST-B7, AC-7
    sp = spec(settings={"test_budget_s": SettingDecl(kind="duration_s", default=1800, max=7200),
                        "code_mode": SettingDecl(kind="choice", default="per_phase", choices=("per_phase", "single")),
                        "publish": SettingDecl(kind="bool", default=True),
                        "base_branch": SettingDecl(kind="text", default="")})
    res, findings = go(sp, {"settings.code_mode": "single", "settings.test_budget_s": 3600,
                            "settings.base_branch": "secret-canary"})
    assert not findings
    assert workflow_settings(res) == {"test_budget_s": 3600, "code_mode": "single", "publish": True,
                                      "base_branch": "secret-canary"}
    assert "secret-canary" not in json.dumps(rows_json(res))
    _, bad = go(sp, {"settings.code_mode": "fast"})
    assert bad[0].code == "setting_value" and "per_phase" in bad[0].message


def test_profiles_first_found_whole() -> None:  # RST-B8
    sp = spec(profiles={"cheap": {"steps.model": "small", "run.run_cost_cap_usd": 5}})
    files = ConfigFiles(user={"schema_version": 1, "profiles": {"cheap": {"steps.timeout_s": 120}}},
                        user_path=Path("/u/settings.json"))
    res, findings = go(sp, profiles=("cheap",), files=files)
    assert not findings and res.profiles == ("cheap",)
    assert res.values["draft.timeout_s"] == 120 and row(res, "draft.timeout_s")["layer"] == "profile"
    assert res.values["run.run_cost_cap_usd"] is None  # the workflow's own `cheap` is not merged in
    res2, _ = go(sp, profiles=("cheap",))
    assert res2.values["run.run_cost_cap_usd"] == 5 and "workflow:profiles.cheap" in row(res2, "draft.model")["ref"]
    _, missing = go(sp, profiles=("nope",))
    assert missing[0].code == "unknown_profile"


def test_shadowed_values_are_shown() -> None:  # RST-B11
    files = ConfigFiles(user={"schema_version": 1, "overrides": [{"workflow": "demo", "set": {"steps.model": "medium"}}]})
    res, _ = go(spec(), {"steps.model": "large"}, files=files)
    r = row(res, "draft.model")
    assert r["value"] == "large" and r["layer"] == "flag" and r["shadowed"][0]["layer"] == "user:overrides"
    assert "draft.model" in overridden_keys(res)


def test_widening_and_unit_in_defaults_refused_from_files() -> None:
    files = ConfigFiles(user={"schema_version": 1, "defaults": {"draft.timeout_s": 5},
                              "overrides": [{"workflow": "*", "set": {"draft.tools.add": ["edit"]}}]})
    _, findings = go(spec(), files=files)
    assert sorted(f.code for f in findings) == ["unit_in_defaults", "widening_in_file"]


def test_files_load_and_refuse_bad_json(tmp_path: Path) -> None:
    root, home = tmp_path / "root", tmp_path / "home"
    (root / "config").mkdir(parents=True)
    (home / "config").mkdir(parents=True)
    (root / "config" / "settings.json").write_text("{nope")
    (home / "config" / "settings.json").write_text(json.dumps({"schema_version": 1, "defaults": {"run.attempt_cap": 9}}))
    files = load_files(root, home)
    assert files.errors[0].code == "config_file" and files.user is not None
    res, findings = go(spec(), files=files)
    assert res.values["run.attempt_cap"] == 9 and findings[0].code == "config_file"


def test_digest_is_stable_and_moves_with_a_value() -> None:
    a, _ = go(spec(), {"draft.timeout_s": 100})
    b, _ = go(spec(), {"draft.timeout_s": 100})
    c, _ = go(spec(), {"draft.timeout_s": 101})
    assert a.digest == b.digest != c.digest


def test_property_no_step_key_reaches_a_judge_and_tighten_only_stays_true() -> None:  # RST-AC-3
    rnd = random.Random(7)
    keys = ["steps.model", "draft.model", "review.model", "steps.timeout_s", "draft.timeout_s", "steps.effort"]
    vals = {"model": ["small", "large", "medium"], "timeout_s": [60, 120, 900], "effort": ["low", "high"]}
    for _ in range(200):
        flags = {k: rnd.choice(vals[k.split(".")[1]]) for k in rnd.sample(keys, rnd.randint(0, len(keys)))}
        flags.update({"run.enforce_tools": True} if rnd.random() < 0.5 else {})
        res, findings = go(spec(), flags)
        assert not findings
        eff = effective_spec(spec(), res)
        for name in ("draft", "review"):
            j = eff.units[name].gate.judge
            assert j.model == ("medium" if name == "review" else None)
            assert j.timeout_s == 600 and j.session_options is None
        assert res.values["run.enforce_tools"] in (True, False)
        assert res.values["run.enforce_tools"] is ("run.enforce_tools" in flags)


def test_snapshot_reapplies_without_files() -> None:  # RST-AC-5
    files = ConfigFiles(user={"schema_version": 1, "defaults": {"steps.timeout_s": 900}})
    opts, _ = options_snapshot(spec(), {}, (), files)
    again = resolve(spec(), RunOptions(settings=json.loads(json.dumps(opts.settings)), profiles=opts.profiles))
    assert again.digest == resolve(spec(), opts).digest and again.values["draft.timeout_s"] == 900


# ---------------------------------------------------------------------------------------------
# Through the CLI and the runner


def _records(repo: Path, task: str, kind: str) -> list[dict[str, Any]]:
    log = repo / ".tempergraph" / "runs" / "demo" / task / "run.jsonl"
    return [r for r in (json.loads(x) for x in log.read_text().splitlines()) if r.get("kind") == kind]


def test_run_records_settings_and_show_equals_run(repo: Path) -> None:  # RST-B9, RST §2.7
    from .test_cli import cli, happy

    argv = ["--set", "draft.timeout_s=1200", "--step-model", "review=large", "--judge-timeout", "300"]
    code, shown, _ = cli(repo, None, "config", "show", "demo", *argv)
    assert code == 0 and not shown["findings"]
    code, _, err = cli(repo, happy(), "run", "demo", "notes", "--task-id", "S-1", *argv)
    assert code == 0, err
    rec = _records(repo, "S-1", "settings_resolved")[0]
    assert rec["rows"] == shown["rows"] and rec["settings_digest"] == shown["settings_digest"]
    assert rec["changed_keys"] == []
    started = _records(repo, "S-1", "run_started")[0]
    assert set(started["overridden_keys"]) == {"draft.timeout_s", "review.model", "judge:draft.timeout_s",
                                               "judge:review.timeout_s"}
    starts = {r["session_key"]: r for r in _records(repo, "S-1", "attempt_start")}
    assert any(k.startswith("draft") and r["timeout_s"] == 1200 for k, r in starts.items())
    assert any(k.startswith("review") and r["alias"] == "large" for k, r in starts.items() if "judge" not in k)
    assert all(r["timeout_s"] == 300 for k, r in starts.items() if "judge" in k)


def test_refused_setting_creates_nothing(repo: Path) -> None:  # RST-AC-2, RST-B5
    from .conftest import hash_tree
    from .test_cli import cli, happy

    before = hash_tree(repo)
    for argv in (["--set", "draft.criteria=x"], ["--set", "plann.model=large"], ["--profile", "nope"],
                 ["--set", "draft.approve=false"]):
        code, _, err = cli(repo, happy(), "run", "demo", "notes", *argv)
        assert code == 2 and err, argv
        code, doc, _ = cli(repo, happy(), "run", "demo", "notes", "--check", *argv)
        assert code == 2 and doc["status"] == "error" and doc["refusals"], argv
    assert hash_tree(repo) == before


def test_resume_reapplies_the_snapshot_and_records_changes(repo: Path, tmp_path: Path) -> None:  # RST-AC-5
    from tempergraph.executors.standins import standin

    from .test_cli import cli
    from .test_run import DRAFT, REVIEW, judge, verdict_block

    home = Path(os.environ["TEMPERGRAPH_HOME"])
    (home / "config").mkdir(parents=True, exist_ok=True)
    (home / "config" / "settings.json").write_text(json.dumps({"schema_version": 1,
                                                               "defaults": {"steps.timeout_s": 900}}))
    ex = standin("claude", steps=[DRAFT], judges=[judge(verdict_block("UNVERIFIABLE"))])
    code, _, _ = cli(repo, ex, "run", "demo", "notes", "--task-id", "S-2")
    assert code == 3
    (home / "config" / "settings.json").write_text(json.dumps({"schema_version": 1,
                                                               "defaults": {"steps.timeout_s": 50}}))
    ex.steps, ex.judges = [REVIEW], [judge()]
    code, _, err = cli(repo, ex, "resume", "demo", "S-2", "--decision", "proceed", "--set", "review.idle_s=45")
    assert code == 0, err
    first, second = _records(repo, "S-2", "settings_resolved")
    assert second["changed_keys"] == ["review.idle_s"] and second["caller"]["kind"] == "person"
    rows = {r["key"]: r for r in second["rows"]}
    assert rows["review.timeout_s"]["value"] == 900  # the snapshot, not the edited file
    assert first["settings_digest"] != second["settings_digest"]


def test_config_paths_and_validate(repo: Path) -> None:
    from .test_cli import cli

    code, doc, _ = cli(repo, None, "config", "paths")
    assert code == 0 and [f["layer"] for f in doc["files"]] == ["project", "user"]
    bad = repo / "s.json"
    bad.write_text(json.dumps({"schema_version": 1, "overrides": [{"workflow": "demo",
                                                                   "set": {"draft.tools.add": ["edit"]}}]}))
    code, doc, _ = cli(repo, None, "config", "validate", "--file", "s.json")
    assert code == 2 and doc["findings"][0]["code"] == "widening_in_file"
    code, doc, _ = cli(repo, None, "config", "validate")
    assert code == 0 and doc["ok"]
