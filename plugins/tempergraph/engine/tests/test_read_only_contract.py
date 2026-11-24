"""Read-only verbs call no model and create nothing but a lost runner's hand-off (OVR-B15, SIL-B29)."""

from __future__ import annotations

from pathlib import Path
from typing import Any

import pytest

from tempergraph import detach
from tempergraph.constants import ExitCode
from tempergraph.executors.standins import standin
from tempergraph.improve import child
from tempergraph.store.layout import home_path, state_root_path

from .conftest import hash_tree
from .test_cli import cli, happy
from .test_loop_fixes_coverage import carriers
from .test_reports import paused_run

# The owner specs' criteria of the contract: the CLI's (read-only verbs, attention), run control's (stop),
# durability's (`status` writes nothing) and the loop's lost-runner criteria.
OWNER_CRITERIA = ("CLI-AC1", "CLI-AC5", "RCT-AC5", "DUR-AC3",
                  "SIL-AC22", "SIL-AC23", "SIL-AC24", "SIL-AC25", "SIL-AC26", "SIL-AC27", "SIL-AC28")


def test_verbs_on_a_state_root_with_no_lost_runner_start_nothing(repo: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    # OVR-AC5
    started: list[Any] = []
    monkeypatch.setenv("TEMPERGRAPH_LOOP", "detached")
    monkeypatch.setattr(detach, "start", lambda *a, **k: started.append((a, k)) or True)
    assert cli(repo, happy(), "run", "demo", "notes", "--task-id", "T-1")[0] == 0  # a finished thread
    paused_run(repo, "T-2")  # and a paused one
    started.clear()  # what the runs themselves started is not the verbs' doing
    tickets_before = sorted(child.tickets_dir(home_path()).glob("*.json"))
    ex = standin("claude", steps=[], judges=[])
    root = state_root_path(repo)
    before = (hash_tree(root), hash_tree(home_path()))
    codes = [cli(repo, ex, "status")[0], cli(repo, ex, "attention")[0],
             cli(repo, ex, "stop", "demo/T-1")[0], cli(repo, ex, "stop", "demo/T-2")[0]]
    assert codes == [0, 0, ExitCode.USAGE, ExitCode.USAGE]  # a paused thread holds no lock either
    assert ex.calls == [] and started == []  # no session, no loop child
    assert sorted(child.tickets_dir(home_path()).glob("*.json")) == tickets_before
    assert (hash_tree(root), hash_tree(home_path())) == before


def test_every_owner_criterion_of_the_contract_is_carried_by_a_test_that_runs() -> None:
    # OVR-AC5
    missing = [c for c in OWNER_CRITERIA if not carriers(c)]
    assert missing == [], f"no test that runs carries {missing}"
