"""Prompt lint (LIF-B7 to LIF-B16, LIF-AC6): model-free, text-style rules over templates, judge briefs and stances,
and the skills and agents a package ships. Part of `validate` (warnings) and shown by `audit` (PRA
`prompt-lint`). The name reader, :func:`names`, is the one the prompt audit and the tool-surface audit
reuse (PRA-AC3).

Rules and codes (LIF-B12): `lint-vague-word`, `lint-self-grading`, `lint-rule-branching`,
`lint-human-wait`, `lint-accepting-brief`, `lint-tool-name-foreign`, `lint-ref-missing`, `lint-oversized`, and
the one error, `lint-skill-undeclared` (LIF-B19): a step prompt names a package skill its step does not declare.
"""

from __future__ import annotations

import contextlib
import re
from collections.abc import Iterator
from dataclasses import dataclass
from pathlib import Path
from typing import Literal

from tempergraph.contracts import TextRef, WorkflowSpec
from tempergraph.executors.capabilities import DECLARED
from tempergraph.model.text import TextUnreadable, load_text, split_judge_file

Role = Literal["step", "judge", "skill", "agent"]

TEMPLATE_LIMIT = 32_000
SKILL_LIMIT = 40_000
CELL_LIMIT = 2_000

VAGUE = ("as appropriate", "as needed", "if necessary", "where relevant", "and so on", "etc.", "appropriately",
         "properly", "reasonable", "sufficiently", "adequate", "nice", "user-friendly", "robust", "high quality",
         "high-quality", "as much as possible", "best possible")
SELF_GRADING = re.compile(r"\b(rate|grade|score|evaluate|assess|judge)\s+(your|its)\s+(own\s+)?(work|answer|output|"
                          r"result|response|quality)|\bself[- ]assess|\bhow confident are you|\bconfirm (that )?you "
                          r"(have|did|met)|\bdeclare (it|the task) (done|complete)", re.I)
BRANCH = re.compile(r"\bif\b[^.\n]{1,160}\b(otherwise|else)\b", re.I)
HUMAN_WAIT = re.compile(r"\b(ask|check with|confirm with|wait for|consult)\s+(the\s+)?(user|person|human|operator|"
                        r"reviewer|me|approval)\b|\bwait until (the )?(user|person)", re.I)
ACCEPTING = re.compile(r"\b(trust|accept|take)\s+(the\s+)?(step'?s|agent'?s|author'?s|worker'?s)\s+(word|claim|"
                       r"report|summary|statement)|\bassume (that )?(the step|it) (is|was|did) (correct|right|done)|"
                       r"\bif the (step|agent) says\b", re.I)
SKILL_REF = re.compile(r"(?:\bskill\s+`([A-Za-z0-9_.:-]+)`|(?<![\w/])/([a-z][a-z0-9-]{2,})(?:\b|$))")
AGENT_REF = re.compile(r"\b(?:sub)?agent\s+`([A-Za-z0-9_.-]+)`", re.I)
FILE_FOLDERS = ("prompts", "judges", "skills", "agents", "lessons")
FILE_REF = re.compile(r"`((?:" + "|".join(FILE_FOLDERS) + r")/[A-Za-z0-9_./-]+)`")
TICKED = re.compile(r"`([A-Za-z_][A-Za-z0-9_]*)`")


@dataclass(frozen=True)
class Names:
    skills: tuple[str, ...]
    agents: tuple[str, ...]
    files: tuple[str, ...]
    tools: tuple[str, ...]  # backticked identifiers that are some executor's tool name


@dataclass(frozen=True)
class LintFinding:
    code: str
    unit: str | None
    where: str  # file path or `inline:<unit>`, with a line when known
    message: str
    severity: Literal["error", "warning"] = "warning"


def _tool_names() -> dict[str, set[str]]:
    """Tool name -> executors whose tool map holds it."""
    out: dict[str, set[str]] = {}
    for name, caps in DECLARED.items():
        for tools in caps.tool_map.values():
            for t in tools:
                if "{" not in t:
                    out.setdefault(t, set()).add(name)
    return out


def names(text: str) -> Names:
    """Everything a model-facing text names: skills, agents, package files, tool names (PRA-B6)."""
    tools = _tool_names()
    skills = [a or b for a, b in SKILL_REF.findall(text)]
    return Names(skills=tuple(dict.fromkeys(skills)), agents=tuple(dict.fromkeys(AGENT_REF.findall(text))),
                 files=tuple(dict.fromkeys(FILE_REF.findall(text))),
                 tools=tuple(dict.fromkeys(t for t in TICKED.findall(text) if t in tools)))


def _line(text: str, pos: int) -> int:
    return text.count("\n", 0, pos) + 1


def _texts(spec: WorkflowSpec) -> Iterator[tuple[str, Role, str, str]]:
    """(unit, role, where, text) for every template, stance and brief, then package skills and agents."""
    for unit in spec.order:
        u = spec.units.get(unit)
        if u is None:
            continue
        if u.step is not None and u.step.prompt != "default":
            src = u.step.prompt
            where = src.path if isinstance(src, TextRef) else f"inline:{unit}"
            with contextlib.suppress(TextUnreadable):  # template-unreadable and PKG text-ref own this
                yield unit, "step", where, load_text(spec, src)
        j = u.gate.judge
        if j is not None:
            stance, brief = j.stance, j.brief
            where = j.file or f"inline:{unit}:judge"
            if j.file and spec.package_root is not None:
                try:
                    stance, brief = split_judge_file(load_text(spec, TextRef(path=j.file)))
                except TextUnreadable:
                    continue
            yield unit, "judge", where, f"{stance}\n\n{brief}"
    root = spec.package_root
    if root is not None:
        for p in sorted((root / "skills").glob("*/SKILL.md")):
            yield None, "skill", p.relative_to(root).as_posix(), p.read_text(encoding="utf-8")  # type: ignore[misc]
        for p in sorted((root / "agents").glob("*.md")):
            yield None, "agent", p.relative_to(root).as_posix(), p.read_text(encoding="utf-8")  # type: ignore[misc]


def _exists(root: Path | None, kind: str, name: str) -> bool:
    if root is None:
        return True  # no package: nothing to resolve against (PRA resolves on the host)
    if kind == "skill":
        return (root / "skills" / name.split(":")[-1] / "SKILL.md").is_file()
    if kind == "agent":
        return (root / "agents" / f"{name}.md").is_file()
    return (root / name).exists()


def _declared_refs(root: Path | None) -> re.Pattern[str] | None:
    """A package path in backticks under a folder of the package's `step_files` (PKG-B13), which must resolve too."""
    from tempergraph.package.manifest import declared_step_files

    folders = sorted({p.split("/", 1)[0] for p in declared_step_files(root) if "/" in p} - set(FILE_FOLDERS))
    folders = [f for f in folders if re.fullmatch(r"[A-Za-z0-9_.-]+", f) and "*" not in f]
    return re.compile(r"`((?:" + "|".join(map(re.escape, folders)) + r")/[A-Za-z0-9_./-]+)`") if folders else None


def lint(spec: WorkflowSpec) -> list[LintFinding]:
    out: list[LintFinding] = []
    root = spec.package_root
    tools = _tool_names()
    seen: set[str] = set()
    declared = _declared_refs(root)
    for unit, role, where, text in _texts(spec):
        key = f"{role}:{where}"
        if key in seen:
            continue  # a file shared by several units is reported once
        seen.add(key)

        def add(code: str, pos: int | None, message: str, unit: str | None = unit, where: str = where,
                text: str = text) -> None:
            out.append(LintFinding(code, unit, f"{where}:{_line(text, pos)}" if pos is not None else where, message))

        low = text.lower()
        if role in ("step", "judge"):
            for word in VAGUE:
                at = low.find(word)
                if at >= 0 and re.match(r"\W|$", low[at + len(word):at + len(word) + 1] or " "):
                    add("lint-vague-word", at, f"vague wording {word!r}: say what to do or what counts, observably")
        if role == "step":
            if m := SELF_GRADING.search(text):
                add("lint-self-grading", m.start(), "the step is asked to grade its own work; the gate's check "
                    "and judge grade it")
            branches = list(BRANCH.finditer(text))
            if len(branches) >= 2:
                add("lint-rule-branching", branches[0].start(), f"{len(branches)} if/otherwise rules: decisions "
                    "a function can make belong in a route or switch, not the prompt")
            if m := HUMAN_WAIT.search(text):
                add("lint-human-wait", m.start(), "a step runs unattended; a person is reached through the "
                    "gate's approval or a pause, never by asking from the step")
            st = spec.units[unit].step if unit else None
            executor = st.executor if st is not None else None
            own = {t for ts in DECLARED.get(executor or spec.default_executor, DECLARED["claude"]).tool_map.values()
                   for t in ts}
            declared_skills = {t.split(":")[-1] for t in ((st.tools or ()) if st is not None else ()) if t.startswith("skill:")}
            for ref in names(text).skills:
                if ref.split(":")[-1] not in declared_skills and root is not None and _exists(root, "skill", ref):
                    out.append(LintFinding("lint-skill-undeclared", unit, f"{where}:{_line(text, text.find(ref))}",
                                           f"the prompt names skill {ref!r}, which the step does not declare as "
                                           "`skill:`; an undeclared skill is denied, so the method would be lost "
                                           "(LIF-B19)", "error"))
            for t in names(text).tools:
                if t not in own:
                    add("lint-tool-name-foreign", text.find(f"`{t}`"), f"`{t}` is a tool name of "
                        f"{', '.join(sorted(tools[t]))}, not of this step's executor; name the capability instead")
        if role == "judge" and (m := ACCEPTING.search(text)):
            add("lint-accepting-brief", m.start(), "the brief tells the judge to accept the step's word; the "
                "judge reads the artifacts, or the criterion is marked `unverified_system`")
        n = names(text)
        files = (*n.files, *(m for m in (declared.findall(text) if declared else []) if m not in n.files))
        for kind, refs in (("skill", n.skills), ("agent", n.agents), ("file", files)):
            for ref in refs:
                if not _exists(root, kind, ref):
                    add("lint-ref-missing", text.find(ref), f"{kind} {ref!r} is not in the package")
        limit = TEMPLATE_LIMIT if role in ("step", "judge") else SKILL_LIMIT
        if len(text) > limit:
            add("lint-oversized", None, f"{len(text)} characters, over {limit}; split it into a core and "
                "references read on demand")
        for i, line in enumerate(text.splitlines(), 1):
            if line.lstrip().startswith("|") and any(len(c) > CELL_LIMIT for c in line.split("|")):
                out.append(LintFinding("lint-oversized", unit, f"{where}:{i}", f"a table cell over {CELL_LIMIT} "
                                       "characters"))
    return out
