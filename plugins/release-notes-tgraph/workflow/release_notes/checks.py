"""The draft gate's model-free check: the notes carry the template's four headings, in order."""

from tempergraph.api import CheckFinding, CheckResult

HEADINGS = ("# Added", "# Changed", "# Fixed", "# Removed")


def draft_check(ctx):
    path = ctx.workdir / "notes.md"
    try:
        lines = [ln.strip() for ln in path.read_text(encoding="utf-8").splitlines()]
    except OSError:
        return CheckResult(result="FAIL", evidence="notes.md is missing",
                           findings=[CheckFinding(status="fail", criterion="rn-sections")])
    found = [h for h in lines if h in HEADINGS]
    if tuple(found) == HEADINGS:
        return CheckResult(result="PASS", evidence="the four headings, in order",
                           findings=[CheckFinding(status="pass", criterion="rn-sections")])
    return CheckResult(result="FAIL", evidence=f"headings found: {', '.join(found) or 'none'}",
                       findings=[CheckFinding(status="fail", criterion="rn-sections")])
