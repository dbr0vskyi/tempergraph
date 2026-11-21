"""The git reader: a sanctioned launch site (SEC §2.2) for `git` with constant arguments.

Refs travel on stdin where git accepts them; callers pass only constants and refs checked by
:func:`is_safe_ref` (SEC-B4).
"""

from __future__ import annotations

import os
import re
import subprocess
from dataclasses import dataclass
from pathlib import Path

_REF_RE = re.compile(r"^(?!.*\.\.)(?!/)(?!.*//)[A-Za-z0-9._/-]{1,200}(?<!\.lock)(?<!/)$")


class GitError(Exception):
    pass


def is_safe_ref(ref: str) -> bool:
    return bool(_REF_RE.match(ref)) and not ref.startswith("-")


def _env() -> dict[str, str]:
    env = dict(os.environ)
    env["GIT_TERMINAL_PROMPT"] = "0"
    env.pop("GIT_DIR", None)
    env.pop("GIT_WORK_TREE", None)
    return env


def git(args: list[str], cwd: Path, *, check: bool = True, stdin: str | None = None) -> str:
    """Run git with list argv, no shell. Raises GitError when ``check`` and git fails."""
    try:
        proc = subprocess.run(
            ["git", *args], cwd=cwd, input=stdin, capture_output=True, text=True, env=_env(), timeout=120
        )
    except (OSError, subprocess.TimeoutExpired) as exc:
        raise GitError(f"git {args[0] if args else ''}: {type(exc).__name__}") from None
    if check and proc.returncode != 0:
        raise GitError(f"git {args[0] if args else ''} exited {proc.returncode}: {proc.stderr.strip()[:300]}")
    return proc.stdout


def git_bytes(args: list[str], cwd: Path) -> bytes:
    """Run git and return its raw output, for a blob that is not text. Raises GitError when git fails."""
    try:
        proc = subprocess.run(["git", *args], cwd=cwd, capture_output=True, env=_env(), timeout=120)
    except (OSError, subprocess.TimeoutExpired) as exc:
        raise GitError(f"git {args[0] if args else ''}: {type(exc).__name__}") from None
    if proc.returncode != 0:
        raise GitError(f"git {args[0] if args else ''} exited {proc.returncode}")
    return proc.stdout


def toplevel(start: Path) -> Path | None:
    try:
        return Path(git(["rev-parse", "--show-toplevel"], start).strip())
    except GitError:
        return None


def main_checkout(start: Path) -> Path | None:
    """The main checkout of the repository that holds ``start``, from git's common directory."""
    try:
        common = git(["rev-parse", "--path-format=absolute", "--git-common-dir"], start).strip()
    except GitError:
        return None
    common_path = Path(common)
    if common_path.name == ".git":
        return common_path.parent
    # A bare common dir or an unusual layout: fall back to the worktree list's first entry.
    try:
        out = git(["worktree", "list", "--porcelain"], start)
    except GitError:
        return None
    for line in out.splitlines():
        if line.startswith("worktree "):
            return Path(line[len("worktree "):])
    return None


@dataclass(frozen=True)
class Fingerprint:
    head: str
    status: str
    manifest: bool = False  # outside git: `status` is the workspace manifest's digest (WSP §2.4)

    @property
    def dirty(self) -> bool | None:
        """Uncommitted changes; None outside git, where the word has no meaning."""
        return None if self.manifest else bool(self.status)


def fingerprint(workdir: Path) -> Fingerprint:
    if toplevel(workdir) is None:  # outside git the guard compares manifests of the files (WSP §2.4)
        from tempergraph.store import manifest

        return Fingerprint("", manifest.status(workdir), manifest=True)
    try:
        head = git(["rev-parse", "HEAD"], workdir, check=False).strip()
        status = git(["status", "--porcelain=v1", "--untracked-files=all"], workdir, check=False)
    except GitError:
        return Fingerprint("", "")
    lines = [ln for ln in status.splitlines() if ".tempergraph/" not in ln]
    return Fingerprint(head, "\n".join(sorted(lines)))


def branch(workdir: Path) -> str:
    try:
        return git(["rev-parse", "--abbrev-ref", "HEAD"], workdir, check=False).strip()
    except GitError:
        return ""


def pushed(workdir: Path, name: str) -> bool:
    """CHK §2.1: the branch exists on any configured remote, by its remote-tracking refs; no network."""
    if not name or not is_safe_ref(name):
        return False
    try:
        refs = git(["for-each-ref", "--format=%(refname)", "refs/remotes"], workdir, check=False)
    except Exception:  # noqa: BLE001 - not a repository, or git is missing: not pushed
        return False
    return any(r.split("/", 3)[-1] == name for r in refs.splitlines() if r.count("/") >= 3)


def changed_paths(workdir: Path, base: str | None = None, limit: int = 500) -> list[str]:
    paths: list[str] = []
    try:
        if base and is_safe_ref(base):
            out = git(["diff", "--name-only", base, "--"], workdir, check=False)
            paths.extend(p for p in out.splitlines() if p)
        status = git(["status", "--porcelain=v1", "--untracked-files=all"], workdir, check=False)
    except GitError:
        return paths[:limit]
    for line in status.splitlines():
        p = line[3:]
        if p and not p.startswith(".tempergraph/") and p not in paths:
            paths.append(p)
    return paths[:limit]
