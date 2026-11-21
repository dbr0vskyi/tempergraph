"""Workflow audit (AUD, ARC, PRA; plan T8.5): the catalog, every built rule raised by a fixture and quiet on a
clean one, owned checks rendered once, ignores, the formats, `--fail-on`, read-only and model-free."""

from __future__ import annotations

import dataclasses
import datetime as dt
import io
import json
import re
from pathlib import Path
from typing import Any

import pytest

from tempergraph.api import Criterion, Gate, Judge, Routing, Script, Step, Value, Workflow
from tempergraph.audit import AuditContext, audit
from tempergraph.audit import catalog as cat
from tempergraph.audit.report import AuditFinding, AuditReport, Ignore, apply_ignores, parse_ignores
from tempergraph.cli.main import main
from tempergraph.contracts import ProbeReport, WorkflowSpec
from tempergraph.docs import read_json
from tempergraph.executors.capabilities import DECLARED
from tempergraph.executors.launcher import ShellTiming
from tempergraph.executors.registry import Registry
from tempergraph.executors.standins import standin

from .conftest import hash_tree
from .fixtures.packages import minimal_package, package_parts, write
from .fixtures.workflows import draft_check, named

CAPS = {"claude": DECLARED["claude"]}
FAST = ShellTiming(login_s=0.05, plain_s=0.01)


def ctx(tmp: Path, **kw: Any) -> AuditContext:
    base: dict[str, Any] = {"target": tmp, "caps": CAPS, "probe": lambda name: "2.1.329",
                            "timing": lambda budget: FAST, "which": lambda prog: f"/usr/bin/{prog}",
                            "plugin_cache": tmp / "no-cache"}
    base.update(kw)
    return AuditContext(**base)


def crit(cid: str, text: str = "The output is good", **kw: Any) -> Criterion:
    return Criterion(id=cid, text=text, check_method=kw.pop("check_method", "Read the output"), **kw)


def judge(**kw: Any) -> Any:
    kw.setdefault("timeout_s", 300)
    return Judge(stance="Verify against the artifacts.", brief="Read the artifacts.", **kw)


def clean_step(**kw: Any) -> Any:
    kw.setdefault("prompt", "Write the notes for {request} into notes.")
    kw.setdefault("tools", ["read", "write"])
    kw.setdefault("produces", {"notes": "file"})
    kw.setdefault("timeout_s", 900)
    gate = kw.pop("gate", None) or Gate(check=draft_check, judge=judge(references=["notes"]), criteria=[crit("c1")])
    return Step(gate=gate, **kw)


def wf(units: dict[str, Any], **fields: Any) -> WorkflowSpec:
    fields.setdefault("routing", Routing(description="Write notes"))
    fields.setdefault("issue_repository", "acme/notes")
    return named(Workflow(order=list(units), units=units, **fields))


def rules(rep: AuditReport) -> set[str]:
    return {f.rule for f in rep.findings}


def own_rules(rep: AuditReport) -> set[str]:
    return {f.rule for f in rep.findings if f.owner == "audit"}


def run(spec: WorkflowSpec, tmp: Path, layers: set[str] | None = None, **kw: Any) -> AuditReport:
    return audit(spec, layers or {"definition", "host"}, ctx(tmp, **kw))  # type: ignore[arg-type]


# -- the catalog (ARC-AC-1 to AC-3) ------------------------------------------------------------------------------


def test_catalog_records_are_complete() -> None:
    ids = [r.id for r in cat.RULES]
    assert len(ids) == len(set(ids))
    for r in cat.RULES:
        assert re.fullmatch(r"[a-z0-9]+(-[a-z0-9]+)*", r.id), r.id
        assert r.layer in cat.LAYERS and r.family in cat.FAMILY_RANK and r.remedy, r.id
        assert r.severity in ("error", "warning", "info", "per owner") and r.owner, r.id
        assert r.confidence in ("high", "medium", "low", "per owner"), r.id
        if r.severity == "per owner":
            assert r.owner != "audit", r.id
        if r.layer == "history":
            assert r.min_n is not None and r.min_n >= 1, r.id


def test_every_family_has_a_rule_and_params_name_their_source() -> None:
    families = {r.family for r in cat.RULES}
    assert {f"C{i}" for i in range(1, 8)} - {"C4"} <= families  # C4 is TSA's (ARC §2.8), release 2
    assert "C8" in families
    for p in cat.PARAMS.values():
        assert p.default > 0 and p.source, p.name


def test_owned_rules_call_their_owner() -> None:
    """ARC-AC-4: the audit renders owned findings and has no copy of their logic."""
    src = Path(cat.__file__).parent
    body = "".join(p.read_text(encoding="utf-8") for p in src.glob("*.py"))
    assert "from tempergraph.model.validate import" in body and "readiness(spec)" in body
    assert "executor_compat.finding(" in body
    for owned_pattern in ("VAGUE", "SELF_GRADING", "HUMAN_WAIT", "ACCEPTING", "_structural"):
        assert owned_pattern not in body
    owned_ids = {r.id for r in cat.RULES if r.owner != "audit"}
    for rid in owned_ids:
        assert f'self.add("{rid}"' not in body, rid


# -- definition rules: each raised by a fixture, quiet on a clean one (AUD-AC-1) ----------------------------------


def test_clean_fixture_raises_no_audit_rule(tmp_path: Path) -> None:
    rep = run(wf({"draft": clean_step()}, allow_commands=["git status"]), tmp_path)
    assert own_rules(rep) == set(), [f.statement for f in rep.findings if f.owner == "audit"]


C1_UNITS = {
    "plan": clean_step(prompt="Write the plan into notes.", gate=Gate(check=None, judge=judge(references=["notes"]), criteria=[
        crit("c-loop", no_change_policy="retry"),
        crit("c-tracker", "The ticket is linked", unverified_system="tracker"),
        crit("c-file", "The notes file exists in the workspace"),
        *[crit(f"c{i}", f"Part {i} is right") for i in range(7)],
    ])),
}


@pytest.mark.parametrize("rule", ["oversized-step", "no-change-blocker-retries", "unverified-blocker",
                                  "single-criterion-gate-judge-only"])
def test_c1_rules(tmp_path: Path, rule: str) -> None:
    rep = run(wf(C1_UNITS), tmp_path)
    assert rule in rules(rep)


@pytest.mark.parametrize(("timeout_s", "fires", "hours"), [(600, False, 1), (3600, True, 6), (7200, True, 12)])
def test_hold_time_arithmetic(tmp_path: Path, timeout_s: int, fires: bool, hours: int) -> None:
    """ARC-B2 as a table test: timeout x (retry_budget + 1) + timeout x infra tries."""
    spec = wf({"code": clean_step(timeout_s=timeout_s, idle_s=300)})
    found = [f for f in run(spec, tmp_path).findings if f.rule == "hold-time-exposure" and f.unit == "code"]
    assert bool(found) is fires
    if fires:
        assert found[0].evidence["hold_h"] == hours


def test_workflow_hold_over_twelve_hours(tmp_path: Path) -> None:
    units = {f"u{i}": clean_step(timeout_s=3000, idle_s=300) for i in range(3)}  # 5 h each
    found = [f for f in run(wf(units), tmp_path).findings if f.rule == "hold-time-exposure" and f.item == "order"]
    assert found and found[0].evidence["hold_h"] == 15


@pytest.mark.parametrize(("step_kw", "judge_kw", "rule"), [
    ({"timeout_s": None}, {}, "default-step-timeout"),
    ({}, {"timeout_s": None}, "default-judge-timeout"),
    ({"timeout_s": 600, "idle_s": 600}, {}, "idle-limit-inert"),
    ({"timeout_s": 2400}, {}, "no-idle-limit"),
])
def test_c3_rules(tmp_path: Path, step_kw: dict[str, Any], judge_kw: dict[str, Any], rule: str) -> None:
    j = Judge(stance="Verify.", brief="Read the notes.", references=["notes"], timeout_s=judge_kw.get("timeout_s", 300))
    spec = wf({"draft": clean_step(gate=Gate(check=draft_check, judge=j, criteria=[crit("c1")]), **step_kw)})
    assert rule in rules(run(spec, tmp_path))


def test_c5_rules(tmp_path: Path) -> None:
    g = Gate(check=draft_check, judge=judge(references=["notes"]), criteria=[crit("c1")], retry_budget=0,
             approval=True)
    rep = run(wf({"a": clean_step(gate=g), "b": clean_step()}), tmp_path)
    assert "every-retry-asks" in rules(rep)
    rep = run(wf({"a": clean_step(gate=g), "b": clean_step(gate=dataclasses.replace(g, retry_budget=1))}), tmp_path)
    assert "approval-on-most-gates" in rules(rep) and "every-retry-asks" in rules(rep)


def test_c6_rules(tmp_path: Path) -> None:
    small = Gate(check=draft_check, judge=judge(references=["notes", "plan"], model="small"), criteria=[crit("c1")])
    spec = wf({"a": clean_step(produces={"notes": "file", "plan": "file"}, prompt="Write notes and plan.",
                               gate=small)})
    assert "small-judge-cross-file" in rules(run(spec, tmp_path))
    big = Gate(check=draft_check, judge=judge(references=["notes"], model="large"), criteria=[crit("c1")])
    spec = wf({"a": clean_step(model="large", gate=big)}, improvement_mode="stable")
    found = rules(run(spec, tmp_path))
    assert {"large-everywhere", "no-run-cost-cap"} <= found


# -- prompt audit (PRA) -----------------------------------------------------------------------------------------


@pytest.mark.parametrize(("template", "tools", "conflict"), [
    ("Never run commands. Write the notes.", ["read", "write", "shell"], True),
    ("Never run commands. Write the notes.", ["read", "write"], False),
    ("Use `Grep` to search, then write the notes.", ["read", "write", "search"], False),
])
def test_prompt_tool_conflict_table(tmp_path: Path, template: str, tools: list[str], conflict: bool) -> None:
    """PRA-B3 rows 1 and 3."""
    spec = wf({"draft": clean_step(prompt=template, tools=tools, commands=["pytest"] if "shell" in tools else [])},
              allow_commands=["pytest"])
    found = [f for f in run(spec, tmp_path).findings if f.rule == "prompt-tool-conflict"]
    assert bool(found) is conflict
    if conflict:
        assert found[0].location["line"] == 1 and found[0].item == "shell"


@pytest.mark.parametrize("executor", sorted(DECLARED))
def test_foreign_tool_name_across_the_tool_maps(executor: str) -> None:
    """PRA-AC-2 / PRA-B3 row 4: a tool name of another executor is owned by prompt lint, once."""
    from tempergraph.model.prompt_lint import lint

    spec = wf({"draft": clean_step(prompt="Use `Grep` to search, then write the notes.", executor=executor,
                                   tools=["read", "write", "search"])})
    own = {t for ts in DECLARED[executor].tool_map.values() for t in ts}
    codes = [f.code for f in lint(spec)]
    assert codes.count("lint-tool-name-foreign") == (0 if "Grep" in own else 1)


def test_artifact_reach_and_long_output(tmp_path: Path) -> None:
    units = {
        "draft": clean_step(prompt="Write the complete document in one answer.", produces={"notes": "file"}),
        "review": clean_step(prompt="Review the notes into verdict.", produces={"verdict": Value(choices=["ok"])},
                             gate=Gate(judge=judge(), criteria=[crit("c2", "The verdict matches `notes`")])),
    }
    found = run(wf(units), tmp_path).findings
    by = {(f.rule, f.unit) for f in found}
    assert ("artifact-not-asked", "draft") in by  # `notes` is never named in the draft template
    assert ("one-shot-long-output", "draft") in by
    assert ("criterion-not-in-reach", "review") in by


def test_skill_frontmatter_only_when_portable(tmp_path: Path) -> None:
    root = minimal_package(tmp_path)
    write(root, "skills/notes/SKILL.md", "---\nname: notes\ndescription: x\nmodel: haiku\n---\nBody\n")
    from tempergraph.package.loader import load_package

    lp = load_package(root)
    rep = audit(lp.spec, {"definition"}, ctx(tmp_path), manifest=lp.manifests.engine)
    assert "skill-frontmatter-nonstandard" not in rules(rep)  # claude only: the extra field is allowed
    manifest = dataclasses.replace(lp.manifests.engine, surfaces={"antigravity": {"skills_dir": "skills"}})
    rep = audit(lp.spec, {"definition"}, ctx(tmp_path), manifest=manifest)
    f = next(f for f in rep.findings if f.rule == "skill-frontmatter-nonstandard")
    assert f.evidence["fields"] == ["model"] and f.location["file"] == "skills/notes/SKILL.md"


# -- host rules ---------------------------------------------------------------------------------------------------


def test_host_toolchain_and_missing_program(tmp_path: Path) -> None:
    """AUD-B4."""
    target = tmp_path / "target"
    write(target, "package.json", {"scripts": {"test": "jest"}})
    spec = wf({"draft": clean_step(tools=["read", "write", "shell"], commands=["test"])}, allow_commands=["test"])
    rep = run(spec, tmp_path, layers={"host"}, target=target)
    f = next(f for f in rep.findings if f.rule == "toolchain-not-covered")
    assert "package.json scripts.test" in f.evidence["documented"]
    assert "check-program-missing" not in rules(rep)
    rep = run(spec, tmp_path, layers={"host"}, target=target, which=lambda prog: None)
    assert "check-program-missing" in rules(rep)
    covered = wf({"draft": clean_step(tools=["read", "write", "shell"], commands=["npm test"])},
                 allow_commands=["npm test"])
    assert "toolchain-not-covered" not in rules(run(covered, tmp_path, layers={"host"}, target=target))


def test_host_slow_shell_and_executor_range(tmp_path: Path) -> None:
    spec = wf({"draft": clean_step()})
    rep = run(spec, tmp_path, layers={"host"}, timing=lambda b: ShellTiming(login_s=16, plain_s=0.01),
              probe=lambda name: "2.3.0")
    assert {"slow-host", "executor-compat:executor-version-untested"} <= rules(rep)
    rep = run(spec, tmp_path, layers={"host"}, timing=lambda b: ShellTiming(login_s=0.4, plain_s=0.01))
    assert "slow-host" not in rules(rep)  # under the 1 s floor the ratio is noise
    rep = run(spec, tmp_path, layers={"host"}, timing=lambda b: None, probe=lambda name: None)
    skipped = {s["rule"]: s["reason"] for s in rep.rules_skipped}
    assert skipped["slow-host"] == "probe failed" and skipped["executor-outside-tested-range"].startswith("probe")


def test_skill_found_in_other_plugins(tmp_path: Path) -> None:
    """PRA-B2: named both plugins."""
    cache = tmp_path / "cache"
    for plugin in ("reviewers", "planning"):
        write(cache, f"market/{plugin}/1.0.0/skills/plan-review/SKILL.md", "---\nname: plan-review\n---\n")
    spec = wf({"draft": clean_step(prompt="Write the notes, then run skill `plan-review` on them.")})
    rep = run(spec, tmp_path, layers={"host"}, plugin_cache=cache)
    f = next(f for f in rep.findings if f.rule == "ref-resolves-elsewhere")
    assert f.evidence["plugins"] == ["planning", "reviewers"]


def test_tool_name_stale_against_the_stamp(tmp_path: Path) -> None:
    spec = wf({"draft": clean_step(prompt="Use `ReadFile` on the notes.")})
    stamp = {"engine_version": "0.0.1", "tool_set": {"claude": ["ReadFile", "Write"]}}
    rep = audit(spec, {"host"}, ctx(tmp_path), stamp=stamp)
    assert "tool-name-stale" in rules(rep)
    rep = audit(spec, {"host"}, ctx(tmp_path))
    assert any(s["rule"] == "tool-name-stale" for s in rep.rules_skipped)


# -- owned checks, ordering, layers (AUD-B1, B2, B8) ---------------------------------------------------------------


def test_owned_finding_appears_once(tmp_path: Path) -> None:
    """AUD-B8 / AUD-AC-4: a criterion with no check method is WFM's warning, never an audit rule too."""
    spec = wf({"draft": clean_step(gate=Gate(check=draft_check, judge=judge(references=["notes"]),
                                             criteria=[crit("c1", check_method="")]))})
    rep = run(spec, tmp_path)
    assert [f.rule for f in rep.findings].count("validate:criterion-no-check-method") == 1
    assert "criterion-without-method" not in rules(rep)
    assert {"owner": "validate", "count": 1} in rep.owned


def test_definition_only_before_first_run(tmp_path: Path) -> None:
    """AUD-B1: history is skipped with its reason and its rules are listed as skipped, never passed."""
    rep = audit(wf({"draft": clean_step()}), {"definition", "host", "history"}, ctx(tmp_path))
    assert rep.layers_run == ["definition", "host"]
    assert {"layer": "history", "reason": "not in release 1 (release 2)"} in rep.layers_skipped
    history = {r.id for r in cat.RULES if r.layer == "history"}
    assert history <= {s["rule"] for s in rep.rules_skipped}
    assert all("min_n" in s for s in rep.rules_skipped if s["rule"] in history)


def test_validation_error_leads(tmp_path: Path) -> None:
    """AUD-B2: a broken template leads, only definition runs."""
    spec = wf({"draft": clean_step(prompt="Write {request into notes."), "b": clean_step(timeout_s=None)})
    rep = run(spec, tmp_path)
    assert rep.findings[0].rule.startswith("validate:") and rep.findings[0].severity == "error"
    assert rep.layers_run == ["definition"]
    assert rep.exit_code("never") == 0 and rep.exit_code("error") == 6


# -- the report: quiet view, ignores, fail-on, formats ---------------------------------------------------------------


def finding(rule: str, severity: str = "warning", confidence: str = "high", unit: str | None = "u") -> AuditFinding:
    return AuditFinding(rule=rule, layer="definition", severity=severity, confidence=confidence, unit=unit,
                        statement=f"{rule} fired")


def test_quiet_by_default() -> None:
    """AUD-B7."""
    rep = AuditReport(workflow="w", version="1", engine_version="0.0.1")
    rep.findings = [finding("default-step-timeout"), finding("idle-limit-inert")]
    rep.findings += [finding("default-judge-timeout", "info", unit=f"u{i}") for i in range(6)]
    ignored = finding("every-retry-asks")
    ignored.ignored = {"reason": "accepted"}
    rep.findings.append(ignored)
    assert len(rep.visible()) == 2
    assert "2 shown, 6 info, 1 ignored" in rep.to_text()
    rep.show_all = True
    assert len(rep.visible()) == 9 and "[ignored]" in rep.to_text()


@pytest.mark.parametrize(("severities", "level", "code"), [
    (["warning"], "error", 0), (["error"], "error", 6), (["warning"], "warning", 6), (["info"], "warning", 0),
    (["error"], "never", 0), ([], "warning", 0),
])
def test_fail_on(severities: list[str], level: str, code: int) -> None:
    """AUD-AC-5."""
    rep = AuditReport(workflow="w", version="1", engine_version="0.0.1",
                      findings=[finding(f"r{i}", s, "low") for i, s in enumerate(severities)])
    assert rep.exit_code(level) == code
    for f in rep.findings:
        f.ignored = {"reason": "accepted"}
    assert rep.exit_code(level) == 0


def test_ignores() -> None:
    """AUD §2.4, AUD-AC-7."""
    igs, problems = parse_ignores([{"rule": "default-step-timeout", "reason": ""}, {"rule": "x"}, "bad"])
    assert igs == [] and len(problems) == 3
    igs, problems = parse_ignores([
        {"rule": "default-step-timeout", "unit": "u", "reason": "Measured fine.", "until": "2026-01-31"},
        {"rule": "validate:template-unbalanced", "reason": "No."},
        {"rule": "no-such-rule", "reason": "Typo."}])
    assert problems == []
    fs = [finding("default-step-timeout"), finding("validate:template-unbalanced", "error")]
    extra = apply_ignores(fs, igs, dt.date(2026, 1, 1))
    assert fs[0].ignored == {"reason": "Measured fine.", "until": "2026-01-31"}
    assert fs[1].ignored is None  # an ignore never hides a validation error
    assert [e.rule for e in extra] == ["ignore-rule-unknown"] and extra[0].severity == "info"
    fs = [finding("default-step-timeout")]
    apply_ignores(fs, [Ignore(rule="default-step-timeout", reason="r", until=dt.date(2026, 1, 31))],
                  dt.date(2026, 2, 1))
    assert fs[0].ignored is None  # a lapsed `until` shows the finding again


def test_ignore_without_reason_is_a_validation_error(tmp_path: Path) -> None:
    from tempergraph.model.validate import validate
    from tempergraph.package.loader import load_package

    root = minimal_package(tmp_path)
    doc = json.loads((root / "tempergraph.json").read_text())
    doc["audit"] = {"ignore": [{"rule": "default-step-timeout"}]}
    write(root, "tempergraph.json", doc)
    codes = {f.code: f.severity for f in validate(load_package(root).spec, CAPS)}
    assert codes.get("audit-ignore-invalid") == "error"


def test_json_schema_and_tolerant_reader(tmp_path: Path) -> None:
    """AUD-AC-6."""
    rep = run(wf({"draft": clean_step(timeout_s=None)}), tmp_path)
    doc = rep.to_json()
    assert doc["schema_version"] == 1
    for key in ("workflow", "version", "engine_version", "layers_run", "layers_skipped", "rules_skipped",
                "findings", "hot_spots", "owned", "summary"):
        assert key in doc
    for f in doc["findings"]:
        assert set(f) >= {"rule", "layer", "severity", "confidence", "cause", "unit", "item", "session",
                          "statement", "evidence", "remedy", "widening", "location", "ignored"}
    doc["a_future_key"] = {"x": 1}
    path = write(tmp_path, "audit.json", doc)
    assert read_json(path, "audit_report")["findings"] == doc["findings"]


def test_sarif_maps_findings_to_package_files(tmp_path: Path) -> None:
    root = minimal_package(tmp_path)
    reg = Registry()
    reg.register(standin("claude", probe_report=ProbeReport(ok=True, version="2.1.329")))
    out = io.StringIO()
    code = main(["audit", str(root), "--layer", "definition", "--format", "sarif", "--fail-on", "warning"],
                registry=reg, cwd=tmp_path, out=out, err=io.StringIO())
    sarif = json.loads(out.getvalue())
    assert code == 6 and sarif["version"] == "2.1.0"
    res = next(r for r in sarif["runs"][0]["results"] if r["ruleId"] == "default-step-timeout")
    assert res["level"] == "warning"
    assert res["locations"][0]["physicalLocation"]["artifactLocation"]["uri"] == "workflow/release_notes/__init__.py"


# -- the verb: read-only, model-free, refusals ------------------------------------------------------------------------


def test_audit_is_read_only_and_model_free(tmp_path: Path, repo: Path) -> None:
    """AUD-B6 / AUD-AC-2."""
    root = minimal_package(tmp_path / "src")
    ex = standin("claude", probe_report=ProbeReport(ok=True, version="2.1.329"))
    reg = Registry()
    reg.register(ex)
    state = repo / ".tempergraph"
    before = (hash_tree(root), hash_tree(repo), hash_tree(state))
    for argv in (["audit", str(root)], ["audit", str(root), "--format", "json", "--all"],
                 ["audit", "prompts", str(root)]):
        out = io.StringIO()
        assert main(argv, registry=reg, cwd=repo, out=out, err=io.StringIO()) == 0
    assert (hash_tree(root), hash_tree(repo), hash_tree(state)) == before
    assert ex.calls == []  # no step or judge session was started


def test_audit_prompts_rows(tmp_path: Path) -> None:
    root = minimal_package(tmp_path)
    out = io.StringIO()
    reg = Registry()
    reg.register(standin("claude"))
    assert main(["audit", "prompts", str(root), "--layer", "definition"], registry=reg, cwd=tmp_path, out=out,
                err=io.StringIO()) == 0
    rows = {r["file"]: r for r in json.loads(out.getvalue())["files"]}
    assert rows["prompts/draft.md"]["used_by"] == ["draft:step"]
    assert rows["judges/draft.md"]["used_by"] == ["draft:judge"]
    assert rows["prompts/draft.md"]["changed"].startswith("not recorded")


@pytest.mark.parametrize(("argv", "code"), [
    (["audit", "tools", "{root}"], 2), (["audit", "{root}", "--layer", "history"], 2),
    (["audit", "no-such-workflow"], 2), (["audit", "{root}", "--target", "nowhere"], 2),
])
def test_refusals(tmp_path: Path, argv: list[str], code: int) -> None:
    root = minimal_package(tmp_path)
    reg = Registry()
    reg.register(standin("claude"))
    err = io.StringIO()
    got = main([a.format(root=root) for a in argv], registry=reg, cwd=tmp_path, out=io.StringIO(), err=err)
    assert got == code, err.getvalue()


def test_not_loaded_is_one_finding(tmp_path: Path) -> None:
    """AUD §4: a workflow that does not load is one finding; exit 0, or 6 with `--fail-on error`."""
    root = minimal_package(tmp_path)
    write(root, "workflow/release_notes/__init__.py", "import nowhere_to_be_found\n")
    reg = Registry()
    reg.register(standin("claude"))
    for fail_on, code in (("never", 0), ("error", 6)):
        out = io.StringIO()
        got = main(["audit", str(root), "--format", "json", "--fail-on", fail_on], registry=reg, cwd=tmp_path,
                   out=out, err=io.StringIO())
        doc = json.loads(out.getvalue())
        assert got == code and [f["rule"] for f in doc["findings"]] == ["validate:not_loaded"]


def test_script_after_external_is_owned_by_validation(tmp_path: Path) -> None:
    after = Script(run=["git", "status"], side_effects="external")
    spec = wf({"draft": clean_step(after=[after])}, allow_commands=["git status"])
    found = rules(run(spec, tmp_path))
    assert "validate:external-after-without-approval" in found and "external-after-without-approval" not in found


def test_stamp_v4_fails_on_a_new_finding(tmp_path: Path, repo: Path) -> None:
    """WUP §2.6 V4: a finding at warning or above that the last stamp's list lacks blocks the stamp."""
    root = minimal_package(tmp_path / "src")
    out = io.StringIO()
    reg = Registry()
    reg.register(standin("claude"))
    assert main(["upgrade-check", str(root), "--stamp"], registry=reg, cwd=repo, out=out, err=io.StringIO()) == 0
    decl = root / "workflow/release_notes/__init__.py"
    decl.write_text(decl.read_text().replace("references=[\"notes\"]))", "references=[\"notes\"]), retry_budget=0)"))
    out = io.StringIO()
    assert main(["upgrade-check", str(root), "--stamp"], registry=reg, cwd=repo, out=out, err=io.StringIO()) == 4
    v4 = next(v for v in json.loads(out.getvalue())["verification"] if v["check"] == "V4 audit")
    assert v4["state"] == "failed" and "every-retry-asks" in v4["evidence"]


def test_stamp_v4_records_anew_on_a_newer_outcome_revision(tmp_path: Path, repo: Path) -> None:
    """WUP §2.6 V4: at `author verify`, an outcome revision newer than the stamped one records the audit
    list anew; the same revision still blocks, and so does `upgrade-check --stamp` at any revision."""
    from tempergraph.package.stamp import check, read_stamp

    root = minimal_package(tmp_path / "src")
    reg = Registry()
    reg.register(standin("claude"))
    caps = {"claude": reg.get("claude").capabilities()}
    assert check(root, caps, stamp=True, accept_revision=True).exit_code == 0
    first = read_stamp(root)
    assert first is not None
    decl = root / "workflow/release_notes/__init__.py"
    decl.write_text(decl.read_text().replace("references=[\"notes\"]))", "references=[\"notes\"]), retry_budget=0)"))
    assert check(root, caps, stamp=True, accept_revision=True).exit_code == 4  # same revision: still blocks
    outcome = root / "outcome.json"
    doc = json.loads(outcome.read_text())
    doc["revision"] = int(doc["revision"]) + 1
    outcome.write_text(json.dumps(doc))
    assert check(root, caps, stamp=True).exit_code == 4  # the upgrade path never records anew
    got = check(root, caps, stamp=True, accept_revision=True)
    v4 = next(v for v in got.checks if v.check == "V4 audit")
    assert got.exit_code == 0 and v4.state == "passed" and "every-retry-asks" in v4.evidence
    after = read_stamp(root)
    assert after is not None and after["outcome_revision"] == first["outcome_revision"] + 1
    assert any(k.startswith("every-retry-asks|") for k in after["audit"])


def test_package_parts_fixture_still_audits(tmp_path: Path) -> None:
    """A package written by `package_parts` (no docs tree) audits without a rule error."""
    root = package_parts(tmp_path / "p", "p", units=("draft",))
    write(root, ".claude-plugin/plugin.json", {"name": "p-tgraph", "version": "0.1.0"})
    write(root, "tempergraph.json", {"schema_version": 1, "name": "p", "entry": "p:workflow", "workflow_api": 1})
    write(root, "workflow/p/__init__.py", "from tempergraph.api import Gate, Step, Workflow\n\n\ndef workflow():\n"
          "    return Workflow(order=['draft'], units={'draft': Step(prompt='Write {request}.', gate=Gate())})\n")
    from tempergraph.package.loader import load_package

    lp = load_package(root)
    rep = audit(lp.spec, {"definition", "host"}, ctx(tmp_path), manifest=lp.manifests.engine)
    assert not [s for s in rep.rules_skipped if s["reason"].startswith("rule error")]


def test_outcome_trust_and_coverage(tmp_path: Path) -> None:
    """OUT §2.3 as read in release 1, and ARC `outcome-unverified-blocker`, `outcome-uncovered`."""
    import shutil

    from tempergraph.package.loader import load_package
    from tempergraph.run.outcome_trust import coverage, profile

    root = minimal_package(tmp_path)
    lp = load_package(root)
    assert lp.spec.outcome is not None
    cov = {c.criterion: c for c in coverage(lp.spec.outcome, lp.spec)}
    assert cov["rn-complete"].covered and cov["rn-complete"].trust == "uncalibrated"
    assert profile(lp.spec.outcome, lp.spec) == {"uncalibrated": 2, "deterministic": 1}
    rep = audit(lp.spec, {"definition"}, ctx(tmp_path), manifest=lp.manifests.engine)
    blockers = {f.item for f in rep.findings if f.rule == "outcome-unverified-blocker"}
    assert blockers == {"rn-complete", "rn-faithful"} and "outcome-uncovered" not in rules(rep)
    shutil.rmtree(root / "evals" / "checks" / "draft" / "must-fail")
    lp = load_package(root)
    rep = audit(lp.spec, {"definition"}, ctx(tmp_path), manifest=lp.manifests.engine)
    f = next(f for f in rep.findings if f.rule == "outcome-uncovered")
    assert f.item == "rn-complete" and f.evidence["missing_units"] == ["draft"]
