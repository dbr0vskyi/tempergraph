"""The package's own tests: the final checks on their fixtures, the judge seeds against the gate checks, the
rule files against the format module, and the scripts and the last stage on a scratch repository."""

from __future__ import annotations

import importlib
import json
import re
import subprocess
import time
from pathlib import Path
from types import SimpleNamespace
from typing import Any

import pytest

from tempergraph.package.loader import load_package
from tempergraph.run.checks import CheckContext, GitFacts, git_facts, run_check
from tempergraph.run.commands import CommandRefusal, CommandRun, resolve_command
from tempergraph.run.outcome import outcome_unit

ROOT = Path(__file__).resolve().parents[1]
SPEC = load_package(ROOT).spec
checks = importlib.import_module("tgwf_temperspec.checks")
routing = importlib.import_module("tgwf_temperspec.routing")
summary = importlib.import_module("tgwf_temperspec.summary")
fmt = importlib.import_module("tgwf_temperspec.specfmt")
OWNER = {key: unit for unit in SPEC.order for key in (SPEC.units[unit].step.produces if SPEC.units[unit].step else {})}


def _copy(src: Path, dst: Path) -> list[Path]:
    out = []
    for f in sorted(p for p in src.rglob("*") if p.is_file()):
        target = dst / f.relative_to(src)
        target.parent.mkdir(parents=True, exist_ok=True)
        target.write_bytes(f.read_bytes())
        out.append(target)
    return out


def _context(unit: str, work: Path, artifacts: dict[str, dict[str, str]], values: dict[str, Any] | None = None,
             git: GitFacts | None = None) -> CheckContext:
    return CheckContext(unit=unit, workdir=work, request={}, artifacts=artifacts, values=values or {},
                        git=git or GitFacts(), allow=SPEC.allow_commands, out_dir=work.parent / f"{work.name}.out",
                        deadline_at=time.monotonic() + 60)


OUTCOME = sorted(p for p in (ROOT / "evals" / "checks" / "outcome").glob("must-*/*") if p.is_dir())


@pytest.mark.parametrize("fixture", OUTCOME, ids=lambda p: f"{p.parent.name}/{p.name}")
def test_outcome_check_on_its_fixtures(fixture: Path, tmp_path: Path) -> None:
    files = _copy(fixture, tmp_path)
    artifacts: dict[str, dict[str, str]] = {}
    for f in files:
        if f.stem in OWNER:
            artifacts.setdefault(OWNER[f.stem], {})[f.stem] = f.relative_to(tmp_path).as_posix()
    values_file = tmp_path / "values.json"
    values = {"triage": json.loads(values_file.read_text())} if values_file.exists() else {}
    gate = outcome_unit(SPEC).gate  # type: ignore[union-attr]
    ctx = _context("outcome", tmp_path, artifacts, values)
    ctx.settings = {"deliverables": [], "outcome_check": SPEC.outcome.check.ref}  # type: ignore[union-attr]
    res, _ = run_check(gate, ctx)
    want = "PASS" if fixture.parent.name == "must-pass" else "FAIL"
    assert res.result == want, res.evidence
    final = {c.id for c in SPEC.outcome.final}  # type: ignore[union-attr]
    assert {f.criterion for f in res.findings} <= final and {f.criterion for f in res.findings}


SEEDS = sorted(p for p in (ROOT / "evals" / "calibration").glob("*/met-*") if p.parent.name in
               ("setup", "triage", "discovery_short", "discovery", "plan", "expand"))


@pytest.mark.parametrize("seed", SEEDS, ids=lambda p: f"{p.parent.name}/{p.name}")
def test_a_met_seed_passes_the_check_of_its_gate(seed: Path, tmp_path: Path) -> None:
    """A seed the judge is to grade MET must first be something the gate's check lets through."""
    gate = seed.parent.name
    _copy(seed / "fixture" / "workspace", tmp_path)
    artifacts: dict[str, dict[str, str]] = {}
    values: dict[str, dict[str, str]] = {}
    for name in ("references.json", "subject.json"):
        for key, value in json.loads((seed / "fixture" / name).read_text()).items():
            if (tmp_path / value).is_file():
                artifacts.setdefault(OWNER.get(key, gate), {})[key] = value
            else:
                values.setdefault(OWNER.get(key, gate), {})[key] = value
    if gate not in ("setup", "triage"):
        artifacts.setdefault("discovery", {})["handoff"] = "docs/tasks/TASK-7.handoff.md"
        artifacts.setdefault("triage", {}).setdefault("triage_note", "docs/tasks/TASK-7.triage.md")
    res, _ = run_check(SPEC.units[gate].gate, _context(gate, tmp_path, artifacts, values))
    assert res.result == "PASS", res.evidence


def test_every_named_seed_has_a_case() -> None:
    o = json.loads((ROOT / "outcome.json").read_text())
    rows = [("outcome", c) for c in o["final"]] + [(u, c) for u, io in o["intermediate"].items()
                                                   for c in io["criteria"]]
    for gate, c in rows:
        for seed in ((c.get("verifier") or {}).get("scale") or {}).get("seeds") or []:
            case = json.loads((ROOT / "evals" / "calibration" / gate / seed / "case.json").read_text())
            assert case["seed"]["criterion_id"] == c["id"]
            assert case["seed"]["expected"] == ("MET" if seed.startswith("met-") else "UNMET")


# -- the rule files say what the format module reads ----------------------------------------------------


def _rule(name: str) -> str:
    return (ROOT / "rules" / f"{name}.rule.md").read_text(encoding="utf-8")


def _example(rule: str, opening: str) -> str:
    """The fenced example of a rule file that starts with `opening`."""
    for block in rule.split("```markdown\n")[1:]:
        body = block.split("\n```", 1)[0]
        if body.startswith(opening):
            return body + "\n"
    raise AssertionError(f"no example starts with {opening!r}")


def test_the_spec_rule_example_passes_the_spec_parser() -> None:
    rule = _rule("spec")
    spec = fmt.parse_spec(_example(rule, "# <Capability name>"))
    assert spec.problems == [] and set(spec.behaviours) == {"SES-B1"} and set(spec.criteria) == {"SES-AC1"}
    assert f"at most {fmt.SPEC_CAP_LINES} lines" in rule
    for heading in fmt.SPEC_HEADINGS:
        assert f"## {heading}" in rule


def test_the_plan_rule_example_and_limits_match_the_parser() -> None:
    rule = _rule("plan")
    plan = fmt.parse_plan(_example(rule, "---\ntask:"))
    assert plan.missing == [] and plan.complexity == "simple" and plan.requirement_criteria == {1}
    assert [r.id for r in plan.rows] == ["1.1", "1.2"] and plan.commands == ["pytest tests/test_session.py"]
    assert fmt.row_problems(plan) == ([], []) and fmt.simple_overruns(plan) == []
    assert plan.status == "planned" and list(plan.requirements) == ["R1"] and [r.req for r in plan.rows] == [["R1"]] * 2
    assert fmt.link_problems(plan) == [] and fmt.mark_problems(plan, done=False) == [] and fmt.scope_cuts(plan) == []
    assert "| " + " | ".join(c.capitalize() for c in fmt.ROW_COLUMNS) + " |" in rule
    for status in fmt.PLAN_STATUS:
        assert f"`{status}`" in rule
    assert "`✓ 2026-11-21`" in rule and fmt.DONE_MARK.match("✓ 2026-11-21")
    assert plan.proof == [("AC 1", "tests/test_session.py", "pytest tests/test_session.py")]
    assert fmt.proof_problems(plan, [1]) == [] and fmt.proof_problems(plan, [1, 2]) != []
    for sign in fmt.HEAVY_SIGNS:
        assert f"`{sign}`" in rule
    limits = {"Phases": "phases", "Task rows": "rows", "Test rows": "test_rows", "Files named by rows": "files",
              "Verification commands": "commands"}
    for label, key in limits.items():
        assert f"| {label} | at most {fmt.SIMPLE_MAX[key]} |" in rule
    assert f"at most {fmt.SIMPLE_MAX['reading_bytes']:,}" in rule


def test_the_task_notes_rule_examples_match_the_parsers() -> None:
    rule = _rule("task-notes")
    note = fmt.parse_triage(_example(rule, "# Triage:"))
    assert note.missing == [] and note.criteria == [1, 2] and (note.gaps, note.deliver, note.route) == (
        "some", "code", "discovery")
    # AC 4, ts-tri-covered: the Gaps example carries a covered row, and the words match the parser's
    assert note.covered == [("SES-B1", "SES-AC1")] and (note.covered_rows, note.gap_rows) == (1, 2)
    assert "`Covered by <behaviour id> and <criterion id>`" in rule and "short discovery visit" in rule
    # AC 5, ts-dis-reading: the hand-off example ends with a Reading list the module reads
    handoff = _example(rule, "# Hand-off:")
    assert fmt.headings_missing(handoff, fmt.HANDOFF_HEADINGS) == [] and fmt.HANDOFF_HEADINGS[-1] == "Reading list"
    assert [(i.path, i.locator, bool(i.reason)) for i in fmt.parse_reading_list(handoff)] == [
        ("docs/specs/session-expiry.spec.md", "SES-B1, SES-B2", True), ("src/auth/session.py", "lines 10-60", True)]
    assert "**Reading list**" in rule and "opens another file only for what the list does not answer" in rule
    report = _example(rule, "# Code report:")
    assert fmt.headings_missing(report, fmt.REPORT_HEADINGS) == [] and fmt.parse_report(report) == {}
    assert "## Rows\n\n  | Row | Status | Note |" in rule and fmt.QUICK_REPORT_HEADINGS[0] == "Rows"
    for route in fmt.ROUTES:
        assert f"`{route}`" in rule
    quick = fmt.parse_triage("## Acceptance criteria\n\n1. One\n\n## Gaps\n\nNone\n\n" + _example(rule, "## Route"))
    assert quick.route == "quick" and fmt.quick_problems(quick) == []
    assert (quick.change_files, quick.change_tests, quick.change_commands) == (
        ["src/auth/session.py"], ["tests/test_session.py"], ["pytest tests/test_session.py"])
    assert f"| Acceptance criteria of the task | at most {fmt.QUICK_MAX['criteria']} |" in rule
    assert f"| Code files to change, beside their tests | at most {fmt.QUICK_MAX['code_files']} |" in rule
    assert f"more than {fmt.QUICK_MAX['lines']} changed lines" in rule


# A sentence several prompts or briefs carry is one rule; a copy edited alone is two rules. Each entry is the words
# that mark the sentence and the sentence itself: a file that holds the mark holds the whole sentence.
SHARED_SENTENCES = (
    ("rank above the specs", "The task's acceptance criteria rank above the specs and decision records, those above "
     "the plan, and the plan above the code."),
    ("claims to verify", "What a step said, a status mark and a reported result are claims to verify, never evidence."),
    ("the line behind its MET", "A criterion the gate's check verified is graded from the check's finding: quote that "
     "finding from the evidence as the line behind its MET, and never grade it UNVERIFIABLE because you cannot run "
     "the check yourself."),
    ("from the file you read", "When you searched and then read the file around the line, quote the line from the "
     "file you read."),
    ("does not block planning", "An open question that the hand-off lists, or that a later note carries on, does not "
     "block planning: the discovery step ends blocked on one that does. It is neither a defect nor something out of "
     "your reach, so it changes no grade and you leave `gap` false for it; the pull request lists it for the owner."),
    ("is not opening it", "Open each rule file named here that this repository holds with the read tool; a search of "
     "a rule file is not opening it."),
    ("never `ls`", "read, search and list files with the file tools (read, grep, glob), never `ls`, `cat`, `wc` or "
     "`python -c`."),
)
IN_EVERY_BRIEF = ("rank above the specs", "claims to verify", "the line behind its MET", "from the file you read")


def test_a_sentence_shared_by_prompts_or_briefs_reads_the_same_in_each() -> None:
    files = sorted([*(ROOT / "prompts").glob("*.md"), *(ROOT / "judges").glob("*.md")])
    for mark, sentence in SHARED_SENTENCES:
        holders = [f for f in files if mark in f.read_text()]
        assert len(holders) >= 4, mark
        for f in holders:
            assert sentence in f.read_text(), f"{f.parent.name}/{f.name}: its copy of the `{mark}` sentence differs"
    for brief in sorted((ROOT / "judges").glob("*.md")):
        for mark in IN_EVERY_BRIEF:
            assert mark in brief.read_text(), f"{brief.name} lacks the `{mark}` sentence"


def test_each_skill_is_named_for_its_folder_and_no_step_loads_one() -> None:
    names = set()
    for path in sorted((ROOT / "skills").glob("*/SKILL.md")):
        head = path.read_text().split("---")[1]
        assert f"name: {path.parent.name}\n" in head and "\ndescription: " in head, path.parent.name
        names.add(path.parent.name)
    assert names == {"answer", "extract", "groom", "review", "setup", "task"}
    assert all(f"`{n}` skill" in (ROOT / "README.md").read_text() for n in names)
    for unit in SPEC.units.values():
        assert not [c for c in (getattr(unit.step, "tools", None) or ()) if str(c).startswith("skill:")]


def test_every_rule_file_says_when_it_is_loaded() -> None:
    """A rule file with no `paths` front matter is loaded into every session of a repository. Only the rule that
    holds for every document may be; each other one names the files it governs, all of them document suffixes."""
    documents = _rule("documents")
    for path in sorted((ROOT / "rules").glob("*.rule.md")):
        text = path.read_text()
        if path.name == "documents.rule.md":
            assert not text.startswith("---"), path.name
            continue
        assert text.startswith("---\npaths:\n"), f"{path.name} has no `paths` front matter"
        patterns = re.findall(r'^  - "([^"]+)"$', text.split("---")[1], re.M)
        assert patterns, path.name
        for pattern in patterns:
            assert pattern.startswith("**/*") and f"`{pattern[4:]}`" in documents, f"{path.name}: {pattern}"


def test_the_copy_of_the_rules_installed_beside_the_package_is_the_same() -> None:
    """A repository that holds the package and its own installed copy (this package's home does) keeps the two the
    same: a rule edited in one place only is a session reading an old rule."""
    for parent in ROOT.parents:
        installed = parent / ".claude" / "rules" / "temperspec"
        if installed.is_dir():
            ours = {p.name: p.read_bytes() for p in (ROOT / "rules").glob("*.rule.md")}
            theirs = {p.name: p.read_bytes() for p in installed.glob("*.rule.md")}
            assert ours == theirs, "run skills/setup/install_rules.py --update in the repository"
            return


def test_the_documents_rule_names_every_suffix() -> None:
    rule = _rule("documents")
    for folder, suffix in fmt.SUFFIX_BY_FOLDER.items():
        assert f"`docs/{folder}/`" in rule and f"`{suffix}`" in rule


# -- the covered mark in triage ---------------------------------------------------------------------------

TRIAGE_CHECKS = ROOT / "evals" / "checks" / "triage"
DISCOVERY_CHECKS = ROOT / "evals" / "checks" / "discovery"


def _triage(fixture: Path, work: Path, **values: str) -> Any:
    _copy(fixture, work)
    ctx = _context("triage", work, {"triage": {"triage_note": "triage_note.md"}}, {"triage": values})
    res, _ = run_check(SPEC.units["triage"].gate, ctx)
    return res


def test_a_gap_row_can_say_it_is_covered_and_the_note_reports_how_many() -> None:  # AC 4, ts-tri-covered
    note = fmt.parse_triage(
        "## Acceptance criteria\n\n1. One\n\n## Gaps\n\n"
        "- G1 spec update: a. Covered by CFG-B1 and CFG-AC1\n"
        "- G2 spec gap: b. Searched `docs/specs/`: nothing\n"
        "- G3 spec update: c. Covered by the config spec\n\n## Route\n\n- Deliver: code\n- Route: discovery\n")
    assert note.gap_rows == 3 and note.covered == [("CFG-B1", "CFG-AC1")] and note.covered_rows == 1
    assert note.covered_claimed == 2  # G3 says it without two ids: claimed, not counted


def test_triage_check_confirms_the_ids_a_covered_row_cites(tmp_path: Path) -> None:  # AC 4, ts-tri-covered
    res = _triage(TRIAGE_CHECKS / "must-pass" / "5-covered", tmp_path / "a", route="discovery", gaps="some",
                  covered="yes")
    assert res.result == "PASS" and _named(res, "ts-tri-covered") == ["pass"], res.evidence
    res = _triage(TRIAGE_CHECKS / "must-fail" / "covered-unknown-id", tmp_path / "b")
    assert res.result == "FAIL" and _named(res, "ts-tri-covered") == ["fail"], res.evidence
    assert "defined 0 times" in next(f.message for f in res.findings if f.criterion == "ts-tri-covered")
    plain = _triage(TRIAGE_CHECKS / "must-pass" / "1-gap", tmp_path / "c")
    assert plain.result == "PASS" and _named(plain, "ts-tri-covered") == ["n_a"]


def test_a_covered_criterion_must_name_the_behaviour_and_the_value_must_follow_the_rows(tmp_path: Path) -> None:
    # AC 4, ts-tri-covered
    work = tmp_path / "a"
    _copy(TRIAGE_CHECKS / "must-pass" / "5-covered", work)
    note = work / "triage_note.md"
    note.write_text(note.read_text().replace("CFG-B1 and CFG-AC1", "CFG-B1 and CFG-AC1x"))  # AC1x is not an id
    ctx = _context("triage", work, {"triage": {"triage_note": "triage_note.md"}}, {"triage": {}})
    assert _named(run_check(SPEC.units["triage"].gate, ctx)[0], "ts-tri-covered") == ["fail"]
    spec = work / "docs" / "specs" / "config-file.spec.md"  # a criterion that names no behaviour of the cited one
    spec.write_text(spec.read_text().replace("(CFG-B1): Started", "(CFG-B2): Started"))
    note.write_text(note.read_text().replace("CFG-AC1x", "CFG-AC1"))
    ctx = _context("triage", work, {"triage": {"triage_note": "triage_note.md"}}, {"triage": {}})
    res = run_check(SPEC.units["triage"].gate, ctx)[0]
    assert "does not name" in next(f.message for f in res.findings if f.criterion == "ts-tri-covered")
    wrong = _triage(TRIAGE_CHECKS / "must-pass" / "1-gap", tmp_path / "b", route="discovery", gaps="some",
                    covered="yes")  # the note has an uncovered row, the value says every row is covered
    assert wrong.result == "FAIL" and _named(wrong, "ts-tri-covered") == ["fail"]
    right = _triage(TRIAGE_CHECKS / "must-pass" / "1-gap", tmp_path / "c", route="discovery", gaps="some",
                    covered="no")
    assert _named(right, "ts-tri-covered") == ["pass"]
    none = _triage(TRIAGE_CHECKS / "must-pass" / "5-covered", tmp_path / "d", covered="no")
    assert _named(none, "ts-tri-covered") == ["fail"]  # every row is covered, so the value is `yes`


# -- the reading list of the hand-off and narrow reading ------------------------------------------------------


def _discovery(fixture: Path, work: Path, **values: str) -> Any:
    _copy(fixture, work)
    ctx = _context("discovery", work, {"discovery": {"handoff": "handoff.md"}}, {"triage": values} if values else None)
    return run_check(SPEC.units["discovery"].gate, ctx)[0]


def test_discovery_check_reads_the_reading_list(tmp_path: Path) -> None:  # AC 5, ts-dis-reading
    for fixture in sorted((DISCOVERY_CHECKS / "must-pass").iterdir()):
        res = _discovery(fixture, tmp_path / fixture.name)
        assert res.result == "PASS" and _named(res, "ts-dis-reading") == ["pass"], (fixture.name, res.evidence)
    res = _discovery(DISCOVERY_CHECKS / "must-fail" / "no-reading-list", tmp_path / "none")
    assert res.result == "FAIL" and _named(res, "ts-dis-reading") == ["fail"], res.evidence
    work = tmp_path / "gone"
    _copy(DISCOVERY_CHECKS / "must-pass" / "2-new-spec", work)
    hand = work / "handoff.md"
    original = hand.read_text()
    item = "`docs/specs/config-file.spec.md` (CFG-B1, CFG-B2): the new behaviours the plan implements"
    assert item in original
    ctx = _context("discovery", work, {"discovery": {"handoff": "handoff.md"}})
    for broken, message in ((item.replace("config-file", "missing"), "does not exist"),
                            (item.replace(" (CFG-B1, CFG-B2)", ""), "ranges or ids"),
                            (item.replace(": the new behaviours the plan implements", ""), "reason")):
        hand.write_text(original.replace(item, broken))
        res = run_check(SPEC.units["discovery"].gate, ctx)[0]
        assert res.result == "FAIL" and message in next(
            f.message for f in res.findings if f.criterion == "ts-dis-reading" and f.status == "fail"), broken


def test_a_run_that_ends_after_discovery_needs_no_reading_list(tmp_path: Path) -> None:  # AC 5, ts-dis-reading
    res = _discovery(DISCOVERY_CHECKS / "must-fail" / "no-reading-list", tmp_path, route="discovery-only")
    assert _named(res, "ts-dis-reading") == ["n_a"]


def test_every_discovery_prompt_says_to_read_narrowly() -> None:  # AC 5, ts-dis-narrow
    prompts = sorted((ROOT / "prompts").glob("discovery*.md"))
    assert prompts
    for prompt in prompts:
        text = " ".join(prompt.read_text(encoding="utf-8").split()).lower()
        assert "search for ids and names" in text, prompt.name
        assert re.search(r"line ranges you need instead of whole files", text), prompt.name
        assert "stop reading once each gap has its answer" in text, prompt.name
        assert "## reading list" in text, prompt.name  # and the hand-off ends with the list the plan starts from


def test_the_plan_prompt_starts_from_the_reading_list() -> None:  # AC 5, ts-plan-reading
    text = " ".join((ROOT / "prompts" / "plan.md").read_text(encoding="utf-8").split()).lower()
    assert "start from the hand-off's reading list" in text
    assert "open another file only for what the list does not answer" in text


# -- routes, scripts and the last stage -------------------------------------------------------------------


def _view(**values: str) -> Any:
    return SimpleNamespace(values=values)


def test_routes_follow_the_values() -> None:  # AC 4, PRL-AC1, OWQ-AC2: the full discovery starts with the reading sessions
    assert routing.route_triage(_view(route="plan")) == "plan"
    assert routing.route_triage(_view(route="discovery")) == "read_gap"
    assert routing.route_triage(_view(route="quick")) == "code"
    assert routing.route_triage(_view()) == "read_gap"  # an unreadable route takes the longer path
    assert routing.route_triage(_view(route="discovery", covered="yes")) == "discovery_short"
    assert routing.route_triage(_view(route="discovery", covered="no")) == "read_gap"
    assert routing.route_triage(_view(route="discovery-only", covered="yes")) == "read_gap"  # docs are the goal
    # OWQ-AC2: a script's key reaches a route as an artifact key; `owner_questions` leaves `empty` only for no question
    assert routing.route_ask(SimpleNamespace(values={}, artifact_keys=("question_list", "empty"))) == "discovery"
    assert routing.route_ask(SimpleNamespace(values={"empty": "yes"}, artifact_keys=())) == "discovery"
    assert routing.route_ask(SimpleNamespace(values={}, artifact_keys=("question_list",))) == "ask_owner"  # a question
    assert routing.route_ask(SimpleNamespace(values={}, artifact_keys=())) == "ask_owner"  # a list that failed pauses
    assert routing.route_short(_view(settled="yes")) == "plan"
    assert routing.route_short(_view(settled="no")) == "read_gap"
    assert routing.route_short(_view()) == "read_gap"
    assert routing.route_discovery(_view(route="discovery-only")) == "finalizer"
    assert routing.route_discovery(_view(route="discovery")) == "plan"
    assert not hasattr(routing, "route_plan")  # AC 1, CDM-AC1: the route after the plan is the switch `code_mode`


def test_setup_runs_only_for_a_repository_with_no_overview_spec() -> None:  # AC 2, PRL-AC5
    assert routing.route_setup(SimpleNamespace(artifact_keys=("setup_needed",))) == "list_components"
    assert routing.route_setup(SimpleNamespace(artifact_keys=("setup_ready",))) == "triage"
    assert SPEC.order[:6] == ("prepare", "setup_route", "list_components", "read_component", "setup", "triage")


def _git(cwd: Path, *args: str) -> str:
    return subprocess.run(["git", *args], cwd=cwd, capture_output=True, text=True, check=True).stdout


@pytest.fixture
def repo(tmp_path: Path) -> Path:
    _git(tmp_path, "init", "-q", "-b", "main")
    _git(tmp_path, "-c", "user.name=t", "-c", "user.email=t@example.invalid", "commit", "-q", "--allow-empty",
         "-m", "start")
    return tmp_path


def test_commit_step_commits_the_steps_files_and_leaves_the_state_folder(repo: Path) -> None:
    (repo / "docs").mkdir()
    (repo / "docs" / "note.md").write_text("x\n")
    (repo / ".tempergraph").mkdir()
    (repo / ".tempergraph" / "state.json").write_text("{}\n")
    ctx = SimpleNamespace(workdir=repo, unit="triage", request={"task_id": "TASK 7"})
    assert routing.commit_step(ctx) == {}
    assert _git(repo, "log", "-1", "--format=%s").strip() == "docs(temperspec): triage for TASK-7"
    assert _git(repo, "show", "--name-only", "--format=").split() == ["docs/note.md"]
    head = _git(repo, "rev-parse", "HEAD")
    assert routing.commit_step(ctx) == {} and _git(repo, "rev-parse", "HEAD") == head  # nothing new, no commit
    assert git_facts(repo).clean


def test_commit_step_commits_when_git_ignores_the_state_folder(repo: Path) -> None:
    # git 2.39 exits 1 on an exclude pathspec that names an ignored path; the step must still commit
    (repo / ".gitignore").write_text(".tempergraph/\n")
    (repo / ".tempergraph").mkdir()
    (repo / ".tempergraph" / "capabilities.md").write_text("x\n")
    (repo / "note.md").write_text("x\n")
    ctx = SimpleNamespace(workdir=repo, unit="prepare", request={"task_id": "i1"})
    assert routing.commit_step(ctx) == {}
    assert _git(repo, "log", "-1", "--format=%s").strip() == "docs(temperspec): prepare for i1"
    assert sorted(_git(repo, "show", "--name-only", "--format=").split()) == [".gitignore", "note.md"]


def test_install_rules_writes_the_rule_files_once(repo: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(Path, "home", lambda: repo / "no-home")
    ctx = SimpleNamespace(workdir=repo, unit="triage", request={})
    routing.install_rules(ctx)
    target = repo / ".claude" / "rules" / "temperspec"
    assert sorted(p.name for p in target.iterdir()) == sorted(p.name for p in (ROOT / "rules").glob("*.rule.md"))
    (target / "spec.rule.md").write_text("edited here\n")
    routing.install_rules(ctx)
    assert (target / "spec.rule.md").read_text() == "edited here\n"  # a repository's own copy is kept
    assert sorted(p.name for p in (repo / fmt.TEMPLATE_DIR).iterdir()) == sorted(_templates())


# -- the fill-in templates are the rule files' own examples ----------------------------------------------


def _templates() -> dict[str, str]:
    out: dict[str, str] = {}
    for rule in sorted((ROOT / "rules").glob("*.rule.md")):
        out.update(fmt.rule_templates(rule.name.split(".")[0], rule.read_text(encoding="utf-8")))
    return out


def test_each_template_is_its_rules_example_and_the_rule_names_it() -> None:
    names = {"decision": "# <The decision", "plan": "---\ntask:", "research": "# <The question>",
             "spec": "# <Capability name>", "triage": "# Triage:", "hand-off": "# Hand-off:",
             "code-report": "# Code report:", "setup": "# Setup:"}
    got = _templates()
    assert sorted(got) == sorted(f"{n}.template.md" for n in names)
    for name, opening in names.items():
        rule = _rule(name if name in ("decision", "plan", "research", "spec") else "task-notes")
        assert got[f"{name}.template.md"] == _example(rule, opening)
        assert f"`{name}.template.md`" in rule or f"`docs/templates/{name}.template.md`" in rule
    assert fmt.headings_missing(got["decision.template.md"], fmt.DECISION_HEADINGS) == []
    assert fmt.headings_missing(got["research.template.md"], fmt.RESEARCH_HEADINGS) == []


def test_the_setup_skill_installs_rules_and_templates_and_keeps_local_edits(tmp_path: Path) -> None:
    script = ROOT / "skills" / "setup" / "install_rules.py"
    run = subprocess.run(["python3", "-I", str(script), "--target", str(tmp_path)], capture_output=True, text=True,
                         check=True)
    assert run.stdout.count("installed") == len(list((ROOT / "rules").glob("*.rule.md"))) + len(_templates())
    for name, body in _templates().items():
        assert (tmp_path / fmt.TEMPLATE_DIR / name).read_text(encoding="utf-8") == body
    (tmp_path / fmt.TEMPLATE_DIR / "plan.template.md").write_text("mine\n")
    again = subprocess.run(["python3", "-I", str(script), "--target", str(tmp_path)], capture_output=True, text=True,
                           check=True).stdout
    assert "kept (differs)" in again and "plan.template.md" in again


def test_prepare_installs_rules_and_the_project_note_once_and_reports_setup(
        repo: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(Path, "home", lambda: repo / "no-home")
    (repo / "CLAUDE.md").write_text("# Project\n\nRun the tests with `pytest`.\n")
    ctx = SimpleNamespace(workdir=repo, unit="prepare", request={"task_id": "TASK-7"})
    assert routing.prepare(ctx) == {"setup_needed": "yes"}
    text = (repo / "CLAUDE.md").read_text()
    assert text.startswith("# Project\n\nRun the tests with `pytest`.\n")  # the repository's own text is kept
    assert text.count(fmt.CONTEXT_START) == 1 and "temperspec" in text
    assert (repo / ".claude" / "rules" / "temperspec" / "spec.rule.md").is_file()
    assert git_facts(repo).clean and _git(repo, "log", "-1", "--format=%s").strip().startswith("docs(temperspec): prepare")
    head = _git(repo, "rev-parse", "HEAD")
    (repo / "docs" / "specs").mkdir(parents=True)
    (repo / "docs" / "specs" / "overview.spec.md").write_text("# x\n")
    _git(repo, "add", "-A")
    _git(repo, "-c", "user.name=t", "-c", "user.email=t@example.invalid", "commit", "-q", "-m", "overview")
    after = _git(repo, "rev-parse", "HEAD")
    assert routing.prepare(ctx) == {"setup_ready": "yes"}
    assert (repo / "CLAUDE.md").read_text() == text and _git(repo, "rev-parse", "HEAD") == after != head


def test_the_project_note_goes_to_agents_md_when_that_is_the_file_and_is_replaced_in_place(tmp_path: Path) -> None:
    (tmp_path / "AGENTS.md").write_text(f"# A\n\n{fmt.CONTEXT_START}\nold\n{fmt.CONTEXT_END}\n\n## After\n")
    assert routing.write_context(tmp_path) == "AGENTS.md" and not (tmp_path / "CLAUDE.md").exists()
    text = (tmp_path / "AGENTS.md").read_text()
    assert "old" not in text and text.endswith("## After\n") and text.count(fmt.CONTEXT_END) == 1


def test_specs_of_the_setup_step_need_no_test_that_names_their_criteria(tmp_path: Path) -> None:
    fixture = ROOT / "evals" / "checks" / "setup" / "must-pass" / "2-components"
    _copy(fixture, tmp_path)
    artifacts = {"setup": {"overview": "overview.md", "setup_note": "setup_note.md"}}
    ctx = _context("outcome", tmp_path, artifacts)
    spec = "docs/specs/config-file.spec.md"
    assert [f.status for f in checks._traced(ctx, [spec], checks._walk(ctx))] == ["n_a"]
    assert [f.status for f in checks._traced(_context("outcome", tmp_path, {}), [spec], checks._walk(ctx))] == [
        "fail", "fail"]


class _Final:
    def __init__(self, replies: dict[str, tuple[int, str]], branch: str = "tg/task-7", base: str = "main") -> None:
        self.replies, self.branch, self.base, self.ran = replies, branch, base, []
        self.git = GitFacts(branch=branch)

    def run(self, cmd: str) -> CommandRun:
        self.ran.append(cmd)
        for prefix, (code, tail) in self.replies.items():
            if cmd.startswith(prefix):
                return CommandRun(argv=tuple(cmd.split()), finished=True, exit_code=code, tail=tail)
        return CommandRun(argv=tuple(cmd.split()), not_started=True)


def test_the_last_stage_opens_a_draft_pull_request() -> None:
    ctx = _Final({"git remote": (0, "origin\n"), "git push": (0, ""), "gh pr list": (0, "[]\n"),
                  "gh pr create": (0, "https://github.com/acme/tool/pull/12\n")})
    got = routing.finalize(ctx)
    assert (got.outcome, got.url) == ("opened", "https://github.com/acme/tool/pull/12")
    assert ctx.ran[-1] == "gh pr create --draft --fill --base main --head tg/task-7"


def test_the_last_stage_reuses_an_open_pull_request() -> None:
    ctx = _Final({"git remote": (0, "origin\n"), "git push": (0, ""),
                  "gh pr list": (0, '[{"url":"https://github.com/acme/tool/pull/9"}]\n')})
    got = routing.finalize(ctx)
    assert (got.outcome, got.url) == ("reused", "https://github.com/acme/tool/pull/9")
    assert not any(c.startswith("gh pr create") for c in ctx.ran)


def test_the_last_stage_never_fails_a_run_for_a_missing_remote_or_tool() -> None:
    assert routing.finalize(_Final({"git remote": (0, "")})).outcome == "skipped"
    assert routing.finalize(_Final({"git remote": (0, "origin\n"), "git push": (1, "denied")})).outcome == "skipped"
    pushed = routing.finalize(_Final({"git remote": (0, "origin\n"), "git push": (0, "")}))
    assert pushed.outcome == "pushed" and pushed.manual_steps
    assert routing.finalize(_Final({}, branch="bad branch;rm")).outcome == "skipped"
    assert set(SPEC.finalizer_outcomes) == {"opened", "reused", "pushed", "skipped"}


def test_a_spec_edit_with_no_behaviour_change_is_reported_as_collateral(repo: Path) -> None:
    spec = (ROOT / "evals/checks/discovery/must-pass/2-new-spec/docs/specs/config-file.spec.md").read_text()
    path = repo / "docs" / "specs" / "config-file.spec.md"
    path.parent.mkdir(parents=True)
    path.write_text(spec)
    _git(repo, "add", "-A")
    _git(repo, "-c", "user.name=t", "-c", "user.email=t@example.invalid", "commit", "-q", "-m", "spec")
    base = _git(repo, "rev-parse", "HEAD").strip()
    path.write_text(spec.replace("People who start the tool depend", "Everyone who starts the tool depends"))
    ctx = _context("outcome", repo, {}, git=git_facts(repo, base))
    found = checks._collateral(ctx, ["docs/specs/config-file.spec.md"])
    assert [(f.status, f.criterion) for f in found] == [("maybe", "ts-collateral")]
    path.write_text(spec.replace("SHALL exit with code 2", "SHALL exit with code 3"))
    ctx = _context("outcome", repo, {}, git=git_facts(repo, base))
    assert [f.status for f in checks._collateral(ctx, ["docs/specs/config-file.spec.md"])] == ["pass"]


def test_no_unit_uses_the_large_model_tier() -> None:
    for name in SPEC.order:
        unit = SPEC.units[name]
        if unit.kind != "step":
            continue
        assert unit.step is not None and unit.step.model == "medium", name
        assert unit.gate.judge is not None and unit.gate.judge.model == "medium", name
    assert outcome_unit(SPEC).gate.judge.model == "medium"  # type: ignore[union-attr]
    assert SPEC.units["discovery"].step.session_options.effort == "max"  # type: ignore[union-attr]


def test_every_step_and_judge_states_its_model_effort_and_reason() -> None:  # decision record `model-and-effort-per-unit`
    blueprint = {u["name"]: u for u in json.loads((ROOT / "blueprint.json").read_text())["units"]}
    efforts = {}
    for name in SPEC.order:
        unit = SPEC.units[name]
        if unit.kind != "step":
            continue
        step, judge = unit.step, unit.gate.judge
        assert step is not None and judge is not None
        assert step.session_options is not None and judge.session_options is not None, name
        efforts[name] = (step.session_options.effort, judge.session_options.effort)
        assert len(step.sizing.split()) >= 4 and len(judge.sizing.split()) >= 4, name
        assert blueprint[name]["sizing"] == {"model": step.model, "effort": step.session_options.effort,
                                             "why": step.sizing}, name
        assert blueprint[name]["judge_sizing"] == {"model": judge.model, "effort": judge.session_options.effort,
                                                   "why": judge.sizing}, name
    assert efforts == {"setup": ("high", "medium"), "triage": ("medium", "medium"),
                       "discovery_short": ("high", "high"), "discovery": ("max", "high"),
                       "plan": ("high", "high"), "expand": ("medium", "medium"), "code": ("high", "high"),
                       "independent_review": ("high", "medium")}


# -- the quick lane, the proof of a criterion and the pull request's description ---------------------------

QUICK = ROOT / "evals" / "checks" / "code" / "must-pass" / "3-quick"


def _quick_ctx(work: Path, changed: tuple[str, ...], visit: int = 1, unit: str = "code") -> CheckContext:
    _copy(QUICK, work)
    ctx = _context(unit, work, {"triage": {"triage_note": "triage_note.md"}, "code": {"code_report": "code_report.md"}},
                   {"triage": {"route": "quick", "gaps": "none"}}, GitFacts(changed_paths=changed))
    ctx.visit = visit
    return ctx


def _named(res: Any, criterion: str) -> list[str]:
    return [f.status for f in res.findings if f.criterion == criterion]


def test_a_quick_change_inside_its_limits_passes_the_code_gate(tmp_path: Path) -> None:
    ctx = _quick_ctx(tmp_path, ("src/tool/config.py", "tests/test_config.py", "docs/tasks/T.triage.md", "CLAUDE.md"))
    res, _ = run_check(SPEC.units["code"].gate, ctx)
    assert res.result == "PASS", res.evidence
    assert _named(res, "ts-code-lane") == ["pass"] and _named(res, "ts-code-proof") == ["pass"]
    assert "Criterion tests: AC 1 -> tests/test_config.py; AC 2 -> tests/test_config.py" in res.evidence


@pytest.mark.parametrize("changed", [
    ("src/tool/config.py", "docs/specs/config-file.spec.md"),  # a spec was edited
    ("src/tool/config.py", "src/tool/main.py"),  # a file the note does not name
    ("src/tool/config.py", "src/tool/a.py", "src/tool/b.py"),  # too many code files
])
def test_a_quick_change_outside_its_limits_is_sent_back(changed: tuple[str, ...], tmp_path: Path) -> None:
    res, _ = run_check(SPEC.units["code"].gate, _quick_ctx(tmp_path, changed))
    lane = [f for f in res.findings if f.criterion == "ts-code-lane"]
    assert res.result == "FAIL" and lane and all(f.status == "fail" for f in lane)
    assert "UPSTREAM triage" in lane[0].fix
    assert "triage" in SPEC.units["code"].gate.back_targets


def test_a_planned_run_is_not_measured_as_quick(tmp_path: Path) -> None:
    files = _copy(ROOT / "evals" / "checks" / "code" / "must-pass" / "2-simple-plan", tmp_path)
    artifacts = {OWNER[f.stem]: {f.stem: f.relative_to(tmp_path).as_posix()} for f in files if f.stem in OWNER}
    ctx = _context("code", tmp_path, artifacts, {"triage": {"route": "plan"}},
                   GitFacts(changed_paths=("src/a.py", "src/b.py", "src/c.py", "docs/specs/x.spec.md")))
    res, _ = run_check(SPEC.units["code"].gate, ctx)
    assert _named(res, "ts-code-lane") == ["n_a"] and res.result == "PASS", res.evidence


def test_a_run_that_came_back_to_triage_cannot_take_the_quick_lane_again(tmp_path: Path) -> None:
    first = _quick_ctx(tmp_path / "a", (), unit="triage")
    again = _quick_ctx(tmp_path / "b", (), visit=2, unit="triage")
    assert run_check(SPEC.units["triage"].gate, first)[0].result == "PASS"
    res, _ = run_check(SPEC.units["triage"].gate, again)
    assert res.result == "FAIL" and _named(res, "ts-tri-route") == ["fail"]


def test_a_criterion_is_carried_only_by_a_test_that_runs() -> None:
    assert fmt.carried("def test_x():  # SES-AC1\n", "SES-AC1") == (True, False)
    assert fmt.carried("@pytest.mark.skip\ndef test_x():  # SES-AC1\n", "SES-AC1") == (True, True)
    assert fmt.carried("def test_ac_2_exit_code():\n", "AC 2") == (True, False)
    assert fmt.carried("def test_ac_21():\n", "AC 2") == (False, False)
    assert fmt.carried("it.skip('AC 1 refuses', () => {})\n", "AC 1") == (True, True)


class _Summary(_Final):
    """A last-stage context with a workspace, for the pull request's description."""

    def __init__(self, work: Path, replies: dict[str, tuple[int, str]], diffs: dict[str, str]) -> None:
        super().__init__(replies, base="main")
        self.workdir, self.out_dir, self.task_id, self.diffs = work, work / ".out", "TASK-7", diffs
        self.artifacts = {"triage": {"triage_note": "note.md"}, "discovery": {"handoff": "handoff.md"},
                          "code": {"code_report": "report.md"}}
        self.values = {"triage": {"route": "discovery"}}

    def run(self, cmd: str) -> CommandRun:
        for prefix, text in self.diffs.items():
            if cmd.startswith(prefix):
                self.ran.append(cmd)
                out = self.workdir / f"{len(self.ran)}.diff"
                out.write_text(text)
                return CommandRun(argv=tuple(cmd.split()), finished=True, exit_code=0, output_path=str(out))
        return super().run(cmd)


def test_the_pull_request_says_what_the_owner_has_to_read(tmp_path: Path) -> None:
    # PRD-AC1, PRD-AC2, PRD-AC3, PRD-AC4 (AC 6)
    (tmp_path / "note.md").write_text("# Triage\n\n## Acceptance criteria\n\n1. An idle session is refused\n")
    (tmp_path / "handoff.md").write_text("# Hand-off\n\n## Decisions\n\n- Idle time counts from the last request\n\n"
                                         "## Open questions\n\n- None\n")
    (tmp_path / "report.md").write_text("# Code report\n\n## Verification\n\n- `pytest`: passed\n\n## Deviations\n\n"
                                        "- `src/auth/clock.py` was needed for the test\n")
    diff = ("+### SES-B2 Idle expiry\n+WHEN a session is idle for 30 minutes THE service SHALL refuse its requests\n"
            "+- SES-AC2 (SES-B2): a request after 31 idle minutes is refused\n+Some prose that is not listed\n")
    ctx = _Summary(tmp_path, {"git remote": (0, "origin\n"), "git push": (0, ""), "gh pr list": (0, "[]\n"),
                              "gh pr create": (0, "https://github.com/acme/tool/pull/12\n")},
                   {"git diff --name-only": "docs/specs/session.spec.md\nsrc/auth/session.py\n.claude/rules/x.md\n",
                    "git diff --unified=0": diff})
    got = routing.finalize(ctx)
    assert got.outcome == "opened" and ctx.ran[-1].endswith("--body-file .tempergraph/pull-request.md")
    # the engine refuses a command that names an absolute or parent path, so every command of the last stage is one
    # its own resolver accepts (a refused `gh pr create` ends the run `pushed`, with no pull request)
    allow = importlib.import_module("tgwf_temperspec").ALLOW
    assert [c for c in ctx.ran if isinstance(resolve_command(allow, c, tmp_path), CommandRefusal)] == []
    assert (tmp_path / ".tempergraph" / ".gitignore").read_text() == "*\n"  # the description is never committed
    body = (tmp_path / ".tempergraph" / "pull-request.md").read_text()
    assert "1. An idle session is refused" in body and "`docs/specs/session.spec.md`" in body
    assert "added: SES-B2 Idle expiry" in body and "added: SES-AC2 (SES-B2)" in body and "prose" not in body
    assert "Idle time counts from the last request" in body and "Open questions" not in body
    assert "`src/auth/clock.py` was needed for the test" in body and ".claude/rules" not in body


def test_a_reused_pull_request_gets_the_new_description(tmp_path: Path) -> None:
    # PRD-AC8 (AC 6)
    (tmp_path / "note.md").write_text("## Acceptance criteria\n\n1. One\n")
    ctx = _Summary(tmp_path, {"git remote": (0, "origin\n"), "git push": (0, ""), "gh pr edit": (0, ""),
                              "gh pr list": (0, '[{"url":"https://github.com/acme/tool/pull/9"}]\n')}, {})
    got = routing.finalize(ctx)
    assert got.outcome == "reused" and "not updated" not in got.reason
    assert ctx.ran[-1] == "gh pr edit https://github.com/acme/tool/pull/9 --body-file .tempergraph/pull-request.md"
    assert not any(c.startswith("gh pr create") for c in ctx.ran)


def test_a_refused_replacement_says_the_description_was_not_updated(tmp_path: Path) -> None:
    # PRD-AC8 (AC 6)
    (tmp_path / "note.md").write_text("## Acceptance criteria\n\n1. One\n")
    ctx = _Summary(tmp_path, {"git remote": (0, "origin\n"), "git push": (0, ""), "gh pr edit": (1, "denied"),
                              "gh pr list": (0, '[{"url":"https://github.com/acme/tool/pull/9"}]\n')}, {})
    got = routing.finalize(ctx)
    assert got.outcome == "reused" and "not updated" in got.reason


def test_a_new_draft_pull_request_carries_the_description(tmp_path: Path) -> None:
    # PRD-AC7 (AC 6)
    (tmp_path / "note.md").write_text("## Acceptance criteria\n\n1. One\n")
    ctx = _Summary(tmp_path, {"git remote": (0, "origin\n"), "git push": (0, ""), "gh pr list": (0, "[]\n"),
                              "gh pr create": (0, "https://github.com/acme/tool/pull/12\n")}, {})
    got = routing.finalize(ctx)
    created = [c for c in ctx.ran if c.startswith("gh pr create")]
    assert got.outcome == "opened" and len(created) == 1
    assert created[0].endswith("--body-file .tempergraph/pull-request.md")
    assert "1. One" in (tmp_path / ".tempergraph" / "pull-request.md").read_text()


def test_a_description_that_cannot_be_written_opens_the_pull_request_without_one(tmp_path: Path) -> None:
    # PRD-AC6 (AC 6)
    (tmp_path / "note.md").write_text("## Acceptance criteria\n\n1. One\n")
    (tmp_path / ".tempergraph").write_text("a file where the folder should be")
    ctx = _Summary(tmp_path, {"git remote": (0, "origin\n"), "git push": (0, ""), "gh pr list": (0, "[]\n"),
                              "gh pr create": (0, "https://github.com/acme/tool/pull/12\n")}, {})
    got = routing.finalize(ctx)
    created = [c for c in ctx.ran if c.startswith("gh pr create")]
    assert got.outcome == "opened" and len(created) == 1 and "--body-file" not in created[0]


def test_the_description_is_never_committed(repo: Path) -> None:
    # PRD-AC5 (AC 6)
    (repo / "note.md").write_text("## Acceptance criteria\n\n1. One\n")
    ctx = _Summary(repo, {"git remote": (0, "origin\n"), "git push": (0, ""), "gh pr list": (0, "[]\n"),
                          "gh pr create": (0, "https://github.com/acme/tool/pull/12\n")}, {})
    routing.finalize(ctx)
    assert (repo / ".tempergraph" / "pull-request.md").is_file()
    status = _git(repo, "status", "--porcelain", "--untracked-files=all")
    assert "pull-request" not in status and ".tempergraph" not in status
    assert "pull-request" not in _git(repo, "log", "--name-only", "--format=")


def test_the_description_lists_only_the_first_14_criteria_and_names_what_the_run_wrote(tmp_path: Path) -> None:
    # PRD-AC1, PRD-AC2, PRD-AC3, PRD-AC4 (AC 6)
    (tmp_path / "note.md").write_text("## Acceptance criteria\n\n" + "".join(f"{n}. Criterion {n}\n" for n in range(1, 16)))
    (tmp_path / "handoff.md").write_text("## Decisions\n\n- None\n\n## Open questions\n\n- None\n")
    (tmp_path / "report.md").write_text("## Deviations\n\n- None\n")
    ctx = _Summary(tmp_path, {}, {"git diff --name-only": "src/a.py\n"})
    body = summary.build(ctx)
    assert "14. Criterion 14" in body and "15. Criterion 15" not in body
    assert "No spec and no decision record changed." in body
    assert "Open questions" not in body and "Deviations from the plan" not in body and "Decisions taken" not in body
    # the run wrote no plan: the line names the three other documents
    line = next(ln for ln in body.splitlines() if "not needed for review" in ln)
    assert "note.md" in line and "handoff.md" in line and "report.md" in line and line.count("`") == 6


def test_the_description_lists_the_findings_that_block_nothing(tmp_path: Path) -> None:
    # PRD-AC9 (AC 6)
    (tmp_path / "note.md").write_text("## Acceptance criteria\n\n1. One\n")
    (tmp_path / "TASK-7.review.md").write_text(
        "# Review: TASK-7\n\n## Findings\n\n1. `src/a.py:3` blocking: the loop never ends\n"
        "2. `src/b.py:9` not blocking: a name could be clearer\n\n## Earlier review\n\n"
        "1. `src/c.py:5` not blocking: a comment is stale\n")
    body = summary.build(_Summary(tmp_path, {}, {}))
    head = "Review findings that block nothing"
    assert head in body and body.index("Read these") < body.index(head)
    listed = body[body.index(head):]
    assert "src/b.py" in listed and "9" in listed and "a name could be clearer" in listed
    assert "src/c.py" in listed and "a comment is stale" in listed
    assert "the loop never ends" not in body
    (tmp_path / "TASK-7.review.md").write_text("# Review: TASK-7\n\n## Findings\n\nNone\n")
    assert head not in summary.build(_Summary(tmp_path, {}, {}))
    (tmp_path / "TASK-7.review.md").unlink()
    assert head not in summary.build(_Summary(tmp_path, {}, {}))


# -- the plan's marks: checked first at the code gate, then verified against what changed -------------------

DONE = ROOT / "evals" / "checks" / "code" / "must-pass" / "1-done"


class _Counting(CheckContext):
    """A check context that counts the commands the check runs."""

    ran: list[str]

    def run(self, cmd: str, **kw: Any) -> Any:  # type: ignore[override]
        self.ran.append(cmd)
        return super().run(cmd, **kw)


def _code_ctx(work: Path, fixture: Path, git: GitFacts | None = None, reuse_store: Path | None = None) -> _Counting:
    files = _copy(fixture, work)
    artifacts: dict[str, dict[str, str]] = {}
    for f in files:
        if f.stem in OWNER:
            artifacts.setdefault(OWNER[f.stem], {})[f.stem] = f.relative_to(work).as_posix()
    ctx = _Counting(unit="code", workdir=work, request={}, artifacts=artifacts, values={"triage": {"route": "plan"}},
                    git=git or GitFacts(), allow=SPEC.allow_commands, out_dir=work.parent / f"{work.name}.out",
                    deadline_at=time.monotonic() + 60, reuse_store=reuse_store)
    ctx.ran = []
    return ctx


def test_an_unmarked_plan_goes_back_to_code_with_no_command_run(tmp_path: Path) -> None:
    ctx = _code_ctx(tmp_path, ROOT / "evals" / "checks" / "code" / "must-fail" / "open-row")
    res, _ = run_check(SPEC.units["code"].gate, ctx)
    assert res.result == "FAIL" and _named(res, "ts-code-rows") == ["fail"] and ctx.ran == []
    assert not _named(res, "ts-code-verify") and not _named(res, "ts-code-proof")


def test_a_marked_row_whose_file_did_not_change_fails_the_code_gate(tmp_path: Path) -> None:
    git = GitFacts(base="abc123", changed_paths=("tests/test_config.py", "src/tool/config.py"))
    res, _ = run_check(SPEC.units["code"].gate, _code_ctx(tmp_path / "a", DONE, git))
    rows = [f for f in res.findings if f.criterion == "ts-code-changed"]
    assert res.result == "FAIL" and [f.place for f in rows] == ["README.md"], res.evidence
    git = GitFacts(base="abc123", changed_paths=("tests/test_config.py", "src/tool/config.py", "README.md"))
    res, _ = run_check(SPEC.units["code"].gate, _code_ctx(tmp_path / "b", DONE, git))
    assert _named(res, "ts-code-changed") == ["pass"] and _named(res, "ts-code-rows") == ["pass"], res.evidence


def test_words_that_cut_scope_are_a_maybe_for_the_plan_judge(tmp_path: Path) -> None:
    files = _copy(ROOT / "evals" / "checks" / "plan" / "must-pass" / "2-simple", tmp_path)
    plan = tmp_path / "plan.md"
    plan.write_text(plan.read_text().replace("Report the missing file and exit with code 2",
                                             "Report the missing file with a stub for now"))
    artifacts = {OWNER[f.stem]: {f.stem: f.relative_to(tmp_path).as_posix()} for f in files if f.stem in OWNER}
    res, _ = run_check(SPEC.units["plan"].gate, _context("plan", tmp_path, artifacts))
    assert res.result == "MAYBE" and _named(res, "ts-plan-scope") == ["maybe"], res.evidence
    assert "stub" in next(f.message for f in res.findings if f.criterion == "ts-plan-scope")


# -- one full run per code visit, and a result the gate already holds is not run again -------------------------


def _code_prompt() -> str:
    return " ".join((ROOT / "prompts" / "code.md").read_text(encoding="utf-8").split())


def test_the_code_prompt_runs_a_phases_test_files_and_the_full_commands_once() -> None:  # AC 1, ts-code-once
    text = _code_prompt()
    assert "After each phase, run only the test files that the phase's rows name" in text
    assert "never the whole suite" in text
    low = text.lower()  # the gate's own check reads the prompt case-insensitively
    assert ("run each verification command of the plan once, after the last phase, with the plan marked completed "
            "and the code report written") in low
    assert "change no file after that run" in low
    assert "in the quick lane, run the note's `verify` commands once, after the last criterion and the report" in low
    assert "before you write the report" not in text  # the report comes before the final run now
    for phrase in checks.PROMPT_SAYS["ts-code-once"][1]:
        assert phrase in text.lower(), phrase


def test_the_code_step_declares_the_preview_and_its_prompt_runs_the_commands_through_it() -> None:
    # AC 2, ts-code-preview (CHK-B17)
    step = SPEC.units["code"].step
    assert step is not None and step.self_check is True
    assert all(SPEC.units[u].step.self_check is False for u in SPEC.order  # type: ignore[union-attr]
               if u != "code" and SPEC.units[u].kind == "step")
    text = _code_prompt()
    assert ('make that one run through the preview command that the engine names under "check your work before you '
            'end"') in text.lower()
    assert "call it once, when nothing is left to change" in text
    assert "the phases' own test runs stay plain commands" in text
    for phrase in checks.PROMPT_SAYS["ts-code-preview"][1]:
        assert phrase in text.lower(), phrase


def _counted(runs: list[dict[str, Any]]) -> list[dict[str, Any]]:
    """The runs `ts-code-reuse` counts: the read of the run's history (PHC-B16) comes after that finding."""
    return [r for r in runs if "--name-only" not in r["argv"]]


def test_a_second_gate_run_on_an_unchanged_tree_runs_no_verification_command(
        repo: Path, tmp_path_factory: pytest.TempPathFactory) -> None:  # AC 3, ts-code-reuse (CHK-B13)
    store = tmp_path_factory.mktemp("store") / "command_runs.jsonl"
    base = _git(repo, "rev-parse", "HEAD").strip()
    _copy(DONE, repo)
    _git(repo, "add", "-A")
    _git(repo, "-c", "user.name=t", "-c", "user.email=t@example.invalid", "commit", "-q", "-m", "the code step")

    def gate_run() -> list[dict[str, Any]]:
        ctx = _code_ctx(repo, DONE, git_facts(repo, base), store)
        res, _ = run_check(SPEC.units["code"].gate, ctx)
        assert _named(res, "ts-code-verify") == ["pass"], res.evidence
        assert _named(res, "ts-code-reuse") == ["pass"], res.evidence  # read from the gate's own runs (B30)
        reuse.append(next(f.message for f in res.findings if f.criterion == "ts-code-reuse"))
        return list(res.runs)

    reuse: list[str] = []

    first, second = gate_run(), gate_run()  # a retry, or a later visit, on the same tree and the same store
    assert first and all(r["reused"] is False and r["exit_code"] == 0 for r in first)
    assert len(second) == len(first) and all(r["reused"] is True for r in second)  # none was started again
    counted = len(_counted(second))
    assert reuse[0].startswith("0 of ") and reuse[1].startswith(f"{counted} of {counted} ")
    (repo / "notes.txt").write_text("changed\n")  # a changed tree changes the key: the commands run again
    third = gate_run()
    assert third and all(r["reused"] is False for r in third)


# -- the session's one run goes through the preview; the gate reuses it after the commit ----------------------


def _preview_ctx(work: Path, fixture: Path, git: GitFacts | None = None, store: Path | None = None) -> _Counting:
    ctx = _code_ctx(work, fixture, git, store)
    ctx.preview = True
    return ctx


def _commit_all(repo: Path, message: str = "the code step") -> None:
    _git(repo, "add", "-A")
    _git(repo, "-c", "user.name=t", "-c", "user.email=t@example.invalid", "commit", "-q", "-m", message)


def test_a_preview_of_the_code_gate_runs_the_commands_and_reports_no_pending_report_or_commit(
        tmp_path: Path) -> None:  # AC 2, ts-code-previewed (CHK-B17, CHK-B10)
    dirty = GitFacts(clean=False)  # the session's files are not committed yet
    ctx = _preview_ctx(tmp_path / "a", DONE, dirty)
    (tmp_path / "a" / "code_report.md").unlink()  # the report is not handed over yet
    res, _ = run_check(SPEC.units["code"].gate, ctx)
    assert ctx.ran == ["git --version"], ctx.ran
    assert not [f for f in res.findings if f.status == "fail"], res.evidence
    assert _named(res, "ts-code-verify") == ["pass"] and _named(res, "ts-code-commit") == []
    plain = _code_ctx(tmp_path / "b", DONE, dirty)  # the same tree as the gate's own check still fails both
    (tmp_path / "b" / "code_report.md").unlink()
    res, _ = run_check(SPEC.units["code"].gate, plain)
    assert _named(res, "ts-code-rows") == ["fail"] and _named(res, "ts-code-commit") == ["fail"]
    assert plain.ran == []
    quick = _quick_ctx(tmp_path / "c", ())  # the quick lane: its rows are read from the report, not yet written
    quick.git = GitFacts(clean=False)
    quick.preview = True
    (tmp_path / "c" / "code_report.md").unlink()
    res, _ = run_check(SPEC.units["code"].gate, quick)
    assert [r["argv"] for r in res.runs][:1] == [["git", "--version"]], res.evidence  # the note's `Verify` command
    assert not [f for f in res.findings if f.criterion in ("ts-code-rows", "ts-code-commit") and f.status == "fail"]


def test_a_preview_on_an_unfinished_plan_runs_no_command(tmp_path: Path) -> None:  # AC 2, ts-code-previewed
    ctx = _preview_ctx(tmp_path, ROOT / "evals" / "checks" / "code" / "must-fail" / "open-row", GitFacts(clean=False))
    res, _ = run_check(SPEC.units["code"].gate, ctx)
    assert ctx.ran == [] and _named(res, "ts-code-rows") == ["fail"]  # the marks still come first


def _previewed_then_committed(repo: Path, store: Path) -> str:
    base = _git(repo, "rev-parse", "HEAD").strip()
    _copy(DONE, repo)
    ctx = _preview_ctx(repo, DONE, git_facts(repo, base), store)  # the session's run, files not committed yet
    res, _ = run_check(SPEC.units["code"].gate, ctx)
    assert _named(res, "ts-code-verify") == ["pass"] and ctx.runs and all(not r.reused for r in ctx.runs), res.evidence
    _commit_all(repo)  # the workflow's commit script runs after the session
    return base


def _gate_after(repo: Path, store: Path, base: str) -> Any:
    ctx = _code_ctx(repo, DONE, git_facts(repo, base), store)
    res, _ = run_check(SPEC.units["code"].gate, ctx)
    return res


def test_the_gate_takes_the_previews_runs_though_the_files_were_committed_after_them(
        repo: Path, tmp_path_factory: pytest.TempPathFactory) -> None:  # AC 3, ts-code-session (CHK-B13)
    store = tmp_path_factory.mktemp("store") / "command_runs.jsonl"
    base = _previewed_then_committed(repo, store)
    res = _gate_after(repo, store, base)
    assert res.runs and all(r["reused"] is True for r in res.runs), res.evidence  # none started again
    assert _named(res, "ts-code-verify") == ["pass"] and _named(res, "ts-code-reuse") == ["pass"], res.evidence
    message = next(f.message for f in res.findings if f.criterion == "ts-code-reuse")
    counted = len(_counted(res.runs))
    assert message.startswith(f"{counted} of {counted} ")


@pytest.mark.parametrize("change", ["tracked", "untracked"])
def test_the_gate_runs_the_commands_again_when_a_file_changed_after_the_previews_run(
        change: str, repo: Path, tmp_path_factory: pytest.TempPathFactory) -> None:  # AC 4, ts-code-rerun (CHK-B13)
    store = tmp_path_factory.mktemp("store") / "command_runs.jsonl"
    (repo / "notes.txt").write_text("tracked before the run\n")  # a file the fixture does not rewrite
    _commit_all(repo, "notes")
    base = _previewed_then_committed(repo, store)
    if change == "tracked":
        (repo / "notes.txt").write_text("changed after the run\n")
    else:
        (repo / "late.txt").write_text("added after the run\n")
    res = _gate_after(repo, store, base)
    assert res.runs and all(r["reused"] is False for r in res.runs), res.evidence


def test_the_gates_evidence_says_for_each_command_whether_it_was_reused_or_run(
        repo: Path, tmp_path_factory: pytest.TempPathFactory) -> None:  # AC 5, ts-code-ran
    store = tmp_path_factory.mktemp("store") / "command_runs.jsonl"
    base = _git(repo, "rev-parse", "HEAD").strip()
    _copy(DONE, repo)
    _commit_all(repo)
    first, second = _gate_after(repo, store, base), _gate_after(repo, store, base)
    assert first.evidence.splitlines()[0] == "`git --version`: run", first.evidence
    assert second.evidence.splitlines()[0] == "`git --version`: reused", second.evidence
    assert first.evidence.index("`git --version`") < first.evidence.index("Changed paths since the run's base")
    assert next(f.message for f in first.findings if f.criterion == "ts-code-ran").startswith("0 of 1")
    assert next(f.message for f in second.findings if f.criterion == "ts-code-ran").startswith("1 of 1")
    # a command the allow list refuses is not started, and says so
    plan = tmp_path_factory.mktemp("refused") / "work"
    ctx = _code_ctx(plan, DONE)
    phases = plan / "phases.md"
    phases.write_text(phases.read_text().replace("- `git --version`\n", "- `git --version`\n- `node test.js`\n", 1))
    res, _ = run_check(SPEC.units["code"].gate, ctx)
    assert res.evidence.splitlines()[:2] == ["`git --version`: not run", "`node test.js`: not run"], res.evidence
    assert ctx.ran == []
    # the preview prints 2,000 characters of the evidence: the command lines come first, whatever the paths
    long_paths = tuple(f"src/package/module_{n:03d}/a_long_file_name_{n:03d}.py" for n in range(200))
    wide = _preview_ctx(tmp_path_factory.mktemp("wide") / "work", DONE, GitFacts(clean=False, changed_paths=long_paths))
    res, _ = run_check(SPEC.units["code"].gate, wide)
    assert "`git --version`: run" in res.evidence[:2000] and len(res.evidence) > 2000
    # the outcome gate's own use of `_verify` keeps returning findings
    found = checks._verify(_code_ctx(tmp_path_factory.mktemp("plain") / "work", DONE), fmt.Plan(commands=["git --version"]),
                           "ts-verify")
    assert [(f.status, f.criterion) for f in found] == [("pass", "ts-verify")]


# -- criteria about how the run works are checked, never judged (B30) ---------------------------------------

PROCESS = {"ts-dis-narrow": "discovery", "ts-plan-reading": "plan", "ts-code-once": "code", "ts-code-reuse": "code",
           "ts-code-preview": "code", "ts-code-previewed": "code", "ts-code-session": "code", "ts-code-rerun": "code",
           "ts-code-ran": "code"}  # AC 2, AC 3, AC 4, AC 5
# Words that put a criterion on what a judge cannot open: the step's prompt, its session or the gate's runs.
UNSEEN = re.compile(r"\b(prompts?|sessions?|command runs?|reused|run once|runs once)\b", re.I)


def test_criteria_about_how_the_run_works_are_checked_by_the_gate_not_a_judge() -> None:  # B30
    o = json.loads((ROOT / "outcome.json").read_text())
    by_id = {c["id"]: (u, c) for u, io in o["intermediate"].items() for c in io["criteria"]}
    for cid, unit in PROCESS.items():
        got_unit, c = by_id[cid]
        assert got_unit == unit and c["verified_by"] == "check", cid
        assert c["verifier"] == {"check": f"tgwf_temperspec.checks:{unit}_check"}, cid
    judged = [(u, c) for u, c in by_id.values() if c["verified_by"] == "judge"]
    judged += [("outcome", c) for c in o["final"] if c["verified_by"] == "judge"]
    assert judged
    for unit, c in judged:  # a judge reads the step's output and its references, nothing else
        assert not UNSEEN.search(c["text"] + " " + c.get("check_method", "")), (unit, c["id"])


def test_a_prompt_that_drops_an_instruction_fails_its_gate_check(tmp_path: Path,
                                                                 monkeypatch: pytest.MonkeyPatch) -> None:  # B30
    for cid in PROCESS:
        if cid in checks.PROMPT_SAYS:
            assert _named_list(checks._prompt_says(cid)) == ["pass"], cid
    prompts = tmp_path / "prompts"
    _copy(ROOT / "prompts", prompts)
    plan = prompts / "plan.md"
    plan.write_text(plan.read_text().replace("open another file only", "open any file"))
    monkeypatch.setattr(checks, "PROMPTS", prompts)
    got = checks._prompt_says("ts-plan-reading")
    assert [f.status for f in got] == ["fail"] and "open another file only" in got[0].message
    assert all(f.status == "pass" for f in checks._prompt_says("ts-code-once"))
    assert all(f.status == "pass" for f in checks._prompt_says("ts-code-preview"))
    code = prompts / "code.md"
    code.write_text(code.read_text().replace("the phases' own test runs stay plain commands", "run what you like"))
    dropped = checks._prompt_says("ts-code-preview")  # AC 2, ts-code-preview
    assert [f.status for f in dropped] == ["fail"] and "stay plain commands" in dropped[0].message
    code.unlink()
    assert [f.status for f in checks._prompt_says("ts-code-once")] == ["fail"]


def test_the_code_gate_names_its_process_criteria_on_a_finished_plan(tmp_path: Path) -> None:  # B30
    res, _ = run_check(SPEC.units["code"].gate, _code_ctx(tmp_path, DONE))
    assert _named(res, "ts-code-once") == ["pass"], res.evidence
    assert _named(res, "ts-code-reuse") == ["n_a"]  # no store outside a run
    assert _named(res, "ts-code-preview") == ["pass"] and _named(res, "ts-code-ran") == ["pass"]  # AC 2, AC 5
    for cid in ("ts-code-previewed", "ts-code-session", "ts-code-rerun"):  # the session's own run is not visible here
        assert _named(res, cid) == ["n_a"], cid
        assert "tests prove" in next(f.message for f in res.findings if f.criterion == cid), cid


def _named_list(found: list[Any]) -> list[str]:
    return [f.status for f in found]


# -- a verification command run in a folder, as CLAUDE.md writes it (B31) -------------------------------------


@pytest.mark.parametrize("command", ["cd sub/engine && python -m pytest", "cd sub/engine && python3 -m pytest",
                                     "cd sub/engine && ruff check src tests", "python -m pytest -q"])
def test_the_plan_check_takes_a_command_run_in_a_folder(command: str, tmp_path: Path) -> None:
    # B31, ts-plan-form, ts-exp-commands
    files = _copy(ROOT / "evals" / "checks" / "plan" / "must-pass" / "2-simple", tmp_path)
    (tmp_path / "sub" / "engine").mkdir(parents=True)
    (tmp_path / "tempergraph.commands.json").write_text(json.dumps(
        {"schema_version": 1, "commands": ["python -m pytest", "python3 -m pytest", "ruff check"]}))
    plan = tmp_path / "plan.md"
    plan.write_text(plan.read_text().replace("`git --version`", f"`{command}`"))
    artifacts = {OWNER[f.stem]: {f.stem: f.relative_to(tmp_path).as_posix()} for f in files if f.stem in OWNER}
    res, _ = run_check(SPEC.units["plan"].gate, _context("plan", tmp_path, artifacts))
    assert _named(res, "ts-plan-form") == ["pass"], res.evidence


@pytest.mark.parametrize(("command", "said"), [
    ("cd sub && node test.js", "tempergraph.commands.json"),
    ("cd sub && pytest | tee out", "the one chain allowed"),
    ("cd ../elsewhere && pytest", "inside the repository"),
    ("cd sub && git push -u origin main", "only the last stage"),
])
def test_a_refused_command_is_told_how_to_write_it_without_dropping_the_cd(command: str, said: str,
                                                                          tmp_path: Path) -> None:  # B31
    (tmp_path / "tempergraph.commands.json").write_text(json.dumps({"schema_version": 1, "commands": ["pytest"]}))
    found =checks._commands(_context("plan", tmp_path, {}), fmt.Plan(commands=[command]), "ts-plan-form")
    assert len(found) == 1 and found[0].status == "fail", command
    assert said in found[0].message + " " + found[0].fix, (command, found[0])
    assert "no `&&` chain" not in found[0].fix


# -- the short discovery visit (decision record `short-discovery-visit`, B21) ---------------------------------------------------

SHORT_CHECKS = ROOT / "evals" / "checks" / "discovery_short"


def _short(fixture: Path, work: Path, **values: str) -> Any:
    _copy(fixture, work)
    ctx = _context("discovery_short", work, {"discovery_short": {"handoff": "handoff.md"},
                                             "triage": {"triage_note": "triage_note.md"}},
                   {"discovery_short": values} if values else None)
    return run_check(SPEC.units["discovery_short"].gate, ctx)[0]


def test_the_short_visit_is_a_second_discovery_step_with_its_own_sizing() -> None:
    short, full = SPEC.units["discovery_short"], SPEC.units["discovery"]
    assert short.step is not None and full.step is not None
    assert SPEC.order.index("triage") < SPEC.order.index("discovery_short") < SPEC.order.index("discovery")
    assert short.step.model == full.step.model  # the same tier; only the effort differs
    assert (short.step.session_options.effort, full.step.session_options.effort) == ("high", "max")
    assert short.gate.judge is not None and short.gate.judge.session_options.effort == "high"
    assert "handoff" in short.step.produces and "handoff" in full.step.produces
    assert not {"edit", "web_search", "web_fetch"} & set(short.step.tools)  # it writes the hand-off only
    for unit in ("plan", "expand", "code"):  # every return to discovery goes to the full visit
        assert "discovery_short" not in SPEC.units[unit].gate.back_targets


@pytest.mark.parametrize("fixture", sorted((SHORT_CHECKS / "must-pass").iterdir()), ids=lambda p: p.name)
def test_the_short_check_passes_a_settled_and_a_handed_on_visit(fixture: Path, tmp_path: Path) -> None:
    res = _short(fixture, tmp_path)
    assert res.result == "PASS", res.evidence
    assert _named(res, "ts-dsh-cited") == ["pass"] and _named(res, "ts-dsh-only") == ["pass"]
    assert _named(res, "ts-dsh-reading") == (["n_a"] if "not-covered" in fixture.name else ["pass"])


@pytest.mark.parametrize(("name", "criterion"), [("wrote-a-spec", "ts-dsh-only"),
                                                 ("cited-id-missing", "ts-dsh-cited"),
                                                 ("long-reading-list", "ts-dsh-reading")])
def test_the_short_check_fails_what_the_short_visit_may_not_do(name: str, criterion: str, tmp_path: Path) -> None:
    res = _short(SHORT_CHECKS / "must-fail" / name, tmp_path)
    assert res.result == "FAIL" and "fail" in _named(res, criterion), res.evidence


def test_the_settled_value_follows_the_not_covered_lines(tmp_path: Path) -> None:
    settled, handed = SHORT_CHECKS / "must-pass" / "1-settled", SHORT_CHECKS / "must-pass" / "2-not-covered"
    assert _named(_short(settled, tmp_path / "a", settled="yes"), "ts-dsh-settled") == ["pass"]
    assert _named(_short(settled, tmp_path / "b", settled="no"), "ts-dsh-settled") == ["fail"]
    assert _named(_short(handed, tmp_path / "c", settled="no"), "ts-dsh-settled") == ["pass"]
    assert _named(_short(handed, tmp_path / "d", settled="yes"), "ts-dsh-settled") == ["fail"]


def test_the_short_prompt_states_the_reading_limit_and_reads_narrowly() -> None:
    text = " ".join((ROOT / "prompts" / "discovery_short.md").read_text(encoding="utf-8").split()).lower()
    assert "read at most 10 files" in text and "not covered" in text and "settled" in text
    assert checks.SHORT_READING_MAX == 10
    assert [f.status for f in checks._prompt_says("ts-dsh-limit")] == ["pass"]
    assert all(f.status == "pass" for f in checks._prompt_says("ts-dis-narrow"))  # both discovery prompts


# -- the outcome gate asks only about what the run changed (B22, ts-spec-links) -------------------------------

SPEC_V1 = """# Config file

## Purpose

The tool reads `tool.toml`.

## Behaviours

### CFG-B1 A missing config file is reported

WHEN the tool starts and `tool.toml` does not exist THE tool SHALL print one line that names the file.

- GIVEN no `tool.toml` WHEN the tool starts THEN one line names it

### CFG-B2 A missing config file ends the run

WHEN the tool starts and `tool.toml` does not exist THE tool SHALL exit with code 2.

- GIVEN no `tool.toml` WHEN the tool starts THEN the exit code is 2

## Acceptance criteria

- CFG-AC1 (CFG-B1): Started with no `tool.toml`, the tool prints one line that names it
- CFG-AC2 (CFG-B2): Started with no `tool.toml`, the tool exits with code 2
"""


def _edited(repo: Path, change: Any) -> Any:
    spec = repo / "docs" / "specs" / "config-file.spec.md"
    spec.parent.mkdir(parents=True, exist_ok=True)
    spec.write_text(SPEC_V1)
    _git(repo, "add", "-A")
    _git(repo, "-c", "user.name=t", "-c", "user.email=t@example.invalid", "commit", "-q", "-m", "base")
    base = _git(repo, "rev-parse", "HEAD").strip()
    spec.write_text(change(SPEC_V1))
    ctx = _context("outcome", repo, {}, git=GitFacts(base=base, changed_paths=("docs/specs/config-file.spec.md",)))
    return checks._traced(ctx, ["docs/specs/config-file.spec.md"], [])


def test_a_spec_edited_only_to_add_a_link_asks_no_test_of_its_old_criteria(repo: Path) -> None:  # B22
    got = _edited(repo, lambda t: t.replace("reads `tool.toml`.", "reads `tool.toml` ([cli](cli.spec.md))."))
    assert [f.status for f in got] == ["n_a"], got


def test_the_outcome_gate_asks_tests_of_added_reworded_and_re_behaved_criteria(repo: Path) -> None:  # B22
    def change(t: str) -> str:
        t = t.replace("exit with code 2.", "exit with code 3.")  # CFG-B2 changed, so CFG-AC2 is asked again
        return t + "- CFG-AC3 (CFG-B1): The line goes to standard error\n"
    got = _edited(repo, change)
    assert sorted(f.message.split()[0] for f in got if f.status == "fail") == ["CFG-AC2", "CFG-AC3"], got


def test_without_a_base_every_criterion_of_an_edited_spec_is_asked(tmp_path: Path) -> None:  # B22
    (tmp_path / "s.spec.md").write_text(SPEC_V1)
    got = checks._traced(_context("outcome", tmp_path, {}), ["s.spec.md"], [])
    assert sorted(f.message.split()[0] for f in got) == ["CFG-AC1", "CFG-AC2"]


def test_spec_links_read_the_edited_specs_not_the_task_notes(tmp_path: Path) -> None:  # ts-spec-links
    (tmp_path / "docs" / "specs").mkdir(parents=True)
    (tmp_path / "docs" / "specs" / "config-file.spec.md").write_text(SPEC_V1)
    (tmp_path / "docs" / "tasks").mkdir()
    (tmp_path / "docs" / "tasks" / "T.handoff.md").write_text("Retired CFG-B9 and CFG-AC9 on purpose.\n")
    git = GitFacts(changed_paths=("docs/specs/config-file.spec.md", "docs/tasks/T.handoff.md"))
    ctx = _context("outcome", tmp_path, {}, git=git)
    ctx.settings = {"deliverables": [], "outcome_check": SPEC.outcome.check.ref}  # type: ignore[union-attr]
    res, _ = run_check(outcome_unit(SPEC).gate, ctx)  # type: ignore[union-attr]
    assert _named(res, "ts-spec-links") == ["pass"], res.evidence


# -- an escaped pipe stays in its table cell (B40) ------------------------------------------------------------


def test_an_escaped_pipe_stays_in_its_cell() -> None:  # B40
    text = (ROOT / "evals" / "checks" / "plan" / "must-pass" / "2-simple" / "plan.md").read_text()
    row = "| 1.3 | code | R2 | `src/tool/config.py` | | Report the missing file and exit with code 2 | |"
    assert row in text
    plan = fmt.parse_plan(text.replace(row, row.replace("exit with code 2", "return `Path \\| None`")))
    got = next(r for r in plan.rows if r.id == "1.3")
    assert not got.completed and "`Path | None`" in got.change, got
    assert fmt._cells("| a \\| b | c |") == ["a | b", "c"]


# -- open questions that do not block planning do not pause the run (B41) -------------------------------------


def test_judges_leave_gap_false_for_open_questions_that_do_not_block() -> None:  # B41
    for name in ("discovery", "discovery_short", "plan", "expand", "code"):
        text = " ".join((ROOT / "judges" / f"{name}.md").read_text(encoding="utf-8").split())
        assert "does not block planning" in text and "leave `gap` false" in text, name
        assert "Set `gap` only when a file or fact you need" in text, name


# -- the prompts say which commands the shell takes (B24) -----------------------------------------------------


def test_the_prompts_name_the_shell_command_shapes() -> None:  # B24
    code = " ".join((ROOT / "prompts" / "code.md").read_text(encoding="utf-8").split())
    for shape in ("`cd sub/pkg && python3 -m pytest tests/test_x.py -q`", "pipes, `;`, a second `&&`",
                  "`2>&1`", "`env`", "inline `python -c`", "with the file tools instead"):
        assert shape in code, shape
    for name in ("triage", "discovery", "discovery_short", "plan", "expand", "setup"):
        unit = SPEC.units[name]
        assert unit.step is not None and "shell" not in unit.step.tools, name
        assert "This step has no shell" in (ROOT / "prompts" / f"{name}.md").read_text(encoding="utf-8"), name


# -- the block prepare writes is not a change the code step must account for (B19 family) ---------------------


def test_the_context_block_prepare_wrote_is_listed_apart_from_the_changed_paths(repo: Path) -> None:
    (repo / "CLAUDE.md").write_text("# Project\n\nRun the tests with pytest.\n")
    _git(repo, "add", "-A")
    _git(repo, "-c", "user.name=t", "-c", "user.email=t@example.invalid", "commit", "-q", "-m", "base")
    base = _git(repo, "rev-parse", "HEAD").strip()
    routing.write_context(repo)  # what prepare does before any step
    git = GitFacts(base=base, changed_paths=("CLAUDE.md", "src/a.py"))
    res = checks._result(_context("code", repo, {}, git=git), [])
    assert "Changed paths since the run's base: src/a.py" in res.evidence
    assert "Written by prepare (the temperspec block only, no step's change): CLAUDE.md" in res.evidence
    (repo / "CLAUDE.md").write_text((repo / "CLAUDE.md").read_text() + "\nA line a step added.\n")
    res = checks._result(_context("code", repo, {}, git=git), [])
    assert "Changed paths since the run's base: CLAUDE.md, src/a.py" in res.evidence  # a step's edit counts
    assert "Written by prepare" in (ROOT / "judges" / "code.md").read_text()
