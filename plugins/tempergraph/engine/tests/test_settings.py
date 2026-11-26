"""Run settings: catalog, layers, files, profiles and the effective spec (RST-B16 to RST-B32, B1–B11, AC-3, AC-7)."""

from __future__ import annotations

import dataclasses
import json
import os
import random
from pathlib import Path
from typing import Any

import pytest

from tempergraph.contracts import RunOptions, SettingDecl, WorkflowSpec, WorktreeDecl
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
                                           ("draft.deadline_s", "setting_not_for_kind"),  # RST-B10: a step has no deadline
                                           ("draft.bogus", "unknown_setting"), ("run.retry_budget", "setting_not_for_kind"),
                                           ("draft.approve", "tighten_only"), ("judges.model", "setting_value"),
                                           ("draft.retry_budget", "setting_value"),
                                           ("draft.on_budget_spent", "no_fallback_target"),
                                           ("run.worktree.root", "setting_value"),
                                           ("draft.tools.add", "unknown-capability"),
                                           ("judge:draft.views.add", "judge-view-not-read-only"),
                                           ("judge:draft.views.add", "judge-view-unclassified"),
                                           ("draft.commands.add", "command-metacharacter")])
def test_refusals(key: str, code: str) -> None:  # RST-B5, B6, B10, RST-B32
    value = {"draft.approve": False, "judges.model": ["small", "large"], "draft.retry_budget": 99,
             "draft.on_budget_spent": "fallback", "run.worktree.root": "path:relative/dir",
             "draft.commands.add": "npm run build; rm"}.get(key, "x")
    if key == "judge:draft.views.add":
        value = "edit" if code == "judge-view-not-read-only" else "mcp:tracker/get_issue"
    _, findings = go(spec(), {key: value})
    assert [f.code for f in findings] == [code], findings
    if code == "unknown_setting" and key.startswith("drafft"):
        assert "draft" in findings[0].message


@pytest.mark.parametrize(("key", "value"), [("run.worktree.root", "in_repo"), ("run.worktree.root", "sibling"),
                                            ("run.worktree.root", "path:/var/worktrees"),
                                            ("run.worktree.base", "default_branch"), ("run.worktree.base", "head"),
                                            ("run.worktree.base", "ref:release/1"),
                                            ("run.worktree.cleanup", "on_finish")])
def test_worktree_extras_are_accepted(key: str, value: str) -> None:  # WTR-AC3 (WTR-B17): no setting_not_in_release
    res, findings = go(spec(), {key: value})
    assert findings == [] and res.values[key] == value


@pytest.mark.parametrize("value", ["elsewhere", "path:", "path:relative/dir", "in_repo/x"])
def test_worktree_root_stays_refused_for_other_values(value: str) -> None:  # WTR-AC3 (WTR-B17)
    _, findings = go(spec(), {"run.worktree.root": value})
    assert [f.code for f in findings] == ["setting_value"], findings


def test_a_workflows_own_worktree_base_is_not_refused() -> None:  # WTR-AC3 (WTR-B17, WTR-B19)
    sp = spec(worktree=WorktreeDecl(base="default_branch", cleanup="on_finish"))
    res, findings = go(sp, {})
    assert findings == []
    assert res.values["run.worktree.base"] == "default_branch" and res.values["run.worktree.cleanup"] == "on_finish"


def council_spec() -> WorkflowSpec:
    from tempergraph.api import Chair, Council, Gate, Judge, Member

    from .fixtures.workflows import crit

    s = spec()
    unit = Council(question="Which design?", members=[Member(name="a", model="large"), Member(name="b")],
                   chair=Chair(), gate=Gate(judge=Judge(stance="V."), criteria=[crit("c1")]))
    return dataclasses.replace(s, units={"decide": unit, **s.units}, order=("decide", *s.order))


def test_the_steps_scope_reaches_member_and_chair_sessions() -> None:  # CNL-AC1 (CNL-B9, RST-B22)
    flags = {"steps.session_cost_cap_usd": 0.5, "steps.model": "small", "steps.executor": "claude"}
    res, findings = go(council_spec(), flags)
    assert findings == [], findings
    eff = effective_spec(council_spec(), res).units["decide"]
    assert eff.council is not None and eff.council.chair is not None
    assert [m.model for m in eff.council.members] == ["large", "small"]  # a member's own model is kept
    assert all(m.executor == "claude" for m in eff.council.members) and eff.council.chair.model == "small"
    assert eff.extra["session_cost_cap_usd"] == 0.5
    plain = effective_spec(council_spec(), go(council_spec())[0]).units["decide"]
    assert plain.extra.get("session_cost_cap_usd") is None  # nothing is set by default


@pytest.mark.parametrize("key", ["decide.model", "decide.session_cost_cap_usd", "decide.executor"])
def test_a_unit_key_on_a_council_is_still_refused(key: str) -> None:  # CNL-AC1 (CNL-B9, RST-B10)
    _, findings = go(council_spec(), {key: "small" if key.endswith("model") else "claude" if "executor" in key else 1.0})
    assert [f.code for f in findings] == ["setting_not_for_kind"], findings


def test_the_council_key_scopes_stay_refused() -> None:  # CNL-AC1 (RST-B10)
    _, findings = go(council_spec(), {"decide.member:a.model": "small"})
    assert [f.code for f in findings] == ["setting_not_for_kind"]


def test_grd_ac6_an_mcp_view_grant_stays_refused_and_its_message_names_the_catalog() -> None:  # GRD-AC6, RST-B28
    _, findings = go(spec(), {"judge:draft.views.add": "mcp:tracker/get_issue"})
    assert [f.code for f in findings] == ["judge-view-unclassified"]
    message = findings[0].message
    assert "release 1" not in message and "no read-only MCP catalog" not in message
    assert "catalog" in message  # a judge sees an MCP tool only through the engine's view catalog


def test_audit_settings_are_accepted_and_resolved() -> None:  # ROP-AC1, RST-B20, RST-B32
    res, findings = go(spec())
    assert not findings and res.values["run.audit_rate"] == 0.0  # the audit judge is off by default
    assert res.values.get("run.audit_executor") is None
    res, findings = go(spec(), {"run.audit_rate": 0.25, "run.audit_executor": "claude"})
    assert not findings, findings  # no `setting_not_in_release`
    assert res.values["run.audit_rate"] == 0.25 and res.values["run.audit_executor"] == "claude"
    assert row(res, "run.audit_rate")["layer"] == "flag" and row(res, "run.audit_executor")["layer"] == "flag"
    _, findings = go(spec(), {"run.audit_rate": 1.5})
    assert [f.code for f in findings] == ["setting_value"]


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


def test_property_no_step_key_reaches_a_judge_and_tighten_only_stays_true() -> None:  # RST-AC3
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


def test_snapshot_reapplies_without_files() -> None:  # RST-AC5
    files = ConfigFiles(user={"schema_version": 1, "defaults": {"steps.timeout_s": 900}})
    opts, _ = options_snapshot(spec(), {}, (), files)
    again = resolve(spec(), RunOptions(settings=json.loads(json.dumps(opts.settings)), profiles=opts.profiles))
    assert again.digest == resolve(spec(), opts).digest and again.values["draft.timeout_s"] == 900


# ---------------------------------------------------------------------------------------------
# Through the CLI and the runner


def _records(repo: Path, task: str, kind: str) -> list[dict[str, Any]]:
    log = repo / ".tempergraph" / "runs" / "demo" / task / "run.jsonl"
    return [r for r in (json.loads(x) for x in log.read_text().splitlines()) if r.get("kind") == kind]


def test_run_records_settings_and_show_equals_run(repo: Path) -> None:  # RST-B9, RST-B27
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


def test_refused_setting_creates_nothing(repo: Path) -> None:  # RST-AC2, RST-B5
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


def test_resume_reapplies_the_snapshot_and_records_changes(repo: Path, tmp_path: Path) -> None:  # RST-AC5
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


# ---------------------------------------------------------------------------------------------
# Tool grants (RST-B28, RST-B29, RST-B30, RST-B13)


def test_grants_widen_the_step_and_the_allow_list() -> None:
    res, findings = go(spec(), {"draft.tools.add": "mcp:tracker/get_issue", "draft.commands.add": ["npm run build"],
                                "judge:review.views.add": ["web_fetch"]})
    assert not findings
    eff = effective_spec(spec(), res)
    assert "mcp:tracker/get_issue" in eff.units["draft"].step.tools
    assert "npm run build" in eff.units["draft"].step.commands and "npm run build" in eff.allow_commands
    assert eff.units["review"].extra["views_add"] == ("web_fetch",)
    assert all(r.get("widening") for r in rows_json(res) if r["key"].endswith(".add"))


def test_an_agent_cannot_widen() -> None:
    _, findings = options_snapshot(spec(), {"draft.tools.add": ["edit"]}, (), ConfigFiles(), caller_kind="agent")
    assert [f.code for f in findings] == ["widening_by_agent"]


def test_property_no_grant_gives_a_judge_a_writing_tool() -> None:  # RST-AC8
    rnd = random.Random(3)
    pool = ["read", "search", "list", "edit", "write", "shell", "web_fetch", "web_search", "subagent",
            "mcp:tracker/create_issue", "skill:kit:review"]
    for _ in range(200):
        views = rnd.sample(pool, rnd.randint(1, 4))
        res, findings = go(spec(), {"judge:draft.views.add": views})
        if findings:
            continue
        eff = effective_spec(spec(), res)
        assert set(eff.units["draft"].extra.get("views_add") or ()) <= {"read", "search", "list", "web_fetch",
                                                                         "web_search"}


def test_tool_access_pause_offers_the_grant_and_resume_applies_it(repo: Path) -> None:  # RST-B13
    from tempergraph.executors.standins import answer, standin

    from .test_cli import cli
    from .test_run import DRAFT, REVIEW, judge

    blocked = answer("Could not read the tracker\nBLOCKED: tracker tool refused", denied=("mcp__tracker__get_issue",))
    ex = standin("claude", steps=[blocked], judges=[])
    code, doc, err = cli(repo, ex, "run", "demo", "notes", "--task-id", "G-1", "--json")
    assert code == 3, err
    offers = doc["payload"]["tool_access"]
    assert offers[0]["class"] == "undeclared_tool" and "--grant draft=mcp:tracker/get_issue" in offers[0]["fix"]
    pause = _records(repo, "G-1", "pause")[-1]
    assert pause["reason"] == "tool_access" and pause["tool_access"][0]["capability"] == "mcp:tracker/get_issue"
    seen: list[Any] = []

    def draft(req: Any) -> Any:
        seen.append(req.tools)
        return DRAFT

    ex.steps, ex.judges = [draft, REVIEW], [judge(), judge()]
    code, _, err = cli(repo, ex, "resume", "demo", "G-1", "--decision", "retry", "--grant",
                       "draft=mcp:tracker/get_issue")
    assert code == 0, err
    assert "mcp:tracker/get_issue" in seen[0]
    grant = _records(repo, "G-1", "grant")[0]
    assert grant["action"] == "given" and grant["by"]["kind"] == "person"
    assert grant["answers"] == {"class": "undeclared_tool", "seq": pause["seq"]}
    ledger = [json.loads(x) for x in (repo / ".tempergraph" / "ledger.jsonl").read_text().splitlines()]
    row = next(r for r in ledger if r.get("kind") == "intervention")
    assert row["grants"][0]["capability"] == "mcp:tracker/get_issue"
    seg = [r for r in ledger if r.get("kind") == "run_segment"][-1]
    assert seg["grants"][0]["capability"] == "mcp:tracker/get_issue"
    shown = cli(repo, None, "config", "show", "demo", "--thread", "G-1", "--key", "draft.tools.add")[1]
    assert shown["rows"][0]["value"] == ["mcp:tracker/get_issue"]  # kept for later resumes


def test_an_operator_moves_a_wait_or_ask_deadline() -> None:  # RST-B18, RST-B19, RST-B20, RST-B21 `deadline_s`, FLX-B8
    from .test_ask_wait import waiting_wf

    sp = waiting_wf(deadline_s=600, on_deadline="stop")
    res, findings = go(sp, {"signoff.deadline_s": 60})
    assert findings == []
    eff = effective_spec(sp, res)
    assert eff.units["signoff"].wait.deadline_s == 60 and eff.units["signoff"].wait.on_deadline == "stop"  # type: ignore[union-attr]
    _, refused = go(sp, {"plan.deadline_s": 60})
    assert [f.code for f in refused] == ["setting_not_for_kind"]


def contested(**fields: Any) -> WorkflowSpec:
    from .test_contest_run import contest_spec

    return contest_spec(slots=3, concurrency=3, cost_cap_usd=1.0, **fields)


def test_rst_ac1_a_contests_two_keys_are_accepted_from_every_layer() -> None:  # RST-AC1 (RST-B19), CTS-AC6
    sp = contested()
    res, findings = go(sp)
    assert findings == [] and res.values["pick.concurrency"] == 3  # the unit's own declared values
    assert res.values["pick.attempt_cost_cap_usd"] == 1.0
    assert row(res, "pick.concurrency")["layer"] == "workflow:unit"
    res, findings = go(sp, {"pick.concurrency": 1, "pick.attempt_cost_cap_usd": 0.4})
    assert findings == [] and (row(res, "pick.concurrency")["layer"], row(res, "pick.attempt_cost_cap_usd")["layer"]) == (
        "flag", "flag")  # a flag resolves over what the unit declares
    assert (res.values["pick.concurrency"], res.values["pick.attempt_cost_cap_usd"]) == (1, 0.4)
    project = ConfigFiles(project={"schema_version": 1, "overrides": [{"workflow": "demo", "set": {
        "pick.concurrency": 2, "pick.attempt_cost_cap_usd": 0.7}}]}, project_path=Path("/p/settings.json"))
    res, findings = go(sp, files=project)
    assert findings == [] and row(res, "pick.concurrency")["layer"] == "project:overrides"
    assert (res.values["pick.concurrency"], res.values["pick.attempt_cost_cap_usd"]) == (2, 0.7)
    from .test_contest_run import contest_spec

    user = ConfigFiles(user={"schema_version": 1, "overrides": [{"workflow": "demo", "set": {
        "pick.attempt_cost_cap_usd": 0.9, "pick.concurrency": 4}}]}, user_path=Path("/u/settings.json"))
    res, findings = go(contest_spec(slots=3), files=user)  # no declared cap: the user's value is the cap
    assert findings == [] and res.values["pick.attempt_cost_cap_usd"] == 0.9 and res.values["pick.concurrency"] == 4
    assert row(res, "pick.attempt_cost_cap_usd")["layer"] == "user:overrides"
    profile = ConfigFiles(user={"schema_version": 1, "profiles": {"fast": {"pick.concurrency": 2}}},
                          user_path=Path("/u/settings.json"))
    res, findings = go(sp, profiles=("fast",), files=profile)
    assert findings == [] and res.values["pick.concurrency"] == 2 and row(res, "pick.concurrency")["layer"] == "profile"


def test_rst_ac1_the_resolved_values_reach_the_contest_the_run_executes() -> None:  # RST-AC1 (RST-B19), CTS-AC6
    sp = contested()
    res, _ = go(sp, {"pick.concurrency": 1, "pick.attempt_cost_cap_usd": 0.4})
    eff = effective_spec(sp, res)
    c = eff.units["pick"].contest
    assert c is not None and (c.concurrency, c.cost_cap_usd) == (1, 0.4)
    assert sp.units["pick"].contest.concurrency == 3 and sp.units["pick"].contest.cost_cap_usd == 1.0  # type: ignore[union-attr]
    plain, _ = go(sp)
    kept = effective_spec(sp, plain).units["pick"].contest
    assert kept is not None and (kept.concurrency, kept.cost_cap_usd) == (3, 1.0)


@pytest.mark.parametrize(("key", "value"), [("draft.concurrency", 2), ("draft.attempt_cost_cap_usd", 0.5),
                                            ("steps.concurrency", 2), ("run.concurrency", 2),
                                            ("judge:draft.concurrency", 2)])
def test_rst_ac1_the_two_keys_are_refused_on_any_other_kind_of_unit(key: str, value: Any) -> None:  # RST-AC1 (RST-B19)
    _, findings = go(spec(), {key: value})
    assert [f.code for f in findings] == ["setting_not_for_kind"], findings


def test_rst_ac1_concurrency_stays_refused_on_a_map() -> None:  # RST-AC1 (RST-B19)
    from .test_map_concurrent import concurrent

    _, findings = go(concurrent(concurrency=2), {"phase.concurrency": 1})
    assert [f.code for f in findings] == ["setting_not_for_kind"], findings


@pytest.mark.parametrize(("key", "value"), [("pick.concurrency", 6), ("pick.concurrency", 0), ("pick.concurrency", -1),
                                            ("pick.attempt_cost_cap_usd", 0), ("pick.attempt_cost_cap_usd", -1.5),
                                            ("pick.attempt_cost_cap_usd", "x")])
def test_rst_ac1_an_out_of_range_value_is_refused(key: str, value: Any) -> None:  # RST-AC1 (RST-B19)
    _, findings = go(contested(), {key: value})
    assert [f.code for f in findings] == ["setting_value"], findings


@pytest.mark.parametrize("level", ["record", "file", "propose", "trial"])
def test_rst_ac1_loop_autonomy_is_accepted_from_every_layer(level: str) -> None:  # RST-AC1 (PRP-B31, RST-B20)
    from tempergraph.settings import CATALOG, run_values

    assert "loop_autonomy" in CATALOG and CATALOG["loop_autonomy"].default is None  # no default: unset lowers nothing
    assert CATALOG["loop_autonomy"].scopes == CATALOG["loop_model"].scopes  # a run-scope key
    res, findings = go(spec(), {"run.loop_autonomy": level})
    assert findings == [] and run_values(res)["loop_autonomy"] == level and row(res, "run.loop_autonomy")["layer"] == "flag"
    project = ConfigFiles(project={"schema_version": 1, "overrides": [{"workflow": "demo", "set": {
        "run.loop_autonomy": level}}]}, project_path=Path("/p/settings.json"))
    res, findings = go(spec(), files=project)
    assert findings == [] and run_values(res)["loop_autonomy"] == level
    user = ConfigFiles(user={"schema_version": 1, "defaults": {"run.loop_autonomy": level}},
                       user_path=Path("/u/settings.json"))
    res, findings = go(spec(), files=user)
    assert findings == [] and run_values(res)["loop_autonomy"] == level
    profile = ConfigFiles(user={"schema_version": 1, "profiles": {"held": {"run.loop_autonomy": level}}},
                          user_path=Path("/u/settings.json"))
    res, findings = go(spec(), profiles=("held",), files=profile)
    assert findings == [] and run_values(res)["loop_autonomy"] == level and row(res, "run.loop_autonomy")["layer"] == "profile"


def test_rst_ac1_loop_autonomy_refuses_any_other_value_and_is_unset_by_default() -> None:  # RST-AC1 (PRP-B31)
    from tempergraph.settings import run_values

    _, findings = go(spec(), {"run.loop_autonomy": "always"})
    assert [f.code for f in findings] == ["setting_value"], findings
    res, findings = go(spec())
    assert findings == [] and run_values(res).get("loop_autonomy") is None


def test_a_slot_scope_key_stays_refused_and_its_message_no_longer_says_release_3() -> None:  # RST-AC1 (RST-B17, RST-B18)
    _, findings = go(contested(), {"pick.slot:s1.model": "small"})
    assert [f.code for f in findings] == ["setting_not_for_kind"], findings
    assert "release 3" not in findings[0].message and "slot" in findings[0].message


def test_rst_ac2_a_contests_base_step_takes_the_unit_and_steps_keys() -> None:  # RST-AC2 (RST-B2, RST-B17, RST-B23)
    sp = contested()
    res, findings = go(sp, {"steps.model": "small", "pick.timeout_s": 900, "pick.retry_budget": 1})
    assert findings == []
    eff = effective_spec(sp, res)
    unit = eff.units["pick"]
    assert unit.step is not None and unit.step.model == "small" and unit.step.timeout_s == 900
    assert unit.gate.retry_budget == 1 and unit.contest is not None and unit.contest.concurrency == 3
    assert "model" in (unit.extra.get("operator_set") or ())  # an operator's model is no slot's to override
