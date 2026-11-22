"""The local store's verbs (LOS-B14, LOS-B15) and retention (LOS-B16): `logs`, `store usage|prune|export`.

`logs` and `store usage` read only (OVR-B15); `store prune --dry-run` reads only too. `store prune` removes
what the retention rule allows of finished threads and never touches a run log, a session's `meta.json`, a
checkpoint, the ledger or stats. `store export` packs one run after a scrub pass over every text file.
"""

from __future__ import annotations

import contextlib
import io
import json
import os
import shutil
import tarfile
import time
from collections.abc import Iterator
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

from tempergraph.constants import ExitCode
from tempergraph.durability.lock import is_held
from tempergraph.security.scrub import scrub
from tempergraph.store.layout import lock_path, run_dir

DAY = 86_400.0
KINDS = ("run", "raw", "activity", "stderr", "check", "hook", "engine")

#: LOS-B16: what `store prune` removes by default and after how many days.
SESSION_LOGS = ("raw.jsonl", "activity.jsonl", "stderr.log", "output")
LOG_DAYS = 30
EVIDENCE_DAYS = 90
ENGINE_DAYS = 14
WARN_BYTES = 2 * 1024**3


def _size(path: Path) -> int:
    if path.is_file():
        try:
            return path.stat().st_size
        except OSError:
            return 0
    total = 0
    for dirpath, _dirs, files in os.walk(path):
        for f in files:
            with contextlib.suppress(OSError):
                total += (Path(dirpath) / f).stat().st_size
    return total


def kind_of(rel: Path) -> str:
    """The LOS-B7, LOS-B8, LOS-B9 kind of a file under a run folder, by its place."""
    parts = rel.parts
    if parts[0] == "sessions" and len(parts) >= 3:
        name = parts[2]
        return {"raw.jsonl": "raw", "activity.jsonl": "activity", "stderr.log": "stderr", "output": "output",
                "tools.jsonl": "tools", "meta.json": "meta", "live.json": "live"}.get(name, "session")
    if parts[0] in ("checks", "hooks", "evidence"):
        return parts[0].rstrip("s") if parts[0] != "evidence" else "evidence"
    if rel.name == "run.jsonl":
        return "run"
    return "record"


@dataclass(frozen=True, kw_only=True)
class Thread:
    workflow: str
    task_id: str
    folder: Path
    running: bool
    exit_code: int | None
    ended_at: float | None  # epoch seconds of the last segment's end

    @property
    def thread_id(self) -> str:
        return f"{self.workflow}/{self.task_id}"

    @property
    def finished(self) -> bool:
        """Ended and not resumable by a person's decision: finished, stopped or failed; never paused or live."""
        return not self.running and self.exit_code is not None and self.exit_code != ExitCode.PAUSED

    @property
    def failed(self) -> bool:
        return self.finished and self.exit_code != ExitCode.FINISHED


def threads(root: Path) -> Iterator[Thread]:
    """Every run folder under the state root, whether or not its workflow is in the catalog."""
    runs = root / "runs"
    if not runs.is_dir():
        return
    for wf in sorted(p for p in runs.iterdir() if p.is_dir()):
        for task in sorted(p for p in wf.iterdir() if p.is_dir()):
            ex = task / "exit.json"
            code: int | None = None
            ended: float | None = None
            if ex.exists():
                try:
                    code = int(json.loads(ex.read_text(encoding="utf-8")).get("exit_code"))
                    ended = ex.stat().st_mtime
                except (OSError, ValueError, TypeError):
                    code = None
            yield Thread(workflow=wf.name, task_id=task.name, folder=task,
                         running=is_held(lock_path(root, wf.name, task.name)), exit_code=code, ended_at=ended)


# -- logs ------------------------------------------------------------------------------------------------------


def run_files(t: Thread) -> list[dict[str, Any]]:
    """`logs <selector>` with no `--kind`: the run's files with their kinds and sizes."""
    out = []
    for path in sorted(p for p in t.folder.rglob("*") if p.is_file()):
        rel = path.relative_to(t.folder)
        out.append({"path": str(rel), "kind": kind_of(rel), "bytes": _size(path)})
    return out


def log_path(root: Path, t: Thread, kind: str, session: str | None) -> list[Path]:
    """The file(s) one `--kind` names. `check` takes `--session <unit>[.<attempt>]`; `engine` filters by thread."""
    if kind == "run":
        return [t.folder / "run.jsonl"]
    if kind in ("raw", "activity", "stderr"):
        if not session:
            raise LookupError(f"--kind {kind} needs --session <session_key>")
        name = {"raw": "raw.jsonl", "activity": "activity.jsonl", "stderr": "stderr.log"}[kind]
        return [t.folder / "sessions" / session / name]
    if kind == "check":
        base = t.folder / "checks"
        if session:
            unit, _, attempt = session.partition(".")
            base = base / unit / attempt if attempt else base / unit
        return sorted(p for p in base.rglob("*") if p.is_file()) if base.exists() else []
    if kind == "hook":
        base = t.folder / "hooks"
        return sorted(base.glob("*.log")) if base.exists() else []
    if kind == "engine":
        return sorted((root / "engine").glob("*.jsonl")) if (root / "engine").exists() else []
    raise LookupError(f"unknown --kind {kind!r}; one of {', '.join(KINDS)}")


def read_lines(paths: list[Path], kind: str, thread_id: str) -> Iterator[str]:
    for path in paths:
        try:
            text = path.read_text(encoding="utf-8", errors="replace")
        except OSError:
            continue
        for line in text.splitlines():
            if kind == "engine":
                try:
                    if json.loads(line).get("thread_id") != thread_id:
                        continue
                except ValueError:
                    continue
            yield line


def follow(path: Path, live: Any, poll_s: float = 0.5, timeout_s: float | None = None) -> Iterator[str]:
    """New lines of one file while `live()` holds; stat first, read second (MADR-0002 of the monitor)."""
    offset = 0
    start = time.monotonic()
    while True:
        try:
            size = path.stat().st_size
        except OSError:
            size = 0
        if size < offset:
            offset = 0
        if size > offset:
            with open(path, "rb") as fh:
                fh.seek(offset)
                chunk = fh.read(size - offset)
            end = chunk.rfind(b"\n")
            if end >= 0:
                yield from chunk[: end + 1].decode("utf-8", errors="replace").splitlines()
                offset += end + 1
        if not live() or (timeout_s is not None and time.monotonic() - start > timeout_s):
            return
        time.sleep(poll_s)


# -- usage and prune -----------------------------------------------------------------------------------------


@dataclass(kw_only=True)
class Plan:
    """What `store prune` removes (or would, with `--dry-run`), and what it refused."""

    remove: list[Path] = field(default_factory=list)
    refused: list[dict[str, str]] = field(default_factory=list)
    kept_failed: list[str] = field(default_factory=list)

    def bytes(self) -> int:
        return sum(_size(p) for p in self.remove)


def prunable(t: Thread, now: float, older_than_days: float = LOG_DAYS, keep_failed: bool = True) -> list[Path]:
    """LOS-B16 for one thread: session logs, check output and hook logs past `older_than_days`, evidence past 90."""
    if not t.finished or t.ended_at is None or (keep_failed and t.failed):
        return []
    age = (now - t.ended_at) / DAY
    out: list[Path] = []
    if age >= older_than_days:
        sessions = t.folder / "sessions"
        if sessions.is_dir():
            for s in sorted(p for p in sessions.iterdir() if p.is_dir()):
                out += [s / n for n in SESSION_LOGS if (s / n).exists()]
        checks = t.folder / "checks"
        if checks.is_dir():
            out += sorted(p for p in checks.rglob("*") if p.is_file() and p.name != "result.json")
        hooks = t.folder / "hooks"
        if hooks.is_dir():
            out += sorted(hooks.glob("*.log"))
    if age >= max(EVIDENCE_DAYS, older_than_days) and (t.folder / "evidence").is_dir():
        out.append(t.folder / "evidence")
    return out


def plan_prune(root: Path, now: float | None = None, older_than_days: float = LOG_DAYS,
               keep_failed: bool = True) -> Plan:
    now = time.time() if now is None else now
    plan = Plan()
    for t in threads(root):
        if t.running:
            plan.refused.append({"thread_id": t.thread_id, "reason": "running"})
            continue
        if keep_failed and t.failed and t.ended_at is not None and (now - t.ended_at) / DAY >= older_than_days:
            plan.kept_failed.append(t.thread_id)
        plan.remove += prunable(t, now, older_than_days, keep_failed)
    engine = root / "engine"
    if engine.is_dir():
        for f in sorted(engine.glob("*.jsonl")):
            try:
                if (now - f.stat().st_mtime) / DAY >= ENGINE_DAYS:
                    plan.remove.append(f)
            except OSError:
                pass
    return plan


def apply(plan: Plan) -> list[str]:
    """Removes the plan's paths; a path that cannot be removed is reported, the others go on (OVR-B4)."""
    failed = []
    for p in plan.remove:
        try:
            if p.is_dir():
                shutil.rmtree(p)
            else:
                p.unlink(missing_ok=True)
        except OSError as exc:
            failed.append(f"{p}: {type(exc).__name__}")
    return failed


def usage(root: Path, now: float | None = None) -> dict[str, Any]:
    """`store usage`: size per thread and per kind, the total, and the threads past the retention rule."""
    now = time.time() if now is None else now
    per_thread: list[dict[str, Any]] = []
    by_kind: dict[str, int] = {}
    for t in threads(root):
        kinds: dict[str, int] = {}
        for f in run_files(t):
            kinds[f["kind"]] = kinds.get(f["kind"], 0) + f["bytes"]
        for k, v in kinds.items():
            by_kind[k] = by_kind.get(k, 0) + v
        per_thread.append({"thread_id": t.thread_id, "bytes": sum(kinds.values()), "by_kind": kinds,
                           "past_retention": bool(prunable(t, now)),
                           "state": "running" if t.running else "ended" if t.exit_code is not None else "unknown"})
    other = {name: _size(root / name) for name in ("checkpoints", "engine", "batches", "backups", "upgrades",
                                                  "authoring", "scratch") if (root / name).exists()}
    ledger = root / "ledger.jsonl"
    if ledger.exists():
        other["ledger"] = _size(ledger)
    total = sum(int(t["bytes"]) for t in per_thread) + sum(other.values())
    warnings = []
    if total > WARN_BYTES:
        warnings.append(f"the state root holds {total / 1024**3:.1f} GB; `tempergraph store prune` lists what "
                        "the retention rule allows to remove")
    return {"schema_version": 1, "state_root": str(root), "total_bytes": total, "by_kind": by_kind,
            "other": other, "threads": per_thread, "warnings": warnings}


# -- export -----------------------------------------------------------------------------------------------


def _is_text(data: bytes) -> bool:
    return b"\0" not in data[:8192]


def export(t: Thread, target: Path) -> dict[str, Any]:
    """Packs one run's folder as `<workflow>/<task_id>/…` in a tar.gz, every text file scrubbed (LOS-AC3)."""
    scrubbed = skipped = 0
    target.parent.mkdir(parents=True, exist_ok=True)
    with tarfile.open(target, "w:gz") as tar:
        for path in sorted(p for p in t.folder.rglob("*") if p.is_file()):
            rel = Path(t.workflow) / t.task_id / path.relative_to(t.folder)
            try:
                data = path.read_bytes()
            except OSError:
                skipped += 1
                continue
            if not _is_text(data):
                skipped += 1  # binary files are left out: the scrub pass cannot read them
                continue
            clean = scrub(data.decode("utf-8", errors="replace")).encode("utf-8")
            scrubbed += 1
            info = tarfile.TarInfo(str(rel))
            info.size = len(clean)
            info.mode = 0o600
            info.mtime = int(path.stat().st_mtime)
            tar.addfile(info, io.BytesIO(clean))
    os.chmod(target, 0o600)
    return {"schema_version": 1, "thread_id": t.thread_id, "archive": str(target), "files": scrubbed,
            "left_out": skipped}


def find(root: Path, thread_id: str) -> Thread:
    wf, _, task = thread_id.partition("/")
    folder = run_dir(root, wf, task)
    for t in threads(root):
        if t.folder == folder:
            return t
    raise LookupError(f"{thread_id} has no run folder")
