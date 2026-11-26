"""The decision record's form: the rule's sections and what fills them, read by the discovery check on every record
a run creates or changes (ts-dis-adrform), with an oversized record or a vague `Revisit when` as leads
(ts-dis-adrlead)."""

from __future__ import annotations

import importlib
import json
import time
from pathlib import Path
from typing import Any

from tempergraph.package.loader import load_package
from tempergraph.run.checks import CheckContext, GitFacts, run_check

ROOT = Path(__file__).resolve().parents[1]
SPEC = load_package(ROOT).spec
specfmt = importlib.import_module("tgwf_temperspec.specfmt")
DISCOVERY = ROOT / "evals" / "checks" / "discovery"
RECORD = "docs/adr/config-errors-go-to-standard-error.adr.md"


def _copy(src: Path, dst: Path) -> Path:
    for f in sorted(p for p in src.rglob("*") if p.is_file()):
        target = dst / f.relative_to(src)
        target.parent.mkdir(parents=True, exist_ok=True)
        target.write_bytes(f.read_bytes())
    return dst


def _discovery(work: Path) -> Any:
    ctx = CheckContext(unit="discovery", workdir=work, request={}, artifacts={"discovery": {"handoff": "handoff.md"}},
                       git=GitFacts(), allow=SPEC.allow_commands, out_dir=work.parent / f"{work.name}.out",
                       deadline_at=time.monotonic() + 60)
    return run_check(SPEC.units["discovery"].gate, ctx)[0]


def _named(res: Any, criterion: str) -> list[Any]:
    return [f for f in res.findings if f.criterion == criterion]


def _good() -> str:
    return (DISCOVERY / "must-pass" / "4-new-decision" / RECORD).read_text(encoding="utf-8")


def test_a_record_in_the_rules_form_passes(tmp_path: Path) -> None:  # ts-dis-adrform, ts-dis-adrlead
    res = _discovery(_copy(DISCOVERY / "must-pass" / "4-new-decision", tmp_path / "w"))
    assert res.result == "PASS", res.evidence
    assert [f.status for f in _named(res, "ts-dis-adrform")] == ["pass"]
    assert [f.status for f in _named(res, "ts-dis-adrlead")] == ["pass"]


def test_an_incomplete_record_fails_with_each_gap_named(tmp_path: Path) -> None:  # ts-dis-adrform, ts-dis-adrlead
    res = _discovery(_copy(DISCOVERY / "must-fail" / "decision-record-incomplete", tmp_path / "w"))
    assert res.result == "FAIL"
    said = " | ".join(f.message for f in _named(res, "ts-dis-adrform") if f.status == "fail")
    for part in ("`## Assumptions` is missing", "cites no path, link or id", "constraint C1 names no source",
                 "has no `How it works:` line", "does not answer force C1", "does not answer force F1",
                 "does not say what limits it"):
        assert part in said, part
    assert [f.status for f in _named(res, "ts-dis-adrlead")] == ["maybe"]
    assert "names nothing observable" in _named(res, "ts-dis-adrlead")[0].message


def test_a_run_that_writes_no_decision_record_is_not_measured(tmp_path: Path) -> None:  # ts-dis-adrform
    res = _discovery(_copy(DISCOVERY / "must-pass" / "2-new-spec", tmp_path / "w"))
    assert [f.status for f in _named(res, "ts-dis-adrform")] == ["n_a"]
    assert [f.status for f in _named(res, "ts-dis-adrlead")] == ["n_a"]


def test_the_sections_are_read_in_any_order_and_the_short_forms_pass() -> None:  # ts-dis-adrform
    text = _good()
    parts = text.split("\n## ")
    reordered = "\n## ".join([parts[0], *reversed(parts[1:])])
    assert specfmt.decision_problems(reordered + "\n") == ([], [])
    short = text.split("## Current state")[0] + "## Current state\n\nNothing exists yet.\n\n## Forces" + \
        text.split("## Forces")[1]
    short = short.split("## Risks")[0] + "## Risks\n\nNone known.\n\n## Assumptions\n\nNone.\n\n## Revisit when" + \
        short.split("## Revisit when")[1]
    assert specfmt.decision_problems(short) == ([], [])


def test_one_option_an_empty_section_and_an_assumption_without_its_cost_fail() -> None:  # ts-dis-adrform
    text = _good()
    one = text.split("### Standard output")[0] + "## Decision" + text.split("## Decision\n", 1)[1]
    assert any("describes 1 option" in m for _, m, _ in specfmt.decision_problems(one)[0])
    empty = text.replace("Scripts that read standard output see nothing from a failed run.", "")
    assert any("`## Consequences` is empty" in m for _, m, _ in specfmt.decision_problems(empty)[0])
    costless = text.replace(" If wrong: a caller must change its parsing.", "")
    assert any("assumption A1" in m for _, m, _ in specfmt.decision_problems(costless)[0])


def test_a_record_over_about_ten_kilobytes_is_a_lead() -> None:  # ts-dis-adrlead
    big = _good().replace("## Consequences\n", "## Consequences\n\n" + "More detail. " * 900 + "\n")
    fails, leads = specfmt.decision_problems(big)
    assert fails == [] and any("over about 10 KB" in m for _, m, _ in leads)


def test_the_rule_template_and_check_name_the_same_sections() -> None:  # ts-dis-adrform
    rule = (ROOT / "rules" / "decision.rule.md").read_text(encoding="utf-8")
    template = specfmt.rule_templates("decision", rule)["decision.template.md"]
    assert specfmt.headings_missing(template, specfmt.DECISION_HEADINGS) == []
    assert [h for h in specfmt.sections(template)] == list(specfmt.DECISION_HEADINGS)
    for phrase in ("Source:", "How it works:", "Limited by:", "Noticed by:", "If wrong:", "`None known.`",
                   "`Nothing exists yet.`", "answers every force by its id", "about 10 KB"):
        assert phrase in rule, phrase
    assert "decision.rule.md" in (ROOT / "prompts" / "discovery.md").read_text(encoding="utf-8")
    assert "ts-dis-adrform" in (ROOT / "judges" / "discovery.md").read_text(encoding="utf-8")


def test_the_criteria_have_their_severities() -> None:
    outcome = json.loads((ROOT / "outcome.json").read_text(encoding="utf-8"))["intermediate"]
    crit = {c["id"]: c for u in outcome.values() for c in u["criteria"]}
    assert crit["ts-dis-adrform"]["severity"] == "blocker" and crit["ts-dis-adrlead"]["severity"] == "warning"
    assert all(crit[c]["verified_by"] == "check" for c in ("ts-dis-adrform", "ts-dis-adrlead"))
    spec = (ROOT / "docs" / "specs" / "discovery.spec.md").read_text(encoding="utf-8")
    assert "ts-dis-adrform" in spec and "ts-dis-adrlead" in spec
