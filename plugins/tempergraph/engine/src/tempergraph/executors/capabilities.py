"""Declared capability sets of the four designed executors (EXI §2, ECC §2.1, EAS, EMA, EAG §2.1).

Release 1 registers `claude` only (ADR-0091); the other three sets are declarations used by the scripted
stand-ins and the conformance suite, so CON-AC-5 and WFM-AC-5 hold against all four before their
adapters ship. A capability resting on an unrun probe is declared false (ADR-0010).
"""

from __future__ import annotations

from tempergraph.contracts import Capabilities

TIERS = frozenset({"small", "medium", "large", "inherit"})

_CLAUDE_TOOLS: dict[str, tuple[str, ...]] = {
    "read": ("Read",), "search": ("Grep",), "list": ("Glob",), "edit": ("Edit",), "write": ("Write",),
    "shell": ("Bash",), "web_fetch": ("WebFetch",), "web_search": ("WebSearch",), "subagent": ("Agent", "Task"),
    "mcp:*": ("mcp__{server}__{tool}",), "skill:*": ("Skill",),
}

CLAUDE = Capabilities(
    name="claude",
    binds_aliases=TIERS,
    families={"small": "anthropic", "medium": "anthropic", "large": "anthropic", "inherit": "anthropic"},
    prompt_off_argv=True, streams_events=True, reports_actions=True, reports_tokens=True, reports_cost=True,
    enforces_step_tools=True, step_allow_rules=True, fresh_session=True,
    restricts_judge_tools=True,
    judge_mcp=False,  # ADR-0091 item 3: no filtering MCP proxy before release 2
    isolates_user_config=False,  # true once P-CC-1 is confirmed (ECC §2.1)
    hosts_authoring_surface=True,
    efforts_uncertain=frozenset({"xhigh", "max"}),  # until live probe P-LAD-1 (LAD §2.6)
    session_options=frozenset({"effort", "cost_cap_usd", "fallback_alias", "turn_cap"}),
    tool_map=_CLAUDE_TOOLS,
)

AGENT_SDK = Capabilities(
    name="agent-sdk",
    binds_aliases=TIERS,
    families={"small": "anthropic", "medium": "anthropic", "large": "anthropic", "inherit": "anthropic"},
    prompt_off_argv=True, streams_events=True, reports_actions=True, reports_tokens=True, reports_cost=True,
    fresh_session=True, enforces_step_tools=True, step_allow_rules=True, judge_mcp=True,
    restricts_judge_tools=True, isolates_user_config=False, hosts_authoring_surface=True,
    efforts_uncertain=frozenset({"xhigh", "max"}),  # until live probe P-LAD-1 (LAD §2.6)
    session_options=frozenset({"effort", "cost_cap_usd", "fallback_alias", "turn_cap"}),
    tool_map=dict(_CLAUDE_TOOLS),
)

MESSAGES_API = Capabilities(
    name="messages-api",
    binds_aliases=TIERS,
    families={"small": "anthropic", "medium": "anthropic", "large": "anthropic", "inherit": "anthropic"},
    prompt_off_argv=True, streams_events=True, reports_actions=True, reports_tokens=True, reports_cost=False,
    fresh_session=True, enforces_step_tools=True, restricts_judge_tools=True, isolates_user_config=True,
    step_allow_rules=True, judge_mcp=True, hosts_authoring_surface=False,
    session_options=frozenset({"effort", "cost_cap_usd", "turn_cap"}),
    tool_map={
        "read": ("read_file",), "search": ("search_files",), "list": ("list_files",), "edit": ("edit_file",),
        "write": ("write_file",), "shell": ("run_command",), "web_fetch": ("web_fetch",),
        "web_search": ("web_search",), "mcp:*": ("mcp__{server}__{tool}",),
    },
)

ANTIGRAVITY = Capabilities(
    name="antigravity",
    binds_aliases=TIERS,
    families={"small": "google", "medium": "google", "large": "google", "inherit": "google"},
    prompt_off_argv=True, streams_events=True, reports_actions=True, reports_tokens=True, reports_cost=False,
    fresh_session=True, isolates_user_config=False, enforces_step_tools=False, judge_mcp=False,
    restricts_judge_tools=False, step_allow_rules=True, hosts_authoring_surface=True,
    efforts=frozenset({"low", "medium", "high"}),
    session_options=frozenset({"effort"}),
    tool_map={
        "read": ("view_file",), "search": ("grep_search",), "list": ("list_dir", "find_by_name"),
        "edit": ("replace_file_content", "multi_replace_file_content"), "write": ("write_to_file",),
        "shell": ("run_command",), "web_fetch": ("read_url_content",), "web_search": ("search_web",),
        "subagent": ("invoke_subagent",), "mcp:*": ("mcp({server}/{tool})",),
    },
)

DECLARED: dict[str, Capabilities] = {c.name: c for c in (CLAUDE, AGENT_SDK, MESSAGES_API, ANTIGRAVITY)}


def tool_names(caps: Capabilities, capability: str) -> tuple[str, ...]:
    """The executor's tool names for one capability, with MCP names filled in."""
    if capability in caps.tool_map:
        return caps.tool_map[capability]
    if capability.startswith("mcp:") and "mcp:*" in caps.tool_map:
        server, tool = capability[4:].split("/", 1)
        return tuple(t.format(server=server, tool=tool) for t in caps.tool_map["mcp:*"])
    if capability.startswith("skill:") and "skill:*" in caps.tool_map:
        return caps.tool_map["skill:*"]
    return ()
