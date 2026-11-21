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
    paths = [p for p in ctx.git.changed_paths if p.endswith(".md") and not (set(Path(p).parts) & SKIP_DIRS)]
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


def _result(ctx: Any, found: list[CheckFinding], plan: fmt.Plan | None = None) -> Any:
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
    return checks.result(found, evidence="\n".join(lines))


def _links(ctx: Any, criterion: str) -> list[CheckFinding]:
    """Every id a changed document mentions has exactly one definition among the repository's specs."""
    docs = [p for p in _changed_docs(ctx) if _read_path(ctx, p) is not None]
    if not docs:
        return [_find("n_a", criterion, message="the run changed no document")]
    index = _spec_index(ctx, _walk(ctx))
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
    found.append(_committed(ctx, "ts-tri-commit"))
    return checks.result(found)


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
    """ts-dis-form, ts-dis-names, ts-dis-links, ts-dis-commit."""
    text, path = _read(ctx, "handoff")
    if text is None:
        return checks.result([_find("fail", "ts-dis-form", path, "the hand-off cannot be read",
                                    "write the hand-off and name its path")])
    found = [_find("fail", "ts-dis-form", path, f"hand-off section `## {h}` is missing or out of order",
                   f"add `## {h}`") for h in fmt.headings_missing(text, fmt.HANDOFF_HEADINGS)]
    found += _spec_form(ctx, "ts-dis-form")
    found += _names(ctx, "ts-dis-names")
    found += _links(ctx, "ts-dis-links")
    found.append(_committed(ctx, "ts-dis-commit"))
    return _result(ctx, found)


# ---------------------------------------------------------------------------------------------
# plan and expand


def _rows(ctx: Any, plan: fmt.Plan, criterion: str, rows_criterion: str | None = None) -> list[CheckFinding]:
    empty, bad = fmt.row_problems(plan)
    found = [_find("fail", rows_criterion or criterion, f"phase {p}", "the phase has no task row",
                   "add a table `| Row | Kind | File | Proves | Change |`") for p in empty]
    found += [_find("fail", criterion, "2. Phases", b, "put the test row first and name its criterion") for b in bad[:8]]
    return found


def _commands(ctx: Any, plan: fmt.Plan, criterion: str) -> list[CheckFinding]:
    found = []
    if not plan.commands:
        found.append(_find("fail", criterion, "3. Verification", "the plan lists no verification command",
                           "list each command as a bullet in a code span"))
    for cmd in plan.commands:
        reason = "only the last stage pushes or opens a pull request" if cmd.startswith(FINAL_ONLY) else getattr(
            ctx.resolve(cmd), "reason", None)
        if reason:
            found.append(_find("fail", criterion, "3. Verification", f"`{cmd[:80]}` is not allowed: {reason}",
                               "use a plain command the workflow allows, with no pipe and no `&&` chain"))
    return found


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
    """ts-plan-form, ts-plan-trace, ts-plan-size, ts-plan-commit."""
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
    if not any(f.status == "fail" for f in found):
        found.append(_ok("ts-plan-form", path))

    note_text, note_path = _read(ctx, "triage_note")
    if note_text is None:
        found.append(_find("fail", "ts-plan-trace", note_path, "the triage note cannot be read"))
    else:
        lost = [n for n in fmt.parse_triage(note_text).criteria if n not in plan.requirement_criteria]
        found += [_find("fail", "ts-plan-trace", path, f"acceptance criterion {n} is named by no requirement",
                        f"add a requirement row whose Criteria cell holds `AC {n}`") for n in lost] or [
            _ok("ts-plan-trace", path)]

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
    found.append(_committed(ctx, "ts-plan-commit"))
    return _result(ctx, found, plan)


def expand_check(ctx: Any) -> Any:
    """ts-exp-rows, ts-exp-tests, ts-exp-commands, ts-exp-commit."""
    text, path = _read(ctx, "phases")
    if text is None:
        return checks.result([_find("fail", "ts-exp-rows", path, "the expanded plan cannot be read",
                                    "write the task rows into the plan and name its path")])
    plan = fmt.parse_plan(text)
    empty, bad = fmt.row_problems(plan)
    found: list[CheckFinding] = []
    if not plan.phases:
        empty = ["(none)"]
    found += [_find("fail", "ts-exp-rows", f"{path}: {p}", "the phase has no task row",
                    "add a table `| Row | Kind | File | Proves | Change |`") for p in empty] or [_ok("ts-exp-rows", path)]
    found += [_find("fail", "ts-exp-tests", path, b, "put the test row first and name its criterion")
              for b in bad[:8]] or [_ok("ts-exp-tests", path)]
    found += _commands(ctx, plan, "ts-exp-commands") or [_ok("ts-exp-commands", path)]
    found.append(_committed(ctx, "ts-exp-commit"))
    return checks.result(found)


# ---------------------------------------------------------------------------------------------
# code


def _plan(ctx: Any) -> tuple[fmt.Plan | None, str]:
    """The plan the code step built from: the expanded one when expand ran."""
    for key in ("phases", "plan"):
        text, path = _read(ctx, key)
        if text is not None:
            return fmt.parse_plan(text), path
    return None, "plan"


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


def code_check(ctx: Any) -> Any:
    """ts-code-rows, ts-code-verify, ts-code-commit."""
    plan, path = _plan(ctx)
    if plan is None:
        return checks.result([_find("fail", "ts-code-rows", path, "the plan cannot be read")])
    report, report_path = _read(ctx, "code_report")
    status = fmt.parse_report(report or "")
    found: list[CheckFinding] = []
    if report is None:
        found.append(_find("fail", "ts-code-rows", report_path, "the code report cannot be read",
                           "write the report and name its path"))
    else:
        found += [_find("fail", "ts-code-rows", report_path, f"section `## {h}` is missing or out of order",
                        f"add `## {h}`") for h in fmt.headings_missing(report, fmt.REPORT_HEADINGS)]
        if not plan.rows:
            found.append(_find("fail", "ts-code-rows", path, "the plan has no task row"))
        open_rows = [r.id for r in plan.rows if status.get(r.id) != "done"]
        found += [_find("fail", "ts-code-rows", report_path, f"row `{r}` is not marked `done` in the report",
                        "finish the row, or say which earlier output makes it impossible") for r in open_rows[:10]]
    if not any(f.status == "fail" for f in found):
        found.append(_ok("ts-code-rows", report_path))
    if _value(ctx, "tests_passed") == "no":
        found.append(_find("fail", "ts-code-verify", "tests_passed", "the step itself reports failing tests",
                           "make the plan's verification pass"))
    else:
        found += _verify(ctx, plan, "ts-code-verify")
    found.append(_committed(ctx, "ts-code-commit"))
    return _result(ctx, found, plan)


# ---------------------------------------------------------------------------------------------
# the outcome gate


def _docs_only(ctx: Any) -> bool:
    return _value(ctx, "route") == "discovery-only"


def _traced(ctx: Any, specs: list[str], files: list[str]) -> list[CheckFinding]:
    wanted: dict[str, str] = {}
    for path in specs:
        spec = fmt.parse_spec(_read_path(ctx, path) or "")
        wanted.update({cid: path for cid in spec.criteria})
    if not wanted:
        return [_find("n_a", "ts-traced", message="no edited spec defines an acceptance criterion")]
    tests = [f for f in files if (set(Path(f).parts[:-1]) & TEST_DIRS or TEST_FILE.match(Path(f).name))
             and not f.endswith(".md")]
    seen: set[str] = set()
    for f in tests:
        seen |= fmt.linked_ids(_read_path(ctx, f) or "") & set(wanted)
        if len(seen) == len(wanted):
            break
    return [_find("fail", "ts-traced", wanted[c], f"{c} is named by no test",
                  f"name {c} in the test that proves it") for c in sorted(set(wanted) - seen)[:12]] or [_ok("ts-traced")]


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
    found += _links(ctx, "ts-spec-links")
    specs, _ = _edited_specs(ctx)
    if _docs_only(ctx):
        found += [_find("n_a", c, message="the run delivers documents only") for c in ("ts-traced", "ts-verify")]
    else:
        found += _traced(ctx, specs, _walk(ctx))
        plan, path = _plan(ctx)
        found += _verify(ctx, plan, "ts-verify") if plan is not None else [
            _find("fail", "ts-verify", path, "the plan cannot be read")]
    found += _collateral(ctx, specs)
    return _result(ctx, found, _plan(ctx)[0])
