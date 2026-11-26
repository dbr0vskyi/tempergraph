"""Observability verbs of the CLI kept apart from the core verbs: `logs` and `store` (LOS-B14, LOS-B15).

`cli/main.py` adds these parsers and commands; every helper it shares (the environment, selectors, output) is
taken from there, so the verbs follow the same exit codes and output rules (CLI-B17, CLI-B18, CLI-B19).
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
    pr.add_argument("--schedules", action="store_true",
                    help="also drop scheduled-run ledger rows older than --older-than days (TCK-B23); kept without it")
    pr.add_argument("--dry-run", action="store_true")
    pr.add_argument("--json", action="store_true")
    ex = ssub.add_parser("export")
    ex.add_argument("selector")
    ex.add_argument("path")
    rp = sub.add_parser("report", help="cost and friction reports over this state root's runs (OBS-B15)")
    rp.add_argument("window", nargs="?", default="30d", help="7d, 24h, 30d (the default) or all")
    rp.add_argument("--by", choices=("unit", "executor", "version", "workflow", "host", "level", "schedule"), default=None)
    rp.add_argument("--supervision", action="store_true", help="touches, levels, waits and supervision cost (SUP-B12)")
    rp.add_argument("--loop", action="store_true", help="the self-improvement loop's own figures (IMD-B22)")
    rp.add_argument("--switch", metavar="WORKFLOW/SWITCH", help="finished runs per arm and zone (CXR-B13)")
    rp.add_argument("--risk", metavar="WORKFLOW", help="judge attempts per gate and risk level (JRK-B10)")
    rp.add_argument("--json", action="store_true")
    lb = sub.add_parser("label", help="a person's label on a gate judgement (FBK-B9 explicit)")
    lb.add_argument("selector")
    lb.add_argument("gate", metavar="UNIT")
    lb.add_argument("--value", required=True, choices=("agree", "disagree"))
    lb.add_argument("--criterion")
    lb.add_argument("--attempt", type=int)
    lb.add_argument("--caller", choices=("person", "agent", "pipeline", "orchestrator", "scheduler", "engine"))
    lb.add_argument("--as-agent", action="store_true")
    lb.add_argument("--caller-app")
    lb.add_argument("--relayed", action="store_true")
    lb.add_argument("--json", action="store_true")
    sa = sub.add_parser("stats", help="per-user monthly run rows, and across machines from a sink (CST-B14, CST-B15, CST-B16)")
    sa.add_argument("action", nargs="?", choices=("flush", "sync", "forget"))
    sa.add_argument("--check", action="store_true",
                    help="with forget: print the state roots and rows it would remove and change nothing (CST-B17 to CST-B24)")
    src = sa.add_mutually_exclusive_group()
    src.add_argument("--source", metavar="SINK")
    src.add_argument("--local", action="store_true")
    sa.add_argument("--sync", action="store_true")
    when = sa.add_mutually_exclusive_group()
    when.add_argument("--month", metavar="YYYY-MM", help="the month to show; `stats forget` takes none (CST-B24)")
    when.add_argument("--since", metavar="YYYY-MM-DD")
    sa.add_argument("--by", choices=BY)
    sa.add_argument("--projection", action="store_true")
    sa.add_argument("--live", action="store_true")
    sa.add_argument("--json", action="store_true")
    sv = sub.add_parser("supervision", help="the supervision journal and the cost of supervising runs (SCO-B16)")
    svs = sv.add_subparsers(dest="action")
    hk = svs.add_parser("hook", help="one host hook event read from standard input; always exit 0 (SHL-B14, SHL-B15)")
    hk.add_argument("event")
    lo = svs.add_parser("log", help="journal entries read as JSON lines from standard input")
    lo.add_argument("--host", required=True)
    lo.add_argument("--session", required=True)
    lo.add_argument("--caller-app")
    cl = svs.add_parser("close", help="close the threads whose supervising sessions have ended (SCO-B15)")
    cl.add_argument("--session")
    sh = svs.add_parser("show", help="a thread's or a session's supervision (read-only)")
    sh.add_argument("selector", nargs="?")
    sh.add_argument("--session")
    sh.add_argument("--json", action="store_true")
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
        from tempergraph.observe import supervision_cost as sco
        from tempergraph.store.layout import home_path

        old = sco.prunable_journals(home_path(), time.time())  # SCO-B17: kept 90 days, like evidence
        gone = [] if a.dry_run else logs.apply(logs.Plan(remove=old))
        pruned["journals_removed" if not a.dry_run else "journals_would_remove"] = [str(p) for p in old]
        pruned["failed"] += gone
        if a.schedules:  # TCK-B23: the one thing that shortens the machine-wide ledger
            from tempergraph.cli import schedule_cli
            from tempergraph.schedule import ledger

            pruned["ledger_fires_removed" if not a.dry_run else "ledger_fires_would_remove"] = ledger.prune(
                a.older_than, schedule_cli.CLOCK(), dry_run=a.dry_run)
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
    """This repository's state root, or every root of the machine index (`--all-roots`, CST-B8)."""
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


def _loop_report(env: Any, a: argparse.Namespace, since: Any) -> int:
    from tempergraph.cli.main import _emit, _root
    from tempergraph.improve import calibration as cal
    from tempergraph.improve import loop_report as lr
    from tempergraph.improve import reliability as rel

    root = _root(env)
    specs = env.catalog.specs
    names = sorted(set(specs) | {p.name for p in (root / "runs").iterdir() if p.is_dir()}
                   if (root / "runs").is_dir() else set(specs))

    def coverage(w: str) -> list[str]:
        spec = specs.get(w)
        if spec is None:
            return []
        try:
            return [g["grade"] for g in rel.report(root, w, cal.judged_gates(spec),
                                                   lambda gate, binding: cal.passing(spec, gate))]
        except Exception:  # noqa: BLE001 - a gate that cannot be graded is left out of coverage
            return []

    doc = lr.report(root, names, since, coverage)
    if a.json:
        _emit(env, doc)
    else:
        env.out.write(lr.text(doc))
    return 0


def _risk_report(env: Any, a: argparse.Namespace) -> int:
    from tempergraph.cli.main import _emit, _root
    from tempergraph.observe import risk_report as rr

    doc = rr.report(_root(env), str(a.risk))
    if a.json:
        _emit(env, doc)
    else:
        env.out.write(rr.text(doc))
    return 0


def _switch_report(env: Any, a: argparse.Namespace, since: Any) -> int:
    from tempergraph.cli.main import UsageError, _emit, _root
    from tempergraph.model import flow
    from tempergraph.observe import switch_report as swr

    workflow, _, switch = str(a.switch).partition("/")
    if not workflow or not switch:
        raise UsageError("report --switch takes <workflow>/<switch>")
    spec = env.catalog.specs.get(workflow)
    units: set[str] | None = None
    size: str | None = None
    if spec is not None:
        u = spec.units.get(switch)
        if u is None or u.switch is None:
            raise UsageError(f"{workflow} has no switch {switch!r}")
        comp = u.switch.complexity
        units = set().union(*[flow.arm_units(spec, e) for e in u.switch.arms.values()])
        if comp is not None:
            units -= flow.arm_units(spec, comp.joins_at)
            size = comp.size
    doc = swr.report(_root(env), workflow, switch, since, units=units, size=size)
    if a.json:
        _emit(env, doc)
    else:
        env.out.write(swr.text(doc))
    return 0


def cmd_report(env: Any, a: argparse.Namespace) -> int:
    from tempergraph.cli.main import UsageError, _emit, _root
    from tempergraph.observe import report as rep
    from tempergraph.observe import rows

    try:
        since = rep.window(a.window)
    except ValueError as exc:
        raise UsageError(str(exc)) from exc
    if a.loop:
        return _loop_report(env, a, since)
    if a.risk:
        return _risk_report(env, a)
    if a.switch:
        return _switch_report(env, a, since)
    if a.supervision:
        from tempergraph.observe import supervision_report as sup

        by = a.by or "workflow"
        if by not in sup.BY:
            raise UsageError(f"report --supervision --by takes {', '.join(sup.BY)}")
        sdoc = sup.report(_root(env), since, by)
        if a.json:
            _emit(env, sdoc)
        else:
            env.out.write(sup.text(sdoc))
        return 0
    if a.by == "schedule":  # TCK-B24: from the schedules' fire logs, machine-wide, read-only
        sdoc = rows.schedule_report()
        if a.json:
            _emit(env, sdoc)
        else:
            for sid, g in sdoc["groups"].items():
                env.out.write(f"{sid}\tfires {g['fires']}\tended {g['ended']}\toutcomes {g['outcomes']}\t"
                              f"${g['estimated_usd']:.2f}{' (lower bound)' if g['incomplete'] else ''}\t"
                              f"skipped {g['skipped']}\tmissed {g['missed']}\trefused {g['refused']}\n")
            t = sdoc["totals"]
            env.out.write(f"total\tfires {t['fires']}\tended {t['ended']}\t${t['estimated_usd']:.2f}\tskipped {t['skipped']}"
                          f"\tmissed {t['missed']}\trefused {t['refused']}\n")
        return 0
    by = a.by or "unit"
    if by not in ("unit", "executor", "version"):
        raise UsageError("report --by takes unit, executor or version (workflow, host, level with --supervision)")
    doc = rep.report(_root(env), since, by)
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
    from tempergraph.store.layout import ensure_home, home_path

    home = home_path()
    if a.action == "forget":
        from tempergraph.observe import forget

        if a.month:
            raise UsageError("stats forget takes no month; it works on the month in which it runs")
        try:
            _emit(env, forget.forget(home, a.check))
        except forget.IndexInUse as exc:
            raise UsageError("the machine index is in use; try again") from exc
        return 0
    root = _here(env)
    try:
        if a.action == "flush":
            from tempergraph.observe import supervision_cost

            closed = supervision_cost.close(ensure_home())["closed"]
            _emit(env, {**sinks.flush(home, root), "supervision_closed": closed})
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
        conflicts: list[str] = []
        found, unknown, synced_at = sinks.rows_for(home, a.source, a.local, a.month, a.since, root, conflicts)
    except sinks.SinkConfigError as exc:
        raise UsageError(str(exc)) from exc
    doc: dict[str, Any] = {"schema_version": 1, "source": a.source or ("local" if a.local else "home"),
                           "month": a.month, "since": a.since, "totals": rows.totals(found), "unknown_schema": unknown,
                           "synced": synced_at, "duplicate_row_ids": conflicts}
    if conflicts:
        env.err.write(f"tempergraph: {len(conflicts)} row ids appear twice with different content; both are shown "
                      "(a copied machine.json or stats file?)\n")
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


def cmd_label(env: Any, a: argparse.Namespace) -> int:
    """The one writing verb of this module: one metadata-only `label` row in the ledger (FBK-B8)."""
    from tempergraph.cli.main import UsageError, _emit, _one, _root
    from tempergraph.docs import append_jsonl
    from tempergraph.observe.labels import LabelRefused, label

    root = _root(env)
    _, tid = _one(env, a.selector)
    caller = env.caller(a)
    try:
        row = label(root, tid, a.gate, a.value, caller, criterion=a.criterion, attempt=a.attempt,
                    relayed=bool(a.relayed))
    except LabelRefused as exc:
        raise UsageError(str(exc)) from exc
    append_jsonl(root / "ledger.jsonl", row)
    if a.json:
        _emit(env, row)
    else:
        env.out.write(f"label {row['value']} on {tid} {a.gate} (attempt {row['attempt']}, "
                      f"{row['gate_verdict']}) recorded, source {row['source']}\n")
    return 0


def cmd_attention(env: Any, a: argparse.Namespace) -> int:
    from tempergraph.cli import schedule_cli
    from tempergraph.cli.main import _emit
    from tempergraph.observe.attention import attention, line, loop_line, stale_line

    where = roots(env, a.all_roots)
    try:  # SIL-B29, SIL-B32: a lost runner is handed to the loop first; a failure there changes nothing below
        from tempergraph.improve import lost

        for r in where:
            lost.settle(r, env.catalog.specs, None, env.registry)
    except Exception:  # noqa: BLE001
        pass
    doc = attention(where, env.catalog.specs, schedule_cli.CLOCK().timestamp())
    if a.json:
        _emit(env, doc)
        return 0
    if not doc["items"] and not doc["loop"] and "trigger_stale" not in doc:
        env.out.write("Nothing is waiting on a person.\n")
    for i in doc["items"]:
        env.out.write(line(i) + "\n")
    if "trigger_stale" in doc:  # TCK-B7
        env.out.write(stale_line(doc["trigger_stale"]) + "\n")
    for s in doc["loop"]:  # CLI-B20: the loop's summaries after the items, never among them
        env.out.write(loop_line(s) + "\n")
    return 0


def _signals_env(env: Any) -> Any:
    import os

    return env.signals[0] if env.signals else os.environ


def cmd_supervision(env: Any, a: argparse.Namespace) -> int:
    import json
    import sys

    from tempergraph.cli.main import UsageError, _emit, _one
    from tempergraph.observe import supervision_cost as sco
    from tempergraph.store.layout import ensure_home, home_path

    if a.action == "hook":  # never changes, delays or refuses the host call (OVR-B4): exit 0 whatever happens
        try:
            raw = sys.stdin.read(4 * 1024 * 1024)
            payload = json.loads(raw) if raw.strip() else {}
            if isinstance(payload, dict):
                sco.hook(a.event, payload, _signals_env(env))
        except Exception:  # noqa: BLE001
            pass
        return 0
    if a.action == "log":
        if sco.disabled(_signals_env(env)):
            return 0
        if a.caller_app is not None and not sco.ID.match(a.caller_app):
            raise UsageError("--caller-app must be an id")
        entries = []
        for n, ln in enumerate(sys.stdin.read().splitlines(), 1):
            if not ln.strip():
                continue
            try:
                e = json.loads(ln)
            except ValueError as exc:
                raise UsageError(f"line {n}: not JSON") from exc
            if not isinstance(e, dict):
                raise UsageError(f"line {n}: not an object")
            if e.get("entry") == "session" and a.caller_app and "caller_app" not in e:
                e["caller_app"] = a.caller_app
            entries.append(e)
        try:
            count = sco.append(ensure_home(), a.host, a.session, entries)
        except sco.EntryRefused as exc:
            raise UsageError(f"nothing appended: {exc}") from exc
        _emit(env, {"schema_version": 1, "appended": count})
        return 0
    if a.action == "close":
        _emit(env, sco.close(ensure_home(), session=a.session))
        return 0
    if a.action == "show":
        if bool(a.selector) == bool(a.session):
            raise UsageError("supervision show takes a selector or --session")
        if a.selector:
            tid = a.selector if "/" in a.selector else _one(env, a.selector)[1]
            doc = sco.show(home_path(), thread=tid)
        else:
            doc = sco.show(home_path(), session=a.session)
        if a.json:
            _emit(env, doc)
        else:
            env.out.write(sco.text(doc))
        return 0
    raise UsageError("supervision takes hook, log, close or show")


COMMANDS = {"supervision": cmd_supervision, "logs": cmd_logs, "store": cmd_store, "report": cmd_report, "stats": cmd_stats, "label": cmd_label,
            "attention": cmd_attention}

