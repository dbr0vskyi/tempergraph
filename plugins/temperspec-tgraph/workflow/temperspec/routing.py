"""The routes, the two engine-run scripts around a step, and the last stage. Plain functions of their
context: no model, no request text."""

from __future__ import annotations

import re
import shutil
import subprocess
from pathlib import Path
from typing import Any

from tempergraph.api import FinalizerResult

PACKAGE = Path(__file__).resolve().parents[2]
RULES = "rules"
REPO_RULES = Path(".claude") / "rules" / "temperspec"
COMMIT_TYPE = {"code": "feat"}
SAFE_REF = re.compile(r"^[A-Za-z0-9][A-Za-z0-9._/-]{0,200}$")
URL = re.compile(r"https://\S+/pull/\d+")


# -- routes ---------------------------------------------------------------------------------------


def route_triage(view: Any) -> str:
    """No gap goes straight to the plan; any gap goes to discovery."""
    return "plan" if view.values.get("route") == "plan" else "discovery"


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
    """Before triage: put the rule files into the repository unless it, or the whole machine, has them."""
    target = Path(ctx.workdir) / REPO_RULES
    if target.is_dir() or (Path.home() / REPO_RULES).is_dir():
        return {}
    target.mkdir(parents=True)
    for src in sorted((PACKAGE / RULES).glob("*.rule.md")):
        shutil.copyfile(src, target / src.name)
    return {}


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


def finalize(ctx: Any) -> FinalizerResult:
    """Push the run's branch and open a draft pull request, or reuse the open one. A repository with no
    remote, or a host with no `gh`, ends with the branch and the steps a person takes by hand."""
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
    if found:
        return FinalizerResult(outcome="reused", reason=f"{branch} pushed to its open pull request",
                               url=found.group(0))
    base = f" --base {ctx.base}" if SAFE_REF.match(ctx.base or "") else ""
    made = ctx.run(f"gh pr create --draft --fill{base} --head {branch}")
    found = URL.search(str(made.tail)) if _passed(made) else None
    if found:
        return FinalizerResult(outcome="opened", reason=f"draft pull request opened for {branch}", url=found.group(0))
    return FinalizerResult(outcome="pushed", reason=f"{branch} is pushed; no pull request could be opened",
                           manual_steps=[f"open a draft pull request for {branch}"])
