"""OBS-B3: logging fails safely."""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any

import pytest

from tempergraph.constants import ExitCode
from tempergraph.executors.standins import standin
from tempergraph.run import log as logmod

from .test_run import DRAFT, REVIEW, go, judge, records


def test_a_full_disk_on_the_ledger_keeps_the_exit_code(repo: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    real = logmod.append_jsonl

    def full(path: Path, row: Any) -> None:
        if path.name == "ledger.jsonl":
            raise OSError(28, "No space left on device")
        real(path, row)

    monkeypatch.setattr(logmod, "append_jsonl", full)
    out = go(repo, standin("claude", steps=[DRAFT, REVIEW], judges=[judge(), judge()]))
    assert out.exit_code is ExitCode.FINISHED
    errs = [r for r in records(repo) if r["kind"] == "engine_error"]
    assert [e["scope"] for e in errs] == ["ledger"]
    assert json.loads((repo / ".tempergraph" / "runs" / "demo" / "T-1" / "exit.json").read_text())["exit_code"] == 0


def test_budget_records_name_each_charged_counter(repo: Path) -> None:  # EVT-B10 to EVT-B16 `budget`
    from .test_run import verdict_block

    ex = standin("claude", steps=[DRAFT, DRAFT, REVIEW, DRAFT, REVIEW],
                 judges=[judge(verdict_block("UNMET")), judge(), judge(verdict_block("UNMET", defect_in="notes")),
                         judge(), judge()])
    go(repo, ex)
    got = [(r["unit"], r["counter"], r["used"], r["limit"]) for r in records(repo) if r["kind"] == "budget"]
    assert got == [("draft", "retries", 1, 2), ("review", "loops:draft", 1, 1)]


def test_operator_capture_level_and_observers(repo: Path) -> None:  # LOS-B17, EVT-B21, EVT-B6, EVT-B22, EVT-B23, EVT-B24
    import os

    from tempergraph.store.layout import run_dir, state_root_path

    cfg = Path(os.environ["TEMPERGRAPH_HOME"]) / "config"
    cfg.mkdir(parents=True, exist_ok=True)
    (cfg / "settings.json").write_text(json.dumps({"schema_version": 1, "observe": {
        "raw": "off", "tool_inputs": "off", "observers": ["not-installed"]}}))

    def step(req: Any) -> Any:
        (req.session_dir / "raw.jsonl").write_text('{"type": "result"}\n')  # as the launcher would
        return DRAFT

    go(repo, standin("claude", steps=[step, REVIEW], judges=[judge(), judge()]))
    started = next(r for r in records(repo) if r["kind"] == "run_started")
    assert started["capture_lowered"] == ["raw", "tool_inputs"]
    assert started["observers"] == ["not-installed"] and started["observers_missing"] == ["not-installed"]
    sessions = run_dir(state_root_path(repo), "demo", "T-1") / "sessions"
    assert list(sessions.glob("*/meta.json")) and not list(sessions.glob("*/raw.jsonl"))
