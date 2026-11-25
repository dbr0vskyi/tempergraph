"""Specs state general rules, not the task's case (issue 119): the spec rule's `General rules, not cases`, the
discovery prompt's extract step, the discovery check's ts-dis-named and ts-dis-literal, and the judge's
ts-dis-general."""

from __future__ import annotations

import json
import subprocess
import time
from pathlib import Path
from typing import Any

from tempergraph.package.loader import load_package
from tempergraph.run.checks import CheckContext, GitFacts, git_facts, run_check

ROOT = Path(__file__).resolve().parents[1]
SPEC = load_package(ROOT).spec
DISCOVERY = ROOT / "evals" / "checks" / "discovery"
SPEC_FILE = "docs/specs/config-file.spec.md"


def _copy(src: Path, dst: Path) -> None:
    for f in sorted(p for p in src.rglob("*") if p.is_file()):
        target = dst / f.relative_to(src)
        target.parent.mkdir(parents=True, exist_ok=True)
        target.write_bytes(f.read_bytes())


def _check(work: Path, git: GitFacts | None = None, task_id: str = "") -> Any:
    ctx = CheckContext(unit="discovery", workdir=work, request={"task_id": task_id} if task_id else {},
                       artifacts={"discovery": {"handoff": "handoff.md"}}, git=git or GitFacts(),
                       allow=SPEC.allow_commands, out_dir=work.parent / f"{work.name}.out",
                       deadline_at=time.monotonic() + 60)
    return run_check(SPEC.units["discovery"].gate, ctx)[0]


def _named(res: Any, criterion: str) -> list[str]:
    return [f.status for f in res.findings if f.criterion == criterion]


def _package(work: Path, name: str = "deploy") -> None:
    folder = work / "plugins" / f"{name}-tgraph"
    folder.mkdir(parents=True, exist_ok=True)
    (folder / "tempergraph.json").write_text(json.dumps({"schema_version": 1, "name": name}), encoding="utf-8")


def test_a_spec_outside_a_package_that_names_its_workflow_fails(tmp_path: Path) -> None:  # ts-dis-named
    res = _check(_fixture(DISCOVERY / "must-fail" / "names-a-workflow", tmp_path))
    assert res.result == "FAIL" and _named(res, "ts-dis-named") == ["fail"], res.evidence
    found = next(f for f in res.findings if f.criterion == "ts-dis-named")
    assert found.place.startswith(SPEC_FILE + ":") and "`deploy`" in found.message


def test_the_package_folder_name_counts_as_a_name_too(tmp_path: Path) -> None:  # ts-dis-named
    work = _fixture(DISCOVERY / "must-pass" / "2-new-spec", tmp_path)
    _package(work)
    spec = work / SPEC_FILE
    spec.write_text(spec.read_text().replace("WHEN the tool starts THEN the exit code is 2",
                                             "WHEN deploy-tgraph starts the tool THEN the exit code is 2"))
    assert _named(_check(work), "ts-dis-named") == ["fail"]


def test_a_spec_inside_its_own_package_may_name_its_workflow(tmp_path: Path) -> None:  # ts-dis-named
    res = _check(_fixture(DISCOVERY / "must-pass" / "3-own-package", tmp_path))
    assert res.result == "PASS" and _named(res, "ts-dis-named") == ["pass"], res.evidence


def test_a_word_that_merely_contains_a_name_is_not_a_hit(tmp_path: Path) -> None:  # ts-dis-named
    work = _fixture(DISCOVERY / "must-pass" / "2-new-spec", tmp_path)
    _package(work)
    spec = work / SPEC_FILE
    spec.write_text(spec.read_text().replace("names the missing file.", "names the missing file, as in redeployment."))
    assert _named(_check(work), "ts-dis-named") == ["pass"]


def test_change_words_issue_numbers_and_the_task_id_are_leads_not_failures(tmp_path: Path) -> None:  # ts-dis-literal
    work = _fixture(DISCOVERY / "must-pass" / "2-new-spec", tmp_path)
    spec = work / SPEC_FILE
    text = spec.read_text()
    text = text.replace("### CFG-B1 A missing config file is reported", "### CFG-B1 A missing config file no longer crashes")
    text = text.replace("GIVEN a folder with a `tool.toml`", "GIVEN the folder of issue #41 with a `tool.toml`")
    text = text.replace("GIVEN a folder with no `tool.toml` WHEN the tool starts THEN the exit code is 2",
                        "GIVEN the case of TASK-7 WHEN the tool starts THEN the exit code is 2")
    spec.write_text(text)
    res = _check(work, task_id="TASK-7")
    assert res.result == "MAYBE", res.evidence  # the judge reads them; a lead never retries the step
    leads = [f for f in res.findings if f.criterion == "ts-dis-literal"]
    assert [f.status for f in leads] == ["maybe"] * 3
    assert {f.message.split("`")[1] for f in leads} == {"no longer", "#41", "TASK-7"}


def test_a_general_spec_raises_no_lead(tmp_path: Path) -> None:  # ts-dis-literal
    res = _check(_fixture(DISCOVERY / "must-pass" / "2-new-spec", tmp_path), task_id="STANDIN-1")
    assert _named(res, "ts-dis-literal") == ["pass"] and _named(res, "ts-dis-named") == ["pass"]


def test_only_the_lines_the_run_added_are_read(tmp_path: Path) -> None:  # ts-dis-named, ts-dis-literal
    work = _fixture(DISCOVERY / "must-pass" / "2-new-spec", tmp_path)
    _package(work)
    spec = work / SPEC_FILE
    spec.write_text(spec.read_text().replace("names the missing file.", "names the missing file, no longer the deploy one."))
    git = ["git", "-C", str(work), "-c", "user.name=t", "-c", "user.email=t@t", "-c", "commit.gpgsign=false"]
    subprocess.run([*git, "init", "-q"], check=True)
    subprocess.run([*git, "add", "-A"], check=True)
    subprocess.run([*git, "commit", "-qm", "base"], check=True)
    base = subprocess.run([*git, "rev-parse", "HEAD"], check=True, capture_output=True, text=True).stdout.strip()
    spec.write_text(spec.read_text() + "\n")  # an edit that adds no line naming anything
    facts = git_facts(work, base)
    assert facts is not None
    res = _check(work, git=facts)
    assert _named(res, "ts-dis-named") == ["pass"] and _named(res, "ts-dis-literal") == ["pass"], res.evidence
    spec.write_text(spec.read_text().replace("THEN standard error is empty", "THEN standard error is empty, as before deploy"))
    res = _check(work, git=git_facts(work, base))
    named = [f for f in res.findings if f.criterion == "ts-dis-named"]
    assert [f.status for f in named] == ["fail"] and named[0].place.endswith(":14"), [f.place for f in named]
    assert _named(res, "ts-dis-literal") == ["maybe"]


def test_the_rule_the_prompt_and_the_judge_say_it() -> None:  # ts-dis-general
    rule = (ROOT / "rules" / "spec.rule.md").read_text()
    assert "## General rules, not cases" in rule
    for phrase in ("never refers to a task", "names no workflow", "not a test", "decision record",
                   "One rule lives in one place", "one case on each side of it", "changes no behaviour changes no spec"):
        assert phrase in rule, phrase
    prompt = (ROOT / "prompts" / "discovery.md").read_text()
    assert "Extract the rule before you write it" in prompt and "General rules, not cases" in prompt
    assert "a case of a behaviour you wrote or of one that exists" in prompt
    assert "Write no behaviour only so that a criterion has something to name" in prompt
    assert "Reread each behaviour you wrote as someone who has never seen the task" in prompt
    assert "owns the mechanism" in (ROOT / "prompts" / "triage.md").read_text()
    judge = (ROOT / "judges" / "discovery.md").read_text()
    assert "General rules, not cases" in judge and "ts-dis-literal" in judge


def test_the_judged_criterion_has_its_seeds() -> None:  # ts-dis-general
    outcome = json.loads((ROOT / "outcome.json").read_text())
    crit = {c["id"]: c for c in outcome["intermediate"]["discovery"]["criteria"]}
    general = crit["ts-dis-general"]
    assert general["severity"] == "blocker" and general["verified_by"] == "judge"
    for seed in general["verifier"]["scale"]["seeds"]:
        case = json.loads((ROOT / "evals" / "calibration" / "discovery" / seed / "case.json").read_text())
        assert case["seed"]["criterion_id"] == "ts-dis-general" and case["case_id"] == seed
    assert crit["ts-dis-named"]["severity"] == "blocker" and crit["ts-dis-literal"]["severity"] == "warning"


def _fixture(src: Path, tmp: Path) -> Path:
    work = tmp / "work"
    _copy(src, work)
    return work
