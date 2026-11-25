"""Spec extraction and spec craft: the extraction rule, the setup note's evidence (ts-set-evidence), the setup
step's general-rules and wording checks (ts-set-named, ts-set-literal, ts-set-wording), a new spec named for its
capability (ts-dis-specname), the wording leads (ts-dis-wording), the `existing behaviour` gap and the capability
list (CAPL)."""

from __future__ import annotations

import importlib
import json
import subprocess
import time
from pathlib import Path
from types import SimpleNamespace
from typing import Any

from tempergraph.package.loader import load_package
from tempergraph.run.checks import CheckContext, GitFacts, run_check

ROOT = Path(__file__).resolve().parents[1]
SPEC = load_package(ROOT).spec
routing = importlib.import_module("tgwf_temperspec.routing")
specfmt = importlib.import_module("tgwf_temperspec.specfmt")
CHECKS = ROOT / "evals" / "checks"
SPEC_FILE = "docs/specs/config-file.spec.md"


def _copy(src: Path, dst: Path) -> Path:
    for f in sorted(p for p in src.rglob("*") if p.is_file()):
        target = dst / f.relative_to(src)
        target.parent.mkdir(parents=True, exist_ok=True)
        target.write_bytes(f.read_bytes())
    return dst


def _check(unit: str, work: Path, artifacts: dict[str, dict[str, str]], task_id: str = "") -> Any:
    ctx = CheckContext(unit=unit, workdir=work, request={"task_id": task_id} if task_id else {},
                       artifacts=artifacts, git=GitFacts(), allow=SPEC.allow_commands,
                       out_dir=work.parent / f"{work.name}.out", deadline_at=time.monotonic() + 60)
    return run_check(SPEC.units[unit].gate, ctx)[0]


def _setup(work: Path) -> Any:
    return _check("setup", work, {"setup": {"setup_note": "setup_note.md", "overview": "overview.md"}})


def _discovery(work: Path, task_id: str = "") -> Any:
    return _check("discovery", work, {"discovery": {"handoff": "handoff.md"}}, task_id)


def _named(res: Any, criterion: str) -> list[str]:
    return [f.status for f in res.findings if f.criterion == criterion]


# -- setup ----------------------------------------------------------------------------------------


def test_every_behaviour_with_its_evidence_passes(tmp_path: Path) -> None:  # ts-set-evidence
    res = _setup(_copy(CHECKS / "setup" / "must-pass" / "2-components", tmp_path / "w"))
    assert res.result == "PASS" and _named(res, "ts-set-evidence") == ["pass"], res.evidence


def test_a_behaviour_without_a_row_or_with_lines_outside_its_file_fails(tmp_path: Path) -> None:  # ts-set-evidence
    res = _setup(_copy(CHECKS / "setup" / "must-fail" / "behaviour-without-evidence", tmp_path / "w"))
    found = [f for f in res.findings if f.criterion == "ts-set-evidence"]
    assert res.result == "FAIL" and [f.status for f in found] == ["fail", "fail"], res.evidence
    assert any("CFG-B2" in f.message and "no Evidence row" in f.message for f in found)
    assert any("line 80" in f.message for f in found)


def test_a_stated_rule_and_a_tested_rule_without_its_test_fail(tmp_path: Path) -> None:  # ts-set-evidence
    work = _copy(CHECKS / "setup" / "must-pass" / "2-components", tmp_path / "w")
    note = work / "setup_note.md"
    text = note.read_text().replace("| CFG-B2 | read |", "| CFG-B2 | stated |")
    note.write_text(text.replace("`tests/config_cases.py::test_missing_file`", "`tests/test_gone.py`"))
    messages = [f.message for f in _setup(work).findings if f.criterion == "ts-set-evidence"]
    assert any("`stated`" in m for m in messages) and any("names no test file" in m for m in messages), messages


def test_setup_specs_get_the_general_rules_and_wording_checks(tmp_path: Path) -> None:
    # ts-set-named, ts-set-literal, ts-set-wording
    work = _copy(CHECKS / "setup" / "must-pass" / "2-components", tmp_path / "w")
    folder = work / "plugins" / "deploy-tgraph"
    folder.mkdir(parents=True)
    (folder / "tempergraph.json").write_text(json.dumps({"schema_version": 1, "name": "deploy"}))
    spec = work / SPEC_FILE
    text = spec.read_text().replace("names the missing file.", "names the missing file, as deploy expects.")
    text = text.replace("THEN standard error is empty", "THEN standard error is empty, which is no longer TODO")
    spec.write_text(text)
    res = _setup(work)
    assert _named(res, "ts-set-named") == ["fail"]
    assert _named(res, "ts-set-literal") == ["maybe"] and _named(res, "ts-set-wording") == ["maybe"], res.evidence


def test_the_setup_note_has_evidence_and_anomalies_sections() -> None:  # ts-set-evidence
    assert specfmt.SETUP_HEADINGS == ("Components", "Commands", "Evidence", "Anomalies", "Not covered")
    rule = (ROOT / "rules" / "task-notes.rule.md").read_text()
    assert "## Evidence" in rule and "## Anomalies" in rule and "partly covered" in rule


# -- discovery ------------------------------------------------------------------------------------


def test_a_new_spec_named_for_the_task_fails(tmp_path: Path) -> None:  # ts-dis-specname
    res = _discovery(_copy(CHECKS / "discovery" / "must-fail" / "spec-named-for-the-task", tmp_path / "w"))
    assert res.result == "FAIL" and _named(res, "ts-dis-specname") == ["fail"], res.evidence


def test_a_spec_named_with_the_task_id_or_an_issue_in_its_title_fails(tmp_path: Path) -> None:  # ts-dis-specname
    work = _copy(CHECKS / "discovery" / "must-pass" / "2-new-spec", tmp_path / "w")
    spec = work / SPEC_FILE
    spec.write_text(spec.read_text().replace("# Config file", "# Config file for issue #12", 1))
    assert _named(_discovery(work), "ts-dis-specname") == ["fail"]
    spec.write_text(spec.read_text().replace("# Config file for issue #12", "# Config file", 1))
    moved = work / "docs" / "specs" / "std-12-config.spec.md"
    spec.rename(moved)
    (work / "handoff.md").write_text((work / "handoff.md").read_text().replace("config-file.spec.md", moved.name))
    assert _named(_discovery(work, task_id="STD-12"), "ts-dis-specname") == ["fail"]


def test_a_spec_named_for_its_capability_passes(tmp_path: Path) -> None:  # ts-dis-specname
    res = _discovery(_copy(CHECKS / "discovery" / "must-pass" / "2-new-spec", tmp_path / "w"), task_id="STANDIN-1")
    assert _named(res, "ts-dis-specname") == ["pass"] and _named(res, "ts-dis-wording") == ["pass"], res.evidence


def test_an_edited_spec_that_existed_at_the_base_is_not_renamed(tmp_path: Path) -> None:  # ts-dis-specname
    work = _copy(CHECKS / "discovery" / "must-fail" / "spec-named-for-the-task", tmp_path / "w")
    git = ["git", "-C", str(work), "-c", "user.name=t", "-c", "user.email=t@t", "-c", "commit.gpgsign=false"]
    subprocess.run([*git, "init", "-q"], check=True)
    subprocess.run([*git, "add", "-A"], check=True)
    subprocess.run([*git, "commit", "-qm", "base"], check=True)
    base = subprocess.run([*git, "rev-parse", "HEAD"], check=True, capture_output=True, text=True).stdout.strip()
    spec = work / "docs" / "specs" / "fix-missing-config.spec.md"
    spec.write_text(spec.read_text() + "\n")
    from tempergraph.run.checks import git_facts
    ctx = CheckContext(unit="discovery", workdir=work, request={}, artifacts={"discovery": {"handoff": "handoff.md"}},
                       git=git_facts(work, base) or GitFacts(), allow=SPEC.allow_commands,
                       out_dir=work.parent / "out", deadline_at=time.monotonic() + 60)
    res = run_check(SPEC.units["discovery"].gate, ctx)[0]
    assert _named(res, "ts-dis-specname") == ["n_a"], res.evidence


def test_long_vague_or_unfinished_behaviours_are_leads(tmp_path: Path) -> None:  # ts-dis-wording
    work = _copy(CHECKS / "discovery" / "must-pass" / "2-new-spec", tmp_path / "w")
    spec = work / SPEC_FILE
    long_result = "print one line to standard error that names the missing file" + ", and the folder" * 40 + "."
    text = spec.read_text().replace(
        "print one line to standard error that names the missing file.", long_result)
    text = text.replace("WHEN the tool starts and `tool.toml` does not exist THE tool SHALL exit with code 2.",
                        "WHEN the tool starts and `tool.toml` does not exist THE tool SHALL exit quickly with code 2.")
    text = text.replace("THEN standard error is empty", "THEN standard error is empty ???")
    spec.write_text(text)
    res = _discovery(work)
    leads = [f for f in res.findings if f.criterion == "ts-dis-wording"]
    assert res.result == "MAYBE" and [f.status for f in leads] == ["maybe"] * 3, res.evidence
    said = " ".join(f.message for f in leads)
    assert "over 500" in said and "`quickly`" in said and "`???`" in said


def test_the_rules_and_prompts_say_it() -> None:  # ts-dis-wording, ts-dis-specname, ts-dis-general
    spec_rule = (ROOT / "rules" / "spec.rule.md").read_text()
    assert "## Naming a spec" in spec_rule and "at most 500 characters" in spec_rule and "`TBD`" in spec_rule
    assert "does not own" in spec_rule
    extraction = (ROOT / "rules" / "extraction.rule.md").read_text()
    for phrase in ("`tested`", "`read`", "`stated`", "## Invariants", "## Suspected bugs", "## Budget"):
        assert phrase in extraction, phrase
    for unit in ("setup", "discovery"):
        assert "extraction.rule.md" in (ROOT / "prompts" / f"{unit}.md").read_text(), unit
    assert "candidate rules" in (ROOT / "prompts" / "read_component.md").read_text()
    triage = (ROOT / "prompts" / "triage.md").read_text()
    assert "`existing behaviour`" in triage and ".tempergraph/capabilities.md" in triage
    discovery = (ROOT / "prompts" / "discovery.md").read_text()
    assert "`existing behaviour`" in discovery and "## Inferred behaviours" in discovery
    judge = (ROOT / "judges" / "discovery.md").read_text()
    assert "read two ways" in judge and "Inferred behaviours" in judge and "ts-dis-wording" in judge
    assert (ROOT / "skills" / "extract" / "SKILL.md").is_file()


def test_the_criteria_have_their_severities() -> None:
    outcome = json.loads((ROOT / "outcome.json").read_text())["intermediate"]
    crit = {c["id"]: c for u in outcome.values() for c in u["criteria"]}
    for cid, severity in (("ts-dis-wording", "warning"), ("ts-dis-specname", "blocker"), ("ts-set-named", "blocker"),
                          ("ts-set-literal", "warning"), ("ts-set-wording", "warning"),
                          ("ts-set-evidence", "blocker")):
        assert crit[cid]["severity"] == severity and crit[cid]["verified_by"] == "check", cid


# -- the capability list --------------------------------------------------------------------------


def _spec(title: str, prefix: str) -> str:
    return (f"# {title}\n\n## Purpose\n\nWhat {title} does. More words here.\n\n## Behaviours\n\n"
            f"### {prefix}-B1 One rule\n\nWHEN a thing happens THE {title} SHALL answer.\n\n"
            f"- GIVEN a state WHEN a thing happens THEN it answers\n\n## Acceptance criteria\n\n"
            f"- {prefix}-AC1 ({prefix}-B1): It answers\n")


def test_prepare_lists_every_spec_without_its_behaviour_text(tmp_path: Path) -> None:  # CAPL-AC1, CAPL-AC2
    for path, title, prefix in (("docs/specs/b.spec.md", "Beta", "BB"), ("docs/specs/a.spec.md", "Alpha", "AA"),
                                ("evals/docs/specs/c.spec.md", "Gamma", "CC")):
        (tmp_path / path).parent.mkdir(parents=True, exist_ok=True)
        (tmp_path / path).write_text(_spec(title, prefix))
    routing.write_inventory(tmp_path)
    text = (tmp_path / routing.CAPABILITIES).read_text()
    assert text.index("`docs/specs/a.spec.md`: Alpha") < text.index("`docs/specs/b.spec.md`: Beta")
    assert "Gamma" not in text
    assert "What Alpha does." in text and "More words" not in text
    assert "- AA-B1 One rule" in text and "SHALL answer" not in text and "GIVEN" not in text


def test_the_list_is_not_committed(tmp_path: Path) -> None:  # CAPL-AC3
    (tmp_path / "docs" / "specs").mkdir(parents=True)
    (tmp_path / "docs" / "specs" / "a.spec.md").write_text(_spec("Alpha", "AA"))
    git = ["git", "-C", str(tmp_path), "-c", "user.name=t", "-c", "user.email=t@t", "-c", "commit.gpgsign=false"]
    subprocess.run([*git, "init", "-q"], check=True)
    subprocess.run([*git, "config", "user.email", "t@t"], check=True)
    subprocess.run([*git, "config", "user.name", "t"], check=True)
    routing.write_inventory(tmp_path)
    routing.commit_step(SimpleNamespace(workdir=str(tmp_path), request={"task_id": "T-1"}, unit="prepare"))
    files = subprocess.run([*git, "ls-files"], check=True, capture_output=True, text=True).stdout.split()
    assert files == ["docs/specs/a.spec.md"] and (tmp_path / routing.CAPABILITIES).is_file()


def test_a_setup_spec_that_names_a_workflow_fails(tmp_path: Path) -> None:  # ts-set-named
    res = _setup(_copy(CHECKS / "setup" / "must-fail" / "names-a-workflow", tmp_path / "w"))
    assert res.result == "FAIL" and "fail" in _named(res, "ts-set-named"), res.evidence
