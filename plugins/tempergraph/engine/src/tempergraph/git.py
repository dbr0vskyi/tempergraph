"""The git reader: a sanctioned launch site (SEC-B7) for `git` with constant arguments.

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


def git(args: list[str], cwd: Path, *, check: bool = True, stdin: str | None = None, timeout_s: float = 120) -> str:
    """Run git with list argv, no shell. Raises GitError when ``check`` and git fails, or on a timeout."""
    try:
        proc = subprocess.run(
            ["git", *args], cwd=cwd, input=stdin, capture_output=True, text=True, env=_env(), timeout=timeout_s
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
    manifest: bool = False  # outside git: `status` is the workspace manifest's digest (WSP-B15 to WSP-B18)

    @property
    def dirty(self) -> bool | None:
        """Uncommitted changes; None outside git, where the word has no meaning."""
        return None if self.manifest else bool(self.status)


def fingerprint(workdir: Path) -> Fingerprint:
    if toplevel(workdir) is None:  # outside git the guard compares manifests of the files (WSP-B15 to WSP-B18)
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
    """CHK-B10: the branch exists on any configured remote, by its remote-tracking refs; no network."""
    if not name or not is_safe_ref(name):
        return False
    try:
        refs = git(["for-each-ref", "--format=%(refname)", "refs/remotes"], workdir, check=False)
    except Exception:  # noqa: BLE001 - not a repository, or git is missing: not pushed
        return False
    return any(r.split("/", 3)[-1] == name for r in refs.splitlines() if r.count("/") >= 3)


def branch_commit(workdir: Path, name: str) -> str:
    """CHK-B22: the commit the branch `name` points to now: the local branch, else `origin`'s remote-tracking branch;
    empty when no ref names it or the name is unsafe. No fetch and no network."""
    if not name or not is_safe_ref(name):
        return ""
    for ref in (f"refs/heads/{name}", f"refs/remotes/origin/{name}"):
        try:
            found = git(["rev-parse", "--verify", "--quiet", f"{ref}^{{commit}}"], workdir, check=False).strip()
        except GitError:
            return ""
        if found:
            return found
    return ""


def head(workdir: Path) -> str:
    """The commit `HEAD` names in `workdir`; empty when there is none."""
    return git(["rev-parse", "--verify", "--quiet", "HEAD"], workdir, check=False).strip()


def _identity(workdir: Path) -> list[str]:
    """The engine's own commit identity, used only where the repository configures none."""
    if git(["config", "user.email"], workdir, check=False).strip():
        return ["-c", "commit.gpgsign=false"]
    return ["-c", "commit.gpgsign=false", "-c", "user.name=tempergraph", "-c", "user.email=tempergraph@localhost.invalid"]


def stage_all_args(workdir: Path) -> list[str]:
    """The `git add` words that stage every change in `workdir` outside the state root. The state root is left out by
    an exclude pathspec only when git does not already ignore it: git 2.39 refuses an exclude pathspec that names an
    ignored path (exit 1, "paths are ignored by one of your .gitignore files") after staging the rest."""
    ignored = git(["check-ignore", ".tempergraph/"], workdir, check=False).strip()
    return ["add", "-A", "--", ".", *([] if ignored else [":(exclude).tempergraph"])]


def commit_all(workdir: Path, message: str) -> str:
    """WSP-B19: commit every uncommitted change in `workdir`, new files included, outside the state root. Returns the
    new commit, or an empty string when there was nothing to commit (no commit is made)."""
    git(stage_all_args(workdir), workdir)
    if not git(["status", "--porcelain=v1", "--untracked-files=no"], workdir).strip():
        return ""
    git([*_identity(workdir), "commit", "--no-verify", "--quiet", "-m", message], workdir)
    return head(workdir)


def merge_no_ff(workdir: Path, ref: str, message: str) -> list[str]:
    """WSP-B11, WSP-B12: merge the branch `ref` into the branch checked out in `workdir` without fast-forward. Returns
    the conflicting paths, empty when the merge went through (a merge in progress is left for the caller to end)."""
    try:
        git([*_identity(workdir), "merge", "--no-ff", "--no-edit", "-m", message, "--end-of-options", ref], workdir)
    except GitError:
        paths = conflicted_paths(workdir)
        if not paths:
            raise
        return paths
    return []


def conflicted_paths(workdir: Path) -> list[str]:
    """The paths a merge in progress left unmerged, sorted."""
    return sorted(p for p in git(["diff", "--name-only", "--diff-filter=U"], workdir, check=False).splitlines() if p)


def merge_abort(workdir: Path) -> None:
    git(["merge", "--abort"], workdir, check=False)


def reset_hard(workdir: Path, commit: str) -> None:
    """Put the branch checked out in `workdir`, its index and its files back at `commit`, a full commit id (`reset`
    takes no `--end-of-options` before its commit, and a hex id cannot be read as an option)."""
    if not re.fullmatch(r"[0-9a-f]{40}|[0-9a-f]{64}", commit):
        raise GitError("git reset: not a full commit id")
    git(["reset", "--hard", "--quiet", commit], workdir)


_COMMIT_ID = re.compile(r"[0-9a-f]{40}|[0-9a-f]{64}")


def is_commit_id(text: str) -> bool:
    """Whether `text` is a full commit id (a hex id cannot be read as an option or a ref name)."""
    return bool(_COMMIT_ID.fullmatch(text))


def prefix(workdir: Path) -> str:
    """The folder of `workdir` inside its repository, `""` at the top, with no trailing slash."""
    return git(["rev-parse", "--show-prefix"], workdir, check=False).strip().rstrip("/")


def base_checkout(workdir: Path, commit: str, dest: Path) -> Path:
    """CHK-B18: a clean checkout of `commit` of the repository that holds `workdir`, in the new folder `dest` outside
    both that repository and its main checkout. It shares the repository's objects and records nothing in it: no
    worktree entry, branch or ref. Returns the folder of `workdir` inside the checkout. Raises GitError when `commit`
    is not a full commit id or cannot be checked out."""
    if not is_commit_id(commit):
        raise GitError("git checkout: not a full commit id")
    top = toplevel(workdir)
    if top is None:
        raise GitError("git clone: not a repository")
    git(["clone", "--shared", "--no-checkout", "--quiet", "--", str(top), str(dest)], dest.parent)
    git(["checkout", "--quiet", "--detach", commit, "--"], dest)
    return dest / prefix(workdir)


def folder_in_commit(workdir: Path, commit: str, folder: str) -> bool:
    """CHK-B19: whether `folder` (relative to `workdir`, as `cd` writes it) is a folder of `commit`."""
    if not is_commit_id(commit):
        return False
    path = "/".join(p for p in (prefix(workdir), folder.strip("/")) if p and p != ".")
    if not path:
        return True
    return git(["cat-file", "-t", f"{commit}:{path}"], workdir, check=False).strip() == "tree"


def changed_between(workdir: Path, base: str, end: str, limit: int = 500) -> list[str]:
    """OUT-B28: the paths that differ between the commits `base` and `end`, sorted, never one under `.tempergraph/`,
    at most `limit`. Empty when either is not a full commit id or git fails."""
    if not is_commit_id(base) or not is_commit_id(end):
        return []
    try:
        out = git(["diff", "--name-only", base, end, "--"], workdir, check=False)
    except GitError:
        return []
    return sorted(p for p in out.splitlines() if p and not p.startswith(".tempergraph/"))[:limit]


def base_problem(workdir: Path, base: str) -> str | None:
    """SRV-B37: why no count can be made from `base`: `outside_repository`, `no_entry_commit` or `commit_unknown`, in
    that order of precedence; None when `base` is a commit of the repository that holds `workdir`."""
    if git(["rev-parse", "--is-inside-work-tree"], workdir, check=False).strip() != "true":
        return "outside_repository"
    if not base:
        return "no_entry_commit"
    if not is_safe_ref(base) or git(["cat-file", "-t", base], workdir, check=False).strip() != "commit":
        return "commit_unknown"
    return None


def judge_changed_paths(workdir: Path, base: str, limit: int) -> list[str]:
    """SRV-B39, SRV-B40: the paths a judge's count covers: those that differ from `base` and exist in the workspace,
    plus the modified and untracked ones, named as the workspace holds them (git's quoting undone), never one under
    `.tempergraph/` and never a deleted one; at most `limit`. `changed_paths` is not this list."""
    top = prefix(workdir)
    lead = f"{top}/" if top else ""
    found: list[str] = []
    try:
        diff = git(["diff", "--name-only", "-z", "--diff-filter=d", base, "--"], workdir, check=False)
        status = git(["status", "--porcelain=v1", "-z", "--untracked-files=all"], workdir, check=False)
    except GitError:
        return found
    names = [p for p in diff.split("\0") if p]
    parts = status.split("\0")
    i = 0
    while i < len(parts):
        entry = parts[i]
        i += 1
        if len(entry) < 4:
            continue
        code, name = entry[:2], entry[3:]
        if "R" in code or "C" in code:
            i += 1  # the origin of a rename or a copy follows as its own field
        if "D" not in code.replace(" ", ""):
            names.append(name)
    for p in names:
        if not p.startswith(lead):
            continue
        rel = p[len(lead):]
        if rel.startswith(".tempergraph/") or rel in found or not (workdir / rel).exists():
            continue
        found.append(rel)
    return found[:limit]


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
