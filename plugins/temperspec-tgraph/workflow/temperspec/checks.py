"""The model-free checks of every gate and of the outcome gate. Each finding names one criterion of
`outcome.json`; the formats come from `specfmt`, which the rule files under `rules/` describe in words.

A check reads the workspace and the engine's git facts; it writes nothing and trusts nothing a step said."""

from __future__ import annotations

import json
import os
import re
from dataclasses import dataclass, replace
from pathlib import Path
from typing import Any

from tempergraph.api import CheckFinding, checks

from . import routing
from . import specfmt as fmt

SKIP_DIRS = {".git", ".tempergraph", ".claude", "node_modules", ".venv", "venv", "__pycache__", "evals", "fixtures", "dist",
             "build", ".tox", ".mypy_cache", ".ruff_cache", ".pytest_cache"}
TEST_DIRS = {"tests", "test", "__tests__", "spec", "specs_test", "e2e"}
TEST_FILE = re.compile(r"(^test_.*|.*_test\.[a-z]+|.*\.test\.[a-z]+|.*Tests?\.[a-z]+|.*\.spec\.(?:ts|tsx|js|jsx))$")
# Commands the last stage alone may run; a plan may not list them as verification.
FINAL_ONLY = ("git push", "gh ")
IN_FOLDER = re.compile(r"^cd\s+\S+\s*&&\s*")
MAX_FILES = 4000


def _find(status: str, criterion: str, place: str = "", message: str = "", fix: str = "") -> CheckFinding:
    return CheckFinding(status=status, criterion=criterion, place=place, message=message, fix=fix)  # type: ignore[arg-type]


def _ok(criterion: str, place: str = "") -> CheckFinding:
    return _find("pass", criterion, place)


def _value(ctx: Any, key: str) -> str | None:
    for vals in (ctx.values or {}).values():
        if isinstance(vals, dict) and key in vals:
            return str(vals[key])
    return None


def _read(ctx: Any, key: str) -> tuple[str | None, str]:
    """(text, path) of artifact `key`; text is None when the artifact is missing or unreadable."""
    path = checks.artifact_path(ctx, key)
    if path is None:
        return None, key
    try:
        return ctx.read_text(path), path
    except (OSError, PermissionError):
        return None, path


def _read_path(ctx: Any, path: str) -> str | None:
    try:
        return str(ctx.read_text(path))
    except (OSError, PermissionError, ValueError):
        return None


def _committed(ctx: Any, criterion: str) -> CheckFinding:
    return checks.git_clean(ctx, criterion)


# What a step's prompt tells its session about how to work: narrow reading, the reading list, commands run once.
# A judge sees the step's output, never its prompt or its command runs, so these criteria are checked here, from
# the prompt files the package gives its steps (B30). Each phrase is matched case-insensitively, spacing ignored.
PROMPTS = Path(__file__).resolve().parents[2] / "prompts"
PROMPT_SAYS: dict[str, tuple[str, tuple[str, ...]]] = {
    "ts-dis-narrow": ("discovery*.md", ("search for ids and names", "line ranges you need instead of whole files",
                                        "stop reading once each gap has its answer")),
    "ts-plan-reading": ("plan.md", ("start from the hand-off's reading list",
                                    "open another file only for what the list does not answer")),
    "ts-code-once": ("code.md", ("after each phase, run only the test files that the phase's rows name",
                                 "never the whole suite",
                                 "run each verification command of the plan once, after the last phase, with the "
                                 "plan marked completed and the code report written",
                                 "change no file after that run",
                                 "in the quick lane, run the note's `verify` commands once, after the last criterion "
                                 "and the report")),
    "ts-code-preview": ("code.md", ("make that one run through the preview command that the engine names under "
                                    "\"check your work before you end\"",
                                    "call it once, when nothing is left to change",
                                    "the phases' own test runs stay plain commands")),
    "ts-dsh-limit": ("discovery_short.md", ("read at most 10 files",)),
}


def _prompt_says(criterion: str) -> list[CheckFinding]:
    """One finding per prompt file that lacks an instruction its criterion asks for, else one pass."""
    pattern, phrases = PROMPT_SAYS[criterion]
    files = sorted(PROMPTS.glob(pattern))
    if not files:
        return [_find("fail", criterion, f"prompts/{pattern}", "no prompt file of the package matches",
                      "restore the step's prompt")]
    found: list[CheckFinding] = []
    for f in files:
        text = " ".join(f.read_text(encoding="utf-8").split()).lower()
        found += [_find("fail", criterion, f"prompts/{f.name}", f"the prompt does not say \"{p}\"",
                        "put the instruction back in the prompt") for p in phrases if p not in text]
    return found or [_ok(criterion, ", ".join(f"prompts/{f.name}" for f in files))]


# What the session record shows (engine CHK-B24, CHK-B25; package SRC-B1 to SRC-B9). `ctx.session` is the calls the
# attempt's session made: `{name, capability, target, ok}` each, in order, or None where there is no record. A finding
# built from it names a rule file, a row, a path or a phase taken from the prompt and the plan, never a call's target.
RULE_FOLDER = ".claude/rules/temperspec"
RULE_NAME = re.compile(r"[\w-]+\.rule\.md")
NO_RECORD = "there is no session record to read (a stand-in executor, the check preview or hidden tool inputs)"
WRITES = ("edit", "write")


def _record(ctx: Any) -> list[dict[str, Any]] | None:
    """The calls of the attempt's session, or None when there is no record to trust: no `session` on the context, or
    a read, edit or write call with no target (`observe.tool_inputs = off`) (SRC-B8)."""
    session = getattr(ctx, "session", None)
    if session is None:
        return None
    calls = [dict(c) for c in session if isinstance(c, dict) or hasattr(c, "keys")]
    if any(c.get("capability") in ("read", *WRITES) and not c.get("target") for c in calls):
        return None
    return calls


def _rule_names(unit: str) -> list[str]:
    """The distinct rule files the unit's prompt names, in order of appearance (exact prompt file, so `discovery`
    never reads `discovery_short.md`)."""
    try:
        text = (PROMPTS / f"{unit}.md").read_text(encoding="utf-8")
    except OSError:
        return []
    return list(dict.fromkeys(RULE_NAME.findall(text)))


def _target_is(call: dict[str, Any], name: str) -> bool:
    return str(call.get("target") or "").replace("\\", "/").rstrip("/").rsplit("/", 1)[-1] == name


def _opened(calls: list[dict[str, Any]], name: str) -> bool:
    """A read call without an error whose target ends in the file's name; a search or a failed read is no opening."""
    return any(c.get("capability") == "read" and c.get("ok") is True and _target_is(c, name) for c in calls)


def _ruleread(ctx: Any, unit: str, criterion: str) -> list[CheckFinding]:
    """The rule files the unit's prompt names and the repository holds are each opened with the read tool (SRC-B1)."""
    held = [n for n in _rule_names(unit) if (Path(ctx.workdir) / RULE_FOLDER / n).is_file()]
    if not held:
        return [_find("n_a", criterion, message=f"the rule files are not in the repository (`{RULE_FOLDER}/`)")]
    calls = _record(ctx)
    if calls is None:
        return [_find("n_a", criterion, message=NO_RECORD)]
    found = [_find("fail", criterion, f"{RULE_FOLDER}/{n}", f"the session never opened `{n}` with the read tool",
                   f"open `{RULE_FOLDER}/{n}` with the read tool, then follow it") for n in held
             if not _opened(calls, n)]
    return found or [_ok(criterion, ", ".join(held))]


def _norm(path: str) -> str:
    """A path as the record writes it: posix, no leading `./`."""
    text = path.replace("\\", "/")
    while text.startswith("./"):
        text = text[2:]
    return text


def _phase_label(heading: str) -> str:
    found = re.match(r"\s*Phase\s+(\d+)", heading, re.I)
    return f"phase {found.group(1)}" if found else heading[:40]


def _test_first(ctx: Any, plan: fmt.Plan, criterion: str) -> list[CheckFinding]:
    """ts-code-order: a phase's source files are not changed before its test files are first written (SRC-B6). A file
    counts for the first phase that names it; a phase is measured only when the record writes a test file of the
    phase; `docs` and `chore` rows count for no phase; a call that ended with an error is not a change."""
    if _quick(ctx) is not None:
        return [_find("n_a", criterion, message="the quick lane has no phases")]
    calls = _record(ctx)
    if calls is None:
        return [_find("n_a", criterion, message=NO_RECORD)]
    owner: dict[str, str] = {}
    for row in plan.rows:
        if row.kind in ("test", "code") and row.file:
            owner.setdefault(_norm(row.file), row.phase)
    changes = [(i, _norm(str(c.get("target") or ""))) for i, c in enumerate(calls)
               if c.get("capability") in WRITES and c.get("ok") is True]
    found: list[CheckFinding] = []
    for phase in dict.fromkeys(r.phase for r in plan.rows):
        tests = {_norm(r.file) for r in plan.rows if r.phase == phase and r.kind == "test" and r.file
                 and owner.get(_norm(r.file)) == phase}
        source = {_norm(r.file) for r in plan.rows if r.phase == phase and r.kind == "code" and r.file
                  and owner.get(_norm(r.file)) == phase} - tests
        written = [i for i, path in changes if path in tests]
        if written and any(i < min(written) for i, path in changes if path in source):
            found.append(_find("fail", criterion, _phase_label(phase),
                               f"{_phase_label(phase)}: a source file of the phase was changed before its test file "
                               "was first written", "write the phase's tests first, see them fail, then change the "
                               "source"))
    return found or [_ok(criterion)]


def _opened_rows(ctx: Any, plan: fmt.Plan, criterion: str) -> list[CheckFinding]:
    """ts-exp-opened: each task row that names a file that exists in the repository has that file opened with the
    read tool; two rows that name one unread file are both named (SRC-B5)."""
    calls = _record(ctx)
    if calls is None:
        return [_find("n_a", criterion, message=NO_RECORD)]
    seen = {_norm(str(c.get("target") or "")) for c in calls if c.get("capability") == "read" and c.get("ok") is True}
    root = Path(ctx.workdir).resolve()
    found: list[CheckFinding] = []
    for row in plan.rows:
        if not row.file:
            continue
        try:
            target = (root / row.file).resolve()
            exists = target.is_relative_to(root) and target.is_file()
        except (OSError, ValueError):
            exists = False
        if exists and _norm(row.file) not in seen:
            found.append(_find("fail", criterion, row.file, f"row `{row.id}` names `{row.file}`, which the session "
                               "never opened with the read tool", "open the file with the read tool before you "
                               "write the row"))
    return found or [_ok(criterion)]


def _walk(ctx: Any) -> list[str]:
    """Repository files as posix paths, without the folders no document or test of the task lives in."""
    out: list[str] = []
    root = Path(ctx.workdir)
    for folder, dirs, files in os.walk(root):
        dirs[:] = sorted(d for d in dirs if d not in SKIP_DIRS)
        for name in sorted(files):
            out.append((Path(folder) / name).relative_to(root).as_posix())
            if len(out) >= MAX_FILES:
                return out
    return out


def _spec_index(ctx: Any, files: list[str]) -> dict[str, list[str]]:
    """Id -> the spec files that define it (a file is listed twice when it defines the id twice)."""
    index: dict[str, list[str]] = {}
    for path in files:
        if path.endswith(".spec.md"):
            for found in fmt.defined_ids(_read_path(ctx, path) or ""):
                index.setdefault(found, []).append(path)
    return index


def _definitions(ctx: Any, docs: list[str]) -> dict[str, list[str]]:
    """Id -> the spec files that define it, over every spec of the repository, the overview wherever it is, and
    the specs among `docs` even inside a skipped folder."""
    index = _spec_index(ctx, _walk(ctx))
    overview = checks.artifact_path(ctx, "overview")
    if overview and not overview.endswith(".spec.md"):  # the overview is a spec wherever it is
        for own in fmt.defined_ids(_read_path(ctx, overview) or ""):
            index.setdefault(own, []).append(overview)
    for path in docs:
        if path.endswith(".spec.md"):
            for own in fmt.defined_ids(_read_path(ctx, path) or ""):  # a changed spec inside a skipped folder counts
                if path not in index.get(own, []):
                    index.setdefault(own, []).append(path)
    return index


def _changed_docs(ctx: Any) -> list[str]:
    """Documents the run changed: the git facts, plus the hand-off's own list (the only source in a fixture)."""
    paths = [p for p in ctx.git.changed_paths if p.endswith(".md") and not (set(Path(p).parts) & SKIP_DIRS)
             and not p.startswith(fmt.TEMPLATE_DIR + "/")]  # templates hold example ids, not links
    text, own = _read(ctx, "handoff")
    if text is not None:
        paths += [own] if own not in paths else []
        low = {k.lower(): v for k, v in fmt.sections(text).items()}
        paths += [p for p in fmt.listed_paths(low.get("changed documents", [])) if p not in paths]
    return paths


def _edited_specs(ctx: Any) -> tuple[list[str], list[str]]:
    """(spec files that exist, listed spec files that do not exist)."""
    have: list[str] = []
    gone: list[str] = []
    for p in _changed_docs(ctx):
        if p.endswith(".spec.md"):
            (have if _read_path(ctx, p) is not None else gone).append(p)
    return have, [p for p in gone if p not in ctx.git.changed_paths]  # a deleted spec is in the git facts only


def _over_budget(ctx: Any, path: str, lines: int) -> list[str]:
    """What of the spec budget the file is over: its lines, its bytes on disk (not its characters)."""
    out: list[str] = []
    if lines > fmt.SPEC_CAP_LINES:
        out.append(f"{lines:,} lines, over the budget of {fmt.SPEC_CAP_LINES:,}")
    try:
        size = (Path(ctx.workdir) / path).stat().st_size
    except OSError:
        size = 0
    if size > fmt.SPEC_CAP_BYTES:
        out.append(f"{size:,} bytes, over the budget of {fmt.SPEC_CAP_BYTES:,}")
    return out


def _spec_form(ctx: Any, criterion: str, cap_criterion: str | None = None,
               budget_criterion: str | None = None) -> list[CheckFinding]:
    """The spec rule's structure check on every edited spec; the line cap under `cap_criterion` if given.

    With `budget_criterion` the size is measured instead against the spec budget (lines and bytes), and an
    overrun is one finding per spec under `ts-dis-over`, never under `criterion`."""
    have, gone = _edited_specs(ctx)
    found = [_find("fail", criterion, p, "the hand-off lists this spec but the file does not exist",
                   "write the spec or drop it from the list") for p in gone]
    over: list[CheckFinding] = []
    index = _definitions(ctx, have) if have else {}
    for path in have:
        # An id a split moved is defined in another file; the parser reads it there, whatever the run's history.
        elsewhere = {i: [f for f in files if f != path] for i, files in index.items() if any(f != path for f in files)}
        spec = fmt.parse_spec(_read_path(ctx, path) or "", elsewhere)
        if budget_criterion:
            figures = _over_budget(ctx, path, spec.lines)
            if figures:
                over.append(_find("fail", "ts-dis-over", path, "; ".join(figures), "split the spec by capability"))
        elif spec.lines > fmt.SPEC_CAP_LINES:
            over.append(_find("fail", cap_criterion or criterion, path,
                              f"{spec.lines} lines, over the cap of {fmt.SPEC_CAP_LINES}",
                              "split the spec by capability, or compress it"))
        if spec.legacy:
            found.append(_find("n_a", criterion, path, "a spec in the earlier layout is not checked for form"))
            continue
        found += [_find("fail", criterion, f"{path}:{line}", message, fix) for line, message, fix in spec.problems[:8]]
    if not any(f.status == "fail" for f in found):
        found.append(_ok(criterion) if have else _find("n_a", criterion, message="the run edited no spec"))
    if budget_criterion:
        found += over or ([_ok(budget_criterion), _ok("ts-dis-over")] if have else [
            _find("n_a", budget_criterion, message="the run edited no spec"),
            _find("n_a", "ts-dis-over", message="the run edited no spec")])
    elif cap_criterion:
        found += over or [_ok(cap_criterion)]
    else:
        found += over
    return found


def _related(ctx: Any, specs: list[str], index: dict[str, list[str]], plan: fmt.Plan | None) -> list[str]:
    """Specs the run did not edit that an edited spec links by id, plus the specs the plan references."""
    out: list[str] = []
    for path in specs:
        text = _read_path(ctx, path) or ""
        own = set(fmt.defined_ids(text))
        for ref in sorted(fmt.linked_ids(text) - own):
            out += [h for h in index.get(ref, []) if h not in specs and h not in out]
    out += [p for p in (plan.specs if plan else []) if p not in specs and p not in out]
    return out


CONTEXT_FILES = ("CLAUDE.md", "AGENTS.md")
_BLOCK = re.compile(re.escape(fmt.CONTEXT_START) + r".*?" + re.escape(fmt.CONTEXT_END), re.S)


def _block_only(ctx: Any, path: str) -> bool:
    """Whether the project-context file differs from the run's base only in the temperspec block, which the
    workflow's prepare script writes before any step (so no plan row names it)."""
    now = _read_path(ctx, path)
    if now is None:
        return False
    before = _at_base(ctx, path) if ctx.git.base else None
    def bare(text: str) -> str:
        return " ".join(_BLOCK.sub("", text).split())
    return bare(before or "") == bare(now)


def _prepared_commands(ctx: Any) -> bool:
    """Whether the commands file is the one prepare wrote and no step touched: the run's base commit has no such
    file and it now holds exactly the text prepare writes (RCM-B9). A step's later edit makes it a changed path."""
    if not ctx.git.base or routing.COMMANDS_FILE not in ctx.git.changed_paths:
        return False
    return _at_base(ctx, routing.COMMANDS_FILE) is None and _read_path(
        ctx, routing.COMMANDS_FILE) == routing.commands_file_text()


# The code judge's reading budget (judge-reading spec, JRD-B2): one source file to read for every 50 changed source
# lines, rounded up, within a floor and a ceiling. First values with no run behind them (outcome.json, assumptions).
LINES_PER_FILE = 50
READING_FLOOR = 10
READING_CEILING = 50


def reading_budget(lines: int) -> int:
    """Files the code judge reads for `lines` changed source lines."""
    return min(READING_CEILING, max(READING_FLOOR, -(-lines // LINES_PER_FILE)))


def _source_lines(ctx: Any, sources: list[str]) -> dict[str, int] | None:
    """Lines added plus removed since the run's base, per changed source file; None with no base or when git fails."""
    if not ctx.git.base:
        return None
    run = ctx.run(f"git diff --numstat --no-renames {ctx.git.base}", reuse=True)
    if run.not_started or run.exit_code != 0:
        return None
    try:
        text = Path(run.output_path).read_text(encoding="utf-8", errors="replace")
    except OSError:
        return None
    counts: dict[str, int] = {}
    for row in text.splitlines():
        added, _, rest = row.partition("\t")
        removed, _, path = rest.partition("\t")
        if path in sources:
            counts[path] = (int(added) if added.isdigit() else 0) + (int(removed) if removed.isdigit() else 0)
    return counts


def _reading_lines(ctx: Any) -> list[str]:
    """The evidence lines the code judge reads from: the changed source lines, the reading budget and the changed
    source files, the file with the most changed lines first (JRD-B1, JRD-B2)."""
    sources = [p for p in ctx.git.changed_paths if not p.startswith(".claude/rules/") and not p.endswith(".md")]
    if _prepared_commands(ctx):
        sources = [p for p in sources if p != routing.COMMANDS_FILE]
    counts = _source_lines(ctx, sources)
    rule = f"one per {LINES_PER_FILE} lines, floor {READING_FLOOR}, ceiling {READING_CEILING}"
    if counts is None:
        why = "no base commit to compare with, or git diff failed"
        return [f"Changed source lines: not counted ({why}). Reading budget: {READING_FLOOR} files (the floor).",
                f"{SOURCE_FILES} (no counts): " + ("; ".join(sources) if sources else "none, the change has no source file")]
    total = sum(counts.values())
    ordered = sorted(sources, key=lambda p: (-counts.get(p, 0), p))
    listed = "; ".join(f"{p} {counts.get(p, 0)}" for p in ordered) or "none, the change has no source file"
    return [f"Changed source lines: {total}. Reading budget: {reading_budget(total)} files ({rule}).",
            f"{SOURCE_FILES} (path lines), most lines first: {listed}"]


SOURCE_FILES = "Changed source files"


def _result(ctx: Any, found: list[CheckFinding], plan: fmt.Plan | None = None,
            links: list[str] | None = None, reading: list[str] | None = None,
            facts: list[str] | None = None, *, commands: list[str] | None = None) -> Any:
    """The result, with the facts a read-only judge cannot get by itself as its evidence. A command judged
    environmental leads the evidence, and the result is marked environmental when no other finding fails. `reading` is the lines a
    judge that reads the changed code needs (`_reading_lines`): the changed source lines, its budget and the files.
    `facts` is lines of plain evidence that follow the first line, never a finding (the outcome check's push line).
    `commands` are the lines that say how each verification command was answered: first, because a preview prints
    only the start."""
    lead = [f"{f.criterion}: {f.message}" for f in found if isinstance(f, _Environmental)]
    bad = "; ".join(lead + [f"{f.criterion}: {f.message}" for f in found
                            if f.status == "fail" and not isinstance(f, _Environmental)])
    environmental = bool(lead) and not any(f.status == "fail" and not isinstance(f, _Environmental) for f in found)
    specs, _ = _edited_specs(ctx)
    head = [bad or f"{len(found)} checked"] + (facts or [])
    # an environmental command leads (it escalates to a person); otherwise the command lines lead for a preview
    lines = (head + [*(commands or [])] if lead else [*(commands or []), *head]) + (reading or [])
    changed = [p for p in ctx.git.changed_paths if not p.startswith(".claude/rules/")]
    prepared = [p for p in changed if p in CONTEXT_FILES and _block_only(ctx, p)]
    commands_file = [routing.COMMANDS_FILE] if _prepared_commands(ctx) else []
    changed = [p for p in changed if p not in prepared and p not in commands_file]
    if changed:
        lines.append("Changed paths since the run's base: " + ", ".join(changed[:120]))
    if prepared:
        lines.append("Written by prepare (the temperspec block only, no step's change): " + ", ".join(prepared))
    if commands_file:
        lines.append("Written by prepare (the repository's commands file, as prepare wrote it, no step's change): "
                     + routing.COMMANDS_FILE)
    if specs:
        lines.append("Edited specs: " + ", ".join(specs))
        related = _related(ctx, specs, _spec_index(ctx, _walk(ctx)), plan)
        lines.append("Related specs: " + (", ".join(related[:40]) or "none"))
    elif plan is not None and plan.specs:
        lines.append("Related specs: " + ", ".join(plan.specs[:40]))
    if links:
        lines.append("Criterion tests: " + "; ".join(links[:40]))
    res = checks.result(found, evidence="\n".join(lines))
    res.environmental = environmental
    return res


def _setup_specs(ctx: Any) -> list[str]:
    """The specs the setup step wrote: its overview and every spec its note lists. Empty when setup did not run."""
    out = [p for p in [checks.artifact_path(ctx, "overview")] if p]
    text, _ = _read(ctx, "setup_note")
    if text is not None:
        low = {k.lower(): v for k, v in fmt.sections(text).items()}
        out += [p for p in fmt.listed_paths(low.get("components", [])) if p.endswith(".md") and p not in out]
    return out


def _links(ctx: Any, criterion: str, docs: list[str] | None = None) -> list[CheckFinding]:
    """Every id a changed document mentions has exactly one definition among the repository's specs."""
    docs = [p for p in (_changed_docs(ctx) if docs is None else docs) if _read_path(ctx, p) is not None]
    if not docs:
        return [_find("n_a", criterion, message="the run changed no document")]
    index = _definitions(ctx, docs)
    found: list[CheckFinding] = []
    for path in docs:
        text = _read_path(ctx, path) or ""
        for ref in sorted(fmt.linked_ids(text)):
            homes = index.get(ref, [])
            if not homes:
                found.append(_find("fail", criterion, path, f"{ref} is defined by no spec",
                                   "link an id that exists, or define the behaviour"))
            elif len(homes) > 1:
                found.append(_find("fail", criterion, path, f"{ref} is defined {len(homes)} times: "
                                   + ", ".join(sorted(set(homes))[:3]), "keep one definition; link the others to it"))
    return found[:12] or [_ok(criterion)]


# ---------------------------------------------------------------------------------------------
# setup


def setup_check(ctx: Any) -> Any:
    """ts-set-form, ts-set-listed, ts-set-links, ts-set-named, ts-set-literal, ts-set-wording, ts-set-evidence,
    ts-set-ruleread, ts-set-commit."""
    note, note_path = _read(ctx, "setup_note")
    overview, overview_path = _read(ctx, "overview")
    if note is None or overview is None:
        return checks.result([_find("fail", "ts-set-form", note_path if note is None else overview_path,
                                    "the setup note or the overview spec cannot be read",
                                    "write both and name their paths")])
    found = [_find("fail", "ts-set-form", note_path, f"setup note section `## {h}` is missing or out of order",
                   f"add `## {h}`") for h in fmt.headings_missing(note, fmt.SETUP_HEADINGS)]
    specs = _setup_specs(ctx)
    listed: list[CheckFinding] = []
    for path in specs:
        text = _read_path(ctx, path)
        if text is None:
            listed.append(_find("fail", "ts-set-listed", path, "the setup note lists this spec but the file does "
                                "not exist", "write the spec or drop it from the list"))
            continue
        spec = fmt.parse_spec(text)
        if spec.legacy:
            found.append(_find("fail", "ts-set-form", path, "a new spec is written in the earlier layout",
                               "use Purpose, Behaviours and Acceptance criteria"))
        if spec.lines > fmt.SPEC_CAP_LINES:
            found.append(_find("fail", "ts-set-form", path, f"{spec.lines} lines, over the cap of "
                               f"{fmt.SPEC_CAP_LINES}", "split the spec by capability"))
        found += [_find("fail", "ts-set-form", f"{path}:{line}", message, fix) for line, message, fix in
                  spec.problems[:6]]
        if path != overview_path and path not in overview:
            listed.append(_find("fail", "ts-set-listed", overview_path, f"the overview does not name `{path}`",
                                "name each component spec by its path in the overview's Purpose"))
    if not any(f.status == "fail" for f in found):
        found.append(_ok("ts-set-form", overview_path))
    found += listed or [_ok("ts-set-listed", note_path)]
    found += _links(ctx, "ts-set-links", specs)
    written = [p for p in specs if _read_path(ctx, p) is not None]
    found += _general(ctx, written, "ts-set-named", "ts-set-literal", "ts-set-wording")
    found += _setup_evidence(ctx, note, note_path, written)
    found += _ruleread(ctx, "setup", "ts-set-ruleread")
    found.append(_committed(ctx, "ts-set-commit"))
    return checks.result(found)


EVIDENCE_BASES = ("tested", "read")
CODE_RANGE = re.compile(r"`([^`:]+):(\d+)(?:-(\d+))?`")


def _setup_evidence(ctx: Any, note: str, note_path: str, specs: list[str]) -> list[CheckFinding]:
    """ts-set-evidence: every behaviour of a spec the setup step wrote has a row in the setup note's `Evidence`,
    with the basis `tested` or `read`, code that exists named with lines inside the file, and a test file that
    exists when the basis is `tested` (`extraction.rule.md`)."""
    rows: dict[str, list[str]] = {}
    for line in {k.lower(): v for k, v in fmt.sections(note).items()}.get("evidence", []):
        cells = [c.strip() for c in line.strip().strip("|").split("|")]
        if len(cells) >= 3 and re.fullmatch(rf"{fmt.ID}-B\d+", cells[0].strip("` ")):
            rows[cells[0].strip("` ")] = cells
    found: list[CheckFinding] = []
    for path in specs:
        for bid in fmt.parse_spec(_read_path(ctx, path) or "").behaviours:
            cells = rows.get(bid)
            if cells is None:
                found.append(_find("fail", "ts-set-evidence", note_path, f"{bid} of `{path}` has no Evidence row",
                                   "add a row with its basis, the code and lines, and the test"))
                continue
            basis = cells[1].strip("` ").lower()
            if basis not in EVIDENCE_BASES:
                found.append(_find("fail", "ts-set-evidence", note_path, f"{bid}: basis `{cells[1]}` is not "
                                   "`tested` or `read`", "a rule only stated somewhere goes under Anomalies"))
            ranges = CODE_RANGE.findall(cells[2])
            if not ranges:
                found.append(_find("fail", "ts-set-evidence", note_path, f"{bid}: no code with lines, "
                                   "`<path>:<from>-<to>`", "name the code the rule was read in"))
            for file, start, stop in ranges:
                text = _read_path(ctx, file)
                if text is None:
                    found.append(_find("fail", "ts-set-evidence", note_path, f"{bid}: `{file}` does not exist",
                                       "name a file of the repository"))
                elif max(int(start), int(stop or start)) > len(text.splitlines()):
                    found.append(_find("fail", "ts-set-evidence", note_path, f"{bid}: `{file}` has "
                                       f"{len(text.splitlines())} lines, the row names line {stop or start}",
                                       "name lines inside the file"))
            if basis == "tested":
                tests = [t.split("::")[0] for t in fmt.CODE_SPAN.findall(cells[3] if len(cells) > 3 else "")]
                if not tests or any(_read_path(ctx, t) is None for t in tests):
                    found.append(_find("fail", "ts-set-evidence", note_path, f"{bid}: basis `tested` names no "
                                       "test file that exists", "name the test, or set the basis to `read`"))
    return found[:12] or [_ok("ts-set-evidence", note_path)]


# ---------------------------------------------------------------------------------------------
# triage


def triage_check(ctx: Any) -> Any:
    """ts-tri-form, ts-tri-route, ts-tri-covered, ts-tri-ruleread, ts-tri-owner, ts-tri-commit."""
    text, path = _read(ctx, "triage_note")
    if text is None:
        return checks.result([_find("fail", "ts-tri-form", path, "the triage note cannot be read",
                                    "write the note and name its path")])
    note = fmt.parse_triage(text)
    found = [_find("fail", "ts-tri-form", path, f"section `## {h}` is missing or out of order", f"add `## {h}`")
             for h in note.missing]
    if not note.criteria:
        found.append(_find("fail", "ts-tri-form", path, "no numbered acceptance criterion",
                           "number each criterion the task states"))
    if not note.gaps:
        found.append(_find("fail", "ts-tri-form", path, "the Gaps section is neither `None` nor rows `G1`, `G2`, …",
                           "write `None`, or one row per gap"))
    if note.deliver not in fmt.DELIVER:
        found.append(_find("fail", "ts-tri-form", path, "the Route section has no `Deliver: code` or `Deliver: docs`",
                           "state what the run delivers"))
    if not any(f.status == "fail" for f in found):
        found.append(_ok("ts-tri-form", path))

    want = "plan" if note.gaps == "none" else ("discovery-only" if note.deliver == "docs" else "discovery")
    route, gaps = _value(ctx, "route"), _value(ctx, "gaps")
    bad = []
    if note.route not in fmt.ROUTES:
        bad.append(f"the note's route is `{note.route}`, not one of {', '.join(fmt.ROUTES)}")
    elif note.route == "quick":
        bad += fmt.quick_problems(note)
        if ctx.visit > 1:
            bad.append("a run that came back to triage takes `plan` or `discovery`, never `quick` again")
        bad += [f.message for f in _commands(ctx, fmt.Plan(commands=note.change_commands), "ts-tri-route")
                if note.change_commands]
    elif note.gaps and note.route != want:
        bad.append(f"the note's route is `{note.route}` but its gaps and delivery give `{want}`")
    if note.gaps == "none" and note.deliver == "docs":
        bad.append("a docs delivery with no gap has nothing to write")
    if route is not None and route != note.route:
        bad.append(f"the route value `{route}` differs from the note's `{note.route}`")
    if gaps is not None and note.gaps and gaps != note.gaps:
        bad.append(f"the gaps value `{gaps}` differs from the note's gap list (`{note.gaps}`)")
    found += [_find("fail", "ts-tri-route", path, b, "make the route follow the gap list") for b in bad] or [
        _ok("ts-tri-route", path)]
    found += _covered(ctx, note, path)
    found += _ruleread(ctx, "triage", "ts-tri-ruleread")
    found += _owner(ctx, note, path)
    found.append(_committed(ctx, "ts-tri-commit"))
    return checks.result(found)


def _owner(ctx: Any, note: fmt.Triage, path: str) -> list[CheckFinding]:
    """ts-tri-owner: with the conversation value `never`, `blocking` or `always`, each gap row ends with its sort and
    the `Owner decisions` section holds one complete entry for each owner-decision row and none for any other (spec
    `conversation`, CONV-B4). With no value given to the check, the note is not read for it."""
    crit = "ts-tri-owner"
    if (getattr(ctx, "settings", None) or {}).get("conversation") not in ("never", "blocking", "always"):
        return [_find("n_a", crit, path, "the check is given no conversation value")]
    bad: list[tuple[str, str, str]] = []  # (place, message, fix)
    for gap, sort in note.sorts.items():
        if not sort:
            bad.append((gap, f"gap row {gap} ends neither `Findable` nor `Owner decision`",
                        f"end row {gap} with `Findable` or `Owner decision`"))
    if not note.owner_section:
        bad.append((fmt.OWNER_HEADING, f"the section `## {fmt.OWNER_HEADING}` is missing",
                    f"add `## {fmt.OWNER_HEADING}` between Gaps and Route, with an entry for each owner decision or `None`"))
    else:
        entered = {e.gap for e in note.owners}
        for gap, sort in note.sorts.items():
            if sort == "owner decision" and gap not in entered:
                bad.append((gap, f"gap row {gap} says `Owner decision` but `{fmt.OWNER_HEADING}` has no entry for it",
                            f"add `- {gap}: <question>` with its options, default and cost"))
        low, high = fmt.OWNER_OPTIONS
        for e in note.owners:
            gap, fix = e.gap, f"complete the entry for {e.gap}"
            if e.gap not in note.sorts:
                bad.append((gap, f"entry {gap} answers no gap row", f"drop the entry or add the row {gap}"))
                continue
            if note.sorts[e.gap] == "findable":
                bad.append((gap, f"entry {gap} is for a gap row that says `Findable`", "drop the entry"))
                continue
            n = len(e.options)
            if not e.question:
                bad.append((gap, f"entry {gap} has no question", fix))
            if not low <= n <= high:
                bad.append((gap, f"entry {gap} has {n} option{'s' if n != 1 else ''}, not two to four",
                            f"give {gap} two to four options under `Options:`"))
            if not e.default:
                bad.append((gap, f"entry {gap} has no default", f"add `Default:` with the label of one option of {gap}"))
            elif n and not e.default_text:
                bad.append((gap, f"the default of entry {gap} (`{e.default}`) is not one of its options",
                            f"name the label of one option of {gap}"))
            if not e.cost:
                bad.append((gap, f"entry {gap} has no cost", "add `If wrong:` with what a wrong default costs"))
    if bad:
        return [_find("fail", crit, place, message, fix) for place, message, fix in bad]
    return [_ok(crit, path)]


def _covered(ctx: Any, note: fmt.Triage, path: str) -> list[CheckFinding]:
    """ts-tri-covered: each `Covered by <behaviour id> and <criterion id>` names two ids that one spec defines
    once each, the criterion naming the behaviour; a `covered` value says `yes` exactly when every gap row is
    covered and there is at least one."""
    crit, fix = "ts-tri-covered", "cite a behaviour and a criterion that one spec defines, or drop the mark"
    bad: list[tuple[str, str]] = []
    if note.covered_claimed != note.covered_rows:
        bad.append((path, "a gap row says `Covered by` without a behaviour id and a criterion id"))
    index = _spec_index(ctx, _walk(ctx)) if note.covered else {}
    for behaviour, criterion in note.covered:
        place, where = f"{behaviour} and {criterion}", {i: index.get(i, []) for i in (behaviour, criterion)}
        wrong = next((f"`{i}` is defined {len(w)} times in the specs, not once" for i, w in where.items()
                      if len(w) != 1), None)
        if wrong is None and where[behaviour][0] != where[criterion][0]:
            wrong = f"`{behaviour}` and `{criterion}` are defined in two different specs"
        if wrong is None:
            spec = fmt.parse_spec(_read_path(ctx, where[behaviour][0]) or "")
            if not spec.legacy and behaviour not in getattr(spec.criteria.get(criterion), "proves", []):
                wrong = f"`{criterion}` does not name `{behaviour}`"
        if wrong is not None:
            bad.append((place, wrong))
    value = _value(ctx, "covered")
    if value is not None:
        every = note.gap_rows > 0 and note.covered_rows == note.gap_rows
        if value != ("yes" if every else "no"):
            bad.append((path, f"the covered value `{value}` differs from the gap rows "
                              f"({note.covered_rows} of {note.gap_rows} say `Covered by`)"))
    if bad:
        return [_find("fail", crit, place, message, fix) for place, message in bad]
    if note.covered or value is not None:
        return [_ok(crit, path)]
    return [_find("n_a", crit, path, "no gap row says `Covered by`")]


# ---------------------------------------------------------------------------------------------
# discovery


def _names(ctx: Any, criterion: str) -> list[CheckFinding]:
    found = []
    for p in _changed_docs(ctx):
        parts = Path(p).parts
        folder = next((d for d in reversed(parts[:-1]) if d in fmt.SUFFIX_BY_FOLDER), None)
        name = parts[-1]
        if folder is None or name.lower() in ("readme.md", "index.md"):
            continue
        suffix = fmt.SUFFIX_BY_FOLDER[folder]
        if not name.endswith(suffix):
            found.append(_find("fail", criterion, p, f"a document under `{folder}/` ends with `{suffix}`",
                               f"rename it to end with `{suffix}`"))
    return found or [_ok(criterion)]


def discovery_check(ctx: Any) -> Any:
    """ts-dis-form, ts-dis-budget, ts-dis-over, ts-dis-names, ts-dis-links, ts-dis-named, ts-dis-literal,
    ts-dis-wording, ts-dis-specname, ts-dis-reading, ts-dis-narrow, ts-dis-ruleread, ts-dis-commit."""
    text, path = _read(ctx, "handoff")
    if text is None:
        return checks.result([_find("fail", "ts-dis-form", path, "the hand-off cannot be read",
                                    "write the hand-off and name its path")])
    found = [_find("fail", "ts-dis-form", path, f"hand-off section `## {h}` is missing or out of order",
                   f"add `## {h}`") for h in fmt.headings_missing(text, fmt.HANDOFF_HEADINGS) if h != READING]
    found += _spec_form(ctx, "ts-dis-form", budget_criterion="ts-dis-budget")
    found += _names(ctx, "ts-dis-names")
    found += _links(ctx, "ts-dis-links")
    specs, _ = _edited_specs(ctx)
    found += _general(ctx, specs, "ts-dis-named", "ts-dis-literal", "ts-dis-wording")
    found += _spec_names(ctx, specs, "ts-dis-specname")
    found += _reading(ctx, text, path)
    found += _prompt_says("ts-dis-narrow")
    found += _ruleread(ctx, "discovery", "ts-dis-ruleread")
    found.append(_committed(ctx, "ts-dis-commit"))
    return _result(ctx, found)


# The spec rule's `General rules, not cases`: words that narrate a change, and an issue reference. Leads for the
# judge (ts-dis-literal, a warning), never a failure: a rule may say "instead of" or name a ticket field on purpose.
CHANGE_WORDS = re.compile(r"\b(no longer|any ?more|known limit|this change|used to|"
                          r"as before|is now|are now)\b", re.I)
ISSUE_REF = re.compile(r"(?<![\w&/#])#\d+\b")
LITERAL_MAX = 8


def _packages(ctx: Any) -> list[tuple[str, list[str]]]:
    """(package folder, the names it goes by) for each workflow package of the repository: a folder holding a
    `tempergraph.json`, at the top or one folder down. The names are its folder name and its workflow name."""
    root = Path(ctx.workdir)
    out: list[tuple[str, list[str]]] = []
    for manifest in sorted([*root.glob("*/tempergraph.json"), *root.glob("*/*/tempergraph.json")]):
        folder = manifest.parent.relative_to(root).as_posix()
        names = {manifest.parent.name}
        try:
            name = json.loads(manifest.read_text(encoding="utf-8")).get("name")
        except (OSError, ValueError, AttributeError):
            name = None
        if isinstance(name, str) and len(name) >= 3:
            names.add(name)
        out.append((folder, sorted(names, key=len, reverse=True)))
    return out


def _added_lines(ctx: Any, path: str) -> list[tuple[int, str]]:
    """(line number, text) of the lines the run added to a spec; every line when there is no base to compare."""
    base = getattr(ctx.git, "base", None) if ctx.git is not None else None
    if base:
        run = ctx.run(f"git diff --unified=0 {base} -- {path}")
        if not run.not_started and run.exit_code == 0:
            try:
                diff = Path(run.output_path).read_text(encoding="utf-8", errors="replace")
            except OSError:
                diff = None
            if diff is not None:
                out: list[tuple[int, str]] = []
                line = 0
                for ln in diff.splitlines():
                    hunk = re.match(r"@@ -\S+ \+(\d+)", ln)
                    if hunk:
                        line = int(hunk.group(1))
                    elif ln.startswith("+") and not ln.startswith("+++"):
                        out.append((line, ln[1:]))
                        line += 1
                return out
    return list(enumerate((_read_path(ctx, path) or "").splitlines(), start=1))


def _general(ctx: Any, specs: list[str], named_id: str, literal_id: str, wording_id: str) -> list[CheckFinding]:
    """The spec rule's `General rules, not cases` and the wording of a behaviour, on the lines a step added to
    `specs`. `named_id`: no line names a workflow package or its workflow outside that package (a failure).
    `literal_id`: lines that narrate a change or cite an issue or the task (leads). `wording_id`: a behaviour sentence
    over the length limit, a word two readers could measure differently, a placeholder left from drafting (leads)."""
    ids = (named_id, literal_id, wording_id)
    if not specs:
        return [_find("n_a", c, message="the step edited no spec") for c in ids]
    packages = _packages(ctx)
    task = str((ctx.request or {}).get("task_id") or "")
    task_word = re.compile(rf"(?<![\w-]){re.escape(task)}(?![\w-])") if len(task) >= 3 else None
    named: list[CheckFinding] = []
    literal: list[CheckFinding] = []
    wording: list[CheckFinding] = []
    for path in specs:
        denied = [n for folder, names in packages if not (path + "/").startswith(folder + "/") for n in names]
        pattern = re.compile(r"(?<![\w-])(" + "|".join(map(re.escape, denied)) + r")(?![\w])", re.I) if denied else None
        for number, text in _added_lines(ctx, path):
            hit = pattern.search(text) if pattern else None
            if hit and len(named) < LITERAL_MAX:
                named.append(_find("fail", named_id, f"{path}:{number}",
                                   f"names the workflow `{hit.group(1)}`, whose package does not hold this spec",
                                   "state the capability without the workflow: a placeholder for its units, "
                                   "its need as a general rule"))
            lead = CHANGE_WORDS.search(text) or ISSUE_REF.search(text) or (task_word.search(text) if task_word else None)
            if lead and len(literal) < LITERAL_MAX:
                literal.append(_find("maybe", literal_id, f"{path}:{number}",
                                     f"`{lead.group(0)}` may tie the line to the task or to a change",
                                     "state the rule as if it always held; keep the task's case in the task notes"))
            said = _wording(text)
            if said and len(wording) < LITERAL_MAX:
                wording.append(_find("maybe", wording_id, f"{path}:{number}", said[0], said[1]))
    return (named or [_ok(named_id)]) + (literal or [_ok(literal_id)]) + (wording or [_ok(wording_id)])


# The spec rule's Behaviours: the sentence's length limit, words two readers could measure differently, and
# placeholders left from drafting. Leads for the judge, never failures.
STATEMENT_MAX = 500
VAGUE = re.compile(r"\b(fast|quickly|robust(ly)?|secure(ly)?|intuitive(ly)?|appropriate(ly)?|reasonabl[ey]|"
                   r"user-friendly|scalable|seamless(ly)?|correctly|properly|as expected)\b", re.I)
PLACEHOLDER = re.compile(r"\b(TODO|TBD|TKTK|FIXME)\b|\?\?\?|<(…|\.\.\.)>")


def _wording(text: str) -> tuple[str, str] | None:
    """(message, fix) for an added spec line whose wording the spec rule warns about, or None."""
    line = text.strip()
    held = PLACEHOLDER.search(line)
    if held:
        return f"`{held.group(0)}` is a placeholder left from drafting", "write the rule, or leave it out"
    statement = fmt.BEHAVIOUR_LINE.match(line)
    if statement and len(line) > STATEMENT_MAX:
        return (f"the behaviour sentence has {len(line)} characters, over {STATEMENT_MAX}",
                "keep the event and the one result in the sentence; move detail to scenarios, split several results")
    if statement or line.startswith("- GIVEN"):
        vague = VAGUE.search(line)
        if vague:
            return (f"`{vague.group(0)}` can be measured two ways", "state what an observer sees, with a value")
    return None


# The spec rule's `Naming a spec`: a new spec's file name and title name its capability, never the task.
WORK_VERB = re.compile(r"^(?:\d+-)?(add|adds|adding|fix|fixes|support|supports|remove|update|implement|change)(?:-|$)",
                       re.I)
ISSUE_NAME = re.compile(r"(?<![a-z0-9])(?:issue-?\d+|gh-?\d+)(?![0-9])|#\d+", re.I)


def _new_files(ctx: Any, paths: list[str]) -> list[str]:
    """The paths the run created, against its base; every path when there is no base to compare."""
    base = getattr(ctx.git, "base", None) if ctx.git is not None else None
    if not base or not paths:
        return list(paths)
    run = ctx.run(f"git diff --name-only --diff-filter=A {base}")
    if run.not_started or run.exit_code != 0:
        return list(paths)
    try:
        added = set(Path(run.output_path).read_text(encoding="utf-8", errors="replace").split())
    except OSError:
        return list(paths)
    return [p for p in paths if p in added]


def _spec_names(ctx: Any, specs: list[str], criterion: str) -> list[CheckFinding]:
    """A spec the step created is named for its capability: no task id, issue number or leading work verb in its
    file name or its title."""
    new = _new_files(ctx, specs)
    if not new:
        return [_find("n_a", criterion, message="the step created no spec")]
    task = str((ctx.request or {}).get("task_id") or "")
    task_word = re.compile(rf"(?<![a-z0-9]){re.escape(task)}(?![a-z0-9])", re.I) if len(task) >= 3 else None
    found: list[CheckFinding] = []
    for path in new:
        stem = Path(path).name.removesuffix(".spec.md")
        title = next((ln[2:].strip() for ln in (_read_path(ctx, path) or "").splitlines() if ln.startswith("# ")), "")
        for where, words in (("file name", stem), ("title", title)):
            hit = (task_word.search(words) if task_word else None) or ISSUE_NAME.search(words) or (
                WORK_VERB.search(words.replace(" ", "-")) if where == "file name" else None)
            if hit:
                found.append(_find("fail", criterion, path, f"its {where} names the task, not the capability: "
                                   f"`{hit.group(0)}`", "name the spec for the capability it owns"))
    return found or [_ok(criterion)]


READING = "Reading list"
SHORT_READING_MAX = 10  # the short visit's reading limit (decision record 0003); its reading list holds at most this
NOT_COVERED = re.compile(r"\bnot covered\b", re.I)


def discovery_short_check(ctx: Any) -> Any:
    """ts-dsh-form, ts-dsh-cited, ts-dsh-only, ts-dsh-settled, ts-dsh-reading, ts-dsh-limit, ts-dsh-ruleread,
    ts-dsh-commit.

    The short visit confirms what triage cited and designs nothing: its hand-off names every cited behaviour,
    lists no changed document, says `Not covered` for a gap the citation does not answer, and its `settled` value
    follows those lines. A settled visit's reading list is the plan's start, at most 10 files."""
    text, path = _read(ctx, "handoff")
    if text is None:
        return checks.result([_find("fail", "ts-dsh-form", path, "the hand-off cannot be read",
                                    "write the hand-off and name its path")])
    found = [_find("fail", "ts-dsh-form", path, f"hand-off section `## {h}` is missing or out of order",
                   f"add `## {h}`") for h in fmt.headings_missing(text, fmt.HANDOFF_HEADINGS) if h != READING]
    found += [] if any(f.status == "fail" for f in found) else [_ok("ts-dsh-form", path)]
    low = {k.lower(): v for k, v in fmt.sections(text).items()}
    closed = [ln for ln in low.get("gaps closed", []) if ln.strip()]
    open_lines = [ln for ln in closed if NOT_COVERED.search(ln)]
    note_text, note_path = _read(ctx, "triage_note")
    note = fmt.parse_triage(note_text or "")
    if note_text is None:
        found.append(_find("fail", "ts-dsh-cited", note_path, "the triage note cannot be read"))
    else:
        said = " ".join(closed)
        missing = [b for b, _ in note.covered if not re.search(rf"(?<![\w-]){re.escape(b)}(?![\w-])", said)]
        found += [_find("fail", "ts-dsh-cited", path, f"`## Gaps closed` does not name {b}, which triage cited",
                        "name each cited behaviour on its gap's line, or say `Not covered` and why")
                  for b in missing] or [_ok("ts-dsh-cited", path)]
    changed = [p for p in fmt.listed_paths(low.get("changed documents", [])) if p != path]
    found += [_find("fail", "ts-dsh-only", p, "the short visit lists a changed document; it writes the hand-off only",
                    "write no spec, record or note: say `Not covered` and let the full discovery write it")
              for p in changed[:6]] or [_ok("ts-dsh-only", path)]
    value = _value(ctx, "settled")
    if value is None:
        found.append(_find("n_a", "ts-dsh-settled", path, "no `settled` value to compare"))
    elif (value == "yes") == bool(open_lines):
        found.append(_find("fail", "ts-dsh-settled", "settled", f"`settled` is `{value}` but {len(open_lines)} "
                           "gap line(s) say `Not covered`", "say `yes` only when every cited behaviour answers "
                           "its gap, `no` when a line says `Not covered`"))
    else:
        found.append(_ok("ts-dsh-settled", path))
    if open_lines or value == "no":
        found.append(_find("n_a", "ts-dsh-reading", path, "the full discovery writes the reading list"))
    else:
        reading = [f if f.criterion != "ts-dis-reading" else _find(f.status, "ts-dsh-reading", f.place, f.message,
                                                                    f.fix) for f in _reading(ctx, text, path)]
        items = fmt.parse_reading_list(text)
        if len(items) > SHORT_READING_MAX:
            reading = [f for f in reading if f.status != "pass"] + [_find(
                "fail", "ts-dsh-reading", path, f"{len(items)} reading-list items, over the short visit's limit "
                f"of {SHORT_READING_MAX}", "keep the files the plan needs; a task that needs more is not short")]
        found += reading
    found += _prompt_says("ts-dsh-limit")
    found += _ruleread(ctx, "discovery_short", "ts-dsh-ruleread")
    found.append(_committed(ctx, "ts-dsh-commit"))
    return _result(ctx, found)


def _reading(ctx: Any, text: str, path: str) -> list[CheckFinding]:
    """ts-dis-reading: a hand-off that goes on to a plan lists each file the plan will need, an existing file with
    the ranges or ids that matter and one line on why. A run that ends after discovery has no plan to read for."""
    crit = "ts-dis-reading"
    if _docs_only(ctx):
        return [_find("n_a", crit, path, "the run ends after discovery, so no plan reads a list")]
    if READING in fmt.headings_missing(text, fmt.HANDOFF_HEADINGS):
        return [_find("fail", crit, path, f"hand-off section `## {READING}` is missing or out of order",
                      f"add `## {READING}` with one item per file the plan will need")]
    items = fmt.parse_reading_list(text)
    if not items:
        return [_find("fail", crit, path, "the reading list has no item",
                      "list each file the plan will need as `path` (ranges or ids): why")]
    found: list[CheckFinding] = []
    for item in items:
        if _read_path(ctx, item.path) is None:
            found.append(_find("fail", crit, item.path[:80], "the reading list names a file that does not exist",
                               "name an existing file, or drop the item"))
        elif not item.locator or not item.reason:
            found.append(_find("fail", crit, item.path[:80],
                               "the item lacks " + ("the line ranges or ids" if not item.locator else "its reason"),
                               "write `path` (ranges or ids): one line on why"))
    return found or [_ok(crit, path)]


# ---------------------------------------------------------------------------------------------
# plan and expand


def _rows(ctx: Any, plan: fmt.Plan, criterion: str, rows_criterion: str | None = None) -> list[CheckFinding]:
    empty, bad = fmt.row_problems(plan)
    found = [_find("fail", rows_criterion or criterion, f"phase {p}", "the phase has no task row",
                   f"add a table `{ROW_TABLE}`") for p in empty]
    found += [_find("fail", criterion, "2. Phases", b, "put the test row first and name its criterion") for b in bad[:8]]
    return found


ROW_TABLE = "| " + " | ".join(c.capitalize() for c in fmt.ROW_COLUMNS) + " |"


def _links_of(plan: fmt.Plan, criterion: str, place: str) -> list[CheckFinding]:
    return [_find("fail", criterion, place, b, "name the requirement in each row's Req cell, and give each listed "
                  "document a `docs` row") for b in fmt.link_problems(plan)[:10]] or [_ok(criterion, place)]


PLANNING_COMMIT = re.compile(r"^\w+(?:\([^)]*\))?!?:\s*(?:plan|expand) for\b")


def _git_lines(ctx: Any, cmd: str) -> list[str] | None:
    """The lines a read-only git command printed; None when it did not start or did not exit 0."""
    run = ctx.run(cmd)
    if run.not_started or run.exit_code != 0:
        return None
    try:
        return Path(run.output_path).read_text(encoding="utf-8", errors="replace").splitlines()
    except OSError:
        return None


def _kept_marks(ctx: Any, plan: fmt.Plan, path: str) -> dict[str, str]:
    """KMK-B1 to KMK-B4: for each marked row of the plan, `""` when the run's history backs its mark, else the
    reason it does not. A commit of the run is one after the base commit. The marking commit of a row is the
    earliest commit that is not a plan or expand step's own in which the row's id carries the mark the plan carries;
    the mark stands when the row reads the same there and no later commit of the run changed the row's file."""
    marked = [r for r in plan.rows if r.completed]
    if not marked:
        return {}
    base = ctx.git.base if ctx.git is not None else ""
    if not base:
        return {r.id: "the run has no base commit to count its commits from, so no commit is known to have "
                      "written the mark" for r in marked}
    log = _git_lines(ctx, f"git log --format=%H%x09%s {base}..HEAD --reverse")
    if log is None:
        return {r.id: "the history of the run cannot be read" for r in marked}
    commits = [c for line in log if (c := line.split("\t", 1)[0]) and not PLANNING_COMMIT.match(
        line.split("\t", 1)[1] if "\t" in line else "")]
    out: dict[str, str] = {}
    pending = {r.id: r for r in marked}
    touched: dict[str, set[str]] = {}
    for commit in commits:
        if not pending:
            break
        lines = _git_lines(ctx, f"git show {commit}:{path}")
        if lines is None:
            continue
        then = {r.id: r for r in fmt.parse_plan("\n".join(lines)).rows}
        for rid in [i for i in pending if i in then and then[i].completed == pending[i].completed]:
            row = pending.pop(rid)
            if fmt.row_text(then[rid]) != fmt.row_text(row):
                out[rid] = "the row differs from the row in its marking commit"
                continue
            if commit not in touched:
                names = _git_lines(ctx, f"git diff --name-only {commit}..HEAD")
                touched[commit] = set(names) if names is not None else {row.file}
            out[rid] = "the row's file changed after its marking commit" if row.file in touched[commit] else ""
    out.update({rid: f"no commit of the run wrote the mark `{r.completed}` on this row" for rid, r in pending.items()})
    return out


def _marks(plan: fmt.Plan, criterion: str, place: str, done: bool, ctx: Any = None) -> list[CheckFinding]:
    fix = ("mark each row `✓ <date>` in its Completed cell when its change is in its file, and set `status: "
           "completed`") if done else ("keep the Completed mark of a row you leave exactly as it was, and empty the "
                                       "Completed cell of a row you change or add; the status stays `planned`")
    kept = None if done or ctx is None else _kept_marks(ctx, plan, place)
    return [_find("fail", criterion, place, b, fix) for b in fmt.mark_problems(plan, done, kept)[:10]]


def _scope(plan: fmt.Plan, criterion: str, place: str) -> list[CheckFinding]:
    return [_find("maybe", criterion, place, f"may do less than asked: {c}",
                  "do what the requirement asks, or say in the hand-off why the cut is part of the task")
            for c in fmt.scope_cuts(plan)[:6]] or [_ok(criterion, place)]


def _commands(ctx: Any, plan: fmt.Plan, criterion: str) -> list[CheckFinding]:
    found = []
    if not plan.commands:
        found.append(_find("fail", criterion, "3. Verification", "the plan lists no verification command",
                           "list each command as a bullet in a code span"))
    for cmd in plan.commands:
        bare = IN_FOLDER.sub("", cmd, count=1)  # `cd <folder> && git push` is still a push
        reason = "only the last stage pushes or opens a pull request" if bare.startswith(FINAL_ONLY) else getattr(
            ctx.resolve(cmd), "reason", None)
        if reason:
            said = f"{reason} in {REPO_FILE}" if reason == "not declared" else reason
            found.append(_find("fail", criterion, "3. Verification", f"`{cmd[:80]}` is not allowed: {said}",
                               COMMAND_FIX.get(reason, COMMAND_FIX[""])))
    return found


# What to do about each refusal of the engine's resolver. `cd <folder> && <command>` is allowed as written: the
# engine runs the command in that folder (CHK-B11), so the fix never tells a session to drop the `cd`. The commands
# a plan may list come from the repository's `tempergraph.commands.json` and read-only git (RCM-B1 to RCM-B3).
REPO_FILE = "tempergraph.commands.json"
COMMAND_FIX = {
    "not declared": f"start the command with a command the repository declares in `{REPO_FILE}` (add one there for "
                    "another toolchain) or with read-only `git`; `cd <folder> && <command>` runs it in a folder of "
                    "the repository",
    "shell metacharacter": "write one command per bullet, with no pipe, `;`, redirect or second `&&`; "
                           "`cd <folder> && <command>` is the one chain allowed",
    "change of directory outside the repository": "`cd` only to a folder inside the repository, by a relative path",
    "": "use a plain command the workflow allows; `cd <folder> && <command>` runs it in a folder of the repository",
}


def _reading_bytes(ctx: Any, plan: fmt.Plan) -> int:
    total = 0
    for name in {r.file for r in plan.rows if r.file} | set(plan.specs):
        try:
            p = (Path(ctx.workdir) / name).resolve()
            if p.is_relative_to(Path(ctx.workdir).resolve()) and p.is_file():
                total += p.stat().st_size
        except (OSError, ValueError):
            continue
    return total


def plan_check(ctx: Any) -> Any:
    """ts-plan-form, ts-plan-trace, ts-plan-links, ts-plan-size, ts-plan-scope, ts-plan-reading, ts-plan-ruleread,
    ts-plan-commit. It also records the seven facts of the plan rule's Complexity table (CDM-B2), which the switch
    `code_mode` reads."""
    text, path = _read(ctx, "plan")
    if text is None:
        return checks.result([_find("fail", "ts-plan-form", path, "the plan cannot be read",
                                    "write the plan and name its path")])
    plan = fmt.parse_plan(text)
    found = [_find("fail", "ts-plan-form", path, f"section `## {h}` is missing or out of order", f"add `## {h}`")
             for h in plan.missing]
    if not plan.handoff_lines:
        found.append(_find("fail", "ts-plan-form", path, "the hand-off section is empty",
                           "list the triage note, the hand-off and the specs the plan was written from"))
    if not plan.phases:
        found.append(_find("fail", "ts-plan-form", path, "no phase under `## 2. Phases`", "add `### Phase 1: …`"))
    if plan.complexity not in fmt.COMPLEXITY:
        found.append(_find("fail", "ts-plan-form", path, "the front matter has no `complexity: simple|complex`",
                           "state the complexity in the front matter"))
    if plan.complexity == "simple":  # a simple plan carries its task rows; a complex one gets them from expand
        found += _rows(ctx, plan, "ts-plan-form") + _commands(ctx, plan, "ts-plan-form")
    found += _marks(plan, "ts-plan-form", path, done=False, ctx=ctx)
    if not any(f.status == "fail" for f in found):
        found.append(_ok("ts-plan-form", path))
    if plan.complexity == "simple":
        found += _links_of(plan, "ts-plan-links", path)
    else:
        found.append(_find("n_a", "ts-plan-links", path, "a complex plan gets its task rows from the expand step"))

    note_text, note_path = _read(ctx, "triage_note")
    if note_text is None:
        found.append(_find("fail", "ts-plan-trace", note_path, "the triage note cannot be read"))
    else:
        criteria = fmt.parse_triage(note_text).criteria
        lost = [_find("fail", "ts-plan-trace", path, f"acceptance criterion {n} is named by no requirement",
                      f"add a requirement row whose Criteria cell holds `AC {n}`")
                for n in criteria if n not in plan.requirement_criteria]
        if plan.complexity == "simple":  # a complex plan gets its proof table from expand
            lost += [_find("fail", "ts-plan-trace", "3. Verification", b,
                           "add a row `| AC <n> | <test file> | <command> |` for each criterion")
                     for b in fmt.proof_problems(plan, criteria)[:8]]
        found += lost or [_ok("ts-plan-trace", path)]

    value = _value(ctx, "complexity")
    reading = _reading_bytes(ctx, plan)
    over = fmt.simple_overruns(plan, reading)
    # A complex plan carries no task rows, so the gate measures only its phases and weights: a plan whose reading set
    # is too large for `simple` says so with a heavy phase (seen in run i16, where the plan flipped between the two).
    heavy_hint = "mark the phase with the large reading set `Weight: heavy (large-context)` (rows are not measured)"
    bad: list[tuple[str, str]] = []
    if value is not None and plan.complexity and value != plan.complexity:
        bad.append((f"the complexity value `{value}` differs from the plan's `{plan.complexity}`",
                    "state the complexity the signs give"))
    if plan.complexity == "simple" and over:
        reading_only = any(o.startswith("reading_bytes") for o in over) and not plan.heavy
        bad.append(("the plan says `simple` but measures over the limit: " + "; ".join(over[:4]),
                    "state `complex`" + ("; " + heavy_hint if reading_only else "")))
    if plan.complexity == "complex" and not over:
        bad.append(("the plan says `complex` but no measured sign is over the limit for `simple`",
                    "state `simple` and write the rows, or " + heavy_hint))
    for phase, sign in plan.heavy.items():
        if sign not in fmt.HEAVY_SIGNS:
            bad.append((f"phase `{phase}` is heavy with no sign of {', '.join(fmt.HEAVY_SIGNS)}",
                        "state the complexity the signs give"))
    found += [_find("fail", "ts-plan-size", path, b, fix) for b, fix in bad] or [
        _ok("ts-plan-size", path)]
    found += _scope(plan, "ts-plan-scope", path)
    found += _prompt_says("ts-plan-reading")
    found += _ruleread(ctx, "plan", "ts-plan-ruleread")
    found.append(_committed(ctx, "ts-plan-commit"))
    res = _result(ctx, found, plan)
    res.facts = {k: str(v) for k, v in fmt.plan_facts(plan, reading).items()}  # CDM-B2
    return res


def expand_check(ctx: Any) -> Any:
    """ts-exp-rows, ts-exp-tests, ts-exp-links, ts-exp-commands, ts-exp-scope, ts-exp-ruleread, ts-exp-opened,
    ts-exp-commit."""
    text, path = _read(ctx, "phases")
    if text is None:
        return checks.result([_find("fail", "ts-exp-rows", path, "the expanded plan cannot be read",
                                    "write the task rows into the plan and name its path")])
    plan = fmt.parse_plan(text)
    empty, bad = fmt.row_problems(plan)
    found: list[CheckFinding] = []
    if not plan.phases:
        empty = ["(none)"]
    rows = [_find("fail", "ts-exp-rows", f"{path}: {p}", "the phase has no task row", f"add a table `{ROW_TABLE}`")
            for p in empty] + _marks(plan, "ts-exp-rows", path, done=False, ctx=ctx)
    found += rows or [_ok("ts-exp-rows", path)]
    note_text, note_path = _read(ctx, "triage_note")
    tests = [_find("fail", "ts-exp-tests", path, b, "put the test row first and name its criterion") for b in bad[:8]]
    if note_text is None:
        tests.append(_find("fail", "ts-exp-tests", note_path, "the triage note cannot be read"))
    else:
        tests += [_find("fail", "ts-exp-tests", "3. Verification", b,
                        "add a row `| AC <n> | <test file> | <command> |` for each criterion")
                  for b in fmt.proof_problems(plan, fmt.parse_triage(note_text).criteria)[:8]]
    found += tests or [_ok("ts-exp-tests", path)]
    found += _links_of(plan, "ts-exp-links", path)
    found += _commands(ctx, plan, "ts-exp-commands") or [_ok("ts-exp-commands", path)]
    found += _scope(plan, "ts-exp-scope", path)
    found += _ruleread(ctx, "expand", "ts-exp-ruleread")
    found += _opened_rows(ctx, plan, "ts-exp-opened")
    found.append(_committed(ctx, "ts-exp-commit"))
    return checks.result(found)


# ---------------------------------------------------------------------------------------------
# code


def _quick(ctx: Any) -> fmt.Triage | None:
    """The triage note of a run in the quick lane, else None."""
    route = _value(ctx, "route")
    if route not in (None, "quick"):
        return None
    text, _ = _read(ctx, "triage_note")
    note = fmt.parse_triage(text) if text is not None else None
    if route is None:  # no value was handed over (a fixture): the note's own route, when no plan was written
        planned = any(checks.artifact_path(ctx, key) for key in ("plan", "phases"))
        return note if note is not None and note.route == "quick" and not planned else None
    return note


def _plan(ctx: Any) -> tuple[fmt.Plan | None, str]:
    """The plan the code step built from: the expanded one when expand ran. In the quick lane the triage
    note's Change section stands in: its commands, and one row per acceptance criterion."""
    note = _quick(ctx)
    if note is not None:
        rows = [fmt.Row(id=f"AC {n}", kind="test", file=(note.change_tests or [""])[0], proves=f"AC {n}",
                        phase="quick") for n in note.criteria]
        return fmt.Plan(rows=rows, commands=list(note.change_commands)), checks.artifact_path(ctx, "triage_note") or ""
    for key in ("phases", "plan"):
        text, path = _read(ctx, key)
        if text is not None:
            return fmt.parse_plan(text), path
    return None, "plan"


def _is_test(path: str) -> bool:
    return bool(set(Path(path).parts[:-1]) & TEST_DIRS or TEST_FILE.match(Path(path).name))


def _proof(ctx: Any, plan: fmt.Plan, criterion: str) -> tuple[list[CheckFinding], list[str]]:
    """Each criterion a test row proves is carried by a test in the row's file, and that test is not skipped.
    In the quick lane any of the note's test files may carry it. Returns the findings and `id -> file` lines."""
    note = _quick(ctx)
    found: list[CheckFinding] = []
    links: list[str] = []
    for row in plan.rows:
        if row.kind != "test":
            continue
        files = list(note.change_tests) if note is not None else [row.file]
        texts = {f: _read_path(ctx, f) for f in files if f}
        gone = [f for f, text in texts.items() if text is None]
        if gone or not texts:
            found.append(_find("fail", criterion, gone[0] if gone else row.id,
                               f"the test file of row `{row.id}` does not exist", "write the test in the named file"))
            continue
        ids = fmt.ANY_ID.findall(row.proves) or [f"AC {n}" for n in sorted(fmt.task_criteria(row.proves))]
        for cid in ids:
            got = {f: fmt.carried(text or "", cid) for f, text in texts.items()}
            live = [f for f, (named, skipped) in got.items() if named and not skipped]
            if live:
                links.append(f"{cid} -> {live[0]}")
            elif any(named for named, _ in got.values()):
                found.append(_find("fail", criterion, next(iter(texts)), f"the test that carries {cid} is skipped",
                                   "remove the skip; a criterion is proved by a test that runs"))
            else:
                found.append(_find("fail", criterion, next(iter(texts)), f"no test in the file carries {cid}",
                                   f"name {cid} in the test's name or in a comment on it"))
    return (found[:12] or [_ok(criterion)]), links


IGNORED_BY_LANE = (".claude/", "docs/tasks/", ".tempergraph/")
SHORTSTAT = re.compile(r"(\d+) insertion|(\d+) deletion")


def _lane(ctx: Any, criterion: str) -> list[CheckFinding]:
    """The guard of the quick lane, measured on what the run changed. A run in another lane is not measured."""
    note = _quick(ctx)
    if note is None:
        return [_find("n_a", criterion, message="the run is not in the quick lane")]
    fix = ("end the step with `UPSTREAM triage: the task is larger than the quick lane`, so triage plans it")
    described = set(_setup_specs(ctx))
    prepared = {routing.COMMANDS_FILE} if _prepared_commands(ctx) else set()
    changed = [p for p in ctx.git.changed_paths if not p.startswith(IGNORED_BY_LANE)
               and p not in ("CLAUDE.md", "AGENTS.md") and p not in described and p not in prepared]
    found = [_find("fail", criterion, p, "the quick lane changed a spec or a decision record", fix)
             for p in changed if p.endswith((".spec.md", ".adr.md"))][:4]
    code = [p for p in changed if not p.endswith(".md") and not _is_test(p)]
    named = set(note.change_files) | set(note.change_tests)
    found += [_find("fail", criterion, p, "changed, but the triage note's Change section does not name it", fix)
              for p in code if p not in named][:6]
    if len(code) > fmt.QUICK_MAX["code_files"]:
        found.append(_find("fail", criterion, "", f"{len(code)} code files changed, over "
                           f"{fmt.QUICK_MAX['code_files']}", fix))
    measured = [p for p in changed if not p.endswith(".md")][:20]
    if ctx.git.base and measured:
        run = ctx.run(f"git diff --shortstat {ctx.git.base} -- {' '.join(measured)}")
        lines = sum(int(a or b) for a, b in SHORTSTAT.findall(str(run.tail or ""))) if run.exit_code == 0 else 0
        if lines > fmt.QUICK_MAX["lines"]:
            found.append(_find("fail", criterion, "", f"{lines} changed lines, over {fmt.QUICK_MAX['lines']}", fix))
    return found or [_ok(criterion)]


@dataclass(frozen=True, kw_only=True)
class _Environmental(CheckFinding):
    """A command that fails at the gate for a reason the code step cannot fix: it fails the same at the run's base,
    or no file the run changed is named in its output (ts-code-base, ts-code-touch)."""


FIX_COMMAND = "fix the code or the test until the command exits 0"


def _named_in(tail: str, path: str) -> bool:
    return re.search(r"(?<![\w.-])" + re.escape(path) + r"(?![\w-])", tail) is not None


def _touches(ctx: Any, cmd: str, tail: str) -> str | None:
    """The first path the run changed that the command's last lines name, written from the repository root or from
    the folder the command ran in (ts-code-touch)."""
    folder = re.match(r"^cd\s+(\S+)\s*&&", cmd)
    prefix = folder.group(1).strip("/") + "/" if folder else ""
    for path in ctx.git.changed_paths:
        if _named_in(tail, path) or (prefix and path.startswith(prefix) and _named_in(tail, path[len(prefix):])):
            return str(path)
    return None


def _compared(ctx: Any, cmd: str, run: Any, criterion: str) -> CheckFinding:
    """A command that finished with a non-zero exit at the gate, compared with the run's base commit. The base run
    is asked for with reuse, so it is made once per visit (ts-code-spend, CHK-B20)."""
    place = cmd[:80]
    there = "none"
    why = "not compared: the run has no base commit"
    verdict = "fail"
    if ctx.git.base:
        base = ctx.run(cmd, reuse=True, at_base=True, min_start_s=run.duration_s)
        there = "none" if base.exit_code is None else str(base.exit_code)
        if base.not_started:
            why = "not compared: the command could not start at the base commit"
        elif base.timed_out or not base.finished:
            why = "not compared: the command did not finish at the base commit"
        elif base.exit_code == 0:
            why = "caused by the change: the command exits 0 at the base commit"
        elif base.exit_code == run.exit_code:
            why, verdict = "environmental: it fails the same at the base commit", "environmental"
        elif (named := _touches(ctx, cmd, str(run.tail or ""))) is not None:
            why = f"caused by the change: its output names the changed file {named}"
        else:
            why, verdict = "environmental: its output names no file the run changed", "environmental"
    tail = " ".join(str(run.tail or "").split())[-120:]
    message = f"`{cmd[:60]}` exit {run.exit_code} at the gate, {there} at the base: {why}"
    if verdict == "environmental":
        return _Environmental(status="fail", criterion=criterion, place=place, message=message)
    return _find("fail", criterion, place, f"{message}: {tail}", FIX_COMMAND)


def _run_commands(ctx: Any, plan: fmt.Plan, criterion: str, compare: bool = False
                  ) -> tuple[list[CheckFinding], list[str]]:
    """The findings of the plan's verification commands and one evidence line per command: `reused` for a stored
    result, `run` for a started command, `not run` for one that did not start (ts-code-ran). With `compare` (the code
    gate), a command that fails is run once at the run's base commit, and a failure that was there before the change
    is environmental (ts-code-base to ts-code-spend)."""
    found = _commands(ctx, plan, criterion)
    if found:
        return found, [f"`{cmd}`: not run" for cmd in plan.commands]
    lines: list[str] = []
    for cmd in plan.commands:
        run = ctx.run(cmd, reuse=True)
        if run.not_started:
            lines.append(f"`{cmd}`: not run")
            found.append(_find("fail", criterion, cmd[:80], "the command did not start (refused, or out of time)"))
            continue
        lines.append(f"`{cmd}`: {'reused' if run.reused else 'run'}")
        if compare and run.finished and run.exit_code not in (0, None):
            found.append(_compared(ctx, cmd, run, criterion))
        elif run.timed_out or not run.finished or run.exit_code != 0:
            tail = " ".join(str(run.tail or "").split())[-120:]
            note = "not compared with the base commit: it did not finish at the gate; " if compare else ""
            found.append(_find("fail", criterion, cmd[:80], f"{note}exit {run.exit_code}: {tail}", FIX_COMMAND))
    return found or [_ok(criterion)], lines


def _verify(ctx: Any, plan: fmt.Plan, criterion: str, compare: bool = False) -> list[CheckFinding]:
    return _run_commands(ctx, plan, criterion, compare)[0]


def _evidence(lines: list[str], criterion: str) -> CheckFinding:
    """ts-code-ran: the gate's own answer for each verification command, counted from its lines."""
    if not lines:
        return _find("n_a", criterion, message="no verification command was run by this gate")
    reused = sum(1 for ln in lines if ln.endswith(": reused"))
    ran = sum(1 for ln in lines if ln.endswith(": run"))
    return _find("pass", criterion, message=f"{reused} of {len(lines)} verification commands were reused, {ran} run")


def _reuse(ctx: Any, criterion: str) -> CheckFinding:
    """ts-code-reuse, from the gate's own command runs: every verification command is asked for with reuse, so
    the engine takes a result recorded for the same tree instead of starting it again (CHK-B13). The finding
    says how many were reused; a command asked for twice in one gate run with no reuse is the failure."""
    if ctx.reuse_store is None:
        return _find("n_a", criterion, message="no store of earlier command runs (the gate runs outside a run)")
    runs = [r for r in ctx.runs if not r.not_started and not r.at_base]  # a run at the base is not a second start
    started: set[tuple[str, ...]] = set()
    for r in runs:
        if r.reused:
            continue
        if tuple(r.argv) in started:
            return _find("fail", criterion, " ".join(r.argv)[:80], "the command ran twice on one tree",
                         "ask for the command once per gate run, with reuse")
        started.add(tuple(r.argv))
    return _find("pass", criterion, message=f"{sum(1 for r in runs if r.reused)} of {len(runs)} verification runs "
                 "were taken from a result recorded for the same tree")


def code_check(ctx: Any) -> Any:
    """ts-code-rows, ts-code-changed, ts-code-verify, ts-code-reuse, ts-code-proof, ts-code-lane, ts-code-once,
    ts-code-commit, ts-code-base, ts-code-touch, ts-code-passes, ts-code-nobase, ts-code-mixed, ts-code-evidence,
    ts-code-spend, ts-code-preview, ts-code-previewed, ts-code-session, ts-code-rerun, ts-code-ran,
    ts-code-ruleread, ts-code-order.

    The marks come first: a plan with a row not marked completed goes back to the code step at once, with no
    command run. Marks are claims, so a marked plan is then verified as before, and each marked row's file must
    be among the paths the run changed. Every verification command is run here whatever the step reported; one that
    fails is run once at the run's base commit, and a failure that was there before the change escalates.

    In a preview (the session's own call of the check, before its report is handed over and before the commit
    that follows it) the marks still come first, and the commands run; the report is not read for failures and
    the uncommitted tree is no failure. The gate cannot see that run, so ts-code-previewed, ts-code-session and
    ts-code-rerun are recorded n_a: the package's tests prove them."""
    plan, path = _plan(ctx)
    if plan is None:
        return checks.result([_find("fail", "ts-code-rows", path, "the plan cannot be read")])
    report, report_path = _read(ctx, "code_report")
    quick = _quick(ctx) is not None
    found: list[CheckFinding] = []
    if report is None:
        if not ctx.preview:
            found.append(_find("fail", "ts-code-rows", report_path, "the code report cannot be read",
                               "write the report and name its path"))
    else:
        wanted = fmt.QUICK_REPORT_HEADINGS if quick else fmt.REPORT_HEADINGS
        found += [_find("fail", "ts-code-rows", report_path, f"section `## {h}` is missing or out of order",
                        f"add `## {h}`") for h in fmt.headings_missing(report, wanted) if not ctx.preview]
    if not plan.rows:
        found.append(_find("fail", "ts-code-rows", path, "the plan has no task row"))
    elif quick:  # no plan to mark: the report's rows, one per acceptance criterion
        status = fmt.parse_report(report or "")
        found += [_find("fail", "ts-code-rows", report_path, f"row `{r.id}` is not marked `done` in the report",
                        "finish the row, or say which earlier output makes it impossible")
                  for r in plan.rows if status.get(r.id) != "done" and not ctx.preview][:10]
    else:
        found += _marks(plan, "ts-code-rows", path, done=True)
    if any(f.status == "fail" for f in found):  # the cheap return: nothing is run on an unfinished plan
        return _result(ctx, found + ([] if ctx.preview else [_committed(ctx, "ts-code-commit")]), plan)
    found.append(_ok("ts-code-rows", report_path if quick else path))
    if quick or not ctx.git.base:
        found.append(_find("n_a", "ts-code-changed", message="the quick lane has no plan to mark" if quick else
                           "no base commit to compare with"))
    else:
        changed = set(ctx.git.changed_paths)
        found += [_find("fail", "ts-code-changed", r.file, f"row `{r.id}` is marked completed but its file did not "
                        "change in the run", "make the row's change, or clear its mark and say why")
                  for r in plan.rows if r.file and r.file not in changed][:10] or [_ok("ts-code-changed", path)]
    verified, lines = _run_commands(ctx, plan, "ts-code-verify", compare=True)
    found += verified
    reading = _reading_lines(ctx)  # its git run is reused on an unchanged tree, and counted by the line below
    found.append(_reuse(ctx, "ts-code-reuse"))
    proof, links = _proof(ctx, plan, "ts-code-proof")
    found += _test_first(ctx, plan, "ts-code-order")
    found += proof + _lane(ctx, "ts-code-lane") + _prompt_says("ts-code-once") + _prompt_says("ts-code-preview")
    found.append(_evidence(lines, "ts-code-ran"))
    found += [_find("n_a", cid, message="the session's own run is not visible to the gate; the package's tests "
                    "prove it") for cid in ("ts-code-previewed", "ts-code-session", "ts-code-rerun")]
    found += _ruleread(ctx, "code", "ts-code-ruleread")
    if not ctx.preview:
        found.append(_committed(ctx, "ts-code-commit"))
    if any(f.status == "fail" and not isinstance(f, _Environmental) for f in found):
        # ts-code-mixed: the step retries, so the retry lists only what it can fix; the environmental command stays
        # in the evidence
        found = [replace(f, status="maybe") if isinstance(f, _Environmental) else f for f in found]
    return _result(ctx, found, plan, links, reading=reading, commands=lines)


# ---------------------------------------------------------------------------------------------
# phase


def phase_check(ctx: Any) -> Any:
    """ts-phs-rows, ts-phs-changed, ts-phs-proof, ts-phs-order, ts-phs-commit: one attempt of one phase item, read on
    the rows of that phase only (PHC-B6 to PHC-B8). No finding names a row of another phase, and none names a step to go
    back to: the checks of the whole change and the lines back stay with the code gate (PHC-B13, PHC-B14)."""
    text, path = _read(ctx, "phases")
    if text is None:
        return checks.result([_find("fail", "ts-phs-rows", path, "the expanded plan cannot be read",
                                    "keep the plan at its path")])
    whole = fmt.parse_plan(text)
    if ctx.item is None:  # no item (a fixture run of the check): the rows of the whole plan stand as one phase
        phase, label = fmt.Plan(rows=list(whole.rows), phases=list(whole.phases)), "the plan"
    else:
        block = next((b for b in routing.phase_blocks(text) if b.id == ctx.item), None)
        if block is None:
            return checks.result([_find("fail", "ts-phs-rows", path, f"the plan has no phase for the item `{ctx.item}`",
                                        "keep the phase headings of the plan as they are")])
        phase = fmt.Plan(rows=[r for r in whole.rows if r.phase == block.heading], phases=[block.heading])
        label = _phase_label(block.heading)
    found: list[CheckFinding] = []
    if not phase.rows:
        found.append(_find("fail", "ts-phs-rows", label, f"{label} has no task row", "do not change the plan's rows"))
    bad = [(r, fmt.DONE_MARK.match(r.completed)) for r in phase.rows]
    found += [_find("fail", "ts-phs-rows", r.id, f"row `{r.id}` of {label} is not marked completed" if not r.completed
                    else f"row `{r.id}` is marked `{r.completed}`; a mark is `✓ YYYY-MM-DD`",
                    "build the row, then mark it `✓ <date>` in its Completed cell") for r, m in bad if m is None]
    found += [] if any(f.status == "fail" for f in found) else [_ok("ts-phs-rows", label)]
    base = ctx.git.base if ctx.git is not None else ""
    if not base:
        found.append(_find("n_a", "ts-phs-changed", message="no base commit to compare with"))
    else:
        changed = set(ctx.git.changed_paths)
        marked = [r for r, m in bad if m is not None]
        # KMK-B8: the paths count from the run's base commit, so a mark kept from an earlier visit stands by its file
        found += [_find("fail", "ts-phs-changed", r.file, f"row `{r.id}` is marked completed but its file did not "
                        "change in the run", "make the row's change, or clear its mark and say why")
                  for r in marked if r.file and r.file not in changed] or [_ok("ts-phs-changed", label)]
    found += _proof(ctx, phase, "ts-phs-proof")[0]
    found += _test_first(ctx, phase, "ts-phs-order")
    found.append(_committed(ctx, "ts-phs-commit"))
    return _result(ctx, found, phase)


# ---------------------------------------------------------------------------------------------
# the outcome gate


def _docs_only(ctx: Any) -> bool:
    return _value(ctx, "route") == "discovery-only"


def _at_ref(ctx: Any, ref: str, path: str) -> str | None:
    """The file as it is at a commit; None when the commit has no such file or it cannot be read."""
    if not ref:
        return None
    run = ctx.run(f"git show {ref}:{path}")
    if run.not_started or run.exit_code != 0:
        return None
    try:
        return Path(run.output_path).read_text(encoding="utf-8", errors="replace")
    except OSError:
        return None


def _at_base(ctx: Any, path: str) -> str | None:
    """The file as it was at the run's base commit; None with no base, or when the run created the file."""
    return _at_ref(ctx, ctx.git.base, path)


def _unseen(ctx: Any, head: str, path: str) -> bool:
    """True when the base branch's head holds a commit that changed the file and the run's branch lacks it; a run
    that merged the base branch has seen every change up to the commit it merged (SBS-B2)."""
    run = ctx.run(f"git log --oneline -1 HEAD..{head} -- {path}")
    if run.not_started or run.exit_code != 0:
        return True
    try:
        return bool(Path(run.output_path).read_text(encoding="utf-8", errors="replace").strip())
    except OSError:
        return True


def _fresh(ctx: Any, specs: list[str]) -> list[CheckFinding]:
    """ts-spec-fresh (SBS-B1 to SBS-B3): no spec the run edited reads differently at the base branch's head than at
    the run's base commit, when the head holds a commit that changed it and the run's branch lacks."""
    base, head = ctx.git.base, ctx.git.base_head
    if not base or not head:
        return [_find("n_a", "ts-spec-fresh", message="the run has no base branch to compare with")]
    if not specs:
        return [_find("n_a", "ts-spec-fresh", message="the run edited no spec")]
    run = ctx.run(f"git log --oneline -1 {base}..{head}")
    if run.not_started or run.exit_code != 0:
        return [_find("n_a", "ts-spec-fresh", message="the base branch's head could not be compared with the run's "
                                                      "base commit")]
    try:
        moved = bool(Path(run.output_path).read_text(encoding="utf-8", errors="replace").strip())
    except OSError:
        moved = False
    if not moved:
        return [_ok("ts-spec-fresh")]
    found = [_find("fail", "ts-spec-fresh", path,
                   "the base branch changed this spec since the run started (it reads differently at its head than "
                   "at the run's base commit)", "start the task again from the head of the base branch")
             for path in specs
             if _at_ref(ctx, base, path) != _at_ref(ctx, head, path) and _unseen(ctx, head, path)]
    return found or [_ok("ts-spec-fresh")]


def _traced(ctx: Any, specs: list[str], files: list[str]) -> list[CheckFinding]:
    """ts-traced: each criterion the run added or reworded in an edited spec, and each old one that proves a
    behaviour the run added or changed, is named by a test that runs. A spec edited only to add a link or a line
    elsewhere asks nothing of its old criteria (B22); with no base to compare, every criterion counts."""
    wanted: dict[str, str] = {}
    described = set(_setup_specs(ctx))  # specs of existing behaviour: their tests get ids as tasks touch them
    for path in specs:
        if path in described:
            continue
        now = _read_path(ctx, path) or ""
        before = _at_base(ctx, path)
        ids = set(fmt.parse_spec(now).criteria) if before is None else fmt.changed_criteria(before, now)
        wanted.update({cid: path for cid in sorted(ids)})
    if not wanted:
        return [_find("n_a", "ts-traced", message="the run added or changed no acceptance criterion and no "
                      "behaviour an old criterion proves")]
    tests = [f for f in files if _is_test(f) and not f.endswith(".md")]
    seen: set[str] = set()
    skipped: set[str] = set()
    for f in tests:
        text = _read_path(ctx, f) or ""
        for cid in fmt.linked_ids(text) & set(wanted):
            (skipped if fmt.carried(text, cid)[1] else seen).add(cid)
        if len(seen) == len(wanted):
            break
    lost = sorted(set(wanted) - seen)[:12]
    return [_find("fail", "ts-traced", wanted[c], f"{c} is named only by a skipped test" if c in skipped else
                  f"{c} is named by no test", f"name {c} in a test that runs and proves it") for c in lost] or [
        _ok("ts-traced")]


def _collateral(ctx: Any, specs: list[str]) -> list[CheckFinding]:
    """A warning: a spec file changed with no change to a behaviour block or a criterion row."""
    base = ctx.git.base
    if not base:
        return [_find("n_a", "ts-collateral", message="no base commit to compare with")]
    found = []
    for path in specs:
        run = ctx.run(f"git diff --unified=0 {base} -- {path}")
        if run.not_started or run.exit_code != 0:
            continue
        try:
            diff = Path(run.output_path).read_text(encoding="utf-8", errors="replace")
        except OSError:
            continue
        changed = [ln[1:] for ln in diff.splitlines() if ln[:1] in "+-" and not ln.startswith(("+++", "---"))]
        if not changed:
            continue
        now = fmt.parse_spec(_read_path(ctx, path) or "")
        if now.legacy:
            continue
        meaningful = any(fmt.BEHAVIOUR_HEAD.match(ln) or fmt.BEHAVIOUR_LINE.match(ln.strip())
                         or fmt.SCENARIO_LINE.match(ln) or fmt.CRITERION_LINE.match(ln) for ln in changed)
        if not meaningful:
            found.append(_find("maybe", "ts-collateral", path,
                               "edited with no change to a behaviour or an acceptance criterion",
                               "revert the edit unless the task needs it"))
    return found or [_ok("ts-collateral")]


def outcome_check(ctx: Any) -> Any:
    """ts-committed, ts-spec-form, ts-spec-cap, ts-spec-links, ts-spec-fresh, ts-traced, ts-verify, ts-collateral."""
    found = [_committed(ctx, "ts-committed")]
    found += _spec_form(ctx, "ts-spec-form", "ts-spec-cap")
    specs, _ = _edited_specs(ctx)
    # Only the edited specs: a task note or a plan names ids the task retired on purpose, and is history.
    found += _links(ctx, "ts-spec-links", specs) if specs else [
        _find("n_a", "ts-spec-links", message="the run edited no spec")]
    found += _fresh(ctx, specs)
    if _docs_only(ctx):
        found += [_find("n_a", c, message="the run delivers documents only") for c in ("ts-traced", "ts-verify")]
    else:
        found += _traced(ctx, specs, _walk(ctx))
        plan, path = _plan(ctx)
        found += _verify(ctx, plan, "ts-verify") if plan is not None else [
            _find("fail", "ts-verify", path, "the plan cannot be read")]
    found += _collateral(ctx, specs)
    push = "The run's branch is pushed." if ctx.git.pushed else "The run's branch is not pushed."
    return _result(ctx, found, _plan(ctx)[0], facts=[push])  # evidence only: a push never decides the result


def owner_answers_check(answers: dict[str, Any]) -> list[str]:
    """The answers check of the pause `ask_owner` (OWQ-B5, ASK-B11): a pure function of the answers. One problem for
    each reading of a gap answered `wrong`, naming the gap and saying that the run can be stopped to correct the task
    or the answer changed to `right`; an owner decision is never refused, and no `wrong` gives an empty list."""
    return [f"the reading of {name.upper()} is called wrong: stop the run to correct the task, or answer `{name}` "
            f"with `right`" for name, value in answers.items() if value == "wrong"]
