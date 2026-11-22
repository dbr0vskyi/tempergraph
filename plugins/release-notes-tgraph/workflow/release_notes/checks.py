"""The model-free checks: the draft gate's four headings, and for both gates the changes since the last tag.

A judge reads files only; it cannot run git. So each check lists the changes since the last tag in its
evidence, which the engine hands the judge as the check's evidence (JDG §2.1). The list is the truth the
judge compares the notes with; the check itself never fails on it.
"""

import contextlib
from pathlib import Path

from tempergraph.api import CheckFinding, CheckResult

HEADINGS = ("# Added", "# Changed", "# Fixed", "# Removed")
MAX_CHANGES = 200


def changes(ctx):
    """`(tag, lines)`: the last tag and the commits since it (`git log <tag>..HEAD --oneline`), or every commit
    when the repository has no tag. Empty when commands cannot run (a context with no `run`)."""
    run = getattr(ctx, "run", None)
    if run is None:
        return "", []
    got = run("git describe --tags --abbrev=0")
    tag = str(got.tail or "").strip().splitlines()[-1].strip() if got.exit_code == 0 and got.tail else ""
    log = run(f"git log {tag}..HEAD --oneline" if tag else "git log --oneline")
    if log.exit_code != 0:
        return tag, []
    text = str(log.tail or "")
    if log.output_path:
        with contextlib.suppress(OSError):
            text = Path(log.output_path).read_text(encoding="utf-8", errors="replace")
    return tag, [ln.strip() for ln in text.splitlines() if ln.strip()][:MAX_CHANGES]


def changes_evidence(ctx):
    tag, lines = changes(ctx)
    if not lines and getattr(ctx, "run", None) is None:
        return ""
    head = f"Changes since the last tag {tag} (git log {tag}..HEAD --oneline):" if tag else \
        "No tag: every commit (git log --oneline):"
    return "\n".join([head, *(f"- {ln}" for ln in lines)] if lines else [head, "- none"])


def draft_check(ctx):
    path = ctx.workdir / "notes.md"
    try:
        lines = [ln.strip() for ln in path.read_text(encoding="utf-8").splitlines()]
    except OSError:
        return CheckResult(result="FAIL", evidence="notes.md is missing",
                           findings=[CheckFinding(status="fail", criterion="rn-sections")])
    found = [h for h in lines if h in HEADINGS]
    listed = changes_evidence(ctx)
    if tuple(found) == HEADINGS:
        return CheckResult(result="PASS", evidence="\n".join(x for x in ("the four headings, in order", listed) if x),
                           findings=[CheckFinding(status="pass", criterion="rn-sections")])
    return CheckResult(result="FAIL", evidence=f"headings found: {', '.join(found) or 'none'}",
                       findings=[CheckFinding(status="fail", criterion="rn-sections")])


def outcome_check(ctx):
    """The outcome gate's own check: no criterion of its own, the change list as the outcome judge's evidence."""
    return CheckResult(result="PASS", evidence=changes_evidence(ctx), findings=[])
