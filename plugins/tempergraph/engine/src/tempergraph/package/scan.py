"""The source scan of a package's Python half, before any import (PKG §2.3 step 3, PKG-B4).

Imports are limited to the standard library, the requirements in `pyproject.toml`, the package's own
modules (imported relatively, because the entry module is imported under its private name) and
`tempergraph.api`. The scan reads the source with `ast`; nothing is executed.
"""

from __future__ import annotations

import ast
import sys
from pathlib import Path

from tempergraph.model.validate import Finding
from tempergraph.package.manifest import normalized

PUBLIC_MODULE = "tempergraph.api"


def _imports(tree: ast.Module) -> list[tuple[str, int, bool]]:
    """(module, line, relative) for every import; `from tempergraph import x` yields `tempergraph.x`."""
    out: list[tuple[str, int, bool]] = []
    for node in ast.walk(tree):
        if isinstance(node, ast.Import):
            out += [(a.name, node.lineno, False) for a in node.names]
        elif isinstance(node, ast.ImportFrom):
            if node.level:
                out.append((node.module or "", node.lineno, True))
            elif node.module == "tempergraph":
                out += [(f"tempergraph.{a.name}", node.lineno, False) for a in node.names]
            elif node.module:
                out.append((node.module, node.lineno, False))
    return out


def scan(package_path: Path, module: str, requirements: tuple[str, ...]) -> list[Finding]:
    src = package_path / "workflow"
    allowed = {normalized(r) for r in requirements}
    stdlib = set(sys.stdlib_module_names) | {"__future__"}
    out: list[Finding] = []
    for path in sorted(src.rglob("*.py")):
        rel = path.relative_to(package_path).as_posix()
        try:
            tree = ast.parse(path.read_text(encoding="utf-8"), filename=rel)
        except (OSError, SyntaxError, ValueError) as exc:
            out.append(Finding("source-unparsable", None, f"{rel}: {type(exc).__name__}"))
            continue
        for name, line, relative in _imports(tree):
            if relative:
                continue
            top = name.partition(".")[0]
            where = f"{rel}:{line}"
            if top == "tempergraph":
                if name != PUBLIC_MODULE and not name.startswith(PUBLIC_MODULE + "."):
                    out.append(Finding("private-engine-import", None,
                                       f"{where} imports {name}; a workflow imports only {PUBLIC_MODULE}"))
            elif top == module:
                out.append(Finding("own-module-absolute-import", None,
                                   f"{where} imports {name} by its folder name; import the package's own "
                                   "modules relatively (`from . import checks`)"))
            elif top not in stdlib and normalized(top) not in allowed:
                out.append(Finding("undeclared-import", None,
                                   f"{where} imports {top}, which is neither the standard library nor a "
                                   "requirement in workflow/pyproject.toml", "warning"))
    return out
