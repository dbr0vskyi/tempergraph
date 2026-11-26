"""The home workflow registry, `registry.json` (UPD-B20 to UPD-B24, ADR `registered-workflows-are-reinstalled-and-pinned-never-lost`), and the `workflows` verbs' logic.

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
from tempergraph.git import GitError, git
from tempergraph.model.validate import Finding, validate
from tempergraph.package.importer import private_name
from tempergraph.package.loader import LoadedPackage, PackageNotLoaded, load_package
from tempergraph.package.manifest import ENGINE_JSON, workflow_name
from tempergraph.store.layout import ensure_home, home_path, lock_path, now_iso

SCHEMA_VERSION = 1
KINDS = ("plugin", "local", "builtin")


class RegistryRefusal(Exception):
    def __init__(self, code: str, message: str, findings: list[Finding] | None = None) -> None:
        super().__init__(f"{code}: {message}")
        self.code = code
        self.findings = findings or []


def plugin_cache() -> Path:
    """Claude Code's plugin cache (research `updating-a-tool-with-long-lived-runs` U4); `CLAUDE_CONFIG_DIR` moves it."""
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
                                "the plugin cache is keyed by the version string (VER-B14, VER-B15)", "warning"))
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
    """`workflows register <path> [--check]`: a local source that loads and validates (UPD-B20 to UPD-B24)."""
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


def _git_out(cwd: Path, *args: str) -> str | None:
    try:
        out = git(list(args), cwd, timeout_s=30).strip()
    except GitError:
        return None
    return out or None


def other_checkout(root: Path, name: str, home: Path | None = None) -> Path | None:
    """The registered path of `name` when it is another checkout of the package at `root`: both folders lie in
    working trees of one git repository and sit at the same place from their top levels (SCF-B24). None otherwise,
    and None when git cannot answer."""
    root = root.expanduser().resolve()
    for e in read_entries(home):
        if not (e["name"] == name or private_name(str(e["name"])) == private_name(name)):
            continue
        other = Path(str(e.get("path") or "")).resolve()
        if other == root or not other.is_dir() or not root.is_dir():
            return None
        mine = _git_out(root, "rev-parse", "--path-format=absolute", "--git-common-dir", "--show-toplevel")
        theirs = _git_out(other, "rev-parse", "--path-format=absolute", "--git-common-dir", "--show-toplevel")
        if mine is None or theirs is None:
            return None
        (mine_common, mine_top), (their_common, their_top) = mine.splitlines(), theirs.splitlines()
        if Path(mine_common).resolve() != Path(their_common).resolve():
            return None
        if root.relative_to(Path(mine_top).resolve()) != other.relative_to(Path(their_top).resolve()):
            return None
        return other
    return None


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
    """Remove the entry only, never files; refused while a thread of it is live (UPD-B20 to UPD-B24)."""
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
              path_of: Callable[[dict[str, Any]], Path] | None = None, installer: Installer | None = None,
              engine: str | None = None) -> list[Checked]:
    """Dependencies into the current environment (pending before T8.2), then load and validate; clears a pin
    that no longer applies (UPD-B20 to UPD-B24)."""
    entries = read_entries(home)
    chosen = entries if names is None else [e for e in entries if e["name"] in names]
    unknown = set(names or ()) - {str(e["name"]) for e in entries}
    if unknown:
        raise RegistryRefusal("unknown-workflow", f"not registered: {', '.join(sorted(unknown))}")
    out = []
    for e in chosen:
        path = path_of(e) if path_of else Path(str(e.get("path") or ""))
        got = check_package(path, caps, e)
        dep_error = install_dependencies(got, installer, engine or ENGINE_VERSION) if got.loaded is not None \
            and installer is not None else None
        if got.ok and dep_error is None and e.get("engine_pin"):
            got.entry["engine_pin"], got.entry["state"] = None, "ok"  # the pin no longer applies
        out.append(got)
    done = {str(c.entry["name"]): c.entry for c in out}
    write_entries([done.get(str(e["name"]), e) for e in entries], home)
    return out


Installer = Callable[[str, list[str]], str | None]  # (workflow name, requirement lines) -> an error, or None


def install_dependencies(got: Checked, installer: Installer | None, engine: str) -> str | None:
    """UPD-B20 to UPD-B24: the package's declared requirements, through the dependency gate, into this environment.
    Returns the reason they are not installed, or None. Without an installer nothing is installed and an
    entry that declares requirements stays `dependencies: pending`."""
    from tempergraph.package.manifest import gate_dependencies

    deps = tuple(got.loaded.pyproject.dependencies) if got.loaded and got.loaded.pyproject else ()
    e = got.entry
    if not deps:
        e.pop("dependencies", None)
        return None
    if engine in (e.get("installed_into") or []) and e.get("installed_digest") == e.get("requirements_digest"):
        e.pop("dependencies", None)
        return None
    if installer is None:
        e["dependencies"] = "pending"
        return None
    refused = gate_dependencies(deps)
    if refused:
        got.findings += refused
        e["dependencies"] = "refused"
        return "dependency_refused"
    err = installer(str(e.get("name") or "workflow"), list(deps))
    if err:
        got.findings.append(Finding("dependency_conflict", None, err[:300]))
        e["dependencies"] = "failed"
        return "dependency_conflict"
    e["installed_into"] = sorted({*(e.get("installed_into") or []), engine})
    e["installed_digest"] = e.get("requirements_digest")
    e.pop("dependencies", None)
    return None


def settle(got: Checked, *, was: str | None, previous: str | None, dep_error: str | None) -> Checked:
    """UPD-B7's table: a workflow that worked on the old engine and fails on this one is pinned to the old
    one; one that never worked is `not_loaded`; one that works has its pin cleared (UPD-B8)."""
    e = got.entry
    works = got.ok and dep_error is None
    if works:
        e["engine_pin"], e["state"] = None, "ok"
        e.pop("reason", None)
        return got
    reason = dep_error or next((f.code for f in got.findings if f.severity == "error"), "not_loaded")
    if isinstance(e.get("engine_pin"), dict):
        e["state"] = "pinned"
    elif was == "ok" and previous:
        e["engine_pin"] = {"engine": previous, "reason": reason, "since": now_iso()}
        e["state"] = "pinned"
    else:
        e["engine_pin"], e["state"], e["reason"] = None, "not_loaded", reason
    return got


def after_update(caps: Mapping[str, Capabilities], *, previous: str | None, engine: str,
                 installer: Installer | None = None, cache: Path | None = None,
                 home: Path | None = None) -> list[Checked]:
    """`update` step 6 inside the new environment: reconcile the registry, install every entry's
    dependencies, load and validate each, and pin what broke. No entry is ever removed (UPD-AC7)."""
    before = {str(e.get("name")): e.get("state") for e in read_entries(home)}
    reconcile(caps, cache=cache, home=home)
    out: list[Checked] = []
    entries = read_entries(home)
    for e in entries:
        path = Path(str(e.get("path") or ""))
        got = check_package(path, caps, e)
        dep_error = install_dependencies(got, installer, engine) if got.loaded is not None else None
        out.append(settle(got, was=before.get(str(e.get("name"))), previous=previous, dep_error=dep_error))
    write_entries([c.entry for c in out], home)
    return out


def listing(home: Path | None = None) -> dict[str, Any]:
    rows = []
    for e in read_entries(home):
        rows.append({k: e.get(k) for k in ("name", "kind", "plugin", "path", "version", "workflow_version", "state",
                                           "reason", "engine_pin", "dependencies", "registered_at",
                                           "last_checked_at") if k in e or k in ("state", "engine_pin")})
    return {"schema_version": SCHEMA_VERSION, "workflows": rows}


def _version_key(v: str) -> tuple[Any, ...]:
    parts = []
    for p in v.split("+", 1)[0].split("."):
        parts.append((0, int(p), "") if p.isdigit() else (1, 0, p))
    return tuple(parts)


def cached_plugins(cache: Path | None = None) -> dict[str, Path]:
    """`<plugin>@<marketplace>` -> its newest non-orphaned version folder holding a workflow package
    (`<cache>/<marketplace>/<plugin>/<version>/`, research `updating-a-tool-with-long-lived-runs` U4)."""
    root = cache or plugin_cache()
    out: dict[str, Path] = {}
    for market in sorted(p for p in root.iterdir() if p.is_dir()) if root.is_dir() else []:
        for plugin in sorted(p for p in market.iterdir() if p.is_dir()):
            versions = [v for v in plugin.iterdir() if v.is_dir() and (v / ENGINE_JSON).is_file()
                        and not (v / ".orphaned_at").exists()]
            if versions:
                out[f"{plugin.name}@{market.name}"] = max(versions, key=lambda v: _version_key(v.name))
    return out


def reconcile(caps: Mapping[str, Capabilities], *, cache: Path | None = None,
              home: Path | None = None) -> list[Checked]:
    """Repoint `plugin` entries to their current cache folder, register newly installed workflow plugins,
    mark a vanished one `missing`, never delete one (UPD-B20 to UPD-B24, PKG-B1)."""
    entries = read_entries(home)
    found = cached_plugins(cache)
    by_plugin = {str(e.get("plugin")): e for e in entries if e.get("kind") == "plugin"}
    out: list[Checked] = []
    kept: list[dict[str, Any]] = [e for e in entries if e.get("kind") != "plugin"]
    taken = {str(e["name"]) for e in kept}
    for pid, path in sorted(found.items()):
        prior = by_plugin.pop(pid, None)
        base = dict(prior) if prior else {"kind": "plugin", "plugin": pid, "registered_at": now_iso(),
                                          "engine_pin": None, "installed_into": []}
        base["path"] = str(path)
        got = check_package(path, caps, base)
        name = got.loaded.spec.name if got.loaded else str(base.get("name") or workflow_name(pid.split("@", 1)[0]))
        if name in taken:
            got.findings.append(Finding("name-taken", None, f"{pid}: workflow {name!r} is already registered"))
            out.append(got)
            continue
        got.entry["name"] = name
        taken.add(name)
        kept.append(got.entry)
        out.append(got)
    for e in by_plugin.values():  # uninstalled: keep the entry and its threads
        e = {**e, "state": "missing", "last_checked_at": now_iso()}
        kept.append(e)
        out.append(Checked(entry=e, findings=[Finding("missing", None, f"{e.get('plugin')} is not in the cache")]))
    write_entries(kept, home)
    return out
