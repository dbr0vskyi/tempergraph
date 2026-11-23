"""The check context and running a gate's check (CHK-B10, CHK-B14; OVR-B7).

`run_check` is the call itself; the engine makes it inside the check worker (`run.check_worker`, CHK-B16),
and the deadline is also enforced on every command the check runs.
"""

from __future__ import annotations

import hashlib
import json
import os
import re
import shutil
import tempfile
import time
from collections.abc import Mapping, Sequence
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

from tempergraph import git as gitmod
from tempergraph.contracts import CheckFinding, CheckResult, GateSpec
from tempergraph.run.commands import CommandRefusal, CommandRun, ResolvedCommand, resolve_command, run_command
from tempergraph.security.scrub import clip, scrub

ORDER = {"PASS": 0, "MAYBE": 1, "FAIL": 2}
FINDING_TO_RESULT = {"pass": "PASS", "n_a": "PASS", "maybe": "MAYBE", "fail": "FAIL"}
FACT_KEY = re.compile(r"^[a-z0-9][a-z0-9_-]{0,39}$")
MAX_FACTS = 20


@dataclass(frozen=True, kw_only=True)
class GitFacts:
    branch: str = ""
    base: str = ""
    head: str = ""
    base_head: str = ""
    clean: bool = True
    pushed: bool = False
    changed_paths: tuple[str, ...] = ()
    commits_since_base: tuple[str, ...] = ()


def git_facts(workdir: Path, base: str = "") -> GitFacts | None:
    """The workspace's git facts; None outside a git repository (WSP-B15 to WSP-B18)."""
    if gitmod.toplevel(workdir) is None:
        return None
    fp = gitmod.fingerprint(workdir)
    name = gitmod.branch(workdir)
    return GitFacts(branch=name, base=base, head=fp.head, clean=not fp.status, pushed=gitmod.pushed(workdir, name),
                    changed_paths=tuple(gitmod.changed_paths(workdir, base or None)))


def changed_paths(workdir: Path, facts: GitFacts | None, baseline: Path | None) -> tuple[str, ...]:
    """What changed in the workspace: git's answer, or outside git the manifest against the thread's first one."""
    if facts is not None:
        return tuple(facts.changed_paths)
    import json

    from tempergraph.store import manifest

    try:
        files = json.loads(baseline.read_text(encoding="utf-8")).get("files") if baseline is not None else None
    except (OSError, ValueError, AttributeError):
        files = None
    return tuple(manifest.changed(workdir, files)) if isinstance(files, dict) else ()


@dataclass(kw_only=True)
class CheckContext:
    unit: str
    workdir: Path
    request: Mapping[str, Any]
    item: str | None = None
    visit: int = 1
    attempt: int = 1
    preview: bool = False
    main_checkout: Path | None = None
    artifacts: Mapping[str, Any] = field(default_factory=dict)
    values: Mapping[str, Any] = field(default_factory=dict)
    facts: Mapping[str, Any] = field(default_factory=dict)
    git: GitFacts | None = field(default_factory=GitFacts)  # None outside git (WSP-B15 to WSP-B18)
    changed_paths: tuple[str, ...] = ()  # git's outside the state root, or the manifest's outside git
    settings: Mapping[str, Any] = field(default_factory=dict)
    criteria: tuple[dict[str, Any], ...] = ()
    allow: tuple[str, ...] = ()
    out_dir: Path | None = None
    deadline_at: float = 0.0
    runs: list[CommandRun] = field(default_factory=list)
    reuse_store: Path | None = None  # the thread's stored command runs (CHK-B12, CHK-B13 Reuse)
    no_reuse_exit_codes: Mapping[str, tuple[int, ...]] = field(default_factory=dict)  # per allow-list prefix
    base_dir: Path | None = None  # where a run at the base makes its checkout (CHK-B18); a temporary folder when None
    base_checkout: Path | None = field(default=None, init=False)  # the checkout this context made, until `cleanup`
    _base_workdir: Path | None = field(default=None, init=False, repr=False)
    _own_dir: Path | None = field(default=None, init=False, repr=False)

    @property
    def deadline_s(self) -> float:
        return max(0.0, self.deadline_at - time.monotonic())

    def read_text(self, path: str | Path, max_bytes: int = 1_000_000) -> str:
        p = (self.workdir / path).resolve()
        if not p.is_relative_to(self.workdir.resolve()):
            raise PermissionError(f"{path} is outside the workspace")
        with open(p, "rb") as fh:
            return fh.read(max_bytes).decode("utf-8", errors="replace")

    def resolve(self, text: str) -> ResolvedCommand | CommandRefusal:
        return resolve_command(self.allow, text, self.workdir)

    def run(self, cmd: ResolvedCommand | str, timeout_s: float | None = None, reuse: bool = False,
            min_start_s: float = 0, at_base: bool = False) -> CommandRun:
        if isinstance(cmd, str):
            got = self.resolve(cmd)
            if isinstance(got, CommandRefusal):
                return CommandRun(argv=(clip(scrub(cmd), 200),), not_started=True, at_base=at_base,
                                  extra={"refused": got.reason})
            cmd = got
        if at_base:
            return self._run_at_base(cmd, timeout_s, reuse, min_start_s)
        left = self.deadline_s
        if left < min_start_s or left <= 0:
            r = CommandRun(argv=cmd.argv, not_started=True)
            self.runs.append(r)
            return r
        key = reuse_key(cmd, self.workdir) if reuse and self.reuse_store is not None else None
        if key is not None:
            hit = _stored(self.reuse_store, key)
            if hit is not None:
                self.runs.append(hit)
                return hit
        out_dir = self.out_dir or (self.workdir / ".tempergraph-check")
        limit = min(timeout_s, left) if timeout_s else left
        r = run_command(cmd, self.workdir, out_dir / f"{len(self.runs) + 1}.out", limit, main=self.main_checkout)
        self.runs.append(r)
        if key is not None and r.finished and r.exit_code not in self.no_reuse_exit_codes.get(cmd.prefix, ()):
            _store(self.reuse_store, key, r)
        return r

    def _run_at_base(self, cmd: ResolvedCommand, timeout_s: float | None, reuse: bool, min_start_s: float
                     ) -> CommandRun:
        """CHK-B18 to CHK-B20: the command in a clean checkout of `git.base`, reused within one visit."""
        base = self.git.base if self.git is not None else ""
        left = self.deadline_s
        if left < min_start_s or left <= 0 or not gitmod.is_commit_id(base):
            return self._added(CommandRun(argv=cmd.argv, not_started=True, at_base=True))
        key = base_reuse_key(cmd, self.workdir, base, self.unit, self.visit) \
            if reuse and self.reuse_store is not None else None
        if key is not None:
            hit = _stored(self.reuse_store, key, at_base=True)
            if hit is not None:
                return self._added(hit)
        try:
            if cmd.cwd and not gitmod.folder_in_commit(self.workdir, base, cmd.cwd):
                return self._added(CommandRun(argv=cmd.argv, not_started=True, at_base=True))
            where = self._checkout(base)
        except (gitmod.GitError, OSError):
            return self._added(CommandRun(argv=cmd.argv, not_started=True, at_base=True))
        out_dir = self.out_dir or (self.workdir / ".tempergraph-check")
        limit = min(timeout_s, left) if timeout_s else left
        r = run_command(cmd, where, out_dir / f"{len(self.runs) + 1}.out", limit, main=self.main_checkout)
        r.at_base = True
        for path in {str(self.workdir), str(self.workdir.resolve())}:  # a command at the base can print either folder
            r.tail, r.program_path = r.tail.replace(path, "<workdir>"), r.program_path.replace(path, "<workdir>")
        self._added(r)
        if key is not None and r.finished and r.exit_code not in self.no_reuse_exit_codes.get(cmd.prefix, ()):
            _store(self.reuse_store, key, r, at_base=True)
        return r

    def _added(self, run: CommandRun) -> CommandRun:
        self.runs.append(run)
        return run

    def _checkout(self, base: str) -> Path:
        """The folder of the workspace in the checkout of `base`, made once per context (CHK-B18)."""
        if self._base_workdir is None:
            if self.base_dir is None:
                self._own_dir = Path(tempfile.mkdtemp(prefix="tempergraph-base-"))
            root = self._own_dir or self.base_dir
            assert root is not None
            root.mkdir(parents=True, exist_ok=True, mode=0o700)
            dest = root / "base"
            try:
                self._base_workdir = gitmod.base_checkout(self.workdir, base, dest)
            except gitmod.GitError:
                shutil.rmtree(dest, ignore_errors=True)
                raise
            self.base_checkout = dest
        return self._base_workdir

    def cleanup(self) -> None:
        """CHK-B21: remove the base checkout this context made, and the folder it made for it."""
        if self.base_checkout is not None:
            shutil.rmtree(self.base_checkout, ignore_errors=True)
        if self._own_dir is not None:
            shutil.rmtree(self._own_dir, ignore_errors=True)
        self.base_checkout = self._base_workdir = self._own_dir = None


def base_reuse_key(cmd: ResolvedCommand, workdir: Path, base: str, unit: str, visit: int) -> str:
    """CHK-B20: argv, resolved program, the command's folder, the base commit, the unit and the visit; never the
    workspace's head, status or files."""
    prog = shutil.which(cmd.argv[0]) if cmd.argv else None
    raw = json.dumps(["at_base", list(cmd.argv), cmd.cwd, prog, base, unit, visit])
    return hashlib.sha256(raw.encode()).hexdigest()


def reuse_key(cmd: ResolvedCommand, workdir: Path) -> str:
    """CHK-B12, CHK-B13: argv, working folder, resolved program and the content of the tree, no history.

    The tree is every file git tracks and every untracked file git does not ignore (every file outside a git
    repository), outside the state root, each by path, bytes and executable bit, read once. A commit of unchanged
    content leaves the key as it was; a tracked file removed from the tree is left out.
    """
    h = hashlib.sha256()
    prog = shutil.which(cmd.argv[0]) if cmd.argv else None
    h.update(json.dumps([list(cmd.argv), cmd.cwd, prog]).encode())
    for path in sorted(_tree_files(workdir)):
        f = workdir / path
        try:
            if not f.is_file():
                continue
            mode = f.stat().st_mode
            body = hashlib.sha256(f.read_bytes()).digest()
        except OSError:
            continue  # gone or unreadable while the key is made: not part of the tree
        h.update(path.encode() + b"\0" + (b"x" if mode & 0o111 else b"-") + body)
    return h.hexdigest()


def _tree_files(workdir: Path) -> list[str]:
    """The paths of the tree under `workdir`, relative to it and outside the state root (CHK-B13)."""
    if gitmod.toplevel(workdir) is not None:
        raw = gitmod.git(["ls-files", "-z", "--cached", "--others", "--exclude-standard"], workdir, check=False)
        paths = {p for p in raw.split("\0") if p}
    else:
        paths = set()
        for folder, dirs, files in os.walk(workdir):
            dirs[:] = [d for d in dirs if d != ".git"]
            rel = Path(folder).relative_to(workdir)
            paths.update(str(rel / name) if rel.parts else name for name in files)
    return [p for p in paths if not p.startswith(".tempergraph")]  # not the state root


def _stored(store: Path | None, key: str, at_base: bool = False) -> CommandRun | None:
    if store is None:
        return None
    try:
        lines = store.read_text(encoding="utf-8").splitlines()
    except OSError:
        return None
    for ln in reversed(lines):
        try:
            row = json.loads(ln)
        except ValueError:
            continue
        if row.get("key") == key and bool(row.get("at_base")) == at_base:  # a base key never matches a workspace run
            r = row["run"]
            return CommandRun(argv=tuple(r.get("argv") or ()), program_path=str(r.get("program_path") or ""),
                              exit_code=r.get("exit_code"), finished=True, reused=True, at_base=at_base,
                              duration_s=float(r.get("duration_s") or 0), output_path=str(r.get("output_path") or ""),
                              tail=str(r.get("tail") or ""))
    return None


def _store(store: Path | None, key: str, run: CommandRun, at_base: bool = False) -> None:
    if store is None:
        return
    try:
        store.parent.mkdir(parents=True, exist_ok=True, mode=0o700)
        with open(store, "a", encoding="utf-8") as fh:
            fh.write(json.dumps({"key": key, "at_base": at_base, "run": run.to_json()}) + "\n")
    except OSError:
        pass  # a lost store entry only costs a rerun of the command


def normalise(res: CheckResult) -> tuple[CheckResult, list[str]]:
    """CHK-B14: the worse of `result` and the worst finding; bounded, scrubbed facts."""
    notes: list[str] = []
    worst = res.result
    for f in res.findings:
        r = FINDING_TO_RESULT.get(f.status, "MAYBE")
        if ORDER[r] > ORDER[worst]:
            worst = r  # type: ignore[assignment]
    if worst != res.result:
        notes.append(f"check_result_mismatch: {res.result} -> {worst}")
    facts = {}
    for k, v in list(res.facts.items())[:MAX_FACTS]:
        if FACT_KEY.match(str(k)):
            facts[str(k)] = clip(scrub(str(v)), 200)
        else:
            notes.append(f"fact_key_invalid: {clip(str(k), 40)}")
    findings = [CheckFinding(status=f.status, criterion=f.criterion, place=clip(scrub(f.place), 200),
                             fix=clip(scrub(f.fix), 200), message=clip(scrub(f.message), 200), kind=f.kind)
                for f in res.findings]
    out = CheckResult(result=worst, evidence=scrub(res.evidence)[:8000], environmental=res.environmental,
                      untracked_only=res.untracked_only, findings=findings, facts=facts, runs=list(res.runs))
    return out, notes


def run_check(gate: GateSpec, ctx: CheckContext) -> tuple[CheckResult, list[str]]:
    """Call the gate's check; a raising check is an environmental FAIL, never a pass."""
    if gate.check is None:
        return CheckResult(result="PASS", evidence=""), []
    ctx.deadline_at = time.monotonic() + gate.check_timeout_s
    fn = gate.check.resolve()
    try:
        try:
            res = fn(ctx)
        except Exception as exc:  # noqa: BLE001 - a check's own failure is a result
            # CHK-B15, CHK-B14, CHK-B10, CHK-B17: a raising check is a workflow fault, not an environmental one; a retry is spent
            return CheckResult(result="FAIL", evidence=f"check raised {type(exc).__name__}"), [
                f"check_raised: {type(exc).__name__}"]
        if not isinstance(res, CheckResult):
            return CheckResult(result="FAIL", evidence="check returned no CheckResult"), ["check_result_invalid"]
        res.runs = [r.to_json() for r in ctx.runs]
        return normalise(res)
    finally:
        ctx.cleanup()  # CHK-B21: the base checkout is removed whether the check returned or raised


def failing(res: CheckResult) -> list[dict[str, str]]:
    """BUD-B16: the failing findings of a check result, as the rows a pause payload shows."""
    return [{"criterion": f.criterion or "", "place": f.place or "", "message": f.message or "", "fix": f.fix or ""}
            for f in res.findings if f.status == "fail"]


def repeat_key(findings: Sequence[Mapping[str, Any]], evidence: str) -> tuple[Any, ...]:
    """BUD-B16: what two failures must share to be the same: the failing findings by criterion, place and message,
    or the scrubbed evidence text when the check returned no finding."""
    rows = sorted((str(f.get("criterion") or ""), str(f.get("place") or ""), str(f.get("message") or ""))
                  for f in findings)
    return ("findings", tuple(rows)) if rows else ("evidence", str(evidence or "").strip())


def to_json(res: CheckResult) -> dict[str, Any]:
    return {"result": res.result, "evidence": res.evidence, "environmental": res.environmental,
            "untracked_only": res.untracked_only,
            "findings": [{"status": f.status, "criterion": f.criterion, "place": f.place, "fix": f.fix,
                          "message": f.message, "kind": f.kind} for f in res.findings],
            "facts": res.facts, "runs": res.runs}
