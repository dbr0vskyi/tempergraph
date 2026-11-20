"""The one renderer for every step prompt on every executor (PRM §2).

``executor`` selects only the tool names written in the tools block; nothing else differs (PRM-AC-2).
The step is shown its criteria texts as the target and never asked to grade itself (PRM-B2). Everything
after the template is appended verbatim, never format-processed (PRM-B4).
"""

from __future__ import annotations

from collections.abc import Mapping
from dataclasses import dataclass, field

from tempergraph.contracts import Capabilities, UnitSpec, ValueKind
from tempergraph.executors.capabilities import tool_names
from tempergraph.render.template import render
from tempergraph.security.scrub import head_tail

PREVIOUS_REPORT_LIMIT = 3000
CHANGED_PATHS_LIMIT = 20


@dataclass(frozen=True, kw_only=True)
class Blocker:
    criterion: str
    place: str = ""
    problem: str = ""
    fix: str = ""


@dataclass(frozen=True, kw_only=True)
class AttemptContext:
    template: str
    fields: Mapping[str, str | None]
    attempt: int = 1
    retry: bool = False
    blockers: tuple[Blocker, ...] = ()
    check_evidence: str = ""
    previous_report: str = ""
    changed_paths: tuple[str, ...] = ()
    paths_only: bool = False  # after a timeout, infra failure or cut-off (PRM §2.1)
    notes: tuple[str, ...] = ()  # unmet warnings of the last pass
    visit_reason: str = ""
    visit_from: str = ""
    feedback: str = ""
    rulings: tuple[str, ...] = ()
    upstream_targets: tuple[str, ...] = ()
    grants: tuple[str, ...] = ()  # capabilities granted for this run (RST §2.8)


@dataclass
class RenderedPrompt:
    text: str
    missing_fields: list[str]
    sections: list[str] = field(default_factory=list)


def render_step(unit: str, spec: UnitSpec, ctx: AttemptContext, caps: Capabilities) -> RenderedPrompt:
    step = spec.step
    assert step is not None
    body, missing = render(ctx.template, ctx.fields)
    parts = [body.rstrip()]
    sections = ["template"]

    def add(name: str, text: str) -> None:
        parts.append(text)
        sections.append(name)

    if step.commands:
        add("commands", "## Commands you may run\n" + "\n".join(f"- `{c}`" for c in step.commands))
    tools = list(dict.fromkeys(tuple(step.tools) + ctx.grants))
    if tools:
        add("tools", _tools_block(tools, caps))
    if step.produces:
        add("artifacts", _artifact_block(step.produces))
    if spec.gate.criteria:
        lines = [f"{i}. {c.text}" for i, c in enumerate(spec.gate.criteria, 1)]
        add("criteria", "## How this output will be judged\nAn independent reviewer will check:\n" + "\n".join(lines))
    blocked = ("## If you are blocked\nIf only a person can unblock this work, end with one line:\n"
               "`BLOCKED: <what a person must decide or provide>`")
    if ctx.upstream_targets:
        names = ", ".join(f"`{t}`" for t in ctx.upstream_targets)
        blocked += (f"\nIf an earlier unit's output ({names}) has a defect you cannot work around, end with one line:\n"
                    "`UPSTREAM <unit>: <defect>`")
    add("blocked", blocked)
    if ctx.notes:
        add("notes", "## Notes from the previous review\n" + "\n".join(f"- {n}" for n in ctx.notes))
    if ctx.visit_reason:
        who = f" (sent back by `{ctx.visit_from}`)" if ctx.visit_from else ""
        add("visit_reason", f"## Why this unit runs again{who}\nEvery point of this reason must be addressed:\n"
                            f"{ctx.visit_reason}")
    if ctx.retry:
        add("retry", _retry_block(ctx))
    if ctx.feedback:
        add("feedback", "## Feedback from a person\n" + ctx.feedback)
    if ctx.rulings:
        add("rulings", "## Rulings from a person (apply on every attempt)\n" + "\n".join(f"- {r}" for r in ctx.rulings))
    return RenderedPrompt(text="\n\n".join(parts) + "\n", missing_fields=missing, sections=sections)


def _tools_block(tools: list[str], caps: Capabilities) -> str:
    names: list[str] = []
    for t in tools:
        names.extend(tool_names(caps, t))
    lines = ["## Tools for this step", "Tools: " + ", ".join(f"`{n}`" for n in dict.fromkeys(names)) + ".",
             "Stay in the working directory."]
    file_tools = {"read", "search", "list", "edit", "write"} & set(tools)
    if "shell" in tools:
        if file_tools:
            lines.append("Prefer the file tools over the shell when both can do the job.")
        lines.append("Run git without a leading change of directory.")
        lines.append("Run only the listed commands.")
    else:
        lines.append("There is no shell in this step.")
    return "\n".join(lines)


def _artifact_block(produces: Mapping[str, object]) -> str:
    lines = ["## What to end with", "End your answer with one line per output:"]
    for key, kind in produces.items():
        if isinstance(kind, ValueKind):
            desc = "one line"
            if kind.choices:
                desc += " (one of: " + ", ".join(kind.choices) + ")"
            lines.append(f"`ARTIFACT {key}: <{desc}>`")
        else:
            lines.append(f"`ARTIFACT {key}: <{kind}>`")
    return "\n".join(lines)


def _retry_block(ctx: AttemptContext) -> str:
    lines = ["## The previous attempt was not accepted"]
    if not ctx.paths_only:
        for b in ctx.blockers:
            row = f"- {b.criterion}"
            if b.place:
                row += f" — at {b.place}"
            if b.problem:
                row += f": {b.problem}"
            if b.fix:
                row += f" Fix: {b.fix}"
            lines.append(row)
        if ctx.check_evidence:
            lines.append("Check evidence:\n" + head_tail(ctx.check_evidence, 2000))
        if ctx.previous_report:
            lines.append("What the previous attempt reported (a claim, not a fact):\n"
                         + head_tail(ctx.previous_report, PREVIOUS_REPORT_LIMIT))
    else:
        lines.append("The previous attempt ended before it finished.")
    if ctx.changed_paths:
        paths = list(ctx.changed_paths)[:CHANGED_PATHS_LIMIT]
        lines.append("Paths changed since it began:\n" + "\n".join(f"- {p}" for p in paths))
    return "\n".join(lines)
