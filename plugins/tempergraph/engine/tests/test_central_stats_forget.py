"""`stats forget`: gone state roots leave the machine index and this month's stats (CST-B17 to CST-B21)."""

from __future__ import annotations

import json
import os
import threading
import time
from collections.abc import Callable
from pathlib import Path
from typing import Any

import pytest

from tempergraph.observe import rows
from tempergraph.store.layout import home_path

from .conftest import hash_tree
from .test_cli import cli

OLD_MONTH = "2020-01"


def _lines(path: Path) -> list[dict[str, Any]]:
    return [json.loads(ln) for ln in path.read_text(encoding="utf-8").splitlines() if ln.strip()]


def _write(path: Path, docs: list[dict[str, Any]]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text("".join(json.dumps(d) + "\n" for d in docs), encoding="utf-8")


def seed(tmp_path: Path, *, with_gone: bool = True, outbox: tuple[str, ...] = ()) -> dict[str, Any]:
    """A home folder: an index with a root that has a folder and (optionally) one that has not, this month's run
    and session rows of both (three rows of the gone root), an earlier month's file and an outbox."""
    home = home_path()
    month = rows.month_now()
    live = tmp_path / "live" / ".tempergraph"
    live.mkdir(parents=True)
    gone = tmp_path / "gone" / ".tempergraph"  # never created
    entries = [{"path": str(live), "repository": "live", "first_seen": "2026-01-01T00:00:00Z"}]
    if with_gone:
        entries.append({"path": str(gone), "repository": "gone", "first_seen": "2026-01-01T00:00:00Z"})
    (home / "stats" / "sessions").mkdir(parents=True)
    (home / "index.json").write_text(json.dumps({"schema_version": 1, "roots": entries}, indent=2) + "\n",
                                     encoding="utf-8")

    def row(rid: str, root: Path, kind: str = "run") -> dict[str, Any]:
        return {"row_id": rid, "kind": kind, "schema_version": 1, "state_root": str(root)}

    _write(rows.stats_path(home, month), [row("run-live", live), row("run-gone-1", gone), row("run-gone-2", gone),
                                          row("run-gone-kept", gone)])
    _write(home / "stats" / "sessions" / f"{month}.jsonl",
           [row("ses-live", live, "session"), row("ses-gone-1", gone, "session"),
            row("ses-gone-kept", gone, "session")])
    _write(rows.stats_path(home, OLD_MONTH), [row("old-gone", gone)])
    _write(home / "stats" / "sessions" / f"{OLD_MONTH}.jsonl", [row("old-ses-gone", gone, "session")])
    if outbox:
        _write(home / "outbox" / "team.jsonl", [{"row_id": rid, "kind": "run", "month": month} for rid in outbox])
    return {"home": home, "month": month, "live": live, "gone": gone}


def _ids(path: Path) -> set[str]:
    return {r["row_id"] for r in _lines(path)}


def test_cst_ac6_the_index_lists_only_the_root_with_a_folder(repo: Path, tmp_path: Path) -> None:  # CST-AC6
    s = seed(tmp_path)
    code, doc, err = cli(repo, None, "stats", "forget")
    assert code == 0, err
    assert doc["check"] is False and doc["schema_version"] == 1
    index = json.loads((s["home"] / "index.json").read_text(encoding="utf-8"))
    assert index["schema_version"] == 1
    assert [r["path"] for r in index["roots"]] == [str(s["live"])]
    assert index["roots"][0]["repository"] == "live"  # the kept entry is as it was


def test_cst_ac6_an_index_with_no_gone_path_is_as_it_was(repo: Path, tmp_path: Path) -> None:  # CST-AC6
    s = seed(tmp_path, with_gone=False)
    before = hash_tree(s["home"])
    code, doc, err = cli(repo, None, "stats", "forget")
    assert code == 0, err
    assert doc["roots"] == []
    assert hash_tree(s["home"]) == before


def test_cst_ac7_this_months_rows_of_the_gone_root_leave_but_an_outbox_row_stays(repo: Path, tmp_path: Path) -> None:
    s = seed(tmp_path, outbox=("run-gone-kept", "ses-gone-kept"))  # CST-AC7
    code, _doc, err = cli(repo, None, "stats", "forget")
    assert code == 0, err
    assert _ids(rows.stats_path(s["home"], s["month"])) == {"run-live", "run-gone-kept"}
    assert _ids(s["home"] / "stats" / "sessions" / f"{s['month']}.jsonl") == {"ses-live", "ses-gone-kept"}


def test_cst_ac7_a_row_of_a_root_with_a_folder_is_never_removed(repo: Path, tmp_path: Path) -> None:  # CST-AC7
    s = seed(tmp_path)
    code, _doc, err = cli(repo, None, "stats", "forget")
    assert code == 0, err
    assert _ids(rows.stats_path(s["home"], s["month"])) == {"run-live"}
    assert _ids(s["home"] / "stats" / "sessions" / f"{s['month']}.jsonl") == {"ses-live"}


def test_cst_ac8_an_earlier_month_is_as_it_was(repo: Path, tmp_path: Path) -> None:  # CST-AC8
    s = seed(tmp_path)
    old = [rows.stats_path(s["home"], OLD_MONTH), s["home"] / "stats" / "sessions" / f"{OLD_MONTH}.jsonl"]
    before = [p.read_bytes() for p in old]
    code, _doc, err = cli(repo, None, "stats", "forget")
    assert code == 0, err
    assert [p.read_bytes() for p in old] == before


def test_cst_ac9_check_prints_the_root_with_its_rows_and_changes_nothing(repo: Path, tmp_path: Path) -> None:
    s = seed(tmp_path)  # CST-AC9
    before = hash_tree(s["home"])
    code, checked, err = cli(repo, None, "stats", "forget", "--check")
    assert code == 0, err
    assert checked["check"] is True and checked["month"] == s["month"]
    assert checked["roots"] == [{"state_root": str(s["gone"]), "rows": 5}]  # three run rows and two session rows
    assert hash_tree(s["home"]) == before
    code, done, err = cli(repo, None, "stats", "forget")
    assert code == 0, err
    assert done["check"] is False
    assert done["roots"] == checked["roots"]
    assert hash_tree(s["home"]) != before


def test_cst_ac9_three_rows_of_a_gone_root_print_as_three(repo: Path, tmp_path: Path) -> None:  # CST-AC9
    s = seed(tmp_path, outbox=("run-gone-1", "run-gone-kept"))  # the outbox keeps two of the five rows
    code, doc, err = cli(repo, None, "stats", "forget", "--check")
    assert code == 0, err
    assert doc["roots"] == [{"state_root": str(s["gone"]), "rows": 3}]


def test_cst_ac10_an_index_in_use_is_refused_and_a_check_still_prints(repo: Path, tmp_path: Path) -> None:
    s = seed(tmp_path)  # CST-AC10
    (s["home"] / "index.lock").write_text("", encoding="utf-8")  # held by another process, and fresh
    before = hash_tree(s["home"])
    started = time.monotonic()
    code, doc, err = cli(repo, None, "stats", "forget")
    waited = time.monotonic() - started
    assert code == 2 and "in use" in err
    assert not doc
    assert 1.5 <= waited < 15
    assert hash_tree(s["home"]) == before
    code, checked, err = cli(repo, None, "stats", "forget", "--check")
    assert code == 0, err
    assert checked["roots"] == [{"state_root": str(s["gone"]), "rows": 5}]
    assert hash_tree(s["home"]) == before


def _patch_replace(monkeypatch: pytest.MonkeyPatch, home: Path,
                   act: Callable[[Path, str], None]) -> None:
    """`os.replace` calls `act(target, source)` first when the target is a stats file (a `.jsonl` under the home
    folder's `stats` folder) and is the real function otherwise and afterwards."""
    real = os.replace

    def replace(src: Any, dst: Any, *args: Any, **kwargs: Any) -> None:
        target = Path(dst)
        if target.suffix == ".jsonl" and (home / "stats") in target.parents:
            act(target, str(src))
        real(src, dst, *args, **kwargs)

    monkeypatch.setattr(os, "replace", replace)


def test_cst_ac11_a_stats_file_that_cannot_be_replaced_keeps_the_index_entry(
        repo: Path, tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:  # CST-AC11, AC 3
    s = seed(tmp_path)
    index = (s["home"] / "index.json").read_bytes()
    stats = {p: p.read_bytes() for p in (rows.stats_path(s["home"], s["month"]),
                                         s["home"] / "stats" / "sessions" / f"{s['month']}.jsonl")}

    def refuse(_target: Path, _src: str) -> None:
        raise OSError("cannot replace")

    _patch_replace(monkeypatch, s["home"], refuse)
    code, _doc, _err = cli(repo, None, "stats", "forget")
    assert code == 1
    assert (s["home"] / "index.json").read_bytes() == index
    assert {p: p.read_bytes() for p in stats} == stats


def test_cst_ac12_the_next_run_removes_the_root_and_its_rows(
        repo: Path, tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:  # CST-AC12, AC 3
    s = seed(tmp_path)
    failing = [True]

    def refuse(_target: Path, _src: str) -> None:
        if failing[0]:
            raise OSError("cannot replace")

    _patch_replace(monkeypatch, s["home"], refuse)
    code, _doc, _err = cli(repo, None, "stats", "forget")
    assert code == 1
    failing[0] = False
    code, _doc, err = cli(repo, None, "stats", "forget")
    assert code == 0, err
    index = json.loads((s["home"] / "index.json").read_text(encoding="utf-8"))
    assert [r["path"] for r in index["roots"]] == [str(s["live"])]
    assert _ids(rows.stats_path(s["home"], s["month"])) == {"run-live"}
    assert _ids(s["home"] / "stats" / "sessions" / f"{s['month']}.jsonl") == {"ses-live"}


def test_cst_ac13_a_row_appended_while_the_verb_runs_is_kept(
        repo: Path, tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:  # CST-AC13, AC 3
    s = seed(tmp_path)
    appended = {"row_id": "run-appended", "kind": "run", "schema_version": 1, "state_root": str(s["live"])}
    threads: list[threading.Thread] = []

    def append_meanwhile(_target: Path, _src: str) -> None:
        if threads:
            return
        thread = threading.Thread(
            target=lambda: rows.append_stats_row(rows.stats_path(s["home"], s["month"]), appended))
        threads.append(thread)
        thread.start()
        time.sleep(0.3)  # the writer is in flight while the verb holds the file

    _patch_replace(monkeypatch, s["home"], append_meanwhile)
    code, _doc, err = cli(repo, None, "stats", "forget")
    assert code == 0, err
    threads[0].join(timeout=10)
    assert _ids(rows.stats_path(s["home"], s["month"])) == {"run-live", "run-appended"}  # none of the gone root's


def test_cst_ac14_the_verb_takes_no_month(repo: Path, tmp_path: Path) -> None:  # CST-AC14, AC 3
    s = seed(tmp_path)
    before = hash_tree(s["home"])
    code, doc, err = cli(repo, None, "stats", "forget", "--month", s["month"])
    assert code == 2 and "takes no month" in err
    assert not doc
    assert hash_tree(s["home"]) == before
    code, doc, err = cli(repo, None, "stats", "forget", "--check", "--month", OLD_MONTH)
    assert code == 2 and "takes no month" in err
    assert not doc  # no root printed
    assert hash_tree(s["home"]) == before
    code, doc, err = cli(repo, None, "stats", "forget")
    assert code == 0, err
    assert doc["roots"] == [{"state_root": str(s["gone"]), "rows": 5}]
    assert _ids(rows.stats_path(s["home"], s["month"])) == {"run-live"}


def test_cst_ac6_a_home_with_no_stats_folder_cleans_the_index(repo: Path, tmp_path: Path) -> None:  # CST-AC6
    import shutil

    s = seed(tmp_path)
    shutil.rmtree(s["home"] / "stats")
    code, doc, err = cli(repo, None, "stats", "forget")
    assert code == 0, err
    index = json.loads((s["home"] / "index.json").read_text(encoding="utf-8"))
    assert [r["path"] for r in index["roots"]] == [str(s["live"])]
    assert not (s["home"] / "stats").exists()  # nothing to rewrite, and no folder made for a lock
