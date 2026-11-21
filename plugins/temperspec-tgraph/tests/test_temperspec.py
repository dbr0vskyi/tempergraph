"""The package's own tests: the final checks on their fixtures, the judge seeds against the gate checks, the
rule files against the format module, and the scripts and the last stage on a scratch repository."""

from __future__ import annotations

import importlib
import json
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
               ("triage", "discovery", "plan", "expand"))


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
    if gate != "triage":
        artifacts.setdefault("discovery", {})["handoff"] = "docs/tasks/TASK-7.handoff.md"
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
    assert fmt.headings_missing(_example(rule, "# Hand-off:"), fmt.HANDOFF_HEADINGS) == []
    report = _example(rule, "# Code report:")
    assert fmt.headings_missing(report, fmt.REPORT_HEADINGS) == []
    assert fmt.parse_report(report) == {"1.1": "done", "1.2": "done"}
    for route in fmt.ROUTES:
        assert f"`{route}`" in rule


def test_the_documents_rule_names_every_suffix() -> None:
    rule = _rule("documents")
    for folder, suffix in fmt.SUFFIX_BY_FOLDER.items():
        assert f"`docs/{folder}/`" in rule and f"`{suffix}`" in rule


# -- routes, scripts and the last stage -------------------------------------------------------------------


def _view(**values: str) -> Any:
    return SimpleNamespace(values=values)


def test_routes_follow_the_values() -> None:
    assert routing.route_triage(_view(route="plan")) == "plan"
    assert routing.route_triage(_view(route="discovery")) == "discovery"
    assert routing.route_triage(_view()) == "discovery"  # an unreadable route takes the longer path
    assert routing.route_discovery(_view(route="discovery-only")) == "finalizer"
    assert routing.route_discovery(_view(route="discovery")) == "plan"
    assert routing.route_plan(_view(complexity="complex")) == "expand"
    assert routing.route_plan(_view(complexity="simple")) == "code"


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
        assert unit.step is not None and unit.step.model == "medium", name
        assert unit.gate.judge is not None and unit.gate.judge.model == "medium", name
    assert outcome_unit(SPEC).gate.judge.model == "medium"  # type: ignore[union-attr]
    assert SPEC.units["discovery"].step.session_options.effort == "max"  # type: ignore[union-attr]
