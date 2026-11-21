"""The formats the checks read: specs, the triage note, the hand-off and the plan.

One home per format: the rule files under `rules/` say the same in words, and `tests/test_rules_match.py`
fails when a rule and this module disagree on a heading or a pattern."""

from __future__ import annotations

import re
from dataclasses import dataclass, field

SPEC_CAP_LINES = 400
SPEC_HEADINGS = ("Purpose", "Behaviours", "Acceptance criteria")
TRIAGE_HEADINGS = ("Task", "Acceptance criteria", "Existing documents", "Gaps", "Route")
HANDOFF_HEADINGS = ("Problem", "Gaps closed", "Changed documents", "Decisions", "Open questions")
PLAN_HEADINGS = ("0. Hand-off", "1. Requirements", "2. Phases", "3. Verification", "4. Docs to update")
REPORT_HEADINGS = ("Rows", "Verification", "Deviations")
SETUP_HEADINGS = ("Components", "Commands", "Not covered")
# The block the prepare script keeps in the project-context file, between these two lines.
CONTEXT_START = "<!-- temperspec:start -->"
CONTEXT_END = "<!-- temperspec:end -->"
DELIVER = ("code", "docs")
COMPLEXITY = ("simple", "complex")
ROW_KINDS = ("test", "code", "docs", "chore")
# The signs that make a phase heavy, and so the plan `complex` (the plan rule lists the same four).
HEAVY_SIGNS = ("refactor", "many-tests", "large-context", "long-running")
ROUTES = ("discovery", "plan", "discovery-only", "quick")
# What the quick lane may hold at most (the task-notes rule lists the same); over any of these the task is planned.
QUICK_MAX = {"criteria": 3, "code_files": 2, "lines": 200}
PROOF_HEADER = ("criterion", "test", "command")
SUFFIX_BY_FOLDER = {"specs": ".spec.md", "adr": ".adr.md", "research": ".rsrch.md", "plans": ".plan.md"}
# What a `simple` plan may hold at most; over any of these the plan is `complex`.
SIMPLE_MAX = {"phases": 3, "rows": 12, "test_rows": 6, "files": 10, "commands": 3, "reading_bytes": 200_000}

ID = r"[A-Z][A-Z0-9]{1,7}"
BEHAVIOUR_HEAD = re.compile(rf"^###\s+({ID}-B\d+)\b(.*)$")
BEHAVIOUR_LINE = re.compile(r"^WHEN\s+\S.*\s+THE\s+\S.*\s+SHALL\s+\S")
SCENARIO_LINE = re.compile(r"^\s*-\s+GIVEN\s+\S.*\bWHEN\s+\S.*\bTHEN\s+\S", re.I)
CRITERION_LINE = re.compile(rf"^\s*-\s+(?:\[[ xX]\]\s+)?\*{{0,2}}({ID}-AC\d+)\*{{0,2}}\s*\(([^)]*)\)\s*:?\s*(\S.*)$")
ANY_ID = re.compile(rf"\b({ID}-(?:B|AC)\d+)\b")
HEADING = re.compile(r"^(#{1,6})\s+(.+?)\s*#*\s*$")
LEGACY = re.compile(r"^##\s+\d+\.\s+(Overview|Contract)\b", re.M)
GAP_ROW = re.compile(r"^\s*(?:[-*]|\|)\s*\**G\d+\b")
NUMBERED = re.compile(r"^\s*(\d+)[.)]\s+\S")
TABLE_ROW = re.compile(r"^\s*\|(.+)\|\s*$")
CODE_SPAN = re.compile(r"`([^`]+)`")


def sections(text: str, level: int = 2) -> dict[str, list[str]]:
    """Heading text -> the lines under it, for headings of one level, in file order."""
    out: dict[str, list[str]] = {}
    current: list[str] | None = None
    for line in text.splitlines():
        m = HEADING.match(line)
        if m and len(m.group(1)) <= level:
            current = out.setdefault(m.group(2).strip(), []) if len(m.group(1)) == level else None
            continue
        if current is not None:
            current.append(line)
    return out


def headings_missing(text: str, wanted: tuple[str, ...], level: int = 2) -> list[str]:
    """The wanted headings that are absent or out of order."""
    found = [h.lower() for h in sections(text, level)]
    missing, pos = [], 0
    for h in wanted:
        try:
            pos = found.index(h.lower(), pos) + 1
        except ValueError:
            missing.append(h)
    return missing


@dataclass
class Behaviour:
    line: int
    statement: str = ""
    scenarios: int = 0


@dataclass
class SpecCriterion:
    line: int
    proves: list[str]
    text: str


@dataclass
class Spec:
    behaviours: dict[str, Behaviour] = field(default_factory=dict)
    criteria: dict[str, SpecCriterion] = field(default_factory=dict)
    legacy: bool = False
    lines: int = 0
    problems: list[tuple[int, str, str]] = field(default_factory=list)  # (line, message, fix)


def parse_spec(text: str) -> Spec:
    spec = Spec(legacy=bool(LEGACY.search(text)), lines=len(text.splitlines()))
    if spec.legacy:
        return spec
    for h in headings_missing(text, SPEC_HEADINGS):
        spec.problems.append((1, f"section `## {h}` is missing or out of order", f"add `## {h}`"))
    section = ""
    current: Behaviour | None = None
    for n, line in enumerate(text.splitlines(), 1):
        m = HEADING.match(line)
        if m and len(m.group(1)) == 2:
            section, current = m.group(2).strip().lower(), None
            continue
        if section == "behaviours":
            b = BEHAVIOUR_HEAD.match(line)
            if b:
                if b.group(1) in spec.behaviours:
                    spec.problems.append((n, f"behaviour id {b.group(1)} is defined twice", "use a new id"))
                current = spec.behaviours.setdefault(b.group(1), Behaviour(line=n))
            elif current is not None and not current.statement and line.strip():
                if BEHAVIOUR_LINE.match(line.strip()):
                    current.statement = line.strip()
                else:
                    current.statement = "?"
                    spec.problems.append((n, "the behaviour's first line is not `WHEN … THE … SHALL …`",
                                          "write one sentence in the fixed pattern"))
            elif current is not None and SCENARIO_LINE.match(line):
                current.scenarios += 1
        elif section == "acceptance criteria":
            c = CRITERION_LINE.match(line)
            if c:
                proves = [p.strip() for p in c.group(2).split(",") if p.strip()]
                if c.group(1) in spec.criteria:
                    spec.problems.append((n, f"criterion id {c.group(1)} is defined twice", "use a new id"))
                spec.criteria[c.group(1)] = SpecCriterion(line=n, proves=proves, text=c.group(3))
    found = {h.lower() for h in sections(text)}
    if "behaviours" in found and not spec.behaviours:
        spec.problems.append((1, "no behaviour is defined", "add `### PREFIX-B1 name` with its WHEN … SHALL line"))
    if "acceptance criteria" in found and not spec.criteria:
        spec.problems.append((1, "no acceptance criterion is defined", "add `- PREFIX-AC1 (PREFIX-B1): …`"))
    proved = {p for crit in spec.criteria.values() for p in crit.proves}
    for bid, beh in spec.behaviours.items():
        if not beh.statement:
            spec.problems.append((beh.line, f"{bid} has no statement", "add the WHEN … THE … SHALL … line"))
        if not beh.scenarios:
            spec.problems.append((beh.line, f"{bid} has no scenario", "add `- GIVEN … WHEN … THEN …`"))
        if bid not in proved:
            spec.problems.append((beh.line, f"{bid} is proved by no acceptance criterion",
                                  f"add a criterion that names {bid}"))
    for cid, crit in spec.criteria.items():
        for p in crit.proves:
            if p not in spec.behaviours:
                spec.problems.append((crit.line, f"{cid} names {p}, which this spec does not define",
                                      "name a behaviour of this spec"))
        if not crit.proves:
            spec.problems.append((crit.line, f"{cid} names no behaviour", "add the behaviour id in brackets"))
    return spec


DEFINITION = re.compile(rf"^\s*(?:#{{1,6}}\s+|\|\s*|[-*]\s+(?:\[[ xX]\]\s+)?)?\*{{0,2}}({ID}-(?:B|AC)\d+)\b")


def defined_ids(text: str) -> list[str]:
    """Ids a spec defines: an id that opens a heading, a list item or a table row (old layouts included).
    An id defined twice in one file is listed twice."""
    return [m.group(1) for line in text.splitlines() if (m := DEFINITION.match(line))]


def linked_ids(text: str) -> set[str]:
    return set(ANY_ID.findall(text))


@dataclass
class Triage:
    criteria: list[int] = field(default_factory=list)
    deliver: str = ""
    gaps: str = ""  # `none`, `some`, or empty when the Gaps section is neither
    gap_rows: int = 0
    route: str = ""
    missing: list[str] = field(default_factory=list)
    # The Change section, which only a `quick` note has: the code files, the test files and the commands.
    change: bool = False
    change_files: list[str] = field(default_factory=list)
    change_tests: list[str] = field(default_factory=list)
    change_commands: list[str] = field(default_factory=list)


def _field(lines: list[str], name: str) -> str:
    for line in lines:
        m = re.match(rf"^\s*[-*]?\s*\**{name}\**\s*:\s*(.+?)\s*$", line, re.I)
        if m:
            return m.group(1).strip().strip("`")
    return ""


def parse_triage(text: str) -> Triage:
    sec = sections(text)
    low = {k.lower(): v for k, v in sec.items()}
    t = Triage(missing=headings_missing(text, TRIAGE_HEADINGS))
    t.criteria = [int(m.group(1)) for line in low.get("acceptance criteria", []) if (m := NUMBERED.match(line))]
    gaps = [ln for ln in low.get("gaps", []) if ln.strip()]
    t.gap_rows = sum(1 for ln in gaps if GAP_ROW.match(ln))
    if t.gap_rows:
        t.gaps = "some"
    elif len(gaps) == 1 and re.fullmatch(r"\W*none\W*", gaps[0], re.I):
        t.gaps = "none"
    route = low.get("route", [])
    t.deliver, t.route = _field(route, "Deliver").lower(), _field(route, "Route").lower()
    t.change = "change" in low
    for line in low.get("change", []):
        m = re.match(r"^\s*[-*]\s+\**(Files|Tests|Verify)\**\s*:\s*(.*)$", line, re.I)
        if m:
            target = {"files": t.change_files, "tests": t.change_tests, "verify": t.change_commands}[m.group(1).lower()]
            target += [span.strip() for span in CODE_SPAN.findall(m.group(2)) if span.strip()]
    return t


def quick_problems(note: Triage) -> list[str]:
    """Why a note may not take the quick lane; empty when it may. Measured from the note alone."""
    bad = []
    if note.gaps != "none":
        bad.append("the quick lane needs `None` under Gaps")
    if note.deliver != "code":
        bad.append("the quick lane delivers code")
    if len(note.criteria) > QUICK_MAX["criteria"]:
        bad.append(f"{len(note.criteria)} acceptance criteria, over {QUICK_MAX['criteria']}")
    if not note.change:
        bad.append("the quick lane needs a `## Change` section")
        return bad
    if not note.change_files:
        bad.append("the Change section names no code file under `Files:`")
    if len(note.change_files) > QUICK_MAX["code_files"]:
        bad.append(f"{len(note.change_files)} code files, over {QUICK_MAX['code_files']}")
    if not note.change_tests:
        bad.append("the Change section names no test file under `Tests:`")
    if not note.change_commands:
        bad.append("the Change section names no command under `Verify:`")
    docs = [f for f in note.change_files + note.change_tests if f.endswith(".md")]
    if docs:
        bad.append(f"`{docs[0]}` is a document: a change to a document is not a quick change")
    return bad


def listed_paths(lines: list[str]) -> list[str]:
    """Paths in a bullet list or a table: the first code span of each line, else the first word of a bullet."""
    out = []
    for line in lines:
        m = CODE_SPAN.search(line)
        if m and ("/" in m.group(1) or m.group(1).endswith(".md")):
            out.append(m.group(1).strip())
        elif (b := re.match(r"^\s*[-*]\s+(\S+\.md)\b", line)):
            out.append(b.group(1))
    return out


@dataclass
class Row:
    id: str
    kind: str
    file: str
    proves: str
    phase: str


@dataclass
class Plan:
    complexity: str = ""
    specs: list[str] = field(default_factory=list)
    requirement_criteria: set[int] = field(default_factory=set)
    phases: list[str] = field(default_factory=list)
    rows: list[Row] = field(default_factory=list)
    commands: list[str] = field(default_factory=list)
    heavy: dict[str, str] = field(default_factory=dict)  # phase -> the sign that makes it heavy
    proof: list[tuple[str, str, str]] = field(default_factory=list)  # (criterion cell, test file, command)
    handoff_lines: int = 0
    missing: list[str] = field(default_factory=list)


def _cells(line: str) -> list[str] | None:
    m = TABLE_ROW.match(line)
    if not m:
        return None
    cells = [c.strip() for c in m.group(1).split("|")]
    return None if all(re.fullmatch(r":?-+:?", c) for c in cells if c) else cells


def parse_plan(text: str) -> Plan:
    plan = Plan(missing=headings_missing(text, PLAN_HEADINGS))
    front = re.match(r"^---\n(.*?)\n---\n", text.replace("\r\n", "\n"), re.S)
    if front:
        plan.complexity = _field(front.group(1).splitlines(), "complexity").lower()
        specs = _field(front.group(1).splitlines(), "specs")
        plan.specs = [s.strip().strip("'\"") for s in specs.strip("[]").split(",") if s.strip()]
    section, phase, header = "", "", None
    for line in text.splitlines():
        m = HEADING.match(line)
        if m and len(m.group(1)) == 2:
            section, phase, header = m.group(2).strip().lower(), "", None
            continue
        if section.startswith("0.") and line.strip():
            plan.handoff_lines += 1
        elif section.startswith("1.") and (cells := _cells(line)) and len(cells) >= 2:
            if cells[0].lower() not in ("req", "requirement"):
                plan.requirement_criteria |= {int(n) for n in re.findall(r"\bAC\s*(\d+)\b", cells[1], re.I)}
        elif section.startswith("2."):
            if m and len(m.group(1)) == 3:
                phase, header = m.group(2).strip(), None
                plan.phases.append(phase)
            elif phase and (w := re.match(r"^\s*[-*]?\s*\**Weight\**\s*:\s*heavy\b\W*([a-z-]*)", line, re.I)):
                plan.heavy[phase] = w.group(1).lower()
            elif phase and (cells := _cells(line)):
                if header is None:
                    header = [c.lower() for c in cells]
                    continue
                got = dict(zip(header, cells, strict=False))
                plan.rows.append(Row(id=got.get("row", ""), kind=got.get("kind", "").lower(),
                                     file=got.get("file", "").strip("`"), proves=got.get("proves", ""),
                                     phase=phase))
        elif section.startswith("3.") and (b := re.match(r"^\s*[-*]\s+`([^`]+)`", line)):
            plan.commands.append(b.group(1).strip())
        elif section.startswith("3.") and (cells := _cells(line)):
            if header is None:
                header = [c.lower() for c in cells]
                continue
            got = dict(zip(header, cells, strict=False))
            plan.proof.append((got.get("criterion", ""), got.get("test", "").strip("` "),
                               got.get("command", "").strip("` ")))
    return plan


def simple_overruns(plan: Plan, reading_bytes: int = 0) -> list[str]:
    """Which measured signs of the plan are over the limit for `simple`."""
    signs = {"phases": len(plan.phases), "rows": len(plan.rows),
             "test_rows": sum(1 for r in plan.rows if r.kind == "test"),
             "files": len({r.file for r in plan.rows if r.file}), "commands": len(plan.commands),
             "reading_bytes": reading_bytes}
    over = [f"{k} {signs[k]} > {limit}" for k, limit in SIMPLE_MAX.items() if signs[k] > limit]
    return over + [f"phase `{p}` is heavy ({sign or 'no sign named'})" for p, sign in plan.heavy.items()]


ROW_PROVES = re.compile(rf"\b(?:{ID}-AC\d+|AC\s*\d+)\b")


def row_problems(plan: Plan) -> tuple[list[str], list[str]]:
    """(phases with no task row, rows that break the order rule): a `code` row needs an earlier `test` row of
    its phase that names an acceptance criterion; every row needs an id, a known kind and a file."""
    empty = [p for p in plan.phases if not any(r.phase == p for r in plan.rows)]
    bad: list[str] = []
    tested: set[str] = set()
    for r in plan.rows:
        if not r.id or r.kind not in ROW_KINDS or not r.file:
            bad.append(f"row `{r.id or '?'}` of `{r.phase}` needs an id, a kind of {'/'.join(ROW_KINDS)} and a file")
        elif r.kind == "test":
            if ROW_PROVES.search(r.proves):
                tested.add(r.phase)
            else:
                bad.append(f"test row `{r.id}` names no acceptance criterion id in its Proves cell")
        elif r.kind == "code" and r.phase not in tested:
            bad.append(f"code row `{r.id}` has no test row before it in `{r.phase}`")
    return empty, bad


def task_criteria(cell: str) -> set[int]:
    """The task criteria a cell names, written `AC <n>`."""
    return {int(n) for n in re.findall(r"(?<![A-Z0-9-])AC\s*(\d+)\b", cell)}


def proof_problems(plan: Plan, criteria: list[int]) -> list[str]:
    """The proof table of `## 3. Verification`: every acceptance criterion of the task has a row that names
    a test file of a test row and one of the plan's verification commands."""
    bad: list[str] = []
    test_files = {r.file for r in plan.rows if r.kind == "test" and r.file}
    proved: set[int] = set()
    for cell, test, command in plan.proof:
        named = task_criteria(cell)
        if not named:
            bad.append(f"proof row `{cell or '?'}` names no criterion as `AC <n>`")
            continue
        if test not in test_files:
            bad.append(f"the test `{test or '?'}` of {cell} is the file of no test row")
        elif command not in plan.commands:
            bad.append(f"the command `{command or '?'}` of {cell} is not one of the listed commands")
        else:
            proved |= named
    bad += [f"acceptance criterion {n} has no row in the proof table" for n in criteria if n not in proved
            and not any(n in task_criteria(c) for c, _, _ in plan.proof)]
    return bad


def marker(criterion: str) -> re.Pattern[str]:
    """How a test carries a criterion: the spec's id as written, or `AC <n>` of the task."""
    n = task_criteria(criterion)
    if n and not ANY_ID.search(criterion):
        return re.compile(rf"(?<![A-Za-z0-9-])AC[\s_]*{next(iter(n))}(?!\d)", re.I)
    return re.compile(rf"\b{re.escape(criterion.strip())}\b")


SKIP_MARK = re.compile(r"(@pytest\.mark\.(skip|xfail)|@unittest\.skip|pytest\.skip\(|\b(it|test|describe)\.skip\(|"
                       r"\bx(it|describe)\(|@Disabled|@Ignore\b|\bt\.Skip\()")


def carried(text: str, criterion: str) -> tuple[bool, bool]:
    """(the text names the criterion, a naming place is skipped): a skip mark on the line or the three above."""
    lines = text.splitlines()
    pat = marker(criterion)
    hits = [i for i, line in enumerate(lines) if pat.search(line)]
    skipped = bool(hits) and all(any(SKIP_MARK.search(x) for x in lines[max(0, i - 3):i + 1]) for i in hits)
    return bool(hits), skipped


def parse_report(text: str) -> dict[str, str]:
    """The code report's row table: row id -> status, lower case."""
    out: dict[str, str] = {}
    header: list[str] | None = None
    for line in {k.lower(): v for k, v in sections(text).items()}.get("rows", []):
        cells = _cells(line)
        if cells is None:
            continue
        if header is None:
            header = [c.lower() for c in cells]
            continue
        got = dict(zip(header, cells, strict=False))
        if got.get("row"):
            out[got["row"]] = got.get("status", "").strip("*` ").lower()
    return out
