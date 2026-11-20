"""The outline script, the route after `draft` and the finalizer: plain functions of their context."""

import re
from pathlib import Path

from tempergraph.api import FinalizerResult

DOC = re.compile(r"[\w./-]+\.md\b")
HEADING = re.compile(r"^#{1,6}\s+\S")


def document(request: str) -> str | None:
    """The document the request names: its first `*.md` path."""
    m = DOC.search(request or "")
    return m.group(0) if m else None


def script_outline(ctx):
    """Write `outline.md`: every heading of the named document, in order. No heading, no outline."""
    name = document(str((ctx.request.get("inputs") or {}).get("request", "")))
    if name is None:
        raise ValueError("the request names no .md document")
    lines = (Path(ctx.workdir) / name).read_text(encoding="utf-8").splitlines()
    heads = [ln.rstrip() for ln in lines if HEADING.match(ln)]
    (Path(ctx.workdir) / "outline.md").write_text(f"<!-- {name} -->\n" + "\n".join(heads) + "\n", encoding="utf-8")
    return {"outline": "outline.md"}


def route_draft(view):
    """A minor rewrite needs no review; a major one goes to `review`."""
    return "finalizer" if view.values.get("size") == "minor" else "review"


def finalize(ctx):
    """Report where the refreshed document is; the run's branch carries it."""
    doc = next((str(a["doc"]) for a in ctx.artifacts.values() if isinstance(a, dict) and a.get("doc")), "")
    return FinalizerResult(outcome="written", reason=f"{doc or 'the document'} refreshed on {ctx.branch or 'the branch'}")
