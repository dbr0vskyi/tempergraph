"""The removal after the session (spec file-removal, FRM-B2 to FRM-B6): a script of the `after` list of the code step
and of a phase removes the file of each marked removal row, before the step's commit and its gate. It starts no
session and no command, passes a file already gone, and records a path it refuses in
`.tempergraph/removal/report.json` (never committed); the gates turn that record into an environmental finding."""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any

from . import specfmt

STATE = Path(".tempergraph") / "removal"
REPORT = STATE / "report.json"


def _plan_text(ctx: Any) -> str:
    """The expanded plan when the run has one, else the plan; empty when neither can be read."""
    artifacts = getattr(ctx, "artifacts", None) or {}
    for unit, key in (("expand", "phases"), ("plan", "plan")):
        got = artifacts.get(unit) if isinstance(artifacts, dict) else None
        rel = got.get(key) if isinstance(got, dict) else None
        if rel:
            try:
                return (Path(ctx.workdir) / str(rel)).read_text(encoding="utf-8")
            except OSError:
                continue
    return ""


def _remove(root: Path, row: Any) -> str:
    """Remove one row's file; the reason it was refused, or an empty string."""
    rel = str(row.file).strip().strip("`")
    target = root / rel
    try:
        inside = target.resolve().is_relative_to(root.resolve())
    except (OSError, RuntimeError, ValueError):
        inside = False
    if not rel or not inside:
        return "the path lies outside the workspace"
    if target.is_dir() and not target.is_symlink():
        return "the path is a folder"
    if not (target.is_file() or target.is_symlink()):
        return ""
    try:
        target.unlink()
    except OSError as exc:
        return f"the file system refused: {exc}"
    return ""


def remove_marked(ctx: Any) -> dict[str, str]:
    """Remove the file of each marked removal row (FRM-B2); a file already gone passes (FRM-B5); a folder, a path
    outside the workspace or a refusal of the file system is left as it was and recorded (FRM-B6)."""
    root = Path(ctx.workdir)
    refused: list[dict[str, str]] = []
    text = _plan_text(ctx)
    if text:
        for row in specfmt.parse_plan(text).rows:
            if row.kind == "remove" and specfmt.DONE_MARK.match(row.completed):
                reason = _remove(root, row)
                if reason:
                    refused.append({"row": row.id, "path": str(row.file).strip().strip("`"), "reason": reason})
    (root / STATE).mkdir(parents=True, exist_ok=True)
    (root / STATE / ".gitignore").write_text("*\n", encoding="utf-8")
    (root / REPORT).write_text(json.dumps({"refused": refused}, indent=2) + "\n", encoding="utf-8")
    return {}


def refused(workdir: Path) -> list[dict[str, str]]:
    """The refused rows the last call recorded (row, path, reason); none when there is no report."""
    try:
        doc = json.loads((Path(workdir) / REPORT).read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return []
    got = doc.get("refused") if isinstance(doc, dict) else None
    return [r for r in got or [] if isinstance(r, dict)]
