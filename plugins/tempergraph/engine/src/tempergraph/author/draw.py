"""`blueprint draw` (SCF §2.2): the diagram of the throwaway spec plus the outcome, verification and
unverified tables and the defaults the person did not set. Pure renderers; no model draws a diagram."""

from __future__ import annotations

from html import escape
from typing import Any

from tempergraph.author.blueprint import Blueprint, to_spec
from tempergraph.contracts import OutcomeSpec
from tempergraph.model.diagram import diagram_model, to_mermaid
from tempergraph.run.outcome_trust import coverage, trust

DEFAULTS = {"on_fail": "retry", "on_budget_spent": "ask", "approval": False, "retry_budget": 2, "loop_budget": 1}


def _cell(text: Any) -> str:
    return str(text).replace("|", "\\|").replace("\n", " ")


def mermaid(bp: Blueprint, outcome: OutcomeSpec | None = None) -> str:
    spec = to_spec(bp)
    if outcome is not None:
        import dataclasses

        from tempergraph.run.outcome import with_outcome

        spec = with_outcome(dataclasses.replace(spec, outcome=outcome))
    return to_mermaid(diagram_model(spec))


def markdown(bp: Blueprint, outcome: OutcomeSpec | None = None) -> str:
    lines = [f"# {bp.name}", "", "```mermaid", mermaid(bp, outcome).rstrip(), "```", "", "## Units", "",
             "| Unit | Kind | Summary | Produces | Reads | Check | Judge | Sign-off |", "|---|---|---|---|---|---|---|---|"]
    for u in bp.units:
        lines.append(f"| {u.name} | {u.kind} | {_cell(u.summary)} | {', '.join(u.produces)} | {', '.join(u.reads)} | "
                     f"{'yes' if u.check else 'no'} | {'yes' if u.judge else 'no'} | {'yes' if u.signoff else 'no'} |")
    if outcome is not None:
        spec = to_spec(bp)
        lines += ["", "## Outcome", "", _cell(outcome.statement), "", "| Deliverable | Kind | Where |", "|---|---|---|"]
        lines += [f"| {d.get('key', '')} | {d.get('kind', '')} | {_cell(d.get('where', ''))} |"
                  for d in outcome.deliverables] or ["| none | | |"]
        lines += ["", "| Final criterion | Severity | Text |", "|---|---|---|"]
        lines += [f"| {c.id} | {c.severity} | {_cell(c.text)} |" for c in outcome.final]
        lines += ["", "## Verification", "",
                  "| Unit | Criterion | Text | Verified by | Verifier | Source | Trust | Serves |",
                  "|---|---|---|---|---|---|---|---|"]
        rows = [("outcome", c) for c in outcome.final] + [(u, c) for u, io in outcome.intermediate.items()
                                                         for c in io.criteria]
        unverified = []
        for unit, c in rows:
            t = trust(c, unit, None)
            if t == "unverified":
                unverified.append(f"- {c.id} on {unit}: {_cell((c.verifier or {}).get('reason', 'no reason given'))}"
                                  f" (risk: {_cell((c.verifier or {}).get('risk', 'not stated'))})")
            verifier = ", ".join(f"{k}={v}" for k, v in (c.verifier or {}).items() if k != "scale")
            lines.append(f"| {unit} | {c.id} | {_cell(c.text)} | {c.verified_by or ''} | {_cell(verifier)} | "
                         f"{c.source or ''} | {t} | {', '.join(c.serves)} |")
        for cov in coverage(outcome, spec):
            if not cov.covered:
                unverified.append(f"- final criterion {cov.criterion} is not covered (no trusted serving criterion on "
                                  f"{', '.join(cov.missing_units) or 'any unit'})")
        lines += ["", "## Unverified", ""] + (unverified or ["none"])
    unset = []
    for u in bp.units:
        for key in ("on_fail", "on_budget_spent", "approval"):
            if getattr(u, key) is None:
                unset.append(f"- {u.name}.{key}: {DEFAULTS[key]}")
        unset.append(f"- {u.name}.retry_budget: {DEFAULTS['retry_budget']}")
    lines += ["", "## Defaults shown", ""] + unset
    return "\n".join(lines) + "\n"


def svg(bp: Blueprint, outcome: OutcomeSpec | None = None) -> str:
    """Units stacked top to bottom, forward arrows between them, back targets as dashed arcs on the right."""
    names = [u.name for u in bp.units] + (["outcome"] if outcome is not None else []) + ["finalizer"]
    w, h, gap, x = 260, 44, 28, 40
    ys = {n: 20 + i * (h + gap) for i, n in enumerate(names)}
    height = 20 + len(names) * (h + gap)
    parts = [f'<svg xmlns="http://www.w3.org/2000/svg" width="{x + w + 120}" height="{height}" '
             f'font-family="sans-serif" font-size="13">',
             '<defs><marker id="a" markerWidth="8" markerHeight="8" refX="7" refY="4" orient="auto">'
             '<path d="M0,0 L8,4 L0,8 z" fill="#555"/></marker></defs>']
    summary = {u.name: u.summary for u in bp.units}
    approval = {u.name for u in bp.units if u.approval or u.signoff}
    for n in names:
        y = ys[n]
        rx = 22 if n in ("finalizer", "outcome") else 4
        parts.append(f'<rect x="{x}" y="{y}" width="{w}" height="{h}" rx="{rx}" fill="#fff" stroke="#333"/>')
        label = escape(n + (" (approval)" if n in approval else ""))
        parts.append(f'<text x="{x + 10}" y="{y + 18}" font-weight="bold">{label}</text>')
        if summary.get(n):
            parts.append(f'<text x="{x + 10}" y="{y + 35}" fill="#555">{escape(summary[n])}</text>')
    for a, b in zip(names, names[1:], strict=False):
        parts.append(f'<line x1="{x + w / 2}" y1="{ys[a] + h}" x2="{x + w / 2}" y2="{ys[b] - 2}" stroke="#555" '
                     'marker-end="url(#a)"/>')
    for u in bp.units:
        for t in u.back_targets:
            if t in ys:
                y1, y2 = ys[u.name] + h / 2, ys[t] + h / 2
                parts.append(f'<path d="M{x + w},{y1} C{x + w + 90},{y1} {x + w + 90},{y2} {x + w + 2},{y2}" '
                             'fill="none" stroke="#555" stroke-dasharray="5,4" marker-end="url(#a)"/>')
    parts.append("</svg>")
    return "\n".join(parts) + "\n"


def draw(bp: Blueprint, outcome: OutcomeSpec | None, fmt: str) -> str:
    if fmt == "mermaid":
        return mermaid(bp, outcome)
    if fmt == "svg":
        return svg(bp, outcome)
    return markdown(bp, outcome)
