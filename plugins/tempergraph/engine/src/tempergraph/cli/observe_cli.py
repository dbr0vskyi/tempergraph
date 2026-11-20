"""Observability verbs of the CLI kept apart from the core verbs: `logs` and `store` (LOS §2.4).

`cli/main.py` adds these parsers and commands; every helper it shares (the environment, selectors, output) is
taken from there, so the verbs follow the same exit codes and output rules (CLI §4).
"""

from __future__ import annotations

import argparse
import time
from pathlib import Path
from typing import Any

from tempergraph.observe.rows import BY


def add_parsers(sub: Any) -> None:
    lg = sub.add_parser("logs", help="one log of a run from the local store (LOS)")
    lg.add_argument("selector")
    lg.add_argument("--session", metavar="KEY", help="a session key, or <unit>[.<attempt>] with --kind check")
    lg.add_argument("--kind", choices=("run", "raw", "activity", "stderr", "check", "hook", "engine"))
    lg.add_argument("--follow", action="store_true")
    lg.add_argument("--json", action="store_true", help="the file list as JSON (with no --kind)")
    lg.add_argument("--timeout", type=float, help=argparse.SUPPRESS)
    so = sub.add_parser("store", help="size, retention and export of the local store (LOS)")
    ssub = so.add_subparsers(dest="action")
    us = ssub.add_parser("usage")
    us.add_argument("--json", action="store_true")
    pr = ssub.add_parser("prune")
    pr.add_argument("--older-than", type=float, default=30.0, metavar="DAYS")
    pr.add_argument("--keep-failed", action=argparse.BooleanOptionalAction, default=True,
                    help="keep the logs of stopped or failed threads (the default); --no-keep-failed prunes them")
    pr.add_argument("--dry-run", action="store_true")
    pr.add_argument("--json", action="store_true")
    ex = ssub.add_parser("export")
    ex.add_argument("selector")
    ex.add_argument("path")
    rp = sub.add_parser("report", help="cost and friction reports over this state root's runs (OBS §2.4)")
    rp.add_argument("window", nargs="?", default="30d", help="7d, 24h, 30d (the default) or all")
    rp.add_argument("--by", choices=("unit", "executor", "version"), default="unit")
    rp.add_argument("--json", action="store_true")
    sa = sub.add_parser("stats", help="per-user monthly run rows, and across machines from a sink (CST §2.5)")
    sa.add_argument("action", nargs="?", choices=("flush", "sync"))
    src = sa.add_mutually_exclusive_group()
    src.add_argument("--source", metavar="SINK")
    src.add_argument("--local", action="store_true")
    sa.add_argument("--sync", action="store_true")
    when = sa.add_mutually_exclusive_group()
    when.add_argument("--month", metavar="YYYY-MM")
    when.add_argument("--since", metavar="YYYY-MM-DD")
    sa.add_argument("--by", choices=BY)
    sa.add_argument("--projection", action="store_true")
    sa.add_argument("--live", action="store_true")
    sa.add_argument("--json", action="store_true")
    at = sub.add_parser("attention", help="everything waiting on a person, oldest first (CLI-B6)")
    at.add_argument("--all-roots", action="store_true")
    at.add_argument("--json", action="store_true")


def cmd_logs(env: Any, a: argparse.Namespace) -> int:
    from tempergraph.cli.main import UsageError, _emit, _one, _root
    from tempergraph.store import logs

    root = _root(env)
    _spec, tid = _one(env, a.selector)
    t = logs.find(root, tid)
    if not a.kind:
        files = logs.run_files(t)
        if a.json:
            _emit(env, {"schema_version": 1, "thread_id": tid, "files": files})
        else:
            for f in files:
                env.out.write(f"{f['bytes']:>10}  {f['kind']:<9} {f['path']}\n")
        return 0
    try:
        paths = logs.log_path(root, t, a.kind, a.session)
    except LookupError as exc:
        raise UsageError(str(exc)) from exc
    if not paths or not any(p.exists() for p in paths):
        raise UsageError(f"{tid} has no {a.kind} log{f' for {a.session}' if a.session else ''}"
                         " (pruned, never written, or capture lowered)")
    if a.follow:
        if len(paths) != 1:
            raise UsageError("--follow takes one file: name it with --session")
        from tempergraph.durability.lock import is_held
        from tempergraph.store.layout import lock_path

        lock = lock_path(root, t.workflow, t.task_id)
        for line in logs.follow(paths[0], lambda: is_held(lock), timeout_s=a.timeout):
            env.out.write(line + "\n")
            env.out.flush()
        return 0
    for line in logs.read_lines(paths, a.kind, tid):
        env.out.write(line + "\n")
    return 0


def cmd_store(env: Any, a: argparse.Namespace) -> int:
    from tempergraph.cli.main import UsageError, _emit, _one, _root
    from tempergraph.store import logs

    root = _root(env)
    if a.action == "usage":
        doc = logs.usage(root)
        if a.json:
            _emit(env, doc)
        else:
            env.out.write(f"{doc['total_bytes']:>12}  total  {doc['state_root']}\n")
            for t in doc["threads"]:
                mark = "  past retention" if t["past_retention"] else ""
                env.out.write(f"{t['bytes']:>12}  {t['thread_id']}{mark}\n")
        for w in doc["warnings"]:
            env.err.write(f"warning: {w}\n")
        return 0
    if a.action == "prune":
        if a.older_than < 0:
            raise UsageError("--older-than takes a number of days, 0 or more")
        plan = logs.plan_prune(root, time.time(), a.older_than, a.keep_failed)
        failed = [] if a.dry_run else logs.apply(plan)
        pruned: dict[str, Any] = {"schema_version": 1, "dry_run": a.dry_run, "bytes": plan.bytes() if a.dry_run else None,
                               "removed" if not a.dry_run else "would_remove":
                               [str(p.relative_to(root)) for p in plan.remove],
                               "refused": plan.refused, "kept_failed": plan.kept_failed, "failed": failed}
        if a.json or a.dry_run:
            _emit(env, pruned)
        else:
            env.err.write(f"store prune: {len(plan.remove)} removed, {len(plan.refused)} running threads left alone"
                          f"{f', {len(failed)} could not be removed' if failed else ''}\n")
        return 0
    if a.action == "export":
        _spec, tid = _one(env, a.selector)
        target = (env.cwd / a.path).resolve()
        if not target.name.endswith(".tar.gz"):
            raise UsageError("store export writes a .tar.gz archive")
        if target.is_relative_to(root):
            raise UsageError("the archive must be written outside the state root")
        _emit(env, logs.export(logs.find(root, tid), target))
        return 0
    raise UsageError("store needs usage, prune or export")


def roots(env: Any, all_roots: bool) -> list[Path]:
    """This repository's state root, or every root of the machine index (`--all-roots`, CST §2.1)."""
    from tempergraph.cli.main import _root
    from tempergraph.observe.rows import index_roots

    if not all_roots:
        return [_root(env)]
    found = [Path(r["path"]) for r in index_roots()]
    try:
        here = _root(env)
        if here not in found:
            found.insert(0, here)
    except Exception:  # noqa: BLE001 - outside a repository, the index alone
        pass
    return found


def cmd_report(env: Any, a: argparse.Namespace) -> int:
    from tempergraph.cli.main import UsageError, _emit, _root
    from tempergraph.observe import report as rep

    try:
        since = rep.window(a.window)
    except ValueError as exc:
        raise UsageError(str(exc)) from exc
    doc = rep.report(_root(env), since, a.by)
    if a.json:
        _emit(env, doc)
        return 0
    env.out.write(report_text(doc))
    return 0


def _money(m: dict[str, Any]) -> str:
    parts = []
    if m.get("reported_usd") is not None:
        partial = "" if m["reported_sessions"] == m["sessions"] else f" ({m['reported_sessions']} of {m['sessions']})"
        parts.append(f"${m['reported_usd']:.2f} rep{partial}")
    if m.get("estimated_usd") is not None:
        parts.append(f"${m['estimated_usd']:.2f} est")
    if not parts:
        return "unmeasured"
    return ("≥ " if m.get("unmeasured") else "") + " · ".join(parts) + f" · {m['completeness']}"


def report_text(doc: dict[str, Any]) -> str:
    out = [f"{doc['threads']} threads since {doc['since'] or 'the start'} · {_money(doc['total'])}",
           f"steps {_money(doc['steps_and_judges']['steps'])} · judges {_money(doc['steps_and_judges']['judges'])}"]
    if doc["by"] == "executor":
        out += [f"  {k}: {_money(v)}" for k, v in doc["by_executor"].items()]
    elif doc["by"] == "version":
        out += [f"  {k}: {_money(v)}" for k, v in doc["by_version"].items()]
    else:
        for u in doc["units"]:
            out.append(f"  {u['workflow']}.{u['unit']}: first {_money(u['first_visit'])}")
            out += [f"      repeat {cause}: {_money(m)}" for cause, m in u["repeats"].items()]
    for c in doc["criteria"]:
        esc = f" · {c['escapes']} escapes" if c["escapes"] else ""
        out.append(f"  criterion {c['workflow']}.{c['criterion']}: "
                   + ", ".join(f"{k} {v}" for k, v in sorted(c["statuses"].items())) + esc)
    out += [f"  {t['class']}: {t['thread_id']} {t['unit']} attempt {t['attempt']}" for t in doc["timeouts"]]
    out += [f"  loop: {lp['thread_id']} {lp['session_key']} {lp['tool']} ×{lp['repeats']}" for lp in doc["loops"]]
    return "\n".join(out) + "\n"


def cmd_stats(env: Any, a: argparse.Namespace) -> int:
    from tempergraph.cli.main import UsageError, _emit
    from tempergraph.observe import rows, sinks
    from tempergraph.store.layout import home_path

    home = home_path()
    root = _here(env)
    try:
        if a.action == "flush":
            _emit(env, sinks.flush(home, root))
            return 0
        if a.action == "sync" or a.sync:
            synced = sinks.sync(home, root)
            if a.action == "sync":
                _emit(env, synced)
                return 0
        if a.live:
            _emit(env, sinks.live(home, a.source, root))
            return 0
        if a.month and (len(a.month) != 7 or a.month[4] != "-"):
            raise UsageError("--month takes YYYY-MM")
        if a.source and a.local:
            raise UsageError("--source and --local exclude each other")
        found, unknown, synced_at = sinks.rows_for(home, a.source, a.local, a.month, a.since, root)
    except sinks.SinkConfigError as exc:
        raise UsageError(str(exc)) from exc
    doc: dict[str, Any] = {"schema_version": 1, "source": a.source or ("local" if a.local else "home"),
                           "month": a.month, "since": a.since, "totals": rows.totals(found), "unknown_schema": unknown,
                           "synced": synced_at}
    if a.by:
        groups: dict[str, list[dict[str, Any]]] = {}
        for r in found:
            groups.setdefault(rows._key(r, a.by), []).append(r)
        doc["by"] = {"key": a.by, "groups": {k: rows.totals(v) for k, v in sorted(groups.items())}}
    if a.projection:
        doc["projection"] = rows.projection(found, by_version=a.by == "version")
    _emit(env, doc)
    return 0


def _here(env: Any) -> Path | None:
    """This folder's state root when there is one; `stats` reads its `config/sinks.json` too."""
    from tempergraph.store.layout import state_root_path

    try:
        root = state_root_path(env.cwd)
    except Exception:  # noqa: BLE001 - outside a repository `stats` reads the home folder only
        return None
    return root if root.is_dir() else None


def cmd_attention(env: Any, a: argparse.Namespace) -> int:
    from tempergraph.cli.main import _emit
    from tempergraph.observe.attention import attention, line

    doc = attention(roots(env, a.all_roots), env.catalog.specs)
    if a.json:
        _emit(env, doc)
    elif not doc["items"]:
        env.out.write("Nothing is waiting on a person.\n")
    else:
        for i in doc["items"]:
            env.out.write(line(i) + "\n")
    return 0


COMMANDS = {"logs": cmd_logs, "store": cmd_store, "report": cmd_report, "stats": cmd_stats,
            "attention": cmd_attention}

