"""How model-facing text is built (PRA-B12 to PRA-B14): size, rendered size, must-read size, prohibitions and reasons,
sentences repeated across files and the share of text under goal branches. Model-free, counted over fixed word lists;
the audit's own rules read these measures and the prompts matrix prints them."""

from __future__ import annotations

import re
from collections.abc import Iterator, Mapping
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

from tempergraph.contracts import TextRef, WorkflowSpec
from tempergraph.model.prompt_lint import FILE_REF
from tempergraph.model.text import TextUnreadable, load_text

# A prohibition tells the session what not to do; a reason says why. Both lists are fixed (PRA-B12).
PROHIBITION = re.compile(r"\b(never|do not|don't|must not|may not|shall not|cannot|can't|is not allowed|are not "
                         r"allowed|forbidden|no longer allowed)\b", re.I)
REASON = re.compile(r"\b(because|since|so that|so the|so a|in order to|otherwise|which means|that way|the reason|"
                    r"this keeps|this stops|this avoids)\b", re.I)
GOAL_BRANCH = re.compile(r"^(?:[-*]\s+|\d+\.\s+|#+\s+)?(?:\*\*)?(if|when|unless|for an?|in (?:the )?\S+ (?:mode|lane))\b",
                         re.I)
SENTENCE_END = re.compile(r"(?<=[.!?])\s+")
MIN_SENTENCE = 40  # shorter sentences ("Do nothing else.") repeat by nature


@dataclass(frozen=True)
class Measures:
    chars: int
    prohibitions: int
    reasons: int
    goal_branch_share: float

    @property
    def prohibitions_per_reason(self) -> float:
        return round(self.prohibitions / max(self.reasons, 1), 2)

    def as_json(self) -> dict[str, Any]:
        return {"chars": self.chars, "prohibitions": self.prohibitions, "reasons": self.reasons,
                "prohibitions_per_reason": self.prohibitions_per_reason, "goal_branch_share": self.goal_branch_share}


def measure(text: str) -> Measures:
    paragraphs = [p for p in re.split(r"\n\s*\n", text) if p.strip()]
    branched = sum(len(p) for p in paragraphs if GOAL_BRANCH.match(p.strip()))
    total = sum(len(p) for p in paragraphs)
    return Measures(chars=len(text), prohibitions=len(PROHIBITION.findall(text)), reasons=len(REASON.findall(text)),
                    goal_branch_share=round(branched / total, 3) if total else 0.0)


def sentences(text: str) -> set[str]:
    """The normalized sentences of a text long enough to count as repeated text (PRA-B13)."""
    out: set[str] = set()
    if text.startswith("---") and (end := text.find("\n---", 3)) > 0:
        text = text[end + 4:]  # a skill's front matter is not text the session follows
    for line in re.split(r"\n\s*\n", text):
        flat = " ".join(line.split())
        for s in SENTENCE_END.split(flat):
            s = s.strip().lstrip("-*0123456789. ").strip().lower()
            if len(s) >= MIN_SENTENCE and not s.startswith(("|", "```", "#")):
                out.add(s)
    return out


@dataclass
class TextFile:
    file: str
    text: str
    used_by: list[str] = field(default_factory=list)  # `unit:role`
    role: str = ""  # step, judge, skill, agent, step_file


def model_facing(spec: WorkflowSpec) -> dict[str, TextFile]:
    """Every model-facing file once: templates, judge files, shipped skills and agents, and each file the package
    declares in `step_files` (PKG-B13), with the units and roles that use it."""
    rows: dict[str, TextFile] = {}

    def add(file: str, unit: str | None, role: str, text: str) -> None:
        row = rows.setdefault(file, TextFile(file=file, text=text, role=role))
        if unit is not None and f"{unit}:{role}" not in row.used_by:
            row.used_by.append(f"{unit}:{role}")

    for unit in spec.order:
        u = spec.units.get(unit)
        if u is None:
            continue
        st = u.step
        if st is not None and st.prompt != "default":
            file = st.prompt.path if isinstance(st.prompt, TextRef) else f"inline:{unit}"
            try:
                add(file, unit, "step", load_text(spec, st.prompt))
            except TextUnreadable:
                add(file, unit, "step", "")
        j = u.gate.judge
        if j is not None:
            if j.file and spec.package_root is not None:
                try:
                    add(j.file, unit, "judge", load_text(spec, TextRef(path=j.file)))
                except TextUnreadable:
                    add(j.file, unit, "judge", "")
            else:
                add(f"inline:{unit}:judge", unit, "judge", f"{j.stance}\n{j.brief}")
    root = spec.package_root
    if root is None:
        return rows
    for p in sorted([*root.glob("skills/*/SKILL.md"), *root.glob("agents/*.md")]):
        add(p.relative_to(root).as_posix(), None, "skill" if p.name == "SKILL.md" else "agent",
            p.read_text(encoding="utf-8"))
    for p in step_file_paths(root):
        rel = p.relative_to(root).as_posix()
        if rel in rows:
            continue
        try:
            add(rel, None, "step_file", p.read_text(encoding="utf-8"))
        except (OSError, UnicodeDecodeError):
            continue
    templates = [(u.split(":")[0], r.text) for r in rows.values() for u in r.used_by if u.endswith(":step")]
    for row in rows.values():
        if row.role == "step_file":
            for unit, text in templates:
                if f"`{row.file}`" in text and f"{unit}:step_file" not in row.used_by:
                    row.used_by.append(f"{unit}:step_file")
    return rows


def step_file_paths(root: Path) -> list[Path]:
    from tempergraph.package.manifest import declared_step_files

    found: dict[Path, None] = {}
    for pattern in declared_step_files(root):
        for p in sorted(root.glob(pattern)):
            if p.is_file() and p.suffix in (".md", ".txt", ".json"):
                found.setdefault(p, None)
    return list(found)


def named_files(text: str, rows: Mapping[str, TextFile]) -> list[str]:
    """The package files a template names in backticks that the audit holds as model-facing text."""
    ticked = set(re.findall(r"`([A-Za-z0-9_./-]+)`", text))
    by_name: dict[str, list[str]] = {}
    for f in rows:
        by_name.setdefault(f.rsplit("/", 1)[-1], []).append(f)
    listed = (set(FILE_REF.findall(text)) | ticked
              | {f for t in ticked if "/" not in t for f in by_name.get(t, ()) if len(by_name[t]) == 1})
    return sorted(f for f in listed if f in rows)


def rendered_size(spec: WorkflowSpec, unit: str, text: str) -> int | None:
    """The characters of the step's prompt as the engine renders it for its first attempt (tools, artifacts and
    criteria appended), with the first start example as the request; None when it cannot be rendered."""
    from tempergraph.executors.capabilities import CLAUDE
    from tempergraph.render.prompt import AttemptContext, render_step

    u = spec.units.get(unit)
    if u is None or u.step is None:
        return None
    example = next(iter(spec.input.examples), "")
    fields: dict[str, str | None] = {"request": example}
    for p in spec.input.parameters:
        fields.setdefault(p.name, p.example or p.name)
    try:
        return len(render_step(unit, u, AttemptContext(template=text, fields=fields), CLAUDE).text)
    except Exception:  # noqa: BLE001 - a template the renderer refuses is reported by validate, not here
        return None


def repeated(rows: Mapping[str, TextFile], min_files: int) -> Iterator[tuple[str, list[str]]]:
    """Each sentence found in at least `min_files` files, with those files (PRA-B13)."""
    where: dict[str, list[str]] = {}
    for row in rows.values():
        for s in sentences(row.text):
            where.setdefault(s, []).append(row.file)
    for s, files in sorted(where.items()):
        if len(files) >= min_files:
            yield s, sorted(files)
