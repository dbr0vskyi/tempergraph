"""Eval suites for checks, steps and whole workflows (EVS-B8, EVS-B17, EVS-B18).

A suite's cases live in the package (`evals/checks/<unit>/`, `evals/steps/<unit>/<case>/`, `evals/cases.json`);
its results are rows of `evals/results.jsonl` under the state root, holding ids, statuses, counts and digests
only. Graders are trusted in a fixed order: code, then an accepted judge, then a person (ADR-0049).
"""

from __future__ import annotations

import dataclasses
import fnmatch
import hashlib
import json
import os
import re
import shutil
import tempfile
import uuid
from collections import defaultdict
from collections.abc import Callable, Mapping, Sequence
from pathlib import Path
from typing import Any

from tempergraph.contracts import InputDeclaration, Param, WorkflowSpec
from tempergraph.docs import append_jsonl
from tempergraph.store.layout import now_iso

KINDS = ("check", "judge", "step", "workflow")
ROLES = ("regression", "capability")
LIVE_KINDS = ("judge", "step", "workflow")
DEFAULT_CAP_USD = 20.0
STEP_TRIALS = 3
NEVER_PASSED_MIN = 5
GRADUATE_RUNS = 3
TEST_MARKER = "PYTEST_CURRENT_TEST"


class SuiteRefused(Exception):
    pass


def results_path(root: Path) -> Path:
    return root / "evals" / "results.jsonl"


def under_test() -> bool:
    """The engine's test marker (EVS-B13, EVS-B12, EVS-B14): set by the test runner, lifted only for marked live checks."""
    return TEST_MARKER in os.environ and os.environ.get("TEMPERGRAPH_LIVE") != "1"


def is_live(executor: Any) -> bool:
    """A scripted stand-in says so itself; every other executor makes model calls."""
    return not getattr(executor, "scripted", False)


def refuse_live(kind: str, executor: Any) -> None:
    """EVS-AC3: no live suite starts under the test marker."""
    if kind in LIVE_KINDS and is_live(executor) and under_test():
        raise SuiteRefused(f"a live `{kind}` suite cannot start from the test suite or CI")


# -- assertions (EVS-B9, EVS-B2, EVS-B10 `expect`, EVS-B12 `end_state`) --------------------------------------------------------

def assertion_failures(asserts: Sequence[Mapping[str, Any]], workdir: Path,
                       changed: Sequence[str] = ()) -> list[str]:
    """The assertions that do not hold, by index and kind; the texts they read are never returned."""
    out = []
    for i, a in enumerate(asserts):
        path = workdir / str(a["path"]) if a.get("path") else None
        if path is not None and not path.resolve().is_relative_to(workdir.resolve()):
            out.append(f"{i}:outside_workspace")
            continue
        text = None
        if path is not None and path.is_file():
            text = path.read_text(encoding="utf-8", errors="replace")
        if "changed_within" in a:
            globs = [str(g) for g in a["changed_within"]]
            if any(not any(fnmatch.fnmatchcase(p, g) for g in globs) for p in changed):
                out.append(f"{i}:changed_within")
        elif path is None:
            out.append(f"{i}:unknown_assertion")
        elif a.get("absent"):
            if path.exists():
                out.append(f"{i}:absent")
        elif "pattern" in a:
            if text is None or not re.search(str(a["pattern"]), text, re.M):
                out.append(f"{i}:pattern")
        elif "heading" in a:
            want = str(a["heading"]).strip().lower()
            heads = [ln.lstrip("#").strip().lower() for ln in (text or "").splitlines() if ln.startswith("#")]
            if want not in heads:
                out.append(f"{i}:heading")
        elif not path.exists():
            out.append(f"{i}:path")
    return out


# -- cases ---------------------------------------------------------------------------------------------------

@dataclasses.dataclass(frozen=True, kw_only=True)
class StepCase:
    unit: str
    case_id: str
    role: str = "regression"
    inputs: Mapping[str, str] = dataclasses.field(default_factory=dict)
    expect: tuple[Mapping[str, Any], ...] = ()
    covered: bool = False  # the assertions cover the case fully, so code decides a pass (EVS-B16)
    trials: int = STEP_TRIALS
    workspace: Path | None = None


def step_cases(spec: WorkflowSpec) -> tuple[list[StepCase], list[dict[str, str]]]:
    """`evals/steps/<unit>/<case_id>/case.json` with an optional `workspace/`; invalid cases are listed."""
    root = spec.package_root
    out: list[StepCase] = []
    bad: list[dict[str, str]] = []
    if root is None:
        return out, bad
    for folder in sorted((root / "evals" / "steps").glob("*/*")):
        unit, cid = folder.parent.name, folder.name
        try:
            doc = json.loads((folder / "case.json").read_text(encoding="utf-8"))
        except (OSError, ValueError):
            bad.append({"unit": unit, "case": cid, "reason": "case.json is missing or not JSON"})
            continue
        u = spec.units.get(unit)
        if u is None or u.step is None or u.gate.judge is None:
            bad.append({"unit": unit, "case": cid, "reason": "not a judged step of the workflow"})
            continue
        if doc.get("role", "regression") not in ROLES:
            bad.append({"unit": unit, "case": cid, "reason": "role is regression or capability"})
            continue
        ws = folder / "workspace"
        out.append(StepCase(unit=unit, case_id=str(doc.get("case_id") or cid), role=doc.get("role", "regression"),
                            inputs={str(k): str(v) for k, v in (doc.get("inputs") or {}).items()},
                            expect=tuple(doc.get("expect") or ()), covered=bool(doc.get("covered")),
                            trials=int(doc.get("trials") or STEP_TRIALS), workspace=ws if ws.is_dir() else None))
    return out, bad


def workflow_cases(spec: WorkflowSpec) -> list[dict[str, Any]]:
    """The reviewed entries of `evals/cases.json` (PRP-B17) with the fields of EVS-B12."""
    from tempergraph.improve.trials import case_set

    root = spec.package_root
    reviewed = {c.case_id: c for c in case_set(spec)[0]}
    try:
        doc = json.loads((root / "evals" / "cases.json").read_text(encoding="utf-8")) if root else []
    except (OSError, ValueError):
        return []
    rows = doc.get("cases") if isinstance(doc, dict) else doc
    out = []
    for r in rows or []:
        cid = str(r.get("case_id") or r.get("id") or "") if isinstance(r, dict) else ""
        if cid in reviewed:
            default = 3 if spec.improvement_mode == "stable" and r.get("role", "regression") == "regression" else 1
            out.append({"case": reviewed[cid], "role": r.get("role", "regression"),
                        "end_state": list(r.get("end_state") or []), "answers": list(r.get("answers") or []),
                        "covered": bool(r.get("covered")), "trials": int(r.get("trials") or default)})
    return out


# -- bindings ------------------------------------------------------------------------------------------------

def _sha(data: Any) -> str:
    return hashlib.sha256(json.dumps(data, sort_keys=True, default=str).encode()).hexdigest()[:16]


def step_binding(spec: WorkflowSpec, unit: str) -> str:
    """The digest of what a step trial ran on: the step's executor, alias, effort and prompt, and its judge's
    binding (EVS-B13, EVS-B14)."""
    from tempergraph.improve import calibration
    from tempergraph.model.text import TextUnreadable, load_text

    st = spec.units[unit].step
    assert st is not None
    try:
        prompt = load_text(spec, st.prompt)
    except TextUnreadable:
        prompt = ""
    opts = st.session_options
    return _sha({"executor": st.executor or spec.default_executor, "alias": st.model, "prompt": _sha(prompt),
                 "effort": opts.effort if opts else None, "ladder": list(st.effort_ladder),
                 "judge": calibration.current_binding(spec, unit)})


def workflow_binding(spec: WorkflowSpec) -> str:
    return _sha({"version": spec.version, "units": {n: step_binding(spec, n) for n, u in spec.units.items()
                                                    if u.step is not None and u.gate.judge is not None}})


# -- grading (EVS-B16) --------------------------------------------------------------------------------------

def grade(*, finished: bool, failures: Sequence[str], covered: bool, failed_by_code: bool,
          judge_state: str) -> tuple[str, str]:
    """`(status, graded_by)` of one trial: code decides a failed assertion or check and a fully covered case,
    an `accepted` judge decides the rest, and otherwise a person must."""
    if failures or (not finished and failed_by_code):
        return "failed", "code"
    if finished and covered:
        return "passed", "code"
    if judge_state == "accepted":
        return ("passed" if finished else "failed"), "judge"
    return "needs_person", "person"


def _unit_end(recs: Sequence[Mapping[str, Any]], unit: str) -> tuple[int, bool]:
    """A unit's attempts in the run and whether its last failure was decided by code (a check, a step that
    did not end with a result) and not by the judge's blockers."""
    attempts = sum(1 for r in recs if r.get("kind") == "attempt_start" and r.get("unit") == unit
                   and r.get("session_kind") in ("step", "retry"))
    checks = [r for r in recs if r.get("kind") == "check" and r.get("unit") == unit]
    judged = [r for r in recs if r.get("kind") == "judgement" and r.get("unit") == unit]
    by_code = bool(checks and checks[-1].get("result") == "FAIL") or not judged
    return attempts, by_code


# -- running -------------------------------------------------------------------------------------------------

def _row(run_id: str, kind: str, subject: str, case: str, role: str, trial: int, status: str, graded_by: str,
         **more: Any) -> dict[str, Any]:
    return {"schema_version": 1, "result_id": uuid.uuid4().hex[:12], "run_id": run_id, "at": now_iso(),
            "kind": kind, "subject": subject, "case": case, "role": role, "trial": trial, "status": status,
            "graded_by": graded_by, **more}


def run_checks(spec: WorkflowSpec, run_id: str) -> list[dict[str, Any]]:
    """The `check` suite: every fixture with LF and CRLF line endings; a case passes when both give the
    expected result and the findings name a criterion (EVS-B2). Model-free."""
    from tempergraph.package import selftest

    root = spec.package_root
    if root is None:
        return []
    with tempfile.TemporaryDirectory() as tmp:
        runs = selftest.fixture_runs(root, Path(tmp), spec)
    cases: dict[tuple[str, str, str], list[dict[str, Any]]] = defaultdict(list)
    out = []
    for r in runs:
        if "missing" in r:
            out.append(_row(run_id, "check", r["unit"], "fixtures", "regression", 1, "invalid", "code",
                            reason="check_without_" + ("fail" if "must-fail" in r["missing"] else "pass") + "_case"))
        else:
            cases[(r["unit"], r["which"], r["fixture"])].append(r)
    for (unit, which, fixture), both in sorted(cases.items()):
        want = "PASS" if which == "must-pass" else "FAIL"
        ok = all(r["result"] == want and r["named"] for r in both)
        differs = len({r["result"] for r in both}) > 1
        out.append(_row(run_id, "check", unit, f"{which}/{fixture}", "regression", 1,
                        "passed" if ok else "failed", "code", expected=want,
                        results=[r["result"] for r in both], line_endings_differ=differs))
    return out


def _step_spec(spec: WorkflowSpec, case: StepCase) -> WorkflowSpec:
    """The one step as its own workflow: its prompt, tools, check, judge and budgets unchanged; what earlier
    units would have produced comes from the case's inputs."""
    u = spec.units[case.unit]
    gate = dataclasses.replace(u.gate, back_targets=(), fallback=None,
                               on_budget_spent="stop" if u.gate.on_budget_spent == "fallback" else u.gate.on_budget_spent)
    names = list(dict.fromkeys(["request", *case.inputs]))
    return dataclasses.replace(
        spec, order=(case.unit,), units={case.unit: dataclasses.replace(u, gate=gate)}, outcome=None,
        input=InputDeclaration(kind="any", parameters=tuple(Param(name=n) for n in names)), settings={}, profiles={})


def _git_repo(workspace: Path | None, into: Path) -> Path:
    from tempergraph import git as gitmod

    repo = into / "repo"
    if workspace is not None:
        shutil.copytree(workspace, repo)
    else:
        repo.mkdir(parents=True)
    (repo / ".gitignore").write_text(".tempergraph/\n", encoding="utf-8") if not (repo / ".gitignore").exists() else None
    gitmod.git(["init", "-q"], repo)
    gitmod.git(["add", "-A"], repo)
    gitmod.git(["-c", "user.email=evals@example.invalid", "-c", "user.name=evals", "commit", "-q", "--allow-empty",
                "-m", "case base"], repo)
    return repo


def run_step_trial(spec: WorkflowSpec, case: StepCase, registry: Any, trial: int, run_id: str, *,
                   judge_state: Callable[[str], str], settings: Callable[..., Any] | None = None) -> dict[str, Any]:
    """One step trial in a fresh repository at the case's workspace: the step, its check and its judge exactly
    as in a run (EVS-B9, EVS-B2, EVS-B10)."""
    from tempergraph import git as gitmod
    from tempergraph.constants import ExitCode
    from tempergraph.improve.trials import _records, run_cost
    from tempergraph.run.runner import RunSettings, start
    from tempergraph.store.layout import state_root_path

    sub = _step_spec(spec, case)
    with tempfile.TemporaryDirectory() as tmp:
        repo = _git_repo(case.workspace, Path(tmp))
        rs = RunSettings(origin="trial", dry_run=True, workspace="in_place", sleep=lambda s: None,
                         caller={"kind": "pipeline", "decided_by": "engine", "caller_app": "evals"},
                         judge_state=judge_state)
        if settings is not None:
            rs = settings(rs)
        task = re.sub(r"[^A-Za-z0-9._-]", "-", f"ev-{run_id[:8]}-{case.case_id}-{trial}")[:64]
        out = start(sub, task, {"request": case.inputs.get("request", ""), **case.inputs}, repo, registry, rs)
        recs = _records(state_root_path(repo), sub.name, task)
        finished = out.exit_code is ExitCode.FINISHED
        failures = assertion_failures(case.expect, repo, gitmod.changed_paths(repo)) if finished else []
    attempts, by_code = _unit_end(recs, case.unit)
    refused = not recs or out.reason in ("not_in_release", "preflight", "validation")
    pauses = [r for r in recs if r.get("kind") == "pause"]
    waits = not finished and bool(pauses) and pauses[-1].get("pause_kind") != "budget"  # not a verdict on the work
    status, by = ("invalid", "code") if refused else ("paused", "code") if waits else grade(
        finished=finished, failures=failures, covered=case.covered, failed_by_code=by_code,
        judge_state=judge_state(case.unit))
    return _row(run_id, "step", case.unit, case.case_id, case.role, trial, status, by, attempts=attempts,
                first_attempt=finished and attempts == 1, cost_usd=round(run_cost(recs), 6),
                failures=failures, binding=step_binding(spec, case.unit),
                **({"reason": out.reason} if refused else {}))


def run_workflow_trial(spec: WorkflowSpec, entry: Mapping[str, Any], repo: Path, registry: Any, trial: int,
                       run_id: str, *, judge_state: Callable[[str], str],
                       settings: Callable[..., Any] | None = None) -> dict[str, Any]:
    """One whole run on a fixed case as a dry run, with the recorded answers applied to its pauses in order
    (EVS-B12)."""
    from tempergraph import git as gitmod
    from tempergraph.constants import ExitCode
    from tempergraph.improve.trials import ChildRuns, _records, run_cost
    from tempergraph.run.runner import RunSettings, read_exit, resume
    from tempergraph.store.layout import state_root_path

    case = entry["case"]
    binding = workflow_binding(spec)
    try:
        gitmod.git(["rev-parse", "--verify", "-q", f"{case.base}^{{commit}}"], repo)
    except gitmod.GitError:
        return _row(run_id, "workflow", spec.name, case.case_id, entry["role"], trial, "invalid", "code",
                    reason="base_missing", binding=binding)
    runner = ChildRuns(repo=repo, registry=registry, settings=settings)
    runner(spec, case, f"ev{trial}", run_id)
    task = runner.tasks[-1]
    root = state_root_path(repo)
    caller = {"kind": "pipeline", "decided_by": "engine", "caller_app": "evals"}
    answers = list(entry.get("answers") or [])
    paused = False
    while True:
        ex = read_exit(root, spec.name, task) or {}
        if ex.get("exit_code") != int(ExitCode.PAUSED):
            break
        if not answers:
            paused = True
            break
        a = answers.pop(0)
        rs = RunSettings(origin="trial", dry_run=True, caller=caller, relayed=True, sleep=lambda s: None)
        if settings is not None:
            rs = settings(rs)
        got = resume(spec, task, repo, registry, decision=str(a.get("decision") or "proceed"),
                     feedback=a.get("feedback"), settings=rs)
        if got.exit_code is ExitCode.USAGE:
            paused = True
            break
    recs = _records(root, spec.name, task)
    ex = read_exit(root, spec.name, task) or {}
    finished = ex.get("exit_code") == int(ExitCode.FINISHED)
    work = Path(str(next((r.get("path") for r in reversed(recs) if r.get("kind") == "workspace"
                          and r.get("path")), repo)))
    failures = assertion_failures(entry["end_state"], work, gitmod.changed_paths(work, case.base)) \
        if finished and work.is_dir() else []
    more = {"cost_usd": round(run_cost(recs), 6), "failures": failures, "binding": binding, "task": task}
    if paused:
        return _row(run_id, "workflow", spec.name, case.case_id, entry["role"], trial, "paused", "code", **more)
    last = next((str(r.get("unit")) for r in reversed(recs) if r.get("kind") == "judgement"), "")
    grader = "outcome" if spec.outcome is not None else last
    _, by_code = _unit_end(recs, last) if last else (0, True)
    status, by = grade(finished=finished, failures=failures, covered=bool(entry.get("covered")),
                       failed_by_code=by_code, judge_state=judge_state(grader) if grader else "unscored")
    return _row(run_id, "workflow", spec.name, case.case_id, entry["role"], trial, status, by, **more)


def run(spec: WorkflowSpec, kind: str, root: Path, *, registry: Any = None, repo: Path | None = None,
        executor: Any = None, role: str | None = None, trials: int | None = None, cap_usd: float | None = None,
        judge_state: Callable[[str], str] | None = None, settings: Callable[..., Any] | None = None,
        write: bool = True) -> dict[str, Any]:
    """`evals run`: the suites of one kind, recorded. A cap reached keeps the record `partial` (EVS-B6)."""
    from tempergraph.improve import calibration

    if kind not in KINDS:
        raise SuiteRefused(f"unknown suite kind {kind!r} ({', '.join(KINDS)})")
    if role is not None and role not in ROLES:
        raise SuiteRefused(f"unknown role {role!r} ({', '.join(ROLES)})")
    refuse_live(kind, executor)
    run_id = uuid.uuid4().hex[:12]
    cap = DEFAULT_CAP_USD if cap_usd is None else float(cap_usd)
    state_of = judge_state or calibration.state_name_for(spec, root)
    rows: list[dict[str, Any]] = []
    invalid: list[dict[str, str]] = []
    spent, partial = 0.0, False

    def take(row: dict[str, Any]) -> None:
        nonlocal spent
        rows.append(row)
        spent += float(row.get("cost_usd") or 0.0)

    if kind == "check":
        rows = [r for r in run_checks(spec, run_id) if role in (None, r["role"])]
    elif kind == "step":
        cases, invalid = step_cases(spec)
        for c in cases:
            if role not in (None, c.role):
                continue
            for t in range(1, (trials or c.trials) + 1):
                if spent >= cap:
                    partial = True
                    break
                take(run_step_trial(spec, c, registry, t, run_id, judge_state=state_of, settings=settings))
    elif kind == "workflow":
        if repo is None:
            raise SuiteRefused("a workflow suite needs the repository its cases are based on")
        for e in workflow_cases(spec):
            if role not in (None, e["role"]):
                continue
            for t in range(1, (trials or e["trials"]) + 1):
                if spent >= cap:
                    partial = True
                    break
                take(run_workflow_trial(spec, e, repo, registry, t, run_id, judge_state=state_of,
                                        settings=settings))
    else:  # judge: each judged gate's gold set, scored under the same cap (JCL)
        for gate in calibration.judged_gates(spec):
            for level in [None, *calibration.levels(spec, gate)[1:]]:
                if spent >= cap:
                    partial = True
                    break
                try:
                    rec = calibration.score(spec, gate, executor, cap_usd=cap - spent, level=level)
                except calibration.CalibrationError as exc:
                    invalid.append({"unit": gate, "case": level or "", "reason": str(exc)[:120]})
                    continue
                partial = partial or bool(rec.get("partial"))
                name = calibration.state(spec, gate, level=level).state
                take(_row(run_id, "judge", gate, level or "judge", "regression", 1,
                          "passed" if name in ("accepted", "provisional") else "failed", "gold",
                          score_id=rec["score_id"], state=name, cost_usd=rec["usage"]["cost_usd"]))
    for r in rows:
        r.update(partial=partial, workflow=spec.name)
    if write:
        for r in rows:
            append_jsonl(results_path(root), r)
    return {"schema_version": 1, "run_id": run_id, "workflow": spec.name, "kind": kind, "partial": partial,
            "cost_usd": round(spent, 6), "cap_usd": cap, "results": rows, "invalid": invalid}


# -- reading, grading by a person, figures (EVS-B17, EVS-B18) --------------------------------------------------------

def read_results(root: Path) -> list[dict[str, Any]]:
    try:
        lines = results_path(root).read_text(encoding="utf-8").splitlines()
    except OSError:
        return []
    rows: list[dict[str, Any]] = []
    grades: dict[str, dict[str, Any]] = {}
    for ln in lines:
        try:
            r = json.loads(ln)
        except ValueError:
            continue
        if isinstance(r, dict) and r.get("record") == "grade":
            grades[str(r.get("result_id"))] = r
        elif isinstance(r, dict):
            rows.append(r)
    for r in rows:
        g = grades.get(str(r.get("result_id")))
        if g and r.get("status") == "needs_person":
            r.update(status="passed" if g.get("passed") else "failed", graded_by="person", graded_at=g.get("at"))
    return rows


def person_grade(root: Path, result_id: str, passed: bool, reason: str, by: str) -> dict[str, Any]:
    """`evals grade`: a person's grade for a `needs_person` trial. No model call."""
    row = next((r for r in read_results(root) if r.get("result_id") == result_id), None)
    if row is None:
        raise SuiteRefused(f"no eval result {result_id!r}")
    if row.get("status") != "needs_person":
        raise SuiteRefused(f"result {result_id} is {row.get('status')}, graded by {row.get('graded_by')}: "
                           "only a `needs_person` trial takes a person's grade")
    if not reason.strip():
        raise SuiteRefused("a grade needs a reason")
    rec = {"schema_version": 1, "record": "grade", "result_id": result_id, "passed": bool(passed),
           "reason": reason.strip()[:400], "by": by, "at": now_iso()}
    append_jsonl(results_path(root), rec)
    return rec


def figures(rows: Sequence[Mapping[str, Any]]) -> dict[str, Any]:
    """The figures of one suite run. A `needs_person`, `paused` or `invalid` trial counts in no rate."""
    counted = [r for r in rows if r.get("status") in ("passed", "failed")]
    passing = [r for r in counted if r["status"] == "passed"]
    by_case: dict[str, list[Mapping[str, Any]]] = defaultdict(list)
    for r in rows:
        by_case[str(r.get("case"))].append(r)
    full = [c for c, rs in by_case.items() if all(r.get("status") in ("passed", "failed") for r in rs)]
    all_pass = [c for c in full if all(r["status"] == "passed" for r in by_case[c])]
    cost = sum(float(r.get("cost_usd") or 0.0) for r in rows)
    attempts = [int(r["attempts"]) for r in passing if r.get("attempts")]
    n = len(counted)
    return {"trials": len(rows), "counted": n, "cases": len(by_case),
            "pass_at_1": round(len(passing) / n, 4) if n else None,
            "pass_hat_k": round(len(all_pass) / len(full), 4) if full else None,
            "first_attempt_pass": round(sum(1 for r in counted if r.get("first_attempt")) / n, 4)
            if n and any("first_attempt" in r for r in counted) else None,
            "mean_attempts": round(sum(attempts) / len(attempts), 4) if attempts else None,
            "cost_per_pass": round(cost / len(passing), 6) if passing and cost else None,
            "needs_person": sum(1 for r in rows if r.get("status") == "needs_person")}


def suite_status(role: str, rows: Sequence[Mapping[str, Any]]) -> str:
    """A regression suite fails on one failing case and is `incomplete` while a trial waits on a person or a
    pause (EVS-AC4); a capability suite is tracked as a rate and never fails."""
    if role == "capability":
        return "tracked"
    if any(r.get("status") in ("failed", "invalid") for r in rows):
        return "failed"
    if any(r.get("status") in ("needs_person", "paused") for r in rows) or any(r.get("partial") for r in rows):
        return "incomplete"
    return "passed" if rows else "empty"


def _corrected(spec: WorkflowSpec, gate: str, raw: float | None) -> dict[str, Any]:
    """A judge-graded pass rate with the judge's state and, where it allows, the corrected estimate."""
    from tempergraph.improve import calibration

    try:
        return calibration.corrected(raw, calibration.state(spec, gate))
    except (calibration.CalibrationError, OSError, ValueError):
        return {"raw": raw, "label": "uncorrected (unscored)", "state": "unscored"}


def report(spec: WorkflowSpec, root: Path) -> dict[str, Any]:
    """`evals report`: the latest run of each suite, the graduation list, stale and `needs_person` results,
    and cases that never passed. No model call."""
    rows = [r for r in read_results(root) if r.get("workflow") == spec.name]
    current: dict[str, Callable[[str], str]] = {"step": lambda s: step_binding(spec, s) if s in spec.units else "",
                                               "workflow": lambda s: workflow_binding(spec)}
    suites: dict[tuple[str, str, str], list[dict[str, Any]]] = defaultdict(list)
    for r in rows:
        suites[(str(r.get("kind")), str(r.get("subject")), str(r.get("role")))].append(r)
    out = []
    graduation: list[dict[str, str]] = []
    never: list[dict[str, Any]] = []
    for (kind, subject, role), rs in sorted(suites.items()):
        runs = list(dict.fromkeys(str(r.get("run_id")) for r in rs))
        latest = [r for r in rs if r.get("run_id") == runs[-1]]
        now = current[kind](subject) if kind in current else None
        stale = now is not None and any(r.get("binding") != now for r in latest)
        fig = figures(latest)
        if kind == "step" and any(r.get("graded_by") == "judge" for r in latest):  # EVS-B15
            fig["judge_graded"] = _corrected(spec, subject, fig["pass_at_1"])
        out.append({"kind": kind, "subject": subject, "role": role, "run_id": runs[-1],
                    "status": "stale" if stale else suite_status(role, latest), "figures": fig,
                    "cases": [{"case": r.get("case"), "trial": r.get("trial"), "status": r.get("status"),
                               "graded_by": r.get("graded_by"), "result_id": r.get("result_id")} for r in latest]})
        by_case: dict[str, list[dict[str, Any]]] = defaultdict(list)
        for r in rs:
            by_case[str(r.get("case"))].append(r)
        for case, crs in sorted(by_case.items()):
            counted = [r for r in crs if r.get("status") in ("passed", "failed")]
            if len(counted) >= NEVER_PASSED_MIN and not any(r["status"] == "passed" for r in counted):
                never.append({"kind": kind, "subject": subject, "case": case, "trials": len(counted),
                              "advice": "check the case first"})
            if role == "capability":
                on_now = [r for r in crs if now is None or r.get("binding") == now]
                last = list(dict.fromkeys(str(r.get("run_id")) for r in on_now))[-GRADUATE_RUNS:]
                if len(last) == GRADUATE_RUNS and all(
                        all(r.get("status") == "passed" for r in on_now if r.get("run_id") == rid) for rid in last):
                    graduation.append({"kind": kind, "subject": subject, "case": case})
    waiting = [{"result_id": r.get("result_id"), "kind": r.get("kind"), "subject": r.get("subject"),
                "case": r.get("case"), "command": f"tempergraph evals grade {r.get('result_id')} --pass|--fail "
                                                  "--reason <text>"}
               for r in rows if r.get("status") == "needs_person"]
    return {"schema_version": 1, "workflow": spec.name, "suites": out, "graduation": graduation,
            "needs_person": waiting, "never_passed": never}


def green_model_free(spec: WorkflowSpec) -> list[str]:
    """EVS-B7: the failing cases of the model-free regression suites, for a stamp. A check with no fixture
    has no case to fail; validation warns about it (EVS-B1)."""
    return [f"{r['subject']} {r['case']}: expected {r.get('expected')}, got {'/'.join(r.get('results') or [])}"
            for r in run_checks(spec, "stamp") if r["status"] == "failed"]
