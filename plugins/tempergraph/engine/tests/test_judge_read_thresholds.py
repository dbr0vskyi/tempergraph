"""The thresholds of the judge read share, and the shape of the specs that state them (SRV-B31; SRV-AC13, SRV-AC14,
SRV-AC45, SRV-AC46; task AC 7 and AC 9).

Every fixture is an engine run with stand-in sessions that open paths through `reads=`. Nothing here names a workflow
package.
"""

from __future__ import annotations

import ast
import re
import uuid
from pathlib import Path

import pytest

from tempergraph.constants import ExitCode
from tempergraph.executors.standins import standin
from tempergraph.improve import params

from .test_judge_changed_paths import causes_of, judge_digest
from .test_judge_read_share import build_unit, flow_of, opened, writer
from .test_run import go

ENGINE = Path(__file__).resolve().parents[1]
DOCS = ENGINE.parent / "docs"
TESTS = ENGINE / "tests"
SPECS = ("judge-read-share", "workflow-model", "session-review")


def visit(repo: Path, task: str, files: int, read: int, *, notes: bool = False) -> tuple[dict[str, int], set[tuple[str, str]]]:
    """One build unit that writes `files` files, the first being the declared notes file when `notes`; a judge that
    passes and opens the notes file (when declared) and then `read` counted files."""
    names = [f"f{i}.md" for i in range(files)]
    if notes:
        names[0] = "notes.md"
    counted = [n for n in names if n != "notes.md"]
    spec = flow_of({"build": build_unit(produces={"notes": "file"} if notes else None)})
    steps = [writer(*names, artifact="notes: notes.md" if notes else "")]
    opens = (["notes.md"] if notes else []) + counted[:read]
    ex = standin("claude", steps=steps, judges=[opened(*opens)])
    assert go(repo, ex, spec, task=task).exit_code is ExitCode.FINISHED
    d = judge_digest(repo, task, "build.1.judge")
    return {"total": d["changed_total"], "read": d["changed_read"]}, causes_of(repo, task)


@pytest.mark.parametrize("n", [2, 3, 3, 4, 8, 10, 10])
def test_a_judge_that_opened_only_the_declared_notes_file_is_unread(repo: Path, n: int) -> None:  # SRV-AC45, AC 7
    got, causes = visit(repo, f"TH-{n}-{uuid.uuid4().hex[:6]}", n, 0, notes=True)
    assert got == {"total": n - 1, "read": 0}
    assert ("build", "judge_unread_pass") in causes and ("build", "judge_partial_read") not in causes


@pytest.mark.parametrize(("total", "read", "partial"), [(5, 1, True), (5, 2, False), (8, 1, True), (8, 2, False)])
def test_a_share_under_a_quarter_is_a_partial_read_and_a_quarter_is_not(repo: Path, total: int, read: int,
                                                                        partial: bool) -> None:  # SRV-AC46, AC 7
    got, causes = visit(repo, f"SH-{total}-{read}", total, read)
    assert got == {"total": total, "read": read}
    assert (("build", "judge_partial_read") in causes) is partial
    assert ("build", "judge_unread_pass") not in causes


def test_the_read_share_keeps_its_value_and_its_source() -> None:  # SRV-AC13, SRV-AC14, AC 7
    p = params.PARAMS["digest.judge_read_share"]
    assert p.value == 0.25 and "SRV-B31" in p.source
    assert params.value("digest.judge_read_share") == 0.25


# -- the shape of the specs (AC 9) -----------------------------------------------------------------------------------


def packages() -> set[str]:
    found = set()
    for manifest in ENGINE.parents[1].glob("*/tempergraph.json"):
        name = manifest.parent.name
        found |= {name, name.removesuffix("-tgraph")}
    return {n for n in found if n and n != "tempergraph"}


@pytest.mark.parametrize("name", SPECS)
def test_a_spec_is_within_its_budget_and_names_no_workflow(name: str) -> None:  # SRV-AC13, AC 9
    path = DOCS / "specs" / f"{name}.spec.md"
    raw = path.read_bytes()
    assert len(raw.splitlines()) <= 400 and len(raw) <= 30_720
    text = raw.decode()
    for pkg in packages():
        assert pkg not in text, pkg


NEW_TESTS = ("test_standin_reads.py", "test_judge_read_share.py", "test_judge_read_thresholds.py",
             "test_judge_read_share_privacy.py")


def test_every_test_of_this_task_carries_the_id_of_its_criterion() -> None:  # SRV-AC13, AC 9
    missing = []
    for file in NEW_TESTS:
        lines = (TESTS / file).read_text().splitlines()
        for node in ast.parse("\n".join(lines)).body:
            if isinstance(node, ast.FunctionDef) and node.name.startswith("test_"):
                head = "\n".join(lines[node.lineno - 2:node.body[0].lineno - 1])
                if not re.search(r"\b(SRV|WFM)-AC\d+", head):
                    missing.append(f"{file}::{node.name}")
    assert missing == []


def test_the_criteria_of_the_existing_behaviour_are_carried_by_tests() -> None:  # SRV-AC13, SRV-AC14, AC 9
    corpus = "\n".join(p.read_text() for p in TESTS.glob("test_*.py"))
    for n in [13, 14, *range(21, 32)]:
        assert re.search(rf"SRV-AC{n}\b", corpus), f"SRV-AC{n}"
