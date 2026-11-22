"""Private import names for workflow packages (PKG-B15, PKG-B16, PKG-B17 step 3, PKG-B3).

A package's entry module, the folder ``workflow/<module>/``, is imported as ``tgwf_<name>`` (the workflow name
with ``-`` as ``_``), so two packages that both hold a ``checks`` module never collide. The package's own
modules import each other relatively; their callables are recorded as ``tgwf_<name>.<sub>:<qualname>``.

A meta-path finder maps each private name to its folder. The engine process registers a package when it
loads it; a child process (the check worker) gets the same map in its context document and calls
:func:`install` before it imports a callable by reference (CHK-B16).
"""

from __future__ import annotations

import importlib.abc
import importlib.machinery
import importlib.util
import sys
from collections.abc import Mapping, Sequence
from pathlib import Path
from types import ModuleType

PREFIX = "tgwf_"


def private_name(workflow: str) -> str:
    return PREFIX + workflow.replace("-", "_")


class _Finder(importlib.abc.MetaPathFinder):
    def __init__(self) -> None:
        self.roots: dict[str, Path] = {}

    def find_spec(self, fullname: str, path: Sequence[str] | None = None,
                  target: ModuleType | None = None) -> importlib.machinery.ModuleSpec | None:
        top = fullname.partition(".")[0]
        root = self.roots.get(top)
        if root is None or fullname != top:
            return None  # submodules are found through the package's __path__
        init = root / "__init__.py"
        if not init.is_file():
            return None
        return importlib.util.spec_from_file_location(fullname, init, submodule_search_locations=[str(root)])


_FINDER = _Finder()


def _ensure_finder() -> None:
    if _FINDER not in sys.meta_path:
        sys.meta_path.insert(0, _FINDER)


def _purge(name: str) -> None:
    for mod in [m for m in sys.modules if m == name or m.startswith(name + ".")]:
        del sys.modules[mod]


def register(name: str, folder: Path) -> None:
    """Map a private name to a package's entry folder; a different folder (a new version) drops the old modules."""
    _ensure_finder()
    folder = folder.resolve()
    if _FINDER.roots.get(name) != folder:
        _purge(name)
        importlib.invalidate_caches()
    _FINDER.roots[name] = folder


def import_entry(workflow: str, folder: Path) -> ModuleType:
    """Import afresh: a load always reads the package's current source (PKG-B15, PKG-B16, PKG-B17). No bytecode is written
    into the package, so loading (and `audit`, AUD-B6) leaves it byte-for-byte unchanged."""
    name = private_name(workflow)
    register(name, folder)
    _purge(name)
    importlib.invalidate_caches()
    was, sys.dont_write_bytecode = sys.dont_write_bytecode, True
    try:
        return importlib.import_module(name)
    finally:
        sys.dont_write_bytecode = was


def mapping() -> dict[str, str]:
    """The registered private names, for a child process's context document."""
    return {k: str(v) for k, v in _FINDER.roots.items()}


def install(roots: Mapping[str, str] | None) -> None:
    for name, folder in (roots or {}).items():
        if name.startswith(PREFIX):
            register(name, Path(folder))
