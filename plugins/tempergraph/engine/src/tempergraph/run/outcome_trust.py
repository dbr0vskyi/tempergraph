"""Trust and coverage of the outcome's criteria (OUT-B13, OUT-B14), computed and never stored.

| Trust | When |
|---|---|
| deterministic | `check`, with a must-pass and a must-fail fixture under `evals/checks/<unit>/` |
| calibrated | `judge` whose binding is `accepted` (JCL-B17, read from the package's scores) |
| uncalibrated | `judge` in any other state, or `check` without both fixtures |
| human | `person` |
| unverified | `none` |

Coverage, release 1 reading: a final criterion is covered when the outcome gate verifies it at deterministic,
calibrated or human trust, or when every model step and script unit with a gate has an intermediate
criterion serving it at such trust (OUT-B13, OUT-B14 says "on every path to the outcome gate"; release 1 flows are
routes and switches over `order`, so every gated unit stands in for every path). This reading lets a
workflow whose final criteria are judged, before any judge is calibrated, be covered by its units' checks
(SCF-B3); recorded in SCF-B11, SCF-B13, SCF-B15, SCF-B16, SCF-B17, SCF-B18, SCF-B19, SCF-B20, SCF-B22.
"""

from __future__ import annotations

from collections.abc import Callable
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

from tempergraph.contracts import Criterion, OutcomeSpec, Trust, WorkflowSpec

TRUSTED: frozenset[str] = frozenset({"deterministic", "calibrated", "human"})


def has_fixtures(root: Path | None, unit: str) -> bool:
    if root is None:
        return False
    base = root / "evals" / "checks" / unit
    return any((base / "must-pass").glob("*")) and any((base / "must-fail").glob("*"))


def trust(c: Criterion, unit: str, root: Path | None, accepted: Callable[[str], bool] = lambda gate: False) -> Trust:
    """OUT-B13, OUT-B14 for one criterion on `unit` (`outcome` for a final criterion)."""
    if c.verified_by == "person":
        return "human"
    if c.verified_by == "none":
        return "unverified"
    if c.verified_by == "check" or (c.verified_by is None and c.mechanical):
        return "deterministic" if has_fixtures(root, unit) else "uncalibrated"
    return "calibrated" if accepted(unit) else "uncalibrated"


@dataclass(kw_only=True)
class Coverage:
    criterion: str
    trust: Trust
    covered: bool
    serving: list[dict[str, Any]] = field(default_factory=list)  # {unit, criterion, trust}
    missing_units: list[str] = field(default_factory=list)


def _accepted(spec: WorkflowSpec) -> Callable[[str], bool]:
    from tempergraph.improve.calibration import accepted_for

    return accepted_for(spec)


def coverage(outcome: OutcomeSpec, spec: WorkflowSpec,
             accepted: Callable[[str], bool] | None = None) -> list[Coverage]:
    root = spec.package_root
    accepted = accepted or _accepted(spec)
    gated = [n for n in spec.order if (u := spec.units.get(n)) is not None
             and (u.kind == "step" or u.gate.check is not None or u.gate.judge is not None)]
    out = []
    for fc in outcome.final:
        fid = fc.id or ""
        own = trust(fc, "outcome", root, accepted)
        serving = []
        for unit, io in outcome.intermediate.items():
            for c in io.criteria:
                if fid in c.serves:
                    serving.append({"unit": unit, "criterion": c.id, "trust": trust(c, unit, root, accepted)})
        trusted_units = {s["unit"] for s in serving if s["trust"] in TRUSTED}
        missing = [u for u in gated if u not in trusted_units]
        out.append(Coverage(criterion=fid, trust=own, covered=own in TRUSTED or (bool(gated) and not missing),
                            serving=serving, missing_units=missing))
    return out


def profile(outcome: OutcomeSpec, spec: WorkflowSpec, accepted: Callable[[str], bool] | None = None
            ) -> dict[str, int]:
    """Counts per trust over every criterion, final and intermediate (`outcome show`)."""
    counts: dict[str, int] = {}
    root = spec.package_root
    accepted = accepted or _accepted(spec)
    for c in outcome.final:
        t = trust(c, "outcome", root, accepted)
        counts[t] = counts.get(t, 0) + 1
    for unit, io in outcome.intermediate.items():
        for c in io.criteria:
            t = trust(c, unit, root, accepted)
            counts[t] = counts.get(t, 0) + 1
    return counts
