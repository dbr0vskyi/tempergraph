"""`author verify <workflow>` (SCF-B18, SCF-B19, SCF-B20, SCF-B21, SCF-B22): the ladder that checks an authored workflow, in order, stopping at the
first failing rung. Rungs 1 to 7 and 10 are model-free. Rung 8 grades the judged criteria's seeds with judge
sessions only, and rung 9 starts one consented, capped trial run (`author/trial.py`); both run only when asked,
and the person's yes on the stated cost is what the flag carries (SCF-B11, SCF-B13, SCF-B15, SCF-B16, SCF-B17, SCF-B18, SCF-B19, SCF-B20, SCF-B22)."""

from __future__ import annotations

import json
import tempfile
from collections.abc import Callable, Mapping
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

from tempergraph.contracts import Capabilities, WorkflowSpec
from tempergraph.docs import write_json
from tempergraph.store.layout import now_iso

RUNGS = ("load", "compare", "literals", "generated_tests", "coverage", "audit", "register", "judge_seeds",
         "trial", "stamp")


@dataclass(kw_only=True)
class Rung:
    n: int
    name: str
    state: str = "skipped"  # passed, failed, skipped, refused, waiting (a trial paused for the person)
    findings: list[dict[str, Any]] = field(default_factory=list)  # {code, unit, message, remedy}
    note: str = ""

    def to_json(self) -> dict[str, Any]:
        return {"rung": self.n, "name": self.name, "state": self.state, "note": self.note, "findings": self.findings}


@dataclass(kw_only=True)
class VerifyReport:
    workflow: str
    rungs: list[Rung] = field(default_factory=list)
    warnings: list[dict[str, Any]] = field(default_factory=list)  # audit warnings, shown, not failing
    refused: str = ""
    seeds: list[dict[str, Any]] = field(default_factory=list)  # rung 8: {gate, criterion, seed, expected, got}
    trial: dict[str, Any] | None = None  # rung 9: the trial record kept in `authoring.json`
    usage: dict[str, Any] = field(default_factory=lambda: {"judge_sessions": 0, "cost_usd": 0.0})
    seeds_shown: dict[str, dict[str, str]] | None = None  # rung 8: seeds the author saw, by gate (JCL-B11)
    tuned: list[str] = field(default_factory=list)  # rung 8: seeds moved to `tune` after an edit
    seeds_passed: dict[str, dict[str, str]] | None = None  # rung 8: seeds graded as expected, by gate, with key
    carried: list[str] = field(default_factory=list)  # rung 8: seeds whose earlier pass still holds

    @property
    def ok(self) -> bool:
        return not self.refused and all(r.state in ("passed", "skipped") for r in self.rungs)

    @property
    def exit_code(self) -> int:
        if self.ok:
            return 0
        waiting = not self.refused and all(r.state in ("passed", "skipped", "waiting") for r in self.rungs)
        return 3 if waiting else 2  # 3: the trial paused for the person (CON-B12, CON-B13)

    def to_json(self) -> dict[str, Any]:
        return {"schema_version": 1, "workflow": self.workflow, "ok": self.ok, "refused": self.refused,
                "rungs": [r.to_json() for r in self.rungs], "warnings": self.warnings, "seeds": self.seeds,
                "trial": self.trial, "usage": self.usage, "tuned": self.tuned, "carried": self.carried}


def _row(code: str, unit: str | None, message: str, remedy: str = "") -> dict[str, Any]:
    return {"code": code, "unit": unit, "message": message, "remedy": remedy}


def _json(path: Path) -> Any:
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return None


def _decided(authoring: Any) -> set[str]:
    """Subjects (criterion or unit ids) of the decisions recorded in `authoring.json` (AUT-B22)."""
    if not isinstance(authoring, dict):
        return set()
    return {str(d.get("subject")) for d in authoring.get("decisions") or [] if isinstance(d, dict)
            and d.get("subject")} | {str(d.get("criterion")) for d in authoring.get("decisions") or []
                                     if isinstance(d, dict) and d.get("criterion")}


def _load(root: Path, caps: Mapping[str, Capabilities], rung: Rung) -> Any:
    from tempergraph.model.validate import validate
    from tempergraph.package.loader import PackageNotLoaded, load_package

    try:
        lp = load_package(root)
    except PackageNotLoaded as exc:
        rung.findings.append(_row(exc.reason, None, str(exc), exc.remedy))
        return None
    for f in validate(lp.spec, caps):
        if f.severity == "error":
            rung.findings.append(_row(f.code, f.unit, f.message, "fix the workflow declaration (WFM, OUT-B22)"))
    from tempergraph.author.criteria_lint import lint, package_doc

    doc = package_doc(root)
    for lf in lint(doc) if doc is not None else []:  # AUT-B19, AUT-B20, AUT-B21 at the severities of AUT-B12, AUT-B15, AUT-B19, AUT-B24, AUT-B25
        if lf.severity("check") == "error":
            rung.findings.append(_row(lf.code, lf.unit, lf.message, lf.guidance))
    return lp


def _compare(spec: WorkflowSpec, root: Path, rung: Rung) -> None:
    from tempergraph.author import blueprint as bpm
    from tempergraph.author.compare import compare

    got = bpm.read(root / bpm.BLUEPRINT_FILE)
    if isinstance(got, list):
        rung.findings += [_row(f.code, f.unit, f.message, "fix blueprint.json") for f in got]
        return
    for d in compare(got, spec, _json(root / "outcome.json")):
        j = d.to_json()
        rung.findings.append(_row("blueprint-difference", j.get("unit"), j.get("statement") or str(j),
                                  "fix the workflow, or change the blueprint with the person's yes and record "
                                  "the accepted difference as a decision"))


def _literals(spec: WorkflowSpec, rung: Rung) -> None:
    from tempergraph.author.literals import scan

    for h in scan(spec, cases=True):
        rung.findings.append(_row(f"literal-{h.kind}", None, f"{h.file}:{h.line}: {h.text!r}",
                                  f"generalise it, or record a decision with literal_digest {h.digest}"))


def _tests(root: Path, rung: Rung) -> None:
    from tempergraph.package import selftest

    # a detached helper of the stand-in run may still be writing its record when the folder is removed
    with tempfile.TemporaryDirectory(prefix="tg-verify-", ignore_cleanup_errors=True) as tmp:
        for name in selftest.NAMES:
            work = Path(tmp) / name
            work.mkdir()
            for p in selftest.run(name, root, work):
                rung.findings.append(_row(f"selftest-{name}", None, p, "fix the package, then re-run"))


def _coverage(spec: WorkflowSpec, decided: set[str], rung: Rung) -> None:
    from tempergraph.run.outcome_trust import coverage, trust

    if spec.outcome is None:
        rung.findings.append(_row("outcome-missing", None, "the workflow has no outcome (OUT-B8, OUT-B9)",
                                  "author the outcome first"))
        return
    for cov in coverage(spec.outcome, spec):
        if not cov.covered and cov.criterion not in decided:
            rung.findings.append(_row("outcome-uncovered", None,
                                      f"final criterion {cov.criterion} is at {cov.trust} trust and units "
                                      f"{cov.missing_units} serve it at no trusted level",
                                      "add a check with fixtures on each unit, a person sign-off, or record "
                                      "a decision"))
    from tempergraph.improve.calibration import accepted_for

    accepted = accepted_for(spec)
    pairs = [("outcome", c) for c in spec.outcome.final] + [
        (u, c) for u, io in spec.outcome.intermediate.items() for c in io.criteria]
    for unit, c in pairs:
        if c.severity == "blocker" and trust(c, unit, spec.package_root, accepted) == "unverified" and c.id not in decided:
            rung.findings.append(_row("blocker-unverified", None if unit == "outcome" else unit,
                                      f"blocker {c.id} is verified by nobody",
                                      "verify it, or record the `none` as a decision (AUT-B16, AUT-B17, AUT-B18)"))


def _audit(spec: WorkflowSpec, lp: Any, caps: Mapping[str, Capabilities], target: Path,
           probe: Callable[[str], str | None], rung: Rung, rep: VerifyReport) -> None:
    from tempergraph.audit import AuditContext, audit
    from tempergraph.package.stamp import read_stamp

    got = audit(spec, {"definition", "host"}, AuditContext(target=target, caps=caps, probe=probe),
                manifest=lp.manifests.engine, stamp=read_stamp(lp.root))
    for f in got.findings:
        if f.ignored is not None:
            continue
        row = _row(f.rule, f.unit, f.statement, f.remedy)
        if f.severity == "error":
            rung.findings.append(row)
        elif f.severity == "warning":
            rep.warnings.append(row)
    rung.note = f"{len(rep.warnings)} warnings shown, to fix or ignore with a reason"


def _register(root: Path, caps: Mapping[str, Capabilities], rung: Rung) -> None:
    from tempergraph.package import registry as reg

    try:
        reg.register(root, caps, check_only=True)
        got = reg.register(root, caps)
    except reg.RegistryRefusal as exc:
        rung.findings.append(_row(exc.code, None, str(exc), "see `tempergraph workflows register --check`"))
        rung.findings += [_row(f.code, f.unit, f.message) for f in exc.findings if f.severity == "error"]
        return
    state = got.entry.get("state")
    if state not in ("ok", "pinned"):
        rung.findings.append(_row("register-not-ok", None, f"the registry entry is {state}"))
    rung.note = f"entry {state}"


def _stamp(root: Path, caps: Mapping[str, Capabilities], rung: Rung) -> None:
    from tempergraph.package.stamp import check

    got = check(root, caps, stamp=True, accept_revision=True)
    if got.stamp is None:
        reason = got.refused or "; ".join(f"{v.check}: {v.evidence}" for v in got.checks if v.state == "failed")
        rung.findings.append(_row("stamp-not-written", None, reason, "`tempergraph upgrade-check <workflow> --stamp`"))
        return
    rung.note = f"docs_digest {got.stamp.get('docs_digest')}"


def _seed_rung(spec: WorkflowSpec, executor_for: Callable[[str], Any], cap: float | None, rung: Rung,
               rep: VerifyReport, authoring: Any) -> None:
    from tempergraph.author.trial import seeds

    shown = authoring.get("seeds_shown") if isinstance(authoring, dict) else None
    passed = authoring.get("seeds_passed") if isinstance(authoring, dict) else None
    got = seeds(spec, executor_for, cap, shown if isinstance(shown, dict) else None,
                passed if isinstance(passed, dict) else None)
    rep.seeds_shown = got.shown
    rep.seeds_passed = got.passed
    rep.carried = got.carried
    rep.tuned = got.tuned
    rung.findings += got.findings
    rep.seeds = got.graded
    rep.usage = {"judge_sessions": got.sessions, "cost_usd": round(got.spent, 6)}
    rung.note = f"{len(got.graded)} seed gradings, {got.sessions} judge sessions, ${got.spent:.2f}"
    if got.carried:
        rung.note += f"; {len(got.carried)} seeds kept an earlier pass"


def _trial_rung(spec: WorkflowSpec, case: str, target: Path, registry: Any, caller: Mapping[str, Any],
                cap: float, rung: Rung, rep: VerifyReport) -> None:
    from tempergraph.author.trial import TrialRefused, start_trial

    left = max(cap - float(rep.usage.get("cost_usd") or 0.0), 0.0)
    try:
        rec = start_trial(spec, case, target, registry, caller, left)
    except TrialRefused as exc:
        rung.findings.append(_row(exc.code, None, str(exc), "name a case of evals/cases.json with --case"))
        return
    rep.trial = rec
    report = f"`tempergraph author trial {spec.name}` shows the report; grade each criterion with `author grade`"
    if rec["state"] == "paused":
        rung.state = "waiting"
        rung.note = (f"{rec['thread']} paused: answer it through the run driver (`tempergraph resume {spec.name} "
                     f"{rec['task']} …`), then {report}")
    elif rec["state"] == "partial":
        rung.findings.append(_row("trial-cap-reached", None, f"{rec['thread']} reached the cap of ${left:.2f}; the "
                                  "report is partial", "raise --cap and run the trial again"))
    elif rec["state"] == "refused":
        rung.findings.append(_row(rec.get("reason") or "trial-refused", None, str(rec.get("message") or ""),
                                  "fix the refusal and run the trial again"))
    else:
        from tempergraph.author.trial import rows

        _, outcome = rows(spec, target, rec["task"])
        if outcome is None or outcome.get("verdict") == "not_reached":
            why = rec["reason"] or f"exit {rec['exit_code']}"
            rung.findings.append(_row("trial-not-at-outcome", None, f"{rec['thread']} ended ({why}) before the "
                                      "outcome gate", f"see `tempergraph status {rec['thread']} --detail`"))
        else:
            rec["verdict"] = outcome.get("verdict")
            rung.note = f"{rec['thread']} reached the outcome gate ({rec['verdict']}); {report}"


def verify(root: Path, caps: Mapping[str, Capabilities], *, target: Path,
           probe: Callable[[str], str | None] = lambda name: None, judge_seeds: bool = False,
           trial: bool = False, case: str | None = None, cap: float = 5.0,
           executor_for: Callable[[str], Any] | None = None, registry: Any = None,
           caller: Mapping[str, Any] | None = None) -> VerifyReport:
    """Run the ladder on the package at `root`; record the outcome in its `authoring.json` (`verify`, and the
    trial as `trial`). `executor_for(gate)` gives the judge executor for rung 8; `registry` runs rung 9."""
    rep = VerifyReport(workflow=root.name)
    rungs = [Rung(n=i + 1, name=name) for i, name in enumerate(RUNGS)]
    rep.rungs = rungs
    if trial and not case:
        rep.refused = "trial-needs-case"
    elif (judge_seeds or trial) and (executor_for is None or (trial and registry is None)):
        rep.refused = "no-executor"
    authoring = _json(root / "authoring.json")
    lp = None

    def run(i: int, fn: Callable[[Rung], None]) -> bool:
        r = rungs[i]
        fn(r)
        if r.state != "waiting":
            r.state = "failed" if r.findings else "passed"
        return not r.findings and r.state == "passed"

    def load(r: Rung) -> None:
        nonlocal lp
        lp = _load(root, caps, r)

    ok = run(0, load)
    spec: WorkflowSpec | None = None
    if ok and lp is not None:
        spec = lp.spec
        rep.workflow = spec.name
        ok = (run(1, lambda r: _compare(spec, root, r))
              and run(2, lambda r: _literals(spec, r))
              and run(3, lambda r: _tests(root, r))
              and run(4, lambda r: _coverage(spec, _decided(authoring), r))
              and run(5, lambda r: _audit(spec, lp, caps, target, probe, r, rep))
              and run(6, lambda r: _register(root, caps, r)))
    if ok and spec is not None and rep.refused:
        for i in (7, 8):
            rungs[i].state = "refused"
            rungs[i].note = rep.refused
        rungs[9].note = "not stamped: the ladder did not reach rung 10"
    elif ok and spec is not None:
        if judge_seeds or trial:
            assert executor_for is not None
            ok = run(7, lambda r: _seed_rung(spec, executor_for, cap, r, rep, authoring))
        else:
            rungs[7].note = "not asked"
        if ok and trial:
            assert case is not None
            ok = run(8, lambda r: _trial_rung(spec, case, target, registry, caller or {}, cap, r, rep))
        elif ok:
            rungs[8].note = "not asked"
        if ok:
            run(9, lambda r: _stamp(root, caps, r))
        else:
            rungs[9].note = "not stamped: the ladder did not reach rung 10"
    for r in rungs:
        if r.state == "skipped" and not r.note:
            r.note = "an earlier rung failed"
    if isinstance(authoring, dict) and (root / "authoring.json").is_file():
        authoring = _json(root / "authoring.json") or authoring  # register and stamp do not touch it; re-read
        authoring["verify"] = {"at": now_iso(), "ok": rep.ok,
                               "rungs": {r.name: r.state for r in rungs}}
        if rep.trial is not None:
            authoring["trial"] = rep.trial
        if rep.seeds_shown is not None:
            authoring["seeds_shown"] = rep.seeds_shown
        if rep.seeds_passed is not None:
            authoring["seeds_passed"] = rep.seeds_passed
        write_json(root / "authoring.json", authoring, mode=0o644)
    return rep
