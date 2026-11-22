"""doc-refresh on stand-ins: every path the workflow declares, on a scratch repository."""

from __future__ import annotations

import json
import subprocess
from pathlib import Path
from typing import Any

import pytest

from tempergraph.constants import ExitCode
from tempergraph.contracts import SessionResult
from tempergraph.executors.registry import Registry
from tempergraph.executors.standins import answer, standin
from tempergraph.package.loader import load_package
from tempergraph.run.runner import RunSettings, resume, start
from tempergraph.store.layout import run_dir, state_root_path

ROOT = Path(__file__).resolve().parents[1]
SPEC = load_package(ROOT).spec
NO_SLEEP = RunSettings(sleep=lambda s: None)


@pytest.fixture(autouse=True)
def _isolated_home(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("TEMPERGRAPH_HOME", str(tmp_path / "home" / ".tempergraph"))
    monkeypatch.setenv("TEMPERGRAPH_LOOP", "off")


@pytest.fixture
def repo(tmp_path: Path) -> Path:
    root = tmp_path / "repo"
    root.mkdir()
    for args in (["init", "-q", "-b", "main"], ["config", "user.email", "test@example.invalid"],
                 ["config", "user.name", "Test"]):
        subprocess.run(["git", *args], cwd=root, check=True, capture_output=True)
    (root / "README.md").write_text("scratch\n")
    subprocess.run(["git", "add", "README.md"], cwd=root, check=True, capture_output=True)
    subprocess.run(["git", "commit", "-q", "-m", "init"], cwd=root, check=True, capture_output=True)
    return root


def registry(ex: Any) -> Registry:
    r = Registry()
    r.register(ex)
    return r


def verdict_block(*statuses: str, defect_in: str | None = None) -> str:
    rows = [{"n": i, "status": s, "evidence": "notes.md:1 shows it" if s == "MET" else "missing",
             "defect_in": defect_in, "no_change": False} for i, s in enumerate(statuses, 1)]
    return "Reviewed.\n```json\n" + json.dumps({"criteria": rows, "gap": False, "confidence": 0.8}) + "\n```"


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
    doc_repo(repo)
    redo = answer(verdict_block("UNMET", "MET", defect_in="doc"), tools=("Read",), session_id="j-review")
    ex = standin("claude", steps=[draft("major"), REVIEW, draft("major"), REVIEW],
                 judges=[met(2), redo, met(2), met(2), met(1, "j-outcome")])
    out = start(SPEC, "D-1", {"request": REQUEST}, repo, registry(ex), NO_SLEEP)
    assert out.exit_code is ExitCode.PAUSED and out.payload["kind"] == "approval", out.message
    outline = records(repo, "D-1", "script")
    assert outline and outline[0]["unit"] == "outline" and not outline[0]["environmental"]  # a unit with no session
    assert entered(repo, "D-1")[:3] == [("draft", "proceed"), ("review", "proceed"), ("draft", "back:review")]
    done = resume(SPEC, "D-1", repo, registry(ex), decision="proceed", settings=NO_SLEEP)
    assert done.exit_code is ExitCode.FINISHED, done.message
    (fin,) = records(repo, "D-1", "finalize")
    assert fin["outcome"] == "written" and "docs/guide.md" in fin["reason"]


def test_doc_refresh_minor_routes_past_the_review(repo: Path) -> None:
    doc_repo(repo)
    ex = standin("claude", steps=[draft("minor")], judges=[met(2), met(1, "j-outcome")])
    out = start(SPEC, "D-2", {"request": REQUEST}, repo, registry(ex), NO_SLEEP)
    assert out.exit_code is ExitCode.FINISHED, out.message
    assert "review" not in {u for u, _ in entered(repo, "D-2")}
    assert records(repo, "D-2", "finalize")[0]["outcome"] == "written"


def test_doc_refresh_check_catches_a_dropped_heading(repo: Path) -> None:
    doc_repo(repo)
    dropped = FRESH.split("## Use")[0]
    ex = standin("claude", steps=[draft("minor", dropped)] * 3, judges=[met(2)] * 3)
    out = start(SPEC, "D-3", {"request": REQUEST}, repo, registry(ex), NO_SLEEP)
    assert out.exit_code is not ExitCode.FINISHED
    checks = records(repo, "D-3", "check")
    assert [c["result"] for c in checks if c["unit"] == "draft"][-1] == "FAIL"
    assert any("dr-headings" in c["evidence"] for c in checks)


def test_doc_refresh_outline_needs_a_named_document(repo: Path) -> None:
    ex = standin("claude")
    out = start(SPEC, "D-4", {"request": "the install section"}, repo, registry(ex), NO_SLEEP)
    assert out.exit_code is not ExitCode.FINISHED and not ex.calls  # no session starts after a failed script


def test_doc_refresh_hands_the_judges_the_changed_sections(repo: Path) -> None:
    """L-25: a judge cannot run `git diff`, so the draft and outcome checks name the sections that changed."""
    doc_repo(repo)
    ex = standin("claude", steps=[draft("minor")], judges=[met(2), met(1, "j-outcome")])
    out = start(SPEC, "D-5", {"request": REQUEST}, repo, registry(ex), NO_SLEEP)
    assert out.exit_code is ExitCode.FINISHED, out.message
    by_unit = {c["unit"]: c["evidence"] for c in records(repo, "D-5", "check")}
    assert "changed since the run's base" in by_unit["draft"] and ": Install" in by_unit["draft"]
    assert ": Install" in by_unit["outcome"] and "Sections removed: none" in by_unit["outcome"]
    prompts = [c.request.prompt for c in ex.calls if c.kind == "judge"]
    assert prompts and all("changed since the run's base" in p for p in prompts)
