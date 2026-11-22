"""The detached child launcher (SEC-B7): the engine interpreter with a constant module and constant words.

A child started here outlives its parent in its own session, with stdin, stdout and stderr closed, so a slow
share or a hung network never delays the process that started it. Release 1 starts two children: the stats
flusher at `run_exit` (CST-B10, CST-B12, CST-B13) and the self-improvement loop after a final exit (SIL-B1); release 2 adds
the lifecycle hook runner (HOK-B1 to HOK-B6). The schedule
tick's `run` and `orchestrate start` join this site later.
"""

from __future__ import annotations

import contextlib
import os
import subprocess
import sys
from pathlib import Path

# module -> the argv words it may be started with; nothing else is ever passed (SEC-B5, SEC-B6)
DETACHED = {"tempergraph.observe.sinks": (("flush",),), "tempergraph.improve.child": (("drain",),),
            "tempergraph.observe.hooks": (("drain",),)}


def start(module: str, words: tuple[str, ...], home: Path) -> bool:
    """Starts `python -m <module> <words…>` detached; False when refused or when the start failed."""
    if words not in DETACHED.get(module, ()):
        return False
    env = {**os.environ, "TEMPERGRAPH_HOME": str(home)}
    with contextlib.suppress(OSError):
        subprocess.Popen([sys.executable, "-m", module, *words], env=env, stdin=subprocess.DEVNULL,
                         stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL, close_fds=True,
                         start_new_session=(os.name == "posix"))
        return True
    return False
