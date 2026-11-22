"""Which tools an attempt could not reach, their refusal class and the grant that fixes each (RST-B28, RST-B29, RST-B30, TSA-B7).

Release 1 classifies from the refused tool's name only: a denied event carries no input summary, so a refused
shell call is `unclassified` and the pause offers `retry` with feedback rather than an `--allow-command`.
"""

from __future__ import annotations

import re
from collections.abc import Sequence
from typing import Any

from tempergraph.contracts import Capabilities, StepSpec
from tempergraph.executors.capabilities import tool_names


def capability_of(caps: Capabilities, name: str) -> str | None:
    """The engine capability an executor tool name stands for, `mcp:<server>/<tool>` included."""
    for cap, names in caps.tool_map.items():
        if "*" not in cap and name in names:
            return cap
    for tmpl in caps.tool_map.get("mcp:*", ()):
        pattern = re.escape(tmpl).replace(r"\{server\}", r"(?P<server>[^_/()]+)").replace(r"\{tool\}", r"(?P<tool>.+)")
        m = re.fullmatch(pattern, name)
        if m:
            return f"mcp:{m.group('server')}/{m.group('tool')}"
    if name in caps.tool_map.get("skill:*", ()):
        return "skill:*"
    return None


def refused(unit: str, step: StepSpec, caps: Capabilities, denied: Sequence[str],
            tools_at_start: Sequence[str]) -> list[dict[str, Any]]:
    """One entry per refused or missing name: `{name, capability, class, fix}`."""
    out: list[dict[str, Any]] = []
    declared = set(step.tools)
    for name in dict.fromkeys(denied):
        cap = capability_of(caps, name)
        if cap is None or cap == "skill:*" or cap == "shell" or cap in declared:
            out.append({"name": name, "capability": cap, "class": "unclassified",
                        "fix": "retry with --feedback naming the permitted way, or stop"})
        else:
            out.append({"name": name, "capability": cap, "class": "undeclared_tool",
                        "fix": f"--decision retry --grant {unit}={cap}"})
    if tools_at_start:
        start = set(tools_at_start)
        for cap in step.tools:
            names = tool_names(caps, cap)
            if not names or cap.startswith("skill:") and "Skill" in start or set(names) & start:
                continue
            host = (f"configure the MCP server {cap[4:].split('/', 1)[0]!r} on this machine, then "
                    if cap.startswith("mcp:") else "")
            out.append({"name": names[0], "capability": cap, "class": "missing_at_start",
                        "fix": f"{host}--decision retry"})
    return out
