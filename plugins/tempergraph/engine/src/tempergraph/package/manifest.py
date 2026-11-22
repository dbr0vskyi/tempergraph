"""The two manifests and the Python half's `pyproject.toml` (PKG-B11, PKG-B12, PKG-B13); read without import or model."""

from __future__ import annotations

import json
import re
import tomllib
from dataclasses import dataclass
from pathlib import Path
from typing import Any

from tempergraph.contracts import PackageManifest
from tempergraph.model.validate import Finding

# A workflow package's plugin name is its workflow name plus PLUGIN_SUFFIX (PKG-B13, ADR-0120), so a
# tempergraph workflow is recognisable by name wherever Claude Code lists plugins. The workflow name stays short:
# it is what `run` takes, the registry key, the run folder and the `tgwf-<name>` distribution.
PLUGIN_SUFFIX = "-tgraph"
PLUGIN_NAME_MAX = 64  # the plugin name is part of namespaced tool and skill names; kept well inside their caps
NAME_RE = re.compile(r"^[a-z0-9][a-z0-9-]*$")  # a workflow name, kebab-case
RESERVED_PREFIXES = ("claude-", "anthropic-", "anthropics-", "cc-plugin-")  # Claude Code reserves these
ENTRY_RE = re.compile(r"^([A-Za-z_][A-Za-z0-9_]*):([A-Za-z_][A-Za-z0-9_]*)$")
DOCS_RE = re.compile(r"^(provisional|[a-z0-9][a-z0-9._-]{0,63})$")
PLUGIN_JSON = Path(".claude-plugin") / "plugin.json"
ENGINE_JSON = Path("tempergraph.json")
PYPROJECT = Path("workflow") / "pyproject.toml"

# The dependency gate (PKG-B18): a PEP 508 name, optional extras, optional version specifiers and an
# optional environment marker. Direct references (`@ url`), paths and installer options are refused.
_REQ_NAME = r"[A-Za-z0-9](?:[A-Za-z0-9._-]*[A-Za-z0-9])?"
_REQ_SPEC = r"(?:===|==|!=|~=|>=|<=|<|>)\s*[A-Za-z0-9.*+!_-]+"
REQUIREMENT_RE = re.compile(
    rf"^\s*(?P<name>{_REQ_NAME})\s*(?:\[\s*{_REQ_NAME}(?:\s*,\s*{_REQ_NAME})*\s*\])?\s*"
    rf"(?:\(?\s*{_REQ_SPEC}(?:\s*,\s*{_REQ_SPEC})*\s*\)?)?\s*"
    r"(?:;\s*[A-Za-z0-9_.\s'\"<>=!~()-]+)?$"
)
ENGINE_DISTRIBUTIONS = frozenset({"tempergraph"})


@dataclass(frozen=True, kw_only=True)
class Manifests:
    plugin: dict[str, Any]
    engine: PackageManifest

    @property
    def module(self) -> str:
        return self.engine.entry.partition(":")[0]

    @property
    def function(self) -> str:
        return self.engine.entry.partition(":")[2]

    @property
    def version(self) -> str:
        return str(self.plugin.get("version") or "0.0.0")


@dataclass(frozen=True, kw_only=True)
class Pyproject:
    name: str
    requires_python: str
    dependencies: tuple[str, ...]


def plugin_name(workflow: str) -> str:
    """The plugin name of the workflow package for `workflow` (ADR-0120)."""
    return workflow + PLUGIN_SUFFIX


def workflow_name(name: str) -> str:
    """The workflow name a person may also type as its plugin name: `notes-tgraph` -> `notes`."""
    return name[: -len(PLUGIN_SUFFIX)] if name.endswith(PLUGIN_SUFFIX) and len(name) > len(PLUGIN_SUFFIX) else name


def name_problem(name: str) -> str | None:
    """Why `name` cannot be a workflow name, or None (PKG-B13)."""
    if not NAME_RE.match(name):
        return f"workflow name {name!r} is not kebab-case (lower-case letters, digits and hyphens)"
    if name.endswith(PLUGIN_SUFFIX):
        return (f"workflow name {name!r} ends in {PLUGIN_SUFFIX!r}; the suffix belongs to the plugin name only, "
                f"so name the workflow {workflow_name(name)!r}")
    if len(plugin_name(name)) > PLUGIN_NAME_MAX:
        return (f"workflow name {name!r} is too long: its plugin name {plugin_name(name)!r} must be at most "
                f"{PLUGIN_NAME_MAX} characters")
    if name.startswith(RESERVED_PREFIXES):
        return f"workflow name {name!r} starts with a prefix Claude Code reserves ({', '.join(RESERVED_PREFIXES)})"
    return None


def _err(code: str, message: str, severity: str = "error") -> Finding:
    return Finding(code, None, message, severity)  # type: ignore[arg-type]


def _object(path: Path) -> dict[str, Any] | Finding:
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
    except FileNotFoundError:
        return _err("manifest", f"{path.name} is missing")
    except (OSError, ValueError) as exc:
        return _err("manifest", f"{path.name}: {type(exc).__name__}")
    if not isinstance(data, dict):
        return _err("manifest", f"{path.name} is not a JSON object")
    return data


def read_manifests(package_path: Path) -> Manifests | list[Finding]:
    """Step 1 of PKG-B15, PKG-B16, PKG-B17: both manifests, the plugin name is the workflow name plus `-tgraph`,
    `schema_version` known; no import, no model."""
    plugin = _object(package_path / PLUGIN_JSON)
    engine = _object(package_path / ENGINE_JSON)
    found = [f for f in (plugin, engine) if isinstance(f, Finding)]
    if found:
        return found
    assert isinstance(plugin, dict) and isinstance(engine, dict)
    out: list[Finding] = []
    if engine.get("schema_version") != 1:
        out.append(_err("manifest", f"tempergraph.json schema_version {engine.get('schema_version')!r} is unknown"))
    name = engine.get("name")
    problem = name_problem(name) if isinstance(name, str) else f"tempergraph.json name {name!r} is not a string"
    if problem:
        out.append(_err("manifest", f"tempergraph.json: {problem}"))
    elif plugin.get("name") != plugin_name(str(name)):
        out.append(_err("plugin-name-suffix", f"plugin.json name is {plugin.get('name')!r}; a workflow package's "
                        f"plugin name is its workflow name plus {PLUGIN_SUFFIX!r}: {plugin_name(str(name))!r} "
                        f"(tempergraph.json name {name!r})"))
    entry = engine.get("entry")
    if not isinstance(entry, str) or not ENTRY_RE.match(entry):
        out.append(_err("manifest", f"entry {entry!r} must be <module>:<function>"))
    api = engine.get("workflow_api")
    if not isinstance(api, int) or isinstance(api, bool) or api < 1:
        out.append(_err("manifest", f"workflow_api {api!r} must be a positive integer"))
    docs = engine.get("docs", "provisional")
    if not isinstance(docs, str) or not DOCS_RE.match(docs):
        out.append(_err("manifest", f"docs {docs!r} must be 'provisional' or a rule set id"))
    surfaces = engine.get("surfaces", {})
    if not isinstance(surfaces, dict):
        out.append(_err("manifest", "surfaces must map an executor to a surface form"))
    audit = engine.get("audit", {})
    if not isinstance(audit, dict):
        out.append(_err("manifest", "audit must be an object, such as {\"ignore\": [...]} (AUD-B14)"))
    unknown = set(engine) - {"schema_version", "name", "entry", "workflow_api", "docs", "surfaces", "audit"}
    if unknown:
        out.append(_err("manifest-field-unknown", f"tempergraph.json fields {sorted(unknown)} are unknown "
                        "(the version comes from plugin.json)", "warning"))
    if any(f.severity == "error" for f in out):
        return out
    return Manifests(plugin=plugin, engine=PackageManifest(
        schema_version=1, name=str(name), entry=str(entry), workflow_api=int(api or 0), docs=str(docs),
        surfaces=dict(surfaces), audit=dict(audit)))


def read_manifest(package_path: Path) -> PackageManifest | list[Finding]:
    """The PKG-B13, PKG-B15 contract: the engine manifest, or the findings that stop it loading."""
    got = read_manifests(package_path)
    return got if isinstance(got, list) else got.engine


def read_pyproject(package_path: Path) -> Pyproject | Finding:
    path = package_path / PYPROJECT
    try:
        data = tomllib.loads(path.read_text(encoding="utf-8"))
    except FileNotFoundError:
        return _err("pyproject-missing", "workflow/pyproject.toml is missing")
    except (OSError, ValueError) as exc:
        return _err("pyproject-invalid", f"workflow/pyproject.toml: {type(exc).__name__}")
    project = data.get("project")
    if not isinstance(project, dict):
        return _err("pyproject-invalid", "workflow/pyproject.toml has no [project] table")
    deps = project.get("dependencies", [])
    if not isinstance(deps, list) or not all(isinstance(d, str) for d in deps):
        return _err("pyproject-invalid", "[project].dependencies must be a list of strings")
    return Pyproject(name=str(project.get("name") or ""), requires_python=str(project.get("requires-python") or ""),
                     dependencies=tuple(deps))


def requirement_name(line: str) -> str | None:
    m = REQUIREMENT_RE.match(line)
    return None if m is None else m.group("name")


def normalized(name: str) -> str:
    return re.sub(r"[-_.]+", "-", name).lower()


def gate_dependencies(deps: tuple[str, ...]) -> list[Finding]:
    """The dependency gate (PKG-B18): a refusal makes the package `not_loaded: dependency_refused`."""
    out = []
    for line in deps:
        name = requirement_name(line)
        if name is None:
            out.append(_err("dependency_refused", f"{line!r} is not a plain requirement (name, extras, "
                            "version specifiers, marker); direct references and options are refused"))
        elif normalized(name) in ENGINE_DISTRIBUTIONS:
            out.append(_err("dependency_refused", f"{line!r}: the engine is not a workflow dependency"))
    return out
