"""`author verify <workflow>` (SCF §2.5): the ladder that checks an authored workflow, in order, stopping at the
first failing rung. Rungs 1 to 7 and 10 are model-free and built in release 1; rungs 8 (judge seeds) and 9
(the first trial) need judge calibration and feedback labels (JCL, FBK; plan T12), so a request for them is
refused with `not_in_release` after rungs 1 to 7 have run, and nothing is stamped (SCF §2.7)."""

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
    state: str = "skipped"  # passed, failed, skipped, refused
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

    @property
    def ok(self) -> bool:
        return not self.refused and all(r.state in ("passed", "skipped") for r in self.rungs)

    @property
    def exit_code(self) -> int:
        return 0 if self.ok else 2

    def to_json(self) -> dict[str, Any]:
        return {"schema_version": 1, "workflow": self.workflow, "ok": self.ok, "refused": self.refused,
                "rungs": [r.to_json() for r in self.rungs], "warnings": self.warnings}


def _row(code: str, unit: str | None, message: str, remedy: str = "") -> dict[str, Any]:
    return {"code": code, "unit": unit, "message": message, "remedy": remedy}


def _json(path: Path) -> Any:
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return None


def _decided(authoring: Any) -> set[str]:
    """Subjects (criterion or unit ids) of the decisions recorded in `authoring.json` (AUT §2.5)."""
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
            rung.findings.append(_row(f.code, f.unit, f.message, "fix the workflow declaration (WFM, OUT §4)"))
    from tempergraph.author.criteria_lint import lint, package_doc

    doc = package_doc(root)
    for lf in lint(doc) if doc is not None else []:  # AUT §2.4.1 at the severities of AUT §2.8
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

    with tempfile.TemporaryDirectory(prefix="tg-verify-") as tmp:
        for name in selftest.NAMES:
            work = Path(tmp) / name
            work.mkdir()
            for p in selftest.run(name, root, work):
                rung.findings.append(_row(f"selftest-{name}", None, p, "fix the package, then re-run"))


def _coverage(spec: WorkflowSpec, decided: set[str], rung: Rung) -> None:
    from tempergraph.run.outcome_trust import coverage, trust

    if spec.outcome is None:
        rung.findings.append(_row("outcome-missing", None, "the workflow has no outcome (OUT §2.1)",
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
                                      "verify it, or record the `none` as a decision (AUT §2.4)"))


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

    got = check(root, caps, stamp=True)
    if got.stamp is None:
        reason = got.refused or "; ".join(f"{v.check}: {v.evidence}" for v in got.checks if v.state == "failed")
        rung.findings.append(_row("stamp-not-written", None, reason, "`tempergraph upgrade-check <workflow> --stamp`"))
        return
    rung.note = f"docs_digest {got.stamp.get('docs_digest')}"


def verify(root: Path, caps: Mapping[str, Capabilities], *, target: Path,
           probe: Callable[[str], str | None] = lambda name: None, judge_seeds: bool = False,
           trial: bool = False, case: str | None = None) -> VerifyReport:
    """Run the ladder on the package at `root`; record the outcome in its `authoring.json` (`verify`)."""
    rep = VerifyReport(workflow=root.name)
    rungs = [Rung(n=i + 1, name=name) for i, name in enumerate(RUNGS)]
    rep.rungs = rungs
    if trial and not case:
        rep.refused = "trial-needs-case"
    authoring = _json(root / "authoring.json")
    lp = None

    def run(i: int, fn: Callable[[Rung], None]) -> bool:
        r = rungs[i]
        fn(r)
        r.state = "failed" if r.findings else "passed"
        return not r.findings

    def load(r: Rung) -> None:
        nonlocal lp
        lp = _load(root, caps, r)

    ok = run(0, load)
    if ok and lp is not None:
        spec = lp.spec
        rep.workflow = spec.name
        ok = (run(1, lambda r: _compare(spec, root, r))
              and run(2, lambda r: _literals(spec, r))
              and run(3, lambda r: _tests(root, r))
              and run(4, lambda r: _coverage(spec, _decided(authoring), r))
              and run(5, lambda r: _audit(spec, lp, caps, target, probe, r, rep))
              and run(6, lambda r: _register(root, caps, r)))
    if ok:
        asked = judge_seeds or trial
        for i in (7, 8):
            wanted = asked if i == 7 else trial
            rungs[i].state = "refused" if wanted else "skipped"
            rungs[i].note = ("not_in_release: judge seeds and the first trial need judge calibration and "
                             "feedback labels (JCL, FBK; plan T12)") if wanted else "not asked"
        if asked or rep.refused:
            rungs[9].note = "not stamped: the ladder did not reach rung 10"
        else:
            run(9, lambda r: _stamp(root, caps, r))
    for r in rungs:
        if r.state == "skipped" and not r.note:
            r.note = "an earlier rung failed"
    if isinstance(authoring, dict) and (root / "authoring.json").is_file():
        authoring["verify"] = {"at": now_iso(), "ok": rep.ok,
                               "rungs": {r.name: r.state for r in rungs}}
        write_json(root / "authoring.json", authoring, mode=0o644)
    return rep
