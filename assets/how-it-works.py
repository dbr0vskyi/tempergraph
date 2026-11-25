"""Draw the README flow diagram: python assets/how-it-works.py assets

Writes how-it-works-light.svg and how-it-works-dark.svg. Every edge cites the spec behaviour it shows;
change the diagram here and in step with specs `compiler-and-flow` CMP, 05 JDG, 07 HUM, 08 BUD and 90 OUT.
"""
import sys
from pathlib import Path

FONT = '-apple-system,BlinkMacSystemFont,"Segoe UI",Helvetica,Arial,sans-serif'
THEMES = {
    "light": dict(text="#1f2328", sub="#59636e", box="#ffffff", line="#8c959f"),
    "dark": dict(text="#e6edf3", sub="#9198a1", box="#161b22", line="#6e7681"),
}
STRAW, BRONZE, PURPLE, BLUE, EMBER, STEEL = "#E3B04B", "#C9773A", "#8A5CB0", "#4A7FC1", "#E5602D", "#7D8EA0"

W, H = 1110, 500
Y, BH = 150, 56          # main row top and box height
CY = Y + BH / 2
BOT = Y + BH

# name: (x, width, title, subtitle, colour, dashed)
BOXES = {
    "outcome_def": (16, 130, "Good outcome", "criteria, verifiers", STRAW, False),
    "step": (186, 112, "Step", "script or model", STEEL, False),
    "checks": (342, 112, "Checks", "deterministic", BRONZE, False),
    "judge": (498, 112, "Judge", "independent", PURPLE, False),
    "gate": (660, 120, "Gate", "budgets, routes", BLUE, False),
    "ogate": (836, 140, "Outcome gate", "final criteria", BLUE, False),
    "done": (1020, 74, "Done", "", BLUE, False),
}
PERSON = (560, 340, 230, "Person decides", "proceed · retry · back · rewind · stop", EMBER, False)
SELF = (820, 430, 230, "Self-improvement", "issues · proposals · trials", STEEL, True)


def cx(name):
    x, w, *_ = BOXES[name]
    return x + w / 2


def right(name):
    x, w, *_ = BOXES[name]
    return x + w


def box(x, y, w, title, sub, colour, dashed, c):
    dash = ' stroke-dasharray="6 5"' if dashed else ""
    ty = y + 24 if sub else y + 33
    out = [f'<rect x="{x}" y="{y}" width="{w}" height="{BH}" rx="10" fill="{c["box"]}" stroke="{colour}" stroke-width="2"{dash}/>',
           f'<rect x="{x}" y="{y + 10}" width="4" height="36" rx="2" fill="{colour}"/>',
           f'<text x="{x + w / 2}" y="{ty}" text-anchor="middle" class="t">{title}</text>']
    if sub:
        out.append(f'<text x="{x + w / 2}" y="{y + 42}" text-anchor="middle" class="s">{sub}</text>')
    return out


def arrow(d, dashed=False):
    dash = ' stroke-dasharray="5 5"' if dashed else ""
    return f'<path d="{d}" fill="none" stroke="{{line}}" stroke-width="1.8"{dash} marker-end="url(#a)"/>'


def label(x, y, text, anchor="middle"):
    return f'<text x="{x}" y="{y}" text-anchor="{anchor}" class="l">{text}</text>'


def svg(theme):
    c = THEMES[theme]
    parts = []
    for name, (x, w, t, s, col, dsh) in BOXES.items():
        parts += box(x, Y, w, t, s, col, dsh, c)
    px, py, pw, pt, ps, pc, pd = PERSON
    parts += box(px, py, pw, pt, ps, pc, pd, c)
    sx, sy, sw, st, ss, sc, sd = SELF
    parts += box(sx, sy, sw, st, ss, sc, sd, c)

    a = []
    # main row
    order = ["outcome_def", "step", "checks", "judge", "gate", "ogate", "done"]
    words = {"checks": "pass", "judge": "verdict", "gate": "pass", "ogate": "met"}
    for left, rgt in zip(order, order[1:]):
        x1, x2 = right(left), BOXES[rgt][0]
        a.append(arrow(f"M{x1} {CY} H{x2 - 4}"))
        if left in words:
            a.append(label((x1 + x2) / 2, CY - 8, words[left]))
    # check FAIL skips the judge and goes to the gate as RETRY (JDG-B1)
    gx = BOXES["gate"][0]
    a.append(arrow(f"M{cx('checks')} {BOT} C{cx('checks')} {BOT + 46}, {gx + 22} {BOT + 46}, {gx + 22} {BOT + 4}"))
    a.append(label((cx('checks') + gx + 22) / 2, BOT + 52, "fail: no judge call"))
    # gate loops back to the step (CMP-B1, CMP-B12, BUD-B8)
    g = cx("gate")
    st = BOXES["step"][0]
    a.append(arrow(f"M{g - 30} {Y} C{g - 30} {Y - 44}, {st + 76} {Y - 44}, {st + 76} {Y - 4}"))
    a.append(label((g - 30 + st + 76) / 2, Y - 40, "retry with the findings, or back to an earlier step (budget left)"))
    a.append(arrow(f"M{g + 10} {Y} C{g + 10} {Y - 104}, {st + 50} {Y - 104}, {st + 50} {Y - 4}"))
    a.append(label((g + 10 + st + 50) / 2, Y - 85, "pass: next step"))
    # outcome gate sends the run back to the step that serves the failed criterion (OUT-B3, OUT-B16)
    o = cx("ogate")
    a.append(arrow(f"M{o} {Y} C{o} {Y - 170}, {st + 24} {Y - 170}, {st + 24} {Y - 4}"))
    a.append(label((o + st + 24) / 2, Y - 133, "unmet: back to the step that serves the criterion"))
    # pauses: the gate, never the judge, routes to the human node (CMP-B9, HUM-B7 to HUM-B9)
    a.append(arrow(f"M{g} {BOT} V{py - 4}"))
    a.append(label(g - 8, BOT + 74, "judge can't verify, blocked,", "end"))
    a.append(label(g - 8, BOT + 90, "budget spent, or approval:", "end"))
    a.append(label(g - 8, BOT + 106, "run pauses, exit 3", "end"))
    # outcome gate pauses: sign-off of person criteria, second failure (OUT-B4, OUT-B3)
    ox = o + 40
    a.append(arrow(f"M{ox} {BOT} V{py + BH / 2} H{px + pw + 4}"))
    a.append(label(ox + 8, BOT + 74, "sign-off, or", "start"))
    a.append(label(ox + 8, BOT + 90, "unmet twice", "start"))
    # decisions (HUM-B12)
    pmid = py + BH / 2
    a.append(arrow(f"M{px} {pmid} H{st + 76} V{BOT + 4}"))
    a.append(label((px + st + 76) / 2, pmid - 8, "retry · back · rewind (with feedback)"))
    pv = px + pw - 40
    a.append(arrow(f"M{pv} {py} C{pv} {BOT + 60}, {o - 40} {BOT + 60}, {o - 40} {BOT + 4}"))
    a.append(label(pv + 12, py - 8, "proceed: go on as passed", "start"))
    a.append(label(px + pw / 2, py + BH + 18, "stop ends the run (exit 4)"))
    # self-improvement (SIL, PRP)
    d = cx("done")
    a.append(arrow(f"M{d} {BOT} V{sy - 4}", dashed=True))
    a.append(label(d - 8, sy - 50, "every finished", "end"))
    a.append(label(d - 8, sy - 34, "run's record", "end"))
    a.append(arrow(f"M{sx} {sy + BH / 2} H{st + 24} V{BOT + 4}", dashed=True))
    a.append(label((sx + st + 24) / 2, sy + BH / 2 - 8, "measured change, merged by a person"))

    body = "".join(parts) + "".join(x.replace("{line}", c["line"]) for x in a)
    aria = ("How a tempergraph run flows: good outcome, then per step: step, deterministic checks, independent judge "
            "and gate, then the outcome gate and done. The gate retries the step, sends the run back or moves to "
            "the next step; it pauses for a person when the judge cannot verify, the step is blocked, a budget is "
            "spent or approval is needed. The person proceeds, retries, goes back, rewinds or stops. Every finished "
            "run feeds the self-improvement loop.")
    style = (f'<style>.t{{font:600 15px {FONT};fill:{c["text"]}}}.s{{font:12.5px {FONT};fill:{c["sub"]}}}'
             f'.l{{font:12px {FONT};fill:{c["sub"]}}}</style>')
    marker = (f'<defs><marker id="a" viewBox="0 0 10 10" refX="9" refY="5" markerWidth="7" markerHeight="7" '
              f'orient="auto-start-reverse"><path d="M0 0 L10 5 L0 10 z" fill="{c["line"]}"/></marker></defs>')
    return (f'<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 {W} {H}" width="{W}" height="{H}" role="img" '
            f'aria-label="{aria}">{style}{marker}{body}</svg>\n')


out = Path(sys.argv[1])
for t in THEMES:
    (out / f"how-it-works-{t}.svg").write_text(svg(t))
