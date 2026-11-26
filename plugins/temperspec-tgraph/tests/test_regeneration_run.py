"""Fixture runs of the regeneration unit on the loaded workflow (RGN-B1, RGN-B2, RGN-B8). The sessions are the
stand-ins of the independent review's tests; the unit itself is the package's own."""

from __future__ import annotations

import dataclasses
import importlib
import json
import subprocess
import sys
from pathlib import Path
from typing import Any

import pytest
from tempergraph.constants import ExitCode

ROOT = Path(__file__).resolve().parents[1]
TASK = "I-1"
GEN = "import pathlib\npathlib.Path('generated.txt').write_text('generated\\n')\n"
MARKER = "import pathlib\npathlib.Path('ran.txt').write_text('x')\n"


def _load(name: str) -> Any:
    here = str(ROOT / "tests")
    if here not in sys.path:
        sys.path.insert(0, here)  # the engine imports the module's check functions by name
    return importlib.import_module(name)


irv = _load("test_independent_review")
modes = _load("test_code_mode")


@pytest.fixture
def repo(tmp_path: Path) -> Path:
    root = tmp_path / "repo"
    root.mkdir()
    for args in (("init", "-q", "-b", "main"), ("config", "user.email", "t@example.invalid"),
                 ("config", "user.name", "Test")):
        subprocess.run(["git", *args], cwd=root, check=True, capture_output=True)
    (root / "README.md").write_text("scratch\n", encoding="utf-8")
    subprocess.run(["git", "add", "-A"], cwd=root, check=True, capture_output=True)
    subprocess.run(["git", "commit", "-q", "-m", "init"], cwd=root, check=True, capture_output=True)
    return root


def _declare(repo: Path, *entries: dict[str, Any], tools: dict[str, str] | None = None) -> None:
    for rel, text in {"tools/gen.py": GEN, "tools/marker.py": MARKER, **(tools or {})}.items():
        (repo / rel).parent.mkdir(parents=True, exist_ok=True)
        (repo / rel).write_text(text, encoding="utf-8")
    (repo / "tempergraph.regenerations.json").write_text(
        json.dumps({"schema_version": 1, "regenerations": list(entries)}), encoding="utf-8")
    subprocess.run(["git", "add", "-A"], cwd=repo, check=True, capture_output=True)
    subprocess.run(["git", "commit", "-q", "-m", "declare"], cwd=repo, check=True, capture_output=True)


def _entry(command: str = "python3 tools/gen.py", inputs: list[str] | None = None,
           outputs: list[str] | None = None) -> dict[str, Any]:
    return {"name": "gen", "command": command, "inputs": inputs or ["src"], "outputs": outputs or ["generated.txt"]}


def _work(repo: Path) -> Path:
    """The run's own worktree."""
    return repo.parent / "repo.worktrees" / f"temperspec--{TASK}"


def _subjects(repo: Path) -> list[str]:
    return irv._git_out(repo, "log", "--format=%s").splitlines()


def _gate_units(repo: Path) -> list[str]:
    return [r["unit"] for r in irv._records(repo, "gate")]


def test_rgn_ac1_the_unit_is_entered_after_the_code_step_on_each_arm(repo: Path) -> None:
    # RGN-AC1, AC 1
    for steps, task in ((modes.SINGLE, "S-1"), (modes.PHASES, "P-1")):
        out = modes._run(repo, steps, task=task)
        assert out.exit_code is ExitCode.FINISHED, json.dumps(out.payload, default=str)[:1500]
        assert modes._entered(repo, task)[-4:] == ["code", "regeneration", "code_join", "independent_review"], task


def test_rgn_ac1_the_quick_lane_enters_the_unit_before_the_outcome_gate_and_no_review(repo: Path) -> None:
    # RGN-AC1, AC 1
    stand = irv.Stand(route="quick")
    out = irv._go(repo, stand)
    assert out.exit_code is ExitCode.FINISHED, out.message
    gates = _gate_units(repo)
    assert gates.index("code") < gates.index("regeneration") < gates.index("outcome")
    assert "independent_review" not in gates and "independent_review" not in stand.units()


def test_rgn_ac2_a_due_regeneration_starts_no_session_and_its_files_are_committed(repo: Path) -> None:
    # RGN-AC2, AC 1, RGN-B2, RGN-B11
    _declare(repo, _entry())
    stand = irv.Stand()
    out = irv._go(repo, stand)
    assert out.exit_code is ExitCode.FINISHED, out.message
    assert "regeneration" not in stand.units() and "regeneration" not in stand.units("judge")
    assert stand.units()[-2:] == ["code", "independent_review"]  # nothing between them: no session for the unit
    assert (_work(repo) / "generated.txt").read_text() == "generated\n"
    assert f"docs(temperspec): regeneration for {TASK}" in _subjects(_work(repo))
    gates = _gate_units(repo)
    assert gates.index("code") < gates.index("regeneration") < gates.index("independent_review")


@pytest.mark.parametrize("entries", [[], [_entry(inputs=["other"])]])
def test_rgn_ac2_nothing_declared_or_no_input_changed_starts_no_command_and_adds_no_commit(
        repo: Path, entries: list[dict[str, Any]]) -> None:
    # AC 1, RGN-AC8 (RGN-B8): an empty list, and a declaration whose input the run did not change
    _declare(repo, *[{**e, "command": "python3 tools/marker.py"} for e in entries])
    stand = irv.Stand()
    out = irv._go(repo, stand)
    assert out.exit_code is ExitCode.FINISHED, out.message
    assert not (_work(repo) / "ran.txt").exists() and not (_work(repo) / "generated.txt").exists()
    assert not any("regeneration for" in s for s in _subjects(_work(repo)))


# -- a failed regeneration goes back to the code step (RGF-B1 to RGF-B8) ----------------------------------------------

# A stand-in command: it fails on the passes named in its second word (1 is the unit's first pass) and prints the report
# in the file named by its third word, which holds the JSON an engine command prints; it counts its passes in a file
# under `.tempergraph/regeneration/`, which the unit never commits or restores.
FLAKY = """import json, pathlib, sys, time
marker, fail_on, report = sys.argv[1], {int(n) for n in sys.argv[2].split(',') if n}, pathlib.Path(sys.argv[3])
mark = pathlib.Path('.tempergraph/regeneration/' + marker)
n = (int(mark.read_text()) if mark.exists() else 0) + 1
mark.write_text(str(n))
if n in fail_on:
    print(report.read_text() if report.exists() else 'plain failure\\nsecond line')
    sys.exit(1)
pathlib.Path(marker + '.txt').write_text('ok\\n')
"""
SLEEPY = "import time\ntime.sleep(30)\n"


def _verify_report(*findings: tuple[str, str, str, str]) -> str:
    """The JSON of `author verify` with one failed rung holding the findings (code, unit, message, remedy)."""
    rows = [{"code": c, "unit": u, "message": m, "remedy": r} for c, u, m, r in findings]
    return json.dumps({"schema_version": 1, "workflow": "w", "ok": False, "refused": "", "rungs": [
        {"rung": 2, "name": "model", "state": "failed", "note": "", "findings": rows}]}, indent=2)


def _flaky(marker: str, fail_on: str, report: str = "tools/none.json") -> dict[str, Any]:
    return {"name": marker, "command": f"python3 tools/flaky.py {marker} {fail_on or ','} {report}",
            "inputs": ["src"], "outputs": [f"{marker}.txt"]}


def _declare_flaky(repo: Path, *entries: dict[str, Any], reports: dict[str, str] | None = None) -> None:
    tools = {"tools/flaky.py": FLAKY, "tools/sleepy.py": SLEEPY, **{f"tools/{k}": v for k, v in (reports or {}).items()}}
    _declare(repo, *entries, tools=tools)


def _spec() -> Any:
    """The package's spec as the review's tests build it, with the regeneration unit's own gate and check."""
    spec = irv._spec()
    units = dict(spec.units)
    units["regeneration"] = dataclasses.replace(units["regeneration"], gate=irv.SPEC.units["regeneration"].gate)
    return dataclasses.replace(spec, units=units)


def _go(repo: Path, stand: Any) -> Any:
    from tempergraph.executors.registry import Registry
    from tempergraph.run.runner import RunSettings, start

    registry = Registry()
    registry.register(stand)
    return start(_spec(), TASK, {"request": "x"}, repo, registry,
                 RunSettings(sleep=lambda s: None, flags={"code_mode.arm": "single"}))


def _code_prompts(stand: Any) -> list[str]:
    return [s["prompt"] for s in stand.sessions if s["kind"] == "step" and s["unit"] == "code"]


THREE = _verify_report(("summary-long", "code", "the summary is 71 characters", "shorten it in blueprint.json"),
                       ("no-case", "plan", "no pass case and no fail case", "add cases to cases/plan.json"),
                       ("blocker-unverified", "plan", "no case verifies the blocker", "add a case to cases/plan.json"))
FOUR = _verify_report(("summary-too-long", "code", "summary over 60 characters", "shorten the summary in workflow/w/__init__.py"),
                      ("no-pass-fail-case", "plan", "a check with no pass case and no fail case", "add both to cases/plan.json"),
                      ("blocker-no-case", "plan", "a blocker no case verifies", "add a case to cases/judge.json"),
                      ("blueprint-differs", None, "the blueprint differs from the model", "regenerate blueprint.json"))


def test_rgf_ac1_a_failed_regeneration_sends_the_run_to_the_code_step_with_numbered_findings(repo: Path) -> None:
    # RGF-AC1 (RGF-B1, RGF-B2), AC 5
    _declare_flaky(repo, _flaky("gen", "1", "tools/three.json"), reports={"three.json": THREE})
    stand = irv.Stand()
    out = _go(repo, stand)
    assert out.exit_code is ExitCode.FINISHED, out.message
    assert stand.units()[-3:] == ["code", "code", "independent_review"]
    reason = _code_prompts(stand)[-1]
    assert "Why this unit runs again" in reason
    at = [reason.index(f"{n}. [") for n in (1, 2, 3)]
    assert at == sorted(at) and "4. [" not in reason
    assert "summary-long" in reason[at[0]:at[1]] and "blocker-unverified" in reason[at[2]:]
    assert "no pass case" in _code_prompts(stand)[-1] and "Why this unit runs again" not in _code_prompts(stand)[0]
    assert _gate_units(repo).count("regeneration") == 2 and (_work(repo) / "gen.txt").is_file()


def test_rgf_ac2_the_four_failures_of_the_earlier_run_come_back_as_four_findings_naming_their_files(repo: Path) -> None:
    # RGF-AC2 (RGF-B3), AC 5
    _declare_flaky(repo, _flaky("gen", "1", "tools/four.json"), reports={"four.json": FOUR})
    stand = irv.Stand()
    out = _go(repo, stand)
    assert out.exit_code is ExitCode.FINISHED, out.message
    reason = _code_prompts(stand)[-1]
    for n, where in enumerate(("workflow/w/__init__.py", "cases/plan.json", "cases/judge.json", "blueprint.json"), start=1):
        assert f"{n}. [" in reason and where in reason, (n, where)
    assert "5. [" not in reason


def test_rgf_ac2_two_failing_regenerations_make_one_trip_and_one_failing_alone_has_its_own_findings(repo: Path) -> None:
    # RGF-AC2 (RGF-B2, RGF-B3), AC 5
    one, two = _verify_report(("a-one", "u", "first one", "fix a")), _verify_report(("b-one", "u", "second one", "fix b"))
    entries = (_flaky("gen", "1", "tools/a.json"), _flaky("other", "1", "tools/b.json"))
    _declare_flaky(repo, *entries, reports={"a.json": one, "b.json": two})
    stand = irv.Stand()
    out = _go(repo, stand)
    assert out.exit_code is ExitCode.FINISHED, out.message
    assert stand.units().count("code") == 2
    reason = _code_prompts(stand)[-1]
    assert reason.index("1. [model] u: a-one: first one") < reason.index("2. [model] u: b-one: second one")
    # only the second fails: the first one's findings are not carried
    other = irv.Stand()
    repo2 = repo.parent / "second"
    repo2.mkdir()
    for args in (("init", "-q", "-b", "main"), ("config", "user.email", "t@example.invalid"), ("config", "user.name", "T")):
        subprocess.run(["git", *args], cwd=repo2, check=True, capture_output=True)
    (repo2 / "README.md").write_text("x\n", encoding="utf-8")
    subprocess.run(["git", "add", "-A"], cwd=repo2, check=True, capture_output=True)
    subprocess.run(["git", "commit", "-q", "-m", "init"], cwd=repo2, check=True, capture_output=True)
    _declare_flaky(repo2, _flaky("gen", ""), _flaky("other", "1", "tools/b.json"), reports={"b.json": two})
    out = _go(repo2, other)
    assert out.exit_code is ExitCode.FINISHED, out.message
    reason = _code_prompts(other)[-1]
    assert "1. [model] u: b-one: second one" in reason and "a-one" not in reason and "2. [" not in reason


def test_rgf_ac6_a_second_failure_pauses_with_kind_budget_and_the_findings_left(repo: Path) -> None:
    # RGF-AC6 (RGF-B7), AC 6
    bad = _verify_report(("still-wrong", "code", "this one is still wrong", "fix it"))
    _declare_flaky(repo, _flaky("gen", "1,2", "tools/bad.json"), reports={"bad.json": bad})
    stand = irv.Stand()
    out = _go(repo, stand)
    assert out.exit_code is ExitCode.PAUSED and out.payload["kind"] == "budget", out.message
    assert stand.units().count("code") == 2 and "independent_review" not in stand.units()
    assert "this one is still wrong" in json.dumps(out.payload, default=str)


def test_rgf_ac6_a_regeneration_that_passes_on_the_second_pass_does_not_pause(repo: Path) -> None:
    # RGF-AC6 (RGF-B7), AC 6
    _declare_flaky(repo, _flaky("gen", "1"))
    out = _go(repo, irv.Stand())
    assert out.exit_code is ExitCode.FINISHED, out.message


def test_rgf_ac6_a_run_the_review_sent_back_is_sent_back_again_by_a_first_failure_after_that_visit(repo: Path) -> None:
    # RGF-AC6 (RGF-B7), AC 6: the trip back of the regeneration is counted from the code visit the review caused
    _declare_flaky(repo, _flaky("gen", "2"))
    stand = irv.Stand(reviews=[[irv.BLOCKS], ["None"]])
    out = _go(repo, stand)
    assert out.exit_code is ExitCode.FINISHED, out.message
    assert stand.units().count("code") == 3 and _gate_units(repo).count("regeneration") == 3


class PhasedStand(irv.Stand):
    """The review's stand-in, answering the expand step and the phase items of the arm `phases` as well."""

    def run_step(self, req: Any, sink: Any) -> Any:
        from tempergraph.executors.standins import answer

        unit = req.session_key.split(".")[0]
        if unit in ("expand", "phase"):
            self.sessions.append({"kind": "step", "unit": unit, "prompt": req.prompt})
            if unit == "expand":
                (Path(req.workdir) / "phases.md").write_text(modes.EXPANDED, encoding="utf-8")
                return answer("Expanded.\nARTIFACT phases: phases.md", session_id=f"s-{len(self.units())}")
            return answer("Built.\nARTIFACT phase_note: built the phase", session_id=f"s-{len(self.units())}")
        return super().run_step(req, sink)


@pytest.mark.parametrize("arm", ["single", "phases"])
def test_rgf_ac7_the_trip_back_runs_the_code_step_alone_on_each_arm(repo: Path, arm: str) -> None:
    # RGF-AC7 (RGF-B6), AC 7
    from tempergraph.executors.registry import Registry
    from tempergraph.run.runner import RunSettings, start

    _declare_flaky(repo, _flaky("gen", "1", "tools/three.json"), reports={"three.json": THREE})
    stand = PhasedStand()
    registry = Registry()
    registry.register(stand)
    out = start(_spec(), TASK, {"request": "x"}, repo, registry,
                RunSettings(sleep=lambda s: None, flags={"code_mode.arm": arm}))
    assert out.exit_code is ExitCode.FINISHED, json.dumps(out.payload, default=str)[:1500]
    units = stand.units()
    assert ("expand" in units) is (arm == "phases")
    assert units.count("code") == 2 and units.count("independent_review") == 1
    for once in ("expand", "phase", "plan", "triage", "discovery"):
        assert units.count(once) <= 1, once
    assert units[units.index("code", units.index("code") + 1) - 1] == "code"  # nothing between the two visits
    assert _gate_units(repo).count("regeneration") == 2
    prompts = _code_prompts(stand)
    assert "1. [model] code: summary-long" in prompts[-1] and "Why this unit runs again" not in prompts[0]


def test_rgf_ac8_a_command_that_cannot_run_pauses_at_once_and_sends_nothing_back(
        repo: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    # RGF-AC8 (RGF-B8), AC 6
    # the module the loaded spec calls: the globals of the unit's own callable
    monkeypatch.setitem(irv.SPEC.units["regeneration"].script.call.func.__globals__, "TIMEOUT_S", 2.0)
    cases = {"does not start": "no-such-program-xyz tools/flaky.py", "refused": "make docs && make site",
             "timeout": "python3 tools/sleepy.py"}
    for i, (what, command) in enumerate(cases.items()):
        root = repo.parent / f"env{i}"
        root.mkdir()
        for args in (("init", "-q", "-b", "main"), ("config", "user.email", "t@example.invalid"), ("config", "user.name", "T")):
            subprocess.run(["git", *args], cwd=root, check=True, capture_output=True)
        (root / "README.md").write_text("x\n", encoding="utf-8")
        subprocess.run(["git", "add", "-A"], cwd=root, check=True, capture_output=True)
        subprocess.run(["git", "commit", "-q", "-m", "init"], cwd=root, check=True, capture_output=True)
        _declare_flaky(root, {**_entry(command), "name": "env"})
        stand = irv.Stand()
        out = _go(root, stand)
        assert out.exit_code is ExitCode.PAUSED and out.payload["kind"] == "escalation", (what, out.message)
        assert stand.units().count("code") == 1, what
        from tempergraph.store.layout import run_dir, state_root_path

        record = (run_dir(state_root_path(root), irv.SPEC.name, TASK) / "run.jsonl").read_text(encoding="utf-8")
        assert command.split()[0] in record, what  # the check's evidence names the command


def test_rgf_ac8_a_command_that_exits_one_is_sent_back_and_does_not_pause(repo: Path) -> None:
    # RGF-AC8 (RGF-B8), AC 6
    _declare_flaky(repo, _flaky("gen", "1"))
    stand = irv.Stand()
    out = _go(repo, stand)
    assert out.exit_code is ExitCode.FINISHED, out.message
    assert stand.units().count("code") == 2 and "plain failure" in _code_prompts(stand)[-1]


def test_rgn_ac2_a_repository_with_no_declaration_passes_the_unit_with_nothing_run(repo: Path) -> None:
    # AC 1, RGN-AC8 (RGN-B8)
    out = irv._go(repo, irv.Stand())
    assert out.exit_code is ExitCode.FINISHED, out.message
    assert "regeneration" in _gate_units(repo)
    assert not any("regeneration for" in s for s in _subjects(_work(repo)))
