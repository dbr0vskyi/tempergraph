"""Sanctioned launch sites (SEC §2.1, §2.2).

Every process launch in the engine goes through one of the functions listed here; a source-scan test
(``tests/test_source_rules.py``) fails when any other module imports :mod:`subprocess` or calls
``os.system``/``os.exec*``/``os.spawn*``/``os.popen`` (SEC-AC-1).
"""

from __future__ import annotations

# Module path -> what it launches. Keep in step with SEC §2.2.
SANCTIONED_SITES: dict[str, str] = {
    "tempergraph.git": "git reader: git with constant arguments",
    "tempergraph.run.commands": "workflow command runner: resolved allow-list argv for checks, scripts, finalizer",
    "tempergraph.executors.launcher": "session launcher: an executor's CLI, its model-free probes, host speed",
}

SHELL_METACHARACTERS = frozenset(";&|`$<>()\\\n\r*?[]{}!~#'\"")


def has_shell_metacharacter(text: str) -> bool:
    return any(ch in SHELL_METACHARACTERS for ch in text)
