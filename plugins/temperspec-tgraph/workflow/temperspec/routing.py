"""The hand-written routes (the route after the plan is the engine's switch `code_mode`, not one of them), the
scripts the engine runs around a step, and the last stage. Plain functions of their context: no model, no request
text."""

from __future__ import annotations

import json
import os
import re
import shutil
import subprocess
import tempfile
from dataclasses import dataclass
from pathlib import Path
from typing import Any

from tempergraph.api import FinalizerResult

from . import specfmt, summary

PACKAGE = Path(__file__).resolve().parents[2]
RULES = "rules"
REPO_RULES = Path(".claude") / "rules" / "temperspec"
COMMIT_TYPE = {"code": "feat", "phase": "feat"}
CONTEXT_FILES = ("CLAUDE.md", "AGENTS.md")
SKIP_DIRS = {".git", ".tempergraph", ".claude", "node_modules", ".venv", "venv", "evals", "fixtures"}
DEFAULT_SPECS = "docs/specs/"
BESIDE_SPECS = ("adr", "research", "plans", "tasks")
SAFE_REF = re.compile(r"^[A-Za-z0-9][A-Za-z0-9._/-]{0,200}$")
URL = re.compile(r"https://\S+/pull/\d+")
PLAIN_PATH = re.compile(r"^[A-Za-z0-9._/:\\-]+$")


# -- routes ---------------------------------------------------------------------------------------


def route_setup(view: Any) -> str:
    """A repository with no overview spec is set up first, and its setup starts with `list_components`, which lists
    the folders the reading sessions read before `setup` writes the specs; every other run starts at triage."""
    return "list_components" if "setup_needed" in view.artifact_keys else "triage"


def route_triage(view: Any) -> str:
    """A quick task goes straight to code; no gap goes to the plan; a task whose every gap a spec answers takes the
    short visit; any other gap, and a docs-only task, goes to the full discovery, whose entry is `owner_questions`:
    it lists what the owner is asked, `ask_route` sends a run with a question to the pause and any other to
    `read_gap` (spec `owner-questions`, OWQ-B1, OWQ-B2)."""
    route = view.values.get("route")
    if route == "discovery" and view.values.get("covered") == "yes":
        return "discovery_short"
    return {"quick": "code", "plan": "plan"}.get(route, "owner_questions")


def route_ask(view: Any) -> str:
    """A run whose list of questions holds one goes to the pause `ask_owner`; every other run goes on to the reading
    sessions at `read_gap` with no pause (OWQ-B1, OWQ-B2). `owner_questions` leaves the key `empty` only when its list
    holds no question, and a script's keys reach a route as artifact keys, as `setup_needed` does for `route_setup`;
    a value `empty` of `yes` is read as well. A run with neither goes to the pause, whose own reader refuses a list
    it cannot read, so a failed list is never skipped in silence."""
    return "read_gap" if "empty" in view.artifact_keys or view.values.get("empty") == "yes" else "ask_owner"


def route_short(view: Any) -> str:
    """A short visit that confirmed every gap goes to the plan; one that found a gap not answered hands it to the
    full discovery, whose entry is `read_gap` (skipped with no item for fewer than two gaps). An unreadable value
    takes the longer path."""
    return "plan" if view.values.get("settled") == "yes" else "read_gap"


def gap_items(ctx: Any) -> list[dict[str, str]]:
    """The items of `read_gap`: one for each gap row of the triage note, with the id `G<n>` of its first number
    and the row as its text, in the order of the rows. A later row with a number already seen is dropped. Fewer
    than two rows give no item, so no reading session starts (PRL-B2)."""
    rows = specfmt.gap_rows(Path(ctx.artifact).read_text(encoding="utf-8", errors="replace"))
    items: dict[str, str] = {}
    for row in rows:
        number = re.search(r"G\d+", row)
        if number is not None and number.group(0) not in items:
            items[number.group(0)] = row.strip()
    return [{"id": gid, "text": text} for gid, text in items.items()] if len(items) >= 2 else []


@dataclass(frozen=True)
class PhaseBlock:
    """One phase of a plan: the item id the map `phase` gives it, its heading (as the plan's rows name it as their
    phase), its goal and its weight."""

    id: str
    heading: str
    goal: str
    weight: str


def phase_blocks(text: str) -> list[PhaseBlock]:
    """The phases of a plan in plan order, each with the id `p<n>` of the number of its `Phase <n>` heading (PHC-B1). A
    heading with no number, or with a number an earlier phase already took, gets `p<position>` instead, made unique,
    so that no id repeats and the list is never shorter than the phases (MAP-B8)."""
    heads = specfmt.parse_plan(text).phases
    goals: dict[str, tuple[str, str]] = {}
    section, current = "", ""
    for line in text.splitlines():
        found = specfmt.HEADING.match(line)
        if found and len(found.group(1)) == 2:
            section, current = found.group(2).strip().lower(), ""
        elif found and len(found.group(1)) == 3 and section.startswith("2."):
            current = found.group(2).strip()
            goals.setdefault(current, ("", ""))
        elif current and (m := re.match(r"^\s*[-*]?\s*\**(Goal|Weight)\**\s*:\s*(.*)$", line, re.I)):
            goal, weight = goals[current]
            goals[current] = (m.group(2).strip(), weight) if m.group(1).lower() == "goal" else (
                goal, m.group(2).strip())
    out: list[PhaseBlock] = []
    used: set[str] = set()
    for position, heading in enumerate(heads, start=1):
        number = re.match(r"\s*Phase\s+(\d+)", heading, re.I)
        pid = f"p{number.group(1)}" if number else f"p{position}"
        if pid in used:
            pid = f"p{position}"
        tail = 1
        while pid in used:
            tail += 1
            pid = f"p{position}-{tail}"
        used.add(pid)
        goal, weight = goals.get(heading, ("", ""))
        out.append(PhaseBlock(id=pid, heading=heading, goal=goal, weight=weight))
    return out


def phase_items(ctx: Any) -> list[dict[str, str]]:
    """The items of the map `phase`: one for each phase of the expanded plan at `ctx.artifact`, in plan order, with the
    id `p<n>` of its heading's number and as text its heading, goal and weight with the plan's path (PHC-B1, PHC-B2).
    The path of the triage note is not known to an extractor; the prompt carries it."""
    plan = Path(ctx.artifact)
    try:
        shown = plan.resolve().relative_to(Path(ctx.workdir).resolve()).as_posix()
    except ValueError:
        shown = str(plan)
    blocks = phase_blocks(plan.read_text(encoding="utf-8", errors="replace"))
    return [{"id": b.id, "text": f"{b.heading}\nGoal: {b.goal}\nWeight: {b.weight}\nPlan: `{shown}`"} for b in blocks]


NOT_COMPONENTS = {"node_modules", ".venv", "venv", "vendor", "dist", "build", "target", "out", "__pycache__", "docs"}
COMPONENT_LIST = Path(".tempergraph") / "component_list.json"


def list_components(ctx: Any) -> dict[str, str]:
    """The script unit before `read_component`: the top-level folders of the repository that are not hidden, not
    a dependency, build-output or documentation folder, as the list the map reads, in alphabetical order. Fewer
    than two folders give an empty list, so no reading session starts (PRL-B4, PRL-B5)."""
    workdir = Path(ctx.workdir)
    names = sorted(p.name for p in workdir.iterdir()
                   if p.is_dir() and not p.name.startswith(".") and p.name not in NOT_COMPONENTS)
    items: list[dict[str, str]] = []
    used: set[str] = set()
    for name in names if len(names) >= 2 else []:
        base = re.sub(r"[^A-Za-z0-9_-]", "-", name)[:40]
        if not base[:1].isalnum():
            base = ("d" + base)[:40]
        gid, n = base, 1
        while gid in used:
            n += 1
            tail = f"-{n}"
            gid = base[: 40 - len(tail)] + tail
        used.add(gid)
        items.append({"id": gid, "text": name})
    target = workdir / COMPONENT_LIST
    target.parent.mkdir(parents=True, exist_ok=True)
    target.write_text(json.dumps(items, indent=2) + "\n", encoding="utf-8")
    (target.parent / ".gitignore").write_text("*\n", encoding="utf-8")  # commit_step excludes the folder as well
    return {"component_list": COMPONENT_LIST.as_posix()}


CAPABILITIES = Path(".tempergraph") / "capabilities.md"


def write_inventory(workdir: Path) -> None:
    """The capability list of every spec of the repository, written to the run's own folder, which no step commits;
    a repository with no spec gets a list that says so."""
    root = Path(workdir)
    specs = [(path + name, (root / path / name).read_text(encoding="utf-8", errors="replace"))
             for path, files in _folders(root) for name in sorted(files) if name.endswith(".spec.md")]
    target = root / CAPABILITIES
    target.parent.mkdir(parents=True, exist_ok=True)
    target.write_text(specfmt.inventory(specs), encoding="utf-8")
    (target.parent / ".gitignore").write_text("*\n", encoding="utf-8")


QUESTION_LIST = Path(".tempergraph") / "question_list.json"
MAX_QUESTIONS = 20  # the engine's ask takes 1 to 20 questions (ASK-B5)
MAX_WORDING = 500  # and a wording of at most 500 characters
ASKING = ("blocking", "always")


def _shorten(text: str, room: int) -> str:
    return text if len(text) <= room else text[: max(room - 1, 0)].rstrip() + "…"


def _wording(gap: str, question: str, options: list[tuple[str, str]]) -> str:
    """OWQ-B3: the gap's id, the question and each option with its label, in the order of the note. Over 500
    characters the options' own words are shortened, never a label; a question too long for even that is cut last."""
    head = f"{gap}: {question}".strip()
    texts = [t for _, t in options]

    def built(ts: list[str], q: str) -> str:
        return " ".join([q, *(f"{lab}) {t}".rstrip() for (lab, _), t in zip(options, ts, strict=True))])

    out = built(texts, head)
    while len(out) > MAX_WORDING and any(len(t) > 1 for t in texts):
        longest = max(range(len(texts)), key=lambda i: len(texts[i]))
        texts[longest] = _shorten(texts[longest], max(len(texts[longest]) - (len(out) - MAX_WORDING), 1))
        out = built(texts, head)
    if len(out) > MAX_WORDING:  # the labels and the gap id alone fill it: cut the question
        room = MAX_WORDING - len(built(texts, f"{gap}: ").rstrip()) - 1
        out = built(texts, f"{gap}: {_shorten(question, max(room, 1))}")
    return out[:MAX_WORDING]


def _labelled(options: list[tuple[str, str]]) -> list[tuple[str, str]]:
    """An option written with no label takes `a`, `b`, … by its place."""
    return [(lab or chr(ord("a") + i), text) for i, (lab, text) in enumerate(options)]


def owner_questions(ctx: Any) -> dict[str, str]:
    """The script unit after triage: the questions of the one pause, as JSON in the engine's `Question` shape
    (OWQ-B2 to OWQ-B6). Each owner decision of the triage note is one `choice` question named by its gap's id in
    lower case, with the labels of its options as choices, its default, and the gap, the question and the labelled
    options as its wording; under `always` each gap row that says findable and does not say `Covered by` then gets a
    question with the choices `right` and `wrong`. At most 20, the decisions first. `never` lists none. It says whether
    the list holds no question by leaving the key `empty` (`yes`) only then, which `ask_route` reads."""
    workdir = Path(ctx.workdir)
    pointer = ((ctx.artifacts or {}).get("triage") or {}).get("triage_note")
    try:
        text = (workdir / str(pointer)).read_text(encoding="utf-8", errors="replace")
    except OSError:
        text = ""
    conversation = (ctx.settings or {}).get("conversation")
    questions: list[dict[str, Any]] = []
    if text and conversation in ASKING:
        note = specfmt.parse_triage(text)
        seen: set[str] = set()
        for entry in note.owners:
            options = _labelled(entry.options)
            name = entry.gap.lower()
            if note.sorts.get(entry.gap) == "findable" or len(options) < 2 or name in seen:
                continue
            chosen = next((lab for lab, t in options if t == entry.default_text and t), options[0][0])
            seen.add(name)
            questions.append({"name": name, "text": _wording(entry.gap, entry.question, options), "kind": "choice",
                              "choices": [lab for lab, _ in options], "required": True, "default": chosen})
        if conversation == "always":
            for row in specfmt.gap_rows(text):
                gap = specfmt.GAP_ID.search(row)
                if gap is None or gap.group(0).lower() in seen or note.sorts.get(gap.group(0)) != "findable" \
                        or specfmt.COVERED_WORDS.search(row):
                    continue
                seen.add(gap.group(0).lower())
                row_text = re.sub(r"^\W+", "", row.strip())
                question = f"Is this reading of {gap.group(0)} right? {row_text}"
                questions.append({"name": gap.group(0).lower(), "text": _shorten(question, MAX_WORDING),
                                  "kind": "choice", "choices": ["right", "wrong"], "required": True,
                                  "default": "right"})
    questions = questions[:MAX_QUESTIONS]
    target = workdir / QUESTION_LIST
    target.parent.mkdir(parents=True, exist_ok=True)
    target.write_text(json.dumps(questions, indent=2) + "\n", encoding="utf-8")
    (target.parent / ".gitignore").write_text("*\n", encoding="utf-8")  # commit_step excludes the folder as well
    return {"question_list": QUESTION_LIST.as_posix(), **({} if questions else {"empty": "yes"})}


def route_discovery(view: Any) -> str:
    """A docs-only run ends after discovery; every other run is planned."""
    return "finalizer" if view.values.get("route") == "discovery-only" else "plan"


def code_join(ctx: Any) -> dict[str, str]:
    """The unit both arms of the switch `code_mode` reach after `code`: a model-free no-op. The engine's `joins_at`
    may not be the entry of an arm, so the arms `single` (to `code`) and `phases` (to `expand`) meet here."""
    return {}


# -- scripts the engine runs around a step --------------------------------------------------------


def _git(workdir: Path, *args: str) -> subprocess.CompletedProcess[str]:
    return subprocess.run(["git", *args], cwd=workdir, capture_output=True, text=True, timeout=120,  # noqa: S603, S607
                          stdin=subprocess.DEVNULL)


def _folders(workdir: Path) -> list[tuple[str, list[str]]]:
    """Every folder of the repository outside the folders of copies and fixtures, as (path from the repository root
    with a closing `/`, `""` for the root; the names of its files), in path order."""
    out: list[tuple[str, list[str]]] = []
    root = Path(workdir)
    for folder, dirs, files in os.walk(root):
        dirs[:] = sorted(d for d in dirs if d not in SKIP_DIRS)
        rel = Path(folder).relative_to(root).as_posix()
        out.append(("" if rel == "." else rel + "/", files))
    return sorted(out, key=lambda item: item[0])


def specs_folders(workdir: Path) -> list[str]:
    """PNR-B1: where the repository keeps its specs, in path order: the folder of each overview spec, else the
    folders of its other specs, else `docs/specs/`."""
    folders = _folders(workdir)
    overviews = [path for path, files in folders if any(n.endswith("overview.spec.md") for n in files)]
    others = [path for path, files in folders if any(n.endswith(".spec.md") for n in files)]
    return overviews or others or [DEFAULT_SPECS]


def rules_held(workdir: Path) -> str | None:
    """PNR-B3, PNR-B4: where the repository holds the rule files, or None when it holds none: its own rule folder, else
    the first folder of the repository that holds every rule file temperspec ships. The machine's rule folder does not
    count: a step session cannot open a file outside its working directory."""
    root = Path(workdir)
    own = REPO_RULES.as_posix() + "/"
    if (root / REPO_RULES).is_dir():
        return own
    wanted = {p.name for p in (PACKAGE / RULES).glob("*.rule.md")}
    for path, files in _folders(root):
        if path and wanted <= set(files):
            return path
    return None


def templates_named(workdir: Path) -> bool:
    """PNR-B5: whether the fill-in templates folder holds templates."""
    return any((Path(workdir) / specfmt.TEMPLATE_DIR).glob("*.template.md"))


def _beside(folder: str) -> list[str]:
    """The folders beside a specs folder (PNR-B2), named whether or not they exist."""
    parent = folder.rstrip("/").rpartition("/")[0]
    return [(parent + "/" if parent else "") + name + "/" for name in BESIDE_SPECS]


def context_block(workdir: Path) -> str:
    """The temperspec block of the project-context file, written from the repository's own layout (PNR-B1 to PNR-B5)."""
    kinds = ("specs", "decision records", "research notes", "plans", "task notes")
    lines = "\n".join(
        "  - " + ", ".join(f"{kind} `{path}`" for kind, path in zip(kinds, [folder, *_beside(folder)], strict=True))
        for folder in specs_folders(workdir))
    held = rules_held(workdir) or REPO_RULES.as_posix() + "/"
    where = f"`{held}`"
    templates = f"; fill-in templates generated from them are in `{specfmt.TEMPLATE_DIR}/`" if templates_named(
        workdir) else ""
    return f"""{specfmt.CONTEXT_START}
## temperspec

This repository is developed with temperspec: a change goes from a task with acceptance criteria through
behaviour specs and a plan to tested code.

- Specs (`*.spec.md`) start at the overview spec. Each docs directory belongs to its own part of the repository: a
  change's documents go to the directories of the part it changes.
{lines}
- How each document is written: the rule files in {where}{templates}.
- When two sources disagree: the task's acceptance criteria, then specs and decision records, then the plan,
  then the code. A code change that makes a spec false changes the spec in the same change.
- A test that proves an acceptance criterion of a spec carries the criterion's id.
- Start a run with `tempergraph run temperspec "<the task and its acceptance criteria>"`.
{specfmt.CONTEXT_END}
"""


def install_rules(ctx: Any) -> dict[str, str]:
    """Put the rule files, and the templates generated from their examples, into the repository unless the repository
    already holds them (PNR-B3), whether or not the machine holds them (PNR-B7); a partial set installs the whole set."""
    if rules_held(Path(ctx.workdir)) is not None:
        return {}
    target = Path(ctx.workdir) / REPO_RULES
    target.mkdir(parents=True)
    templates = Path(ctx.workdir) / specfmt.TEMPLATE_DIR
    for src in sorted((PACKAGE / RULES).glob("*.rule.md")):
        shutil.copyfile(src, target / src.name)
        for name, body in specfmt.rule_templates(src.name.split(".")[0], src.read_text(encoding="utf-8")).items():
            if not (templates / name).exists():  # a repository's own template is kept
                templates.mkdir(parents=True, exist_ok=True)
                (templates / name).write_text(body, encoding="utf-8")
    return {}


def has_overview(workdir: Path) -> bool:
    """Whether the repository holds an overview spec (`overview.spec.md`, with or without a number prefix)."""
    return any(n.endswith("overview.spec.md") for _, files in _folders(workdir) for n in files)


def _names_specs(text: str, workdir: Path) -> bool:
    """PNR-B6: whether the text, leaving out any temperspec block, names by its whole path from the repository root a
    specs folder or the folder that contains it (never the repository root). A path counts from a path boundary on
    and up to one, or on into a longer path."""
    own = re.sub(f"{re.escape(specfmt.CONTEXT_START)}.*?{re.escape(specfmt.CONTEXT_END)}", "", text, flags=re.S)
    for folder in specs_folders(workdir):
        parent = folder.rstrip("/").rpartition("/")[0]
        for path in (folder.rstrip("/"), parent):
            if path and re.search(rf"(?<![A-Za-z0-9._/-]){re.escape(path)}(?![A-Za-z0-9._-])", own):
                return True
    return False


def write_context(workdir: Path) -> str:
    """Keep the temperspec block in the project-context file: added once, replaced in place afterwards, and not
    written at all when the file, apart from any block, already names where the specs are (PNR-B6)."""
    target = next((workdir / n for n in CONTEXT_FILES if (workdir / n).is_file()), workdir / CONTEXT_FILES[0])
    text = target.read_text(encoding="utf-8") if target.is_file() else ""
    if _names_specs(text, workdir):
        return target.name
    block = context_block(workdir)
    start, end = text.find(specfmt.CONTEXT_START), text.find(specfmt.CONTEXT_END)
    if start >= 0 and end > start:
        new = text[:start] + block.rstrip("\n") + text[end + len(specfmt.CONTEXT_END):]
    else:
        new = (text.rstrip("\n") + "\n\n" if text.strip() else "") + block
    if new != text:
        target.write_text(new, encoding="utf-8")
    return target.name


COMMANDS_FILE = "tempergraph.commands.json"
PYTHON_PROJECT_FILES = ("pyproject.toml", "setup.py", "setup.cfg", "requirements.txt", "Pipfile")
PYTHON_COMMANDS = ["pytest", "python -m pytest", "python3 -m pytest", "ruff check", "ruff format --check", "mypy"]


def commands_file_text() -> str:
    """The text prepare writes as the repository's commands file (RCM-B6): the same bytes in every repository."""
    return json.dumps({"schema_version": 1, "commands": PYTHON_COMMANDS}, indent=2) + "\n"


def is_python(workdir: Path) -> bool:
    """RCM-B6, RCM-B8: whether a Python project file is in the repository root or in a folder that is not a folder of
    copies or fixtures."""
    return any(name in files for _, files in _folders(workdir) for name in PYTHON_PROJECT_FILES)


def write_commands(workdir: Path) -> bool:
    """RCM-B6 to RCM-B8: write the Python commands file at the root of a Python repository that has none; an existing
    file, valid or not, and a repository that is not Python are left as they are."""
    target = Path(workdir) / COMMANDS_FILE
    if target.exists() or target.is_symlink() or not is_python(workdir):
        return False
    target.write_text(commands_file_text(), encoding="utf-8")
    return True


def prepare(ctx: Any) -> dict[str, str]:
    """The first unit, with no session: install the rule files unless the repository holds them (the machine's folder
    does not count), keep
    the temperspec block in the project-context file unless it already says where the specs are, write the commands
    file of a Python repository that has none, commit what changed, and say whether the repository still needs its
    overview and specs."""
    workdir = Path(ctx.workdir)
    install_rules(ctx)
    write_context(workdir)
    write_commands(workdir)
    write_inventory(workdir)
    commit_step(ctx)
    return {"setup_ready": "yes"} if has_overview(workdir) else {"setup_needed": "yes"}


def commit_step(ctx: Any) -> dict[str, str]:
    """After each step: commit everything the step left, on the run's branch. Nothing is pushed here."""
    workdir = Path(ctx.workdir)
    # git 2.39 exits 1 on an exclude pathspec that names an ignored path, so the state folder is left out by the
    # pathspec only where git does not already ignore it
    ignored = _git(workdir, "check-ignore", ".tempergraph/").stdout.strip()
    added = _git(workdir, "add", "-A", "--", ".", *([] if ignored else [":(exclude).tempergraph"]))
    if added.returncode != 0:
        raise RuntimeError(f"git add: {added.stderr.strip()[:200]}")
    if _git(workdir, "diff", "--cached", "--quiet").returncode == 0:
        return {}
    task = re.sub(r"[^A-Za-z0-9._-]+", "-", str((ctx.request or {}).get("task_id") or "task"))[:60]
    message = f"{COMMIT_TYPE.get(ctx.unit, 'docs')}(temperspec): {ctx.unit} for {task}"
    who = [] if _git(workdir, "config", "user.email").stdout.strip() else [
        "-c", "user.name=temperspec", "-c", "user.email=temperspec@localhost"]
    done = _git(workdir, *who, "commit", "-q", "-m", message)
    if done.returncode != 0:
        raise RuntimeError(f"git commit: {(done.stderr or done.stdout).strip()[:200]}")
    return {}


# -- the last stage -------------------------------------------------------------------------------


def _passed(run: Any) -> bool:
    return bool(run.finished) and run.exit_code == 0


def _body_file(ctx: Any) -> str:
    """The pull request description, written outside the repository; empty when it cannot be written."""
    try:
        folder = Path(ctx.out_dir) if ctx.out_dir else Path(tempfile.mkdtemp(prefix="temperspec-"))
        folder.mkdir(parents=True, exist_ok=True)
        path = folder / "pull-request.md"
        path.write_text(summary.build(ctx), encoding="utf-8")
    except Exception:  # noqa: BLE001 - a description is never worth a failed last stage
        return ""
    return str(path) if PLAIN_PATH.match(str(path)) else ""


def finalize(ctx: Any) -> FinalizerResult:
    """Push the run's branch and open a draft pull request, or reuse the open one, with a description of what
    the owner has to read. A repository with no remote, or a host with no `gh`, ends with the branch and the
    steps a person takes by hand."""
    branch = ctx.branch or ctx.git.branch
    if not SAFE_REF.match(branch or ""):
        return FinalizerResult(outcome="skipped", reason="the run has no branch name that can be pushed")
    if "origin" not in str(ctx.run("git remote").tail).split():
        return FinalizerResult(outcome="skipped", reason=f"no remote named origin; the commits are on {branch}",
                               manual_steps=[f"add a remote, then `git push -u origin {branch}`"])
    if not _passed(ctx.run(f"git push -u origin {branch}")):
        return FinalizerResult(outcome="skipped", reason=f"the push of {branch} failed; the commits are local",
                               manual_steps=[f"`git push -u origin {branch}`, then open a draft pull request"])
    listed = ctx.run(f"gh pr list --head {branch} --state open --json url --limit 1")
    found = URL.search(str(listed.tail)) if _passed(listed) else None
    body = _body_file(ctx)
    if found:
        told = bool(body) and _passed(ctx.run(f"gh pr edit {found.group(0)} --body-file {body}"))
        return FinalizerResult(outcome="reused", url=found.group(0),
                               reason=f"{branch} pushed to its open pull request"
                               + ("" if told else "; its description was not updated"))
    base = f" --base {ctx.base}" if SAFE_REF.match(ctx.base or "") else ""
    made = ctx.run(f"gh pr create --draft --fill{base} --head {branch}" + (f" --body-file {body}" if body else ""))
    found = URL.search(str(made.tail)) if _passed(made) else None
    if found:
        return FinalizerResult(outcome="opened", reason=f"draft pull request opened for {branch}", url=found.group(0))
    return FinalizerResult(outcome="pushed", reason=f"{branch} is pushed; no pull request could be opened",
                           manual_steps=[f"open a draft pull request for {branch}"])
