#!/usr/bin/env python3
"""Add the tempergraph state-root ignore rule to a repository's root `.gitignore` (SHL, project bootstrap).

The only writer of the ignore file. It asks git, not the file's text, whether the state folder is already
ignored; it keeps the file's bytes and line endings; it never overrides a negation the person wrote; it never
stages, commits, untracks or deletes. It prints one JSON line:

  {"status": "added" | "already_ignored" | "negated" | "write_failed" | "not_a_repository",
   "tracked": [...], "untrack": "<command for the person>" | null, "paste": "<block>" | null}

Exit 0 for added and already_ignored, 1 otherwise. No third-party imports; git is called with list argv.
"""

from __future__ import annotations

import json
import subprocess
import sys
from pathlib import Path

STATE = ".tempergraph"
RULE = "/.tempergraph/"
COMMENT = "# tempergraph run state (local only)"


def git(repo: Path, *args: str) -> subprocess.CompletedProcess[str]:
    return subprocess.run(["git", "-C", str(repo), *args], capture_output=True, text=True, stdin=subprocess.DEVNULL,
                          check=False)


def main(argv: list[str]) -> int:
    start = Path(argv[1] if len(argv) > 1 else ".").resolve()
    top = git(start, "rev-parse", "--show-toplevel")
    if top.returncode != 0:
        print(json.dumps({"status": "not_a_repository", "tracked": [], "untrack": None, "paste": None}))
        return 1
    repo = Path(top.stdout.strip())
    tracked = [ln for ln in git(repo, "ls-files", "--", STATE).stdout.splitlines() if ln]
    untrack = f"git rm -r --cached -- {STATE}" if tracked else None
    match = rule(repo)
    if match is None:
        status = add(repo / ".gitignore")
    else:
        status = "negated" if match.startswith("!") else "already_ignored"  # a person's negation stands
    paste = f"{COMMENT}\n{RULE}\n" if status in ("write_failed", "negated") else None
    print(json.dumps({"status": status, "tracked": tracked, "untrack": untrack, "paste": paste}))
    return 0 if status in ("added", "already_ignored") else 1


def rule(repo: Path) -> str | None:
    """The pattern git applies to the state folder from an ignore source outside it, or None.

    Git is asked about the folder itself. Once the folder exists, its own `.gitignore` ("*") can answer instead
    when no outer rule ignores the folder; that answer does not count, because this rule is the repository's
    second guard, so the root file's own lines are read only to spot a negation the person wrote.
    """
    out = git(repo, "check-ignore", "-v", "-n", "--no-index", "--", f"{STATE}/").stdout
    source, _, _ = out.partition("\t")
    parts = source.split(":", 2)
    if len(parts) == 3 and parts[2] and not Path(parts[0]).as_posix().startswith(f"{STATE}/"):
        return parts[2]
    try:
        lines = (repo / ".gitignore").read_text(encoding="utf-8", errors="replace").splitlines()
    except OSError:
        return None
    return next((ln.strip() for ln in reversed(lines) if ln.strip().startswith("!") and STATE in ln), None)


def add(path: Path) -> str:
    try:
        data = path.read_bytes() if path.exists() else b""
        eol = b"\r\n" if b"\r\n" in data else b"\n"
        lead = b"" if not data or data.endswith(b"\n") else eol
        with open(path, "ab") as fh:
            fh.write(lead + COMMENT.encode() + eol + RULE.encode() + eol)
    except OSError:
        return "write_failed"
    return "added"


if __name__ == "__main__":
    sys.exit(main(sys.argv))
