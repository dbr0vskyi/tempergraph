"""Loading a workflow package (PKG-B15, PKG-B16, PKG-B17): read-only, calls no model (OVR-B15).

Steps: 1 manifests, 2 interface level, then the dependency gate and the source scan before any import,
3 import under the private name, 4 build, 5 attach `outcome.json`, 6 validation (WFM `validate`, whose
last step is :func:`package_findings`). The Python half is imported from the package folder, never
installed (PKG-B15, PKG-B16, PKG-B17).
"""

from __future__ import annotations

import dataclasses
import importlib
import json
import traceback
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Literal

from tempergraph.constants import LOADS_WORKFLOW_API_FROM, WORKFLOW_API
from tempergraph.contracts import Criterion, GateSpec, WorkflowSpec
from tempergraph.model.validate import Finding
from tempergraph.package import docs_check, importer, rules
from tempergraph.package.inventory import (
    PackageInventory,
    content_digest,
    docs_digest,
    package_files,
    workflow_version,
)
from tempergraph.package.manifest import (
    Manifests,
    Pyproject,
    gate_dependencies,
    read_manifests,
    read_pyproject,
)
from tempergraph.package.scan import scan


class PackageNotLoaded(Exception):
    """`not_loaded: <reason>` (PKG-B15, PKG-B16, PKG-B17, PKG-B11, PKG-B13, PKG-B14, PKG-B18, PKG-B19, PKG-B20, PKG-B23); `findings` carry the codes behind it."""

    def __init__(self, reason: str, detail: str = "", findings: list[Finding] | None = None,
                 remedy: str = "") -> None:
        super().__init__(f"not_loaded: {reason}" + (f" ({detail})" if detail else ""))
        self.reason = reason
        self.detail = detail
        self.findings = findings or []
        self.remedy = remedy


@dataclass(kw_only=True)
class LoadedPackage:
    root: Path
    manifests: Manifests
    pyproject: Pyproject | None
    spec: WorkflowSpec
    inventory: PackageInventory
    content_digest: str
    docs_digest: str
    findings: list[Finding] = field(default_factory=list)  # load-time findings (scan, pyproject, outcome)
    outcome_pending: bool = False  # PKG-B15, PKG-B16, PKG-B17 step 5 waits on OUT's reader (plan T5.8.1)

    @property
    def workflow_version(self) -> str:
        return workflow_version(self.spec.version, self.content_digest)


# The workflow version with its content digest, by package root, as of the last load in this process (VER-B14, VER-B15).
_VERSIONS: dict[Path, str] = {}


def full_version(spec: WorkflowSpec) -> str:
    """`<version>+<digest>` of a loaded package, else the spec's declared version."""
    root = spec.package_root
    if root is None:
        return spec.version
    if root not in _VERSIONS:
        try:
            load_package(root)
        except PackageNotLoaded:
            return spec.version
    return _VERSIONS.get(root, spec.version)


# Load-time findings by package root, so the one validation function reports them (WFM-AC2).
_LOAD_FINDINGS: dict[Path, list[Finding]] = {}


def _detail(exc: BaseException) -> str:
    """WFM-B7: an exception's type only, unless an engine builder raised it (its text names the field)."""
    frames = traceback.extract_tb(exc.__traceback__)
    if isinstance(exc, TypeError) and frames and frames[-1].filename.endswith(("tempergraph/api.py",)):
        return f"TypeError: {exc}"
    return type(exc).__name__


def _stamp_engine(root: Path) -> str | None:
    """`verified_engine` mirrors the stamp's `engine_version` (VER-B16)."""
    try:
        doc = json.loads((root / "stamp.json").read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return None
    return str(doc["engine_version"]) if isinstance(doc, dict) and doc.get("engine_version") else None


def _interface(api: int, engine_api: int, loads_from: int) -> None:
    if api > engine_api:
        raise PackageNotLoaded("workflow_api_newer", f"package level {api}, engine {engine_api}",
                               remedy="update the engine (`tempergraph update`)")
    if api < loads_from:
        raise PackageNotLoaded("workflow_api_retired", f"package level {api}, engine loads from {loads_from}",
                               remedy="upgrade the workflow (`tempergraph upgrade`)")


def _behind(api: int, engine_api: int) -> list[Finding]:
    """PKG-B6 row 2: a package below the engine's level loads, with a warning when the changelog has breaking
    `workflow` entries it has not met."""
    if api >= engine_api:
        return []
    from tempergraph.package.changelog import breaking_since_level

    ids = breaking_since_level(api)
    if not ids:
        return []
    return [Finding("workflow_api_behind", None, f"package level {api}, engine {engine_api}: breaking workflow "
                    f"entries {', '.join(ids)} since; run `tempergraph upgrade-check <workflow>`", "warning")]


def _attach_outcome(spec: WorkflowSpec, root: Path) -> tuple[WorkflowSpec, list[Finding], bool]:
    """Step 5: read `outcome.json` and fill each gate's criteria (OUT-B13, OUT-B14). Pending until OUT's reader exists."""
    try:
        outcome_mod: Any = importlib.import_module("tempergraph.run.outcome")
        read_outcome = outcome_mod.read_outcome
        gate_criteria = outcome_mod.gate_criteria
    except (ImportError, AttributeError):
        return spec, [], True
    got = read_outcome(root)
    if isinstance(got, list):
        return spec, list(got), False
    inline = {u: {c.id for c in unit.gate.criteria if c.id} for u, unit in spec.units.items()}
    units = {}
    for name, unit in spec.units.items():
        extra: list[Criterion] = list(gate_criteria(got, name))
        gate: GateSpec = dataclasses.replace(unit.gate, criteria=(*unit.gate.criteria, *(
            c for c in extra if c.id not in inline[name])))
        units[name] = dataclasses.replace(unit, gate=gate)
    spec = dataclasses.replace(spec, outcome=got, units=units)
    return spec, rules.criteria_twice(spec, inline) + list(outcome_mod.check_against(got, spec)), False


def load_package(package_path: Path, *, engine_api: int = WORKFLOW_API,
                 loads_from: int = LOADS_WORKFLOW_API_FROM) -> LoadedPackage:
    root = package_path.resolve()
    got = read_manifests(root)
    if isinstance(got, list):
        raise PackageNotLoaded("manifest", "; ".join(f.message for f in got if f.severity == "error"), got)
    m = got
    _interface(m.engine.workflow_api, engine_api, loads_from)
    findings: list[Finding] = _behind(m.engine.workflow_api, engine_api)
    py = read_pyproject(root)
    pyproject = py if isinstance(py, Pyproject) else None
    if not isinstance(py, Pyproject):
        findings.append(py)
    deps = pyproject.dependencies if pyproject else ()
    refused = gate_dependencies(deps)
    if refused:
        raise PackageNotLoaded("dependency_refused", refused[0].message, refused)
    entry_dir = root / "workflow" / m.module
    if not (entry_dir / "__init__.py").is_file():
        raise PackageNotLoaded("build", f"workflow/{m.module}/__init__.py is missing")
    scanned = scan(root, m.module, deps)
    blocking = [f for f in scanned if f.severity == "error"]
    if blocking:
        raise PackageNotLoaded(blocking[0].code, blocking[0].message, scanned)
    findings += scanned
    try:
        module = importer.import_entry(m.engine.name, entry_dir)
    except Exception as exc:  # noqa: BLE001 - WFM-B7: the exception type only
        raise PackageNotLoaded("import", type(exc).__name__) from exc
    builder = getattr(module, m.function, None)
    if builder is None or not callable(builder):
        raise PackageNotLoaded("build", f"{m.engine.entry} is not a function of the entry module")
    try:
        spec = builder()
    except Exception as exc:  # noqa: BLE001
        raise PackageNotLoaded("build", _detail(exc)) from exc
    if not isinstance(spec, WorkflowSpec):
        raise PackageNotLoaded("build", "the entry did not return a WorkflowSpec")
    stamp = _stamp_engine(root)
    spec = dataclasses.replace(spec, name=m.engine.name, version=m.version, package_root=root,
                               verified_engine=stamp or spec.verified_engine)
    spec, outcome_findings, pending = _attach_outcome(spec, root)
    findings += outcome_findings
    inventory = package_files(root)
    _LOAD_FINDINGS[root] = list(findings)
    lp = LoadedPackage(root=root, manifests=m, pyproject=pyproject, spec=spec, inventory=inventory,
                       content_digest=content_digest(spec, inventory, deps), docs_digest=docs_digest(inventory),
                       findings=findings, outcome_pending=pending)
    _VERSIONS[root] = lp.workflow_version
    return lp


def load(package_path: Path) -> WorkflowSpec:
    """The PKG-B13, PKG-B15 contract (WFM-B7 `load()`)."""
    return load_package(package_path).spec


def package_findings(spec: WorkflowSpec, mode: Literal["dev", "stable"] | None = None) -> list[Finding]:
    """The package rules of PKG, run as the last step of WFM `validate` for a spec loaded from a package."""
    root = spec.package_root
    if root is None:
        return []
    root = root.resolve()
    got = read_manifests(root)
    if isinstance(got, list):
        return got
    out = list(_LOAD_FINDINGS.get(root, []))
    out += rules.plugin_parts(root, got)
    py = read_pyproject(root)
    inventory = package_files(root)
    if isinstance(py, Pyproject):
        out += rules.layout(root, got, py, inventory)
    out += rules.text_refs(spec, root)
    from tempergraph.package.manifest import over_budget

    out += [Finding("text-over-budget", None, f"{f} holds {n} characters, over its budget of {most} in "  # PKG-B26
                    "tempergraph.json `text_budgets`") for f, n, most in over_budget(root, got.engine.text_budgets)]
    out += rules.check_cases(spec, root)
    out += docs_check.docs_check(spec, root, mode)
    from tempergraph.package.readiness import stable_findings

    out += stable_findings(spec)
    from tempergraph.author.criteria_lint import lint, package_doc

    doc = package_doc(root)  # AUT-B12, AUT-B15, AUT-B19, AUT-B24, AUT-B25: in validation every criteria lint code is a warning
    out += [Finding(f.code, f.unit, f.message, "warning") for f in (lint(doc) if doc is not None else [])]
    from tempergraph.audit.report import parse_ignores

    out += [Finding("audit-ignore-invalid", None, f"tempergraph.json: {p}")  # AUD-AC7
            for p in parse_ignores(got.engine.audit.get("ignore"))[1]]
    seen: set[tuple[str, str | None, str]] = set()
    unique = []
    for f in out:
        key = (f.code, f.unit, f.message)
        if key not in seen:
            seen.add(key)
            unique.append(f)
    return unique
