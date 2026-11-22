"""Lifecycle hooks: the registry, the facts file, the detached runner and a failing hook (HOK-B1 to HOK-B6, EVT-B22, EVT-B23, EVT-B24)."""

from __future__ import annotations

import json
import sys
from pathlib import Path

import pytest

from tempergraph import detach
from tempergraph.constants import ExitCode
from tempergraph.observe import hooks
from tempergraph.store.layout import home_path, run_dir, state_root_path

from .test_cli import cli, happy

WRITE = [sys.executable, "-c",
         "import os,sys,json,pathlib;f=json.load(open(os.environ['TEMPERGRAPH_HOOK_FACTS']));"
         "pathlib.Path('hook-out.txt').open('a').write(os.environ['TEMPERGRAPH_HOOK_EVENT']+' '+f['thread_id']+'\\n');"
         "print(sys.argv[1:])"]


def out(got: tuple) -> dict:
    return got[1]


def test_add_list_remove(repo: Path) -> None:
    code, doc, _ = cli(repo, None, "hooks", "add", "finished", "--", *WRITE, "--flag")
    assert code == ExitCode.FINISHED
    added = doc["added"]
    assert added["event"] == "finished" and added["argv"][-1] == "--flag"
    listed = out(cli(repo, None, "hooks", "list"))
    assert [h["id"] for h in listed["hooks"]] == [added["id"]] and "paused" in listed["events"]
    assert cli(repo, None, "hooks", "remove", added["id"])[0] == ExitCode.FINISHED
    assert out(cli(repo, None, "hooks", "list"))["hooks"] == []
    assert cli(repo, None, "hooks", "remove", added["id"])[0] == ExitCode.USAGE


@pytest.mark.parametrize("argv", [["hooks", "add", "nonsense", "--", "true"], ["hooks", "add", "stalled", "--", "true"],
                                  ["hooks", "add", "finished"], ["hooks", "add", "finished", "--", "a\nb"]])
def test_add_refusals_write_nothing(repo: Path, argv: list[str]) -> None:
    assert cli(repo, None, *argv)[0] == ExitCode.USAGE
    assert not hooks.config_path(state_root_path(repo)).exists()


def test_events_of_records() -> None:
    assert hooks.event_of({"kind": "run_started", "segment": 0}) == "started"
    assert hooks.event_of({"kind": "run_started", "segment": 2}) == "resumed"
    assert hooks.event_of({"kind": "run_exit", "exit_code": 0}) == "finished"
    assert hooks.event_of({"kind": "run_exit", "exit_code": 3}) is None
    assert hooks.event_of({"kind": "run_exit", "exit_code": 5}) == "failed"
    assert hooks.event_of({"kind": "pause"}) == "paused" and hooks.event_of({"kind": "session"}) is None


def test_a_run_fires_hooks_with_facts_only(repo: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    started: list[tuple] = []
    monkeypatch.setattr(detach, "start", lambda m, w, h: started.append((m, *w)) or True)
    for event in ("started", "gate_verdict", "finished"):
        cli(repo, None, "hooks", "add", event, "--", *WRITE)
    code, doc, _ = cli(repo, happy(), "run", "demo", "write the secret request text", "--json")
    assert code == ExitCode.FINISHED
    assert started and set(started) == {("tempergraph.observe.hooks", "drain")}
    root = state_root_path(repo)
    tid = doc["thread_id"].split("/")[1]
    folder = run_dir(root, "demo", tid) / "hooks"
    facts = [json.loads(p.read_text()) for p in sorted(folder.glob("*.facts.json"))]
    assert {f["event"] for f in facts} == {"started", "gate_verdict", "finished"}
    assert all("secret request" not in json.dumps(f) for f in facts)  # ids, enums and numbers only (SEC-B5, SEC-B6)
    tickets = list(hooks.tickets_dir(home_path()).glob("*.json"))
    assert tickets and all("argv" not in json.loads(t.read_text()) for t in tickets)
    done = hooks.drain()  # what the detached child does
    assert done and all(d["ok"] for d in done)
    lines = (repo / "hook-out.txt").read_text().splitlines()
    assert f"finished demo/{tid}" in lines and f"started demo/{tid}" in lines
    results = [json.loads(x) for x in (folder / "results.jsonl").read_text().splitlines()]
    assert len(results) == len(done) and not list(hooks.tickets_dir(home_path()).glob("*"))
    assert list(folder.glob("finished-*.log"))


def test_a_failing_hook_never_changes_the_run(repo: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(detach, "start", lambda m, w, h: (_ for _ in ()).throw(RuntimeError("no child")))
    cli(repo, None, "hooks", "add", "finished", "--", sys.executable, "-c", "raise SystemExit(7)")
    cli(repo, None, "hooks", "add", "started", "--", "/no/such/program")
    code, doc, _ = cli(repo, happy(), "run", "demo", "write it", "--json")
    assert code == ExitCode.FINISHED and doc["exit_code"] == 0, doc
    done = hooks.drain()
    assert {d["exit_code"] for d in done} == {7, None} and not any(d["ok"] for d in done)


def test_ticket_is_validated_again(repo: Path, tmp_path: Path) -> None:
    cli(repo, None, "hooks", "add", "finished", "--", *WRITE)
    root = state_root_path(repo)
    (hid,) = [h["id"] for h in hooks.load(root)]
    base = {"root": str(root), "workflow": "demo", "task_id": "t1", "event": "finished", "seq": 4, "hook": hid}
    for bad in ({"root": str(tmp_path)}, {"workflow": "../x"}, {"event": "bogus"}, {"hook": "ffffffff"},
                {"seq": "4; rm"}, {}):  # the last one: no facts file for this thread
        assert hooks.process({**base, **bad}) == {"error": "ticket_refused"}
    assert not (repo / "hook-out.txt").exists()


def test_hooks_test_runs_against_a_fixture(repo: Path) -> None:
    cli(repo, None, "hooks", "add", "paused", "--", *WRITE)
    code, doc, _ = cli(repo, None, "hooks", "test", "paused")
    assert code == ExitCode.FINISHED and doc["results"][0]["ok"]
    assert (repo / "hook-out.txt").read_text() == "paused example/hook-test\n"
    cli(repo, None, "hooks", "add", "paused", "--", sys.executable, "-c", "raise SystemExit(1)")
    assert cli(repo, None, "hooks", "test", "paused")[0] == ExitCode.ADVISORY


def test_detached_site_is_constant() -> None:  # SEC-B7
    assert detach.DETACHED["tempergraph.observe.hooks"] == (("drain",),)
    assert hooks.main(["drain", "extra"]) == 2
