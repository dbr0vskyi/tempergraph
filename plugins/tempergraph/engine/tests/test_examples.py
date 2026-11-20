"""The example workflows of the repository (first-release plan T11.1): each loads, passes its generated tests
and covers its outcome, and the three-step document workflow runs every path it declares on stand-ins."""

from __future__ import annotations

import json
import subprocess
import sys
from pathlib import Path
from typing import Any

import pytest

from tempergraph.constants import ExitCode
from tempergraph.contracts import SessionResult
from tempergraph.executors.standins import answer, standin
from tempergraph.package import selftest
from tempergraph.package.loader import load_package
from tempergraph.run.outcome_trust import coverage
from tempergraph.run.runner import RunSettings, resume, start
from tempergraph.store.layout import run_dir, state_root_path

from .conftest import REPO_ROOT
from .test_run import registry, verdict_block

EXAMPLES = ("release-notes", "doc-refresh")
NO_SLEEP = RunSettings(sleep=lambda s: None)


def plugin(name: str) -> Path:
    return REPO_ROOT / "plugins" / f"{name}-tgraph"  # the plugin folder carries the suffix (ADR-0120)


@pytest.mark.parametrize("name", EXAMPLES)
def test_example_loads_and_passes_its_generated_tests(name: str, tmp_path: Path) -> None:
    spec = load_package(plugin(name)).spec
    assert spec.name == name and spec.outcome is not None
    assert all(c.covered for c in coverage(spec.outcome, spec)), "every final criterion is covered (SCF rung 5)"
    for test in selftest.NAMES:
        work = tmp_path / test
        work.mkdir()
        assert selftest.run(test, plugin(name), work) == [], test


@pytest.mark.parametrize("name", EXAMPLES)
def test_example_is_in_the_marketplace(name: str) -> None:
    market = json.loads((REPO_ROOT / ".claude-plugin" / "marketplace.json").read_text())
    entry = next(p for p in market["plugins"] if p["name"] == f"{name}-tgraph")  # ADR-0120
    manifest = json.loads((plugin(name) / ".claude-plugin" / "plugin.json").read_text())
    assert entry["source"] == f"./plugins/{name}-tgraph" and manifest["name"] == f"{name}-tgraph"
    assert "tempergraph" in manifest["dependencies"]


def test_release_notes_own_tests_pass() -> None:
    root = plugin("release-notes")
    got = subprocess.run([sys.executable, "-m", "pytest", "-q", "-p", "no:cacheprovider", "-o", "addopts=",
                          str(root / "tests")], cwd=root, capture_output=True, text=True,
                         env={**__import__("os").environ, "PYTHONPATH": str(root / "workflow")})
    assert got.returncode == 0, got.stdout[-2000:]


# -- doc-refresh on stand-ins -------------------------------------------------------------------------------------

GUIDE = "# Guide\n\n## Install\n\nRun `pip install demo` on Python 3.9.\n\n## Use\n\nRun `demo --help`.\n"
FRESH = GUIDE.replace("Python 3.9", "Python 3.12 or newer")
REQUEST = "docs/guide.md: the install section, for Python 3.12"


def doc_repo(repo: Path) -> Path:
    (repo / "docs").mkdir()
    (repo / "docs" / "guide.md").write_text(GUIDE)
    subprocess.run(["git", "add", "docs"], cwd=repo, check=True, capture_output=True)
    subprocess.run(["git", "commit", "-q", "-m", "guide"], cwd=repo, check=True, capture_output=True)
    return repo


def draft(size: str, text: str = FRESH) -> Any:
    def reply(req: Any) -> SessionResult:
        (Path(req.workdir) / "docs" / "guide.md").write_text(text)
        return answer(f"Rewrote the install section.\nARTIFACT doc: docs/guide.md\nARTIFACT size: {size}",
                      session_id="s-draft")
    return reply


REVIEW = answer("Install matches pyproject.\nARTIFACT verdict: approve", session_id="s-review")


def met(n: int, sid: str = "j") -> SessionResult:
    return answer(verdict_block(*["MET"] * n), tools=("Read",), session_id=sid)


def entered(repo: Path, task: str) -> list[tuple[str, str]]:
    p = run_dir(state_root_path(repo), "doc-refresh", task) / "run.jsonl"
    return [(r["unit"], r["entered_from"]) for r in map(json.loads, p.read_text().splitlines())
            if r["kind"] == "unit_entered"]


def records(repo: Path, task: str, kind: str) -> list[dict[str, Any]]:
    p = run_dir(state_root_path(repo), "doc-refresh", task) / "run.jsonl"
    return [r for r in map(json.loads, p.read_text().splitlines()) if r["kind"] == kind]


def test_doc_refresh_major_trips_back_then_waits_for_approval(repo: Path) -> None:
    spec = load_package(plugin("doc-refresh")).spec
    doc_repo(repo)
    redo = answer(verdict_block("UNMET", "MET", defect_in="doc"), tools=("Read",), session_id="j-review")
    ex = standin("claude", steps=[draft("major"), REVIEW, draft("major"), REVIEW],
                 judges=[met(2), redo, met(2), met(2), met(1, "j-outcome")])
    out = start(spec, "D-1", {"request": REQUEST}, repo, registry(ex), NO_SLEEP)
    assert out.exit_code is ExitCode.PAUSED and out.payload["kind"] == "approval", out.message
    outline = records(repo, "D-1", "script")
    assert outline and outline[0]["unit"] == "outline" and not outline[0]["environmental"]  # a unit with no session
    assert entered(repo, "D-1")[:3] == [("draft", "proceed"), ("review", "proceed"), ("draft", "back:review")]
    done = resume(spec, "D-1", repo, registry(ex), decision="proceed", settings=NO_SLEEP)
    assert done.exit_code is ExitCode.FINISHED, done.message
    (fin,) = records(repo, "D-1", "finalize")
    assert fin["outcome"] == "written" and "docs/guide.md" in fin["reason"]


def test_doc_refresh_minor_routes_past_the_review(repo: Path) -> None:
    spec = load_package(plugin("doc-refresh")).spec
    doc_repo(repo)
    ex = standin("claude", steps=[draft("minor")], judges=[met(2), met(1, "j-outcome")])
    out = start(spec, "D-2", {"request": REQUEST}, repo, registry(ex), NO_SLEEP)
    assert out.exit_code is ExitCode.FINISHED, out.message
    assert "review" not in {u for u, _ in entered(repo, "D-2")}
    assert records(repo, "D-2", "finalize")[0]["outcome"] == "written"


def test_doc_refresh_check_catches_a_dropped_heading(repo: Path) -> None:
    spec = load_package(plugin("doc-refresh")).spec
    doc_repo(repo)
    dropped = FRESH.split("## Use")[0]
    ex = standin("claude", steps=[draft("minor", dropped)] * 3, judges=[met(2)] * 3)
    out = start(spec, "D-3", {"request": REQUEST}, repo, registry(ex), NO_SLEEP)
    assert out.exit_code is not ExitCode.FINISHED
    checks = records(repo, "D-3", "check")
    assert [c["result"] for c in checks if c["unit"] == "draft"][-1] == "FAIL"
    assert any("dr-headings" in c["evidence"] for c in checks)


def test_doc_refresh_outline_needs_a_named_document(repo: Path) -> None:
    spec = load_package(plugin("doc-refresh")).spec
    ex = standin("claude")
    out = start(spec, "D-4", {"request": "the install section"}, repo, registry(ex), NO_SLEEP)
    assert out.exit_code is not ExitCode.FINISHED and not ex.calls  # no session starts after a failed script
