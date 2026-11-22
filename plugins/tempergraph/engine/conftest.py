"""The project's own pytest configuration: how many worker processes the suite runs on (TST-B1 to TST-B3).

`python -m pytest` in this folder spreads its tests over one worker per processor, at most four (an earlier
ran the suite on four workers, never `auto`). `-n 0` runs one process; any other `-n`, `--dist` or `--tx` the
caller gives is left alone. When `pytest-xdist` is missing (or switched off with `-p no:xdist`) the suite runs in
one process and says which package to install, so no option is ever unknown.
"""

from __future__ import annotations

import os

import pytest

MAX_WORKERS = 4


def default_workers() -> int:
    return max(1, min(os.cpu_count() or 1, MAX_WORKERS))


def _xdist_loaded(config: pytest.Config) -> bool:
    return config.pluginmanager.hasplugin("xdist")


@pytest.hookimpl(tryfirst=True)
def pytest_cmdline_main(config: pytest.Config) -> None:
    """Choose the default worker count before the runner reads its options (a conftest is asked this hook only
    when it is an initial conftest, which this one is: it sits in the rootdir)."""
    if os.environ.get("PYTEST_XDIST_WORKER") or not _xdist_loaded(config):
        return
    opt = config.option
    if getattr(opt, "numprocesses", None) is not None:  # `-n <k>` was given, `-n 0` included
        return
    if getattr(opt, "distload", False) or getattr(opt, "tx", None) or getattr(opt, "usepdb", False):
        return
    workers = default_workers()
    if workers > 1:
        opt.numprocesses = workers


def pytest_terminal_summary(terminalreporter: object, config: pytest.Config) -> None:
    """One line when the parallel runner is not in use because it is missing (the header is hidden by `-q`)."""
    if not _xdist_loaded(config):
        terminalreporter.write_line(  # type: ignore[attr-defined]
            "pytest-xdist is not active: every test ran in one process. Install it with the `dev` extra "
            "(python -m pip install -e '.[dev]') to run on up to four workers."
        )
