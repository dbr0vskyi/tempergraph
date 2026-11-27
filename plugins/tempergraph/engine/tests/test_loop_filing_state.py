"""What decides a final exit's filing: the thread's `run.loop_dry_run`, the legacy log rule, the lift of a declared
`record` and the hold; the improvement mode decides nothing of it (LFS-B2 to LFS-B6)."""

from __future__ import annotations

import dataclasses
import itertools
import json
from pathlib import Path
from typing import Any

import pytest

from tempergraph import detach
from tempergraph.catalog import Catalog
from tempergraph.constants import ExitCode
from tempergraph.contracts import RunOptions
from tempergraph.executors.standins import standin
from tempergraph.improve import child
from tempergraph.improve import proposals as prp
from tempergraph.improve.codehost import MemoryCodeHost
from tempergraph.run import runner
from tempergraph.run.runner import RunSettings

from .fixtures.workflows import two_step
from .test_cli import cli
from .test_loop_child import judge_says, tickets
from .test_run import DRAFT, REVIEW, judge, registry, verdict_block

KEY = "run.loop_dry_run"
SUMMARY = {"lenses": {"friction": True}, "fault_fingerprints": ["abc"], "outcome_fingerprints": [],
           "fingerprints": ["abc"]}


def declare_record(repo: Path, monkeypatch: pytest.MonkeyPatch) -> bytes:
    """The run's spec is no package (the preflight would refuse a bare one): only the declared level is read from one."""
    pkg = repo / "pkg"
    pkg.mkdir(exist_ok=True)
    (pkg / "tempergraph.json").write_text(json.dumps({"improvement": {"autonomy": "record"}}))
    real = prp.autonomy
    monkeypatch.setattr(prp, "autonomy", lambda spec, machine=None, setting=None: real(
        dataclasses.replace(spec, package_root=pkg), machine, setting))
    return (pkg / "tempergraph.json").read_bytes()


def settings_file(**values: Any) -> None:
    import os

    home = Path(os.environ["TEMPERGRAPH_HOME"])
    (home / "config").mkdir(parents=True, exist_ok=True)
    (home / "config" / "settings.json").write_text(json.dumps(
        {"schema_version": 1, "defaults": {f"run.{k}": v for k, v in values.items()}}))


def thread(repo: Path, monkeypatch: pytest.MonkeyPatch, task: str, spec: Any = None, run_argv: tuple[str, ...] = (),
           resume_argv: tuple[str, ...] = ()) -> Path:
    """A thread with one blocked attempt, paused at the next judge, resumed to its final exit; the ticket's path."""
    monkeypatch.setenv("TEMPERGRAPH_LOOP", "detached")
    monkeypatch.setattr(detach, "start", lambda *a, **k: True)
    cat = Catalog(specs={"demo": spec or two_step()})
    ex = standin("claude", steps=[DRAFT, DRAFT], judges=[judge(verdict_block("UNMET")),
                                                         judge(verdict_block("UNVERIFIABLE"))])
    code, _, err = cli(repo, ex, "run", "demo", "notes", "--task-id", task, *run_argv, catalog=cat)
    assert code == ExitCode.PAUSED, err
    ex.steps, ex.judges = [REVIEW], [judge()]
    code, _, err = cli(repo, ex, "resume", "demo", task, "--decision", "proceed", *resume_argv, catalog=cat)
    assert code == 0, err
    (path,) = tickets()
    return path


def drained(path: Path) -> tuple[dict[str, Any], dict[str, Any], MemoryCodeHost]:
    """The ticket as written, the child's result and the host after the child has judged and filed."""
    doc = json.loads(path.read_text())
    path.write_text(json.dumps({**doc, "issue_repository": "team/notes", "review": "off"}))
    host = MemoryCodeHost()
    (out,) = child.drain(registry=registry(standin("claude", judges=[judge_says(0.9)])), host=lambda: host)
    return doc, out, host


def ops(out: dict[str, Any]) -> set[str]:
    return {r["op"] for r in out["results"]}


def files(out: dict[str, Any], host: MemoryCodeHost) -> bool:
    return "filed" in ops(out) and bool(host.issues)


def files_nothing(out: dict[str, Any], host: MemoryCodeHost) -> bool:
    return not host.issues and not host.comments and not (ops(out) & {"filed", "commented"})


def test_lfs_ac2_a_workflow_declaring_nothing_files_in_dev_and_in_stable(
        repo: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    for mode in ("dev", "stable"):
        spec = dataclasses.replace(two_step(), improvement_mode=mode)
        doc, out, host = drained(thread(repo, monkeypatch, f"M-{mode}", spec))
        assert doc["filing"] == "file" and doc["filing_source"] == "default", mode
        assert doc["dry_run"] is False and doc["autonomy"] == "file", mode
        assert files(out, host), mode


def test_lfs_ac2_the_ticket_holds_the_same_filing_in_both_modes(tmp_path: Path) -> None:
    pkg = tmp_path / "pkg"
    pkg.mkdir()
    (pkg / "tempergraph.json").write_text(json.dumps({"improvement": {"autonomy": "record"}}))
    n = 0
    for dry, declared, hold, lift in itertools.product((False, True), (False, True), (None, "record"), (False, True)):
        seen = []
        for mode in ("dev", "stable"):
            n += 1
            spec = dataclasses.replace(two_step(), improvement_mode=mode, package_root=pkg if declared else None)
            p = child.hand_off(tmp_path, spec, f"T-{n}", f"demo/T-{n}", SUMMARY, dry_run=dry, judge_executor="claude",
                               home=tmp_path / "home", loop_autonomy=hold, dry_source="settings", lift=lift)
            assert p is not None
            t = json.loads(p.read_text())
            seen.append((t["filing"], t["filing_source"], t["autonomy"], t["dry_run"]))
        assert seen[0] == seen[1], (dry, declared, hold, lift)
        held = hold == "record" or (declared and not lift)
        want = "held" if held else "dry_run" if dry else "file"
        assert seen[0][0] == want, (dry, declared, hold, lift)
        if held:
            assert seen[0][1] == ("machine_hold" if hold == "record" else "declared_record")
        else:
            assert seen[0][1] == "settings"


def test_lfs_ac7_a_declared_dry_run_files_nothing_at_every_exit(repo: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    doc, out, host = drained(thread(repo, monkeypatch, "D-1", two_step(loop_dry_run=True)))
    assert doc["dry_run"] is True and doc["filing"] == "dry_run" and doc["filing_source"] == "workflow"
    assert "would_file" in ops(out) and files_nothing(out, host)
    assert all(r["title"] for r in out["results"] if r["op"] == "would_file")
    settings_file(loop_dry_run=True)
    doc, out, host = drained(thread(repo, monkeypatch, "D-2"))
    assert doc["filing"] == "dry_run" and doc["filing_source"] == "settings"
    assert "would_file" in ops(out) and files_nothing(out, host)


def test_lfs_ac7_rop_ac8_the_argument_overrides_the_declaration_in_both_directions(
        repo: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    doc, out, host = drained(thread(repo, monkeypatch, "O-1", two_step(loop_dry_run=True), ("--no-dry-run",)))
    assert doc["filing"] == "file" and doc["filing_source"] == "argument" and files(out, host)
    doc, out, host = drained(thread(repo, monkeypatch, "O-2", None, ("--dry-run",)))
    assert doc["filing"] == "dry_run" and doc["filing_source"] == "argument"
    assert "would_file" in ops(out) and files_nothing(out, host)


def test_lfs_ac3_rop_ac12_the_value_given_last_wins_across_a_resume(
        repo: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    doc, out, host = drained(thread(repo, monkeypatch, "W-1", None, ("--dry-run",), ("--no-dry-run",)))
    assert doc["dry_run"] is False and files(out, host)
    doc, out, host = drained(thread(repo, monkeypatch, "W-2", None, ("--no-dry-run",), ("--dry-run",)))
    assert doc["dry_run"] is True and files_nothing(out, host)
    doc, out, host = drained(thread(repo, monkeypatch, "W-3", None, ("--dry-run",), ()))  # neither: kept
    assert doc["dry_run"] is True and files_nothing(out, host)


def exit_of(repo: Path, task: str, monkeypatch: pytest.MonkeyPatch, log: list[dict[str, Any]],
            options: RunOptions | None, settings: RunSettings | None = None) -> dict[str, Any]:
    """The ticket `hand_to_loop` writes at an exit of a thread whose `run.jsonl` holds `log`."""
    monkeypatch.setenv("TEMPERGRAPH_LOOP", "detached")
    monkeypatch.setattr(detach, "start", lambda *a, **k: True)
    folder = repo / ".tempergraph" / "runs" / "demo" / task
    folder.mkdir(parents=True, exist_ok=True)
    (folder / "run.jsonl").write_text("".join(json.dumps(r) + "\n" for r in log))
    for old in tickets():
        old.unlink()
    runner.hand_to_loop(repo / ".tempergraph", two_step(), task, f"demo/{task}", SUMMARY, settings, registry(standin("claude")),
                        {}, options=options)
    (path,) = tickets()
    return json.loads(path.read_text())


def test_lfs_ac3_a_thread_with_a_dry_run_start_and_no_value_runs_dry_until_a_call_gives_one(
        repo: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    legacy = {"kind": "run_started", "dry_run": True}
    t = exit_of(repo, "G-1", monkeypatch, [legacy], RunOptions())
    assert t["dry_run"] is True and t["filing"] == "dry_run" and t["filing_source"] == "argument"
    row = {"kind": "settings_resolved", "rows": [{"key": KEY, "value": False, "layer": "flag"}]}
    flag = RunOptions(settings={"flag": {KEY: {"value": False, "ref": "--no-dry-run"}}})
    t = exit_of(repo, "G-1", monkeypatch, [legacy, row], flag)
    assert t["dry_run"] is False and t["filing"] == "file" and t["filing_source"] == "argument"
    t = exit_of(repo, "G-1", monkeypatch, [legacy, row], RunOptions())  # a later `--unset`: no row, the log has one
    assert t["dry_run"] is False and t["filing"] == "file" and t["filing_source"] == "default"


def test_lfs_ac3_a_thread_the_engine_started_dry_stays_dry(repo: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    t = exit_of(repo, "G-2", monkeypatch, [{"kind": "run_started"}], RunOptions(), RunSettings(dry_run=True))
    assert t["dry_run"] is True and t["filing_source"] == "argument"


def lifted_thread(repo: Path, monkeypatch: pytest.MonkeyPatch, task: str, *, run_argv: tuple[str, ...] = (),
                  resume_argv: tuple[str, ...] = (), spec: Any = None) -> tuple[dict[str, Any], dict[str, Any],
                                                                              MemoryCodeHost]:
    return drained(thread(repo, monkeypatch, task, spec, run_argv, resume_argv))


def test_lfs_ac4_prp_ac16_no_dry_run_lifts_a_declared_record_for_one_thread(
        repo: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    before = declare_record(repo, monkeypatch)
    for task, run_argv, resume_argv in (("L-1", ("--no-dry-run",), ()), ("L-2", (), ("--no-dry-run",))):
        doc, out, host = lifted_thread(repo, monkeypatch, task, run_argv=run_argv, resume_argv=resume_argv)
        assert doc["autonomy"] == "file" and doc["filing"] == "file" and doc["filing_source"] == "argument", task
        kinds = [json.loads(ln)["kind"] for ln in child.loop_log(repo / ".tempergraph", "demo", task).read_text().splitlines()]
        assert files(out, host) and not [k for k in kinds if "proposal" in k or "trial" in k], (task, kinds)
    doc, out, host = lifted_thread(repo, monkeypatch, "L-3")  # no argument
    assert doc["autonomy"] == "record" and doc["filing"] == "held" and doc["filing_source"] == "declared_record"
    assert files_nothing(out, host) and {r["reason"] for r in out["results"]} == {"autonomy_record"}
    # a `false` from the declaration, a settings file or a profile is no argument
    doc, out, host = lifted_thread(repo, monkeypatch, "L-4", spec=two_step(loop_dry_run=False))
    assert doc["autonomy"] == "record" and files_nothing(out, host)
    settings_file(loop_dry_run=False)
    doc, out, host = lifted_thread(repo, monkeypatch, "L-5")
    assert doc["autonomy"] == "record" and files_nothing(out, host)
    doc, out, host = lifted_thread(repo, monkeypatch, "L-6", run_argv=("--set", f"{KEY}=false"))
    assert doc["autonomy"] == "file" and files(out, host)  # the flag layer is the argument, however it was spelled
    assert (repo / "pkg" / "tempergraph.json").read_bytes() == before


def test_lfs_ac4_the_hold_wins_over_the_argument(repo: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    declare_record(repo, monkeypatch)
    settings_file(loop_autonomy="record")
    doc, out, host = lifted_thread(repo, monkeypatch, "H-1", run_argv=("--no-dry-run",))
    assert doc["autonomy"] == "record" and doc["filing"] == "held" and doc["filing_source"] == "machine_hold"
    assert files_nothing(out, host) and {r["reason"] for r in out["results"]} == {"autonomy_record"}
    settings_file()
    monkeypatch.setenv("TEMPERGRAPH_AUTONOMY", "record")
    doc, out, host = lifted_thread(repo, monkeypatch, "H-2", run_argv=("--no-dry-run",))
    assert doc["autonomy"] == "record" and doc["filing_source"] == "machine_hold"
    assert files_nothing(out, host) and {r["reason"] for r in out["results"]} == {"autonomy_record"}


def test_lfs_ac4_the_level_function_lifts_only_a_declared_record(tmp_path: Path) -> None:
    pkg = tmp_path / "pkg"
    pkg.mkdir()
    (pkg / "tempergraph.json").write_text(json.dumps({"improvement": {"autonomy": "record"}}))
    declared = dataclasses.replace(two_step(), package_root=pkg)
    plain = two_step()
    assert prp.filing_level(declared, None, None, True) == ("file", "declared")
    assert prp.filing_level(declared, None, None, False) == ("record", "declared_record")
    assert prp.filing_level(declared, "record", None, True) == ("record", "machine_hold")
    assert prp.filing_level(declared, None, "record", True) == ("record", "machine_hold")
    assert prp.filing_level(declared, "propose", None, True) == ("file", "declared")  # never above the hold's level
    assert prp.filing_level(plain, None, None, True) == ("file", "none")
    assert prp.filing_level(plain, "record", None, False) == ("record", "machine_hold")
    assert prp.filing_level(plain, None, "trial", True)[0] == "file"  # never raised above `file`
