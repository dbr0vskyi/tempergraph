"""`tempergraph audit tools <workflow> [--executor <name>]` (TSA-B3, TSA-B5, TSA-B8; TSA-AC4, TSA-AC6): the matrix of
sessions and tools with `Granted`, `Needed`, `Used` and `Verdict`; the same on every executor but for tool names; `—`
in every `Used` cell, and the history rules listed as skipped, when the workflow has no history."""

from __future__ import annotations

import io
import json
from pathlib import Path
from typing import Any

import pytest

from tempergraph.cli.main import main
from tempergraph.contracts import ProbeReport
from tempergraph.executors.capabilities import DECLARED
from tempergraph.executors.registry import Registry
from tempergraph.executors.standins import standin

from .fixtures.packages import DECLARATION, minimal_package
from .test_audit_history import many, write_run

DECL = DECLARATION.replace('tools=["read", "write"]', 'tools=["read", "search", "shell"], commands=["pytest"]'
                           ).replace('order=["draft"],', 'order=["draft"], allow_commands=["pytest"],')
NAME = "release-notes"
WINDOW = ["--window", "36500", "--version", "all"]


def registry() -> Registry:
    reg = Registry()
    reg.register(standin("claude", probe_report=ProbeReport(ok=True, version="2.1.329")))
    return reg


def tools(root: Path, repo: Path, *extra: str, fmt: str = "json") -> tuple[int, Any]:
    out = io.StringIO()
    code = main(["audit", "tools", str(root), "--format", fmt, *WINDOW, *extra], registry=registry(), cwd=repo, out=out,
                err=io.StringIO())
    return code, (json.loads(out.getvalue()) if fmt == "json" else out.getvalue())


def state(repo: Path) -> Path:
    return repo / ".tempergraph"


def cells(doc: dict[str, Any], *keys: str) -> set[tuple[Any, ...]]:
    return {tuple(r[k] for k in keys) for r in doc["rows"]}


def test_the_matrix_has_one_row_per_session_and_tool(tmp_path: Path, repo: Path) -> None:
    """TSA-AC4 (TSA-B8): rows of `<unit>` and `<unit>:judge` with Granted, Needed, Used and Verdict."""
    root = minimal_package(tmp_path / "src", declaration=DECL)
    code, text = tools(root, repo, fmt="text")
    assert code == 0
    header = next(line for line in text.splitlines() if "Granted" in line)
    assert all(h in header for h in ("Session", "Tool", "Capability", "Granted", "Needed", "Used", "Verdict"))
    body = [line.split() for line in text.splitlines() if line.startswith("draft")]
    assert any(r[0] == "draft" and "Bash" in r and "shell" in r for r in body)
    assert any(r[0] == "draft:judge" and "Read" in r for r in body)
    code, doc = tools(root, repo)
    assert code == 0 and doc["workflow"] == NAME and doc["schema_version"] == 1
    for row in doc["rows"]:
        assert set(row) >= {"session", "unit", "tool", "capability", "granted", "needed", "used", "verdict"}
        assert row["granted"] in ("yes", "no", "ambient")
        assert row["verdict"] in ("ok", "missing", "unused", "exposed", "refused", "drift")


@pytest.mark.parametrize("executor", sorted(DECLARED))
def test_each_executors_rows_come_from_its_tool_map(tmp_path: Path, repo: Path, executor: str) -> None:
    """TSA-AC4 (TSA-B3): `--executor <name>` shows the step's `read`, `search` and `shell` as that executor's tool
    names; `shell` maps to `Bash` on claude and agent-sdk and to `run_command` on messages-api and antigravity."""
    root = minimal_package(tmp_path / "src", declaration=DECL)
    code, doc = tools(root, repo, "--executor", executor)
    assert code == 0 and doc["executor"] == executor
    step = {r["capability"]: r["tool"] for r in doc["rows"] if r["session"] == "draft" and r["granted"] == "yes"}
    tool_map = DECLARED[executor].tool_map
    assert step["shell"] in tool_map["shell"] and step["read"] in tool_map["read"]
    assert step["shell"] == ("Bash" if executor in ("claude", "agent-sdk") else "run_command")


def test_the_four_executors_differ_only_in_tool_names(tmp_path: Path, repo: Path) -> None:
    """TSA-AC4 (TSA-B3): without the tool names every executor's rows are the same."""
    root = minimal_package(tmp_path / "src", declaration=DECL)
    seen = []
    for executor in sorted(DECLARED):
        _, doc = tools(root, repo, "--executor", executor)
        seen.append(cells(doc, "session", "capability", "granted", "needed", "used", "verdict"))
    assert all(s == seen[0] for s in seen)
    assert seen[0], "the matrix is not empty"


def test_granted_comes_from_the_tool_maps_alone_not_from_run_records(tmp_path: Path, repo: Path) -> None:
    """TSA-AC4: recorded runs change `Used`, never `Granted` or `Needed`."""
    root = minimal_package(tmp_path / "src", declaration=DECL)
    _, before = tools(root, repo)
    many(state(repo), 3, workflow=NAME, attempts=[{"calls": [{"name": "Read"}, {"name": "Bash", "capability": "shell"}]}])
    _, after = tools(root, repo)
    keep = ("session", "tool", "capability", "granted", "needed")
    assert cells(before, *keep) == cells(after, *keep)
    assert cells(before, "used") != cells(after, "used")


# -- no history, and with it (TSA-B5, TSA-AC6) ----------------------------------------------------------------------------


def test_without_history_every_used_cell_is_a_dash_and_the_history_rules_are_listed_skipped(tmp_path: Path,
                                                                                            repo: Path) -> None:
    """TSA-AC6 (TSA-B5): a workflow with no runs shows `—` in every `Used` cell and the history rules as skipped."""
    root = minimal_package(tmp_path / "src", declaration=DECL)
    _, doc = tools(root, repo)
    assert doc["rows"] and {r["used"] for r in doc["rows"]} == {"—"} and doc["history"] is False
    skipped = {s["rule"]: s for s in doc["rules_skipped"]}
    assert {"judge-exposed-tool", "granted-never-used", "undeclared-calls", "refusals-by-class",
            "granted-at-run", "loop-driver-criterion"} <= set(skipped)
    assert all(s["reason"] == "no runs in window" and "min_n" in s for s in skipped.values())
    _, text = tools(root, repo, fmt="text")
    assert "history rules skipped" in text and "granted-never-used" in text


def test_with_history_the_cells_hold_counts(tmp_path: Path, repo: Path) -> None:
    """TSA-AC6: with runs, `Used` holds calls and refusals per tool."""
    root = minimal_package(tmp_path / "src", declaration=DECL)
    many(state(repo), 3, workflow=NAME, attempts=[{"calls": [{"name": "Read"}, {"name": "Read"}],
                                                   "denied": [{"name": "Bash", "input_summary": "grep x ."}]}])
    _, doc = tools(root, repo)
    used = {(r["session"], r["tool"]): r["used"] for r in doc["rows"]}
    assert used[("draft", "Read")] == "6 calls, 0 refused" and used[("draft", "Bash")] == "0 calls, 3 refused"
    assert doc["history"] is True
    assert next(r for r in doc["rows"] if r["tool"] == "Bash" and r["session"] == "draft")["verdict"] == "refused"
    assert "loop-driver-criterion" in {s["rule"] for s in doc["rules_skipped"]}  # n=3 of 5, still listed


def test_an_ambient_tool_the_judge_listed_is_exposed(tmp_path: Path, repo: Path) -> None:
    """TSA-B8: a tool in a recorded start list that nobody granted is `ambient` in `Granted` and `exposed`."""
    root = minimal_package(tmp_path / "src", declaration=DECL)
    many(state(repo), 2, workflow=NAME, attempts=[{"judge": {"tools_started": ["Read", "mcp__monitor__status"]}}])
    _, doc = tools(root, repo)
    row = next(r for r in doc["rows"] if r["session"] == "draft:judge" and r["tool"] == "mcp__monitor__status")
    assert (row["granted"], row["verdict"]) == ("ambient", "exposed")


def test_the_matrix_verdicts_agree_with_the_findings(tmp_path: Path, repo: Path) -> None:
    """TSA-AC6: a step tool the matrix calls `unused` is the capability `granted-not-needed` names, and the matrix
    and the findings come from one surface."""
    decl = DECL.replace('tools=["read", "search", "shell"]', 'tools=["write", "web_fetch", "shell"]')
    root = minimal_package(tmp_path / "src", declaration=decl)
    _, doc = tools(root, repo)
    unused = {r["capability"] for r in doc["rows"] if r["session"] == "draft" and r["verdict"] == "unused"}
    assert unused == {"web_fetch"}
    out = io.StringIO()
    main(["audit", str(root), "--format", "json", "--all", "--layer", "definition"], registry=registry(), cwd=repo,
         out=out, err=io.StringIO())
    named = {f["item"] for f in json.loads(out.getvalue())["findings"] if f["rule"] == "granted-not-needed"}
    assert named == unused


def test_fail_on_counts_only_tool_findings(tmp_path: Path, repo: Path) -> None:
    """TSA-B13, AUD-B9: `--fail-on error` exits 6 on a C4 error (`shell` with no command prefix) and 0 otherwise."""
    bad = DECL.replace(', commands=["pytest"]', "")
    root = minimal_package(tmp_path / "bad", declaration=bad)
    assert tools(root, repo, "--fail-on", "error")[0] == 6
    assert tools(root, repo)[0] == 0
    good = minimal_package(tmp_path / "good", declaration=DECL)
    assert tools(good, repo, "--fail-on", "error")[0] == 0


def test_step_narrows_the_matrix(tmp_path: Path, repo: Path) -> None:
    """AUD-B11: `--step` keeps only that unit's sessions."""
    root = minimal_package(tmp_path / "src", declaration=DECL)
    _, doc = tools(root, repo, "--step", "draft")
    assert {r["unit"] for r in doc["rows"]} == {"draft"}
    _, doc = tools(root, repo, "--step", "elsewhere")
    assert doc["rows"] == []


def test_the_tools_verb_writes_nothing(tmp_path: Path, repo: Path) -> None:
    """AUD-AC2: the verb leaves the state root unchanged."""
    from .conftest import hash_tree

    root = minimal_package(tmp_path / "src", declaration=DECL)
    write_run(state(repo), "t000", workflow=NAME)
    before = hash_tree(state(repo))
    tools(root, repo)
    assert hash_tree(state(repo)) == before
