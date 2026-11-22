"""IMD-B5 join keys on the ledger rows: workflow version, machine id and repository digest."""

from __future__ import annotations

import json
import subprocess
from pathlib import Path

import pytest

from tempergraph.identity import normalize_remote, repo_id

from .test_cli import cli, happy


@pytest.mark.parametrize("url", ["git@github.com:Org/Repo.git", "https://github.com/org/repo",
                                 "https://user:tok@github.com/org/repo.git/", "ssh://git@github.com/org/repo.git"])
def test_remote_forms_normalize_alike(url: str) -> None:
    assert normalize_remote(url) == "github.com/org/repo"


def test_ledger_rows_carry_the_join_keys(repo: Path) -> None:
    assert repo_id(repo) is None  # no origin
    subprocess.run(["git", "remote", "add", "origin", "git@example.test:team/notes.git"], cwd=repo, check=True)
    code, _, err = cli(repo, happy(), "run", "demo", "notes", "--task-id", "J-1")
    assert code == 0, err
    rows = [json.loads(x) for x in (repo / ".tempergraph" / "ledger.jsonl").read_text().splitlines()]
    seg = [r for r in rows if r["kind"] == "run_segment"][-1]
    assert seg["workflow_version"] and len(seg["repo"]) == 16 and seg["machine"]
    assert "example.test" not in json.dumps(seg)
