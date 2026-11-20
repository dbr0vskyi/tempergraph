"""Template and brief text of a workflow: inline, a package file, or the engine default (PKG §2.4, PRM)."""

from __future__ import annotations

from pathlib import Path

from tempergraph.contracts import TextRef, TextSource, WorkflowSpec

# VAL §2.3 engine keys; reserved, so no input or artifact may use them.
ENGINE_KEYS = frozenset(
    {"task_id", "thread_id", "workflow", "unit", "attempt", "visit", "branch", "base", "workdir", "run_label"}
)
ITEM_KEYS = frozenset({"item_id", "item_index", "item_count", "item"})
RESERVED_KEYS = ENGINE_KEYS | ITEM_KEYS

# PRM §2.1: the engine's default template. A workflow that declares no input parameters has one input,
# `request`: the whole start request (CLI §2, PRM §2.1).
DEFAULT_TEMPLATE = "{request}"


class TextUnreadable(Exception):
    pass


def resolve_path(spec: WorkflowSpec, ref: TextRef) -> Path:
    root = spec.package_root
    if root is None:
        raise TextUnreadable(f"text ref {ref.path!r} without a package root")
    path = (root / ref.path).resolve()
    if not path.is_relative_to(root.resolve()):
        raise TextUnreadable(f"text ref {ref.path!r} is outside the package")
    return path


def load_text(spec: WorkflowSpec, source: TextSource) -> str:
    if isinstance(source, TextRef):
        path = resolve_path(spec, source)
        try:
            return path.read_text(encoding="utf-8")
        except OSError as exc:
            raise TextUnreadable(f"{source.path}: {type(exc).__name__}") from None
    if source == "default":
        return DEFAULT_TEMPLATE
    return source


def input_names(spec: WorkflowSpec) -> set[str]:
    names = {p.name for p in spec.input.parameters}
    return names or {"request"}


def split_judge_file(text: str) -> tuple[str, str]:
    """`judges/<unit>.md`: the stance, then the brief, under two fixed headings (PKG §2.1)."""
    stance: list[str] = []
    brief: list[str] = []
    cur: list[str] | None = None
    for line in text.splitlines():
        head = line.strip().lower()
        if head.startswith("#") and head.lstrip("#").strip() == "stance":
            cur = stance
            continue
        if head.startswith("#") and head.lstrip("#").strip() == "brief":
            cur = brief
            continue
        if cur is not None:
            cur.append(line)
    return "\n".join(stance).strip(), "\n".join(brief).strip()
