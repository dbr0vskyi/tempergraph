"""The route after the plan is the engine's complexity switch `code_mode` (spec `code-mode.spec.md`, CDM-B1 to CDM-B11):
the facts the plan check records, the rules file, the arms on scripted runs, the operator's arm, the report by arm and
the live-check row."""

from __future__ import annotations

import dataclasses
import importlib
import io
import json
import re
import subprocess
import time
from collections.abc import Callable
from pathlib import Path
from typing import Any

import pytest

from tempergraph.api import Gate, Judge
from tempergraph.catalog import Catalog
from tempergraph.cli.main import main
from tempergraph.constants import ExitCode
from tempergraph.contracts import CheckResult, Criterion, SessionRequest, SessionResult
from tempergraph.executors.capabilities import DECLARED
from tempergraph.executors.registry import Registry
from tempergraph.executors.standins import answer, standin
from tempergraph.model.validate import validate
from tempergraph.observe import switch_report as swr
from tempergraph.package.loader import load_package
from tempergraph.run import complexity
from tempergraph.run.checks import CheckContext, GitFacts, run_check
from tempergraph.run.log import RunLog
from tempergraph.run.runner import RunSettings, start
from tempergraph.store.layout import run_dir, state_root_path

ROOT = Path(__file__).resolve().parents[1]
SPEC = load_package(ROOT).spec
checks = importlib.import_module("tgwf_temperspec.checks")
fmt = importlib.import_module("tgwf_temperspec.specfmt")
OWNER = {key: unit for unit in SPEC.order for key in (SPEC.units[unit].step.produces if SPEC.units[unit].step else {})}
FACTS = ("phases", "rows", "test_rows", "files", "commands", "reading_bytes", "heavy_phases")
PLANS = ROOT / "evals" / "checks" / "plan"


def _copy(src: Path, dst: Path) -> list[Path]:
    out = []
    for f in sorted(p for p in src.rglob("*") if p.is_file()):
        target = dst / f.relative_to(src)
        target.parent.mkdir(parents=True, exist_ok=True)
        target.write_bytes(f.read_bytes())
        out.append(target)
    return out


def _context(unit: str, work: Path, artifacts: dict[str, dict[str, str]],
             values: dict[str, Any] | None = None) -> CheckContext:
    return CheckContext(unit=unit, workdir=work, request={}, artifacts=artifacts, values=values or {},
                        git=GitFacts(), allow=SPEC.allow_commands, out_dir=work.parent / f"{work.name}.out",
                        deadline_at=time.monotonic() + 60)


def _plan_facts(work: Path) -> dict[str, str]:
    """The facts the plan check records for the `plan.md` and `triage_note.md` written in `work`."""
    artifacts = {"plan": {"plan": "plan.md"}, "triage": {"triage_note": "triage_note.md"}}
    res, _ = run_check(SPEC.units["plan"].gate, _context("plan", work, artifacts))
    return dict(res.facts)


def _counted(plan_text: str, work: Path) -> dict[str, int]:
    """What the test counts by itself from the parsed plan and the sizes of the files and specs the rows name."""
    plan = fmt.parse_plan(plan_text)
    named = {r.file for r in plan.rows if r.file} | set(plan.specs)
    size = sum((work / n).stat().st_size for n in named if (work / n).is_file())
    return {"phases": len(plan.phases), "rows": len(plan.rows), "test_rows": sum(r.kind == "test" for r in plan.rows),
            "files": len({r.file for r in plan.rows if r.file}), "commands": len(plan.commands),
            "reading_bytes": size, "heavy_phases": len(plan.heavy)}


FIXTURES = ["must-pass/1-complex", "must-pass/2-simple", "must-fail/simple-with-heavy-phase"]


@pytest.mark.parametrize("fixture", FIXTURES)
def test_the_plan_check_records_the_seven_facts_of_each_plan_fixture(fixture: str, tmp_path: Path) -> None:
    # AC 1, CDM-AC3 (CDM-B2)
    _copy(PLANS / fixture, tmp_path)
    got = _plan_facts(tmp_path)
    assert set(FACTS) <= set(got), got
    want = _counted((tmp_path / "plan.md").read_text(encoding="utf-8"), tmp_path)
    assert {k: int(got[k]) for k in FACTS} == want
    if fixture == "must-pass/2-simple":
        assert [want[k] for k in FACTS] == [1, 4, 2, 3, 1, 0, 0]


def _plan(phases: list[tuple[str, str, list[tuple[str, str]]]], commands: tuple[str, ...] = ("git --version",),
          specs: str = "[]") -> str:
    """A plan of the plan rule's shape: phases of (name, weight, rows of (kind, file))."""
    out = [f"---\ntask: T-1\ncomplexity: complex\nstatus: planned\nspecs: {specs}\n---\n", "# Plan: a goal\n",
           "## 0. Hand-off\n\n- Triage note: `triage_note.md`\n- Why this design: one place.\n",
           "## 1. Requirements\n\n| Req | Criteria | Statement | Spec ids |\n|---|---|---|---|\n"
           "| R1 | AC 1 | One line names the file | |\n", "## 2. Phases\n"]
    n = 0
    for i, (name, weight, rows) in enumerate(phases, 1):
        out.append(f"### Phase {i}: {name}\n\nGoal: {name} is in place.\nWeight: {weight}\n")
        if rows:
            out.append("| Row | Kind | Req | File | Proves | Change | Completed |\n|---|---|---|---|---|---|---|")
            for kind, file in rows:
                n += 1
                proves = "AC 1" if kind == "test" else ""
                out.append(f"| {i}.{n} | {kind} | R1 | `{file}` | {proves} | A change of {file} | |")
            out.append("")
    out.append("## 3. Verification\n\n" + "\n".join(f"- `{c}`" for c in commands) + "\n")
    out.append("## 4. Docs to update\n\n- None\n")
    return "\n".join(out)


def _written(work: Path, plan_text: str, sizes: dict[str, int] | None = None) -> None:
    (work / "plan.md").write_text(plan_text, encoding="utf-8")
    (work / "triage_note.md").write_text(
        "# Triage: T-1\n\n## Task\n\nA task.\n\n## Acceptance criteria\n\n1. One line names the file\n\n"
        "## Existing documents\n\n- None\n\n## Gaps\n\n- None\n\n## Route\n\n- Deliver: code\n- Route: plan\n",
        encoding="utf-8")
    for name, size in (sizes or {}).items():
        (work / name).parent.mkdir(parents=True, exist_ok=True)
        (work / name).write_bytes(b"x" * size)


EIGHT_ROWS = [("test", "tests/a.py"), ("test", "tests/a.py"), ("code", "src/a.py"), ("docs", "docs/a.md")]
EIGHT_MORE = [("test", "tests/b.py"), ("test", "tests/b.py"), ("code", "src/b.py"), ("docs", "docs/b.md")]


def test_the_facts_of_a_plan_with_no_rows_and_of_plans_with_heavy_phases_and_reading_bytes(tmp_path: Path) -> None:
    # AC 1, CDM-AC4 (CDM-B2)
    five = _plan([(f"Part {i}", "light", []) for i in range(1, 6)])
    (tmp_path / "a").mkdir()
    _written(tmp_path / "a", five)
    got = _plan_facts(tmp_path / "a")
    assert {k: int(got[k]) for k in FACTS} == {"phases": 5, "rows": 0, "test_rows": 0, "files": 0, "commands": 1,
                                               "reading_bytes": 0, "heavy_phases": 0}
    assert fmt.simple_overruns(fmt.parse_plan(five)) == ["phases 5 > 3"]

    (tmp_path / "b").mkdir()
    heavy = _plan([("Restructure", "heavy (refactor)", []), ("Tests", "heavy (many-tests)", []),
                   ("Docs", "light", [])])
    _written(tmp_path / "b", heavy)
    assert int(_plan_facts(tmp_path / "b")["heavy_phases"]) == 2

    (tmp_path / "c").mkdir()
    sized = _plan([("One", "light", EIGHT_ROWS), ("Two", "light", EIGHT_MORE)], commands=("git --version", "git status"))
    _written(tmp_path / "c", sized, {"src/a.py": 40_000, "src/b.py": 50_000})
    got = _plan_facts(tmp_path / "c")
    assert [int(got[k]) for k in FACTS] == [2, 8, 4, 6, 2, 90_000, 0]
    assert fmt.simple_overruns(fmt.parse_plan(sized)) == []

    (tmp_path / "d").mkdir()
    big = _plan([("One", "light", [("test", "tests/a.py"), ("code", "src/big.py")])])
    _written(tmp_path / "d", big, {"src/big.py": 300_000})
    assert int(_plan_facts(tmp_path / "d")["reading_bytes"]) == 300_000
    assert fmt.simple_overruns(fmt.parse_plan(big), 300_000) == ["reading_bytes 300000 > 200000"]


# -- the rules file and the declaration -------------------------------------------------------------------------


def _rules() -> dict[str, Any]:
    return json.loads((ROOT / "routing" / "code_mode.json").read_text(encoding="utf-8"))


def test_the_bounds_of_single_are_the_plan_rules_limits() -> None:
    # AC 3, CDM-AC7 (CDM-B4)
    rules = _rules()
    when = rules["arms"]["single"]["when"]
    assert set(rules["arms"]) == {"single"}, "the safe arm `phases` takes no bounds"
    assert {k: v["max"] for k, v in when.items()} == {
        "phases": 3, "rows": 12, "test_rows": 6, "files": 10, "commands": 3, "reading_bytes": 200_000,
        "heavy_phases": 0}
    for key, limit in fmt.SIMPLE_MAX.items():
        assert when[key] == {"max": limit}
    rule = (ROOT / "rules" / "plan.rule.md").read_text(encoding="utf-8")
    labels = {"Phases": "phases", "Task rows": "rows", "Test rows": "test_rows", "Files named by rows": "files",
              "Verification commands": "commands"}
    for label, key in labels.items():
        assert f"| {label} | at most {when[key]['max']} |" in rule
    assert f"| Bytes of the files and specs the rows name | at most {when['reading_bytes']['max']:,} |" in rule
    assert "| A heavy phase | none |" in rule and when["heavy_phases"] == {"max": 0}


def test_the_rules_declare_no_margin_and_the_switch_no_exploration_or_rearm() -> None:
    # AC 3, CDM-AC8 (CDM-B4)
    rules = _rules()
    assert rules["schema_version"] == 1 and "margin" not in rules
    comp = SPEC.units["code_mode"].switch.complexity  # type: ignore[union-attr]
    assert comp is not None and comp.explore is None and comp.rules is None and comp.size == "phases"
    assert SPEC.units["code_mode"].switch.rearm == ()  # type: ignore[union-attr]
    assert SPEC.units["code_mode"].switch.mode == "route"  # type: ignore[union-attr]


def test_the_workflow_validates_and_declares_the_switch() -> None:
    # AC 1, AC 3, CDM-AC1 (CDM-B1)
    assert [f for f in validate(SPEC, DECLARED) if f.severity == "error"] == []
    switch = SPEC.units["code_mode"].switch
    assert switch is not None and list(switch.arms) == ["single", "phases"] and switch.default == "phases"
    assert dict(switch.arms) == {"single": "code", "phases": "expand"}
    here = SPEC.order.index("plan")
    assert SPEC.order[here:here + 5] == ("plan", "code_mode", "expand", "code", "code_join")
    assert SPEC.units["plan"].route is None and SPEC.units["plan"].route_targets == ()
    blueprint = json.loads((ROOT / "blueprint.json").read_text(encoding="utf-8"))
    assert "plan" not in blueprint["flow"]
    assert blueprint["flow"]["code_mode"]["switch"] == {"arms": {"single": "code", "phases": "expand"},
                                                        "default": "phases"}
    kinds = {u["name"]: u["kind"] for u in blueprint["units"]}
    assert kinds["code_mode"] == "switch" and kinds["code_join"] == "script"


# -- scripted runs of the package's own units --------------------------------------------------------------------


@pytest.fixture
def repo(tmp_path: Path) -> Path:
    root = tmp_path / "repo"
    root.mkdir()
    for args in (("init", "-q", "-b", "main"), ("config", "user.email", "t@example.invalid"),
                 ("config", "user.name", "Test")):
        subprocess.run(["git", *args], cwd=root, check=True, capture_output=True)
    (root / "README.md").write_text("scratch\n", encoding="utf-8")
    subprocess.run(["git", "add", "README.md"], cwd=root, check=True, capture_output=True)
    subprocess.run(["git", "commit", "-q", "-m", "init"], cwd=root, check=True, capture_output=True)
    return root


def counted_check(ctx: Any) -> CheckResult:
    """The plan check as far as the switch is concerned: it counts the written plan and records the seven facts."""
    plan = fmt.parse_plan((Path(ctx.workdir) / "plan.md").read_text(encoding="utf-8"))
    facts = fmt.plan_facts(plan, checks._reading_bytes(ctx, plan))
    return CheckResult(result="PASS", evidence="counted", facts={k: str(v) for k, v in facts.items()})


def silent_check(ctx: Any) -> CheckResult:
    """A plan check that records no fact."""
    return CheckResult(result="PASS", evidence="counted")


UNITS = ("triage", "plan", "code_mode", "expand", "code", "code_join")


def _scripted(check: Callable[..., Any]) -> Any:
    """The package's own units, each step with one-line prompt and an empty gate, the plan's gate with `check`."""
    units: dict[str, Any] = {}
    for name in UNITS:
        unit = SPEC.units[name]
        if unit.step is not None:
            step = dataclasses.replace(unit.step, prompt="Do it.", after=(), self_check=False)
            gate = Gate(check=check if name == "plan" else None, judge=Judge(stance="Verify."),
                        criteria=[Criterion(id=f"c-{name}", text="The output is good",
                                            check_method="Read the file and compare", severity="blocker")])
            unit = dataclasses.replace(unit, step=step, gate=gate,
                                       route_targets=tuple(t for t in unit.route_targets if t in UNITS))
        units[name] = unit
    return dataclasses.replace(SPEC, order=UNITS, units=units, flow={}, outcome=None, finalizer=None,
                               finalizer_outcomes=())


MET = ("Reviewed.\n```json\n" + json.dumps({"criteria": [{"n": 1, "status": "MET", "evidence": "notes.md:1 shows it",
                                                          "defect_in": None, "no_change": False}],
                                           "gap": False, "confidence": 0.8}) + "\n```")


def _said(text: str, sid: str) -> SessionResult:
    return answer(text, session_id=sid)


def _triage(route: str = "plan") -> Callable[[SessionRequest], SessionResult]:
    def run(req: SessionRequest) -> SessionResult:
        (req.workdir / "triage_note.md").write_text("# Triage: T-1\n", encoding="utf-8")
        return _said(f"Triaged.\nARTIFACT triage_note: triage_note.md\nARTIFACT gaps: none\nARTIFACT route: {route}", "t")
    return run


def _planner(text: str, sizes: dict[str, int] | None = None) -> Callable[[SessionRequest], SessionResult]:
    def run(req: SessionRequest) -> SessionResult:
        (req.workdir / "plan.md").write_text(text, encoding="utf-8")
        for name, size in (sizes or {}).items():
            (req.workdir / name).parent.mkdir(parents=True, exist_ok=True)
            (req.workdir / name).write_bytes(b"x" * size)
        return _said("Planned.\nARTIFACT plan: plan.md\nARTIFACT complexity: simple", "p")
    return run


def _expander(req: SessionRequest) -> SessionResult:
    (req.workdir / "phases.md").write_text("rows\n", encoding="utf-8")
    return _said("Expanded.\nARTIFACT phases: phases.md", "e")


def _coder(req: SessionRequest) -> SessionResult:
    (req.workdir / "report.md").write_text("done\n", encoding="utf-8")
    return _said("Coded.\nARTIFACT code_report: report.md\nARTIFACT tests_passed: yes", "c")


def _run(repo: Path, steps: list[Any], check: Callable[..., Any] = counted_check, task: str = "C-1",
         **settings: Any) -> Any:
    registry = Registry()
    registry.register(standin("claude", steps=list(steps), judges=[answer(MET, tools=("Read",), session_id="j")
                                                                   for _ in steps]))
    return start(_scripted(check), task, {"request": "x"}, repo, registry,
                 RunSettings(sleep=lambda s: None, **settings))


def _records(repo: Path, kind: str, task: str = "C-1") -> list[dict[str, Any]]:
    path = run_dir(state_root_path(repo), SPEC.name, task) / "run.jsonl"
    return [r for r in map(json.loads, path.read_text(encoding="utf-8").splitlines()) if r["kind"] == kind]


def _entered(repo: Path, task: str = "C-1") -> list[str]:
    """The units entered, with the join unit `code_join` (a script unit, which the engine records as a `script` run)
    last when it ran."""
    return [r["unit"] for r in _records(repo, "unit_entered", task)] + [
        r["unit"] for r in _records(repo, "script", task) if r["unit"] == "code_join"]


def _routes(repo: Path, task: str = "C-1") -> list[dict[str, Any]]:
    return [r for r in _records(repo, "route", task) if r.get("unit") == "code_mode"]


SIMPLE = _plan([("One", "light", [("test", "tests/a.py"), ("code", "src/a.py")])])
FIVE = _plan([(f"Part {i}", "light", []) for i in range(1, 6)])
SINGLE = [_triage(), _planner(SIMPLE), _coder]
PHASES = [_triage(), _planner(FIVE), _expander, _coder]


def test_a_run_records_one_route_with_the_switch_the_arm_the_zone_and_the_seven_measures(repo: Path) -> None:
    # AC 1, CDM-AC2 (CDM-B1)
    out = _run(repo, SINGLE)
    assert out.exit_code is ExitCode.FINISHED, out.message
    (route,) = _routes(repo)
    assert (route["unit"], route["arm"], route["zone"], route["chosen_by"]) == ("code_mode", "single", "simple",
                                                                               "predicate")
    assert route["measures"] == {"phases": 1, "rows": 2, "test_rows": 1, "files": 2, "commands": 1,
                                 "reading_bytes": 0, "heavy_phases": 0}


def test_a_simple_plan_takes_single_and_a_complex_plan_takes_phases(repo: Path) -> None:
    # AC 1, CDM-AC5, CDM-AC11, CDM-AC12 (CDM-B3, CDM-B6, CDM-B7)
    assert _run(repo, SINGLE, task="S-1").exit_code is ExitCode.FINISHED
    (route,) = _routes(repo, "S-1")
    assert (route["arm"], route["zone"]) == ("single", "simple")
    assert _entered(repo, "S-1") == ["triage", "plan", "code", "code_join"]  # the expand step is never entered

    assert _run(repo, PHASES, task="P-1").exit_code is ExitCode.FINISHED
    (route,) = _routes(repo, "P-1")
    assert (route["arm"], route["zone"]) == ("phases", "complex")
    assert _entered(repo, "P-1") == ["triage", "plan", "expand", "code", "code_join"]
    log = run_dir(state_root_path(repo), SPEC.name, "P-1") / "run.jsonl"
    records = [json.loads(line) for line in log.read_text(encoding="utf-8").splitlines()]
    passed = next(i for i, r in enumerate(records) if r["kind"] == "gate" and r.get("unit") == "expand")
    opened = next(i for i, r in enumerate(records) if r["kind"] == "unit_entered" and r["unit"] == "code")
    assert records[passed]["verdict"] == "PROCEED" and passed < opened


OVER_ONE = {
    "phases": (_plan([(f"P{i}", "light", [("test", f"tests/t{i}.py")]) for i in range(1, 5)]), None),
    "heavy": (_plan([("One", "heavy (refactor)", [("test", "tests/a.py"), ("code", "src/a.py")])]), None),
    "reading_bytes": (_plan([("One", "light", [("test", "tests/a.py"), ("code", "src/big.py")])]),
                      {"src/big.py": 300_000}),
    "rows": (_plan([("One", "light", [("test", "tests/a.py")] * 6 + [("code", "src/a.py")] * 7)]), None),
    "test_rows": (_plan([("One", "light", [("test", "tests/a.py")] * 7 + [("code", "src/a.py")] * 3)]), None),
    "files": (_plan([("One", "light", [("test", f"tests/t{i}.py") for i in range(6)]
                      + [("code", f"src/c{i}.py") for i in range(5)])]), None),
    "commands": (_plan([("One", "light", [("test", "tests/a.py"), ("code", "src/a.py")])],
                       commands=("git --version", "git status", "git diff", "git log")), None),
}


@pytest.mark.parametrize("sign", list(OVER_ONE))
def test_a_plan_over_exactly_one_limit_takes_phases(repo: Path, sign: str) -> None:
    # AC 1, CDM-AC6 (CDM-B3)
    text, sizes = OVER_ONE[sign]
    out = _run(repo, [_triage(), _planner(text, sizes), _expander, _coder])
    assert out.exit_code is ExitCode.FINISHED, out.message
    (route,) = _routes(repo)
    assert (route["arm"], route["zone"]) == ("phases", "complex"), route["measures"]
    assert _entered(repo) == ["triage", "plan", "expand", "code", "code_join"]


def test_the_control_plan_inside_every_limit_takes_single(repo: Path) -> None:
    # AC 1, CDM-AC6 (CDM-B3)
    inside = _plan([("One", "light", [("test", "tests/a.py")] * 6 + [("code", "src/a.py")] * 6)],
                   commands=("git --version", "git status", "git diff"))
    assert _run(repo, [_triage(), _planner(inside, {"src/a.py": 190_000}), _coder]).exit_code is ExitCode.FINISHED
    (route,) = _routes(repo)
    assert (route["arm"], route["zone"]) == ("single", "simple"), route["measures"]


def test_a_missing_fact_takes_phases_in_the_zone_fault(repo: Path) -> None:
    # AC 1, CDM-AC9 (CDM-B5)
    out = _run(repo, [_triage(), _planner(SIMPLE), _expander, _coder], check=silent_check)
    assert out.exit_code is ExitCode.FINISHED, out.message
    (route,) = _routes(repo)
    assert (route["arm"], route["zone"]) == ("phases", "fault")
    assert route["measures"]["phases"] == "fault"
    assert _entered(repo) == ["triage", "plan", "expand", "code", "code_join"]


def test_a_repository_override_that_is_not_json_takes_phases_in_the_zone_fault(repo: Path) -> None:
    # AC 1, CDM-AC10 (CDM-B5)
    path = complexity.override_path(state_root_path(repo), SPEC.name, "code_mode")
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text("{not json", encoding="utf-8")
    out = _run(repo, [_triage(), _planner(SIMPLE), _expander, _coder])
    assert out.exit_code is ExitCode.FINISHED, out.message
    (route,) = _routes(repo)
    assert (route["arm"], route["zone"], route["rules_source"]) == ("phases", "fault", "repository")
    assert route["rules_error"]


def test_the_operator_names_phases_for_a_simple_plan(repo: Path) -> None:
    # AC 2, CDM-AC13 (CDM-B8)
    out = _run(repo, [_triage(), _planner(SIMPLE), _expander, _coder], flags={"code_mode.arm": "phases"})
    assert out.exit_code is ExitCode.FINISHED, out.message
    (route,) = _routes(repo)
    assert (route["arm"], route["chosen_by"], route["would_choose"]) == ("phases", "operator", "single")
    assert _entered(repo) == ["triage", "plan", "expand", "code", "code_join"]


def test_the_operator_names_single_for_a_plan_of_five_phases(repo: Path) -> None:
    # AC 2, CDM-AC14 (CDM-B8)
    out = _run(repo, [_triage(), _planner(FIVE), _coder], flags={"code_mode.arm": "single"})
    assert out.exit_code is ExitCode.FINISHED, out.message
    (route,) = _routes(repo)
    assert (route["arm"], route["chosen_by"], route["would_choose"]) == ("single", "operator", "phases")
    assert _entered(repo) == ["triage", "plan", "code", "code_join"]  # the expand step is never entered


# -- the report by arm ---------------------------------------------------------------------------------------------


def _logged(root: Path, task: str, arm: str, zone: str, *, chosen_by: str = "predicate", would_choose: str | None = None,
            phases: int = 2, usd: float = 2.0) -> None:
    """A finished run's log, as the engine writes it: the route record of the switch, one session of the arm's unit,
    its gate and the end."""
    log = RunLog(run_dir(root, SPEC.name, task) / "run.jsonl")
    use = {"input_tokens": 1, "output_tokens": 1, "reported_cost_usd": usd, "estimated_cost_usd": usd}
    unit = "code" if arm == "single" else "expand"
    log.write("run_started", workflow_version="0.1.0")
    log.write("route", unit="code_mode", arm=arm, target=unit, chosen_by=chosen_by, zone=zone,
              measures={"phases": phases}, shadow=False, would_choose=would_choose or arm)
    log.write("agent_run", unit=unit, attempt=1, executor="claude", session_kind="step", usage=use)
    log.write("gate", unit=unit, verdict="PROCEED")
    log.write("outcome", verdict="met")
    log.write("run_exit", exit_code=0, reason="finished")


def test_the_report_counts_the_operators_run_under_the_arm_it_took(repo: Path) -> None:
    # AC 2, CDM-AC16 (CDM-B10)
    root = state_root_path(repo)
    _logged(root, "S-0", "single", "simple")
    _logged(root, "P-0", "phases", "complex")
    _logged(root, "O-0", "phases", "simple", chosen_by="operator", would_choose="single")
    doc = swr.report(root, SPEC.name, "code_mode", None, units={"expand", "code"}, size="phases")
    cells = {(c["arm"], c["zone"]): c for c in doc["cells"]}
    assert set(cells) == {("single", "simple"), ("phases", "complex"), ("phases", "simple")}
    assert cells[("phases", "simple")]["runs"] == 1 and cells[("phases", "simple")]["would_choose"] == "single"
    assert cells[("phases", "complex")]["runs"] == 1 and cells[("single", "simple")]["runs"] == 1
    assert doc["runs"] == 3


def _cli(repo: Path, *argv: str) -> tuple[int, str]:
    out, err = io.StringIO(), io.StringIO()
    code = main(list(argv), catalog=Catalog(specs={SPEC.name: SPEC}), registry=Registry(), cwd=repo, out=out, err=err,
                run_settings=RunSettings(sleep=lambda s: None), signals=({}, True))
    return code, out.getvalue()


def test_the_report_divides_a_cells_cost_by_the_sum_of_its_phases(repo: Path) -> None:
    # AC 2, CDM-AC17 (CDM-B10)
    root = state_root_path(repo)
    for i in range(5):
        _logged(root, f"S-{i}", "single", "simple", phases=2, usd=2.0)
    doc = swr.report(root, SPEC.name, "code_mode", None, units={"expand", "code"}, size="phases")
    (cell,) = doc["cells"]
    assert (cell["arm"], cell["zone"], cell["runs"], cell["cost_per_size_usd"]) == ("single", "simple", 5, 1.0)
    code, text = _cli(repo, "report", "all", "--switch", f"{SPEC.name}/code_mode")
    assert code == 0, text
    assert "single / simple: 5 runs" in text and "$1.00 per unit of size" in text


def test_a_quick_lane_run_takes_no_arm_and_enters_no_expand_step(repo: Path) -> None:
    # AC 1, CDM-AC15 (CDM-B9)
    out = _run(repo, [_triage("quick"), _coder])
    assert out.exit_code is ExitCode.FINISHED, out.message
    assert _entered(repo) == ["triage", "code", "code_join"]
    assert _routes(repo) == []


# -- the live check and the package's documents -----------------------------------------------------------------------

TRIAL = "tempergraph author verify <path to plugins/temperspec-tgraph> --trial --case missing-config --cap 15"


def _live_rows() -> tuple[list[list[str]], list[list[str]]]:
    """The rows (cells) of the Rows table and of the Results table of the package's live checks."""
    text = (ROOT / "docs" / "plans" / "live-checks.plan.md").read_text(encoding="utf-8")
    rows, results = text.split("## Rows", 1)[1].split("## Results", 1)
    results = results.split("\n## ", 1)[0]

    def cells(block: str) -> list[list[str]]:
        return [[c.strip() for c in line.strip().strip("|").split("|")] for line in block.splitlines()
                if line.startswith("|")]
    return cells(rows), cells(results)


def test_the_live_checks_hold_a_row_for_the_trial_run_of_missing_config_and_no_result_for_it() -> None:
    # AC 4, CDM-AC18 (CDM-B11)
    rows, results = _live_rows()
    (row,) = [r for r in rows if r[0] == "TS-L3"]
    assert row[2].strip("`") == TRIAL
    assert not [r for r in results if r[0].startswith("TS-L3")], "no result is invented"


def test_the_pass_criterion_of_the_trial_row_names_the_gate_the_verdict_and_the_route_record() -> None:
    # AC 4, CDM-AC19 (CDM-B11)
    rows, _ = _live_rows()
    (row,) = [r for r in rows if r[0] == "TS-L3"]
    passes = " ".join(row[3].replace("`", "").lower().split())
    for phrase in ("outcome gate", "a verdict other than not_reached", "no pause", "route record", "code_mode", "an arm"):
        assert phrase in passes, phrase


def test_the_readme_the_module_docstring_and_the_diagram_say_what_the_route_does_now() -> None:
    # AC 3, CDM-AC1
    readme = (ROOT / "README.md").read_text(encoding="utf-8")
    (plan_row,) = [ln for ln in readme.splitlines() if ln.startswith("| plan |")]
    assert "code_mode" in plan_row and "A complex plan goes to expand; a simple one" not in plan_row
    (expand_row,) = [ln for ln in readme.splitlines() if ln.startswith("| expand |")]
    assert "phases" in expand_row and "code_mode" in expand_row
    (code_row,) = [ln for ln in readme.splitlines() if ln.startswith("| code |")]
    assert "both arms" in code_row
    (full,) = [ln for ln in readme.splitlines() if ln.startswith("| full |")]
    assert "triage → discovery → plan → expand → code" in full and "over a limit" in full
    assert "--arm code_mode=" in readme and "report --switch temperspec/code_mode" in readme
    assert "TS-L3" in readme
    diagram = (ROOT / "diagram" / "workflow.md").read_text(encoding="utf-8")
    assert "code_mode" in diagram and "code_join" in diagram
    assert "code_mode" in (importlib.import_module("tgwf_temperspec").__doc__ or "")


LINK = re.compile(r"\]\((?P<target>[^)\s]+)\)")
NEW_UNIT_SPECS = {"code_mode": "10-code_mode.spec.md", "code_join": "11-code_join.spec.md"}


def test_every_unit_has_its_numbered_spec_the_overview_names_both_new_ones_and_every_link_resolves() -> None:
    # AC 3 (CDM-B1)
    from tempergraph.package.docs_check import docs_check

    assert [f.message for f in docs_check(SPEC, ROOT, "stable")] == []
    specs = ROOT / "docs" / "specs"
    for unit in SPEC.order:
        assert len(list(specs.glob(f"[0-9][0-9]-{unit}.spec.md"))) == 1, unit
    for unit, name in NEW_UNIT_SPECS.items():
        assert (specs / name).is_file(), unit
    overview = (specs / "00-overview.spec.md").read_text(encoding="utf-8")
    for name in NEW_UNIT_SPECS.values():
        assert f"({name})" in overview
    note = ROOT / "docs" / "tasks" / "i116.triage.md"
    targets = [m.group("target").split("#", 1)[0] for m in LINK.finditer(note.read_text(encoding="utf-8"))]
    assert targets
    for target in targets:
        assert not target.startswith("plugins/"), target
        assert (note.parent / target).exists(), target


@pytest.mark.parametrize("name", list(NEW_UNIT_SPECS.values()))
def test_the_new_unit_specs_read_as_the_packages_other_unit_specs_do(name: str) -> None:
    # AC 3 (CDM-B1)
    text = (ROOT / "docs" / "specs" / name).read_text(encoding="utf-8")
    parsed = fmt.parse_spec(text)
    assert parsed.legacy and not parsed.problems
    assert fmt.defined_ids(text) == []
    assert "(00-overview.spec.md)" in text and "(code-mode.spec.md)" in text
