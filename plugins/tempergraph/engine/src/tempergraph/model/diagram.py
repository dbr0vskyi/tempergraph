"""The diagram model (LIF-B7 to LIF-B16): versioned JSON with a digest, generated from the spec, verified against the
compiled graph (CMP-B6, CMP-AC4). Renderers are pure; digests, not bytes, are compared (LIF-B3).
"""

from __future__ import annotations

import hashlib
import json
from typing import Any

from tempergraph.constants import SCHEMA
from tempergraph.contracts import WorkflowSpec
from tempergraph.model import flow


def diagram_model(spec: WorkflowSpec) -> dict[str, Any]:
    order = flow.effective_order(spec)
    nodes: list[str] = []
    edges: list[list[str]] = []
    units: list[dict[str, Any]] = []
    for unit in order:
        step, judge, gate, human = flow.node_names(unit)
        nodes += [step, judge, gate, human]
        edges += [[step, judge, "next"], [judge, gate, "next"]]
        s = flow.successors(spec, unit)
        for token, targets in s.by_token().items():
            for t in targets:
                edges.append([gate, t, token])
        fb = flow.fallback_node(spec, unit)
        if fb:
            edges.append([gate, fb, "FALLBACK"])
        dl = flow.deadline_node(spec, unit)
        for t in flow.human_targets(spec, unit):
            edges.append([human, t, "DEADLINE" if t == dl and t not in s.proceed else "decision"])
        u = spec.units.get(unit)
        if u is not None and u.kind == "parallel":  # the fork to every branch and the engine-owned join
            fork = flow.fork_node(unit)
            nodes.append(fork)
            for b in u.branches:
                nodes.append(flow.done_node(b))
                edges += [[fork, flow.step_node(b), "fork"], [flow.done_node(b), step, "join"]]
        if u is not None and u.council is not None:  # CMP-B16: a council is one box of the unit's four nodes, its mode named, no member count
            summary = f"{u.council.mode} council"
        else:
            summary = (u.step.summary if u is not None and u.step is not None else "") if u else "outcome gate"
        entry: dict[str, Any] = {
            "name": unit,
            "kind": u.kind if u is not None else "outcome",
            "summary": summary,
            "approval": bool(u.gate.approval) if u is not None else False,
        }
        if flow.is_contest(spec, unit):  # CMP-B16: a contest is one unit, drawn with its slot count
            entry["slots"] = len(flow.slot_names(spec, unit))
        units.append(entry)
    nodes.append(flow.FINALIZER)
    edges.append([flow.FINALIZER, flow.END, "next"])
    edges.append(["__start__", flow.entry_node(spec, order[0]), "next"])
    shape = {"nodes": sorted(nodes), "edges": sorted({(a, b) for a, b, _ in edges})}
    digest = hashlib.sha256(json.dumps(shape, sort_keys=True).encode()).hexdigest()
    return {
        "schema_version": SCHEMA["diagram_model"],
        "workflow": spec.name,
        "units": units,
        "nodes": nodes,
        "edges": edges,
        "digest": digest,
    }


def edge_set(model: dict[str, Any]) -> set[tuple[str, str]]:
    return {(a, b) for a, b, _ in model["edges"]}


def to_mermaid(model: dict[str, Any]) -> str:
    """Draw one box per unit, with its routing edges between units (counts and words only)."""
    lines = ["flowchart TD", "  start((start))"]
    ids = {u["name"]: f"u{i}" for i, u in enumerate(model["units"])}
    ov = model.get("overlay") or {}
    for u in model["units"]:
        label = u["name"] + (f"<br/>{u['summary']}" if u["summary"] else "") + (" ✋" if u["approval"] else "")
        if u.get("slots"):  # a contest: its slot count beside the unit's name (CMP-B16)
            label += f"<br/>{u['slots']} slots"
        o = (ov.get("units") or {}).get(u["name"])
        if o:  # the run overlay (OBS-B15): counts and engine words only
            verdicts = ", ".join(f"{k} {v}" for k, v in o["verdicts"].items())
            label += f"<br/>visits {o['visits']} · sessions {o['sessions']}" + (f" · {verdicts}" if verdicts else "")
        lines.append(f'  {ids[u["name"]]}["{label}"]')
    lines.append("  fin([finalizer])")
    lines.append("  stop((end))")
    for a, b, _ in model["edges"]:
        if a == "__start__":
            entry = [e.split(".")[0] for x, e, t in model["edges"] if x == b and t == "fork"] or [b.split(".")[0]]
            lines += [f"  start --> {ids[name]}" for name in entry if name in ids]
    seen: set[tuple[str, str, str]] = set()
    taken: dict[tuple[str, str, str], int] = {}
    for a, b, token, n in ov.get("edges") or []:
        dst_unit = "fin" if b == flow.FINALIZER.split(".")[0] else b
        taken[(a, dst_unit, token)] = taken.get((a, dst_unit, token), 0) + n
    forks: dict[str, list[str]] = {a: [] for a, _, t in model["edges"] if t == "fork"}
    for a, b, token in model["edges"]:
        if token == "fork":
            forks[a].append(b.split(".")[0])
    joins = {a: b.split(".")[0] for a, b, t in model["edges"] if t == "join"}
    drawn = {"PROCEED": "-->", "BACK": "-.->|back|", "FALLBACK": "-.->|fallback|", "DEADLINE": "-.->|deadline|"}
    for a, b, token in model["edges"]:
        src = a.split(".")[0]
        if (a.endswith(".gate") and token in ("PROCEED", "BACK", "FALLBACK")) or token == "DEADLINE":
            # a block is entered at every branch, and a branch's pass goes to its join
            names = forks[b] if b in forks else [joins[b]] if b in joins else [b.split(".")[0]]
            for name in names:
                dst = "fin" if b == flow.FINALIZER else ids.get(name)
                if dst is None:
                    continue
                key = (ids[src], dst, token)
                if key in seen:
                    continue
                seen.add(key)
                n = taken.pop((src, "fin" if b == flow.FINALIZER else b.split(".")[0], token), 0)
                mark = f" ×{n}" if n else ""
                arrow = (f"-->|{mark.strip()}|" if n else "-->") if token == "PROCEED" else \
                    drawn[token].replace("|", f"|{mark.strip()} " if n else "|", 1) if n else drawn[token]
                lines.append(f"  {ids[src]} {arrow} {dst}")
    for (src, dst_unit, token), n in sorted(taken.items()):  # taken routes the unit boxes do not draw
        dst = "fin" if dst_unit in ("fin", "end") else ids.get(dst_unit)
        if src in ids and dst is not None:
            lines.append(f"  {ids[src]} -.->|{token.lower()} ×{n}| {dst}")
    lines.append("  fin --> stop")
    return "\n".join(lines) + "\n"


def to_svg(model: dict[str, Any]) -> str:
    """The same boxes and routing edges as :func:`to_mermaid`, as one standalone SVG: units top to bottom, forward
    edges on the left, back, fallback and deadline edges dashed on the right; with an overlay, each box carries the
    counts the overlay holds for its unit and nothing else (OBS-B15)."""
    from html import escape

    names = [u["name"] for u in model["units"]] + ["finalizer"]
    w, h, gap, x = 300, 58, 30, 70
    ys = {n: 20 + i * (h + gap) for i, n in enumerate(names)}
    height = 20 + len(names) * (h + gap)
    ov = (model.get("overlay") or {}).get("units") or {}
    parts = [f'<svg xmlns="http://www.w3.org/2000/svg" width="{x + w + 140}" height="{height}" '
             'font-family="sans-serif" font-size="13">',
             '<defs><marker id="a" markerWidth="8" markerHeight="8" refX="7" refY="4" orient="auto">'
             '<path d="M0,0 L8,4 L0,8 z" fill="#555"/></marker></defs>']
    for u in model["units"]:
        y = ys[u["name"]]
        parts.append(f'<rect x="{x}" y="{y}" width="{w}" height="{h}" rx="4" fill="#fff" stroke="#333"/>')
        label = u["name"] + (" (approval)" if u["approval"] else "") + (f" · {u['slots']} slots" if u.get("slots")
                                                                        else "")
        parts.append(f'<text x="{x + 10}" y="{y + 18}" font-weight="bold">{escape(label)}</text>')
        if u["summary"]:
            parts.append(f'<text x="{x + 10}" y="{y + 34}" fill="#555">{escape(u["summary"])}</text>')
        o = ov.get(u["name"])
        if o:
            verdicts = ", ".join(f"{k} {v}" for k, v in o["verdicts"].items())
            line = f"visits {o['visits']} · sessions {o['sessions']}" + (f" · {verdicts}" if verdicts else "")
            parts.append(f'<text x="{x + 10}" y="{y + 50}" fill="#264">{escape(line)}</text>')
    fy = ys["finalizer"]
    parts.append(f'<rect x="{x}" y="{fy}" width="{w}" height="{h}" rx="22" fill="#fff" stroke="#333"/>')
    parts.append(f'<text x="{x + 10}" y="{fy + 18}" font-weight="bold">finalizer</text>')
    seen: set[tuple[str, str, str]] = set()
    for a, b, token in model["edges"]:
        if not ((a.endswith(".gate") and token in ("PROCEED", "BACK", "FALLBACK")) or token == "DEADLINE"):
            continue
        src, dst = a.split(".")[0], "finalizer" if b == flow.FINALIZER else b.split(".")[0]
        if src not in ys or dst not in ys or (src, dst, token) in seen:
            continue
        seen.add((src, dst, token))
        y1, y2 = ys[src], ys[dst]
        if token == "PROCEED" and y2 > y1:
            if y2 == y1 + h + gap:
                parts.append(f'<line x1="{x + w / 2}" y1="{y1 + h}" x2="{x + w / 2}" y2="{y2 - 2}" stroke="#555" '
                             'marker-end="url(#a)"/>')
            else:
                parts.append(f'<path d="M{x},{y1 + h / 2} C{x - 60},{y1 + h / 2} {x - 60},{y2 + h / 2} '
                             f'{x - 2},{y2 + h / 2}" fill="none" stroke="#555" marker-end="url(#a)"/>')
        else:
            word = {"BACK": "back", "FALLBACK": "fallback", "DEADLINE": "deadline"}.get(token, token.lower())
            c = x + w + 90
            parts.append(f'<path d="M{x + w},{y1 + h / 2} C{c},{y1 + h / 2} {c},{y2 + h / 2} {x + w + 2},{y2 + h / 2}" '
                         'fill="none" stroke="#555" stroke-dasharray="5,4" marker-end="url(#a)"/>')
            parts.append(f'<text x="{c - 20}" y="{(y1 + y2 + h) / 2}" fill="#555" font-size="11">{word}</text>')
    parts.append("</svg>")
    return "\n".join(parts) + "\n"
