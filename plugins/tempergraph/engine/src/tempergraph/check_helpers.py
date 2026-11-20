"""The engine's check helpers, `tempergraph.api.checks` (SCF §2.4): the primitives a scaffolded check uses for
a `check` criterion. Each returns one `CheckFinding` naming the criterion id; `result` combines them. Pure
over the workspace (CHK: no write, no model)."""

from __future__ import annotations

import re
from collections.abc import Iterable
from typing import Any

from tempergraph.contracts import CheckFinding, CheckResult

PRIMITIVES = ("file_present", "headings_in_order", "pattern_present", "pattern_absent", "value_in_choices",
              "git_clean", "git_pushed")


def artifact_path(ctx: Any, key: str) -> str | None:
    """The path a step recorded for artifact `key`, from any unit (latest unit in the mapping wins)."""
    found = None
    for arts in (ctx.artifacts or {}).values():
        if isinstance(arts, dict) and arts.get(key):
            found = str(arts[key])
    return found


def _text(ctx: Any, key: str) -> str | None:
    path = artifact_path(ctx, key)
    if path is None:
        return None
    try:
        return str(ctx.read_text(path))
    except (OSError, PermissionError):
        return None


def _f(ok: bool, criterion: str, place: str, message: str, fix: str = "") -> CheckFinding:
    return CheckFinding(status="pass" if ok else "fail", criterion=criterion, place=place,
                        message=message if not ok else "", fix=fix if not ok else "")


def file_present(ctx: Any, key: str, criterion: str) -> CheckFinding:
    path = artifact_path(ctx, key)
    ok = path is not None and (ctx.workdir / path).is_file()
    return _f(ok, criterion, path or key, f"artifact {key!r} is not a file in the workspace", f"write {key}")


def headings_in_order(ctx: Any, key: str, headings: Iterable[str], criterion: str) -> CheckFinding:
    """Every heading present, in this order (`#` level ignored, case and spacing normalised)."""
    want = [" ".join(h.lower().split()) for h in headings]
    text = _text(ctx, key)
    if text is None:
        return _f(False, criterion, key, f"artifact {key!r} cannot be read")
    found = [" ".join(m.group(1).lower().split()) for m in re.finditer(r"^\s*#{1,6}\s+(.+?)\s*#*\s*$", text, re.M)]
    pos = 0
    for h in want:
        try:
            pos = found.index(h, pos) + 1
        except ValueError:
            return _f(False, criterion, key, f"heading {h!r} is missing or out of order", f"add the {h!r} heading")
    return _f(True, criterion, key, "")


def pattern_present(ctx: Any, key: str, pattern: str, criterion: str) -> CheckFinding:
    text = _text(ctx, key)
    ok = text is not None and re.search(pattern, text, re.M) is not None
    return _f(ok, criterion, key, f"{key} does not match {pattern!r}")


def pattern_absent(ctx: Any, key: str, pattern: str, criterion: str) -> CheckFinding:
    text = _text(ctx, key)
    m = re.search(pattern, text, re.M) if text is not None else None
    ok = text is not None and m is None
    line = text.count("\n", 0, m.start()) + 1 if (text is not None and m is not None) else 0
    return _f(ok, criterion, f"{key}:{line}" if line else key, f"{key} matches {pattern!r}")


def value_in_choices(ctx: Any, key: str, choices: Iterable[str], criterion: str) -> CheckFinding:
    value = None
    for vals in (ctx.values or {}).values():
        if isinstance(vals, dict) and key in vals:
            value = vals[key]
    ok = value is not None and str(value) in set(choices)
    return _f(ok, criterion, key, f"value {key}={value!r} is not one of {sorted(choices)}")


def git_clean(ctx: Any, criterion: str) -> CheckFinding:
    return _f(bool(ctx.git.clean), criterion, "git", "the workspace has uncommitted changes", "commit or remove them")


def git_pushed(ctx: Any, criterion: str) -> CheckFinding:
    return _f(bool(ctx.git.pushed), criterion, "git", "the branch is not pushed", "push the branch")


def result(findings: Iterable[CheckFinding], evidence: str = "") -> CheckResult:
    fs = list(findings)
    bad = [f for f in fs if f.status == "fail"]
    return CheckResult(result="FAIL" if bad else "PASS", evidence=evidence or (
        "; ".join(f"{f.criterion}: {f.message}" for f in bad) or f"{len(fs)} checked"), findings=fs)
