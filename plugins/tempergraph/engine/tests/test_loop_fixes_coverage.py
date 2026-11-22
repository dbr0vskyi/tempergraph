"""Every criterion of the loop-fixes task has an offline test that carries its id (AC 6; plan `loop-fixes`)."""

from __future__ import annotations

import ast
import re
from pathlib import Path

import pytest

TESTS = Path(__file__).resolve().parent
CRITERIA = ("SRV-AC8", "SRV-AC9", "SRV-AC10", "SRV-AC11", "BUD-AC8", "SIL-AC14", "SIL-AC15", "CLI-AC10", "RDD-AC6")


def carries(criterion: str, name: str, lines: list[str]) -> bool:
    """The id stands in the test's name or in a comment of its lines."""
    token = re.compile(rf"(?<![\w-]){re.escape(criterion)}(?![\w-])")
    if token.search(name):
        return True
    return any(token.search(ln.split("#", 1)[1]) for ln in lines if "#" in ln)


def skipped(node: ast.FunctionDef, source: str) -> bool:
    if any("skip" in (ast.get_source_segment(source, d) or "") for d in node.decorator_list):
        return True
    return any(isinstance(n, ast.Call) and (ast.get_source_segment(source, n.func) or "") == "pytest.skip"
               for n in ast.walk(node))


def carriers(criterion: str) -> list[str]:
    found: list[str] = []
    for path in sorted(TESTS.glob("test_*.py")):
        if path.name == Path(__file__).name:
            continue
        source = path.read_text(encoding="utf-8")
        rows = source.splitlines()
        for node in ast.walk(ast.parse(source)):
            if isinstance(node, ast.FunctionDef) and node.name.startswith("test_") and not skipped(node, source):
                start = min([node.lineno, *[d.lineno for d in node.decorator_list]])
                if carries(criterion, node.name, rows[start - 1:node.end_lineno]):
                    found.append(f"{path.name}::{node.name}")
    return found


@pytest.mark.parametrize("criterion", CRITERIA)
def test_every_criterion_of_the_task_is_carried_by_a_test_that_runs(criterion: str) -> None:  # AC 6
    assert carriers(criterion), f"no test that runs carries {criterion}"


def test_the_matcher_reads_ids_whole() -> None:  # AC 6
    assert carries("SRV-AC1", "test_x", ["    assert x  # SRV-AC10"]) is False
    assert carries("SRV-AC10", "test_x", ["    assert x  # SRV-AC10"]) is True
    assert carries("RDD-AC6", "test_rdd_ac6", []) is False  # the id is spelled in capitals
