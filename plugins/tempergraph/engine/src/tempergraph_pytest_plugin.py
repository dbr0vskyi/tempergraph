"""The engine's pytest plugin: a home folder of its own and the self-improvement loop off wherever pytest runs
(TST-B7 to TST-B12).

The engine's install declares this module under the `pytest11` entry point, as `tempergraph.pytest_plugin`, so every
pytest run of the environment loads it, from whatever folder pytest starts in and with nothing written in the
package under test. `-p no:tempergraph.pytest_plugin` switches all of it off (TST-B11).

It imports only the standard library and pytest, never the engine package: pytest loads it before it imports any
conftest, and a conftest (the engine's own suite's) is where a checkout puts its own `src` first, so loading this
module must leave `tempergraph` unimported (TST-B12).

- Before any conftest is imported, the session gets a home folder of its own and the loop off, so code that runs at
  import time and fixtures of session, module and class scope see them too (TST-B9, TST-B10). Workers inherit the
  values and each makes a folder of its own.
- Each test gets a home folder of its own and the loop off. A test that sets either variable itself afterwards keeps
  its value; both are restored when the test ends (TST-B7, TST-B8).
"""

from __future__ import annotations

import os
import shutil
import tempfile
from pathlib import Path

import pytest

_VARIABLES = ("TEMPERGRAPH_HOME", "TEMPERGRAPH_LOOP")
_UNSET = object()
_session: dict[str, object] = {}


@pytest.hookimpl(tryfirst=True)
def pytest_load_initial_conftests() -> None:
    """Give the session a home folder of its own and the loop off, before any conftest or test module is imported."""
    if _session:
        return
    folder = tempfile.mkdtemp(prefix="tempergraph-session-")
    _session["folder"] = folder
    _session["before"] = {name: os.environ.get(name, _UNSET) for name in _VARIABLES}
    os.environ["TEMPERGRAPH_HOME"] = str(Path(folder) / ".tempergraph")
    os.environ["TEMPERGRAPH_LOOP"] = "off"  # no detached loop child from a test run (SIL-B1)


def pytest_unconfigure() -> None:
    """Restore the two variables as the process had them and remove the session's folder."""
    if not _session:
        return
    before = _session["before"]
    assert isinstance(before, dict)
    for name, value in before.items():
        if value is _UNSET:
            os.environ.pop(name, None)
        else:
            os.environ[name] = str(value)
    shutil.rmtree(str(_session["folder"]), ignore_errors=True)
    _session.clear()


@pytest.fixture(autouse=True)
def _tempergraph_isolated_home(tmp_path_factory: pytest.TempPathFactory, monkeypatch: pytest.MonkeyPatch) -> None:
    home = tmp_path_factory.mktemp("tempergraph-home")
    monkeypatch.setenv("TEMPERGRAPH_HOME", str(home / ".tempergraph"))
    monkeypatch.setenv("TEMPERGRAPH_LOOP", "off")  # no detached loop child from a test run (SIL-B1)
