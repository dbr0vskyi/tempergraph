"""What the judges of the workflow are told to read and to quote (spec judge-reading, JRD-*): the evidence the code
gate hands its judge (changed source files, reading budget), the code brief's reading rules, and the quoted line
behind every MET in the seven briefs and the outcome judge's stance."""

from __future__ import annotations

import importlib
import json
import subprocess
import time
from pathlib import Path

import pytest

from tempergraph.api import checks as api_checks
from tempergraph.package.loader import load_package
from tempergraph.run.checks import CheckContext, GitFacts, git_facts
from tempergraph.run.judging import JudgeInputs, render_judge

ROOT = Path(__file__).resolve().parents[1]
SPEC = load_package(ROOT).spec
checks = importlib.import_module("tgwf_temperspec.checks")

SOURCE_LINE = "Changed source files"  # the evidence line that lists the changed source files
# AC 3, JRD-AC6, JRD-AC7: the judges of the two reading units join the seven step judges
UNITS = ("setup", "triage", "discovery_short", "read_gap", "read_component", "discovery", "plan", "expand", "code")


def _git(cwd: Path, *args: str) -> str:
    return subprocess.run(["git", "-c", "user.name=t", "-c", "user.email=t@example.invalid", *args], cwd=cwd,
                          capture_output=True, text=True, check=True).stdout


def _scratch(root: Path, files: dict[str, int]) -> tuple[Path, str]:
    """A repository with a base commit, then one commit that adds each file with that many lines.
    Returns (repository, base commit)."""
    _git(root, "init", "-q", "-b", "main")
    (root / "README.txt").write_text("start\n")
    _git(root, "add", "-A")
    _git(root, "commit", "-q", "-m", "start")
    base = _git(root, "rev-parse", "HEAD").strip()
    for name, count in files.items():
        (root / name).parent.mkdir(parents=True, exist_ok=True)
        (root / name).write_text("".join(f"line {i}\n" for i in range(count)))
    _git(root, "add", "-A")
    _git(root, "commit", "-q", "-m", "the change")
    return root, base


def _ctx(work: Path, git: GitFacts) -> CheckContext:
    return CheckContext(unit="code", workdir=work, request={}, artifacts={}, values={}, git=git,
                        allow=SPEC.allow_commands, out_dir=work.parent / f"{work.name}.out",
                        deadline_at=time.monotonic() + 60)


def _evidence(work: Path, git: GitFacts) -> str:
    ctx = _ctx(work, git)
    return str(checks._result(ctx, [], None, None, reading=checks._reading_lines(ctx)).evidence)


def _line(evidence: str, prefix: str) -> str:
    found = [ln for ln in evidence.splitlines() if ln.startswith(prefix)]
    assert len(found) == 1, evidence
    return found[0]


def _said(text: str) -> str:
    return " ".join(text.split()).lower()


def test_the_evidence_lists_the_source_files_most_changed_lines_first(tmp_path: Path) -> None:  # JRD-AC1, AC 2
    repo, base = _scratch(tmp_path, {"src/small.py": 30, "src/big.py": 120, "src/mid.py": 80, "docs/note.md": 40})
    evidence = _evidence(repo, git_facts(repo, base))
    listed = _line(evidence, SOURCE_LINE)
    assert listed.endswith("src/big.py 120; src/mid.py 80; src/small.py 30"), listed
    assert "note.md" not in listed
    assert listed.count(";") == 2  # exactly the three source files


def test_a_change_of_markdown_documents_alone_has_no_source_file(tmp_path: Path) -> None:  # JRD-AC1, AC 2
    repo, base = _scratch(tmp_path, {"docs/note.md": 40, "docs/more.md": 10})
    evidence = _evidence(repo, git_facts(repo, base))
    assert "no source file" in _line(evidence, SOURCE_LINE)
    assert "Changed source lines: 0" in evidence and "Reading budget: 10 files" in evidence


@pytest.mark.parametrize(("lines", "budget"), [(120, 10), (2100, 42), (2101, 43), (5000, 50)])
def test_the_reading_budget_is_one_file_per_50_changed_source_lines(
        tmp_path: Path, lines: int, budget: int) -> None:  # JRD-AC3, AC 1
    repo, base = _scratch(tmp_path, {"src/one.py": lines, "docs/note.md": 500})  # Markdown lines are not counted
    evidence = _evidence(repo, git_facts(repo, base))
    assert f"Changed source lines: {lines}." in evidence, evidence
    assert f"Reading budget: {budget} files" in evidence, evidence


def test_with_no_base_the_evidence_says_why_it_counts_nothing_and_states_the_floor(
        tmp_path: Path) -> None:  # JRD-AC3, AC 1
    git = GitFacts(changed_paths=("src/a.py", "docs/note.md", "src/b.py"))
    evidence = _evidence(tmp_path, git)
    assert "not counted" in _line(evidence, "Changed source lines") and "no base commit" in evidence
    assert "Reading budget: 10 files" in evidence
    assert _line(evidence, SOURCE_LINE).endswith("src/a.py; src/b.py")  # no counts, no Markdown document


def test_the_prompt_names_all_40_changed_source_files(tmp_path: Path) -> None:  # JRD-AC2, AC 2
    names = {f"src/package/subpackage/module_{i:02d}.py": 100 + i for i in range(40)}
    assert {len(n) for n in names} == {35}
    repo, base = _scratch(tmp_path, names)
    evidence = _evidence(repo, git_facts(repo, base))
    brief = (ROOT / "judges" / "code.md").read_text(encoding="utf-8").split("# Brief", 1)[1]
    result = api_checks.result([], evidence=evidence)
    prompt = render_judge(JudgeInputs(gate=SPEC.units["code"].gate, stance="", brief=brief, request="the task",
                                      check=result))
    assert _line(evidence, SOURCE_LINE) in prompt
    assert all(name in prompt for name in names)


# -- the code brief ----------------------------------------------------------------------------------------


def _code_brief() -> str:
    return _said((ROOT / "judges" / "code.md").read_text(encoding="utf-8").split("# Brief", 1)[1])


def test_the_code_brief_has_the_judge_read_each_listed_file_up_to_the_budget() -> None:  # JRD-AC4, AC 2
    brief = _code_brief()
    for phrase in ("read each source file the evidence lists", "in the listed order", "up to the reading budget",
                   "before you grade `ts-code-aligned` or `ts-code-related`", "the file itself",
                   "not only the lines a search prints"):
        assert phrase in brief, phrase


def test_the_code_brief_grades_unverifiable_what_rests_on_a_file_beyond_the_budget() -> None:  # JRD-AC5
    brief = _code_brief()
    for phrase in ("rests on a listed source file beyond the reading budget", "is unverifiable",
                   "name the files you did not read", "rests only on files you read is not limited by"):
        assert phrase in brief, phrase


def test_only_the_code_judge_has_a_time_limit_of_its_own() -> None:  # AC 2 (JDG-B4: a judge timeout escalates)
    limits = {u: SPEC.units[u].gate.judge.timeout_s for u in UNITS}  # type: ignore[union-attr]
    assert limits.pop("code") == 1800
    assert set(limits.values()) == {None}


# -- the quoted line and the search-line rule in every judge text ---------------------------------------------


def _texts() -> dict[str, str]:
    out = {u: (ROOT / "judges" / f"{u}.md").read_text(encoding="utf-8").split("# Brief", 1)[1] for u in UNITS}
    out["outcome stance"] = json.loads((ROOT / "outcome.json").read_text())["judge"]["stance"]
    return {k: _said(v) for k, v in out.items()}


@pytest.mark.parametrize("name", [*UNITS, "outcome stance"])
def test_every_judge_text_asks_for_the_quoted_line_behind_a_met(name: str) -> None:  # JRD-AC6, AC 3
    text = _texts()[name]
    assert "behind every met, quote the line you relied on, with its path and line number" in text


@pytest.mark.parametrize("name", [*UNITS, "outcome stance"])
def test_every_judge_text_grades_search_lines_alone_partial(name: str) -> None:  # JRD-AC7, AC 4
    text = _texts()[name]
    assert "grade a criterion partial, not met, when its only evidence is lines a search printed" in text
    assert "when you searched and then read the file around the line, quote the line from the file you read" in text


# -- the follow-through of the change ----------------------------------------------------------------------


def test_the_code_seeds_carry_the_new_evidence_and_the_outcome_record_says_so() -> None:  # AC 5
    seeds = sorted((ROOT / "evals" / "calibration" / "code").glob("*-ts-code-*"))
    assert len(seeds) == 10
    for seed in seeds:
        evidence = json.loads((seed / "fixture" / "check.json").read_text())["evidence"]
        for prefix in ("Changed source lines:", "Reading budget:", SOURCE_LINE):
            assert prefix in evidence, (seed.name, prefix)
    outcome = json.loads((ROOT / "outcome.json").read_text())
    entry = next(r for r in outcome["revisions"] if "issues 55 and 56" in r.get("note", ""))
    assert entry["revision"] >= 8 and outcome["revision"] == outcome["revisions"][-1]["revision"] >= entry["revision"]
    assert any("one file per 50" in a and "first values" in a for a in outcome["assumptions"])


@pytest.mark.parametrize("name", [*UNITS, "outcome stance"])
def test_every_judge_text_grades_a_check_verified_criterion_from_its_finding(name: str) -> None:  # JRD-AC8
    text = _texts()[name]
    assert "a criterion the gate's check verified is graded from the check's finding" in text
    assert "never grade it unverifiable because you cannot run the check yourself" in text
