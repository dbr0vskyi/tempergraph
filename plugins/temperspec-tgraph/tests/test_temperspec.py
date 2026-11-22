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
from tempergraph.run.commands import CommandRun
from tempergraph.run.outcome import outcome_unit

ROOT = Path(__file__).resolve().parents[1]
SPEC = load_package(ROOT).spec
checks = importlib.import_module("tgwf_temperspec.checks")
routing = importlib.import_module("tgwf_temperspec.routing")
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
               ("setup", "triage", "discovery", "plan", "expand"))


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


def test_routes_follow_the_values() -> None:
    assert routing.route_triage(_view(route="plan")) == "plan"
    assert routing.route_triage(_view(route="discovery")) == "discovery"
    assert routing.route_triage(_view(route="quick")) == "code"
    assert routing.route_triage(_view()) == "discovery"  # an unreadable route takes the longer path
    assert routing.route_discovery(_view(route="discovery-only")) == "finalizer"
    assert routing.route_discovery(_view(route="discovery")) == "plan"
    assert routing.route_plan(_view(complexity="complex")) == "expand"
    assert routing.route_plan(_view(complexity="simple")) == "code"


def test_setup_runs_only_for_a_repository_with_no_overview_spec() -> None:
    assert routing.route_setup(SimpleNamespace(artifact_keys=("setup_needed",))) == "setup"
    assert routing.route_setup(SimpleNamespace(artifact_keys=("setup_ready",))) == "triage"
    assert SPEC.order[:4] == ("prepare", "setup_route", "setup", "triage")


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


def test_every_step_and_judge_states_its_model_effort_and_reason() -> None:  # decision record 0002
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
    assert efforts == {"setup": ("high", "medium"), "triage": ("medium", "medium"), "discovery": ("max", "high"),
                       "plan": ("high", "high"), "expand": ("medium", "medium"), "code": ("high", "high")}


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
    assert got.outcome == "opened" and ctx.ran[-1].endswith(f"--body-file {tmp_path / '.out' / 'pull-request.md'}")
    body = (tmp_path / ".out" / "pull-request.md").read_text()
    assert "1. An idle session is refused" in body and "`docs/specs/session.spec.md`" in body
    assert "added: SES-B2 Idle expiry" in body and "added: SES-AC2 (SES-B2)" in body and "prose" not in body
    assert "Idle time counts from the last request" in body and "Open questions" not in body
    assert "`src/auth/clock.py` was needed for the test" in body and ".claude/rules" not in body


def test_a_reused_pull_request_gets_the_new_description(tmp_path: Path) -> None:
    (tmp_path / "note.md").write_text("## Acceptance criteria\n\n1. One\n")
    ctx = _Summary(tmp_path, {"git remote": (0, "origin\n"), "git push": (0, ""), "gh pr edit": (0, ""),
                              "gh pr list": (0, '[{"url":"https://github.com/acme/tool/pull/9"}]\n')}, {})
    got = routing.finalize(ctx)
    assert got.outcome == "reused" and "not updated" not in got.reason
    assert ctx.ran[-1].startswith("gh pr edit https://github.com/acme/tool/pull/9 --body-file ")


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


def test_the_code_prompt_runs_a_phases_test_files_and_the_full_commands_once() -> None:  # AC 2, ts-code-once
    text = " ".join((ROOT / "prompts" / "code.md").read_text(encoding="utf-8").split())
    assert "After each phase, run only the test files that the phase's rows name" in text
    assert "never the whole suite" in text
    assert "run each verification command of the plan once, after the last phase and before you write the report" in text
    assert "in the quick lane, the note's `Verify` commands once, after the last criterion" in text


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
        return list(res.runs)

    first, second = gate_run(), gate_run()  # a retry, or a later visit, on the same tree and the same store
    assert first and all(r["reused"] is False and r["exit_code"] == 0 for r in first)
    assert len(second) == len(first) and all(r["reused"] is True for r in second)  # none was started again
    (repo / "notes.txt").write_text("changed\n")  # a changed tree changes the key: the commands run again
    third = gate_run()
    assert third and all(r["reused"] is False for r in third)
