"""The formats the checks read: specs, decision records, the triage note, the hand-off and the plan.

One home per format: the rule files under `rules/` say the same in words, and `tests/test_rules_match.py`
fails when a rule and this module disagree on a heading or a pattern."""

from __future__ import annotations

import re
from collections.abc import Mapping, Sequence
from dataclasses import dataclass, field

SPEC_CAP_LINES = 400
# The repository's spec budget is at most 400 lines and at most 30 KB; "over" means strictly more.
SPEC_CAP_BYTES = 30 * 1024
SPEC_HEADINGS = ("Purpose", "Behaviours", "Acceptance criteria")
TRIAGE_HEADINGS = ("Task", "Acceptance criteria", "Intent", "Existing documents", "Uncertainties", "Gaps", "Route")
HANDOFF_HEADINGS = ("Problem", "Gaps closed", "Changed documents", "Decisions", "Open questions", "Reading list")
PLAN_HEADINGS = ("0. Hand-off", "1. Requirements", "2. Phases", "3. Verification", "4. Docs to update")
REPORT_HEADINGS = ("Verification", "Deviations")  # the quick lane adds `## Rows` before them (no plan to mark)
QUICK_REPORT_HEADINGS = ("Rows", *REPORT_HEADINGS)
SETUP_HEADINGS = ("Components", "Commands", "Evidence", "Anomalies", "Not covered")
# The block the prepare script keeps in the project-context file, between these two lines.
CONTEXT_START = "<!-- temperspec:start -->"
CONTEXT_END = "<!-- temperspec:end -->"
DELIVER = ("code", "docs")
COMPLEXITY = ("simple", "complex")
ROW_KINDS = ("test", "code", "docs", "chore")
PLAN_STATUS = ("planned", "in-progress", "completed")
ROW_COLUMNS = ("row", "kind", "req", "file", "proves", "change", "completed")
DONE_MARK = re.compile(r"^[✓✔]\s*(\d{4}-\d{2}-\d{2})$")
REQ_ID = re.compile(r"\bR\d+\b")
# Words that say a requirement or a row does less than asked; the plan judge then looks at the scope.
SCOPE_CUT = re.compile(r"\b(stub(?:s|bed)?|for now|placeholder|temporar(?:y|ily)|hard-?coded|v1 only|not yet|"
                       r"later (?:release|version|task)|follow-?up task|skip(?:ped)? for|mock(?:ed)? out|TODO)\b", re.I)
# The signs that make a phase heavy, and so the plan `complex` (the plan rule lists the same four).
HEAVY_SIGNS = ("refactor", "many-tests", "large-context", "long-running")
ROUTES = ("discovery", "plan", "discovery-only", "quick")
# What the quick lane may hold at most (the task-notes rule lists the same); over any of these the task is planned.
QUICK_MAX = {"criteria": 3, "code_files": 2, "lines": 200}
PROOF_HEADER = ("criterion", "test", "command")
# The decision rule's sections, in reasoning order; the check reads that each is present, not their order.
DECISION_HEADINGS = ("Context", "Current state", "Forces", "Options considered", "Decision", "Decision rationale",
                     "Consequences", "Risks", "Assumptions", "Revisit when")
DECISION_CAP_BYTES = 10 * 1024  # "at most about 10 KB": over it the record reaches the judge as a lead
FORCE_ROW = re.compile(r"^\s*[-*]\s+\**([CF])(\d+)\b\**")
ASSUMPTION_ROW = re.compile(r"^\s*[-*]\s+\**(A\d+)\b")
# A sentence of `Current state` cites when it holds a code span, a link or a behaviour or criterion id.
CITES = re.compile(r"`[^`]+`|\]\([^)]+\)|\b[A-Z][A-Z0-9]{1,7}-(?:B|AC)\d+\b")
SENTENCE_END = re.compile(r"(?<=[.!?])\s+(?=[A-Z`\[(])")
VAGUE_REVISIT = re.compile(r"\b(if|when|as) (needs?|requirements?|circumstances|things) change|\bas needed\b|"
                           r"\bif necessary\b|\bwhen appropriate\b|\bif (it|this) (no longer works|stops working)\b",
                           re.I)
RESEARCH_HEADINGS = ("Problem statement", "Sources consulted", "Key findings", "Conclusions", "Open questions")
TEMPLATE_DIR = "docs/templates"
EXAMPLE = re.compile(r"^```markdown\n(.*?)^```$", re.M | re.S)
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
COVERED_WORDS = re.compile(r"\bCovered by\b", re.I)
COVERED = re.compile(rf"\b(?i:Covered by)\s+`?({ID}-B\d+)`?\s+and\s+`?({ID}-AC\d+)\b`?")
# The conversation setting `never` (spec `conversation`): each gap row ends with its sort, and the section
# `Owner decisions`, between Gaps and Route, holds one entry per owner decision. A note of a `blocking` run has neither.
OWNER_HEADING = "Owner decisions"
SORT_END = re.compile(r"\b(findable|owner decision)\W*$", re.I)
GAP_ID = re.compile(r"\bG\d+\b")
OWNER_ENTRY = re.compile(r"^\s*(?:[-*]\s+)?\**([GU]\d+)\**\s*:\s*(.*?)\s*$")
# The triage note's `## Intent` (what the task is for and where it stops) and `## Uncertainties` (what the task leaves
# open about its own intent, one row for each question, found by a scan of fixed categories). A row is
# `U<n> <category>: <question>. <Impact> <what>. Route: <route>`: the impact says how much rests on the answer and
# the route where the answer is looked for. `Detail` rows are settled by the plan; every other row is working.
INTENT_FIELDS = ("Goal", "In scope", "Out of scope", "Assumptions")
ASSUMPTION = re.compile(r"^\s*(?:[-*]\s+)?\**(A\d+)\**\s*:\s*(.*?)\s*$")
IF_WRONG = re.compile(r"\bIf wrong\s*:\s*\S", re.I)
UNCERTAINTY_CATEGORIES = ("goal", "scope", "actors", "data", "names", "side effects", "failures", "limits",
                          "life cycle", "dependencies", "existing behaviour", "terms")
UNCERTAINTY_IMPACTS = ("blocks", "shapes", "detail")
UNCERTAINTY_ROUTES = ("code", "docs", "source", "owner", "plan")
READ_ROUTES = ("code", "docs", "source")  # the routes a reading session can follow
UNCERTAINTY_ROW = re.compile(r"^\s*(?:[-*]|\|)\s*\**(U\d+)\**\s+([^:|]*?)\s*:\s*(\S.*)$")
UNCERTAINTY_IMPACT = re.compile(r"(?:^|[.?!]\s+)\**(Blocks|Shapes|Detail)\b")
UNCERTAINTY_ROUTE = re.compile(r"\bRoute\s*:\s*`?([a-z]+)`?\W*$", re.I)
UNCERTAINTY_ID = re.compile(r"\bU\d+\b")
# An option written on a line of its own under an empty `Options:` (`a) 30 minutes`, `- b) 15 minutes`).
OWNER_OPTION_LINE = re.compile(r"^\s*(?:[-*]\s+)?\(?([a-z])\)\s+(.+?)\s*$")
OWNER_ITEM = re.compile(r"^\s*(?:[-*]\s+)?\**(Options|Default|If wrong)\**\s*:\s*(.*?)\s*$", re.I)
OPTION_LABEL = re.compile(r"(?:(?<=^)|(?<=[\s;,]))([a-z])\)\s+")
OWNER_OPTIONS = (2, 4)
READING_ITEM = re.compile(r"^\s*[-*]\s+`([^`]+)`\s*(.*)$")
NUMBERED = re.compile(r"^\s*(\d+)[.)]\s+\S")
TABLE_ROW = re.compile(r"^\s*\|(.+)\|\s*$")
CODE_SPAN = re.compile(r"`([^`]+)`")


def rule_templates(rule: str, text: str) -> dict[str, str]:
    """The fill-in templates of a rule file: each example in it of a whole document (one that opens with front
    matter or a `# ` title), named `<rule>.template.md`, or by the example's title when the rule has several.
    Generated at install, so a template is never a second copy to keep in step with its rule."""
    docs = [b for b in EXAMPLE.findall(text.replace("\r\n", "\n")) if b.startswith(("---\n", "# "))]
    out: dict[str, str] = {}
    for body in docs:
        name = rule
        if len(docs) > 1:
            title = re.search(r"^# ([^:\n]+)", body, re.M)
            name = re.sub(r"[^a-z0-9]+", "-", (title.group(1) if title else rule).lower()).strip("-")
        out[f"{name}.template.md"] = body
    return out


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


def behaviour_blocks(text: str) -> dict[str, str]:
    """Behaviour id -> its block (heading, statement and scenarios), spacing normalised, so two versions of a
    spec can be compared block by block."""
    out: dict[str, list[str]] = {}
    current: list[str] | None = None
    for line in text.splitlines():
        b = BEHAVIOUR_HEAD.match(line)
        if b:
            current = out.setdefault(b.group(1), [])
        elif HEADING.match(line):
            current = None
        if current is not None and line.strip():
            current.append(" ".join(line.split()))
    return {k: "\n".join(v) for k, v in out.items()}


def changed_criteria(before: str, after: str) -> set[str]:
    """The criteria of `after` that a change from `before` concerns: each one added or reworded, and each old
    one that proves a behaviour added or changed. Criteria the change leaves alone are not in the set."""
    old, new = parse_spec(before), parse_spec(after)
    old_b, new_b = behaviour_blocks(before), behaviour_blocks(after)
    moved = {bid for bid, block in new_b.items() if old_b.get(bid) != block}
    out = set()
    for cid, crit in new.criteria.items():
        was = old.criteria.get(cid)
        if was is None or (was.text, was.proves) != (crit.text, crit.proves) or set(crit.proves) & moved:
            out.add(cid)
    return out


def _prefix(ident: str) -> str:
    return ident.rsplit("-", 1)[0]


def parse_spec(text: str, defined_elsewhere: Mapping[str, Sequence[str]] | None = None) -> Spec:
    """Read a spec. `defined_elsewhere` maps an id to the other spec files that define it: a criterion may then
    name an id that exactly one other file defines when the id's prefix is one this spec defines (an id a split
    moved, or one of the spec it was split from). Without it every criterion names this spec's behaviours only."""
    elsewhere = defined_elsewhere or {}
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
    own_prefixes = {_prefix(i) for i in (*spec.behaviours, *spec.criteria)}
    for cid, crit in spec.criteria.items():
        for p in crit.proves:
            moved = len(elsewhere.get(p, ())) == 1 and _prefix(p) in own_prefixes
            if p not in spec.behaviours and not moved:
                spec.problems.append((crit.line, f"{cid} names {p}, which this spec does not define",
                                      "name a behaviour of this spec or of the spec it was split from"))
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
class OwnerEntry:
    """One entry of the `Owner decisions` section: the gap it answers, its question, its options as (label, text),
    its default as written, and the cost of a wrong default."""

    gap: str
    question: str = ""
    options: list[tuple[str, str]] = field(default_factory=list)
    default: str = ""
    cost: str = ""

    @property
    def default_text(self) -> str:
        """The text of the option the default names (by its label, or by its words), else empty."""
        want = self.default.strip().strip("`*").strip()
        label = re.match(r"^\(?([a-z])\)?(?:[\s.:)-]|$)", want, re.I)
        for lab, text in self.options:
            if lab and label and lab == label.group(1).lower():
                return text
        for _, text in self.options:
            if text and text.lower() == want.lower():
                return text
        return ""


def _options(text: str) -> list[tuple[str, str]]:
    """`a) 2; b) 1; c) 78` -> [("a", "2"), ("b", "1"), ("c", "78")]; without labels, the `;`-separated parts."""
    marks = list(OPTION_LABEL.finditer(text))
    if not marks:
        return [("", p.strip()) for p in text.split(";") if p.strip()]
    return [(m.group(1), text[m.end():(marks[i + 1].start() if i + 1 < len(marks) else len(text))].strip(" ;,"))
            for i, m in enumerate(marks)]


def _owner_entries(lines: list[str]) -> list[OwnerEntry]:
    entries: list[OwnerEntry] = []
    listing = False  # under an `Options:` that holds no option: the options follow one per line
    for line in lines:
        head, item = OWNER_ENTRY.match(line), OWNER_ITEM.match(line)
        option = OWNER_OPTION_LINE.match(line)
        if head:
            entries.append(OwnerEntry(gap=head.group(1), question=head.group(2)))
            listing = False
        elif item and entries:
            key, value = item.group(1).lower(), item.group(2).strip()
            listing = key == "options" and not value
            if key == "options":
                entries[-1].options = _options(value)
            elif key == "default":
                entries[-1].default = value
            else:
                entries[-1].cost = value
        elif listing and option and entries:
            entries[-1].options.append((option.group(1).lower(), option.group(2).strip(" ;,")))
    return entries


@dataclass
class Uncertainty:
    """One row of the `Uncertainties` section: its id, its category, its impact and its route as written (lower
    case, empty when the row names none), and the row itself."""

    id: str
    category: str = ""
    impact: str = ""
    route: str = ""
    text: str = ""

    @property
    def working(self) -> bool:
        """A row the run has to answer before the plan: every row but a `Detail` one."""
        return self.impact != "detail"


@dataclass
class Triage:
    criteria: list[int] = field(default_factory=list)
    # The Intent section's fields by lower-case name (`goal`, `in scope`, `out of scope`, `assumptions`), the
    # assumption rows `A<n>` with whether each states `If wrong:`, and the Uncertainties section: `none`, `some`, or
    # empty when it is neither, and its rows.
    intent: dict[str, str] = field(default_factory=dict)
    assumptions: dict[str, bool] = field(default_factory=dict)
    uncertain: str = ""
    uncertainties: list[Uncertainty] = field(default_factory=list)
    deliver: str = ""
    gaps: str = ""  # `none`, `some`, or empty when the Gaps section is neither
    gap_rows: int = 0
    # Gap rows that end `Covered by <behaviour id> and <criterion id>`: the cited pairs, one per covered row, and
    # how many rows say `Covered by` at all (a row that says it without two ids is claimed but not counted).
    covered: list[tuple[str, str]] = field(default_factory=list)
    covered_rows: int = 0
    covered_claimed: int = 0
    route: str = ""
    missing: list[str] = field(default_factory=list)
    # The Change section, which only a `quick` note has: the code files, the test files and the commands.
    change: bool = False
    change_files: list[str] = field(default_factory=list)
    change_tests: list[str] = field(default_factory=list)
    change_commands: list[str] = field(default_factory=list)
    # The conversation setting `never`: gap id -> `findable`, `owner decision` or empty (a row with no sort), whether the
    # `Owner decisions` section exists, whether it says `None`, and its entries.
    sorts: dict[str, str] = field(default_factory=dict)
    owner_section: bool = False
    owner_none: bool = False
    owners: list[OwnerEntry] = field(default_factory=list)

    @property
    def working(self) -> list[Uncertainty]:
        """The uncertainty rows the run answers before the plan (`Blocks` and `Shapes`)."""
        return [u for u in self.uncertainties if u.working]

    @property
    def readable(self) -> list[Uncertainty]:
        """The working rows a reading session can answer: routed to the code, the documents or a public source."""
        return [u for u in self.working if u.route in READ_ROUTES]


def _field(lines: list[str], name: str) -> str:
    for line in lines:
        m = re.match(rf"^\s*[-*]?\s*\**{name}\**\s*:\s*(.+?)\s*$", line, re.I)
        if m:
            return m.group(1).strip().strip("`")
    return ""


def gap_rows(text: str) -> list[str]:
    """The lines of a triage note's Gaps section that open a gap row, unchanged and in order."""
    low = {k.lower(): v for k, v in sections(text).items()}
    return [ln for ln in low.get("gaps", []) if GAP_ROW.match(ln)]


def parse_triage(text: str) -> Triage:
    sec = sections(text)
    low = {k.lower(): v for k, v in sec.items()}
    t = Triage(missing=headings_missing(text, TRIAGE_HEADINGS))
    t.criteria = [int(m.group(1)) for line in low.get("acceptance criteria", []) if (m := NUMBERED.match(line))]
    gaps = [ln for ln in low.get("gaps", []) if ln.strip()]
    rows = [ln for ln in gaps if GAP_ROW.match(ln)]
    t.gap_rows = len(rows)
    for ln in rows:
        if COVERED_WORDS.search(ln):
            t.covered_claimed += 1
        if (c := COVERED.search(ln)):
            t.covered.append((c.group(1), c.group(2)))
    t.covered_rows = len(t.covered)
    for ln in rows:
        sort, gap = SORT_END.search(ln.rstrip()), GAP_ID.search(ln)
        if gap:
            t.sorts[gap.group(0)] = sort.group(1).lower() if sort else ("findable" if COVERED_WORDS.search(ln) else "")
    intent = low.get("intent", [])
    for name in INTENT_FIELDS:
        t.intent[name.lower()] = _field(intent, name)
    for ln in intent:
        if (a := ASSUMPTION.match(ln)):
            t.assumptions[a.group(1)] = bool(IF_WRONG.search(a.group(2)))
    listed = [ln for ln in low.get("uncertainties", []) if ln.strip()]
    for ln in listed:
        if (u := UNCERTAINTY_ROW.match(ln)) is None or any(u.group(1) == seen.id for seen in t.uncertainties):
            continue
        rest = u.group(3).strip().strip("|").strip()
        impact, route = UNCERTAINTY_IMPACT.search(rest), UNCERTAINTY_ROUTE.search(rest)
        t.uncertainties.append(Uncertainty(
            id=u.group(1), category=" ".join(u.group(2).lower().split()), text=ln.strip(),
            impact=impact.group(1).lower() if impact else "", route=route.group(1).lower() if route else ""))
        t.sorts[u.group(1)] = "owner decision" if t.uncertainties[-1].route == "owner" else "findable"
    if t.uncertainties:
        t.uncertain = "some"
    elif len(listed) == 1 and re.fullmatch(r"\W*none\W*", listed[0], re.I):
        t.uncertain = "none"
    owner = [ln for ln in low.get(OWNER_HEADING.lower(), []) if ln.strip()]
    t.owner_section = OWNER_HEADING.lower() in low
    t.owner_none = len(owner) == 1 and bool(re.fullmatch(r"\W*none\W*", owner[0], re.I))
    t.owners = _owner_entries(owner)
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


@dataclass
class ReadingItem:
    path: str
    locator: str  # the line ranges or ids that matter
    reason: str  # one line on why the plan will need the file


def parse_reading_list(text: str) -> list[ReadingItem]:
    """The items of a hand-off's `## Reading list`: each bullet is `` `path` (ranges or ids): why ``. The first
    code span is the path, the words between it and the colon the locator, the rest the reason."""
    low = {k.lower(): v for k, v in sections(text).items()}
    items: list[ReadingItem] = []
    for line in low.get("reading list", []):
        m = READING_ITEM.match(line)
        if not m:
            continue
        locator, colon, reason = m.group(2).partition(":")
        locator = locator.strip()
        if locator.startswith("(") and locator.endswith(")"):
            locator = locator[1:-1].strip()
        items.append(ReadingItem(path=m.group(1).strip(), locator=locator, reason=reason.strip() if colon else ""))
    return items


def uncertainty_rows(text: str) -> list[str]:
    """The lines of a triage note's Uncertainties section that open a row, unchanged and in order."""
    low = {k.lower(): v for k, v in sections(text).items()}
    return [ln for ln in low.get("uncertainties", []) if UNCERTAINTY_ROW.match(ln)]


def intent_problems(note: Triage) -> list[tuple[str, str, str]]:
    """What is wrong with a note's Intent and Uncertainties sections, as (place, message, fix); empty when both
    hold what the task-notes rule asks. Measured from the note alone."""
    bad: list[tuple[str, str, str]] = []
    for name in INTENT_FIELDS[:3]:
        if not note.intent.get(name.lower()):
            bad.append(("Intent", f"the Intent section has no `{name}:` line with words after it",
                        f"add `- {name}: …`"))
    stated = note.intent.get("assumptions", "")
    if not note.assumptions and not re.fullmatch(r"\W*none\W*", stated, re.I):
        bad.append(("Intent", "the Intent section has neither `Assumptions: None` nor assumption rows `A1`, `A2`, …",
                    "write `- Assumptions: None`, or one row `A<n>: <assumption>. If wrong: <cost>` for each"))
    for aid, costed in note.assumptions.items():
        if not costed:
            bad.append((aid, f"assumption {aid} does not say what it costs if it is wrong",
                        f"end {aid} with `If wrong: <what it costs>`"))
    if not note.uncertain:
        bad.append(("Uncertainties", "the Uncertainties section is neither `None` nor rows `U1`, `U2`, …",
                    "write `None`, or one row for each open question"))
    for u in note.uncertainties:
        if u.category not in UNCERTAINTY_CATEGORIES:
            bad.append((u.id, f"row {u.id} names the category `{u.category}`, not one of "
                              f"{', '.join(UNCERTAINTY_CATEGORIES)}", f"open {u.id} with one of the categories"))
        if not u.impact:
            bad.append((u.id, f"row {u.id} states no impact after its question",
                        f"add a sentence that opens `Blocks`, `Shapes` or `Detail` to {u.id}"))
        if u.route not in UNCERTAINTY_ROUTES:
            bad.append((u.id, f"row {u.id} does not end `Route:` with one of {', '.join(UNCERTAINTY_ROUTES)}",
                        f"end {u.id} with `Route: <where the answer is looked for>`"))
        elif u.impact and (u.impact == "detail") != (u.route == "plan"):
            bad.append((u.id, f"row {u.id} is `{u.impact.capitalize()}` with the route `{u.route}`: a `Detail` row "
                              "goes to `plan`, and no other row does", f"change the impact or the route of {u.id}"))
    return bad


def quick_problems(note: Triage) -> list[str]:
    """Why a note may not take the quick lane; empty when it may. Measured from the note alone."""
    bad = []
    if note.gaps != "none":
        bad.append("the quick lane needs `None` under Gaps")
    if note.deliver != "code":
        bad.append("the quick lane delivers code")
    if note.working:
        bad.append(f"the quick lane takes no open question that blocks or shapes the change ({note.working[0].id})")
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
    req: list[str] = field(default_factory=list)
    completed: str = ""  # the Completed cell as written: empty until the code step marks it `✓ <date>`
    change: str = ""
    has_req: bool = True  # the table has a `Req` column


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
    status: str = ""
    requirements: dict[str, str] = field(default_factory=dict)  # requirement id -> its statement
    docs: list[str] = field(default_factory=list)  # paths under `## 4. Docs to update`


def _cells(line: str) -> list[str] | None:
    m = TABLE_ROW.match(line)
    if not m:
        return None
    # A pipe escaped as `\|` (Markdown's way to put one in a cell, as in a type union `X \| None`) stays in its cell.
    cells = [c.strip().replace("\\|", "|") for c in re.split(r"(?<!\\)\|", m.group(1))]
    return None if all(re.fullmatch(r":?-+:?", c) for c in cells if c) else cells


def parse_plan(text: str) -> Plan:
    plan = Plan(missing=headings_missing(text, PLAN_HEADINGS))
    front = re.match(r"^---\n(.*?)\n---\n", text.replace("\r\n", "\n"), re.S)
    if front:
        plan.complexity = _field(front.group(1).splitlines(), "complexity").lower()
        plan.status = _field(front.group(1).splitlines(), "status").lower()
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
                if REQ_ID.fullmatch(cells[0].strip("*` ")):
                    plan.requirements[cells[0].strip("*` ")] = cells[2] if len(cells) > 2 else ""
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
                                     phase=phase, req=REQ_ID.findall(got.get("req", "")),
                                     completed=got.get("completed", "").strip(), change=got.get("change", ""),
                                     has_req="req" in header))
        elif section.startswith("3.") and (b := re.match(r"^\s*[-*]\s+`([^`]+)`", line)):
            plan.commands.append(b.group(1).strip())
        elif section.startswith("3.") and (cells := _cells(line)):
            if header is None:
                header = [c.lower() for c in cells]
                continue
            got = dict(zip(header, cells, strict=False))
            plan.proof.append((got.get("criterion", ""), got.get("test", "").strip("` "),
                               got.get("command", "").strip("` ")))
        elif section.startswith("4."):
            plan.docs += listed_paths([line])
    return plan


def link_problems(plan: Plan) -> list[str]:
    """Rows against requirements and docs: every row names a requirement of the plan in its `Req` cell, every
    requirement is named by a row, and every document under Docs to update is the file of a `docs` row."""
    bad: list[str] = []
    named: set[str] = set()
    for r in plan.rows:
        if not r.has_req:
            bad.append(f"the task table of `{r.phase}` has no `Req` column")
            continue
        unknown = [q for q in r.req if q not in plan.requirements]
        if not r.req:
            bad.append(f"row `{r.id}` names no requirement in its Req cell")
        elif unknown:
            bad.append(f"row `{r.id}` names {', '.join(unknown)}, which is not a requirement of the plan")
        named |= set(r.req)
    bad += [f"requirement {q} is named by no task row" for q in plan.requirements if q not in named]
    doc_rows = {r.file for r in plan.rows if r.kind == "docs"}
    bad += [f"`{d}` is under Docs to update but no `docs` row changes it" for d in plan.docs if d not in doc_rows]
    return list(dict.fromkeys(bad))


def row_text(row: Row) -> str:
    """What a row says, for comparing it with itself in an earlier commit (KMK-B1, KMK-B2): kind, requirements,
    file, proof and change with whitespace collapsed; the phase heading and the Completed cell are left out."""
    parts = (row.kind, " ".join(row.req), row.file, row.proves, row.change)
    return "\x1f".join(" ".join(p.split()) for p in parts)


def mark_problems(plan: Plan, done: bool, kept: dict[str, str] | None = None) -> list[str]:
    """The plan's status and the rows' Completed marks. Before code (`done` false) the plan is `planned` and a row
    is marked only when `kept` backs the mark: `kept` maps the id of each marked row to `""` (the run's history
    backs it) or to the reason it does not; with `kept` `None`, or a marked row absent from it, no commit of the
    run is known to have written the mark. After code every row carries `✓ <date>` and the plan is `completed`."""
    bad: list[str] = []
    if plan.status not in PLAN_STATUS:
        bad.append(f"the front matter has no `status: {'|'.join(PLAN_STATUS)}`")
    if not done:
        if plan.status in PLAN_STATUS and plan.status != "planned":
            bad.append(f"the plan's status is `{plan.status}` before any code is written; it is `planned`")
        for r in plan.rows:
            if r.completed:
                reason = (kept or {}).get(r.id, "no commit of the run wrote this mark")
                if reason:
                    bad.append(f"row `{r.id}` is marked `{r.completed}` but {reason}")
        return bad
    if plan.status in PLAN_STATUS and plan.status != "completed":
        bad.append(f"the plan's status is `{plan.status}`, not `completed`")
    for r in plan.rows:
        m = DONE_MARK.match(r.completed)
        if not r.completed:
            bad.append(f"row `{r.id}` is not marked completed")
        elif not m:
            bad.append(f"row `{r.id}` is marked `{r.completed}`; a mark is `✓ YYYY-MM-DD`")
    return bad


def scope_cuts(plan: Plan) -> list[str]:
    """Requirements and rows whose words say they do less than asked (`stub`, `for now`, …)."""
    out = [f"requirement {q}: \"{m.group(0)}\"" for q, text in plan.requirements.items() if (m := SCOPE_CUT.search(text))]
    out += [f"row `{r.id}`: \"{m.group(0)}\"" for r in plan.rows if (m := SCOPE_CUT.search(r.change))]
    return out


def plan_facts(plan: Plan, reading_bytes: int = 0) -> dict[str, int]:
    """CDM-B2: the seven numbers the plan rule's Complexity table measures, one for each sign. `reading_bytes` is
    the size of the files and specs the rows name, which only the check can read."""
    return {"phases": len(plan.phases), "rows": len(plan.rows),
            "test_rows": sum(1 for r in plan.rows if r.kind == "test"),
            "files": len({r.file for r in plan.rows if r.file}), "commands": len(plan.commands),
            "reading_bytes": reading_bytes, "heavy_phases": len(plan.heavy)}


def simple_overruns(plan: Plan, reading_bytes: int = 0) -> list[str]:
    """Which measured signs of the plan are over the limit for `simple` (the numbers are `plan_facts`, CDM-B2)."""
    signs = plan_facts(plan, reading_bytes)
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


INVENTORY_PURPOSE_MAX = 300


def inventory(specs: Sequence[tuple[str, str]]) -> str:
    """The capability list: for each spec (path, text), its path, its title, the first sentence of its Purpose (or
    its earlier layout's Overview) and its behaviour headings, without statements or scenarios. Generated from the
    specs, never edited by hand (documents rule 3), so triage and discovery can find the spec that owns a rule."""
    out = ["# Capabilities", "",
           "Generated from the repository's specs at the start of the run. Do not edit: change a spec instead.", ""]
    for path, text in specs:
        title = next((ln[2:].strip() for ln in text.splitlines() if ln.startswith("# ")), path)
        found = sections(text)
        body = found.get("Purpose") or next((v for k, v in found.items() if k.lower().endswith("overview")), [])
        para: list[str] = []
        for ln in body:
            if ln.strip():
                para.append(ln.strip())
            elif para:
                break
        purpose = " ".join(para)
        first = re.split(r"(?<=[.!?])\s", purpose, maxsplit=1)[0][:INVENTORY_PURPOSE_MAX]
        out += [f"## `{path}`: {title}", ""]
        if first:
            out += [first, ""]
        heads = [f"- {m.group(1)}{m.group(2).rstrip()}" for m in map(BEHAVIOUR_HEAD.match, text.splitlines()) if m]
        out += (heads or ["- (no behaviours)"]) + [""]
    return "\n".join(out)


def _section_lines(text: str) -> dict[str, list[tuple[int, str]]]:
    """Level-2 heading (lower case) -> its (line number, line) pairs, outside fenced code."""
    out: dict[str, list[tuple[int, str]]] = {}
    current: list[tuple[int, str]] | None = None
    fenced = False
    for n, line in enumerate(text.splitlines(), 1):
        if line.lstrip().startswith("```"):
            fenced = not fenced
        m = None if fenced else HEADING.match(line)
        if m and len(m.group(1)) <= 2:
            current = out.setdefault(m.group(2).strip().lower(), []) if len(m.group(1)) == 2 else None
            continue
        if current is not None:
            current.append((n, line))
    return out


def _filled(lines: list[tuple[int, str]]) -> list[tuple[int, str]]:
    return [(n, ln) for n, ln in lines if ln.strip() and not ln.strip().startswith("<!--")]


def decision_problems(text: str) -> tuple[list[tuple[int, str, str]], list[tuple[int, str, str]]]:
    """The decision rule's form, read from a decision record: (failures, leads), each (line, message, fix).
    Failures: a section missing or empty; a `Current state` sentence that cites nothing; a constraint with no
    source; fewer than two options, or an option with no `How it works:` line; a force id the rationale never
    names; a risk without `Limited by:` and `Noticed by:`; an assumption without `If wrong:`. Leads: a record over
    about 10 KB, a `Revisit when` that names nothing observable."""
    fails: list[tuple[int, str, str]] = []
    leads: list[tuple[int, str, str]] = []
    secs = _section_lines(text)
    for h in DECISION_HEADINGS:
        if h.lower() not in secs:
            fails.append((1, f"section `## {h}` is missing", f"add `## {h}` as the decision rule says"))
        elif not _filled(secs[h.lower()]) and h != "Options considered":
            fails.append((1, f"section `## {h}` is empty", "fill it, with one line for a small decision"))
    current = _filled(secs.get("current state", []))
    if not (len(current) == 1 and current[0][1].strip().lower().rstrip(".") == "nothing exists yet"):
        for n, line in current:
            body = line.strip().lstrip("-*|").strip()
            for sentence in SENTENCE_END.split(body):
                if sentence.strip() and not CITES.search(sentence):
                    fails.append((n, f"a sentence of `Current state` cites no path, link or id: "
                                     f"`{sentence.strip()[:80]}`", "cite the file, document or id it was read in"))
                    break
    forces: list[str] = []
    for n, line in _filled(secs.get("forces", [])):
        row = FORCE_ROW.match(line)
        if row is None:
            continue
        forces.append(row.group(1) + row.group(2))
        if row.group(1) == "C" and not re.search(r"\bSource\s*:", line, re.I):
            fails.append((n, f"constraint {forces[-1]} names no source", "add `Source:` with the spec id, document, "
                          "file or person it comes from, or move it under `Assumptions`"))
    if "forces" in secs and not forces:
        fails.append((1, "`Forces` lists no force with an id", "list each force as `- C1 (constraint): …` or `- F1: …`"))
    options = _option_blocks(text)
    if "options considered" in secs and len(options) < 2:
        fails.append((1, f"`Options considered` describes {len(options)} option(s) under `###` headings",
                      "compare at least two real options, each under its own `###` heading"))
    for n, title, body in options:
        if not re.search(r"^\s*\**How it works\**\s*:", body, re.I | re.M):
            fails.append((n, f"option `{title}` has no `How it works:` line",
                          "say in one to three sentences what would be built or changed"))
    rationale = " ".join(ln for _, ln in secs.get("decision rationale", []))
    for fid in forces:
        if not re.search(rf"(?<![\w-]){fid}(?![\w-])", rationale):
            fails.append((1, f"`Decision rationale` does not answer force {fid}",
                          f"say whether the chosen option meets {fid} or gives it up, and why"))
    risks = _filled(secs.get("risks", []))
    if not (len(risks) == 1 and risks[0][1].strip().lower().rstrip(".") == "none known"):
        for n, line in risks:
            if re.match(r"^\s*[-*]\s+", line) and not (re.search(r"\bLimited by\s*:", line, re.I)
                                                       and re.search(r"\bNoticed by\s*:", line, re.I)):
                fails.append((n, "a risk does not say what limits it and how it would be noticed",
                              "add `Limited by:` and `Noticed by:`, or write `None known.`"))
    assumptions = _filled(secs.get("assumptions", []))
    if not (len(assumptions) == 1 and assumptions[0][1].strip().lower().rstrip(".") == "none"):
        for n, line in assumptions:
            row = ASSUMPTION_ROW.match(line)
            if row and not re.search(r"\bIf wrong\s*:", line, re.I):
                fails.append((n, f"assumption {row.group(1)} does not say what it costs if wrong",
                              "add `If wrong:` with what it would cost"))
    size = len(text.encode("utf-8"))
    if size > DECISION_CAP_BYTES:
        leads.append((1, f"the record has {size:,} bytes, over about 10 KB", "a longer record holds two decisions: "
                      "split it"))
    for n, line in _filled(secs.get("revisit when", [])):
        vague = VAGUE_REVISIT.search(line)
        if vague:
            leads.append((n, f"`{vague.group(0)}` names nothing observable",
                          "name an event or a measurement that reopens the decision"))
    return fails, leads


def _option_blocks(text: str) -> list[tuple[int, str, str]]:
    """(line, title, body) of each `###` option under `## Options considered`."""
    out: list[tuple[int, str, list[str]]] = []
    inside = False
    for n, line in enumerate(text.splitlines(), 1):
        m = HEADING.match(line)
        if m and len(m.group(1)) == 2:
            inside = m.group(2).strip().lower() == "options considered"
            continue
        if not inside:
            continue
        if m and len(m.group(1)) == 3:
            out.append((n, m.group(2).strip(), []))
        elif out:
            out[-1][2].append(line)
    return [(n, t, "\n".join(b)) for n, t, b in out]
