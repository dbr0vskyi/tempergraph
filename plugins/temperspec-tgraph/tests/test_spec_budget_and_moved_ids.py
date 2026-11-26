"""Task i57: the spec budget at the discovery gate (ts-dis-budget, ts-dis-over) and the ids a split moves
(ts-spec-moved, ts-spec-parent), with the criteria file, the discovery prompt and the spec rule that state them."""

from __future__ import annotations

import importlib
import json
import re
import time
from pathlib import Path
from typing import Any

import pytest

from tempergraph.package.loader import load_package
from tempergraph.run.checks import CheckContext, GitFacts, run_check
from tempergraph.run.outcome import outcome_unit

ROOT = Path(__file__).resolve().parents[1]
SPEC = load_package(ROOT).spec
checks = importlib.import_module("tgwf_temperspec.checks")
fmt = importlib.import_module("tgwf_temperspec.specfmt")
FIXTURE = ROOT / "evals" / "checks" / "discovery" / "must-pass" / "2-new-spec"
SPEC_PATH = "docs/specs/config-file.spec.md"
BYTES, LINES = 30 * 1024, 400


def _copy(src: Path, dst: Path) -> None:
    for f in sorted(p for p in src.rglob("*") if p.is_file()):
        target = dst / f.relative_to(src)
        target.parent.mkdir(parents=True, exist_ok=True)
        target.write_bytes(f.read_bytes())


def _context(unit: str, work: Path, artifacts: dict[str, dict[str, str]], git: GitFacts | None = None) -> CheckContext:
    ctx = CheckContext(unit=unit, workdir=work, request={}, artifacts=artifacts, values={}, git=git or GitFacts(),
                       allow=SPEC.allow_commands, out_dir=work.parent / f"{work.name}.out",
                       deadline_at=time.monotonic() + 60)
    ctx.settings = {"deliverables": [], "outcome_check": SPEC.outcome.check.ref}  # type: ignore[union-attr]
    return ctx


def _discovery(work: Path, git: GitFacts | None = None) -> Any:
    ctx = _context("discovery", work, {"discovery": {"handoff": "handoff.md"}}, git)
    return run_check(SPEC.units["discovery"].gate, ctx)[0]


def _outcome(work: Path, changed: tuple[str, ...], base: str = "") -> Any:
    ctx = _context("outcome", work, {}, GitFacts(base=base, changed_paths=changed))
    return run_check(outcome_unit(SPEC).gate, ctx)[0]  # type: ignore[union-attr]


def _named(res: Any, criterion: str, status: str | None = None) -> list[Any]:
    return [f for f in res.findings if f.criterion == criterion and (status is None or f.status == status)]


# -- the budget at discovery ----------------------------------------------------------------------------------


def _sized(lines: int, size: int | None = None) -> str:
    """The fixture's spec with filler lines in its Purpose, so it has `lines` lines and, when given, `size` bytes."""
    base = (FIXTURE / SPEC_PATH).read_text(encoding="utf-8")
    count = lines - len(base.splitlines())
    assert count > 0
    each = [20] * count
    if size is not None:
        extra = size - len(base.encode("utf-8")) - sum(each)
        each = [n + extra // count + (1 if i < extra % count else 0) for i, n in enumerate(each)]
    filler = "".join("x" * (n - 1) + "\n" for n in each)
    text = base.replace("\n## Behaviours", filler + "\n## Behaviours", 1)
    assert len(text.splitlines()) == lines and (size is None or len(text.encode("utf-8")) == size)
    return text


def _with_spec(work: Path, text: str) -> Any:
    _copy(FIXTURE, work)
    (work / SPEC_PATH).write_text(text, encoding="utf-8")
    return _discovery(work)


def test_a_spec_at_the_budget_passes_discovery(tmp_path: Path) -> None:  # AC 1, ts-dis-budget, ts-dis-over
    res = _with_spec(tmp_path, _sized(LINES, BYTES))
    assert (tmp_path / SPEC_PATH).stat().st_size == BYTES
    assert res.result == "PASS", res.evidence
    assert [f.status for f in _named(res, "ts-dis-budget")] == ["pass"]
    assert [f.status for f in _named(res, "ts-dis-over")] == ["pass"]


def test_a_spec_one_byte_over_fails_with_one_finding_that_says_to_split(tmp_path: Path) -> None:  # AC 1, ts-dis-over
    res = _with_spec(tmp_path, _sized(300, BYTES + 1))
    assert res.result == "FAIL"
    over = _named(res, "ts-dis-over", "fail")
    assert len(over) == 1 and over[0].place == SPEC_PATH
    assert "30,721 bytes" in over[0].message and "30,720" in over[0].message
    assert "split the spec by capability" in over[0].fix
    assert _named(res, "ts-dis-budget", "pass") == []


def test_a_spec_one_line_over_fails_with_the_line_figure(tmp_path: Path) -> None:  # AC 1, ts-dis-over
    res = _with_spec(tmp_path, _sized(LINES + 1))
    over = _named(res, "ts-dis-over", "fail")
    assert res.result == "FAIL" and len(over) == 1 and over[0].place == SPEC_PATH
    assert "401 lines" in over[0].message and "400" in over[0].message and "bytes" not in over[0].message
    assert "split the spec by capability" in over[0].fix


def test_a_spec_over_both_figures_is_one_finding(tmp_path: Path) -> None:  # AC 1, ts-dis-over
    res = _with_spec(tmp_path, _sized(LINES + 20, BYTES + 500))
    over = _named(res, "ts-dis-over", "fail")
    assert len(over) == 1 and "420 lines" in over[0].message and "31,220 bytes" in over[0].message


def test_bytes_are_counted_from_the_file_not_the_characters(tmp_path: Path) -> None:  # AC 1, ts-dis-over
    base = (FIXTURE / SPEC_PATH).read_text(encoding="utf-8")
    text = base.replace("\n## Behaviours", ("é" * 80 + "\n") * 200 + "\n## Behaviours", 1)
    assert len(text) < BYTES < len(text.encode("utf-8")) and len(text.splitlines()) < LINES
    res = _with_spec(tmp_path, text)
    over = _named(res, "ts-dis-over", "fail")
    assert res.result == "FAIL" and len(over) == 1 and "bytes" in over[0].message


def test_a_spec_in_the_earlier_layout_over_the_budget_fails_too(tmp_path: Path) -> None:  # AC 1, ts-dis-over
    text = "# Config\n\n## 1. Overview\n\n### CFG-B1 One\n\n" + ("y" * 99 + "\n") * 320
    assert len(text.encode("utf-8")) > BYTES and fmt.parse_spec(text).legacy
    res = _with_spec(tmp_path, text)
    over = _named(res, "ts-dis-over", "fail")
    assert res.result == "FAIL" and len(over) == 1 and over[0].place == SPEC_PATH and "bytes" in over[0].message


def test_the_size_is_not_reported_under_the_form_criterion(tmp_path: Path) -> None:  # AC 1, ts-dis-over
    res = _with_spec(tmp_path, _sized(LINES + 5, BYTES + 100))
    assert _named(res, "ts-dis-form", "fail") == [] and _named(res, "ts-dis-form", "pass")


def test_the_outcome_cap_still_counts_lines_only(tmp_path: Path) -> None:  # AC 1, ts-dis-budget
    _copy(FIXTURE, tmp_path)
    (tmp_path / SPEC_PATH).write_text(_sized(300, BYTES + 1), encoding="utf-8")
    res = _outcome(tmp_path, (SPEC_PATH,))
    assert [f.status for f in _named(res, "ts-spec-cap")] == ["pass"]
    assert _named(res, "ts-dis-over") == [] and _named(res, "ts-dis-budget") == []
    (tmp_path / SPEC_PATH).write_text(_sized(LINES + 1), encoding="utf-8")
    assert [f.status for f in _named(_outcome(tmp_path, (SPEC_PATH,)), "ts-spec-cap")] == ["fail"]


def test_a_run_that_edited_no_spec_has_no_budget_to_measure(tmp_path: Path) -> None:  # AC 1, ts-dis-budget
    _copy(FIXTURE, tmp_path)
    (tmp_path / SPEC_PATH).unlink()
    (tmp_path / "handoff.md").write_text("# Hand-off: T\n\n## Problem\n\nx\n\n## Gaps closed\n\n- none\n\n"
                                         "## Changed documents\n\n- none\n\n## Decisions\n\n- none\n\n"
                                         "## Open questions\n\n- None\n", encoding="utf-8")
    res = _discovery(tmp_path)
    assert [f.status for f in _named(res, "ts-dis-budget")] == ["n_a"]


# -- ids moved by a split -------------------------------------------------------------------------------------

OLD, NEW = "docs/specs/schema.spec.md", "docs/specs/schema-types.spec.md"
OTHER, DUP = "docs/specs/other.spec.md", "docs/specs/dup.spec.md"


def _spec(title: str, behaviours: dict[str, str], criteria: list[str]) -> str:
    body = "".join(f"### {bid} {name}\n\nWHEN a file is read THE reader SHALL answer {bid}.\n\n"
                   "- GIVEN a file WHEN it is read THEN it is answered\n\n" for bid, name in behaviours.items())
    return (f"# {title}\n\n## Purpose\n\nWhat {title} does.\n\n## Behaviours\n\n{body}## Acceptance criteria\n\n"
            + "".join(f"- {c}\n" for c in criteria))


# Modelled on the split of run r3-t5-1: SCH-B15 moved from the old spec to a split-off spec with its own prefix.
OLD_TEXT = _spec("Schema", {"SCH-B1": "Names"}, ["SCH-AC1 (SCH-B1, SCH-B15): Names and the moved type check are read"])
NEW_TEXT = _spec("Schema types", {"SCT-B1": "Types", "SCH-B15": "Moved type check"},
                 ["SCT-AC1 (SCT-B1): A type is read", "SCT-AC2 (SCH-B15, SCH-B1): The moved check and the name are read"])
OTHER_TEXT = _spec("Other", {"OTH-B1": "Other"}, ["OTH-AC1 (OTH-B1): Other is read"])
DUP_TEXT = _spec("Duplicate", {"DUP-B1": "Dup", "SCH-B15": "Defined again"}, ["DUP-AC1 (DUP-B1, SCH-B15): Dup is read"])


def _repo(work: Path, files: dict[str, str] | None = None) -> Path:
    for name, text in {OLD: OLD_TEXT, NEW: NEW_TEXT, **(files or {})}.items():
        (work / name).parent.mkdir(parents=True, exist_ok=True)
        (work / name).write_text(text, encoding="utf-8")
    return work


def _handoff(work: Path, changed: tuple[str, ...]) -> None:
    listed = "".join(f"- `{p}`: edited\n" for p in changed)
    (work / "handoff.md").write_text(
        f"# Hand-off: T\n\n## Problem\n\nx\n\n## Gaps closed\n\n- G1: `{changed[0]}`\n\n## Changed documents\n\n{listed}\n"
        f"## Decisions\n\n- none\n\n## Open questions\n\n- None\n\n## Reading list\n\n- `{changed[0]}` (SCH-B1): why\n",
        encoding="utf-8")


def _form(work: Path, changed: tuple[str, ...], base: str = "") -> dict[str, list[str]]:
    """The messages of failed form findings and of failed link findings, by gate."""
    _handoff(work, changed)
    out = _outcome(work, changed, base)
    dis = _discovery(work, GitFacts(base=base, changed_paths=changed))
    return {"outcome": [f.message for f in _named(out, "ts-spec-form", "fail")],
            "outcome-links": [f.message for f in _named(out, "ts-spec-links", "fail")],
            "discovery": [f.message for f in _named(dis, "ts-dis-form", "fail")],
            "discovery-links": [f.message for f in _named(dis, "ts-dis-links", "fail")]}


def test_a_criterion_left_by_a_split_may_name_the_moved_id(tmp_path: Path) -> None:  # AC 2, ts-spec-moved, ts-spec-parent
    got = _form(_repo(tmp_path), (OLD, NEW))
    assert got == {"outcome": [], "outcome-links": [], "discovery": [], "discovery-links": []}


def test_a_criterion_of_the_split_off_spec_may_name_an_id_of_its_parent(tmp_path: Path) -> None:  # AC 2, ts-spec-parent
    assert "SCH-B1" in NEW_TEXT and "SCH-B1 Names" not in NEW_TEXT  # SCT-AC2 names an id only the old spec defines
    got = _form(_repo(tmp_path), (NEW,))
    assert got == {"outcome": [], "outcome-links": [], "discovery": [], "discovery-links": []}


@pytest.mark.parametrize("changed", [(OLD, NEW), (OLD,), (NEW,)], ids=["both", "old only", "new only"])
@pytest.mark.parametrize("base", ["", "0" * 40], ids=["no base", "unknown base"])
def test_the_reading_of_a_moved_id_does_not_depend_on_the_run_or_its_history(
        changed: tuple[str, ...], base: str, tmp_path: Path) -> None:  # AC 2, ts-spec-moved, ts-spec-parent
    got = _form(_repo(tmp_path), changed, base)
    assert all(not messages for messages in got.values()), got


def test_the_parser_reads_a_moved_id_only_when_it_is_given_the_definitions(tmp_path: Path) -> None:  # AC 2, ts-spec-moved
    plain = fmt.parse_spec(OLD_TEXT)
    assert [p[1] for p in plain.problems] == ["SCH-AC1 names SCH-B15, which this spec does not define"]
    given = fmt.parse_spec(OLD_TEXT, {"SCH-B15": [NEW]})
    assert given.problems == []
    assert fmt.parse_spec(OLD_TEXT, {}).problems == plain.problems


@pytest.mark.parametrize("case", ["other prefix", "two definitions", "no definition", "no behaviour"])
def test_the_boundaries_of_a_moved_id_stay_findings(case: str, tmp_path: Path) -> None:  # AC 2, ts-spec-moved, ts-spec-parent
    files: dict[str, str] = {}
    old = OLD_TEXT
    if case == "other prefix":
        files[OTHER] = OTHER_TEXT
        old = old.replace("SCH-B1, SCH-B15", "SCH-B1, OTH-B1")
        expect = "SCH-AC1 names OTH-B1, which this spec does not define"
    elif case == "two definitions":
        files[DUP] = DUP_TEXT
        expect = "SCH-AC1 names SCH-B15, which this spec does not define"
    elif case == "no definition":
        old = old.replace("SCH-B15", "SCH-B99")
        expect = "SCH-AC1 names SCH-B99, which this spec does not define"
    else:
        old = old.replace("(SCH-B1, SCH-B15)", "()")
        expect = "SCH-AC1 names no behaviour"
    files[OLD] = old
    got = _form(_repo(tmp_path, files), (OLD, NEW))
    assert any(expect in m for m in got["outcome"]) and any(expect in m for m in got["discovery"]), got


def test_the_split_off_spec_cannot_name_an_id_of_a_prefix_it_does_not_define(tmp_path: Path) -> None:  # AC 2, ts-spec-parent
    new = NEW_TEXT.replace("(SCH-B15, SCH-B1)", "(SCH-B15, OTH-B1)")
    got = _form(_repo(tmp_path, {OTHER: OTHER_TEXT, NEW: new}), (NEW,))
    assert any("SCT-AC2 names OTH-B1, which this spec does not define" in m for m in got["outcome"])


# -- the criteria file, the prompt and the rule ---------------------------------------------------------------


def _rows(path: str) -> dict[str, str]:
    text = (ROOT / "docs" / "specs" / path).read_text(encoding="utf-8")
    return {m.group(1): m.group(2) for line in text.splitlines() if (m := re.match(r"^- \[[ xX]\] (ts-\S+) (.+)$", line))}


def _criteria() -> dict[str, tuple[str, dict[str, Any]]]:
    o = json.loads((ROOT / "outcome.json").read_text(encoding="utf-8"))
    out = {c["id"]: ("outcome", c) for c in o["final"]}
    for unit, io in o["intermediate"].items():
        out.update({c["id"]: (unit, c) for c in io["criteria"]})
    return out


def test_the_criteria_file_has_the_revision_entries_for_the_change() -> None:  # AC 1, AC 2, AC 5, ts-code-ran, ts-dis-budget, ts-spec-moved
    o = json.loads((ROOT / "outcome.json").read_text(encoding="utf-8"))
    for issue in ("issue 57", "issue 69", "issue 72"):
        entry = next(r for r in o["revisions"] if issue in r.get("note", ""))
        assert entry["revision"] >= (13 if issue == "issue 72" else 8), issue
    assert o["revision"] >= 13 and o["revision"] == o["revisions"][-1]["revision"]
    assert any("30,720" in a and "ts-spec-cap" in a for a in o["assumptions"])


@pytest.mark.parametrize("cid, unit, verifier", [
    ("ts-set-ruleread", "setup", "setup_check"), ("ts-tri-ruleread", "triage", "triage_check"),
    ("ts-dsh-ruleread", "discovery_short", "discovery_short_check"),
    ("ts-dis-ruleread", "discovery", "discovery_check"), ("ts-plan-ruleread", "plan", "plan_check"),
    ("ts-exp-ruleread", "expand", "expand_check"), ("ts-code-ruleread", "code", "code_check"),
])
def test_each_rule_file_criterion_is_a_blocker_checked_by_its_gate_and_names_its_rule_files(
        cid: str, unit: str, verifier: str) -> None:  # AC 1, SRC-B1
    where, row = _criteria()[cid]
    assert where == unit and row["severity"] == "blocker" and row["verified_by"] == "check"
    assert row["verifier"]["check"] == f"tgwf_temperspec.checks:{verifier}"
    names = checks._rule_names(unit)
    assert names and all(n in row["text"] for n in names)


def test_the_outcome_record_has_the_revision_entry_of_issue_150() -> None:  # AC 6
    o = json.loads((ROOT / "outcome.json").read_text(encoding="utf-8"))
    entry = next(r for r in o["revisions"] if "issue 150" in r.get("note", ""))
    assert entry["origin"] == "authored" and entry["revision"] >= 23
    assert o["revision"] == o["revisions"][-1]["revision"] >= entry["revision"]


def test_the_phase_scope_criterion_is_graded_on_the_paths_changed_since_the_phase_step_was_entered() -> None:
    # AC 3, PHC-AC18 (PHC-B18)
    o = json.loads((ROOT / "outcome.json").read_text(encoding="utf-8"))
    entry = next(r for r in o["revisions"] if "issue 148" in r.get("note", ""))
    assert entry["revision"] <= o["revision"] == o["revisions"][-1]["revision"]
    where, row = _criteria()["ts-phs-scope"]
    assert where == "phase" and "since the phase step was entered" in row["text"]
    assert row["text"] == _rows("phase.spec.md")["ts-phs-scope"]  # the docs check compares the whole line
    assert "earlier steps" in row["check_method"] and "since the phase step was entered" in row["check_method"]
    scale = row["verifier"]["scale"]
    assert all("first list" in scale[k] for k in ("met", "partial", "unmet"))
    # the criterion of the expand step keeps its words
    _, opened = _criteria()["ts-exp-opened"]
    assert all(w in opened["text"] for w in ("task row", "file", "opened"))


@pytest.mark.parametrize("cid, unit, verifier, words", [
    ("ts-exp-opened", "expand", "expand_check", ("task row", "file", "opened")),
    ("ts-code-order", "code", "code_check", ("phase", "source", "test files", "first written")),
])
def test_the_expand_and_test_first_criteria_are_blockers_checked_by_their_gate(
        cid: str, unit: str, verifier: str, words: tuple[str, ...]) -> None:  # AC 3, AC 4, SRC-B5, SRC-B6
    where, row = _criteria()[cid]
    assert where == unit and row["severity"] == "blocker" and row["verified_by"] == "check"
    assert row["verifier"]["check"] == f"tgwf_temperspec.checks:{verifier}"
    assert all(w in row["text"] for w in words)
    o = json.loads((ROOT / "outcome.json").read_text(encoding="utf-8"))
    note = next(r for r in o["revisions"] if "issue 72" in r.get("note", ""))["note"]
    assert "ts-exp-opened" in note and "ts-code-order" in note


@pytest.mark.parametrize("cid", ["ts-code-once", "ts-code-preview", "ts-code-previewed", "ts-code-session",
                                 "ts-code-rerun", "ts-code-ran"])
def test_each_code_criterion_of_the_run_is_a_warning_checked_by_the_gate_with_the_text_of_its_spec_row(
        cid: str) -> None:  # AC 1, AC 2, AC 3, AC 4, AC 5, ts-code-once, ts-code-preview, ts-code-ran
    where, row = _criteria()[cid]
    assert where == "code" and row["text"] == _rows("code.spec.md")[cid]
    assert row["severity"] == "warning" and row["verified_by"] == "check"
    assert row["verifier"]["check"] == "tgwf_temperspec.checks:code_check"


@pytest.mark.parametrize("cid, unit, spec, verifier", [
    ("ts-dis-budget", "discovery", "discovery.spec.md", "discovery_check"),
    ("ts-dis-over", "discovery", "discovery.spec.md", "discovery_check"),
    ("ts-spec-moved", "outcome", "overview.spec.md", "outcome_check"),
    ("ts-spec-parent", "outcome", "overview.spec.md", "outcome_check"),
    ("ts-dis-form", "discovery", "discovery.spec.md", "discovery_check"),
    ("ts-spec-cap", "outcome", "overview.spec.md", "outcome_check"),
])
def test_each_new_criterion_is_a_blocker_checked_by_its_gate_with_the_text_of_its_spec_row(
        cid: str, unit: str, spec: str, verifier: str) -> None:  # AC 1, AC 2, ts-dis-budget, ts-dis-over, ts-spec-moved, ts-spec-parent
    where, row = _criteria()[cid]
    assert where == unit and row["text"] == _rows(spec)[cid]
    assert row["severity"] == "blocker" and row["verified_by"] == "check"
    assert row["verifier"]["check"] == f"tgwf_temperspec.checks:{verifier}"


def test_the_new_criteria_serve_the_outcome_criteria_they_belong_to() -> None:  # AC 1, AC 2, ts-dis-budget, ts-spec-moved
    rows = _criteria()
    assert {"ts-spec-cap"} <= set(rows["ts-dis-budget"][1]["serves"]) and {"ts-spec-cap"} <= set(rows["ts-dis-over"][1]["serves"])
    assert "ts-spec-links" in rows["ts-spec-moved"][1]["serves"] and "ts-spec-links" in rows["ts-spec-parent"][1]["serves"]
    assert "size" in rows["ts-dis-form"][1]["check_method"]


def test_the_spec_rule_states_the_budget_and_the_moved_ids() -> None:  # AC 1, AC 2, ts-dis-budget, ts-spec-moved, ts-spec-parent
    rule = " ".join((ROOT / "rules" / "spec.rule.md").read_text(encoding="utf-8").split())
    assert "30,720 bytes" in rule and f"at most {fmt.SPEC_CAP_LINES} lines" in rule
    assert "keeps its id" in rule and "split from" in rule
    assert fmt.SPEC_CAP_BYTES == BYTES


def test_the_discovery_prompt_states_the_budget_and_the_moved_ids() -> None:  # AC 1, AC 2, ts-dis-budget, ts-spec-moved
    prompt = " ".join((ROOT / "prompts" / "discovery.md").read_text(encoding="utf-8").split())
    assert "400 lines" in prompt and "30,720 bytes" in prompt and "split by capability" in prompt
    assert "keeps its id" in prompt
    assert all(f.status == "pass" for f in checks._prompt_says("ts-dis-narrow"))
