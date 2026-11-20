"""The home workflow registry, `registry.json` (UPD §2.8, ADR-0060), and the `workflows` verbs' logic.

The registry lives in the home folder, outside every engine environment. No verb but `unregister` removes
an entry; a path that disappeared keeps its entry as `missing`. Loading and validation call no model.

Release 1 has no managed engine environment yet (plan T8.2), so `reinstall` checks each package's declared
requirements against the dependency gate and records their digest, but installs nothing: a package that
declares requirements is reported `dependencies_pending` until the environment exists.
"""

from __future__ import annotations

import hashlib
import json
import os
from collections.abc import Callable, Mapping
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

from tempergraph.constants import ENGINE_VERSION
from tempergraph.contracts import Capabilities
from tempergraph.docs import write_json
from tempergraph.model.validate import Finding, validate
from tempergraph.package.importer import private_name
from tempergraph.package.loader import LoadedPackage, PackageNotLoaded, load_package
from tempergraph.package.manifest import ENGINE_JSON
from tempergraph.store.layout import ensure_home, home_path, lock_path, now_iso

SCHEMA_VERSION = 1
KINDS = ("plugin", "local", "builtin")


class RegistryRefusal(Exception):
    def __init__(self, code: str, message: str, findings: list[Finding] | None = None) -> None:
        super().__init__(f"{code}: {message}")
        self.code = code
        self.findings = findings or []


def plugin_cache() -> Path:
    """Claude Code's plugin cache (R-055 U4); `CLAUDE_CONFIG_DIR` moves it."""
    base = os.environ.get("CLAUDE_CONFIG_DIR")
    return (Path(base) if base else Path.home() / ".claude") / "plugins" / "cache"


def registry_path(home: Path | None = None) -> Path:
    return (home or home_path()) / "registry.json"


def read_entries(home: Path | None = None) -> list[dict[str, Any]]:
    path = registry_path(home)
    try:
        doc = json.loads(path.read_text(encoding="utf-8"))
    except FileNotFoundError:
        return []
    except (OSError, ValueError) as exc:
        raise RegistryRefusal("registry-unreadable", f"{path}: {type(exc).__name__}") from exc
    rows = doc.get("workflows") if isinstance(doc, dict) else None
    return [dict(r) for r in rows or [] if isinstance(r, dict) and r.get("name")]


def write_entries(entries: list[dict[str, Any]], home: Path | None = None) -> None:
    home = ensure_home(home)
    write_json(registry_path(home), {"schema_version": SCHEMA_VERSION,
                                     "workflows": sorted(entries, key=lambda e: str(e["name"]))})


def requirements_digest(deps: tuple[str, ...]) -> str:
    return hashlib.sha256("\n".join(sorted(" ".join(d.split()) for d in deps)).encode()).hexdigest()[:16]


@dataclass(kw_only=True)
class Checked:
    """One load and validation of a registered or candidate package."""

    entry: dict[str, Any]
    loaded: LoadedPackage | None = None
    findings: list[Finding] = field(default_factory=list)
    remedy: str = ""

    @property
    def ok(self) -> bool:
        return self.loaded is not None and not any(f.severity == "error" for f in self.findings)


def check_package(path: Path, caps: Mapping[str, Capabilities], entry: dict[str, Any] | None = None) -> Checked:
    """Load and validate; fill the entry's state, versions and requirement fields."""
    e = dict(entry or {})
    e["last_checked_at"] = now_iso()
    if not path.exists():
        e["state"] = "missing"
        return Checked(entry=e, findings=[Finding("missing", None, f"{path} does not exist")])
    try:
        loaded = load_package(path)
    except PackageNotLoaded as exc:
        e["state"], e["reason"] = "not_loaded", exc.reason
        found = exc.findings or [Finding(exc.reason, None, exc.detail or str(exc))]
        return Checked(entry=e, findings=found, remedy=exc.remedy)
    findings = validate(loaded.spec, caps)
    deps = loaded.pyproject.dependencies if loaded.pyproject else ()
    last_version, last_wv = e.get("version"), e.get("workflow_version")
    if (e.get("kind") == "plugin" and last_version == loaded.spec.version and last_wv
            and last_wv != loaded.workflow_version):
        findings.append(Finding("version-not-bumped", None, f"content changed under version {last_version}; "
                                "the plugin cache is keyed by the version string (VER §2.4)", "warning"))
    e.update(version=loaded.spec.version, workflow_version=loaded.workflow_version,
             requirements_digest=requirements_digest(deps))
    e.pop("reason", None)
    errors = [f for f in findings if f.severity == "error"]
    if errors:
        e["state"], e["reason"] = "not_loaded", "invalid"
    elif e.get("engine_pin"):
        e["state"] = "pinned"
    else:
        e["state"] = "ok"
    if deps and ENGINE_VERSION not in (e.get("installed_into") or []):
        e["dependencies"] = "pending"  # no managed environment before plan T8.2
    else:
        e.pop("dependencies", None)
    return Checked(entry=e, loaded=loaded, findings=findings)


def register(path: Path, caps: Mapping[str, Capabilities], *, check_only: bool = False,
             home: Path | None = None) -> Checked:
    """`workflows register <path> [--check]`: a local source that loads and validates (UPD §2.8)."""
    root = path.expanduser().resolve()
    if root.is_relative_to(plugin_cache().resolve()):
        raise RegistryRefusal("plugin-cache-path", f"{root} is in Claude Code's plugin cache; installed workflow "
                              "plugins are registered by `tempergraph install` or `update`")
    if not (root / ENGINE_JSON).is_file():
        raise RegistryRefusal("not-a-package", f"{root} holds no tempergraph.json, so it is not a workflow package")
    entries = read_entries(home)
    got = check_package(root, caps, {"kind": "local", "path": str(root)})
    if got.loaded is None or not got.ok:
        raise RegistryRefusal("not-valid", f"{root} does not load and validate", got.findings)
    name = got.loaded.spec.name
    for e in entries:
        same_private = private_name(str(e["name"])) == private_name(name)
        if (e["name"] == name or same_private) and Path(str(e.get("path") or "")).resolve() != root:
            raise RegistryRefusal("name-taken", f"workflow {e['name']!r} is registered from {e.get('path')}")
    prior = next((e for e in entries if e["name"] == name), {})
    entry = {**prior, **got.entry, "name": name, "kind": prior.get("kind", "local"), "path": str(root),
             "registered_at": prior.get("registered_at") or now_iso(), "engine_pin": prior.get("engine_pin"),
             "installed_into": prior.get("installed_into") or []}
    got.entry = entry
    if not check_only:
        write_entries([e for e in entries if e["name"] != name] + [entry], home)
    return got


def live_threads(name: str, state_roots: list[Path]) -> list[str]:
    """Threads of the workflow holding a run lock in the given state roots (WSP, DUR)."""
    from tempergraph.durability.lock import is_held

    out = []
    for root in state_roots:
        folder = lock_path(root, name, "x").parent
        for lock in sorted(folder.glob("*.lock")) if folder.is_dir() else []:
            if is_held(lock):
                out.append(f"{name}:{lock.stem}")
    return out


def unregister(name: str, state_roots: list[Path], *, home: Path | None = None) -> dict[str, Any]:
    """Remove the entry only, never files; refused while a thread of it is live (UPD §2.8)."""
    entries = read_entries(home)
    entry = next((e for e in entries if e["name"] == name), None)
    if entry is None:
        raise RegistryRefusal("unknown-workflow", f"{name!r} is not registered")
    live = live_threads(name, state_roots)
    if live:
        raise RegistryRefusal("thread-live", f"{name!r} has live threads: {', '.join(live)}")
    write_entries([e for e in entries if e["name"] != name], home)
    return entry


def reinstall(names: list[str] | None, caps: Mapping[str, Capabilities], *, home: Path | None = None,
              path_of: Callable[[dict[str, Any]], Path] | None = None) -> list[Checked]:
    """Dependencies into the current environment (pending before T8.2), then load and validate; clears a pin
    that no longer applies (UPD §2.8)."""
    entries = read_entries(home)
    chosen = entries if names is None else [e for e in entries if e["name"] in names]
    unknown = set(names or ()) - {str(e["name"]) for e in entries}
    if unknown:
        raise RegistryRefusal("unknown-workflow", f"not registered: {', '.join(sorted(unknown))}")
    out = []
    for e in chosen:
        path = path_of(e) if path_of else Path(str(e.get("path") or ""))
        got = check_package(path, caps, e)
        if got.ok and e.get("engine_pin"):
            got.entry["engine_pin"], got.entry["state"] = None, "ok"  # the pin no longer applies
        out.append(got)
    done = {str(c.entry["name"]): c.entry for c in out}
    write_entries([done.get(str(e["name"]), e) for e in entries], home)
    return out


def listing(home: Path | None = None) -> dict[str, Any]:
    rows = []
    for e in read_entries(home):
        rows.append({k: e.get(k) for k in ("name", "kind", "plugin", "path", "version", "workflow_version", "state",
                                           "reason", "engine_pin", "dependencies", "registered_at",
                                           "last_checked_at") if k in e or k in ("state", "engine_pin")})
    return {"schema_version": SCHEMA_VERSION, "workflows": rows}
