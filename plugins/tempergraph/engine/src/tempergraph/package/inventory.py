"""What is where in a package, and the digests over it (PKG §2 `package_files`, VER §2.4, PKG-AC-7).

`content_digest` covers what a run runs: the spec's canonical JSON, `outcome.json`, every template, brief,
lessons file, skill and agent file, every Python source under `workflow/` and the `dependencies` of its
`pyproject.toml`. It never covers `docs/`, `diagram/`, `evals/`, `authoring.json`, `README.md` or `tests/`.
`docs_digest` covers `docs/` only (PKG §2.5).
"""

from __future__ import annotations

import dataclasses
import hashlib
import json
from collections.abc import Iterable, Mapping
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

from tempergraph.contracts import CallableRef, WorkflowSpec

# Folders and files whose content is part of what runs (VER §2.4).
CONTENT_DIRS = ("prompts", "judges", "lessons", "skills", "agents")
CONTENT_FILES = ("outcome.json",)
SKIP_PARTS = frozenset({"__pycache__", ".pytest_cache", ".mypy_cache", ".ruff_cache"})


@dataclass(frozen=True, kw_only=True)
class PackageInventory:
    root: Path
    content: tuple[str, ...] = ()  # package-relative paths inside the content digest
    python: tuple[str, ...] = ()  # workflow/**/*.py
    docs: tuple[str, ...] = ()
    other: tuple[str, ...] = ()  # present, outside both digests
    present: frozenset[str] = field(default_factory=frozenset)  # top-level names

    def has(self, rel: str) -> bool:
        return (self.root / rel).exists()


def _walk(root: Path, top: Path) -> Iterable[Path]:
    if top.is_file():
        yield top
        return
    if not top.is_dir():
        return
    for p in sorted(top.rglob("*")):
        rel = p.relative_to(root)
        if p.is_file() and not (SKIP_PARTS & set(rel.parts)) and p.suffix not in (".pyc", ".pyo"):
            yield p


def package_files(package_path: Path) -> PackageInventory:
    root = package_path
    content: list[str] = []
    for name in (*CONTENT_DIRS, *CONTENT_FILES):
        content += [p.relative_to(root).as_posix() for p in _walk(root, root / name)]
    python = [p.relative_to(root).as_posix() for p in _walk(root, root / "workflow") if p.suffix == ".py"]
    docs = [p.relative_to(root).as_posix() for p in _walk(root, root / "docs")]
    known = set(content) | set(python) | set(docs)
    other = [p.relative_to(root).as_posix() for p in _walk(root, root)
             if p.relative_to(root).as_posix() not in known and p.relative_to(root).parts[0] != ".git"]
    present = frozenset(p.name for p in root.iterdir()) if root.is_dir() else frozenset()
    return PackageInventory(root=root, content=tuple(content), python=tuple(python), docs=tuple(docs),
                            other=tuple(other), present=present)


def canonical(obj: Any) -> Any:
    """A JSON-ready, order-stable form of a spec: callables by reference, paths and live objects left out."""
    if isinstance(obj, CallableRef):
        return obj.ref
    if dataclasses.is_dataclass(obj) and not isinstance(obj, type):
        return {f.name: canonical(getattr(obj, f.name)) for f in dataclasses.fields(obj)
                if f.name not in ("package_root", "outcome", "func")}
    if isinstance(obj, Mapping):
        return {str(k): canonical(v) for k, v in sorted(obj.items(), key=lambda kv: str(kv[0]))}
    if isinstance(obj, (list, tuple, set, frozenset)):
        items = [canonical(v) for v in obj]
        return sorted(items, key=json.dumps) if isinstance(obj, (set, frozenset)) else items
    if isinstance(obj, Path):
        return None
    if obj is None or isinstance(obj, (str, int, float, bool)):
        return obj
    return repr(obj)


def _feed(h: Any, label: str, data: bytes) -> None:
    h.update(label.encode() + b"\0" + str(len(data)).encode() + b"\0" + data)


def content_digest(spec: WorkflowSpec, inventory: PackageInventory, dependencies: Iterable[str]) -> str:
    h = hashlib.sha256()
    _feed(h, "spec", json.dumps(canonical(spec), sort_keys=True, separators=(",", ":")).encode())
    for rel in sorted((*inventory.content, *inventory.python)):
        _feed(h, rel, (inventory.root / rel).read_bytes())
    _feed(h, "dependencies", "\n".join(sorted(" ".join(d.split()) for d in dependencies)).encode())
    return h.hexdigest()


def docs_digest(inventory: PackageInventory) -> str:
    h = hashlib.sha256()
    for rel in sorted(inventory.docs):
        _feed(h, rel, (inventory.root / rel).read_bytes())
    return h.hexdigest()


def workflow_version(version: str, digest: str) -> str:
    return f"{version}+{digest[:12]}"
