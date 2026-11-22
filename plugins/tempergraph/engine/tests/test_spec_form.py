"""The engine's specs follow the spec rule of the docs README, and no old section reference is left (OVR-AC2, OVR-AC3).

The form checked here is the one the docs README states: a title, Purpose, Behaviours, Acceptance criteria and,
while a question is open, Open questions; each behaviour a `WHEN … THE … SHALL …` line and at least one
`GIVEN … WHEN … THEN …` scenario; each criterion naming the behaviours it proves, every behaviour named by one.
"""

from __future__ import annotations

import re
from pathlib import Path

from .conftest import DOCS, REPO_ROOT

SPECS = sorted((DOCS / "specs").glob("*.spec.md"))
SECTIONS = ("Purpose", "Behaviours", "Acceptance criteria", "Open questions")
BEHAVIOUR = re.compile(r"^### ([A-Z]{3})-B(\d+) \S")
STATEMENT = re.compile(r"^WHEN .+? THE .+? SHALL [a-z]")
SCENARIO = re.compile(r"^- GIVEN .+ WHEN .+ THEN .+")
CRITERION = re.compile(r"^- ([A-Z]{3})-AC(\d+) \(([^)]+)\): \S")


def _prefixes() -> set[str]:
    out = set()
    for p in SPECS:
        m = re.search(r"^### ([A-Z]{3})-B\d+", p.read_text(), re.M)
        if m:
            out.add(m.group(1))
    return out


def _problems(text: str) -> list[str]:
    lines = text.splitlines()
    found: list[str] = []
    if not lines or not lines[0].startswith("# "):
        found.append("first line is not the `# ` title")
    heads = [ln[3:].strip() for ln in lines if ln.startswith("## ")]
    if heads[:3] != list(SECTIONS[:3]) or heads[3:] not in ([], [SECTIONS[3]]):
        found.append(f"sections are {heads}")
    if "```" in text:
        found.append("a code block")
    if re.search(r"^\s*- \[[ x]\]", text, re.M):
        found.append("a checkbox")
    prefixes, behaviours, named = set(), [], set()
    for i, ln in enumerate(lines):
        m = BEHAVIOUR.match(ln)
        if m:
            bid = f"{m.group(1)}-B{m.group(2)}"
            behaviours.append(bid)
            body = []
            for nxt in lines[i + 1:]:
                if nxt.startswith("#"):
                    break
                body.append(nxt)
            filled = [b for b in body if b.strip()]
            if not filled or not STATEMENT.match(filled[0]):
                found.append(f"{bid}: first line is not `WHEN … THE … SHALL …`")
            if not any(SCENARIO.match(b) for b in filled):
                found.append(f"{bid}: no `- GIVEN … WHEN … THEN …` scenario")
        c = CRITERION.match(ln)
        if c:
            prefixes.add(c.group(1))
            named |= set(re.findall(r"[A-Z]{3}-B\d+", c.group(3)))
    # One prefix per spec; a behaviour moved by a split keeps its old id (spec-migration plan, Over the cap).
    if len(prefixes) > 1 or (behaviours and prefixes and behaviours[0].split("-")[0] not in prefixes):
        found.append(f"criteria prefixes {sorted(prefixes)} against first behaviour {behaviours[:1]}")
    found += [f"{b}: named by no criterion" for b in behaviours if b not in named]
    if len(set(behaviours)) != len(behaviours):
        found.append("a behaviour id defined twice")
    return found


def test_every_spec_follows_the_spec_rule() -> None:
    bad = {p.name: probs for p in SPECS if (probs := _problems(p.read_text()))}
    assert bad == {}, bad


def test_the_overview_names_every_spec() -> None:
    overview = (DOCS / "specs" / "00-overview.spec.md").read_text()
    purpose = overview.split("## Behaviours", 1)[0]
    missing = [p.name for p in SPECS if p.name != "00-overview.spec.md" and f"({p.name})" not in purpose]
    assert missing == [], missing


def _scanned() -> list[Path]:
    skip = ("/node_modules/", "/.git/", "spec-migration.plan.md", "R-150-rationale")
    out = []
    for p in (REPO_ROOT / "plugins").rglob("*"):
        s = p.as_posix()
        if p.is_file() and p.suffix in (".md", ".py", ".ts", ".tsx", ".json") and not any(k in s for k in skip):
            out.append(p)
    return out + [REPO_ROOT / "README.md", REPO_ROOT / "CLAUDE.md"]


def test_no_old_section_reference_is_left() -> None:
    """The section map in the spec-migration plan resolves old references; nothing outside it writes one."""
    engine = "|".join(sorted(_prefixes()))
    old = re.compile(rf"\b(?:{engine}) §\d|\b(?:{engine})-AC-\d|\b[Cc]ontracts? C\d+\b")
    hits = []
    for p in _scanned():
        try:
            text = p.read_text()
        except (UnicodeDecodeError, OSError):
            continue
        hits += [f"{p.relative_to(REPO_ROOT)}: {m.group(0)}" for m in old.finditer(text)]
    assert hits == [], hits[:20]
