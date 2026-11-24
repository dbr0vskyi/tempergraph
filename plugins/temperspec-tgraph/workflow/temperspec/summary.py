"""The pull request's description: what the owner has to read, built from the run's files with no model.

It lists the task's acceptance criteria, the owner decisions of the triage note with the default the run took for
each (`Assumptions to confirm`, never clipped, present only when the note has an `Owner decisions` section), the
behaviours and criteria that changed in each spec, the decisions and open questions of the hand-off, and the
deviations of the code report. Everything else a run writes is a
hand-over between steps and is named only by its path."""

from __future__ import annotations

import re
from pathlib import Path
from typing import Any

from tempergraph.api import checks

from . import specfmt as fmt

MAX_LINES = 14
SAFE_REF = re.compile(r"^[A-Za-z0-9][A-Za-z0-9._/-]{0,200}$")


def _base(ctx: Any) -> str:
    """What the run's branch is compared with: the base commit when the engine gave one, else the base branch."""
    base = str(getattr(ctx.git, "base", "") or getattr(ctx, "base", "") or "")
    return base if SAFE_REF.match(base) else ""


def _output(ctx: Any, command: str) -> str | None:
    run = ctx.run(command)
    if run.not_started or run.exit_code != 0:
        return None
    try:
        return Path(run.output_path).read_text(encoding="utf-8", errors="replace")
    except OSError:
        return str(run.tail or "")


def _changed(ctx: Any) -> list[str]:
    """Paths the run's commits changed. The last stage's own git facts hold uncommitted changes only."""
    paths = list(ctx.git.changed_paths)
    base = _base(ctx)
    if not paths and base:
        paths = [ln.strip() for ln in (_output(ctx, f"git diff --name-only {base}...HEAD") or "").splitlines()
                 if ln.strip()]
    return [p for p in paths if not p.startswith((".claude/", ".tempergraph/"))]


def _text(ctx: Any, key: str) -> tuple[str, str]:
    path = checks.artifact_path(ctx, key)
    if not path:
        return "", ""
    try:
        return (Path(ctx.workdir) / path).read_text(encoding="utf-8", errors="replace"), path
    except OSError:
        return "", path


def _section(text: str, name: str) -> list[str]:
    low = {k.lower(): v for k, v in fmt.sections(text).items()}
    lines = [ln.rstrip() for ln in low.get(name.lower(), []) if ln.strip()]
    return [] if len(lines) == 1 and lines[0].strip("-* .").lower() == "none" else lines


def _spec_changes(ctx: Any, path: str) -> list[str]:
    """The behaviour and criterion lines a spec gained or lost since the run's base."""
    base = _base(ctx)
    diff = _output(ctx, f"git diff --unified=0 {base}...HEAD -- {path}") if base and SAFE_REF.match(path) else None
    if diff is None:
        return []
    out = []
    for line in diff.splitlines():
        if line[:1] not in "+-" or line.startswith(("+++", "---")):
            continue
        body = line[1:].strip()
        if (fmt.BEHAVIOUR_HEAD.match(body) or fmt.BEHAVIOUR_LINE.match(body) or fmt.CRITERION_LINE.match(line[1:])):
            out.append(f"  - {'added' if line[0] == '+' else 'removed'}: {body.lstrip('#- ').strip()[:220]}")
    return out


def _assumptions(note_text: str) -> list[str]:
    """The owner decisions of the triage note as the defaults the run took, none clipped: nothing when the note has no
    `Owner decisions` section (a run on `blocking`), one line when the section says `None`, else one item each."""
    note = fmt.parse_triage(note_text)
    if not note.owner_section:
        return []
    if not note.owners:
        return ["- The run took no default: the triage note lists no owner decision."] if note.owner_none else []
    return [f"- {e.gap}: {e.question or '(no question written)'} Default: {e.default_text or e.default or '(none)'}. "
            f"If wrong: {e.cost or '(not stated)'}" for e in note.owners]


def build(ctx: Any) -> str:
    """The description, as Markdown."""
    note_text, note_path = _text(ctx, "triage_note")
    handoff, handoff_path = _text(ctx, "handoff")
    report, report_path = _text(ctx, "code_report")
    route = next((str(v["route"]) for v in (ctx.values or {}).values() if isinstance(v, dict) and "route" in v), "")
    changed = _changed(ctx)
    specs = [p for p in changed if p.endswith(".spec.md")]
    records = [p for p in changed if p.endswith(".adr.md")]
    code = [p for p in changed if not p.endswith(".md")]
    lane = {"quick": "quick (no spec changed)", "plan": "planned, no gap in the specs",
            "discovery": "discovery, plan and code", "discovery-only": "documents only"}.get(route, route or "?")

    out = [f"## temperspec run `{ctx.task_id}`", "", f"Lane: {lane}.", "", "### Acceptance criteria of the task", ""]
    out += _section(note_text, "Acceptance criteria")[:MAX_LINES] or ["- (the triage note could not be read)"]
    if assumed := _assumptions(note_text):
        out += ["", "### Assumptions to confirm", ""] + assumed
    out += ["", "### Read these", ""]
    if specs or records:
        for path in specs:
            lines = _spec_changes(ctx, path)
            out.append(f"- `{path}`" + ("" if lines else ": changed, with no behaviour or criterion line changed"))
            out += lines[:MAX_LINES]
        out += [f"- `{path}`: decision record" for path in records]
    else:
        out.append("- No spec and no decision record changed.")
    for title, lines in (("Decisions taken", _section(handoff, "Decisions")),
                         ("Open questions", _section(handoff, "Open questions")),
                         ("Deviations from the plan", _section(report, "Deviations"))):
        if lines:
            out += ["", f"### {title}", ""] + lines[:MAX_LINES]
    out += ["", "### The change", "", f"- {len(code)} code and test files, {len(specs)} specs, "
            f"{len(records)} decision records."]
    out += [ln for ln in _section(report, "Verification")[:6]]
    notes = [p for p in (note_path, handoff_path, checks.artifact_path(ctx, "phases")
                         or checks.artifact_path(ctx, "plan"), report_path) if p]
    if notes:
        out += ["", "Hand-overs between steps, not needed for review: " + ", ".join(f"`{p}`" for p in notes) + "."]
    out += ["", "The gates of the run checked this change; a person has not yet read it."]
    return "\n".join(out) + "\n"
