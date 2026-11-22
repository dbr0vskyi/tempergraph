"""The workflow catalog and request resolution (CLI-B7, CLI-B8, CLI-B14, CON-B9, UPD-B20 to UPD-B24).

The catalog reads the home registry (`registry.json`, UPD-B20 to UPD-B24) and loads each entry's package by PKG-B15, PKG-B16, PKG-B17
(`tempergraph.package.loader`): both manifests, the interface level, the dependency gate and the source
scan, the import under the package's private name, the build and the outcome.
"""

from __future__ import annotations

import dataclasses
import hashlib
import json
import re
from collections.abc import Mapping
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

from tempergraph.constants import SCHEMA
from tempergraph.contracts import Question, ResolveResult, WorkflowSpec
from tempergraph.package.loader import LoadedPackage, PackageNotLoaded
from tempergraph.package.loader import load_package as _load
from tempergraph.store.layout import home_path

TASK_ID = re.compile(r"^[A-Za-z0-9][A-Za-z0-9._-]{0,63}$")
TRACKER_KEY = re.compile(r"^[A-Z][A-Z0-9]{0,9}-[0-9]{1,9}$")


@dataclass(kw_only=True)
class Catalog:
    specs: dict[str, WorkflowSpec] = field(default_factory=dict)
    broken: dict[str, str] = field(default_factory=dict)  # name -> not_loaded reason
    packages: dict[str, LoadedPackage] = field(default_factory=dict)  # name -> digests and load findings
    compat: dict[str, str] = field(default_factory=dict)  # name -> VER-B2, VER-B5 state

    def to_json(self) -> dict[str, Any]:
        rows = [{"name": n, "version": s.version, "state": "ok", "description": s.routing.description,
                 "when_to_use": s.routing.when_to_use, "task_kind": s.routing.task_kind, "input": s.input.kind,
                 "units": list(s.order),
                 "workflow_version": self.packages[n].workflow_version if n in self.packages else None,
                 "compatibility": self.compat.get(n)}
                for n, s in sorted(self.specs.items()) if not s.builtin]  # a built-in is no routing target
        rows += [{"name": n, "state": "not_loaded", "reason": r} for n, r in sorted(self.broken.items())]
        return {"schema_version": SCHEMA.get("catalog", 1), "workflows": rows}


def load_package(path: Path) -> WorkflowSpec:
    """PKG-B15, PKG-B16, PKG-B17; read-only, calls no model."""
    return _load(path).spec


def _compat(loaded: LoadedPackage) -> str:
    """VER-B2, VER-B5, read-only and model-free; the state is a catalog column and never refuses on its own."""
    from tempergraph.package.changelog import compatibility
    from tempergraph.package.stamp import read_stamp

    try:
        return str(compatibility(loaded.spec, loaded.root, read_stamp(loaded.root))["state"])
    except (OSError, ValueError):
        return "unknown"


def builtins(cat: Catalog) -> Catalog:
    """The engine's own workflows, added after every package so none can shadow them (UWF-B6, UWF-B5, UWF-B7)."""
    from tempergraph.builtin import upgrade

    cat.broken.pop(upgrade.NAME, None)
    cat.packages.pop(upgrade.NAME, None)
    cat.specs[upgrade.NAME] = upgrade.workflow()
    return cat


def from_registry(home: Path | None = None) -> Catalog:
    cat = Catalog()
    reg = (home or home_path()) / "registry.json"
    if not reg.exists():
        return builtins(cat)
    try:
        entries = json.loads(reg.read_text(encoding="utf-8")).get("workflows") or []
    except (OSError, ValueError, AttributeError):
        return builtins(cat)
    for e in entries:
        name = str(e.get("name") or "")
        if not name:
            continue
        try:
            loaded = _load(Path(str(e.get("path") or "")))
            cat.specs[name], cat.packages[name] = loaded.spec, loaded
            cat.compat[name] = _compat(loaded)
        except PackageNotLoaded as exc:
            cat.broken[name] = exc.reason
    return builtins(cat)


def _digest(text: str, n: int = 10) -> str:
    return hashlib.sha256(" ".join(text.split()).encode()).hexdigest()[:n]


def resolve_request(spec: WorkflowSpec, words: list[str], inputs: Mapping[str, str], cwd: Path,
                    task_id: str | None = None) -> ResolveResult:
    """Turn a start request into a task source with a stable id; read-only, model-free.

    Without a resolver the id is the request's own: a tracker key as given, else `t-<hash>` of the
    whitespace-normalised text, so the same request finds the same thread (ROP-B1 to ROP-B13)."""
    text = " ".join(words).strip()
    if task_id is not None and not TASK_ID.match(task_id):
        return ResolveResult(status="error", message=f"task id {task_id!r}: 1 to 64 letters, digits, '.', '_' or '-'")
    decl = spec.input
    if decl.kind == "resolver" and decl.resolver is not None:
        try:
            res = decl.resolver.resolve()(text)
        except Exception as exc:  # noqa: BLE001 - a resolver's failure is the workflow's, shown as broken
            raise PackageNotLoaded("resolver", type(exc).__name__) from exc
        if not isinstance(res, ResolveResult):
            raise PackageNotLoaded("resolver", "the resolver did not return a ResolveResult")
        if res.status == "ok":
            res = dataclasses.replace(res, task_id=task_id or res.task_id,
                                      inputs={"request": text, **dict(res.inputs), **dict(inputs)})
        return res
    if not text:
        return ResolveResult(status="needs", questions=(Question(name="request", question="What should the run do?"),))
    merged = {"request": text, **dict(inputs)}
    if decl.kind == "tracker_key":
        if not TRACKER_KEY.match(text):
            return ResolveResult(status="error", message=f"{text!r} is not a tracker key such as ABC-123")
        return ResolveResult(status="ok", task_id=task_id or text, inputs=merged)
    if decl.kind == "file":
        p = (cwd / text).resolve()
        if not p.is_file():
            return ResolveResult(status="error", message=f"{text}: no such file")
        stem = re.sub(r"[^A-Za-z0-9._-]+", "-", p.stem)[:40].strip("-") or "file"
        return ResolveResult(status="ok", task_id=task_id or f"f-{stem}-{_digest(str(p), 6)}",
                             inputs={**merged, "file": str(p)})
    return ResolveResult(status="ok", task_id=task_id or f"t-{_digest(text)}", inputs=merged)
