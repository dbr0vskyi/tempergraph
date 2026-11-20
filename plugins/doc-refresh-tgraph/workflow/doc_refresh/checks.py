"""The model-free checks: the outline has headings; the rewrite keeps every outline heading, in order."""

import re

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
    return checks.result([checks.headings_in_order(ctx, "doc", want, "dr-headings")])
