"""Interpreter lookup for the first install (UPD §2.7 step 1): `TEMPERGRAPH_PYTHON`, an activated
environment, then the 3.11+ names; never a bare `python` or an alias stub."""

from __future__ import annotations

import os
import shutil
from pathlib import Path

from tempergraph.install.launch import run

NAMES = ("python3.14", "python3.13", "python3.12", "python3.11", "python3")
MIN = (3, 11)
_PROBE = "import sys; print('%d.%d' % sys.version_info[:2])"


def version_of(python: str) -> tuple[int, int] | None:
    got = run([python, "-c", _PROBE])
    if got.code != 0:
        return None
    try:
        major, minor = (int(x) for x in got.out.strip().split("."))
    except ValueError:
        return None
    return major, minor


def _stub(path: str) -> bool:
    """A Windows Store alias or a zero-byte stub is never a real interpreter."""
    p = Path(path)
    return "WindowsApps" in p.parts or (p.is_file() and p.stat().st_size == 0)


def candidates() -> list[str]:
    out: list[str] = []
    if os.environ.get("TEMPERGRAPH_PYTHON"):
        out.append(os.environ["TEMPERGRAPH_PYTHON"])
    venv = os.environ.get("VIRTUAL_ENV")
    if venv:
        out.append(str(Path(venv) / "bin" / "python"))
    for name in NAMES:
        found = shutil.which(name)
        if found and not _stub(found):
            out.append(found)
    return list(dict.fromkeys(out))


def find_python() -> tuple[str, tuple[int, int]] | None:
    for c in candidates():
        v = version_of(c)
        if v is not None and v >= MIN:
            return c, v
    return None
