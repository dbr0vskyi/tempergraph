"""The model-free parts of the independent review unit (IRV-B3, IRV-B4, IRV-B9 to IRV-B11; RVF-B1 to RVF-B7).

The findings document: its parser, its writer, the form check of its `Findings` section and the builder of the committed
document. The reader's inputs: the change since the run's base commit and the task's numbered criteria, written to the
run's own folder `.tempergraph/review/`, which no step commits. The step a blocking finding goes back to, and the text
the step is given as the reason for its visit."""

from __future__ import annotations

import re
import subprocess
from dataclasses import dataclass, field, replace
from pathlib import Path

from . import specfmt as fmt

REVIEW_DIR = Path(".tempergraph") / "review"
DRAFT = (REVIEW_DIR / "findings.md").as_posix()
CHANGE = (REVIEW_DIR / "change.diff").as_posix()
CRITERIA = (REVIEW_DIR / "criteria.md").as_posix()
CHANGE_NAME = "change.diff"
FILES_NAME = "files.txt"
BASE_NAME = "base.txt"
FAILED_NAME = "failed.txt"
FILES = (REVIEW_DIR / FILES_NAME).as_posix()
BASE = (REVIEW_DIR / BASE_NAME).as_posix()
FAILED = (REVIEW_DIR / FAILED_NAME).as_posix()
GIT_TIMEOUT = 120.0
MARKS = ("blocking", "not blocking")
EMPTY_TREE = "4b825dc642cb6eb9a060e54bf8d69288fbb53904"
HAND_OVER = re.compile(r"\.(?:triage|setup|handoff|report|review|plan)\.md$")
ITEM = re.compile(r"^\s*(\d+)[.)]\s+(.*?)\s*$")
LOCATION = re.compile(r"^`([^`]*)`\s*(.*)$")
RESULT = re.compile(r"\s+Visit:\s*(built|refused)\s*$")
RUN_COMMIT = re.compile(r"^\w+\(temperspec\)!?:\s*(\w+) for (.+)$")


@dataclass
class Finding:
    number: int
    file: str
    line: int | None
    mark: str
    text: str
    result: str = ""

    @property
    def blocking(self) -> bool:
        return self.mark == "blocking"


@dataclass
class Review:
    findings: list[Finding] = field(default_factory=list)
    earlier: list[Finding] = field(default_factory=list)
    sections: dict[str, list[str]] = field(default_factory=dict)

    @property
    def none(self) -> bool:
        return [ln.strip() for ln in self.sections.get("Findings", []) if ln.strip()] == ["None"]


def format_finding(f: Finding) -> str:
    """One item of the document (RVF-B2); a visit result ends the line (RVF-B7)."""
    line = f"{f.number}. `{f.file}:{f.line}` {f.mark}: {f.text}"
    return f"{line} Visit: {f.result}" if f.result else line


def parse_item(line: str) -> Finding | None:
    """A numbered line as a finding, read leniently: a missing part is empty so that the form check can name it."""
    m = ITEM.match(line)
    if not m:
        return None
    rest = m.group(2)
    result = ""
    r = RESULT.search(rest)
    if r:
        result, rest = r.group(1), rest[:r.start()]
    file, line_no = "", None
    loc = LOCATION.match(rest)
    if loc:
        place, rest = loc.group(1).strip(), loc.group(2)
        head, sep, tail = place.rpartition(":")
        if sep and tail.strip().isdigit():
            file, line_no = head.strip(), int(tail)
        else:
            file = place
    mark, text = "", rest.strip()
    head, sep, tail = rest.partition(":")
    if sep:
        mark, text = head.strip(), tail.strip()
    return Finding(int(m.group(1)), file, line_no, mark, text, result)


def _items(lines: list[str]) -> list[Finding]:
    return [f for f in (parse_item(ln) for ln in lines) if f is not None]


def parse_document(text: str) -> Review:
    sections = fmt.sections(text)
    return Review(findings=_items(sections.get("Findings", [])), earlier=_items(sections.get("Earlier review", [])),
                  sections=sections)


def _file_lines(workdir: Path, rel: str) -> int | None:
    root = workdir.resolve()
    path = (root / rel).resolve()
    if not rel or root not in path.parents or not path.is_file():
        return None
    return len(path.read_text(encoding="utf-8", errors="replace").splitlines())


def form_problems(text: str, workdir: Path) -> list[tuple[str, str]]:
    """(place, message) for each refusal of the `Findings` section (RVF-B3 to RVF-B5): the place is the section or
    `finding <n>`."""
    doc = parse_document(text)
    if "Findings" not in doc.sections:
        return [("Findings", "the document has no `Findings` section")]
    lines = [ln for ln in doc.sections["Findings"] if ln.strip()]
    if not lines:
        return [("Findings", "the `Findings` section is empty; write the single word `None` when nothing was found")]
    if doc.none:
        return []
    if not doc.findings:
        return [("Findings", "the `Findings` section holds no numbered finding and not the single word `None`")]
    problems: list[tuple[str, str]] = []
    for index, f in enumerate(doc.findings, start=1):
        bad: list[str] = []
        if f.number != index:
            bad.append(f"numbered {f.number} where {index} comes next")
        count = _file_lines(workdir, f.file) if f.file else None
        if not f.file:
            bad.append("names no file")
        elif count is None:
            bad.append(f"names `{f.file}`, which is not a file of the branch")
        if f.line is None:
            bad.append("names no line")
        elif count is not None and not 1 <= f.line <= count:
            bad.append(f"names line {f.line}, outside `{f.file}` ({count} lines)")
        if f.mark not in MARKS:
            bad.append(f"is marked `{f.mark}`, not `blocking` or `not blocking`" if f.mark else "has no mark")
        if bad:
            problems.append((f"finding {f.number}", f"finding {f.number} " + "; ".join(bad)))
    return problems


def build_document(task: str, draft: str, earlier_doc: str | None, built: bool) -> str:
    """The committed document (RVF-B1, RVF-B6, RVF-B7): the draft's findings under `Findings`, and when a document of
    an earlier review is given, its findings under `Earlier review` as it gave them, each blocking one ending with the
    visit's result."""
    draft_lines = list(fmt.sections(draft).get("Findings", []))
    body = "\n".join(draft_lines).strip()
    out = [f"# Review: {task}", "", "## Findings", "", body, ""]
    kept = parse_document(earlier_doc).findings if earlier_doc else []
    if kept:
        word = "built" if built else "refused"
        out += ["## Earlier review", ""]
        out += [format_finding(replace(f, result=word if f.blocking else "")) for f in kept]
        out.append("")
    return "\n".join(out)


# -- the reader's inputs (IRV-B3, IRV-B4) -------------------------------------------------------------------------


def _git(workdir: Path, *args: str) -> str:
    done = subprocess.run(["git", *args], cwd=workdir, capture_output=True, text=True, timeout=120,
                          stdin=subprocess.DEVNULL, check=False)
    return done.stdout if done.returncode == 0 else ""


def run_base(workdir: Path, task: str) -> tuple[str, list[str]]:
    """The run's base commit and the paths its prepare commit wrote or changed, found from the commit subjects the run
    writes: the commits at the tip of the branch that end `for <task>` belong to the run, and the base is the parent of
    the oldest of them. ("", []) when the branch holds none."""
    name = re.sub(r"[^A-Za-z0-9._-]+", "-", task or "task")[:60]
    run: list[tuple[str, str, str]] = []
    for row in _git(workdir, "log", "-n", "500", "--format=%H%x09%P%x09%s").splitlines():
        commit, _, rest = row.partition("\t")
        parents, _, subject = rest.partition("\t")
        m = RUN_COMMIT.match(subject)
        if not m or m.group(2) != name:
            break
        run.append((commit, parents.split()[0] if parents.split() else EMPTY_TREE, m.group(1)))
    if not run:
        return "", []
    prepared: list[str] = []
    for commit, _, step in run:
        if step == "prepare":
            prepared += [p for p in _git(workdir, "show", "--name-only", "--format=", commit).splitlines() if p.strip()]
    return run[-1][1], sorted(set(prepared))


def criteria_text(triage: str) -> str:
    """The task's acceptance criteria as the triage note numbers them, and nothing else of the note."""
    out: list[str] = []
    for line in fmt.sections(triage).get("Acceptance criteria", []):
        if ITEM.match(line) or (out and line.strip() and line[:1].isspace()):
            out.append(line.rstrip())
    return "# Acceptance criteria\n\n" + "\n".join(out) + "\n"


class GitFailed(Exception):
    """A git command of the inputs failed or did not finish; the message is the command and the reason."""


def _strict_git(workdir: Path, *args: str) -> str:
    command = "git " + " ".join(args)
    try:
        done = subprocess.run(["git", *args], cwd=workdir, capture_output=True, text=True, timeout=GIT_TIMEOUT,
                              stdin=subprocess.DEVNULL, check=False)
    except subprocess.TimeoutExpired as exc:
        raise GitFailed(f"{command}: timed out after {GIT_TIMEOUT:g} seconds") from exc
    except OSError as exc:
        raise GitFailed(f"{command}: could not be run ({type(exc).__name__})") from exc
    if done.returncode != 0:
        raise GitFailed(f"{command}: exit status {done.returncode}")
    return done.stdout


def prepared_files(workdir: Path, base: str, task: str) -> list[str]:
    """The paths the run's prepare commits between `base` and the head wrote or changed (IRV-B3); strict about git."""
    name = re.sub(r"[^A-Za-z0-9._-]+", "-", task or "task")[:60]
    out: set[str] = set()
    for row in _strict_git(workdir, "log", "--format=%H%x09%s", f"{base}..HEAD").splitlines():
        commit, _, subject = row.partition("\t")
        m = RUN_COMMIT.match(subject)
        if m and m.group(1) == "prepare" and m.group(2) == name:
            out.update(p for p in _strict_git(workdir, "show", "--name-only", "--format=", commit).splitlines()
                       if p.strip())
    return sorted(out)


def _generated(path: str, outputs: list[str]) -> bool:
    return any(path == o or path.startswith(o + "/") for o in outputs)


def _clear_inputs(folder: Path) -> None:
    for name in (CHANGE_NAME, FILES_NAME, BASE_NAME, FAILED_NAME):
        (folder / name).unlink(missing_ok=True)


def write_inputs(workdir: Path, task: str, triage: str, base: str) -> list[str]:
    """Write `.tempergraph/review/` (`change.diff`, `files.txt`, `base.txt`, `criteria.md`) and return the paths the
    change touches. The change is the diff since the engine's base commit without the hand-over documents and without
    the files the run's prepare commits wrote or changed. A failing or timed-out git leaves `failed.txt` and no change
    (IRV-B18, IRV-B19); no base commit leaves no change."""
    from . import regeneration

    folder = workdir / REVIEW_DIR
    folder.mkdir(parents=True, exist_ok=True)
    (folder / ".gitignore").write_text("*\n", encoding="utf-8")
    _clear_inputs(folder)
    changed: list[str] = []
    if base:
        try:
            prepared = set(prepared_files(workdir, base, task))
            names = _strict_git(workdir, "diff", "--no-renames", "--name-only", "-z", base, "HEAD").split("\0")
            changed = [p for p in names if p and not HAND_OVER.search(p) and p not in prepared
                       and not p.startswith(".tempergraph/")]
            counts: dict[str, str] = {}
            if changed:
                parts = _strict_git(workdir, "diff", "--numstat", "-z", "--no-renames", base, "HEAD",
                                    "--", *changed).split("\0")
                for part in parts:
                    fields = part.split("\t", 2)
                    if len(fields) == 3:
                        added, removed, path = fields
                        counts[path] = "+0 -0" if added == "-" else f"+{added} -{removed}"
            diff = (_strict_git(workdir, "diff", "--no-color", "--no-renames", base, "HEAD", "--", *changed)
                    if changed else "")
            outputs = regeneration.declared_outputs(workdir)
            ordered = [p for p in changed if not _generated(p, outputs)] + [p for p in changed if _generated(p, outputs)]
            rows = [f"{counts.get(p, '+0 -0')} {p}" + (" [generated]" if _generated(p, outputs) else "")
                    for p in ordered]
            (folder / CHANGE_NAME).write_text(diff, encoding="utf-8")
            (folder / FILES_NAME).write_text("".join(r + "\n" for r in rows), encoding="utf-8")
            (folder / BASE_NAME).write_text(base + "\n", encoding="utf-8")
        except GitFailed as exc:
            _clear_inputs(folder)
            (folder / FAILED_NAME).write_text(str(exc) + "\n", encoding="utf-8")
            changed = []
    try:
        note = (workdir / triage).read_text(encoding="utf-8")
    except OSError:
        note = ""
    (folder / "criteria.md").write_text(criteria_text(note), encoding="utf-8")
    return changed


# -- the step a blocking finding goes back to (IRV-B9 to IRV-B11) ---------------------------------------------------


def choose_step(findings: list[Finding], changed: list[str]) -> str:
    """`code` when every blocking finding names a file the change touches, `plan` when any names another, `""` when no
    finding blocks."""
    blocking = [f for f in findings if f.blocking]
    if not blocking:
        return ""
    touched = set(changed)
    return "code" if all(f.file in touched for f in blocking) else "plan"


def reason_text(findings: list[Finding]) -> str:
    """Each blocking finding with its number, file, line and text, in the order of the document."""
    return "\n".join(f"{f.number}. `{f.file}:{f.line}` {f.text}" for f in findings if f.blocking)
