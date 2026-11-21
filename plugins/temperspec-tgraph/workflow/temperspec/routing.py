"""The routes, the two engine-run scripts around a step, and the last stage. Plain functions of their
context: no model, no request text."""

from __future__ import annotations

import os
import re
import shutil
import subprocess
import tempfile
from pathlib import Path
from typing import Any

from tempergraph.api import FinalizerResult

from . import specfmt, summary

PACKAGE = Path(__file__).resolve().parents[2]
RULES = "rules"
REPO_RULES = Path(".claude") / "rules" / "temperspec"
COMMIT_TYPE = {"code": "feat"}
CONTEXT_FILES = ("CLAUDE.md", "AGENTS.md")
SKIP_DIRS = {".git", ".tempergraph", ".claude", "node_modules", ".venv", "venv", "evals", "fixtures", "baseline"}
CONTEXT_BLOCK = f"""{specfmt.CONTEXT_START}
## temperspec

This repository is developed with temperspec: a change goes from a task with acceptance criteria through
behaviour specs and a plan to tested code.

- Specs are in `docs/specs/` (`*.spec.md`), starting at the overview spec. Decision records are in `docs/adr/`,
  research notes in `docs/research/`, plans in `docs/plans/`, task notes in `docs/tasks/`.
- How each document is written: the rule files in `.claude/rules/temperspec/`; fill-in templates generated from
  them are in `docs/templates/`.
- When two sources disagree: the task's acceptance criteria, then specs and decision records, then the plan,
  then the code. A code change that makes a spec false changes the spec in the same change.
- A test that proves an acceptance criterion of a spec carries the criterion's id.
- Start a run with `tempergraph run temperspec "<the task and its acceptance criteria>"`.
{specfmt.CONTEXT_END}
"""
SAFE_REF = re.compile(r"^[A-Za-z0-9][A-Za-z0-9._/-]{0,200}$")
URL = re.compile(r"https://\S+/pull/\d+")
PLAIN_PATH = re.compile(r"^[A-Za-z0-9._/:\\-]+$")


# -- routes ---------------------------------------------------------------------------------------


def route_setup(view: Any) -> str:
    """A repository with no overview spec is set up first; every other run starts at triage."""
    return "setup" if "setup_needed" in view.artifact_keys else "triage"


def route_triage(view: Any) -> str:
    """A quick task goes straight to code; no gap goes to the plan; any gap goes to discovery."""
    route = view.values.get("route")
    return {"quick": "code", "plan": "plan"}.get(route, "discovery")


def route_discovery(view: Any) -> str:
    """A docs-only run ends after discovery; every other run is planned."""
    return "finalizer" if view.values.get("route") == "discovery-only" else "plan"


def route_plan(view: Any) -> str:
    """A complex plan gets its task rows from `expand`; a simple plan already has them."""
    return "expand" if view.values.get("complexity") == "complex" else "code"


# -- scripts the engine runs around a step --------------------------------------------------------


def _git(workdir: Path, *args: str) -> subprocess.CompletedProcess[str]:
    return subprocess.run(["git", *args], cwd=workdir, capture_output=True, text=True, timeout=120,  # noqa: S603, S607
                          stdin=subprocess.DEVNULL)


def install_rules(ctx: Any) -> dict[str, str]:
    """Put the rule files, and the templates generated from their examples, into the repository unless it, or
    the whole machine, has the rules."""
    target = Path(ctx.workdir) / REPO_RULES
    if target.is_dir() or (Path.home() / REPO_RULES).is_dir():
        return {}
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
    for _, dirs, files in os.walk(workdir):
        dirs[:] = [d for d in dirs if d not in SKIP_DIRS]
        if any(name.endswith("overview.spec.md") for name in files):
            return True
    return False


def write_context(workdir: Path) -> str:
    """Keep the temperspec block in the project-context file: added once, replaced in place afterwards."""
    target = next((workdir / n for n in CONTEXT_FILES if (workdir / n).is_file()), workdir / CONTEXT_FILES[0])
    text = target.read_text(encoding="utf-8") if target.is_file() else ""
    start, end = text.find(specfmt.CONTEXT_START), text.find(specfmt.CONTEXT_END)
    if start >= 0 and end > start:
        new = text[:start] + CONTEXT_BLOCK.rstrip("\n") + text[end + len(specfmt.CONTEXT_END):]
    else:
        new = (text.rstrip("\n") + "\n\n" if text.strip() else "") + CONTEXT_BLOCK
    if new != text:
        target.write_text(new, encoding="utf-8")
    return target.name


def prepare(ctx: Any) -> dict[str, str]:
    """The first unit, with no session: install the rule files when missing, keep the temperspec block in the
    project-context file, commit both, and say whether the repository still needs its overview and specs."""
    workdir = Path(ctx.workdir)
    install_rules(ctx)
    write_context(workdir)
    commit_step(ctx)
    return {"setup_ready": "yes"} if has_overview(workdir) else {"setup_needed": "yes"}


def commit_step(ctx: Any) -> dict[str, str]:
    """After each step: commit everything the step left, on the run's branch. Nothing is pushed here."""
    workdir = Path(ctx.workdir)
    added = _git(workdir, "add", "-A", "--", ".", ":(exclude).tempergraph")
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
