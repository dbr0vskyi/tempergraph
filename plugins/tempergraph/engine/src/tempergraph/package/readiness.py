"""The structural judge readiness report (LIF-B7 to LIF-B16, LIF-B6): per judged gate, model-free.

Grades: `ready` (structure clean and the judge binding `accepted` under JCL), `needs cases` (structure clean,
not accepted), `needs work` (a structural finding). Acceptance is read from the package's calibration scores
(JCL-B17, `improve/calibration.py`), so a workflow in `stable` mode is refused with `gate-not-ready` until
every judged gate is `accepted` (LIF-B6).
"""

from __future__ import annotations

from collections.abc import Callable, Iterable
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

from tempergraph.contracts import Criterion, WorkflowSpec
from tempergraph.model import flow
from tempergraph.model.prompt_lint import VAGUE
from tempergraph.model.validate import Finding

SCALE_FIELDS = ("met", "unmet", "evidence")


@dataclass(kw_only=True)
class GateReadiness:
    gate: str
    grade: str
    findings: list[str] = field(default_factory=list)
    criteria: int = 0
    blockers: int = 0
    calibration_cases: int = 0
    acceptance: str = "unscored"

    def to_json(self) -> dict[str, Any]:
        return {"gate": self.gate, "grade": self.grade, "findings": self.findings, "criteria": self.criteria,
                "blockers": self.blockers, "calibration_cases": self.calibration_cases, "acceptance": self.acceptance}


def _structural(c: Criterion) -> list[str]:
    out: list[str] = []
    if c.mechanical or c.verified_by in ("check", "person", "none"):
        return out
    if not c.check_method.strip():
        out.append(f"{c.id or c.text[:30]}: no check method")
    if c.verified_by == "judge":
        scale = dict((c.verifier or {}).get("scale") or {})
        missing = [f for f in SCALE_FIELDS if not str(scale.get(f) or "").strip()]
        if c.severity == "blocker" and not str(scale.get("partial") or "").strip():
            missing.append("partial")
        if missing:
            out.append(f"{c.id}: scale lacks {', '.join(missing)} (OUT-B11)")
    low = c.text.lower()
    vague = [w for w in VAGUE if w in low]
    if vague:
        out.append(f"{c.id or c.text[:30]}: vague wording {', '.join(repr(w) for w in vague)}")
    return out


def _cases(root: Path | None, gate: str) -> int:
    folder = root / "evals" / "calibration" / gate if root is not None else None
    return sum(1 for p in folder.iterdir() if not p.name.startswith(".") and p.name != "scores.jsonl"
               ) if folder and folder.is_dir() else 0


def _gates(spec: WorkflowSpec) -> Iterable[tuple[str, list[Criterion]]]:
    for name in spec.order:
        u = spec.units.get(name)
        if u is not None and u.gate.judge is not None:
            yield name, list(u.gate.criteria)
    if spec.outcome is not None and spec.outcome.final:
        yield flow.OUTCOME_UNIT, list(spec.outcome.final)


def readiness(spec: WorkflowSpec, accepted: Callable[[str], bool] | None = None,
              state_of: Callable[[str], str] | None = None) -> list[GateReadiness]:
    """`accepted(gate)` answers whether the gate's judge binding is `accepted` (JCL-B17); by default it is
    read from the package's calibration scores (`improve/calibration.py`), as is `state_of(gate)`."""
    from tempergraph.author.criteria_lint import lint, package_doc

    if accepted is None:
        from tempergraph.improve import calibration

        accepted = calibration.accepted_for(spec)
        state_of = state_of or calibration.state_name_for(spec)

    doc = package_doc(spec.package_root)
    linted = lint(doc) if doc is not None else []
    out = []
    for gate, criteria in _gates(spec):
        notes = [n for c in criteria for n in _structural(c)]
        mine = [f for f in linted if (f.unit or flow.OUTCOME_UNIT) == gate and f.criterion is not None]
        notes += [f"{f.code}: {f.message}" for f in mine if f.code != "criterion-no-seed"]
        seedless = [f.criterion for f in mine if f.code == "criterion-no-seed"]
        judged = [c for c in criteria if not c.mechanical and c.verified_by not in ("check", "person", "none")]
        blockers = sum(1 for c in judged if c.severity == "blocker")
        if judged and not blockers:
            notes.append("no judged criterion is a blocker, so the judge can never send the work back")
        ok = accepted(gate)
        grade = "needs work" if notes else ("ready" if ok else "needs cases")
        # AUT-B12, AUT-B15, AUT-B19, AUT-B24, AUT-B25: a missing seed is a calibration gap, shown but not graded as structural
        notes += [f"criterion-no-seed: {c} has no met and unmet seed" for c in seedless]
        out.append(GateReadiness(gate=gate, grade=grade, findings=notes, criteria=len(criteria), blockers=blockers,
                                 calibration_cases=_cases(spec.package_root, gate),
                                 acceptance=state_of(gate) if state_of else ("accepted" if ok else "unscored")))
    return out


def stable_findings(spec: WorkflowSpec) -> list[Finding]:
    """LIF-B6: a `stable` workflow needs every judged gate `ready`."""
    if spec.improvement_mode != "stable":
        return []
    from tempergraph.improve import calibration

    def why(g: GateReadiness) -> str:
        if g.findings:
            return f": {'; '.join(g.findings)}"
        raised = calibration.unaccepted_levels(spec, g.gate)  # JRK-B5: every routed level, with what fixes it
        if raised and g.acceptance == "accepted":
            return "; " + "; ".join(f"risk level {lv!r} is {st}: run `tempergraph evals score {spec.name} {g.gate} "
                                    f"--level {lv}`" for lv, st in raised)
        return " (no accepted judge binding)"

    return [Finding("gate-not-ready", g.gate, f"`stable` needs the gate `ready`; it is {g.grade!r}" + why(g))
            for g in readiness(spec) if g.grade != "ready"]
