"""Source-scan rules every later track relies on.

- LangGraph is imported only by the compiler and durability packages (R-011 U4, plan T1.1).
- Process launches happen only at sanctioned sites (SEC-AC1).
- No module outside the executor package imports a concrete executor (EXI-AC1).
- No engine source file names a shipped workflow (WFM-AC4, OVR-B10).
"""

from __future__ import annotations

import ast
from pathlib import Path

from tempergraph.security.launch import SANCTIONED_SITES

from .conftest import SRC, workflow_names

LANGGRAPH_ALLOWED = ("tempergraph.compiler", "tempergraph.durability")
CONCRETE_EXECUTORS = ("tempergraph.executors.claude", "tempergraph.executors.standins")
EXECUTOR_PACKAGE = "tempergraph.executors"
SHIPPED_WORKFLOW_NAMES = tuple(workflow_names())  # found in the repository, never typed here
LAUNCH_CALLS = {("os", "system"), ("os", "popen"), ("os", "execv"), ("os", "execve"), ("os", "execvp"),
                ("os", "spawnv"), ("os", "spawnl"), ("os", "posix_spawn"), ("os", "fork")}


def modules() -> list[tuple[str, Path, ast.Module]]:
    out = []
    for path in sorted(SRC.rglob("*.py")):
        rel = path.relative_to(SRC.parent).with_suffix("")
        name = ".".join(rel.parts)
        if name.endswith(".__init__"):
            name = name[: -len(".__init__")]
        out.append((name, path, ast.parse(path.read_text(encoding="utf-8"), filename=str(path))))
    return out


def imported(tree: ast.Module) -> set[str]:
    names: set[str] = set()
    for node in ast.walk(tree):
        if isinstance(node, ast.Import):
            names.update(a.name for a in node.names)
        elif isinstance(node, ast.ImportFrom) and node.module:
            names.add(node.module)
            names.update(f"{node.module}.{a.name}" for a in node.names)
    return names


def _within(name: str, prefixes: tuple[str, ...]) -> bool:
    return any(name == p or name.startswith(p + ".") for p in prefixes)


def test_langgraph_confined() -> None:
    bad = [name for name, _, tree in modules()
           if any(i == "langgraph" or i.startswith("langgraph.") for i in imported(tree))
           and not _within(name, LANGGRAPH_ALLOWED)]
    assert bad == [], f"LangGraph imported outside the compiler and durability modules: {bad}"


def test_launch_sites_sanctioned() -> None:
    bad = []
    for name, _, tree in modules():
        if name in SANCTIONED_SITES:
            continue
        if "subprocess" in imported(tree) or any(i.startswith("subprocess.") for i in imported(tree)):
            bad.append(f"{name}: imports subprocess")
        for node in ast.walk(tree):
            if (isinstance(node, ast.Call) and isinstance(node.func, ast.Attribute)
                    and isinstance(node.func.value, ast.Name)
                    and (node.func.value.id, node.func.attr) in LAUNCH_CALLS):
                bad.append(f"{name}: calls {node.func.value.id}.{node.func.attr}")
    assert bad == [], bad


def test_sanctioned_sites_exist() -> None:
    names = {name for name, _, _ in modules()}
    missing = [s for s in SANCTIONED_SITES if s not in names]
    assert missing == [], f"launch sites listed but not built: {missing}"


def test_no_shell_true() -> None:
    bad = []
    for name, _, tree in modules():
        for node in ast.walk(tree):
            if isinstance(node, ast.Call):
                for kw in node.keywords:
                    if kw.arg == "shell" and isinstance(kw.value, ast.Constant) and kw.value.value is True:
                        bad.append(name)
    assert bad == []


def test_concrete_executors_only_in_executor_package() -> None:
    bad = []
    for name, _, tree in modules():
        if _within(name, (EXECUTOR_PACKAGE,)):
            continue
        hits = [i for i in imported(tree) if _within(i, CONCRETE_EXECUTORS)]
        if hits:
            bad.append((name, hits))
    assert bad == [], bad


def test_engine_names_no_shipped_workflow() -> None:
    bad = []
    for name, path, _ in modules():
        text = path.read_text(encoding="utf-8").lower()
        bad.extend(f"{name}: {w}" for w in SHIPPED_WORKFLOW_NAMES if w in text)
    assert bad == [], bad
