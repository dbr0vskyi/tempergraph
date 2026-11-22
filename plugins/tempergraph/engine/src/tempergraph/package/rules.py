"""The package rules of PKG, applied after WFM `validate` (PKG-B15, PKG-B16, PKG-B17 step 6, PKG-B11, PKG-B12, PKG-B19, PKG-B20, PKG-B11, PKG-B13, PKG-B14, PKG-B17, PKG-B18, PKG-B19, PKG-B20, PKG-B23)."""

from __future__ import annotations

import json
from pathlib import Path

from tempergraph.contracts import TextRef, WorkflowSpec
from tempergraph.model.validate import Finding
from tempergraph.package.inventory import PackageInventory
from tempergraph.package.manifest import Manifests, Pyproject

# Refused plugin parts (PKG-B11, PKG-B12, ADR-0112): code -> remedy.
REMEDY = {
    "plugin-hooks": "declare the tools the step needs; lifecycle hooks are registered with `tempergraph hooks add`",
    "plugin-mcp": "declare the step's MCP tools as `mcp:<server>/<tool>`; the server is configured on the machine",
    "plugin-bin": "run programs from a script unit or a declared command, not from the plugin's bin/",
    "plugin-session-settings": "a step's session is configured by its declaration, not by plugin settings",
    "plugin-instruction-file": "Claude Code does not read it from a plugin; put the text in prompts/ or a skill",
}
# Files the layout requires once a package exists, short of those whose absence stops loading (PKG-B11, PKG-B12).
REQUIRED_FILES = ("README.md", "docs", "tests", "diagram", "evals/cases.json")


def _refused(code: str, what: str) -> Finding:
    return Finding(code, None, f"{what} is refused in a workflow package: {REMEDY[code]}")


def plugin_parts(root: Path, manifests: Manifests) -> list[Finding]:
    out: list[Finding] = []
    plugin = manifests.plugin
    if (root / "hooks" / "hooks.json").exists() or "hooks" in plugin:
        out.append(_refused("plugin-hooks", "hooks/hooks.json or a `hooks` manifest key"))
    if (root / ".mcp.json").exists() or "mcpServers" in plugin:
        out.append(_refused("plugin-mcp", ".mcp.json or `mcpServers`"))
    if (root / "bin").exists():
        out.append(_refused("plugin-bin", "bin/"))
    settings = root / "settings.json"
    agent_settings = False
    if settings.is_file():
        try:
            agent_settings = "agent" in json.loads(settings.read_text(encoding="utf-8"))
        except (OSError, ValueError, TypeError):
            agent_settings = False
    if (root / ".lsp.json").exists() or "lspServers" in plugin or agent_settings:
        out.append(_refused("plugin-session-settings", ".lsp.json, `lspServers` or settings.json with `agent`"))
    for name in ("CLAUDE.md", "AGENTS.md"):
        if (root / name).exists():
            out.append(_refused("plugin-instruction-file", name))
    return out


def layout(root: Path, manifests: Manifests, pyproject: Pyproject, inventory: PackageInventory) -> list[Finding]:
    out: list[Finding] = []
    want = f"tgwf-{manifests.engine.name}"
    if pyproject.name != want:
        out.append(Finding("pyproject-name", None, f"workflow/pyproject.toml name is {pyproject.name!r}; "
                           f"it must be {want!r}"))
    for rel in REQUIRED_FILES:
        if not inventory.has(rel):
            out.append(Finding("package-file-missing", None, f"{rel} is part of every package (PKG-B11, PKG-B12)",
                               "warning"))
    return out


def check_cases(spec: WorkflowSpec, root: Path) -> list[Finding]:
    """EVS-B1: every check is tested both ways, with a must-pass and a must-fail fixture under
    `evals/checks/<unit>/`."""
    out: list[Finding] = []
    for name, u in spec.units.items():
        if u.gate.check is None:
            continue
        base = root / "evals" / "checks" / name
        for which, code in (("must-fail", "check_without_fail_case"), ("must-pass", "check_without_pass_case")):
            if not any((base / which).glob("*")):
                out.append(Finding(code, name, f"the check of {name} has no {which} fixture under "
                                               f"evals/checks/{name}/{which}/ (EVS-B9, EVS-B2, EVS-B10)", "warning"))
    return out


def text_refs(spec: WorkflowSpec, root: Path) -> list[Finding]:
    """Every `text()` reference and judge file resolves inside the package (PKG-B19, PKG-B20, PKG-B11, PKG-B13, PKG-B14, PKG-B17, PKG-B18, PKG-B23 `text-ref`)."""
    out: list[Finding] = []
    base = root.resolve()

    def check(unit: str, rel: str) -> None:
        path = (base / rel).resolve()
        if not path.is_relative_to(base):
            out.append(Finding("text-ref", unit, f"{rel}: outside the package"))
        elif not path.is_file():
            out.append(Finding("text-ref", unit, f"{rel}: no such file in the package"))

    for name, u in spec.units.items():
        if u.step is not None and isinstance(u.step.prompt, TextRef):
            check(name, u.step.prompt.path)
        if u.gate.judge is not None and u.gate.judge.file:
            check(name, u.gate.judge.file)
    return out


def criteria_twice(spec: WorkflowSpec, inline: dict[str, set[str]]) -> list[Finding]:
    """An id given both inline on a gate and in `outcome.json` (PKG-B19, PKG-B20 `criterion-declared-twice`)."""
    if spec.outcome is None:
        return []
    out = []
    for unit, ids in inline.items():
        inter = spec.outcome.intermediate.get(unit)
        dup = ids & {c.id for c in inter.criteria if c.id} if inter is not None else set()
        for cid in sorted(dup):
            out.append(Finding("criterion-declared-twice", unit, f"criterion {cid!r} is inline and in outcome.json"))
    return out
