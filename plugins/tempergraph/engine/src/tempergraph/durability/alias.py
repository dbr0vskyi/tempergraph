"""Run aliases (DUR §2.2 `alias`, DUR-B8): a short name unique among live threads.

The table is `<state root>/runs/aliases.json`: alias -> thread ids, latest last. A finished thread frees
its alias; a lookup of a name whose threads are all finished returns the latest one.
"""

from __future__ import annotations

import re
from collections.abc import Callable
from pathlib import Path

from tempergraph.docs import read_json, write_json

ALIAS_RE = re.compile(r"^[A-Za-z0-9][A-Za-z0-9._-]{0,39}$")


class AliasTaken(Exception):
    def __init__(self, alias: str, holder: str) -> None:
        super().__init__(f"alias {alias!r} is held by live thread {holder}")
        self.alias, self.holder = alias, holder


class AliasInvalid(ValueError):
    pass


def _path(state_root: Path) -> Path:
    return state_root / "runs" / "aliases.json"


def _read(state_root: Path) -> dict[str, list[str]]:
    p = _path(state_root)
    if not p.exists():
        return {}
    doc = read_json(p, "status")
    return {k: [str(t) for t in v] for k, v in (doc.get("aliases") or {}).items() if isinstance(v, list)}


def claim(state_root: Path, alias: str, thread: str, is_live: Callable[[str], bool]) -> None:
    if not ALIAS_RE.match(alias):
        raise AliasInvalid(f"alias {alias!r}: letters, digits, '.', '_' and '-', at most 40")
    table = _read(state_root)
    for holder in table.get(alias, []):
        if holder != thread and is_live(holder):
            raise AliasTaken(alias, holder)
    threads = [t for t in table.get(alias, []) if t != thread] + [thread]
    table[alias] = threads
    write_json(_path(state_root), {"schema_version": 1, "aliases": table})


def resolve(state_root: Path, name: str, is_live: Callable[[str], bool] | None = None) -> str | None:
    """The live thread holding ``name``, else its latest thread, else None."""
    threads = _read(state_root).get(name, [])
    if is_live is not None:
        for t in reversed(threads):
            if is_live(t):
                return t
    return threads[-1] if threads else None


def alias_of(state_root: Path, thread: str) -> str | None:
    for alias, threads in _read(state_root).items():
        if thread in threads:
            return alias
    return None
