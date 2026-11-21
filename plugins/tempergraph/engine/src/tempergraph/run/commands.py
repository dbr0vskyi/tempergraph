"""Command resolution and the workflow command runner (CHK §2.2, §2.3; SEC §2.2 "Workflow command runner").

A command reaches a process only as list argv resolved against the workflow's allow-list, with standard
input closed, output to a file, credentials removed from the environment and the process tree ended at
its limit.
"""

from __future__ import annotations

import contextlib
import json
import os
import re
import signal
import subprocess
import time
from collections.abc import Mapping, Sequence
from dataclasses import dataclass, field
from pathlib import Path

from tempergraph.security.launch import has_shell_metacharacter
from tempergraph.security.scrub import head_tail, scrub

CREDENTIAL_VARS = re.compile(r"(TOKEN|SECRET|PASSWORD|API_KEY|CREDENTIAL|_AUTH)", re.I)
TAIL_LINES = 40
TAIL_CHARS = 8000
_CD_RE = re.compile(r"^cd\s+([A-Za-z0-9_./-]+)\s*&&\s*(.+)$")


REPOSITORY = "@repository"  # in an allow-list or a step's commands: the commands the repository declares
REPO_FILE = "tempergraph.commands.json"
REPO_COMMANDS_MAX = 50


def _plain(text: str) -> bool:
    words = text.split()
    return bool(words) and not has_shell_metacharacter(text) and not any(
        w.startswith("/") or ".." in w.split("/") for w in words)


def repository_commands(workdir: Path) -> list[str]:
    """CHK §2.2: the command prefixes a repository declares in `tempergraph.commands.json` at its root, as a
    list or as a map of names to commands. An entry that is not plain words is dropped, never run."""
    try:
        doc = json.loads((workdir / REPO_FILE).read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return []
    got = doc.get("commands") if isinstance(doc, dict) and doc.get("schema_version") == 1 else None
    items = list(got.values()) if isinstance(got, dict) else got if isinstance(got, list) else []
    out = [" ".join(c.split()) for c in items if isinstance(c, str) and _plain(c)]
    return list(dict.fromkeys(out))[:REPO_COMMANDS_MAX]


def expand(commands: Sequence[str], workdir: Path) -> tuple[str, ...]:
    """A step's commands with `@repository` replaced by what the repository declares."""
    out: list[str] = []
    for c in commands:
        out.extend(repository_commands(workdir) if c == REPOSITORY else [c])
    return tuple(dict.fromkeys(out))


@dataclass(frozen=True, kw_only=True)
class ResolvedCommand:
    argv: tuple[str, ...]
    prefix: str
    cwd: str | None = None
    documented: bool = False
    resolver: str = "allow_list"


@dataclass(frozen=True, kw_only=True)
class CommandRefusal:
    reason: str


@dataclass(kw_only=True)
class CommandRun:
    argv: tuple[str, ...]
    program_path: str = ""
    exit_code: int | None = None
    finished: bool = False
    timed_out: bool = False
    not_started: bool = False
    reused: bool = False
    duration_s: float = 0.0
    output_path: str = ""
    tail: str = ""
    extra: dict[str, object] = field(default_factory=dict)

    def to_json(self) -> dict[str, object]:
        return {"argv": list(self.argv), "program_path": self.program_path, "exit_code": self.exit_code,
                "finished": self.finished, "timed_out": self.timed_out, "not_started": self.not_started,
                "reused": self.reused, "duration_s": round(self.duration_s, 3), "output_path": self.output_path,
                "tail": self.tail}


def resolve_command(allow: Sequence[str], text: str, workdir: Path) -> ResolvedCommand | CommandRefusal:
    """CHK §2.2 without a custom resolver: a declared prefix with plain-word arguments."""
    text = text.strip()
    cwd = None
    m = _CD_RE.match(text)
    if m:
        folder, text = m.group(1), m.group(2).strip()
        target = (workdir / folder).resolve()
        if folder.startswith("/") or ".." in Path(folder).parts or not target.is_relative_to(workdir.resolve()):
            return CommandRefusal(reason="change of directory outside the repository")
        cwd = folder
    if has_shell_metacharacter(text):
        return CommandRefusal(reason="shell metacharacter")
    words = text.split()
    if not words:
        return CommandRefusal(reason="empty")
    if any(w.startswith("/") or ".." in w.split("/") for w in words):
        return CommandRefusal(reason="absolute or parent path")
    for prefix in sorted((a for a in allow if a != REPOSITORY), key=len, reverse=True):
        if text == prefix or text.startswith(prefix + " "):
            return ResolvedCommand(argv=tuple(words), prefix=prefix, cwd=cwd)
    if REPOSITORY in allow:  # documented by the repository itself (CHK §2.2)
        for prefix in sorted(repository_commands(workdir), key=len, reverse=True):
            if text == prefix or text.startswith(prefix + " "):
                return ResolvedCommand(argv=tuple(words), prefix=prefix, cwd=cwd, documented=True,
                                       resolver="repository")
    return CommandRefusal(reason="not declared")


def command_env(base: dict[str, str] | None = None) -> dict[str, str]:
    env = {k: v for k, v in (os.environ if base is None else base).items() if not CREDENTIAL_VARS.search(k)}
    env["GIT_TERMINAL_PROMPT"] = "0"
    env["GH_PROMPT_DISABLED"] = "1"
    return env


def _placeholders(text: str, workdir: Path, main: Path | None) -> str:
    for path, word in ((workdir, "<workdir>"), (main, "<main>"), (Path.home(), "<home>")):
        if path is not None:
            text = text.replace(str(path), word)
    return text


def run_command(cmd: ResolvedCommand, workdir: Path, out_path: Path, timeout_s: float, *,
                main: Path | None = None, finished_codes: Sequence[int] | None = None,
                env_extra: Mapping[str, str] | None = None) -> CommandRun:
    out_path.parent.mkdir(parents=True, exist_ok=True, mode=0o700)
    cwd = workdir / cmd.cwd if cmd.cwd else workdir
    t0 = time.monotonic()
    run = CommandRun(argv=tuple(scrub(a) for a in cmd.argv), output_path=str(out_path))
    with open(out_path, "wb") as fh:
        try:
            proc = subprocess.Popen(  # noqa: S603 - resolved list argv (CHK §2.3)
                list(cmd.argv), cwd=cwd, stdin=subprocess.DEVNULL, stdout=fh, stderr=subprocess.STDOUT,
                env={**command_env(), **(env_extra or {})}, start_new_session=(os.name == "posix"))
        except OSError as exc:
            run.extra["error"] = type(exc).__name__
            run.duration_s = time.monotonic() - t0
            return run
        try:
            proc.wait(timeout=max(0.1, timeout_s))
        except subprocess.TimeoutExpired:
            run.timed_out = True
            if os.name == "posix":
                with contextlib.suppress(ProcessLookupError, PermissionError):
                    os.killpg(proc.pid, signal.SIGKILL)
            else:
                proc.kill()
            proc.wait()
    os.chmod(out_path, 0o600)
    run.duration_s = time.monotonic() - t0
    run.exit_code = proc.returncode
    normal = proc.returncode is not None and proc.returncode >= 0 and not run.timed_out
    run.finished = normal and (finished_codes is None or proc.returncode in finished_codes)
    text = out_path.read_text(encoding="utf-8", errors="replace")
    tail = "\n".join(text.splitlines()[-TAIL_LINES:])
    run.tail = head_tail(_placeholders(scrub(tail), workdir, main), TAIL_CHARS)
    return run
