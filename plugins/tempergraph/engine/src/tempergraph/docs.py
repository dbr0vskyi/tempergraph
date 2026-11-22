"""Versioned documents and tolerant readers (CON-B14, CON-B1, CON-B15, OVR-B14).

Every reader ignores unknown keys and reads a missing key as "not recorded", never as zero. A document
with a newer major schema is refused with :class:`NewerSchema`; the caller turns that into its own exit.
"""

from __future__ import annotations

import json
import os
import tempfile
from collections.abc import Iterator
from pathlib import Path
from typing import Any

from tempergraph.constants import SCHEMA


class NewerSchema(Exception):
    def __init__(self, path: Path, found: int, known: int) -> None:
        super().__init__(f"{path} has schema {found}; this engine reads up to {known}")
        self.path, self.found, self.known = path, found, known


def _owner_only_dirs(path: Path) -> None:
    path.parent.mkdir(parents=True, exist_ok=True, mode=0o700)


def write_json(path: Path, data: Any, *, mode: int = 0o600) -> None:
    """Atomic write, owner-only."""
    _owner_only_dirs(path)
    fd, tmp = tempfile.mkstemp(dir=path.parent, prefix=f".{path.name}.")
    try:
        with os.fdopen(fd, "w", encoding="utf-8") as fh:
            json.dump(data, fh, indent=2, sort_keys=False, ensure_ascii=False)
            fh.write("\n")
        os.chmod(tmp, mode)
        os.replace(tmp, path)
    except BaseException:
        Path(tmp).unlink(missing_ok=True)
        raise


def append_jsonl(path: Path, record: dict[str, Any]) -> None:
    _owner_only_dirs(path)
    new = not path.exists()
    fd = os.open(path, os.O_WRONLY | os.O_APPEND | os.O_CREAT, 0o600)
    try:
        os.write(fd, (json.dumps(record, ensure_ascii=False, sort_keys=False) + "\n").encode("utf-8"))
    finally:
        os.close(fd)
    if new:
        os.chmod(path, 0o600)


def read_json(path: Path, kind: str, *, key: str = "schema_version") -> dict[str, Any]:
    """Read a versioned JSON document of ``kind``; raise NewerSchema on a newer major."""
    data = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(data, dict):
        raise ValueError(f"{path}: not a JSON object")
    found = data.get(key)
    known = SCHEMA[kind]
    if isinstance(found, int) and found > known:
        raise NewerSchema(path, found, known)
    return data


def iter_jsonl(path: Path, known_kinds: frozenset[str] | None = None, counts: dict[str, int] | None = None
               ) -> Iterator[dict[str, Any]]:
    """Yield JSON-lines records; skip unparsable lines and unknown kinds (CON-B1), counting them."""
    if not path.exists():
        return
    with path.open(encoding="utf-8") as fh:
        for line in fh:
            line = line.strip()
            if not line:
                continue
            try:
                rec = json.loads(line)
            except json.JSONDecodeError:
                if counts is not None:
                    counts["unparsable"] = counts.get("unparsable", 0) + 1
                continue
            if not isinstance(rec, dict):
                continue
            if known_kinds is not None and rec.get("kind") not in known_kinds:
                if counts is not None:
                    counts["unknown_kinds"] = counts.get("unknown_kinds", 0) + 1
                continue
            yield rec
