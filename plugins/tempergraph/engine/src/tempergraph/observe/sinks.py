"""Sinks for run rows and heartbeats (CST-B10, CST-B12, CST-B13, CST-B11), the fleet copy at home, and the readers (CST-B14, CST-B15, CST-B16).

Nothing leaves the machine unless the operator lists a sink in `config/sinks.json` of the home folder or the
state root (CST-B1). A run's exit appends a *reference* to its local stats row to each sink's outbox; the
flusher builds the sink row from that local row with the sink's key, appends it to this machine's folder in
the sink, and only then drops the reference, so an outbox never holds names or text (CST-B5) and a row may
arrive twice (readers de-duplicate by `row_id`). Every flush also syncs the fleet copy under
`~/.tempergraph/fleet/<sink>/`, which `stats` reads with no sink access at query time (CST-B7).

The flusher is detached by default, so a slow share never delays a run's exit; `TEMPERGRAPH_FLUSHER=inline`
flushes in the exiting process and `off` leaves the outbox for `stats flush`.
"""

from __future__ import annotations

import contextlib
import hashlib
import hmac
import json
import os
import re
import secrets
import sys
import time
from collections import defaultdict
from collections.abc import Iterable
from dataclasses import dataclass
from datetime import datetime
from pathlib import Path
from typing import Any

from tempergraph.observe.rows import _locked, read_index, read_rows, totals
from tempergraph.store.layout import now_iso

SINKS_FILE = "sinks.json"
ROW_KINDS = ("run", "heartbeat", "supervision", "session")
DEFAULT_KINDS = ("run", "heartbeat", "supervision")  # `session` rows are opt-in (CST-B9)
SLUG = re.compile(r"^[a-z0-9-]{1,40}$")
WORD = re.compile(r"^[a-z0-9_:-]{1,40}$")
STALE_S = 300
FAILING_WARN_S = 7 * 86_400
HEARTBEAT_S = 60.0
ROLLUP_BY = ("machine", "user", "repo", "workflow", "executor", "model")
# Fields copied as they are from a local `run` row: numbers, booleans and engine words only (CST-B9).
COPY = ("row_id", "kind", "schema_version", "machine_id", "workflow", "workflow_version", "segment", "executors",
        "models", "exit_code", "reason", "units_run", "repeats", "gate_verdicts", "escapes", "tokens", "sessions",
        "reported_sessions", "estimated_sessions", "unmeasured_sessions", "reported_cost_usd", "estimated_cost_usd",
        "completeness", "wall_s", "agent_s", "person_wait_s", "touches_undesigned", "touches_by_decider",
        "agent_own_rescues", "level", "level_by", "callers_unknown", "ended_at")


class SinkConfigError(ValueError):
    """A `sinks.json` the engine refuses (CST-B10, CST-B14, CST-B8): exit 2 from the `stats` verbs."""


@dataclass(frozen=True, kw_only=True)
class Sink:
    name: str
    kind: str
    path: Path
    include: tuple[str, ...] = DEFAULT_KINDS
    user: str = "hash"
    repo: str = "hash"
    tickets: bool = False

    def takes(self, kind: str) -> bool:
        return kind in self.include


# -- configuration ---------------------------------------------------------------------------------------------


def _file(folder: Path) -> list[dict[str, Any]]:
    p = folder / "config" / SINKS_FILE
    if not p.exists():
        return []
    try:
        doc = json.loads(p.read_text(encoding="utf-8"))
    except (OSError, ValueError) as exc:
        raise SinkConfigError(f"{p}: not readable JSON ({type(exc).__name__})") from exc
    entries = doc.get("sinks") if isinstance(doc, dict) else None
    if not isinstance(entries, list):
        raise SinkConfigError(f"{p}: needs a `sinks` list")
    names = [str(e.get("name")) for e in entries if isinstance(e, dict)]
    dup = sorted({n for n in names if names.count(n) > 1})
    if dup:
        raise SinkConfigError(f"{p}: two sinks named {dup[0]!r}")
    return [dict(e, _file=str(p)) for e in entries if isinstance(e, dict)]


def _sink(e: dict[str, Any]) -> Sink:
    where = e.get("_file")
    name, kind = str(e.get("name") or ""), str(e.get("kind") or "directory")
    if not SLUG.match(name):
        raise SinkConfigError(f"{where}: sink name {name!r} must match [a-z0-9-]{{1,40}}")
    if kind == "otlp":
        raise SinkConfigError(f"{where}: sink {name!r}: the otlp kind is designed but not in this release (TEL)")
    if kind != "directory" or not e.get("path"):
        raise SinkConfigError(f"{where}: sink {name!r} needs kind `directory` and a `path`")
    include = tuple(e.get("include") or DEFAULT_KINDS)
    bad = [k for k in include if k not in ROW_KINDS]
    user, repo = str(e.get("user") or "hash"), str(e.get("repo") or "hash")
    if bad or user not in ("name", "hash", "none") or repo not in ("name", "hash"):
        raise SinkConfigError(f"{where}: sink {name!r}: include, user or repo has a value it does not take")
    return Sink(name=name, kind=kind, path=Path(str(e["path"])).expanduser(), include=include, user=user,
                repo=repo, tickets=e.get("tickets") is True)


def load(home: Path, state_root: Path | None = None) -> list[Sink]:
    """The sinks in force: the home folder's list, a state root's entries replacing those of the same name."""
    merged: dict[str, dict[str, Any]] = {}
    for folder in (home, state_root):
        if folder is not None:
            for e in _file(folder):
                merged[str(e.get("name"))] = e
    return [_sink(e) for e in merged.values()]


def find(home: Path, name: str, state_root: Path | None = None) -> Sink | None:
    return next((s for s in load(home, state_root) if s.name == name), None)


# -- identity (CST-B11) ---------------------------------------------------------------------------------------


def sink_key(sink: Sink) -> bytes | None:
    """The sink's shared key from `<path>/sink.json`, made by the first machine that writes; None if unreachable."""
    if not sink.path.is_dir():
        return None
    p = sink.path / "sink.json"
    for _ in range(2):
        try:
            return bytes.fromhex(str(json.loads(p.read_text(encoding="utf-8"))["key"]))
        except FileNotFoundError:
            pass
        except (OSError, ValueError, KeyError):
            return None
        try:
            fd = os.open(p, os.O_CREAT | os.O_EXCL | os.O_WRONLY, 0o600)
        except FileExistsError:
            time.sleep(0.05)
            continue
        except OSError:
            return None
        with os.fdopen(fd, "w", encoding="utf-8") as fh:
            json.dump({"schema_version": 1, "key": secrets.token_hex(32), "created_at": now_iso()}, fh)
    return None


def digest(key: bytes, text: str) -> str:
    return hmac.new(key, text.encode("utf-8"), hashlib.sha256).hexdigest()[:32]


def normalize_origin(url: str) -> str:
    """`git@host:o/r.git`, `https://u:p@host/o/r` → `host/o/r`: no scheme, credentials or `.git`."""
    u = url.strip()
    u = re.sub(r"^[a-z+]+://", "", u)
    u = re.sub(r"^[^@/]*@", "", u)
    u = u.replace(":", "/", 1) if re.match(r"^[^/]+:[^/]", u) else u
    u = re.sub(r"\.git/?$", "", u).rstrip("/")
    host, _, rest = u.partition("/")
    return f"{host.lower()}/{rest}" if rest else host.lower()


def _git(repo_dir: Path, *args: str) -> str:
    from tempergraph import git

    if not repo_dir.is_dir():
        return ""
    try:
        return git.git(list(args), repo_dir, check=False).strip()
    except git.GitError:
        return ""


@dataclass
class _Who:
    """The git facts one state root's rows are hashed from; read once per flush."""

    origin: str
    folder: str
    email: str
    name: str


_WHO: dict[str, _Who] = {}


def _who(state_root: str | None) -> _Who:
    key = str(state_root or "")
    if key not in _WHO:
        repo_dir = Path(key).parent if key else Path.cwd()
        origin = _git(repo_dir, "remote", "get-url", "origin")
        _WHO[key] = _Who(origin=normalize_origin(origin) if origin else "", folder=repo_dir.name,
                         email=_git(repo_dir, "config", "user.email"), name=_git(repo_dir, "config", "user.name"))
    return _WHO[key]


def _repo_id(sink: Sink, key: bytes, who: _Who) -> str | None:
    if sink.repo == "name":
        return who.folder or None
    return digest(key, who.origin or f"folder:{who.folder}")


def sink_row(row: dict[str, Any], sink: Sink, key: bytes) -> dict[str, Any]:
    """The row a sink receives from a local `run` row: hashed names, no free text (CST-B11, CST-B5)."""
    who = _who(row.get("state_root"))
    out = {k: row.get(k) for k in COPY}
    out["thread_hash"] = digest(key, str(row.get("thread_id")))
    out["repo_id"] = _repo_id(sink, key, who)
    out["user"] = (digest(key, who.email) if who.email else None) if sink.user == "hash" \
        else (row.get("user") or who.name or None) if sink.user == "name" else None
    out["ticket"] = row.get("ticket") if sink.tickets else None
    alias = row.get("alias")
    out["alias"] = alias if isinstance(alias, str) and SLUG.match(alias) else None
    origin = row.get("origin")
    out["origin"] = origin if isinstance(origin, str) and WORD.match(origin) else None
    for f in ("parent", "schedule_id"):  # TCK-B24: a scheduled run's `origin` goes as a word, its schedule id as an HMAC
        out[f] = digest(key, str(row[f])) if row.get(f) else None
    return out


# -- writing into the sink -------------------------------------------------------------------------------------


def _machine(home: Path) -> dict[str, Any]:
    try:
        return dict(json.loads((home / "machine.json").read_text(encoding="utf-8")))
    except (OSError, ValueError):
        return {}


def _replace(path: Path, data: Any) -> None:
    """Atomic replace with the share's own permissions, so every machine can read it."""
    path.parent.mkdir(parents=True, exist_ok=True)
    tmp = path.with_name(f".{path.name}.{os.getpid()}.tmp")
    tmp.write_text(json.dumps(data, ensure_ascii=False) + "\n", encoding="utf-8")
    os.replace(tmp, path)


def _append(path: Path, row: dict[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with open(path, "a", encoding="utf-8") as fh:
        fh.write(json.dumps(row, ensure_ascii=False) + "\n")
        fh.flush()
        os.fsync(fh.fileno())


def _machine_dir(sink: Sink, home: Path) -> Path:
    from tempergraph.constants import ENGINE_VERSION
    from tempergraph.store.layout import ensure_home

    me = _machine(ensure_home(home))  # machine.json exists before this machine writes anywhere
    folder = sink.path / "machines" / str(me.get("machine_id") or "unknown")
    if not (folder / "machine.json").exists():
        _replace(folder / "machine.json", {"schema_version": 1, "machine_id": me.get("machine_id"),
                                           "label": me.get("label"), "engine_version": ENGINE_VERSION,
                                           "first_seen": now_iso()})
    return folder


# -- outbox and flush ------------------------------------------------------------------------------------------


def outbox(home: Path, name: str) -> Path:
    return home / "outbox" / f"{name}.jsonl"


def enqueue(home: Path, row: dict[str, Any], log: Path) -> int:
    """At `run_exit`: a reference to the local row in each sink's outbox; returns how many sinks took it."""
    from tempergraph.docs import append_jsonl

    root = log.parents[3]
    try:
        sinks = [s for s in load(home, root) if s.takes("run")]
    except SinkConfigError:
        import logging

        logging.getLogger("tempergraph.sinks").warning("sinks.json refused; no row queued")
        return 0
    month = str(row.get("ended_at") or now_iso())[:7]
    for s in sinks:
        append_jsonl(outbox(home, s.name), {"row_id": row["row_id"], "kind": "run", "month": month,
                                            "state_root": str(root)})
    return len(sinks)


def enqueue_sessions(home: Path, sessions: list[dict[str, Any]], log: Path, month: str) -> int:
    """References to the segment's `session` rows for each sink that opted into them."""
    from tempergraph.docs import append_jsonl

    if not sessions:
        return 0
    root = log.parents[3]
    try:
        takers = [s for s in load(home, root) if s.takes("session")]
    except SinkConfigError:
        return 0
    for s in takers:
        for r in sessions:
            append_jsonl(outbox(home, s.name), {"row_id": r["row_id"], "kind": "session", "month": month,
                                                "state_root": str(root)})
    return len(takers)


def session_row(row: dict[str, Any], key: bytes) -> dict[str, Any]:
    """The `session` row a sink receives: the thread hashed, no text (CST-B9, CST-B11)."""
    out = {k: row.get(k) for k in ("row_id", "kind", "schema_version", "machine_id", "workflow", "workflow_version",
                                   "segment", "unit", "session_kind", "executor", "model", "tokens",
                                   "reported_cost_usd", "estimated_cost_usd", "duration_s", "slow_host", "outcome",
                                   "tool_calls", "ended_at")}
    out["thread_hash"] = digest(key, str(row.get("thread_id")))
    return out


def start_flusher(home: Path) -> None:
    mode = os.environ.get("TEMPERGRAPH_FLUSHER", "detached")
    if mode == "off":
        return
    if mode == "inline":
        flush(home)
        return
    from tempergraph import detach

    detach.start("tempergraph.observe.sinks", ("flush",), home)


def _local_rows(home: Path, month: str, cache: dict[str, dict[str, dict[str, Any]]]) -> dict[str, dict[str, Any]]:
    if month not in cache:
        found, _ = read_rows([home / "stats" / f"{month}.jsonl"])
        cache[month] = {str(r.get("row_id")): r for r in found}
    return cache[month]


def _kept_rows(home: Path, kind: str, month: str, cache: dict[str, dict[str, dict[str, Any]]]
               ) -> dict[str, dict[str, Any]]:
    k = f"{kind}:{month}"
    if k not in cache:
        path = home / "supervision" / "rows" if kind == "supervision" else home / "stats" / "sessions"
        cache[k] = {str(r.get("row_id")): r for r in _read_jsonl(path / f"{month}.jsonl")}
    return cache[k]


def supervision_row(row: dict[str, Any], key: bytes) -> dict[str, Any]:
    """The `supervision` row a sink receives (CST-B9, SCO-B17): figures and hashed ids only."""
    out = {k: row.get(k) for k in ("row_id", "kind", "schema_version", "workflow", "closed_at", "marginal", "turn",
                                   "completeness")}
    out["machine_id"] = row.get("machine_id")
    out["thread_hash"] = digest(key, str(row.get("thread_id")))
    out["sessions"] = [{"host": s.get("host"), "session_hash": digest(key, str(s.get("session_hash"))),
                        "reported_cost_usd": s.get("reported_cost_usd")} for s in row.get("sessions") or []]
    return out


def _read_jsonl(path: Path) -> list[dict[str, Any]]:
    try:
        lines = path.read_text(encoding="utf-8").splitlines()
    except OSError:
        return []
    out = []
    for ln in lines:
        with contextlib.suppress(ValueError):
            r = json.loads(ln)
            if isinstance(r, dict):
                out.append(r)
    return out


def _flush_one(home: Path, name: str, box: Path) -> dict[str, Any]:
    state_file = box.with_suffix(".state.json")
    result: dict[str, Any] = {"name": name, "delivered": 0, "kept": 0, "error": None}
    with _locked(box, wait_s=0.5) as got:
        if not got:
            result["error"] = "another flush holds the outbox"
            return result
        entries = _read_jsonl(box)
        cache: dict[str, dict[str, dict[str, Any]]] = {}
        done = 0
        for e in entries:
            root = e.get("state_root")
            try:
                sink = find(home, name, Path(root) if root else None)
            except SinkConfigError as exc:
                result["error"] = str(exc)
                break
            if sink is None:
                result["error"] = "no longer configured"
                break
            kind = str(e.get("kind")) if e.get("kind") in ("supervision", "session") else "run"
            rows = _local_rows(home, str(e.get("month")), cache) if kind == "run" else \
                _kept_rows(home, kind, str(e.get("month")), cache)
            local = rows.get(str(e.get("row_id")))
            if local is None:  # the local row is gone; nothing to send
                done += 1
                continue
            key = sink_key(sink)
            if key is None:
                result["error"] = "unreachable"
                break
            try:
                folder = _machine_dir(sink, home)
                if kind == "run":
                    _append(folder / "runs" / f"{e.get('month')}.jsonl", sink_row(local, sink, key))
                elif kind == "supervision":
                    _append(folder / "supervision" / f"{e.get('month')}.jsonl", supervision_row(local, key))
                else:
                    _append(folder / "sessions" / f"{e.get('month')}.jsonl", session_row(local, key))
            except OSError as exc:
                result["error"] = f"write failed ({type(exc).__name__})"
                break
            done += 1
            result["delivered"] += 1
        rest = entries[done:]
        if rest:
            tmp = box.with_name(f".{box.name}.tmp")
            tmp.write_text("".join(json.dumps(r) + "\n" for r in rest), encoding="utf-8")
            os.replace(tmp, box)
        else:
            box.unlink(missing_ok=True)
        result["kept"] = len(rest)
    from tempergraph.docs import write_json

    if result["error"] and result["error"] != "another flush holds the outbox":
        prev = _read_state(state_file)
        write_json(state_file, {"schema_version": 1, "first_failure_at": prev.get("first_failure_at") or now_iso(),
                                "last_error": result["error"], "last_try_at": now_iso()})
    elif not result["error"]:
        state_file.unlink(missing_ok=True)
    return result


def _read_state(path: Path) -> dict[str, Any]:
    try:
        return dict(json.loads(path.read_text(encoding="utf-8")))
    except (OSError, ValueError):
        return {}


def flush(home: Path, state_root: Path | None = None) -> dict[str, Any]:
    """`stats flush` and the detached flusher: deliver every outbox, in order, then sync (CST-B10, CST-B12, CST-B13)."""
    results = []
    names = sorted(p.stem for p in (home / "outbox").glob("*.jsonl")) if (home / "outbox").is_dir() else []
    for name in names:
        results.append(_flush_one(home, name, outbox(home, name)))
    with contextlib.suppress(SinkConfigError):
        write_heartbeats(home, state_root)
    synced = sync(home, state_root)
    return {"schema_version": 1, "sinks": results, "synced": synced["sinks"]}


def warnings(home: Path, now: float | None = None) -> list[str]:
    """One line per sink failing for 7 days or more (CST-B10, CST-B12, CST-B13), for `status`."""
    now = time.time() if now is None else now
    out = []
    folder = home / "outbox"
    for p in sorted(folder.glob("*.state.json")) if folder.is_dir() else []:
        st = _read_state(p)
        since = _ts(st.get("first_failure_at"))
        if since is not None and now - since >= FAILING_WARN_S:
            name = p.name.removesuffix(".state.json")
            out.append(f"sink {name} has failed since {st.get('first_failure_at')}: {st.get('last_error')}; "
                       f"its rows wait in the outbox (`tempergraph stats flush`)")
    return out


def _ts(text: Any) -> float | None:
    try:
        return datetime.fromisoformat(str(text).replace("Z", "+00:00")).timestamp()
    except ValueError:
        return None


# -- heartbeat (CST-B9) --------------------------------------------------------------------------------------


def _live_threads(home: Path, now: float) -> list[dict[str, Any]]:
    """Threads on this machine that run now or wait on a person, from the indexed state roots; read-only."""
    from tempergraph.durability.lock import is_held
    from tempergraph.run.events import records
    from tempergraph.store.layout import lock_path

    out = []
    for entry in read_index(home):
        root = Path(str(entry.get("path")))
        runs = root / "runs"
        if not runs.is_dir():
            continue
        for folder in sorted(p for p in runs.glob("*/*") if p.is_dir()):
            wf, task = folder.parent.name, folder.name
            held = is_held(lock_path(root, wf, task))
            if not held and _read_state(folder / "exit.json").get("exit_code") != 3:
                continue
            unit = attempt = alias = None
            est = 0.0
            pause_ts = None
            exit_code: Any = None
            measured = False
            for r in records(folder / "run.jsonl"):
                k = r.get("kind")
                if k == "run_started":
                    alias, est, pause_ts, exit_code, measured = r.get("alias"), 0.0, None, None, False
                elif k == "run_exit":  # written while the lock is still held
                    exit_code = r.get("exit_code")
                elif k == "unit_entered":
                    unit = r.get("unit")
                elif k == "attempt_start":
                    attempt = r.get("attempt")
                elif k == "agent_run":
                    v = (r.get("usage") or {}).get("estimated_cost_usd")
                    if isinstance(v, int | float):
                        est, measured = est + float(v), True
                elif k == "pause":
                    pause_ts = _ts(r.get("ts"))
            running = held and exit_code is None
            paused = exit_code == 3
            if not (running or paused):
                continue
            out.append({"thread_id": f"{wf}/{task}", "state_root": str(root), "workflow": wf, "alias": alias,
                        "state": "running" if running else "paused", "unit": unit, "attempt": attempt,
                        "estimated_cost_usd": round(est, 6) if measured else None,  # never 0 when unmeasured
                        "waiting_for_person_s": round(now - pause_ts, 1) if paused and pause_ts else None,
                        "waiting_on": "person" if paused else None})
    return out


def heartbeat(home: Path, sink: Sink, key: bytes, now: float | None = None) -> dict[str, Any]:
    now = time.time() if now is None else now
    me = _machine(home)
    threads = []
    for t in _live_threads(home, now):
        who = _who(t["state_root"])
        alias = t.get("alias")
        threads.append({"thread_hash": digest(key, t["thread_id"]), "repo_id": _repo_id(sink, key, who),
                        "workflow": t["workflow"], "alias": alias if isinstance(alias, str) and SLUG.match(alias)
                        else None, **{k: t[k] for k in ("state", "unit", "attempt", "estimated_cost_usd",
                                                         "waiting_for_person_s", "waiting_on")}})
    return {"schema_version": 1, "kind": "heartbeat", "machine_id": me.get("machine_id"), "label": me.get("label"),
            "at": now_iso(), "threads": threads}


def write_heartbeats(home: Path, state_root: Path | None = None) -> int:
    """Replaces this machine's `heartbeat.json` in every reachable sink that takes heartbeats; best effort."""
    n = 0
    for s in load(home, state_root):
        if not s.takes("heartbeat"):
            continue
        key = sink_key(s)
        if key is None:
            continue
        with contextlib.suppress(OSError):
            _replace(_machine_dir(s, home) / "heartbeat.json", heartbeat(home, s, key))
            n += 1
    return n


_LAST_BEAT: dict[str, float] = {}


def on_record(log: Path, kind: str) -> None:
    """Called by the run log's writer: a heartbeat at most every 60 s while the run lives, and at its ends."""
    home_s = os.environ.get("TEMPERGRAPH_HOME", "")
    now = time.monotonic()
    if kind not in ("run_started", "run_exit", "pause") and now - _LAST_BEAT.get(home_s, -1e9) < HEARTBEAT_S:
        return
    _LAST_BEAT[home_s] = now
    from tempergraph.store.layout import home_path

    with contextlib.suppress(Exception):
        home, root = home_path(), log.parents[3]
        if (home / "config" / SINKS_FILE).exists() or (root / "config" / SINKS_FILE).exists():
            write_heartbeats(home, root)


# -- sync and the fleet copy (CST-B10, CST-B12, CST-B13, LOS-B10, LOS-B11) --------------------------------------------------------------


def _copy_new_bytes(src: Path, dst: Path, offset: int) -> int:
    """Appends `src`'s whole lines past `offset` to `dst`; returns the new offset. A shorter source starts over."""
    size = src.stat().st_size
    if size < offset:
        offset = 0
        dst.unlink(missing_ok=True)
    if size == offset:
        return offset
    with open(src, "rb") as fh:
        fh.seek(offset)
        data = fh.read(size - offset)
    cut = data.rfind(b"\n") + 1
    if cut:
        dst.parent.mkdir(parents=True, exist_ok=True)
        with open(dst, "ab") as out:
            out.write(data[:cut])
    return offset + cut


def _sync_one(home: Path, sink: Sink) -> dict[str, Any]:
    from tempergraph.docs import write_json

    dst = home / "fleet" / sink.name
    state = _read_state(dst / "synced.json")
    offsets: dict[str, int] = dict(state.get("offsets") or {})
    machines: dict[str, Any] = dict(state.get("machines") or {})
    src = sink.path / "machines"
    if not src.is_dir():
        return {"name": sink.name, "reachable": False, "synced_at": state.get("synced_at")}
    now = now_iso()
    for mdir in sorted(p for p in src.iterdir() if p.is_dir()):
        mid = mdir.name
        rows = 0
        for f in sorted(mdir.rglob("*.jsonl")):
            rel = str(f.relative_to(src))
            with contextlib.suppress(OSError):
                offsets[rel] = _copy_new_bytes(f, dst / "machines" / rel, int(offsets.get(rel) or 0))
            rows += len(_read_jsonl(dst / "machines" / rel)) if "runs" in f.parts else 0
        for whole in ("machine.json", "heartbeat.json"):
            with contextlib.suppress(OSError, ValueError):
                _replace(dst / "machines" / mid / whole, json.loads((mdir / whole).read_text(encoding="utf-8")))
        label = _read_state(dst / "machines" / mid / "machine.json").get("label")
        machines[mid] = {"label": label, "synced_at": now, "rows": rows}
    me = str(_machine(home).get("machine_id") or "unknown")
    key = sink_key(sink)
    pending: list[dict[str, Any]] = []
    if key is not None:  # this machine's rows still in the outbox (CST-B10, CST-B12, CST-B13 "adds this machine's own rows")
        cache: dict[str, dict[str, dict[str, Any]]] = {}
        for e in _read_jsonl(outbox(home, sink.name)):
            local = _local_rows(home, str(e.get("month")), cache).get(str(e.get("row_id")))
            if local is not None:
                pending.append(sink_row(local, sink, key))
    pend = dst / "machines" / me / "pending.jsonl"
    if pending:
        pend.parent.mkdir(parents=True, exist_ok=True)
        pend.write_text("".join(json.dumps(r) + "\n" for r in pending), encoding="utf-8")
    else:
        pend.unlink(missing_ok=True)
    _rollup(dst)
    write_json(dst / "synced.json", {"schema_version": 1, "synced_at": now, "machines": machines,
                                     "offsets": offsets})
    return {"name": sink.name, "reachable": True, "synced_at": now, "machines": len(machines)}


def _fleet_paths(dst: Path) -> list[Path]:
    m = dst / "machines"
    return sorted(m.glob("*/runs/*.jsonl")) + sorted(m.glob("*/pending.jsonl")) if m.is_dir() else []


def _rollup(dst: Path) -> None:
    from tempergraph.docs import write_json
    from tempergraph.observe.rows import _key

    found, _ = read_rows(_fleet_paths(dst))
    _labels(found, _machine_labels([dst / "machines"]))
    per_month: dict[str, list[dict[str, Any]]] = defaultdict(list)
    for r in found:
        per_month[str(r.get("ended_at") or "")[:7] or "unknown"].append(r)
    for month, rs in per_month.items():
        doc: dict[str, Any] = {"schema_version": 1, "month": month, "totals": totals(rs), "by": {}}
        for by in ROLLUP_BY:
            groups: dict[str, list[dict[str, Any]]] = defaultdict(list)
            for r in rs:
                groups[_key(r, by)].append(r)
            doc["by"][by] = {k: totals(v) for k, v in sorted(groups.items())}
        write_json(dst / "rollup" / f"{month}.json", doc)


def sync(home: Path, state_root: Path | None = None) -> dict[str, Any]:
    """`stats sync`: pull every directory sink into the fleet copy; writes the fleet copy only (CST-B14, CST-B15, CST-B16)."""
    return {"schema_version": 1, "sinks": [_sync_one(home, s) for s in load(home, state_root)]}


# -- readers (CST-B14, CST-B15, CST-B16) ----------------------------------------------------------------------------------------


def _machine_labels(folders: Iterable[Path]) -> dict[str, str]:
    out: dict[str, str] = {}
    for f in folders:
        for m in sorted(f.glob("*/machine.json")) if f.is_dir() else []:
            label = _read_state(m).get("label")
            if label:
                out[m.parent.name] = str(label)
    return out


def _labels(rows: list[dict[str, Any]], labels: dict[str, str]) -> None:
    for r in rows:
        mid = str(r.get("machine_id") or "")
        if mid in labels and not r.get("machine_label"):
            r["machine_label"] = labels[mid]


def _month_ok(row: dict[str, Any], month: str | None, since: str | None) -> bool:
    ended = str(row.get("ended_at") or "")
    if month:
        return ended[:7] == month
    if since:
        return ended[:10] >= since
    return True


def _ago(at: Any, now: float) -> float | None:
    t = _ts(at)
    return round(now - t, 1) if t is not None else None


def rows_for(home: Path, source: str | None, local: bool, month: str | None, since: str | None,
             state_root: Path | None = None, conflicts: list[str] | None = None
             ) -> tuple[list[dict[str, Any]], int, dict[str, Any] | None]:
    """Rows for `stats`: the home folder (this machine plus each sink's fleet copy), `--local`, or `--source`."""
    now = time.time()
    local_paths = sorted((home / "stats").glob("*.jsonl")) if (home / "stats").is_dir() else []
    me = _machine(home)
    labels = {str(me.get("machine_id")): str(me.get("label"))} if me.get("label") else {}
    synced: dict[str, Any] | None = None
    if local:
        paths = local_paths
    elif source:
        sink = find(home, source, state_root)
        if sink is None:
            raise SinkConfigError(f"no sink named {source!r} is configured")
        paths = sorted((sink.path / "machines").glob("*/runs/*.jsonl"))
        labels.update(_machine_labels([sink.path / "machines"]))
    else:
        paths, synced = [], {}
        for s in load(home, state_root):
            dst = home / "fleet" / s.name
            paths += _fleet_paths(dst)
            labels.update(_machine_labels([dst / "machines"]))
            st = _read_state(dst / "synced.json")
            if st:
                synced[s.name] = {"synced_at": st.get("synced_at"), "machines": {
                    mid: {**m, "ago_s": _ago(m.get("synced_at"), now)} for mid, m in (st.get("machines") or {}).items()}}
        paths += local_paths  # after the fleet copy, so a delivered row reads as the sink holds it
        synced = synced or None
    if month:
        paths = [p for p in paths if p.stem in (month, "pending")]
    found, unknown = read_rows(paths, conflicts)
    found = [r for r in found if _month_ok(r, month, since)]
    _labels(found, labels)
    return found, unknown, synced


def live(home: Path, source: str | None, state_root: Path | None = None) -> dict[str, Any]:
    """`stats --live`: heartbeats of every machine, a beat older than 5 minutes that lists a running thread
    marked `stale`; this machine's own threads are read fresh. Read-only."""
    now = time.time()
    me = str(_machine(home).get("machine_id") or "")
    beats: dict[str, dict[str, Any]] = {}
    if source:
        sink = find(home, source, state_root)
        if sink is None:
            raise SinkConfigError(f"no sink named {source!r} is configured")
        folders = [sink.path / "machines"]
    else:
        folders = [home / "fleet" / s.name / "machines" for s in load(home, state_root)]
    for f in folders:
        for p in sorted(f.glob("*/heartbeat.json")) if f.is_dir() else []:
            b = _read_state(p)
            mid = str(b.get("machine_id") or p.parent.name)
            if mid not in beats or str(b.get("at")) > str(beats[mid].get("at")):
                beats[mid] = b
    if not source:
        own = _live_threads(home, now)
        beats[me] = {"machine_id": me, "label": _machine(home).get("label"), "at": now_iso(), "threads": [
            {k: t[k] for k in ("workflow", "alias", "state", "unit", "attempt", "estimated_cost_usd",
                               "waiting_for_person_s", "waiting_on")} | {"thread_id": t["thread_id"]} for t in own]}
    machines, runs = [], []
    for mid, b in sorted(beats.items()):
        age = _ago(b.get("at"), now)
        threads = list(b.get("threads") or [])
        stale = bool(age is not None and age > STALE_S and any(t.get("state") == "running" for t in threads))
        machines.append({"machine_id": mid, "label": b.get("label"), "at": b.get("at"), "age_s": age,
                         "stale": stale, "this_machine": mid == me})
        for t in threads:
            wait = t.get("waiting_for_person_s")
            if isinstance(wait, int | float) and t.get("state") == "paused" and age is not None and mid != me:
                wait = round(wait + age, 1)  # the wait has gone on since the beat was written
            runs.append({**t, "waiting_for_person_s": wait, "machine_id": mid, "label": b.get("label"),
                         "stale": stale})
    return {"schema_version": 1, "source": source or "home", "machines": machines, "runs": runs}


def main(argv: list[str] | None = None) -> int:
    """`python -m tempergraph.observe.sinks flush`: the detached flusher."""
    from tempergraph.store.layout import home_path

    args = sys.argv[1:] if argv is None else argv
    if args[:1] == ["flush"]:
        with contextlib.suppress(Exception):
            flush(home_path())
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
