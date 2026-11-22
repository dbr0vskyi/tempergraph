"""The judge view catalog for MCP tools (GRD-B1, GRD-B7, GRD-AC6, ADR a-judge-reaches-an-mcp-server-only-through-the-engines-filtering-proxy).

A constant table keyed by the full tool name `mcp:<server>/<tool>`: a tracker's create or update tool maps to its
`get_issue` read view, a wiki's update tool to its `get_page` read view, and a read view maps to itself, so a step
that declares one gives its judge that same view. Nothing is inferred from a name pattern or an MCP hint; a tool
the table does not list has no view, and its judge gets nothing of it. Add newer tool names beside the old ones,
never renaming, so a workflow pinned to an older server keeps its views.

The names under `tracker` and `wiki` are the generic servers of the specs' scenarios and of the stand-in servers
the tests use.
"""

from __future__ import annotations

CATALOG: dict[str, tuple[str, ...]] = {
    "mcp:tracker/create_issue": ("mcp:tracker/get_issue",),
    "mcp:tracker/update_issue": ("mcp:tracker/get_issue",),
    "mcp:tracker/get_issue": ("mcp:tracker/get_issue",),
    "mcp:tracker/get_comments": ("mcp:tracker/get_comments",),
    "mcp:wiki/update_page": ("mcp:wiki/get_page",),
    "mcp:wiki/get_page": ("mcp:wiki/get_page",),
}


def read_views(tool: str) -> tuple[str, ...]:
    """The read views of one declared MCP tool, or nothing when the catalog does not list it."""
    return CATALOG.get(tool, ())
