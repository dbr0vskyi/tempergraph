"""Task i124: the outcome check's guard for a spec the base branch changed since the run started (`ts-spec-fresh`),
with the criteria file that states it (SBS-B1 to SBS-B3, OUT-B16)."""

from __future__ import annotations

import importlib
import json
import re
import subprocess
import time
from pathlib import Path
from typing import Any

import pytest

from tempergraph.package.loader import load_package
from tempergraph.run.checks import CheckContext, GitFacts, run_check
from tempergraph.run.outcome import outcome_unit

ROOT = Path(__file__).resolve().parents[1]
SPEC = load_package(ROOT).spec
checks = importlib.import_module("tgwf_temperspec.checks")
A = "docs/specs/a.spec.md"
B = "docs/specs/b.spec.md"
FIX = "start the task again from the head of the base branch"


def _git(cwd: Path, *args: str) -> str:
    return subprocess.run(["git", "-c", "user.name=t", "-c", "user.email=t@example.invalid", *args], cwd=cwd,
                          capture_output=True, text=True, check=True).stdout.strip()


def _write(repo: Path, path: str, text: str) -> None:
    (repo / path).parent.mkdir(parents=True, exist_ok=True)
    (repo / path).write_text(text, encoding="utf-8")


def _commit(repo: Path, message: str) -> str:
    _git(repo, "add", "-A")
    _git(repo, "commit", "-q", "-m", message)
    return _git(repo, "rev-parse", "HEAD")


@pytest.fixture
def repo(tmp_path: Path) -> Path:
    """`main` holds two specs; the run's branch `run` starts at that commit."""
    root = tmp_path / "repo"
    root.mkdir()
    _git(root, "init", "-q", "-b", "main")
    _write(root, A, "# A\n\nversion 1\n")
    _write(root, B, "# B\n\nversion 1\n")
    _write(root, "README.md", "readme\n")
    _commit(root, "base")
    _git(root, "checkout", "-q", "-b", "run")
    return root


def _base(repo: Path) -> str:
    return _git(repo, "rev-parse", "run")  # the run's branch has no commit yet: its tip is the base commit


def _on_main(repo: Path, change: Any) -> str:
    """Make a commit on `main` and come back to the run's branch; returns main's head."""
    dirty = bool(_git(repo, "status", "--porcelain"))
    if dirty:
        _git(repo, "stash", "push", "-q", "-u", "-m", "run files")
    _git(repo, "checkout", "-q", "main")
    change(repo)
    head = _commit(repo, "main moves")
    _git(repo, "checkout", "-q", "run")
    if dirty:
        _git(repo, "stash", "pop", "-q")
    return head


def _context(repo: Path, base: str, base_head: str, edited: tuple[str, ...]) -> CheckContext:
    git = GitFacts(base=base, base_head=base_head, changed_paths=edited)
    ctx = CheckContext(unit="outcome", workdir=repo, request={}, artifacts={}, values={}, git=git,
                       allow=SPEC.allow_commands, out_dir=repo.parent / "out", deadline_at=time.monotonic() + 60)
    ctx.settings = {"deliverables": [], "outcome_check": SPEC.outcome.check.ref}  # type: ignore[union-attr]
    return ctx


def _fresh(ctx: CheckContext, specs: list[str]) -> list[Any]:
    return checks._fresh(ctx, specs)  # type: ignore[no-any-return]


def _fails(found: list[Any]) -> list[Any]:
    return [f for f in found if f.status == "fail"]


# -- a spec the base branch changed fails the guard (SBS-B1) ----------------------------------------------


def test_a_spec_the_base_branch_changed_fails_and_is_named(repo: Path) -> None:  # SBS-AC1, SBS-AC2, AC 4
    base = _base(repo)
    _write(repo, A, "# A\n\nversion 2 by the run\n")
    head = _on_main(repo, lambda r: _write(r, A, "# A\n\nversion 1 changed on main\n"))
    got = _fresh(_context(repo, base, head, (A,)), [A])
    (bad,) = _fails(got)
    assert bad.criterion == "ts-spec-fresh" and bad.place == A and FIX in bad.fix


def test_only_the_changed_one_of_two_edited_specs_is_named(repo: Path) -> None:  # SBS-AC1, SBS-AC2, AC 4
    base = _base(repo)
    _write(repo, A, "# A\n\nrun edit\n")
    _write(repo, B, "# B\n\nrun edit\n")
    head = _on_main(repo, lambda r: _write(r, B, "# B\n\nmain edit\n"))
    got = _fresh(_context(repo, base, head, (A, B)), [A, B])
    assert [f.place for f in _fails(got)] == [B]


def test_a_spec_the_run_created_where_main_added_one_is_named(repo: Path) -> None:  # SBS-AC1, SBS-AC2, AC 4
    base = _base(repo)
    new = "docs/specs/new.spec.md"
    _write(repo, new, "# New\n\nthe run's text\n")
    head = _on_main(repo, lambda r: _write(r, new, "# New\n\nmain's text\n"))
    got = _fresh(_context(repo, base, head, (new,)), [new])
    assert [f.place for f in _fails(got)] == [new]


def test_a_spec_main_deleted_is_named(repo: Path) -> None:  # SBS-AC1, SBS-AC2, AC 4
    base = _base(repo)
    _write(repo, A, "# A\n\nrun edit\n")
    head = _on_main(repo, lambda r: (r / A).unlink())
    got = _fresh(_context(repo, base, head, (A,)), [A])
    assert [f.place for f in _fails(got)] == [A]


def test_a_failed_guard_fails_the_outcome_check_with_a_final_criterion(repo: Path) -> None:  # SBS-AC1, SBS-AC2, AC 4
    base = _base(repo)
    _write(repo, A, "# A\n\nrun edit\n")
    head = _on_main(repo, lambda r: _write(r, A, "# A\n\nmain edit\n"))
    res, _ = run_check(outcome_unit(SPEC).gate, _context(repo, base, head, (A,)))  # type: ignore[union-attr]
    assert res.result == "FAIL"
    assert [f.place for f in res.findings if f.criterion == "ts-spec-fresh" and f.status == "fail"] == [A]
    final = {c.id for c in SPEC.outcome.final}  # type: ignore[union-attr]
    assert {f.criterion for f in res.findings} <= final


# -- what passes, and what does not apply (SBS-B2, SBS-B3) ------------------------------------------------


def test_the_guard_passes_when_main_has_not_moved(repo: Path) -> None:  # SBS-AC3, AC 5
    base = _base(repo)
    _write(repo, A, "# A\n\nrun edit\n")
    got = _fresh(_context(repo, base, base, (A,)), [A])
    assert not _fails(got) and [f.status for f in got] == ["pass"]


def test_the_guard_passes_when_main_changed_other_files_only(repo: Path) -> None:  # SBS-AC3, AC 5
    base = _base(repo)
    _write(repo, A, "# A\n\nrun edit\n")
    head = _on_main(repo, lambda r: _write(r, "README.md", "readme changed\n"))
    assert head != base
    got = _fresh(_context(repo, base, head, (A,)), [A])
    assert not _fails(got) and [f.status for f in got] == ["pass"]


def test_the_guard_passes_when_the_head_is_behind_the_base_commit(repo: Path) -> None:  # SBS-AC3, AC 5
    _git(repo, "checkout", "-q", "main")
    old = _git(repo, "rev-parse", "HEAD")
    _write(repo, A, "# A\n\nversion 1.5\n")
    _commit(repo, "main moves on")
    _git(repo, "checkout", "-q", "run")
    _git(repo, "reset", "-q", "--hard", "main")  # the run starts after that commit
    base = _base(repo)
    _write(repo, A, "# A\n\nrun edit\n")
    got = _fresh(_context(repo, base, old, (A,)), [A])  # main was set back to the older text
    assert not _fails(got) and [f.status for f in got] == ["pass"]


def test_the_guard_passes_when_main_changed_the_spec_and_restored_it(repo: Path) -> None:  # SBS-AC3, AC 5
    base = _base(repo)
    _write(repo, A, "# A\n\nrun edit\n")
    _on_main(repo, lambda r: _write(r, A, "# A\n\nmain edit\n"))
    head = _on_main(repo, lambda r: _write(r, A, "# A\n\nversion 1\n"))
    got = _fresh(_context(repo, base, head, (A,)), [A])
    assert not _fails(got) and [f.status for f in got] == ["pass"]


def test_a_run_with_no_base_branch_is_not_applicable(repo: Path) -> None:  # SBS-AC4, AC 5
    base = _base(repo)
    _write(repo, A, "# A\n\nrun edit\n")
    got = _fresh(_context(repo, base, "", (A,)), [A])
    assert [f.status for f in got] == ["n_a"] and "no base branch" in got[0].message
    assert got[0].criterion == "ts-spec-fresh"


def test_a_run_that_edited_no_spec_is_not_applicable(repo: Path) -> None:  # SBS-AC4, AC 5
    base = _base(repo)
    head = _on_main(repo, lambda r: _write(r, A, "# A\n\nmain edit\n"))
    got = _fresh(_context(repo, base, head, ()), [])
    assert [f.status for f in got] == ["n_a"] and "edited no spec" in got[0].message


def test_a_not_applicable_guard_fails_nothing_in_the_outcome_check(repo: Path) -> None:  # SBS-AC4, AC 5
    base = _base(repo)
    res, _ = run_check(outcome_unit(SPEC).gate, _context(repo, base, "", ()))  # type: ignore[union-attr]
    fresh = [f for f in res.findings if f.criterion == "ts-spec-fresh"]
    assert fresh and all(f.status == "n_a" for f in fresh)


# -- the criteria file (AC 4, AC 5, ts-spec-fresh) --------------------------------------------------------


def _rows() -> dict[str, str]:
    text = (ROOT / "docs" / "specs" / "00-overview.spec.md").read_text(encoding="utf-8")
    return {m.group(1): m.group(2) for line in text.splitlines()
            if (m := re.match(r"^- \[[ xX]\] (ts-\S+) (.+)$", line))}


def _outcome() -> dict[str, Any]:
    return json.loads((ROOT / "outcome.json").read_text(encoding="utf-8"))  # type: ignore[no-any-return]


def test_the_criteria_file_has_the_revision_entry_that_cites_the_issues() -> None:  # AC 4, AC 5, ts-spec-fresh
    o = _outcome()
    entry = next(r for r in o["revisions"] if "issues 118 and 124" in r.get("note", ""))
    assert entry["revision"] >= 12 and entry["origin"] == "authored"
    assert o["revision"] == o["revisions"][-1]["revision"] >= entry["revision"]


def test_ts_spec_fresh_is_a_blocker_checked_by_the_outcome_check() -> None:  # AC 4, AC 5, ts-spec-fresh
    row = next(c for c in _outcome()["final"] if c["id"] == "ts-spec-fresh")
    assert row["text"] == _rows()["ts-spec-fresh"]
    assert row["severity"] == "blocker" and row["verified_by"] == "check"
    assert row["verifier"]["check"] == "tgwf_temperspec.checks:outcome_check" and row["check_method"].strip()
    served = [c for io in _outcome()["intermediate"].values() for c in io["criteria"]
              if "ts-spec-fresh" in (c.get("serves") or [])]
    assert served == []  # OUT-B16: no unit criterion serves it
