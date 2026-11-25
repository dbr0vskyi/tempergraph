"""The engine's pytest plugin: a home folder of its own and the self-improvement loop off for every test (TST-B7, TST-B8).

The engine's install declares it under the `pytest11` entry point, so every pytest run of the environment loads it,
from whatever folder pytest starts in and with nothing written in the test's own package. A test that sets one of
the two variables itself afterwards keeps its value; both are restored when the test ends.
"""

from __future__ import annotations

import pytest


@pytest.fixture(autouse=True)
def _tempergraph_isolated_home(tmp_path_factory: pytest.TempPathFactory, monkeypatch: pytest.MonkeyPatch) -> None:
    home = tmp_path_factory.mktemp("tempergraph-home")
    monkeypatch.setenv("TEMPERGRAPH_HOME", str(home / ".tempergraph"))
    monkeypatch.setenv("TEMPERGRAPH_LOOP", "off")  # no detached loop child from a test run (SIL-B1)
