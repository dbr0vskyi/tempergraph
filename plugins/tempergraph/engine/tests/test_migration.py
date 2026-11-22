"""A thread at its next resume, a workflow changed under a thread, and store layout steps
(MIG-B9, MIG-B10, MIG-B5, MIG-B12, MIG-B13, MIG-B14, MIG-B15; MIG-AC1 to AC-5)."""

from __future__ import annotations

import dataclasses
import io
import json
import os
from pathlib import Path
from typing import Any

import pytest

from tempergraph.api import Gate, Judge, Step, Workflow
from tempergraph.catalog import Catalog
from tempergraph.cli.main import main
from tempergraph.constants import ENGINE_VERSION, ExitCode
from tempergraph.contracts import InputDeclaration, Param
from tempergraph.durability import engine_file as ef
from tempergraph.durability.status import status
from tempergraph.release import release
from tempergraph.run.runner import resume
from tempergraph.store import migrate
from tempergraph.store.layout import checkpoint_path, ensure_state_root, home_path, run_dir, state_root_path

from .conftest import hash_tree
from .fixtures.workflows import crit, named, two_step
from .test_run import DRAFT, NO_SLEEP, REVIEW, go, judge, records, registry, standin, verdict_block


def paused(repo: Path) -> Path:
    """A thread of `demo` paused at `review`, with `draft` behind it."""
    ex = standin("claude", steps=[DRAFT, REVIEW], judges=[judge(), judge(verdict_block("UNVERIFIABLE"))])
    assert go(repo, ex).exit_code is ExitCode.PAUSED
    return state_root_path(repo)


def history(root: Path, **fields: Any) -> None:
    """Rewrite the thread's last history entry, as an older engine version would have left it."""
    doc = ef.read(root, "demo", "T-1")
    doc["history"][-1].update(fields)
    ef.path(root, "demo", "T-1").write_text(json.dumps(doc), encoding="utf-8")


def keep(home: Path, name: str, formats: list[int]) -> Path:
    env = home / "engines" / name
    env.mkdir(parents=True)
    (env / ".complete").write_text("x\n", encoding="utf-8")
    (env / "release.json").write_text(json.dumps({"resumes_checkpoint_formats": formats}), encoding="utf-8")
    return env


def release_is(monkeypatch: pytest.MonkeyPatch, **fields: Any) -> None:
    doc = {**release(), **fields}
    monkeypatch.setattr("tempergraph.release.release", lambda: doc)


def cli(repo: Path, *argv: str, handed: list[Any] | None = None) -> tuple[int, str]:
    out, err = io.StringIO(), io.StringIO()

    def hand_over(interpreter: Path, args: list[str]) -> int:
        assert handed is not None, "nothing was to be handed to another engine"
        handed.append((interpreter, args))
        return 0

    ex = standin("claude", steps=[REVIEW], judges=[judge()])
    code = main(list(argv), catalog=Catalog(specs={"demo": two_step()}), registry=registry(ex), cwd=repo, out=out,
                err=err, signals=({}, True), hand_over=hand_over, run_settings=lambda **kw: NO_SLEEP)
    return code, out.getvalue() + err.getvalue()


# -- MIG-B12, MIG-B13, MIG-B14 and MIG-B2: the decision -------------------------------------------------------------------------


@pytest.mark.parametrize(("fmt", "resumes", "kept", "want"), [
    (2, [2, 3], {}, ("move", None)),
    (2, [3], {"1.6.2-aaa": [2]}, ("pin", "1.6.2-aaa")),
    (2, [3], {"1.6.2-aaa": [2], "1.7.0-bbb": [2, 3], "1.5.0-ccc": [1]}, ("pin", "1.7.0-bbb")),
    (2, [3], {"1.5.0-ccc": [1]}, ("refuse", None)),
])
def test_decision_by_checkpoint_format(fmt: int, resumes: list[int], kept: dict[str, list[int]],
                                       want: tuple[str, str | None]) -> None:
    got = ef.decide({"history": [{"checkpoint_format": fmt}]}, resumes=resumes, kept=kept)
    assert got[0] == want[0]
    if want[0] == "refuse":
        assert "format 2" in str(got[1])
    else:
        assert got[1] == want[1]


def test_a_pinned_thread_dispatches_whatever_this_engine_resumes() -> None:
    doc = {"pinned": {"engine": "1.6.2-aaa"}, "history": [{"checkpoint_format": 1}]}
    assert ef.decide(doc, resumes=[1], kept={}) == ("dispatch", "1.6.2-aaa")
    assert ef.decide(doc, resumes=[1], kept={}, current="1.6.2-aaa") == ("move", None)  # the pinned engine itself


def test_a_thread_from_before_the_record_is_not_pinned(repo: Path) -> None:  # MIG-B16, MIG-B12, MIG-B10, MIG-B15
    root = paused(repo)
    ef.path(root, "demo", "T-1").unlink()
    assert ef.at_resume(root, "demo", "T-1") == ("move", None)
    ex = standin("claude", steps=[REVIEW], judges=[judge()])
    assert resume(two_step(), "T-1", repo, registry(ex), decision="proceed",
                  settings=NO_SLEEP).exit_code is ExitCode.FINISHED
    doc = ef.read(root, "demo", "T-1")
    assert doc["last_on"]["engine_version"] == ENGINE_VERSION
    # live check L-27: a release 1 thread was recorded as started on 0.2.0; the start is unknown (MIG-B16, MIG-B12, MIG-B10, MIG-B15)
    assert doc["started_on"] == {"engine_version": None, "engine": "unknown"}
    started = [r for r in records(repo) if r["kind"] == "run_started"]
    assert started[-1]["moved_from"] == {"engine_version": "unknown", "workflow_version": None}
    assert not [r for r in records(repo) if r["kind"] == "workflow_changed"]


# -- MIG-B1: a paused thread moves -----------------------------------------------------------------------------


def test_a_paused_thread_moves_to_this_engine(repo: Path) -> None:
    root = paused(repo)
    first = next(r for r in records(repo) if r["kind"] == "run_started")
    assert first["engine_version"] == ENGINE_VERSION and first["shape_digest"]
    assert "moved_from" not in first
    history(root, engine_version="0.0.0-earlier")
    code, text = cli(repo, "resume", "demo", "T-1", "--decision", "proceed")
    assert code == 0, text
    started = [r for r in records(repo) if r["kind"] == "run_started"]
    assert started[-1]["moved_from"] == {"engine_version": "0.0.0-earlier", "workflow_version": "0.1.0"}
    doc = ef.read(root, "demo", "T-1")
    assert len(doc["history"]) == 2 and doc["pinned"] is None and "units" not in doc["history"][0]
    row = status(root, {"demo": two_step()})["threads"][0]
    assert row["engine"] == ENGINE_VERSION and "engine_pin" not in row


# -- MIG-B2: a format break pins -------------------------------------------------------------------------------


def test_a_format_break_pins_and_hands_the_resume_over(repo: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    root = paused(repo)
    history(root, checkpoint_format=2)
    env = keep(home_path(), "1.6.2-aaa", [2])
    release_is(monkeypatch, checkpoint_format=3, resumes_checkpoint_formats=[3])
    handed: list[Any] = []
    argv = ("resume", "demo", "T-1", "--decision", "proceed")
    assert cli(repo, *argv, handed=handed)[0] == 0
    assert handed == [(env / "bin" / "python", list(argv))]
    pin = ef.read(root, "demo", "T-1")["pinned"]
    assert pin["engine"] == "1.6.2-aaa" and pin["reason"] == "checkpoint_format" and pin["since"]
    assert len([r for r in records(repo) if r["kind"] == "run_started"]) == 1  # this engine resumed nothing
    assert cli(repo, *argv, handed=handed)[0] == 0 and len(handed) == 2  # pinned: dispatched again
    monkeypatch.undo()
    row = status(root, {"demo": two_step()})["threads"][0]
    assert row["engine_pin"]["engine"] == "1.6.2-aaa"
    out = resume(two_step(), "T-1", repo, registry(standin("claude")), decision="proceed", settings=NO_SLEEP)
    assert out.exit_code is ExitCode.USAGE and out.reason == "engine_pinned"  # the runner never resumes it itself


def test_no_kept_engine_resumes_the_format(repo: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    root = paused(repo)
    history(root, checkpoint_format=2)
    keep(home_path(), "1.5.0-ccc", [1])
    release_is(monkeypatch, checkpoint_format=3, resumes_checkpoint_formats=[3])
    before = hash_tree(root)
    code, text = cli(repo, "resume", "demo", "T-1", "--decision", "proceed")
    assert code == 2 and "resumes format 2" in text
    assert hash_tree(root) == before


def test_a_pinned_engine_that_is_gone(repo: Path) -> None:  # MIG-B16, MIG-B12, MIG-B10, MIG-B15
    root = paused(repo)
    ef.pin(root, "demo", "T-1", "1.6.2-aaa", "checkpoint_format")
    before = hash_tree(root)
    code, text = cli(repo, "resume", "demo", "T-1", "--decision", "proceed")
    assert code == 2 and "1.6.2-aaa" in text and "tempergraph update" in text
    assert hash_tree(root) == before
    code, text = cli(repo, "resume", "demo", "T-1", "--decision", "proceed", "--unpin")  # this engine resumes it
    assert code == 0, text
    assert ef.read(root, "demo", "T-1")["pinned"] is None


def test_unpin_is_refused_without_a_converter(repo: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    root = paused(repo)
    history(root, checkpoint_format=2)
    ef.pin(root, "demo", "T-1", "1.6.2-aaa", "checkpoint_format")
    release_is(monkeypatch, checkpoint_format=3, resumes_checkpoint_formats=[3])
    code, text = cli(repo, "resume", "demo", "T-1", "--decision", "proceed", "--unpin")
    assert code == 2 and "converter" in text and ef.read(root, "demo", "T-1")["pinned"]


def test_a_finished_thread_loses_its_pin(repo: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    root = paused(repo)
    ef.pin(root, "demo", "T-1", "9.9.9-zzz", "checkpoint_format")
    monkeypatch.setattr(ef, "this_engine", lambda: {"engine_version": ENGINE_VERSION, "engine": "9.9.9-zzz"})
    assert cli(repo, "resume", "demo", "T-1", "--decision", "proceed")[0] == 0  # this process is the pinned engine
    assert ef.read(root, "demo", "T-1")["pinned"] is None


def test_two_formats_never_share_a_database(repo: Path, monkeypatch: pytest.MonkeyPatch) -> None:  # MIG-AC5
    root = paused(repo)
    assert checkpoint_path(root, "demo").name == "demo.sqlite"  # format 1 keeps its name
    release_is(monkeypatch, checkpoint_format=3, resumes_checkpoint_formats=[1, 3])
    ex = standin("claude", steps=[DRAFT, REVIEW], judges=[judge(), judge()])
    assert go(repo, ex, task="T-2").exit_code is ExitCode.FINISHED
    assert (root / "checkpoints" / "demo.f3.sqlite").is_file()
    assert ef.checkpoint_of(root, "demo", "T-2").name == "demo.f3.sqlite"
    assert ef.checkpoint_of(root, "demo", "T-1").name == "demo.sqlite"  # the older thread stays in its own file
    ex = standin("claude", steps=[REVIEW], judges=[judge()])
    assert resume(two_step(), "T-1", repo, registry(ex), decision="proceed",
                  settings=NO_SLEEP).exit_code is ExitCode.FINISHED  # moved: resumed where it was written
    release_is(monkeypatch, checkpoint_format=3, resumes_checkpoint_formats=[3])
    assert ef.at_resume(root, "demo", "T-1")[0] == "refuse"  # an engine never opens a format it does not resume


# -- MIG-B15: a workflow changed under a thread ---------------------------------------------------------------


def changed(**units: Any) -> Any:
    base = two_step()
    merged = {**base.units, **units}
    return dataclasses.replace(base, units={k: v for k, v in merged.items() if v is not None}, version="0.2.0")


def step_of(spec: Any, unit: str, **fields: Any) -> Any:
    return dataclasses.replace(spec.units[unit], step=dataclasses.replace(spec.units[unit].step, **fields))


def refused(repo: Path, spec: Any) -> str:
    root = state_root_path(repo)
    before = hash_tree(run_dir(root, "demo", "T-1"))
    out = resume(spec, "T-1", repo, registry(standin("claude")), decision="proceed", settings=NO_SLEEP)
    assert out.exit_code is ExitCode.USAGE and out.reason == "workflow_changed", out.message
    assert "0.1.0" in out.message and "start a new thread" in out.message
    assert hash_tree(run_dir(root, "demo", "T-1")) == before  # nothing written
    return "; ".join(out.refusals)


def renamed() -> Any:
    spec = two_step()
    w = Workflow(order=["draft", "elaborate"], units={
        "draft": Step(prompt="Write the notes for {request} into notes.md", tools=["read", "write"],
                      produces={"notes": "file"}, gate=Gate(judge=Judge(stance="Verify."), criteria=[crit("c-file")])),
        "elaborate": Step(prompt="Review {notes}", tools=["read"],
                          gate=Gate(judge=Judge(stance="Verify."), criteria=[crit("c-review")]))})
    return dataclasses.replace(named(w, version="0.2.0"), package_root=spec.package_root)


def test_a_renamed_pending_unit_refuses(repo: Path) -> None:  # MIG-B4
    paused(repo)
    assert "the pending unit 'review' no longer exists" in refused(repo, renamed())


def test_a_pending_unit_of_another_kind_refuses() -> None:
    prev = {"units": {"review": {"kind": "script", "digest": "x", "produces": []}}}
    got = ef.breaks(prev, two_step(), {"attempts": {}, "request": {"inputs": {}}}, ["review"])
    assert got == ["the pending unit 'review' changed kind from script to step"]


def test_a_completed_unit_that_is_gone_refuses(repo: Path) -> None:
    paused(repo)
    w = Workflow(order=["review"], units={"review": Step(
        prompt="Review for {task_id}", tools=["read"],
        gate=Gate(judge=Judge(stance="Verify."), criteria=[crit("c-review")]))})
    assert "the completed unit 'draft' no longer exists" in refused(repo, named(w, version="0.2.0"))


def test_a_key_this_thread_never_recorded_refuses(repo: Path) -> None:
    paused(repo)
    base = two_step()
    spec = changed(draft=step_of(base, "draft", produces={**base.units["draft"].step.produces, "summary": "file"}),
                   review=step_of(base, "review", prompt="Review {notes} and {summary} for {task_id}"))
    assert "'draft' now produces 'summary'" in refused(repo, spec)


def test_a_new_required_input_refuses(repo: Path) -> None:
    paused(repo)
    spec = dataclasses.replace(changed(), input=InputDeclaration(parameters=(Param(name="audience"),)))
    assert "the input parameter 'audience' has no value" in refused(repo, spec)


def test_a_change_that_keeps_the_path_resumes_with_one_notice(repo: Path) -> None:  # MIG-B3
    root = paused(repo)
    base = two_step()
    review = base.units["review"]
    spec = changed(review=dataclasses.replace(review, gate=dataclasses.replace(
        review.gate, judge=dataclasses.replace(review.gate.judge, brief="Read the notes twice"))))
    ex = standin("claude", steps=[REVIEW], judges=[judge()])
    out = resume(spec, "T-1", repo, registry(ex), decision="proceed", settings=NO_SLEEP)
    assert out.exit_code is ExitCode.FINISHED, out.message
    recs = records(repo)
    notices = [r for r in recs if r["kind"] == "workflow_changed"]
    assert len(notices) == 1 and notices[0]["units"] == ["review"]
    assert (notices[0]["from_version"], notices[0]["to_version"]) == ("0.1.0", "0.2.0")
    started = [r for r in recs if r["kind"] == "run_started"][-1]
    assert started["moved_from"] == {"engine_version": ENGINE_VERSION, "workflow_version": "0.1.0"}
    assert ef.last(ef.read(root, "demo", "T-1"))["workflow_version"] == "0.2.0"


def test_an_unchanged_workflow_writes_no_notice(repo: Path) -> None:
    paused(repo)
    ex = standin("claude", steps=[REVIEW], judges=[judge()])
    assert resume(two_step(), "T-1", repo, registry(ex), decision="proceed",
                  settings=NO_SLEEP).exit_code is ExitCode.FINISHED
    recs = records(repo)
    assert not [r for r in recs if r["kind"] == "workflow_changed"]
    assert all("moved_from" not in r for r in recs if r["kind"] == "run_started")


# -- MIG-B9, MIG-B10, MIG-B5: layout steps ------------------------------------------------------------------------------------


def old_root(tmp_path: Path) -> Path:
    """A state root one layout behind, with one settings file a step will move."""
    root = ensure_state_root(tmp_path / "state")
    man = json.loads((root / "manifest.json").read_text())
    (root / "manifest.json").write_text(json.dumps({**man, "layout": 0}), encoding="utf-8")
    (root / "config" / "settings.json").write_text('{"a": 1}', encoding="utf-8")
    return root


def _move(root: Path) -> None:
    os.replace(root / "config" / "settings.json", root / "config" / "overrides.json")


ADDITIVE = {0: migrate.Step(from_layout=0, kind="additive", apply=lambda r: (r / "notes").mkdir(exist_ok=True))}
BREAKING = {0: migrate.Step(from_layout=0, kind="breaking", apply=_move, touches=lambda r: ["config/settings.json"])}


def test_an_additive_step_before_and_after(tmp_path: Path) -> None:  # MIG-AC3
    root = old_root(tmp_path)
    assert migrate.migrate(root, target=1, engine="9.0.0", steps=ADDITIVE) == [0]
    man = json.loads((root / "manifest.json").read_text())
    assert man["layout"] == 1 and man["moved_by"] == "9.0.0" and not man.get("backup")
    assert (root / "notes").is_dir() and not (root / "backups").exists()
    after = hash_tree(root)
    assert migrate.migrate(root, target=1, engine="9.0.0", steps=ADDITIVE) == []  # idempotent
    assert hash_tree(root) == after and not (root / "locks" / ".migrate").exists()


def test_a_breaking_step_backs_up_what_it_moves(tmp_path: Path) -> None:
    root = old_root(tmp_path)
    assert migrate.migrate(root, target=1, engine="9.0.0", steps=BREAKING) == [0]
    man = json.loads((root / "manifest.json").read_text())
    backup = Path(man["backup"])
    assert backup.parent == root / "backups" and backup.name.startswith("layout-0-")
    assert (backup / "config" / "settings.json").read_text() == '{"a": 1}'
    assert json.loads((backup / "manifest.json").read_text())["layout"] == 0
    assert (root / "config" / "overrides.json").is_file() and not (root / "config" / "settings.json").exists()


def test_a_fault_mid_step_restores_the_backup(tmp_path: Path) -> None:
    root = old_root(tmp_path)

    def half(r: Path) -> None:
        (r / "config" / "settings.json").write_text("half-written", encoding="utf-8")
        raise RuntimeError("disk")

    steps = {0: migrate.Step(from_layout=0, kind="breaking", apply=half, touches=lambda r: ["config/settings.json"])}
    with pytest.raises(migrate.MigrationFailed, match="unchanged"):
        migrate.migrate(root, target=1, engine="9.0.0", steps=steps)
    assert (root / "config" / "settings.json").read_text() == '{"a": 1}'
    assert json.loads((root / "manifest.json").read_text())["layout"] == 0
    assert not (root / "locks" / ".migrate").exists()


def test_a_held_migration_lock_refuses_with_the_holder(tmp_path: Path) -> None:  # MIG-B16, MIG-B12, MIG-B10, MIG-B15
    root = old_root(tmp_path)
    (root / "locks" / ".migrate").write_text("4242", encoding="utf-8")
    with pytest.raises(migrate.MigrationRefused, match="pid 4242"):
        migrate.migrate(root, target=1, engine="9.0.0", steps=ADDITIVE, wait_s=0.2)
    assert json.loads((root / "manifest.json").read_text())["layout"] == 0


def test_a_breaking_step_waits_for_a_run_of_an_older_engine(tmp_path: Path) -> None:  # MIG-B5
    root = old_root(tmp_path)
    holder = root / "locks" / "demo" / "T-1.holder.json"
    holder.parent.mkdir(parents=True)
    holder.write_text(json.dumps({"pid": os.getppid(), "engine_version": "0.0.0-earlier"}), encoding="utf-8")
    live = lambda r: migrate.older_live(r, "9.0.0")  # noqa: E731
    assert live(root) == ["demo/T-1"]
    with pytest.raises(migrate.MigrationRefused, match=r"demo/T-1 .*stop --drain"):
        migrate.migrate(root, target=1, engine="9.0.0", steps=BREAKING, older_live=live)
    assert (root / "config" / "settings.json").is_file() and not (root / "backups").exists()
    assert migrate.migrate(root, target=1, engine="9.0.0", steps=ADDITIVE, older_live=live) == [0]  # additive goes on
    root2 = old_root(tmp_path / "second")
    assert migrate.migrate(root2, target=1, engine="9.0.0", steps=BREAKING, older_live=live) == [0]  # none live


def test_reading_never_migrates_and_the_first_write_does(repo: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    root = paused(repo)  # MIG-AC4
    man = json.loads((root / "manifest.json").read_text())
    (root / "manifest.json").write_text(json.dumps({**man, "layout": 0}), encoding="utf-8")
    monkeypatch.setattr(migrate, "STEPS", ADDITIVE)
    before = hash_tree(root)
    for verb in (("status", "--json"), ("list",), ("status", "demo/T-1", "--json")):
        assert cli(repo, *verb)[0] == 0
    assert hash_tree(root) == before
    assert cli(repo, "resume", "demo", "T-1", "--decision", "proceed")[0] == 0
    assert json.loads((root / "manifest.json").read_text())["layout"] == 1 and (root / "notes").is_dir()
