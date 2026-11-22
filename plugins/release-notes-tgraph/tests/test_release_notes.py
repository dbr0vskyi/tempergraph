"""Offline tests of the package's own code; the engine's tests load and run the whole package on stand-ins."""

from pathlib import Path

from release_notes.checks import draft_check


class Ctx:
    def __init__(self, workdir: Path) -> None:
        self.workdir = workdir


def test_four_headings_pass(tmp_path: Path) -> None:
    (tmp_path / "notes.md").write_text("# Added\n- a\n# Changed\n- none\n# Fixed\n- none\n# Removed\n- none\n")
    assert draft_check(Ctx(tmp_path)).result == "PASS"


def test_a_missing_heading_fails(tmp_path: Path) -> None:
    (tmp_path / "notes.md").write_text("# Added\n- a\n")
    assert draft_check(Ctx(tmp_path)).result == "FAIL"


def _git(cwd: Path, *argv: str) -> None:
    import subprocess

    subprocess.run(["git", "-c", "user.email=t@example.invalid", "-c", "user.name=t", *argv], cwd=cwd, check=True,
                   capture_output=True)


def test_the_checks_hand_the_judges_the_changes_since_the_last_tag(tmp_path: Path) -> None:
    """L-25: a judge cannot run git, so the draft and outcome checks list the commits since the last tag."""
    import time

    from release_notes.checks import outcome_check

    from tempergraph.run.checks import CheckContext

    _git(tmp_path, "init", "-q", "-b", "main")
    _git(tmp_path, "commit", "-q", "--allow-empty", "-m", "first")
    _git(tmp_path, "tag", "v1.0")
    _git(tmp_path, "commit", "-q", "--allow-empty", "-m", "add the export button")
    (tmp_path / "notes.md").write_text("# Added\n- export\n# Changed\n- none\n# Fixed\n- none\n# Removed\n- none\n")
    ctx = CheckContext(unit="draft", workdir=tmp_path, request={"request": "v1.1"},
                       allow=("git describe", "git log"), out_dir=tmp_path / ".out",
                       deadline_at=time.monotonic() + 60)
    got = draft_check(ctx)
    assert got.result == "PASS" and "Changes since the last tag v1.0" in got.evidence
    assert "add the export button" in got.evidence and "first" not in got.evidence.split("v1.0..HEAD")[1]
    assert "add the export button" in outcome_check(ctx).evidence
