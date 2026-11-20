"""`upgrade --check [--stamp]` and `upgrade-check [--stamp]` in release 1 (WUP §2.1, §2.6; VER §2.5).

Release 1 builds the check and the stamp only; the transforms, the upgrade workflow, the branch and the pull
request are release 3 (ADR-0090). `--check` runs WUP phases 1 to 3 (locate, baseline, plan) read-only.
`--stamp` on a clean check runs the model-free verification V1 to V7 and writes `stamp.json` in the
package. V4 (audit) and V6 (model-free suites) report `skipped` with their reason until audit (plan T8.5)
and eval suites (release 2) exist. V7 regenerates `diagram/` with the stamp, because the diagram is generated
and never typed (PKG §2.1).
"""

from __future__ import annotations

import json
from collections.abc import Mapping
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

from tempergraph.constants import ENGINE_VERSION, WORKFLOW_API
from tempergraph.contracts import READ_ONLY_CAPABILITIES, Capabilities, WorkflowSpec
from tempergraph.docs import write_json
from tempergraph.executors.capabilities import DECLARED
from tempergraph.model.diagram import diagram_model, to_mermaid
from tempergraph.model.validate import Finding, validate
from tempergraph.package.changelog import compatibility
from tempergraph.package.loader import LoadedPackage, PackageNotLoaded, load_package
from tempergraph.package.registry import plugin_cache
from tempergraph.store.layout import now_iso

STAMP = "stamp.json"


def read_stamp(root: Path) -> dict[str, Any] | None:
    try:
        doc = json.loads((root / STAMP).read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return None
    return doc if isinstance(doc, dict) and doc.get("engine_version") else None


def tool_set(spec: WorkflowSpec) -> dict[str, list[str]]:
    """Per executor, the tool names the steps and judges were checked against (VER §2.5 `tool_set`)."""
    out: dict[str, set[str]] = {}
    for u in spec.units.values():
        ex = (u.step.executor if u.step else None) or spec.default_executor
        caps = DECLARED.get(ex)
        if caps is None:
            continue
        names = out.setdefault(ex, set())
        tools = list(u.step.tools) if u.step else []
        if u.gate.judge is not None:
            tools += sorted(READ_ONLY_CAPABILITIES & {"read", "search", "list"})
        for t in tools:
            key = "mcp:*" if t.startswith("mcp:") else "skill:*" if t.startswith("skill:") else t
            names.update(n.replace("{server}", t[4:].split("/")[0]).replace("{tool}", t.split("/")[-1])
                         for n in caps.tool_map.get(key, ()))
    return {k: sorted(v) for k, v in sorted(out.items())}


@dataclass(kw_only=True)
class Verification:
    check: str
    state: str  # passed, failed, skipped
    evidence: str = ""


@dataclass(kw_only=True)
class StampReport:
    workflow: str
    exit_code: int = 0
    compat: dict[str, Any] = field(default_factory=dict)
    pending: list[dict[str, Any]] = field(default_factory=list)
    checks: list[Verification] = field(default_factory=list)
    findings: list[Finding] = field(default_factory=list)
    stamp: dict[str, Any] | None = None
    refused: str = ""

    def to_json(self) -> dict[str, Any]:
        return {"schema_version": 1, "workflow": self.workflow, "exit_code": self.exit_code, "refused": self.refused,
                "compatibility": self.compat, "pending": self.pending,
                "verification": [v.__dict__ for v in self.checks],
                "findings": [{"severity": f.severity, "code": f.code, "unit": f.unit, "message": f.message}
                             for f in self.findings],
                "stamp": self.stamp}


def _diagram_current(lp: LoadedPackage, model: Mapping[str, Any]) -> bool:
    try:
        doc = json.loads((lp.root / "diagram" / "model.json").read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return False
    return isinstance(doc, dict) and doc.get("digest") == model.get("digest")


def check(path: Path, caps: Mapping[str, Capabilities], *, stamp: bool = False,
          fail_on_pending: bool = False) -> StampReport:
    root = path.resolve()
    rep = StampReport(workflow=root.name)
    if root.is_relative_to(plugin_cache().resolve()):  # WUP §2.2: phase 1 locate
        rep.refused, rep.exit_code = "upgrade the workflow's source; this is an installed copy", 2
        return rep
    try:
        lp = load_package(root)  # V1
    except PackageNotLoaded as exc:
        rep.checks.append(Verification(check="V1 load", state="failed", evidence=str(exc)))
        rep.exit_code = 4 if stamp else 2
        return rep
    rep.workflow = lp.spec.name
    rep.checks.append(Verification(check="V1 load", state="passed", evidence=lp.workflow_version))
    found = validate(lp.spec, caps)  # baseline and V2
    rep.findings = found
    prior = read_stamp(root)
    rep.compat = compatibility(lp.spec, root, prior, finding_codes={f.code for f in found})
    rep.pending = [{"item_id": eid, "hits": hits} for eid, hits in rep.compat["hits"].items()]
    if not stamp:
        rep.exit_code = 6 if fail_on_pending and rep.pending else 0
        return rep
    errors = [f for f in found if f.severity == "error"]
    rep.checks.append(Verification(check="V2 validation", state="failed" if errors else "passed",
                                   evidence=f"{len(errors)} errors, {len(found) - len(errors)} warnings"))
    rep.checks.append(Verification(check="V3 proof", state="failed" if rep.pending else "passed",
                                   evidence=f"{len(rep.pending)} changelog items pending"))
    rep.checks.append(Verification(check="V4 audit", state="skipped", evidence="audit is plan T8.5"))
    rep.checks.append(Verification(check="V5 change classes", state="passed", evidence="no change was made"))
    rep.checks.append(Verification(check="V6 suites", state="skipped",
                                   evidence="model-free eval suites are release 2 (ADR-0090)"))
    model = diagram_model(lp.spec)
    if any(v.state == "failed" for v in rep.checks):
        rep.exit_code = 4
        return rep
    current = _diagram_current(lp, model)
    write_json(root / "diagram" / "model.json", model, mode=0o644)
    (root / "diagram" / "workflow.md").write_text("```mermaid\n" + to_mermaid(model) + "\n```\n", encoding="utf-8")
    rep.checks.append(Verification(check="V7 diagram", state="passed",
                                   evidence="current" if current else "regenerated"))
    lp = load_package(root)  # the stamp records what the package now holds
    rep.stamp = {
        "schema_version": 1, "engine_version": ENGINE_VERSION, "workflow_api": WORKFLOW_API,
        "workflow_version": lp.workflow_version, "docs_digest": lp.docs_digest, "shape_digest": model["digest"],
        "entries_applied": [{"id": e, "by": "none"} for e in rep.compat["entries"]],
        "tool_set": tool_set(lp.spec),
        "baseline": {"error": 0, "warning": sum(1 for f in found if f.severity == "warning")},
        "stamped_at": now_iso(),
    }
    write_json(root / STAMP, rep.stamp, mode=0o644)
    return rep
