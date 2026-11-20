"""Observability verbs of the CLI kept apart from the core verbs: `logs` and `store` (LOS §2.4).

`cli/main.py` adds these parsers and commands; every helper it shares (the environment, selectors, output) is
taken from there, so the verbs follow the same exit codes and output rules (CLI §4).
"""

from __future__ import annotations

import argparse
import time
from typing import Any


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


COMMANDS = {"logs": cmd_logs, "store": cmd_store}

