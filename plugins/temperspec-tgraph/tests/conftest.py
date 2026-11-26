"""The package's tests run against the engine source of this repository when it sits next to the package, as the
engine's own suite does, and not against another copy of the engine installed in the environment (a checkout or a
worktree whose environment was installed from another one has an older engine)."""

from __future__ import annotations

import sys
from pathlib import Path

_ENGINE_SRC = Path(__file__).resolve().parents[2] / "tempergraph" / "engine" / "src"
if (_ENGINE_SRC / "tempergraph").is_dir() and sys.path[:1] != [str(_ENGINE_SRC)]:
    sys.path.insert(0, str(_ENGINE_SRC))
