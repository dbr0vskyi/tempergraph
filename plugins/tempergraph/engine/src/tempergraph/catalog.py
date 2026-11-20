"""The workflow catalog and request resolution (CLI §2, CON §2.3, PKG §2.3 steps 1, 3 and 4).

Release 1 at T6.1 reads the home registry (`registry.json`, UPD §2.8) and loads each entry's package with the
first steps of PKG §2.3: the two manifests, the entry import from `workflow/`, and the build. The private
import name, the source scan, the interface level, `outcome.json` and the package rules land with T8.1.
"""

from __future__ import annotations

import dataclasses
import hashlib
import importlib
import json
import re
import sys
from collections.abc import Mapping
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

from tempergraph.constants import SCHEMA
from tempergraph.contracts import Question, ResolveResult, WorkflowSpec
from tempergraph.store.layout import home_path

TASK_ID = re.compile(r"^[A-Za-z0-9][A-Za-z0-9._-]{0,63}$")
TRACKER_KEY = re.compile(r"^[A-Z][A-Z0-9]{0,9}-[0-9]{1,9}$")


class PackageNotLoaded(Exception):
    def __init__(self, reason: str, detail: str = "") -> None:
        super().__init__(f"not_loaded: {reason}" + (f" ({detail})" if detail else ""))
        self.reason = reason


@dataclass(kw_only=True)
class Catalog:
    specs: dict[str, WorkflowSpec] = field(default_factory=dict)
    broken: dict[str, str] = field(default_factory=dict)  # name -> not_loaded reason

    def to_json(self) -> dict[str, Any]:
        rows = [{"name": n, "version": s.version, "state": "ok", "description": s.routing.description,
                 "when_to_use": s.routing.when_to_use, "task_kind": s.routing.task_kind, "input": s.input.kind,
                 "units": list(s.order)} for n, s in sorted(self.specs.items())]
        rows += [{"name": n, "state": "not_loaded", "reason": r} for n, r in sorted(self.broken.items())]
        return {"schema_version": SCHEMA.get("catalog", 1), "workflows": rows}


def _json(path: Path) -> dict[str, Any]:
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, ValueError) as exc:
        raise PackageNotLoaded("manifest", f"{path.name}: {type(exc).__name__}") from exc
    if not isinstance(data, dict):
        raise PackageNotLoaded("manifest", f"{path.name} is not an object")
    return data


def load_package(path: Path) -> WorkflowSpec:
    """PKG §2.3 steps 1, 3 and 4; read-only, calls no model."""
    plugin = _json(path / ".claude-plugin" / "plugin.json")
    engine = _json(path / "tempergraph.json")
    if engine.get("schema_version") != 1 or not engine.get("name") or plugin.get("name") != engine.get("name"):
        raise PackageNotLoaded("manifest", "names differ or schema_version unknown")
    module, _, func = str(engine.get("entry") or "").partition(":")
    if not module or not func:
        raise PackageNotLoaded("manifest", "entry must be <module>:<function>")
    src = str((path / "workflow").resolve())
    if src not in sys.path:
        sys.path.insert(0, src)
    try:
        builder = getattr(importlib.import_module(module), func)
    except Exception as exc:  # noqa: BLE001 - WFM §4: the exception type only
        raise PackageNotLoaded("import", type(exc).__name__) from exc
    try:
        spec = builder()
    except Exception as exc:  # noqa: BLE001
        raise PackageNotLoaded("build", type(exc).__name__) from exc
    if not isinstance(spec, WorkflowSpec):
        raise PackageNotLoaded("build", "the entry did not return a WorkflowSpec")
    return dataclasses.replace(spec, name=str(engine["name"]), version=str(plugin.get("version") or ""))


def from_registry(home: Path | None = None) -> Catalog:
    cat = Catalog()
    reg = (home or home_path()) / "registry.json"
    if not reg.exists():
        return cat
    try:
        entries = json.loads(reg.read_text(encoding="utf-8")).get("workflows") or []
    except (OSError, ValueError, AttributeError):
        return cat
    for e in entries:
        name = str(e.get("name") or "")
        if not name:
            continue
        try:
            cat.specs[name] = load_package(Path(str(e.get("path") or "")))
        except PackageNotLoaded as exc:
            cat.broken[name] = exc.reason
    return cat


def _digest(text: str, n: int = 10) -> str:
    return hashlib.sha256(" ".join(text.split()).encode()).hexdigest()[:n]


def resolve_request(spec: WorkflowSpec, words: list[str], inputs: Mapping[str, str], cwd: Path,
                    task_id: str | None = None) -> ResolveResult:
    """Turn a start request into a task source with a stable id; read-only, model-free.

    Without a resolver the id is the request's own: a tracker key as given, else `t-<hash>` of the
    whitespace-normalised text, so the same request finds the same thread (CLI §2.1)."""
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
