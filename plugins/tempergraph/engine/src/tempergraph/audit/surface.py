"""The session surface of the tool audit (TSA-B6, TSA-B7, ADR-0052): for every step session and every judge session
the grant, the need and the use of its tools, built once per audit.

The grant comes from the executor's tool map, the declared commands and the manifest; the need is read by prompt
lint's name reader (`audit.prompts.read_names`, PRA-AC3) from the template, brief and criteria, and from the artifact
kinds produced and referenced; the use comes from the recorded tool names and calls of `HistoryFacts`, `None` when
there is no history. A refusal is classed from its tool name and its scrubbed input summary only, as `unclassified`
when none was recorded (TSA-B7). Nothing the model said is read here (TSA-AC3).
"""

from __future__ import annotations

import contextlib
import re
from collections.abc import Collection, Mapping
from dataclasses import dataclass, field
from typing import Any

from tempergraph.audit.history import HistoryFacts
from tempergraph.audit.prompts import read_names
from tempergraph.contracts import Capabilities, TextRef, WorkflowSpec
from tempergraph.executors.capabilities import DECLARED, tool_names
from tempergraph.model.text import TextUnreadable, load_text, split_judge_file

READ_PROGRAMS = ("cat", "head", "tail", "grep", "rg", "find", "ls")
DIR_CHANGE = re.compile(r"^\s*cd\s+\S+\s*(?:&&|;)\s*\S")
OUTSIDE_PATH = re.compile(r"(?:^|\s)(?:/|~/|\.\./|\.\.(?:\s|$))")
WRITE_ARTIFACTS = frozenset({"tracker_issue", "wiki_page", "pull_request"})
JUDGE_VIEW = ("read", "search", "list")  # the read-only view set of a judge without its own `tools` (GRD)
READ_FAMILY = ("read", "search", "list")  # a step that writes a file is implied to look at the workspace
CLASSES = ("shell_for_read", "dir_change_then_command", "outside_workspace", "undeclared_tool", "needed_command")


@dataclass(kw_only=True)
class SessionSurface:
    """TSA-B6: one session's executor, grant, commands, ambient names, need, use, refusals and enforcement."""

    session: str  # `<unit>` or `<unit>:judge`
    unit: str
    role: str  # `step` or `judge`
    executor: str
    granted: dict[str, str] = field(default_factory=dict)  # executor tool name -> capability
    commands: tuple[str, ...] = ()
    ambient: set[str] = field(default_factory=set)
    ambient_runs: dict[str, list[str]] = field(default_factory=dict)  # ambient name -> runs whose start list held it
    needed: dict[str, str] = field(default_factory=dict)  # tool name -> where it was found
    used: dict[str, dict[str, int]] | None = None  # None: no history
    refusals: dict[str, int] | str = field(default_factory=dict)  # per class, or `unclassified` without a journal
    refusal_examples: dict[str, str] = field(default_factory=dict)  # the most common scrubbed summary of each class
    enforced: bool = False
    artifacts_unwritable: list[str] = field(default_factory=list)  # produced kinds with no tool that can write them
    produces: dict[str, str] = field(default_factory=dict)
    capabilities: tuple[str, ...] = ()  # the declared capabilities (step) or the view set (judge)
    known: dict[str, str] = field(default_factory=dict)  # every tool name of the executor's map -> its capability
    text: str = ""


@dataclass(kw_only=True)
class Surface:
    sessions: list[SessionSurface] = field(default_factory=list)
    history: bool = False  # the use of tools was read from runs

    def get(self, session: str) -> SessionSurface | None:
        return next((s for s in self.sessions if s.session == session), None)


def classify_refusal(tool: str, summary: str | None, *, granted: Collection[str], shell: Collection[str],
                     file_tools: bool) -> str:
    """TSA-B7: one class from the tool name and the scrubbed input summary, `unclassified` when none was recorded."""
    if tool not in granted:
        return "undeclared_tool"
    if not summary or not summary.strip():
        return "unclassified"
    if tool in shell:
        if DIR_CHANGE.match(summary):
            return "dir_change_then_command"
        words = summary.split()
        if file_tools and (words[0] in READ_PROGRAMS or summary.lstrip().startswith("sed -n")):
            return "shell_for_read"
    if OUTSIDE_PATH.search(summary):
        return "outside_workspace"
    return "needed_command"


def caps_of(caps: Mapping[str, Capabilities], name: str) -> Capabilities | None:
    return caps.get(name) or DECLARED.get(name)


def step_text(spec: WorkflowSpec, unit: str) -> str:
    st = spec.units[unit].step
    if st is None or st.prompt == "default":
        return ""
    try:
        return load_text(spec, st.prompt)
    except TextUnreadable:
        return ""


def judge_text(spec: WorkflowSpec, unit: str) -> str:
    u = spec.units[unit]
    j = u.gate.judge
    if j is None:
        return ""
    stance, brief = j.stance, j.brief
    if j.file and spec.package_root is not None:
        with contextlib.suppress(TextUnreadable):
            stance, brief = split_judge_file(load_text(spec, TextRef(path=j.file)))
    return "\n\n".join([stance, brief, *(c.text for c in u.gate.criteria)])


def _known(caps: Capabilities) -> dict[str, str]:
    return {n: cap for cap, names in caps.tool_map.items() for n in names if "{" not in n}


def _grant(caps: Capabilities, capabilities: Collection[str]) -> dict[str, str]:
    out: dict[str, str] = {}
    for cap in capabilities:
        for name in tool_names(caps, cap):
            out[name] = cap
    return out


Group = tuple[tuple[str, ...], str, bool]  # (capabilities, where found, listed as needed even when none is granted)


def _need(s: SessionSurface, caps: Capabilities, text: str, where: str, groups: list[Group]) -> None:
    """The need: names the reader finds in the text, then capability groups implied by artifacts and commands. A
    group is met by any one of its capabilities; when none is granted a required group names its first (so the
    matrix shows it missing), an optional one names nothing."""
    mine = {n for names in caps.tool_map.values() for n in names if "{" not in n}
    for name in read_names(text).tools:
        if name in mine:
            s.needed.setdefault(name, where)
    for name in s.granted:
        if name.startswith(("mcp__", "mcp(")) and name in text:
            s.needed.setdefault(name, where)
    for group, why, required in groups:
        held = [n for n, cap in s.granted.items() if cap in group]
        for name in held or ([n for cap in group[:1] for n in tool_names(caps, cap)] if required else []):
            s.needed.setdefault(name, why)


def build_surface(spec: WorkflowSpec, caps: Mapping[str, Capabilities], manifest: Any, facts: HistoryFacts | None, *,
                  executor: str | None = None) -> Surface:
    """TSA-B6: one session per step and per judge. `executor` shows every session on that executor's tool map
    (TSA-B3); a judge on another executor keeps it otherwise (cross-executor judging, ADR-0013)."""
    out = Surface(history=facts is not None and facts.runs > 0)
    for unit in spec.order:
        u = spec.units.get(unit)
        if u is None:
            continue
        st, j = u.step, u.gate.judge
        step_ex = executor or (st.executor if st else None) or spec.default_executor
        if st is not None:
            sc = caps_of(caps, step_ex)
            if sc is not None:
                s = SessionSurface(session=unit, unit=unit, role="step", executor=step_ex,
                                   granted=_grant(sc, st.tools),
                                   commands=tuple(dict.fromkeys((*st.commands, *spec.allow_commands))),
                                   enforced=sc.enforces_step_tools, capabilities=tuple(st.tools), known=_known(sc),
                                   produces={k: str(v) if isinstance(v, str) else "value"
                                             for k, v in st.produces.items()})
                groups: list[Group] = []
                for key, kind in s.produces.items():
                    if kind == "file":
                        groups.append((("edit", "write"), f"artifact {key}", True))
                        groups.append((READ_FAMILY, f"artifact {key}", False))  # writing a file implies looking
                    elif kind in WRITE_ARTIFACTS:
                        can = [c for c in st.tools if c == "shell" or c.startswith("mcp:")]
                        if not can:
                            s.artifacts_unwritable.append(key)
                        groups.append((tuple(can) or ("shell",), f"artifact {key}", True))
                if st.commands:
                    groups.append((("shell",), "commands", True))
                _need(s, sc, step_text(spec, unit), "template", groups)
                out.sessions.append(s)
        if j is not None:
            jex = executor or j.executor or step_ex
            jc = caps_of(caps, jex)
            if jc is not None:
                view = tuple(j.tools) if j.tools is not None else JUDGE_VIEW
                s = SessionSurface(session=f"{unit}:judge", unit=unit, role="judge", executor=jex,
                                   granted=_grant(jc, view), enforced=jc.restricts_judge_tools, capabilities=view,
                                   known=_known(jc))
                refs: list[Group] = [(("read",), f"artifact {k}", True) for k in (*j.references, *j.subject)]
                _need(s, jc, judge_text(spec, unit), "brief", refs)
                out.sessions.append(s)
    if facts is not None and facts.runs:
        for s in out.sessions:
            _use(s, facts)
    return out


def _use(s: SessionSurface, facts: HistoryFacts) -> None:
    """The use of tools and the refusals of the session, from the recorded names and scrubbed summaries."""
    mine = [r for r in facts.sessions if r.unit == s.unit and r.judge == (s.role == "judge")]
    used: dict[str, dict[str, int]] = {}
    refusals: dict[str, int] = {}
    seen: dict[str, dict[str, int]] = {}
    shell = {n for n, cap in s.granted.items() if cap == "shell"}
    file_tools = any(cap in ("read", "search", "list") for cap in s.granted.values())
    for r in mine:
        for name in r.started_tools or ():
            if name not in s.granted:
                s.ambient.add(name)
                runs = s.ambient_runs.setdefault(name, [])
                if r.run not in runs:
                    runs.append(r.run)
        for c in r.calls:
            row = used.setdefault(c.name, {"calls": 0, "ok": 0, "refused": 0, "subagent": 0})
            row["calls"] += 1
            row["ok"] += 1 if c.ok else 0
            row["subagent"] += 1 if c.subagent else 0
        for name, summary in r.denied:
            used.setdefault(name, {"calls": 0, "ok": 0, "refused": 0, "subagent": 0})["refused"] += 1
            klass = classify_refusal(name, summary, granted=s.granted, shell=shell, file_tools=file_tools)
            refusals[klass] = refusals.get(klass, 0) + 1
            if summary:
                seen.setdefault(klass, {})[summary] = seen.get(klass, {}).get(summary, 0) + 1
    s.refusal_examples = {k: max(v, key=lambda x: v[x]) for k, v in seen.items()}
    s.used = used
    s.refusals = "unclassified" if facts.runs and facts.journal_runs == 0 else refusals
    for runs in s.ambient_runs.values():
        runs.sort()
