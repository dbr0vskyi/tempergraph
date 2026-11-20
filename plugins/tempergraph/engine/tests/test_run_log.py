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
