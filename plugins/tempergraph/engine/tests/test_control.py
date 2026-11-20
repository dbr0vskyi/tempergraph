"""Stop requests (RCT §2, RCT-B2, RCT-B3, RCT §4; RCT-AC-2 with the launcher's tree kill)."""

from __future__ import annotations

import json
import os
import sys
import time
from pathlib import Path

import pytest

from tempergraph.contracts import EventSink
from tempergraph.durability.control import NotLive, StopWatcher, request_stop, stop_file, take_stop
from tempergraph.durability.lock import RunLock
from tempergraph.executors.claude import parse_line
from tempergraph.executors.launcher import LaunchSpec, StopRequest, launch
from tempergraph.store.layout import ensure_state_root, lock_path

from .conftest import hash_tree
from .fixtures import streams as S
from .test_launcher import alive


@pytest.fixture
def root(tmp_path: Path) -> Path:
    return ensure_state_root(tmp_path / ".tempergraph")


def test_not_live_writes_nothing(root: Path) -> None:
    before = hash_tree(root)
    with pytest.raises(NotLive):
        request_stop(root, "demo", "t")
    assert hash_tree(root) == before


def test_stronger_mode_wins_and_take_removes(root: Path) -> None:
    with RunLock(lock_path(root, "demo", "t")):
        assert request_stop(root, "demo", "t", "now", {"kind": "person"}) == "now"
        assert request_stop(root, "demo", "t", "drain") == "now"
        p = stop_file(root, "demo", "t")
        assert p.stat().st_mode & 0o777 == 0o600
        got = take_stop(root, "demo", "t")
        assert got is not None and got.mode == "now" and got.caller == {"kind": "person"}
        assert not p.exists() and take_stop(root, "demo", "t") is None


def test_unparsable_request_is_a_drain(root: Path) -> None:
    p = stop_file(root, "demo", "t")
    p.parent.mkdir(parents=True)
    p.write_text("{nope")
    got = take_stop(root, "demo", "t", stale=True)
    assert got is not None and got.mode == "drain" and got.unparsable and got.stale


@pytest.mark.skipif(os.name != "posix", reason="POSIX process groups")
def test_stop_now_ends_the_session_tree(root: Path, tmp_path: Path) -> None:
    pid = tmp_path / "gc.pid"
    sc = tmp_path / "sc.json"
    sc.write_text(json.dumps({"grandchild": str(pid), "lines": [S.init(), S.tool_use("Bash", "t1")], "hang": 120,
                              "ignore_term": True}))
    stop = StopRequest()
    spec = LaunchSpec(argv=[sys.executable, str(S.STANDIN)], stdin_payload=b"p", workdir=tmp_path, timeout_s=600,
                      session_key="code.1.step", env_overlay={"STANDIN_SCENARIO": str(sc)}, grace_s=1.0)
    with RunLock(lock_path(root, "demo", "t")), StopWatcher(root, "demo", "t", stop, poll_s=0.1) as w:
        import threading
        threading.Timer(0.5, request_stop, args=(root, "demo", "t", "now")).start()
        t = time.monotonic()
        out = launch(spec, parse_line, EventSink(), stop=stop)
    assert time.monotonic() - t < 15  # RCT-B2
    assert out.stop_reason == "stop" and out.killed and w.taken is not None and w.taken.mode == "now"
    time.sleep(0.2)
    assert not alive(int(pid.read_text()))  # RCT-AC-2
