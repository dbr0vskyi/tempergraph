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
import re
import subprocess
import sys
from collections.abc import Mapping
from pathlib import Path

# module -> the argv words it may be started with; nothing else is ever passed (SEC-B5, SEC-B6)
DETACHED = {"tempergraph.observe.sinks": (("flush",),), "tempergraph.improve.child": (("drain",),),
            "tempergraph.observe.hooks": (("drain",),)}
CHECKED = re.compile(r"^[A-Za-z0-9][A-Za-z0-9._@:/-]{0,200}$")  # a workflow name, a fire id, a task id: never a person's text
LOOP_WORDS = (("schedule", "loop"),)


def _spawn(argv: list[str], env: Mapping[str, str], cwd: Path | None = None) -> bool:
    """One detached child in its own process group (own session on POSIX, a new process group on Windows)."""
    extra: dict[str, object] = {}
    if os.name == "nt":
        extra["creationflags"] = getattr(subprocess, "CREATE_NEW_PROCESS_GROUP", 0) | getattr(subprocess, "DETACHED_PROCESS", 0)
    if cwd is not None:
        extra["cwd"] = str(cwd)
    with contextlib.suppress(OSError):
        subprocess.Popen(argv, env=dict(env), stdin=subprocess.DEVNULL, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL,
                         close_fds=True, start_new_session=(os.name == "posix"), **extra)  # type: ignore[call-overload]
        return True
    return False


def start(module: str, words: tuple[str, ...], home: Path) -> bool:
    """Starts `python -m <module> <words…>` detached; False when refused or when the start failed."""
    if words not in DETACHED.get(module, ()):
        return False
    return _spawn([sys.executable, "-m", module, *words], {**os.environ, "TEMPERGRAPH_HOME": str(home)})


def start_run(words: tuple[str, ...], home: Path, *, env: Mapping[str, str] | None = None, cwd: Path | None = None) -> bool:
    """The schedule tick's start (TCK-B16): `python -m tempergraph run <workflow> --schedule <fire id> --task-id <id>`.

    Every word is a constant or a checked value, and the request, the inputs and the options go through the hand-off
    ticket (SEC-B5, SEC-B6). `env` is laid over the child's environment only: it carries the fire token. `cwd` is the
    target repository the run starts in."""
    if (len(words) != 6 or words[0] != "run" or words[2] != "--schedule" or words[4] != "--task-id"
            or not all(CHECKED.match(w) for w in (words[1], words[3], words[5]))):
        return False
    return _spawn([sys.executable, "-m", "tempergraph", *words], {**os.environ, "TEMPERGRAPH_HOME": str(home), **(env or {})},
                  cwd)


def start_loop(home: Path, shim: Path | None = None) -> bool:
    """`schedule loop` detached, for `schedule loop --detach` and the host adapter (TCK-B14): constant words only. With
    `shim`, the shim's absolute path starts it, so a loop that finds a new engine installed re-executes onto it (TCK-B8)."""
    argv = [str(shim), *LOOP_WORDS[0]] if shim is not None else [sys.executable, "-m", "tempergraph", *LOOP_WORDS[0]]
    return _spawn(argv, {**os.environ, "TEMPERGRAPH_HOME": str(home)})
