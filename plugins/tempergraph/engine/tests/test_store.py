"""T7.3: the local store's verbs and retention (LOS-B14, LOS-B15, LOS-B16) and the session's `meta.json` (LOS-B7, LOS-B8, LOS-B9)."""

from __future__ import annotations

import json
import os
import tarfile
import time
from pathlib import Path

from tempergraph.executors.standins import standin
from tempergraph.store import logs
from tempergraph.store.layout import run_dir, state_root_path

from .conftest import hash_tree
from .test_cli import cli
from .test_run import DRAFT, REVIEW, go, judge

CANARY = "sk-ant-CANARY0123456789abcdef"


def finished_run(repo: Path, task: str = "T-1") -> Path:
    go(repo, standin("claude", steps=[DRAFT, REVIEW], judges=[judge(), judge()]), task=task)
    return run_dir(state_root_path(repo), "demo", task)


def age(folder: Path, days: float) -> None:
    """Moves a thread's end `days` into the past (exit.json's mtime is the end time)."""
    t = time.time() - days * 86_400
    os.utime(folder / "exit.json", (t, t))


def plant_logs(folder: Path) -> None:
    s = folder / "sessions" / "draft.1.step"
    (s / "raw.jsonl").write_text('{"type":"system"}\n')
    (s / "stderr.log").write_text(f"warning {CANARY}\n")
    (folder / "checks" / "review" / "1").mkdir(parents=True)
    (folder / "checks" / "review" / "1" / "1.out").write_text("3 passed\n")
    (folder / "hooks").mkdir()
    (folder / "hooks" / "run_started-1.log").write_text("ok\n")


def test_session_meta_is_written_and_closed(repo: Path) -> None:  # LOS-B7, LOS-B8, LOS-B9
    folder = finished_run(repo)
    meta = json.loads((folder / "sessions" / "draft.1.step" / "meta.json").read_text())
    assert meta["executor"] == "claude" and meta["session_key"] == "draft.1.step"
    assert meta["session_id"] == "s-draft" and meta["started_at"] and meta["ended_at"]
    assert meta["transcript"]["engine"].endswith("sessions/draft.1.step/raw.jsonl")


def test_logs_lists_and_prints_without_writing(repo: Path) -> None:  # LOS-AC2
    folder = finished_run(repo)
    plant_logs(folder)
    root = state_root_path(repo)
    before = hash_tree(root)
    code, doc, _ = cli(repo, None, "logs", "demo/T-1", "--json")
    assert code == 0
    kinds = {f["path"]: f["kind"] for f in doc["files"]}
    assert kinds["run.jsonl"] == "run" and kinds["sessions/draft.1.step/raw.jsonl"] == "raw"
    assert kinds["checks/review/1/1.out"] == "check"
    code, text, _ = cli(repo, None, "logs", "demo/T-1", "--kind", "run")
    assert code == 0 and '"run_started"' in str(text)
    code, text, _ = cli(repo, None, "logs", "demo/T-1", "--kind", "check", "--session", "review.1")
    assert code == 0 and text.strip() == "3 passed"
    code, _, err = cli(repo, None, "logs", "demo/T-1", "--kind", "raw")
    assert code == 2 and "--session" in err
    code, _, err = cli(repo, None, "logs", "demo/T-1", "--kind", "stderr", "--session", "nope.1.step")
    assert code == 2 and "pruned" in err
    for argv in (("store", "usage", "--json"), ("store", "prune", "--dry-run", "--older-than", "0")):
        assert cli(repo, None, *argv)[0] == 0
    assert hash_tree(root) == before


def test_usage_counts_kinds_and_retention(repo: Path) -> None:
    folder = finished_run(repo)
    plant_logs(folder)
    code, doc, _ = cli(repo, None, "store", "usage", "--json")
    assert code == 0
    [t] = doc["threads"]
    assert t["thread_id"] == "demo/T-1" and t["past_retention"] is False
    assert t["by_kind"]["raw"] > 0 and doc["total_bytes"] >= t["bytes"]
    age(folder, 31)
    assert cli(repo, None, "store", "usage", "--json")[1]["threads"][0]["past_retention"] is True


def test_prune_keeps_the_record(repo: Path) -> None:  # LOS-B5
    folder = finished_run(repo)
    plant_logs(folder)
    age(folder, 40)
    code, doc, _ = cli(repo, None, "store", "prune", "--json")
    assert code == 0 and doc["dry_run"] is False
    s = folder / "sessions" / "draft.1.step"
    assert not (s / "raw.jsonl").exists() and not (s / "stderr.log").exists() and not (s / "activity.jsonl").exists()
    assert not (folder / "checks" / "review" / "1" / "1.out").exists() and not (folder / "hooks" / "run_started-1.log").exists()
    assert (folder / "run.jsonl").exists() and (s / "meta.json").exists() and (folder / "exit.json").exists()
    code, d, _ = cli(repo, None, "status", "demo/T-1", "--detail")
    assert code == 0 and d["run"]["thread_id"] == "demo/T-1"


def test_prune_spares_young_paused_failed_and_running(repo: Path) -> None:
    young = finished_run(repo, "T-1")
    plant_logs(young)
    paused = finished_run(repo, "T-2")
    (paused / "exit.json").write_text(json.dumps({"exit_code": 3, "reason": "pause"}))
    failed = finished_run(repo, "T-3")
    (failed / "exit.json").write_text(json.dumps({"exit_code": 5, "reason": "budget"}))
    for f in (paused, failed):
        plant_logs(f)
        age(f, 60)
    root = state_root_path(repo)
    plan = logs.plan_prune(root, older_than_days=30)
    assert plan.remove == [] and plan.kept_failed == ["demo/T-3"]
    plan = logs.plan_prune(root, older_than_days=30, keep_failed=False)
    assert plan.remove and all(str(p).startswith(str(failed)) for p in plan.remove)


def test_prune_refuses_a_running_thread(repo: Path) -> None:  # LOS-B12, LOS-B18, LOS-B15
    from tempergraph.durability.lock import RunLock
    from tempergraph.store.layout import lock_path

    folder = finished_run(repo)
    plant_logs(folder)
    age(folder, 40)
    root = state_root_path(repo)
    with RunLock(lock_path(root, "demo", "T-1")):
        plan = logs.plan_prune(root)
    assert plan.remove == [] and plan.refused == [{"thread_id": "demo/T-1", "reason": "running"}]


def test_export_is_scrubbed(repo: Path, tmp_path: Path) -> None:  # LOS-AC3
    folder = finished_run(repo)
    plant_logs(folder)
    target = tmp_path / "out" / "run.tar.gz"
    code, doc, _ = cli(repo, None, "store", "export", "demo/T-1", str(target))
    assert code == 0 and doc["files"] > 3
    with tarfile.open(target) as tar:
        names = tar.getnames()
        assert "demo/T-1/run.jsonl" in names
        for m in tar.getmembers():
            data = tar.extractfile(m).read().decode()  # type: ignore[union-attr]
            assert CANARY not in data
    inside = state_root_path(repo) / "x.tar.gz"
    assert cli(repo, None, "store", "export", "demo/T-1", str(inside))[0] == 2
    assert cli(repo, None, "store", "export", "demo/T-1", str(tmp_path / "x.zip"))[0] == 2


def test_engine_log_filtered_by_thread(repo: Path) -> None:
    finished_run(repo)
    eng = state_root_path(repo) / "engine"
    (eng / "2026-11-20-1.jsonl").write_text(json.dumps({"thread_id": "demo/T-1", "msg": "mine"}) + "\n"
                                             + json.dumps({"thread_id": "demo/T-9", "msg": "other"}) + "\nbad\n")
    code, text, _ = cli(repo, None, "logs", "demo/T-1", "--kind", "engine")
    assert code == 0 and text == {"thread_id": "demo/T-1", "msg": "mine"}  # one line, parsed by the helper
