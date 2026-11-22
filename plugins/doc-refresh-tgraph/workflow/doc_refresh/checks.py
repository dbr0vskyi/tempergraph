"""The model-free checks: the outline has headings; the rewrite keeps every outline heading, in order.

A judge reads files only and cannot run `git diff`, so the draft check states which sections changed
against the run's base, as its evidence (live check L-25, 2026-11-21).
"""

import re
from pathlib import Path

from tempergraph.api import CheckFinding, checks

HEADING = re.compile(r"^#{1,6}\s+(\S.*?)\s*$", re.M)


def outline_check(ctx):
    """dr-outline: `outline.md` lists at least one heading."""
    return checks.result([checks.pattern_present(ctx, "outline", "^#", "dr-outline")])


def draft_check(ctx):
    """dr-headings: every heading of `outline.md` is in the document, in the same order."""
    outline = checks.artifact_path(ctx, "outline")
    try:
        want = HEADING.findall(ctx.read_text(outline)) if outline else []
    except (OSError, PermissionError):
        want = []
    if not want:
        return checks.result([CheckFinding(status="fail", criterion="dr-headings", place="outline",
                                           message="the outline is missing or has no headings")])
    found = [checks.headings_in_order(ctx, "doc", want, "dr-headings")]
    return checks.result(found, evidence="\n".join(x for x in (_bad(found), section_evidence(ctx)) if x))


def _bad(found):
    return "; ".join(f"{f.criterion}: {f.message}" for f in found if f.status == "fail") or f"{len(found)} checked"


def sections(text):
    """Heading -> body, in order; text before the first heading is the section `(top)`."""
    out, name, body = {}, "(top)", []
    for line in text.splitlines():
        m = HEADING.match(line)
        if m:
            out[name] = "\n".join(body)
            name, body = m.group(1), []
        else:
            body.append(line)
    out[name] = "\n".join(body)
    return out


def section_changes(before, after):
    """`(changed, added, removed)` section names between two texts of the document."""
    a, b = sections(before), sections(after)
    changed = [k for k in b if k in a and a[k] != b[k]]
    return changed, [k for k in b if k not in a], [k for k in a if k not in b]


def section_evidence(ctx):
    """The sections of the document that changed since the run's base, from `git show <base>:<path>`."""
    path = checks.artifact_path(ctx, "doc")
    base = getattr(getattr(ctx, "git", None), "base", "") or ""
    run = getattr(ctx, "run", None)
    if not path or not base or run is None:
        return ""
    got = run(f"git show {base}:{path}")
    if got.exit_code != 0:
        return f"{path} is new since the run's base"
    try:
        before = Path(got.output_path).read_text(encoding="utf-8", errors="replace") if got.output_path else ""
        after = ctx.read_text(path)
    except (OSError, PermissionError):
        return ""
    before = before or str(got.tail or "")
    changed, added, removed = section_changes(before, after)
    same = [k for k in sections(after) if k not in changed and k not in added]
    return "\n".join([
        f"The check compared {path} with its text at the run's base {base[:12]} (git show), section by section:",
        f"Sections changed: {', '.join(changed) or 'none'}",
        f"Sections byte-for-byte the same as at the base: {', '.join(same) or 'none'}",
        f"Sections added: {', '.join(added) or 'none'}", f"Sections removed: {', '.join(removed) or 'none'}"])


def outcome_check(ctx):
    """The outcome gate's own check: no criterion of its own; the changed sections as the outcome judge's
    evidence for dr-request (no section the request did not name changed)."""
    return checks.result([], evidence=section_evidence(ctx) or "no base to compare with")
