"""The machine index (CST §2.1), the per-user stats rows (OBS §2.4, CST §2.2 `run`) and their readers.

Rows are written from the run log at each `run_exit`, by :func:`on_run_exit`, which the run log's writer calls
after the record is on disk; the index is touched at `run_started` by :func:`on_run_started`. Both are best
effort and never change a run (contract C2). `stats` and `attention` only read (contract C13).
"""

from __future__ import annotations

import contextlib
import json
import os
import statistics
import time
import uuid
from collections import defaultdict
from collections.abc import Iterable, Iterator
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

from tempergraph.docs import append_jsonl, write_json
from tempergraph.store.layout import ensure_home, home_path, now_iso

INDEX_LOCK_S = 2.0
TOKENS = ("input_tokens", "output_tokens", "cache_read_tokens", "cache_write_tokens", "thinking_tokens")
BY = ("machine", "user", "repo", "workflow", "version", "executor", "model", "ticket", "exit", "month", "parent",
      "schedule", "level", "decider", "host")


def _parts(log: Path) -> tuple[Path, str, str]:
    """`<state root>/runs/<workflow>/<task>/run.jsonl` → (state root, workflow, task)."""
    return log.parents[3], log.parent.parent.name, log.parent.name


# -- machine index ---------------------------------------------------------------------------------------------


@contextlib.contextmanager
def _locked(path: Path, wait_s: float = INDEX_LOCK_S) -> Iterator[bool]:
    lock = path.with_suffix(".lock")
    deadline = time.monotonic() + wait_s
    fd = None
    while fd is None:
        try:
            fd = os.open(lock, os.O_CREAT | os.O_EXCL | os.O_WRONLY, 0o600)
        except FileExistsError:
            with contextlib.suppress(OSError):
                if time.time() - lock.stat().st_mtime > 30:  # a holder that died long ago
                    lock.unlink()
                    continue
            if time.monotonic() >= deadline:
                yield False
                return
            time.sleep(0.05)
    try:
        yield True
    finally:
        os.close(fd)
        with contextlib.suppress(OSError):
            lock.unlink()


def read_index(home: Path | None = None) -> list[dict[str, Any]]:
    path = (home or home_path()) / "index.json"
    try:
        doc = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return []
    roots = doc.get("roots") if isinstance(doc, dict) else None
    return [r for r in roots if isinstance(r, dict) and r.get("path")] if isinstance(roots, list) else []


def touch_index(state_root: Path, home: Path | None = None, now: str | None = None) -> bool:
    """Adds or refreshes this state root in `~/.tempergraph/index.json` under a lock (CST §2.1, LOS-B6)."""
    home = ensure_home(home)
    path = home / "index.json"
    stamp = now or now_iso()
    with _locked(path) as got:
        if not got:
            return False
        roots = read_index(home)
        key = str(state_root.resolve())
        for r in roots:
            if r["path"] == key:
                r["last_run_at"] = stamp
                break
        else:
            roots.append({"path": key, "repository": state_root.resolve().parent.name, "first_seen": stamp,
                          "last_run_at": stamp})
        write_json(path, {"schema_version": 1, "roots": roots})
    return True


def index_roots(home: Path | None = None) -> list[dict[str, Any]]:
    """Every indexed state root with `missing` when its folder is gone; the index is never changed by a reader."""
    return [{**r, "missing": not Path(r["path"]).is_dir()} for r in read_index(home)]


# -- stats rows ------------------------------------------------------------------------------------------------


def _machine(home: Path) -> dict[str, Any]:
    try:
        return dict(json.loads((home / "machine.json").read_text(encoding="utf-8")))
    except (OSError, ValueError):
        return {}


def _git_user(state_root: Path) -> str | None:
    from tempergraph import git

    try:
        name = git.git(["config", "user.name"], state_root.parent, check=False).strip()
    except Exception:  # noqa: BLE001
        return None
    return name or None


def _ts(text: Any) -> float | None:
    try:
        return datetime.fromisoformat(str(text).replace("Z", "+00:00")).timestamp()
    except ValueError:
        return None


def run_row(log: Path, recs: Iterable[dict[str, Any]], segment: int | None = None) -> dict[str, Any] | None:
    """The `run` row of one segment of a thread, from its run log (CST §2.2, OBS §2.4); numbers and names only."""
    root, workflow, task = _parts(log)
    started: dict[str, Any] | None = None
    exit_: dict[str, Any] | None = None
    executors: set[str] = set()
    models: set[str] = set()
    units: set[str] = set()
    repeats: dict[str, int] = defaultdict(int)
    verdicts: dict[str, int] = defaultdict(int)
    tokens: dict[str, int | None] = dict.fromkeys(TOKENS)
    rep = est = 0.0
    n = n_rep = n_est = unmeasured = 0
    agent_s = 0.0
    wait_s = 0.0
    attempts: dict[str, int] = defaultdict(int)
    sup: dict[str, Any] | None = None
    for r in recs:
        if segment is not None and r.get("segment") != segment:
            continue
        kind = r.get("kind")
        if kind == "run_started":
            started = r
        elif kind == "run_exit":
            exit_ = r
        elif kind == "unit_entered" and r.get("unit"):
            units.add(str(r["unit"]))
            if int(r.get("visit") or 1) > 1:
                repeats[str(r.get("entered_from") or "revisit").split(":", 1)[0]] += 1
        elif kind == "attempt_start" and r.get("session_kind") in ("step", "retry") and r.get("unit"):
            attempts[str(r["unit"])] += 1
            if r.get("session_kind") == "retry":
                repeats["retry"] += 1
        elif kind == "agent_run":
            n += 1
            if r.get("executor"):
                executors.add(str(r["executor"]))
            u = r.get("usage") or {}
            for m in (u.get("by_model") or {}):
                models.add(str(m))
            for t in TOKENS:
                v = u.get(t)
                if isinstance(v, int):
                    tokens[t] = (tokens[t] or 0) + v
            rc, ec = u.get("reported_cost_usd"), u.get("estimated_cost_usd")
            if isinstance(rc, int | float):
                rep, n_rep = rep + rc, n_rep + 1
            if isinstance(ec, int | float):
                est, n_est = est + ec, n_est + 1
            if not isinstance(rc, int | float) and not isinstance(ec, int | float):
                unmeasured += 1
            if isinstance(r.get("duration_s"), int | float):
                agent_s += float(r["duration_s"])
        elif kind == "gate" and r.get("verdict"):
            verdicts[str(r["verdict"])] += 1
        elif kind == "supervision":
            sup = r
        elif kind == "human" and isinstance(r.get("wait_s"), int | float):
            wait_s += float(r["wait_s"])
    if exit_ is None:
        return None
    t0, t1 = _ts((started or {}).get("ts")), _ts(exit_.get("ts"))
    home = home_path()
    completeness = "incomplete" if unmeasured else "complete" if n_rep == n else "estimated"
    return {
        "row_id": str(uuid.uuid4()), "kind": "run", "schema_version": 1,
        "machine_id": _machine(home).get("machine_id"), "user": _git_user(root),
        "repo": root.parent.name, "state_root": str(root), "workflow": workflow,
        "workflow_version": (started or {}).get("workflow_version"), "thread_id": f"{workflow}/{task}",
        "segment": exit_.get("segment"), "alias": (started or {}).get("alias"), "label": (started or {}).get("label"),
        "origin": (started or {}).get("origin"), "parent": (started or {}).get("parent"),
        "schedule_id": (started or {}).get("schedule"), "ticket": task,
        "executors": sorted(executors), "models": sorted(models),
        "exit_code": exit_.get("exit_code"), "reason": exit_.get("reason"), "units_run": len(units),
        "repeats": dict(repeats), "gate_verdicts": dict(verdicts), "escapes": None, "tokens": tokens,
        "sessions": n, "reported_sessions": n_rep, "estimated_sessions": n_est, "unmeasured_sessions": unmeasured,
        "reported_cost_usd": round(rep, 6) if n_rep else None, "estimated_cost_usd": round(est, 6) if n_est else None,
        "completeness": completeness, "wall_s": round(t1 - t0, 3) if t0 is not None and t1 is not None else None,
        "agent_s": round(agent_s, 3) if agent_s else None, "person_wait_s": round(wait_s, 3) if wait_s else None,
        # copied from the segment's supervision record, the builder the ledger row uses too (SUP-AC-2)
        **_supervision_fields(sup),
        "ended_at": exit_.get("ts"),
    }


def session_rows(log: Path, recs: Iterable[dict[str, Any]], run: dict[str, Any]) -> list[dict[str, Any]]:
    """The `session` rows of one segment, one per `agent_run` (CST §2.2): numbers and engine words only."""
    out = []
    for r in recs:
        if r.get("kind") != "agent_run" or r.get("segment") != run.get("segment"):
            continue
        u = r.get("usage") or {}
        models = sorted((u.get("by_model") or {}).keys())
        outcome = "ok" if r.get("ok") else "timed_out" if r.get("timed_out") else "stalled" if r.get("stalled") \
            else "infra" if r.get("infra_cause") else "failed"
        out.append({"row_id": str(uuid.uuid4()), "kind": "session", "schema_version": 1,
                    "machine_id": run.get("machine_id"), "thread_id": run.get("thread_id"),
                    "state_root": run.get("state_root"), "workflow": run.get("workflow"),
                    "workflow_version": run.get("workflow_version"), "segment": run.get("segment"),
                    "unit": r.get("unit"), "session_kind": r.get("session_kind") or "step",
                    "executor": r.get("executor"), "model": models[0] if len(models) == 1 else None,
                    "tokens": {t: u.get(t) for t in TOKENS}, "reported_cost_usd": u.get("reported_cost_usd"),
                    "estimated_cost_usd": u.get("estimated_cost_usd"), "duration_s": r.get("duration_s"),
                    "slow_host": bool(r.get("slow_host")), "outcome": outcome, "tool_calls": len(r.get("tools") or []),
                    "ended_at": r.get("ts")})
    return out


def _supervision_fields(sup: dict[str, Any] | None) -> dict[str, Any]:
    if sup is None:
        return dict.fromkeys(("touches_undesigned", "touches_by_decider", "agent_own_rescues", "level", "level_by",
                              "callers_unknown"))
    by: dict[str, int] = defaultdict(int)
    for cls in ("rescue", "steer"):
        for d, n in ((sup.get("touches") or {}).get(cls) or {}).items():
            if isinstance(n, int) and n:
                by[d] += n
    return {"touches_undesigned": sup.get("undesigned"), "touches_by_decider": dict(sorted(by.items())),
            "agent_own_rescues": sup.get("agent_own_rescues"), "level": sup.get("level"),
            "level_by": sup.get("level_by"), "callers_unknown": sup.get("callers_unknown")}


def stats_path(home: Path, month: str) -> Path:
    return home / "stats" / f"{month}.jsonl"


def on_run_started(log: Path) -> None:
    """Called by the run log's writer after `run_started`: the machine index (CST §2.1); best effort."""
    try:
        touch_index(_parts(log)[0])
    except Exception:  # noqa: BLE001 - C2, LOS-B6
        import logging

        logging.getLogger("tempergraph.index").warning("machine index not updated")


def on_run_exit(log: Path, segment: int | None) -> None:
    """Called by the run log's writer after `run_exit`: the stats row and the outbox rows; best effort (C2)."""
    try:
        from tempergraph.run.events import records

        row = run_row(log, records(log), segment)
        if row is None:
            return
        home = ensure_home()
        month = str(row["ended_at"] or now_iso())[:7]
        append_jsonl(stats_path(home, month), row)
        sessions = session_rows(log, records(log), row)
        for srow in sessions:
            append_jsonl(home / "stats" / "sessions" / f"{month}.jsonl", srow)
        from tempergraph.observe import sinks, supervision_cost

        with contextlib.suppress(Exception):  # SCO §2.5: the next writing process closes what has ended
            supervision_cost.close(home)
        if sinks.enqueue(home, row, log) + sinks.enqueue_sessions(home, sessions, log, month):
            sinks.start_flusher(home)
    except Exception:  # noqa: BLE001
        import logging

        logging.getLogger("tempergraph.stats").warning("stats row not written")


# -- readers ---------------------------------------------------------------------------------------------------


SAME = ("kind", "machine_id", "workflow", "segment", "exit_code", "ended_at")  # equal in a row's local and sink form


def read_rows(paths: Iterable[Path], conflicts: list[str] | None = None) -> tuple[list[dict[str, Any]], int]:
    """Rows from JSON-lines files, de-duplicated by `row_id` (CST-AC-3); a newer major schema is skipped. A
    repeated `row_id` whose content differs (a copied `machine.json` or stats file) is kept twice and its id
    added to `conflicts` (CST §4)."""
    seen: dict[str, tuple[Any, ...]] = {}
    out: list[dict[str, Any]] = []
    unknown = 0
    for p in paths:
        try:
            lines = p.read_text(encoding="utf-8").splitlines()
        except OSError:
            continue
        for ln in lines:
            try:
                r = json.loads(ln)
            except ValueError:
                continue
            if not isinstance(r, dict):
                continue
            if int(r.get("schema_version") or 1) > 1:
                unknown += 1
                continue
            rid = str(r.get("row_id") or "")
            same = tuple(r.get(k) for k in SAME)
            if rid and rid in seen:
                if seen[rid] == same:
                    continue
                if conflicts is not None and rid not in conflicts:
                    conflicts.append(rid)
            seen.setdefault(rid, same)
            out.append(r)
    return out, unknown


def _key(r: dict[str, Any], by: str) -> str:
    if by == "version":
        return f"{r.get('workflow')}@{r.get('workflow_version') or '?'}"
    if by == "exit":
        return str(r.get("exit_code"))
    if by == "month":
        return str(r.get("ended_at") or "")[:7]
    if by == "executor":
        return ",".join(r.get("executors") or []) or "none"
    if by == "model":
        return ",".join(r.get("models") or []) or "not recorded"
    if by == "machine":
        mid = str(r.get("machine_id") or "?")  # two machines may share a label (a host name); never one key
        return f"{r['machine_label']} ({mid[:8]})" if r.get("machine_label") else mid
    if by == "schedule":
        return str(r.get("schedule_id") or "none")
    if by == "decider":
        return ",".join(sorted((r.get("touches_by_decider") or {}).keys())) or "none"
    if by == "repo":
        return str(r.get("repo_id") or r.get("repo") or "none")
    field = {"user": "user", "workflow": "workflow", "ticket": "ticket", "parent": "parent",
             "level": "level", "host": "host"}[by]
    return str(r.get(field) or "none")


def totals(rows: list[dict[str, Any]]) -> dict[str, Any]:
    """Run count, thread count, and reported and estimated cost apart with the completeness flag (CST §2.5)."""
    rep = [r["reported_cost_usd"] for r in rows if isinstance(r.get("reported_cost_usd"), int | float)]
    est = [r["estimated_cost_usd"] for r in rows if isinstance(r.get("estimated_cost_usd"), int | float)]
    incomplete = any(r.get("completeness") == "incomplete" for r in rows)
    estimated = any(r.get("completeness") == "estimated" for r in rows)
    return {"runs": len(rows), "threads": len({r.get("thread_id") or r.get("thread_hash") for r in rows}),
            "reported_usd": round(sum(rep), 6) if rep else None, "estimated_usd": round(sum(est), 6) if est else None,
            "completeness": "incomplete" if incomplete else "estimated" if estimated else "complete",
            "lower_bound": incomplete,
            "exits": dict(sorted(_count(str(r.get("exit_code")) for r in rows).items()))}


def _count(xs: Iterable[str]) -> dict[str, int]:
    out: dict[str, int] = defaultdict(int)
    for x in xs:
        out[x] += 1
    return out


def projection(rows: list[dict[str, Any]], by_version: bool = False) -> list[dict[str, Any]]:
    """Median and 90th percentile of estimated cost per finished run, per workflow (CST §2.5); `thin` under 5."""
    per: dict[str, dict[str, float]] = defaultdict(dict)
    finished: set[str] = set()
    for r in rows:
        tid = str(r.get("thread_id") or r.get("thread_hash"))
        key = f"{r.get('workflow')}@{r.get('workflow_version') or '?'}" if by_version else str(r.get("workflow"))
        cost = r.get("estimated_cost_usd") if isinstance(r.get("estimated_cost_usd"), int | float) \
            else r.get("reported_cost_usd")
        if isinstance(cost, int | float):
            per[key][tid] = per[key].get(tid, 0.0) + float(cost)
        if r.get("exit_code") == 0:
            finished.add(tid)
    out = []
    for key, threads in sorted(per.items()):
        costs = sorted(c for t, c in threads.items() if t in finished)
        if not costs:
            continue
        p90 = costs[min(len(costs) - 1, max(0, round(0.9 * len(costs) + 0.5) - 1))]
        out.append({"workflow": key, "runs": len(costs), "median_usd": round(statistics.median(costs), 6),
                    "p90_usd": round(p90, 6), "thin": len(costs) < 5})
    return out


def month_now() -> str:
    return datetime.now(UTC).strftime("%Y-%m")
