"""The updater's launch site (SEC §2.2): `python -m venv`, `pip` from engine-derived paths and an
engine-written requirements file, the interpreter probe and the self-check. Argv holds constants and
engine-computed paths only; no shell; output captured; a timeout on every call."""

from __future__ import annotations

import subprocess
from dataclasses import dataclass
from pathlib import Path

INSTALL_TIMEOUT_S = 1800
PROBE_TIMEOUT_S = 20


@dataclass(frozen=True)
class Ran:
    code: int
    out: str
    err: str


def run(argv: list[str], *, timeout_s: int = PROBE_TIMEOUT_S, cwd: Path | None = None) -> Ran:
    try:
        p = subprocess.run(argv, capture_output=True, text=True, timeout=timeout_s, cwd=cwd,
                           stdin=subprocess.DEVNULL, check=False)
    except (OSError, subprocess.TimeoutExpired) as exc:
        return Ran(127 if isinstance(exc, OSError) else 124, "", type(exc).__name__)
    return Ran(p.returncode, p.stdout, p.stderr)
