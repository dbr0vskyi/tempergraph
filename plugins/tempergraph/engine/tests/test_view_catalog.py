"""A judge's MCP views come from a constant catalog, never from a step's own tool (GRD-B1, GRD-B7, GRD-AC6)."""

from __future__ import annotations

import dataclasses
from pathlib import Path

from tempergraph.contracts import StepSpec
from tempergraph.executors import viewcatalog
from tempergraph.executors.capabilities import CLAUDE
from tempergraph.run.guard import view_set

JUDGE = dataclasses.replace(CLAUDE, judge_mcp=True)  # a judge executor that can host MCP views


def step(*tools: str) -> StepSpec:
    return StepSpec(tools=tuple(tools))


def test_grd_ac6_a_tracker_write_tool_gives_its_read_view_and_never_itself() -> None:
    for tool in ("mcp:tracker/create_issue", "mcp:tracker/update_issue"):
        views = view_set(step("read", "write", tool), [], JUDGE)
        assert views.tools == ("Read", "Grep", "Glob", "mcp__tracker__get_issue")
        assert "mcp__tracker__" + tool.split("/")[1] not in views.tools
        assert views.deferred == ()


def test_grd_ac6_a_wiki_update_tool_gives_the_page_view() -> None:
    views = view_set(step("read", "mcp:wiki/update_page"), [], JUDGE)
    assert views.tools == ("Read", "Grep", "Glob", "mcp__wiki__get_page")
    assert views.deferred == ()


def test_grd_ac6_one_view_per_read_tool_however_many_writes_name_it() -> None:
    views = view_set(step("mcp:tracker/create_issue", "mcp:tracker/update_issue", "mcp:wiki/update_page"), [], JUDGE)
    assert views.tools == ("Read", "Grep", "Glob", "mcp__tracker__get_issue", "mcp__wiki__get_page")


def test_grd_ac6_a_tool_the_catalog_does_not_list_gives_no_view_and_is_deferred() -> None:
    views = view_set(step("read", "mcp:tracker/transition_issue", "mcp:tracker/update_issue"), [], JUDGE)
    assert views.tools == ("Read", "Grep", "Glob", "mcp__tracker__get_issue")  # nothing of the unlisted tool
    assert [(d.capability, d.reason) for d in views.deferred] == [("mcp:tracker/transition_issue", "view_unlisted")]


def test_grd_ac6_the_step_tool_is_never_offered_even_when_it_is_the_unlisted_one() -> None:
    views = view_set(step("mcp:crm/update_contact"), [], JUDGE)
    assert not [t for t in views.tools if t.startswith("mcp__")]
    assert [d.capability for d in views.deferred] == ["mcp:crm/update_contact"]


def test_grd_ac6_an_executor_without_judge_mcp_defers_every_mcp_tool() -> None:
    views = view_set(step("mcp:tracker/update_issue"), [], dataclasses.replace(CLAUDE, judge_mcp=False))
    assert views.tools == ("Read", "Grep", "Glob")
    assert [(d.capability, d.reason) for d in views.deferred] == [("mcp:tracker/update_issue", "judge_mcp")]


def test_grd_ac6_an_authors_judge_tools_only_narrow_the_views() -> None:
    views = view_set(step("mcp:tracker/update_issue"), [], JUDGE, judge_tools=["read"])
    assert views.tools == ("Read",)


def test_grd_ac1_the_catalog_is_keyed_by_full_tool_name_and_infers_nothing() -> None:
    assert viewcatalog.read_views("mcp:tracker/update_issue") == ("mcp:tracker/get_issue",)
    assert viewcatalog.read_views("mcp:tracker/update_issues") == ()  # a near name is not the listed one
    assert viewcatalog.read_views("mcp:other/update_issue") == ()  # nor is the same tool on another server
    assert all(key.startswith("mcp:") and "/" in key for key in viewcatalog.CATALOG)
    source = Path(viewcatalog.__file__).read_text(encoding="utf-8")
    assert "import re" not in source and "fnmatch" not in source and "startswith(" not in source
