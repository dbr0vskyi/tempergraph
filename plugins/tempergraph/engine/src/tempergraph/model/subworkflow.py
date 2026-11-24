"""The one reader of a sub-workflow's child (SWF-B1, SWF-B5 to SWF-B8, SWF-B12, WFM-AC2).

`validate`, the start, `run --check` and the run of a child all read a child here, so they agree on what a child is.
A child is found by name in the home registry (PKG-B15) or among the engine's own built-in workflows; it is never run
here and no model is called (the run is `tempergraph.run.subrun`). A child that cannot be read is an answer
(`ChildUnknown`), not an exception.
"""

from __future__ import annotations

import re
from collections.abc import Callable, Mapping
from dataclasses import dataclass
from pathlib import Path
from typing import Any

from tempergraph.contracts import UnitSpec, WorkflowSpec
from tempergraph.model import flow
from tempergraph.model.text import input_names
from tempergraph.model.validate import _produced

MAX_DEPTH = 3  # SWF-B6: the parent's child is level one
_RANGE_PART = re.compile(r"^(>=|<=|==|<|>|!=)\s*(\d+(?:\.\d+){0,2})$")  # the grammar of a version range (VER-B14)


@dataclass(frozen=True)
class Child:
    """A readable child: what the checks of SWF-B6 and SWF-B12 need of it."""

    name: str
    version: str
    spec: WorkflowSpec
    inputs: tuple[str, ...]  # every one required (SWF-B6); `request` when the child declares none
    produced: frozenset[str]  # keys some unit of the child makes
    deliverables: tuple[str, ...]  # keys its outcome lists (OUT-B8)
    builtin: bool


@dataclass(frozen=True)
class ChildUnknown:
    """A child that is not registered or does not load (`subworkflow-unknown`)."""

    name: str
    reason: str


Reader = Callable[[str], "Child | ChildUnknown"]


def _child(name: str, spec: WorkflowSpec, builtin: bool) -> Child:
    produced: set[str] = set()
    for u in spec.units.values():
        produced |= _produced(u)
    outcome = spec.outcome
    keys = tuple(str(d["key"]) for d in (outcome.deliverables if outcome is not None else ()) if d.get("key"))
    return Child(name=name, version=spec.version, spec=spec, inputs=tuple(sorted(input_names(spec))),
                 produced=frozenset(produced), deliverables=keys, builtin=builtin or bool(spec.builtin))


def read_child(name: str, home: Path | None = None) -> Child | ChildUnknown:
    """Resolve a child by name: the engine's own built-in, else the home registry's entry, loaded as a package."""
    from tempergraph.catalog import Catalog, builtins

    shipped = builtins(Catalog()).specs
    if name in shipped:
        return _child(name, shipped[name], True)
    from tempergraph.package import registry
    from tempergraph.package.loader import PackageNotLoaded, load_package

    try:
        entries = registry.read_entries(home)
    except registry.RegistryRefusal:
        return ChildUnknown(name, "the registry cannot be read")
    entry = next((e for e in entries if e["name"] == name), None)
    if entry is None:
        return ChildUnknown(name, "no registry entry names it")
    try:
        loaded = load_package(Path(str(entry.get("path") or "")))
    except PackageNotLoaded as exc:
        return ChildUnknown(name, f"it does not load ({exc.reason})")
    except Exception as exc:  # noqa: BLE001 - a bad package is an answer, never a raise
        return ChildUnknown(name, f"it does not load ({type(exc).__name__})")
    return _child(name, loaded.spec, False)


def units_of(spec: WorkflowSpec) -> list[str]:
    """The sub-workflow units of a workflow, in order."""
    return [n for n in spec.order if n in spec.units and spec.units[n].kind == "subworkflow"
            and spec.units[n].subworkflow is not None]


def exposed_keys(unit: UnitSpec, child: Child | ChildUnknown) -> tuple[str, ...]:
    """SWF-B7, SWF-B12: the keys a later unit reads as `{<unit>.<key>}`: `produces`, or with it empty the child's
    deliverables."""
    rec = unit.subworkflow
    if rec is None:
        return ()
    if rec.produces:
        return rec.produces
    return child.deliverables if isinstance(child, Child) else ()


def range_problem(requires: str) -> bool:
    """True when `requires` is not a range of VER-B14: every comma part must match the grammar."""
    parts = [p.strip() for p in requires.split(",") if p.strip()]
    return not parts or any(_RANGE_PART.match(p) is None for p in parts)


def _in_range(version: str, requires: str) -> bool:
    from tempergraph.package.changelog import _in_range as in_range

    try:
        return in_range(version, requires)
    except ValueError:
        return False


def _reach(spec: WorkflowSpec, above: tuple[str, ...], at: str, read: Reader) -> list[tuple[str, str, str]]:
    """The recursion, depth and unknown-child findings of the children below `spec`, reported on the unit `at`."""
    out: list[tuple[str, str, str]] = []
    for uname in units_of(spec):
        rec = spec.units[uname].subworkflow
        assert rec is not None
        out += _link(rec.workflow, above, at, f"{uname} of {above[-1]!r}", read)
    return out


def _link(name: str, above: tuple[str, ...], at: str, where: str, read: Reader) -> list[tuple[str, str, str]]:
    """One edge of the tree: `name` under the workflows in `above`. Returns the findings of it and of what is below."""
    if name in above:
        return [("subworkflow-recursive", at, f"{where}: {name!r} is already above it ({' -> '.join((*above, name))})")]
    if len(above) > MAX_DEPTH:
        return [("subworkflow-depth", at, f"{where}: {name!r} would be level {len(above)}, and nesting stops at "
                                          f"level {MAX_DEPTH}")]
    child = read(name)
    if isinstance(child, ChildUnknown):
        return [("subworkflow-unknown", at, f"{where}: child {name!r} {child.reason}")]
    return _reach(child.spec, (*above, name), at, read)


def unit_problems(parent: WorkflowSpec, unit: str, above: tuple[str, ...] = (),
                  read: Reader = read_child) -> list[tuple[str, str, str]]:
    """The SWF-B6 refusals of one sub-workflow unit as `(code, unit, message)`; `above` names the workflows over `parent`."""
    u = parent.units[unit]
    rec = u.subworkflow
    if rec is None:
        return []
    chain = (*above, parent.name)
    name = rec.workflow
    if name in chain or len(chain) > MAX_DEPTH:
        return _link(name, chain, unit, f"unit {unit!r}", read)
    child = read(name)
    if isinstance(child, ChildUnknown):
        return [("subworkflow-unknown", unit, f"unit {unit!r}: child {name!r} {child.reason}")]
    out = _reach(child.spec, (*chain, name), unit, read)
    if child.builtin:
        out.append(("subworkflow-builtin", unit, f"unit {unit!r}: {name!r} is a built-in workflow and cannot be a child"))
    if rec.requires is not None:
        if range_problem(rec.requires):
            out.append(("subworkflow-version", unit, f"unit {unit!r}: requires {rec.requires!r} is not a version range"))
        elif not _in_range(child.version, rec.requires):
            out.append(("subworkflow-version", unit,
                        f"unit {unit!r}: child {name!r} is at version {child.version}, outside {rec.requires!r}"))
    for key in child.inputs:
        if key not in rec.inputs:
            out.append(("subworkflow-input-missing", unit,
                        f"unit {unit!r}: child {name!r} needs the input {key!r}, which `inputs` does not map"))
    for key in rec.produces:
        if key not in child.produced:
            out.append(("subworkflow-produces", unit,
                        f"unit {unit!r}: `produces` names {key!r}, which no unit of child {name!r} makes"))
    return out


def problems(parent: WorkflowSpec, chain: tuple[str, ...] = (), read: Reader = read_child) -> list[tuple[str, str, str]]:
    """Every SWF-B6 refusal of `parent`'s sub-workflow units; `chain` names the workflows above `parent`."""
    out: list[tuple[str, str, str]] = []
    for unit in units_of(parent):
        out += unit_problems(parent, unit, chain, read)
    return out


def unit_reasons(spec: WorkflowSpec, where: str = "") -> list[str]:
    """WSP-B15 to WSP-B18: what the units of `spec` cannot use outside a git repository, each named with `where`."""
    out: list[str] = []
    for name, u in spec.units.items():
        risk = u.gate.judge.risk if u.gate is not None and u.gate.judge is not None else None
        if risk is not None and any(w.paths or w.min_lines is not None for w in risk.when):
            out.append(f"the risk rule of {where}{name} (changed paths or lines)")
        out += [f"the writer branch {where}{b} of block {where}{name} (its own worktree, merged at the join)"
                for b in flow.writer_branches(spec, name)]
        if flow.writer_map(spec, name):
            out.append(f"the writing concurrent map {where}{name} (each item in its own worktree, merged when all have passed)")
        cx =u.switch.complexity if u.switch is not None else None
        if cx is not None and any(m.stock[:1] == ("changed_paths",) for m in cx.measures):
            out.append(f"the `changed_paths` measure of {where}{name}")
    return out


def needs_git(spec: WorkflowSpec, read: Reader = read_child) -> list[str]:
    """What the child tree under `spec` cannot use outside git (SWF-B6, WSP-B18); empty when no child needs git."""
    out: list[str] = []

    def walk(s: WorkflowSpec, above: tuple[str, ...]) -> None:
        for uname in units_of(s):
            rec = s.units[uname].subworkflow
            assert rec is not None
            if rec.workflow in above or len(above) > MAX_DEPTH:
                continue
            child = read(rec.workflow)
            if isinstance(child, Child):
                out.extend(unit_reasons(child.spec, f"{child.name}/"))
                walk(child.spec, (*above, child.name))

    walk(spec, (spec.name,))
    return out


def child_inputs(unit: UnitSpec, request: Mapping[str, Any], earlier: Mapping[str, Mapping[str, Any]]) -> dict[str, str]:
    """SWF-B7: the child's `request.inputs`: each parameter read from the parent's request text, an earlier unit's key
    (`earlier` maps unit to its artifacts and values) or a quoted literal. A key no unit made is left out, so the child
    sees it as a missing field."""
    rec = unit.subworkflow
    out: dict[str, str] = {}
    if rec is None:
        return out
    for param, src in rec.inputs.items():
        if src == "request":
            out[param] = str((request.get("inputs") or {}).get("request", ""))
        elif len(src) >= 2 and src[0] == src[-1] and src[0] in "\"'":
            out[param] = src[1:-1]
        else:
            owner, _, key = src.partition(".")
            got = (earlier.get(owner) or {}).get(key)
            if got is not None:
                out[param] = str(got)
    return out


def exposed(unit: UnitSpec, child: Child | ChildUnknown, artifacts: Mapping[str, Any], values: Mapping[str, Any]
            ) -> tuple[dict[str, Any], dict[str, Any], list[str]]:
    """SWF-B7: of the child's final artifacts and values, the ones `produces` exposes under the unit's name, and the
    exposed keys the child did not make (each fails the unit's gate as a missing artifact)."""
    keys = exposed_keys(unit, child)
    arts = {k: artifacts[k] for k in keys if k in artifacts}
    vals = {k: values[k] for k in keys if k in values and k not in arts}
    return arts, vals, [k for k in keys if k not in arts and k not in vals]


def mapped_source(unit: UnitSpec, name: str) -> str | None:
    """SWF-B5: the parent unit that made the key `inputs` maps to the child parameter `name` (or that names the
    mapped `<unit>.<key>` itself); None when the parameter reads the request or a literal, or none is mapped."""
    rec = unit.subworkflow
    if rec is None:
        return None
    for param, src in rec.inputs.items():
        if name in (param, src):
            owner, dot, _ = src.partition(".")
            return owner if dot and src[0] not in "\"'" else None
    return None


def is_input_name(unit: UnitSpec, name: str) -> bool:
    """SWF-B5: `name` is a child parameter the parent mapped, or the `<unit>.<key>` it was mapped from."""
    rec = unit.subworkflow
    return rec is not None and any(name in (param, src) for param, src in rec.inputs.items())


def workspace_note(child: Child) -> str | None:
    """SWF-B8: the one note written when the child declares a `run.workspace` of its own, which a child never uses."""
    if child.spec.workspace == "auto":
        return None
    return (f"child {child.name!r} declares run.workspace {child.spec.workspace!r}; it runs in the parent's workspace "
            "and the declaration is ignored")
