"""The model-free checks of every gate and of the outcome gate. Each finding names one criterion of
`outcome.json`; the formats come from `specfmt`, which the rule files under `rules/` describe in words.

A check reads the workspace and the engine's git facts; it writes nothing and trusts nothing a step said."""

from __future__ import annotations

import os
import re
from pathlib import Path
from typing import Any

from tempergraph.api import CheckFinding, checks

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
                                 "run each verification command of the plan once, after the last phase and before "
                                 "you write the report",
                                 "in the quick lane, the note's `verify` commands once, after the last criterion")),
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


def _spec_form(ctx: Any, criterion: str, cap_criterion: str | None = None) -> list[CheckFinding]:
    """The spec rule's structure check on every edited spec; the line cap under `cap_criterion` if given."""
    have, gone = _edited_specs(ctx)
    found = [_find("fail", criterion, p, "the hand-off lists this spec but the file does not exist",
                   "write the spec or drop it from the list") for p in gone]
    over: list[CheckFinding] = []
    for path in have:
        spec = fmt.parse_spec(_read_path(ctx, path) or "")
        if spec.lines > fmt.SPEC_CAP_LINES:
            over.append(_find("fail", cap_criterion or criterion, path,
                              f"{spec.lines} lines, over the cap of {fmt.SPEC_CAP_LINES}",
                              "split the spec by capability, or compress it"))
        if spec.legacy:
            found.append(_find("n_a", criterion, path, "a spec in the earlier layout is not checked for form"))
            continue
        found += [_find("fail", criterion, f"{path}:{line}", message, fix) for line, message, fix in spec.problems[:8]]
    if not any(f.status == "fail" for f in found):
        found.append(_ok(criterion) if have else _find("n_a", criterion, message="the run edited no spec"))
    if cap_criterion:
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


def _result(ctx: Any, found: list[CheckFinding], plan: fmt.Plan | None = None,
            links: list[str] | None = None) -> Any:
    """The result, with the facts a read-only judge cannot get by itself as its evidence."""
    bad = "; ".join(f"{f.criterion}: {f.message}" for f in found if f.status == "fail")
    specs, _ = _edited_specs(ctx)
    lines = [bad or f"{len(found)} checked"]
    changed = [p for p in ctx.git.changed_paths if not p.startswith(".claude/rules/")]
    if changed:
        lines.append("Changed paths since the run's base: " + ", ".join(changed[:120]))
    if specs:
        lines.append("Edited specs: " + ", ".join(specs))
        related = _related(ctx, specs, _spec_index(ctx, _walk(ctx)), plan)
        lines.append("Related specs: " + (", ".join(related[:40]) or "none"))
    elif plan is not None and plan.specs:
        lines.append("Related specs: " + ", ".join(plan.specs[:40]))
    if links:
        lines.append("Criterion tests: " + "; ".join(links[:40]))
    return checks.result(found, evidence="\n".join(lines))


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
    index = _spec_index(ctx, _walk(ctx))
    overview = checks.artifact_path(ctx, "overview")
    if overview and not overview.endswith(".spec.md"):  # the overview is a spec wherever it is
        for own in fmt.defined_ids(_read_path(ctx, overview) or ""):
            index.setdefault(own, []).append(overview)
    found: list[CheckFinding] = []
    for path in docs:
        text = _read_path(ctx, path) or ""
        if path.endswith(".spec.md"):
            for own in fmt.defined_ids(text):  # a changed spec inside a skipped folder still counts
                if path not in index.get(own, []):
                    index.setdefault(own, []).append(path)
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
    """ts-set-form, ts-set-listed, ts-set-links, ts-set-commit."""
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
    found.append(_committed(ctx, "ts-set-commit"))
    return checks.result(found)


# ---------------------------------------------------------------------------------------------
# triage


def triage_check(ctx: Any) -> Any:
    """ts-tri-form, ts-tri-route, ts-tri-commit."""
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
    found.append(_committed(ctx, "ts-tri-commit"))
    return checks.result(found)


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
    """ts-dis-form, ts-dis-names, ts-dis-links, ts-dis-reading, ts-dis-narrow, ts-dis-commit."""
    text, path = _read(ctx, "handoff")
    if text is None:
        return checks.result([_find("fail", "ts-dis-form", path, "the hand-off cannot be read",
                                    "write the hand-off and name its path")])
    found = [_find("fail", "ts-dis-form", path, f"hand-off section `## {h}` is missing or out of order",
                   f"add `## {h}`") for h in fmt.headings_missing(text, fmt.HANDOFF_HEADINGS) if h != READING]
    found += _spec_form(ctx, "ts-dis-form")
    found += _names(ctx, "ts-dis-names")
    found += _links(ctx, "ts-dis-links")
    found += _reading(ctx, text, path)
    found += _prompt_says("ts-dis-narrow")
    found.append(_committed(ctx, "ts-dis-commit"))
    return _result(ctx, found)


READING = "Reading list"
SHORT_READING_MAX = 10  # the short visit's reading limit (decision record 0003); its reading list holds at most this
NOT_COVERED = re.compile(r"\bnot covered\b", re.I)


def discovery_short_check(ctx: Any) -> Any:
    """ts-dsh-form, ts-dsh-cited, ts-dsh-only, ts-dsh-settled, ts-dsh-reading, ts-dsh-limit, ts-dsh-commit.

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


def _marks(plan: fmt.Plan, criterion: str, place: str, done: bool) -> list[CheckFinding]:
    fix = ("mark each row `✓ <date>` in its Completed cell when its change is in its file, and set `status: "
           "completed`") if done else "leave Completed empty and the status `planned`: the code step marks them"
    return [_find("fail", criterion, place, b, fix) for b in fmt.mark_problems(plan, done)[:10]]


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
            found.append(_find("fail", criterion, "3. Verification", f"`{cmd[:80]}` is not allowed: {reason}",
                               COMMAND_FIX.get(reason, COMMAND_FIX[""])))
    return found


# What to do about each refusal of the engine's resolver. `cd <folder> && <command>` is allowed as written: the
# engine runs the command in that folder (CHK-B11), so the fix never tells a session to drop the `cd`.
ALLOWED_SHAPES = ", ".join(f"`{c}`" for c in ("pytest", "python -m pytest", "python3 -m pytest", "ruff check", "mypy"))
COMMAND_FIX = {
    "not declared": f"start the command with a prefix the workflow allows ({ALLOWED_SHAPES}, read-only `git`); "
                    "`cd <folder> && <command>` runs it in a folder of the repository",
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
    """ts-plan-form, ts-plan-trace, ts-plan-links, ts-plan-size, ts-plan-scope, ts-plan-reading, ts-plan-commit."""
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
    found += _marks(plan, "ts-plan-form", path, done=False)
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
    over = fmt.simple_overruns(plan, _reading_bytes(ctx, plan))
    bad = []
    if value is not None and plan.complexity and value != plan.complexity:
        bad.append(f"the complexity value `{value}` differs from the plan's `{plan.complexity}`")
    if plan.complexity == "simple" and over:
        bad.append("the plan says `simple` but measures over the limit: " + "; ".join(over[:4]))
    if plan.complexity == "complex" and not over:
        bad.append("the plan says `complex` but no measured sign is over the limit for `simple`")
    for phase, sign in plan.heavy.items():
        if sign not in fmt.HEAVY_SIGNS:
            bad.append(f"phase `{phase}` is heavy with no sign of {', '.join(fmt.HEAVY_SIGNS)}")
    found += [_find("fail", "ts-plan-size", path, b, "state the complexity the signs give") for b in bad] or [
        _ok("ts-plan-size", path)]
    found += _scope(plan, "ts-plan-scope", path)
    found += _prompt_says("ts-plan-reading")
    found.append(_committed(ctx, "ts-plan-commit"))
    return _result(ctx, found, plan)


def expand_check(ctx: Any) -> Any:
    """ts-exp-rows, ts-exp-tests, ts-exp-links, ts-exp-commands, ts-exp-scope, ts-exp-commit."""
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
            for p in empty] + _marks(plan, "ts-exp-rows", path, done=False)
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
    changed = [p for p in ctx.git.changed_paths if not p.startswith(IGNORED_BY_LANE)
               and p not in ("CLAUDE.md", "AGENTS.md") and p not in described]
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


def _verify(ctx: Any, plan: fmt.Plan, criterion: str) -> list[CheckFinding]:
    found = _commands(ctx, plan, criterion)
    if found:
        return found
    for cmd in plan.commands:
        run = ctx.run(cmd, reuse=True)
        if run.not_started:
            found.append(_find("fail", criterion, cmd[:80], "the command did not start (refused, or out of time)"))
        elif run.timed_out or not run.finished or run.exit_code != 0:
            tail = " ".join(str(run.tail or "").split())[-120:]
            found.append(_find("fail", criterion, cmd[:80], f"exit {run.exit_code}: {tail}",
                               "fix the code or the test until the command exits 0"))
    return found or [_ok(criterion)]


def _reuse(ctx: Any, criterion: str) -> CheckFinding:
    """ts-code-reuse, from the gate's own command runs: every verification command is asked for with reuse, so
    the engine takes a result recorded for the same tree instead of starting it again (CHK-B13). The finding
    says how many were reused; a command asked for twice in one gate run with no reuse is the failure."""
    if ctx.reuse_store is None:
        return _find("n_a", criterion, message="no store of earlier command runs (the gate runs outside a run)")
    runs = [r for r in ctx.runs if not r.not_started]
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
    ts-code-commit.

    The marks come first: a plan with a row not marked completed goes back to the code step at once, with no
    command run. Marks are claims, so a marked plan is then verified as before, and each marked row's file must
    be among the paths the run changed."""
    plan, path = _plan(ctx)
    if plan is None:
        return checks.result([_find("fail", "ts-code-rows", path, "the plan cannot be read")])
    report, report_path = _read(ctx, "code_report")
    quick = _quick(ctx) is not None
    found: list[CheckFinding] = []
    if report is None:
        found.append(_find("fail", "ts-code-rows", report_path, "the code report cannot be read",
                           "write the report and name its path"))
    else:
        wanted = fmt.QUICK_REPORT_HEADINGS if quick else fmt.REPORT_HEADINGS
        found += [_find("fail", "ts-code-rows", report_path, f"section `## {h}` is missing or out of order",
                        f"add `## {h}`") for h in fmt.headings_missing(report, wanted)]
    if not plan.rows:
        found.append(_find("fail", "ts-code-rows", path, "the plan has no task row"))
    elif quick:  # no plan to mark: the report's rows, one per acceptance criterion
        status = fmt.parse_report(report or "")
        found += [_find("fail", "ts-code-rows", report_path, f"row `{r.id}` is not marked `done` in the report",
                        "finish the row, or say which earlier output makes it impossible")
                  for r in plan.rows if status.get(r.id) != "done"][:10]
    else:
        found += _marks(plan, "ts-code-rows", path, done=True)
    if any(f.status == "fail" for f in found):  # the cheap return: nothing is run on an unfinished plan
        return _result(ctx, found + [_committed(ctx, "ts-code-commit")], plan)
    found.append(_ok("ts-code-rows", report_path if quick else path))
    if quick or not ctx.git.base:
        found.append(_find("n_a", "ts-code-changed", message="the quick lane has no plan to mark" if quick else
                           "no base commit to compare with"))
    else:
        changed = set(ctx.git.changed_paths)
        found += [_find("fail", "ts-code-changed", r.file, f"row `{r.id}` is marked completed but its file did not "
                        "change in the run", "make the row's change, or clear its mark and say why")
                  for r in plan.rows if r.file and r.file not in changed][:10] or [_ok("ts-code-changed", path)]
    if _value(ctx, "tests_passed") == "no":
        found.append(_find("fail", "ts-code-verify", "tests_passed", "the step itself reports failing tests",
                           "make the plan's verification pass"))
    else:
        found += _verify(ctx, plan, "ts-code-verify")
    found.append(_reuse(ctx, "ts-code-reuse"))
    proof, links = _proof(ctx, plan, "ts-code-proof")
    found += proof + _lane(ctx, "ts-code-lane") + _prompt_says("ts-code-once")
    found.append(_committed(ctx, "ts-code-commit"))
    return _result(ctx, found, plan, links)


# ---------------------------------------------------------------------------------------------
# the outcome gate


def _docs_only(ctx: Any) -> bool:
    return _value(ctx, "route") == "discovery-only"


def _at_base(ctx: Any, path: str) -> str | None:
    """The file as it was at the run's base commit; None with no base, or when the run created the file."""
    base = ctx.git.base
    if not base:
        return None
    run = ctx.run(f"git show {base}:{path}")
    if run.not_started or run.exit_code != 0:
        return None
    try:
        return Path(run.output_path).read_text(encoding="utf-8", errors="replace")
    except OSError:
        return None


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
    """ts-committed, ts-spec-form, ts-spec-cap, ts-spec-links, ts-traced, ts-verify, ts-collateral."""
    found = [_committed(ctx, "ts-committed")]
    found += _spec_form(ctx, "ts-spec-form", "ts-spec-cap")
    specs, _ = _edited_specs(ctx)
    # Only the edited specs: a task note or a plan names ids the task retired on purpose, and is history.
    found += _links(ctx, "ts-spec-links", specs) if specs else [
        _find("n_a", "ts-spec-links", message="the run edited no spec")]
    if _docs_only(ctx):
        found += [_find("n_a", c, message="the run delivers documents only") for c in ("ts-traced", "ts-verify")]
    else:
        found += _traced(ctx, specs, _walk(ctx))
        plan, path = _plan(ctx)
        found += _verify(ctx, plan, "ts-verify") if plan is not None else [
            _find("fail", "ts-verify", path, "the plan cannot be read")]
    found += _collateral(ctx, specs)
    return _result(ctx, found, _plan(ctx)[0])
