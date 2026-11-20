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
