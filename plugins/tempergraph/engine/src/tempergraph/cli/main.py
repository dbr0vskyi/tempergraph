"""The engine CLI's release 1 core verbs (CLI §2, §4; milestone M1).

Exit codes are the caller contract (CON §2.9, ADR-0015). Read-only verbs create nothing and call no model
(contract C13). Machine output is JSON with `schema_version`; a run's one-line outcome goes to stderr.
"""

from __future__ import annotations

import argparse
import dataclasses
import json
import logging
import sys
import traceback
from collections.abc import Callable, Sequence
from pathlib import Path
from typing import IO, Any

from tempergraph.catalog import Catalog, PackageNotLoaded, from_registry, resolve_request
from tempergraph.cli import observe_cli
from tempergraph.constants import SCHEMA, ExitCode
from tempergraph.contracts import WorkflowSpec, thread_id
from tempergraph.executors.registry import Registry, default_registry

# Every verb word of CLI §2, reserved so it is never read as a workflow or a request (CLI-B2, AC-3).
VERBS = ("attention", "audit", "author", "batch", "blueprint", "config", "evals", "events", "executors", "facts",
         "graph", "hooks", "improve", "install", "label", "labels", "list", "literals", "logs", "orchestrate",
         "outcome", "report", "rerun", "resume", "run", "scaffold", "schedule", "self-check", "stats", "status",
         "stop", "store", "supervision", "update", "upgrade", "upgrade-check", "validate", "wait", "workflows",
         "worktree", "help")
WORKSPACES = ("auto", "worktree", "in_place")
CHECK_EXIT = {"ok": ExitCode.FINISHED, "needs": ExitCode.USAGE, "error": ExitCode.USAGE,
              "broken": ExitCode.INTERNAL}


class UsageError(Exception):
    pass


class _Parser(argparse.ArgumentParser):
    def error(self, message: str) -> Any:  # exit 2 through our own path, never argparse's SystemExit text
        raise UsageError(message)


def _parser() -> _Parser:
    p = _Parser(prog="tempergraph", description="Tempered rails for AI workflows")
    sub = p.add_subparsers(dest="verb", parser_class=_Parser)

    run = sub.add_parser("run", help="resolve, preflight and start a workflow")
    run.add_argument("workflow")
    run.add_argument("request", nargs="*")
    run.add_argument("--check", action="store_true", help="resolve and preflight only; nothing is created")
    run.add_argument("--task-id")
    run.add_argument("--input", action="append", default=[], metavar="K=V")
    _run_options(run)

    res = sub.add_parser("resume", help="resume a paused, stopped or unfinished thread")
    res.add_argument("workflow")
    res.add_argument("thread")
    res.add_argument("--decision")
    fb = res.add_mutually_exclusive_group()
    fb.add_argument("--feedback")
    fb.add_argument("--feedback-file")
    _run_options(res, start=False)

    st = sub.add_parser("status", help="the status document, or one thread's detail document")
    st.add_argument("selector", nargs="?")
    st.add_argument("--detail", action="store_true", help="the run detail document of one thread (RDD)")
    st.add_argument("--unit", help="with --detail: one unit in full")
    st.add_argument("--no-live", action="store_true", help="with --detail: leave out the live session blocks")
    st.add_argument("--json", action="store_true", help="machine output (the default for status)")
    ev = sub.add_parser("events", help="a thread's run-log records in seq order (EVT)")
    ev.add_argument("selector")
    ev.add_argument("--since", type=int, metavar="SEQ")
    ev.add_argument("--follow", action="store_true")
    ev.add_argument("--activity", metavar="SESSION_KEY", help="one session's activity journal instead")
    ev.add_argument("--json", action="store_true", help="one JSON object per line")
    ev.add_argument("--timeout", type=float, help=argparse.SUPPRESS)
    sub.add_parser("list", help="the workflow catalog")
    va = sub.add_parser("validate", help="validate a workflow")
    va.add_argument("workflow")
    ex = sub.add_parser("executors", help="registered executors and their capabilities")
    ex.add_argument("--probe", action="store_true")
    fa = sub.add_parser("facts", help="read-only facts about a run")
    fa.add_argument("selector")
    gr = sub.add_parser("graph", help="the workflow diagram")
    gr.add_argument("workflow")
    gr.add_argument("--format", choices=("mermaid", "md", "json"), default="mermaid")
    wa = sub.add_parser("wait", help="block until a thread's outcome")
    wa.add_argument("selector")
    wa.add_argument("--timeout", type=float, default=3600.0)
    so = sub.add_parser("stop", help="ask a live run to stop")
    so.add_argument("selector")
    so.add_argument("--now", action="store_true", help="stop the open session now instead of draining")
    wt = sub.add_parser("worktree", help="run worktrees")
    wsub = wt.add_subparsers(dest="action", parser_class=_Parser)
    wsub.add_parser("list")
    wp = wsub.add_parser("path")
    wp.add_argument("thread")
    observe_cli.add_parsers(sub)
    return p


def _run_options(p: argparse.ArgumentParser, start: bool = True) -> None:
    p.add_argument("--judge-executor")
    p.add_argument("--enforce-tools", action="store_true")
    p.add_argument("--strict-permissions", action="store_true")
    p.add_argument("--json", action="store_true")
    if start:
        p.add_argument("--alias")
        p.add_argument("--label")
        p.add_argument("--run-cost-cap", type=float)
        ws = p.add_mutually_exclusive_group()
        ws.add_argument("--workspace", choices=WORKSPACES)
        ws.add_argument("--worktree", dest="workspace", action="store_const", const="worktree")
        ws.add_argument("--in-place", dest="workspace", action="store_const", const="in_place")


@dataclasses.dataclass(kw_only=True)
class Env:
    catalog: Catalog
    registry: Registry
    cwd: Path
    out: IO[str]
    err: IO[str]
    run_settings: Callable[..., Any] | None = None  # tests pass a factory to replace the backoff sleep


def _emit(env: Env, doc: Any) -> None:
    env.out.write(json.dumps(doc, indent=2, sort_keys=False, default=str) + "\n")


def _spec(env: Env, name: str) -> WorkflowSpec:
    if name in VERBS:
        raise UsageError(f"{name!r} is a reserved verb, not a workflow (CLI-B2)")
    if name in env.catalog.broken:
        raise PackageNotLoaded(env.catalog.broken[name])
    if name not in env.catalog.specs:
        raise UsageError(f"unknown workflow {name!r}; `tempergraph list` shows the catalog")
    return env.catalog.specs[name]


def _inputs(pairs: Sequence[str]) -> dict[str, str]:
    out = {}
    for p in pairs:
        k, sep, v = p.partition("=")
        if not sep or not k:
            raise UsageError(f"--input {p!r}: expected key=value")
        out[k] = v
    return out


def _settings(env: Env, a: argparse.Namespace) -> Any:
    from tempergraph.run.runner import RunSettings

    fields = {"judge_override": a.judge_executor, "enforce_tools": a.enforce_tools,
              "strict_permissions": a.strict_permissions, "caller": {"kind": "person", "via": "cli"}}
    if hasattr(a, "alias"):
        fields.update(workspace=a.workspace, alias=a.alias, label=a.label)
    if env.run_settings is not None:
        return env.run_settings(**fields)
    return RunSettings(**fields)


def _report(env: Env, out: Any, as_json: bool) -> int:
    doc = {"schema_version": 1, "exit_code": int(out.exit_code), "reason": out.reason, "thread_id": out.thread_id,
           "message": out.message, "payload": out.payload, "refusals": out.refusals, "warnings": out.warnings}
    if as_json:
        _emit(env, doc)
    line = out.message or out.reason or ExitCode(out.exit_code).name.lower()
    env.err.write(f"{out.thread_id or 'tempergraph'}: {line}\n")
    if out.payload and out.payload.get("resume"):
        env.err.write(f"  {out.payload['resume']}\n")
    return int(out.exit_code)


def cmd_run(env: Env, a: argparse.Namespace) -> int:
    from tempergraph.executors.preflight import preflight
    from tempergraph.run.runner import start

    try:
        spec = _spec(env, a.workflow)
    except PackageNotLoaded as exc:
        if a.check:
            _emit(env, {"schema_version": 1, "status": "broken", "workflow": a.workflow, "reason": exc.reason})
        else:
            env.err.write(f"{a.workflow}: {exc}\n")
        return int(CHECK_EXIT["broken"])
    if a.run_cost_cap is not None:
        if a.run_cost_cap <= 0:
            raise UsageError("--run-cost-cap must be a positive number of USD")
        spec = dataclasses.replace(spec, run_cost_cap_usd=a.run_cost_cap)
    if a.request and a.request[0] in VERBS:
        raise UsageError(f"{a.request[0]!r} is a reserved verb and cannot start a request (CLI-B2)")
    try:
        res = resolve_request(spec, list(a.request), _inputs(a.input), env.cwd, a.task_id)
    except PackageNotLoaded as exc:
        _emit(env, {"schema_version": 1, "status": "broken", "workflow": spec.name, "reason": exc.reason})
        return int(CHECK_EXIT["broken"])
    if a.check or res.status != "ok":
        doc: dict[str, Any] = {"schema_version": 1, "status": res.status, "workflow": spec.name}
        if res.status == "ok":
            settings = _settings(env, a)
            rep = preflight(spec, env.registry, judge_override=settings.judge_override,
                            enforce_tools=settings.enforce_tools, strict_permissions=settings.strict_permissions)
            doc.update(task_id=res.task_id, thread_id=thread_id(spec.name, res.task_id),
                       refusals=[{"code": f.code, "unit": f.unit, "message": f.message} for f in rep.refusals],
                       warnings=[{"code": f.code, "unit": f.unit, "message": f.message} for f in rep.warnings],
                       judges=rep.judges)
            if rep.refusals:
                doc["status"] = "error"
        elif res.status == "needs":
            doc["questions"] = [{"name": q.name, "question": q.question, "choices": list(q.choices or [])}
                                for q in res.questions]
        else:
            doc["message"] = res.message
        _emit(env, doc)
        return int(CHECK_EXIT[doc["status"]])
    out = start(spec, res.task_id, res.inputs, env.cwd, env.registry, _settings(env, a))
    return _report(env, out, a.json)


def cmd_resume(env: Env, a: argparse.Namespace) -> int:
    from tempergraph.run.runner import resume

    spec = _spec(env, a.workflow)
    task = a.thread.split("/", 1)[1] if a.thread.startswith(spec.name + "/") else a.thread
    feedback = a.feedback
    if a.feedback_file:
        path = (env.cwd / a.feedback_file)
        try:
            feedback = path.read_text(encoding="utf-8")
        except OSError as exc:
            raise UsageError(f"--feedback-file {a.feedback_file}: {type(exc).__name__}") from exc
    out = resume(spec, task, env.cwd, env.registry, decision=a.decision, feedback=feedback,
                 settings=_settings(env, a))
    return _report(env, out, a.json)


def _root(env: Env) -> Path:
    from tempergraph.store.layout import NotInRepository, state_root_path

    try:
        return state_root_path(env.cwd)
    except NotInRepository as exc:
        raise UsageError("not inside a git repository") from exc


def _one(env: Env, selector: str) -> tuple[WorkflowSpec, str]:
    from tempergraph.durability.status import Selector, select

    found = select(_root(env), env.catalog.specs, Selector(value=selector))
    if len(found) != 1:
        raise UsageError(f"{selector!r} names {'no' if not found else 'more than one'} thread")
    return found[0]


def cmd_status(env: Env, a: argparse.Namespace) -> int:
    from tempergraph.durability.status import Selector, status

    if a.detail:
        from tempergraph.observe.detail import detail

        if not a.selector:
            raise UsageError("status --detail needs one thread")
        spec, tid = _one(env, a.selector)
        doc = detail(_root(env), spec, tid, unit=a.unit, with_live=not a.no_live)
        if doc is None:
            raise UsageError(f"{a.unit!r} is not a unit of {spec.name}")
        if doc["run"].get("state") == "none":
            raise UsageError(f"{tid}: no such thread")
        _emit(env, doc)
        return 0
    if a.unit:
        raise UsageError("--unit needs --detail")
    _emit(env, status(_root(env), env.catalog.specs, Selector(value=a.selector)))
    return 0


def cmd_events(env: Env, a: argparse.Namespace) -> int:
    from tempergraph.durability.lock import is_held
    from tempergraph.run import events as evmod
    from tempergraph.store.layout import lock_path, run_dir, session_dir

    spec, tid = _one(env, a.selector)
    root, task = _root(env), tid.split("/", 1)[1]
    log = run_dir(root, spec.name, task) / "run.jsonl"
    if not log.exists():
        raise UsageError(f"{tid} has no run log")
    lock = lock_path(root, spec.name, task)

    def held() -> bool:
        return is_held(lock)

    def show(rec: dict[str, Any]) -> None:
        env.out.write((json.dumps(rec, ensure_ascii=False) if a.json else evmod.narrate(rec)) + "\n")
        env.out.flush()

    if a.activity:
        sdir = session_dir(root, spec.name, task, a.activity)
        journal = sdir / "activity.jsonl"
        if not sdir.is_dir():
            raise UsageError(f"{tid} has no session {a.activity!r}")
        lines = (evmod.follow_activity(journal, sdir / "live.json", held, a.since, timeout_s=a.timeout)
                 if a.follow else evmod.activity(journal, a.since))
        for ln in lines:
            env.out.write(json.dumps(ln, ensure_ascii=False) + "\n")
        return 0
    recs = evmod.follow(log, held, a.since, timeout_s=a.timeout) if a.follow else evmod.records(log, a.since)
    for rec in recs:
        show(rec)
    return 0


def cmd_list(env: Env, a: argparse.Namespace) -> int:
    _emit(env, env.catalog.to_json())
    return 0


def cmd_validate(env: Env, a: argparse.Namespace) -> int:
    from tempergraph.executors.preflight import preflight

    spec = _spec(env, a.workflow)
    rep = preflight(spec, env.registry)
    doc = {"schema_version": 1, "workflow": spec.name, "ok": rep.ok,
           "findings": [{"severity": "error", "code": f.code, "unit": f.unit, "message": f.message}
                        for f in rep.refusals]
           + [{"severity": "warning", "code": f.code, "unit": f.unit, "message": f.message} for f in rep.warnings],
           "deferred_views": {u: [dataclasses.asdict(d) for d in ds] for u, ds in rep.deferred.items()}}
    _emit(env, doc)
    return 0 if rep.ok else int(ExitCode.USAGE)


def cmd_executors(env: Env, a: argparse.Namespace) -> int:
    rows = []
    for name in env.registry.available():
        ex = env.registry.get(name)
        caps = ex.capabilities()
        row: dict[str, Any] = {"name": name, "capabilities": dataclasses.asdict(caps)}
        facts = getattr(ex, "live_facts", None)  # live probe facts and their recorded state (CLI-B3)
        if isinstance(facts, dict):
            row["live_facts"] = dict(facts)
        if a.probe:
            pr = ex.probe()
            row["probe"] = {"ok": pr.ok, "reason": pr.reason, "version": pr.version, "path": pr.path,
                            "facts": dict(pr.facts)}
        rows.append(row)
    _emit(env, {"schema_version": 1, "executors": rows})
    return 0


def cmd_facts(env: Env, a: argparse.Namespace) -> int:
    from tempergraph.durability.status import row

    spec, tid = _one(env, a.selector)
    r = row(_root(env), spec, tid)
    keep = ("thread_id", "workflow", "state", "alive", "pending_gates", "workspace", "alias", "label", "origin",
            "exit_code", "exit_reason", "cost", "artifacts", "next")
    _emit(env, {"schema_version": SCHEMA["status"], **{k: r[k] for k in keep if k in r}})
    return 0


def cmd_graph(env: Env, a: argparse.Namespace) -> int:
    from tempergraph.model.diagram import diagram_model, to_mermaid

    model = diagram_model(_spec(env, a.workflow))
    if a.format == "json":
        _emit(env, model)
    else:
        text = to_mermaid(model)
        env.out.write(f"```mermaid\n{text}\n```\n" if a.format == "md" else text + "\n")
    return 0


def cmd_wait(env: Env, a: argparse.Namespace) -> int:
    from tempergraph.durability.status import wait

    if a.timeout <= 0:
        raise UsageError("--timeout must be positive")
    spec, tid = _one(env, a.selector)
    w = wait(_root(env), spec, tid, a.timeout)
    _emit(env, {"schema_version": 1, "state": w.state, "exit_code": int(w.exit_code), "reason": w.reason,
                "row": w.row})
    return int(w.exit_code)


def cmd_stop(env: Env, a: argparse.Namespace) -> int:
    from tempergraph.durability.control import NotLive, request_stop

    spec, tid = _one(env, a.selector)
    try:
        mode = request_stop(_root(env), spec.name, tid.split("/", 1)[1], "now" if a.now else "drain",
                            caller={"kind": "person", "via": "cli"})
    except NotLive as exc:
        raise UsageError(str(exc)) from exc
    _emit(env, {"schema_version": 1, "thread_id": tid, "mode": mode})
    return 0


def cmd_worktree(env: Env, a: argparse.Namespace) -> int:
    from tempergraph.workspace import list_worktrees, worktree_path

    if a.action == "list":
        _emit(env, {"schema_version": 1, "worktrees": list_worktrees(env.cwd)})
        return 0
    if a.action == "path":
        p = worktree_path(env.cwd, a.thread)
        if p is None:
            raise UsageError(f"no run worktree for {a.thread}")
        env.out.write(f"{p}\n")
        return 0
    raise UsageError("worktree needs list or path")


COMMANDS: dict[str, Callable[[Env, argparse.Namespace], int]] = {
    "run": cmd_run, "resume": cmd_resume, "status": cmd_status, "list": cmd_list, "validate": cmd_validate,
    "executors": cmd_executors, "events": cmd_events, "facts": cmd_facts, "graph": cmd_graph, "wait": cmd_wait, "stop": cmd_stop,
    "worktree": cmd_worktree, **observe_cli.COMMANDS,
}


def main(argv: Sequence[str] | None = None, *, catalog: Catalog | None = None, registry: Registry | None = None,
         cwd: Path | None = None, out: IO[str] | None = None, err: IO[str] | None = None,
         run_settings: Callable[..., Any] | None = None) -> int:
    out, err = out or sys.stdout, err or sys.stderr
    try:
        a = _parser().parse_args(list(argv if argv is not None else sys.argv[1:]))
        if not a.verb:
            raise UsageError("a verb is needed; `tempergraph --help` lists them")
        if a.verb not in COMMANDS:
            raise UsageError(f"{a.verb}: not in this release")
        env = Env(catalog=catalog if catalog is not None else from_registry(),
                  registry=registry if registry is not None else default_registry(),
                  cwd=(cwd or Path.cwd()).resolve(), out=out, err=err, run_settings=run_settings)
        return COMMANDS[a.verb](env, a)
    except UsageError as exc:
        err.write(f"tempergraph: {exc}\n")
        return int(ExitCode.USAGE)
    except PackageNotLoaded as exc:
        err.write(f"tempergraph: {exc}\n")
        return int(ExitCode.INTERNAL)
    except SystemExit as exc:  # --help
        return int(exc.code or 0) if isinstance(exc.code, int) else 0
    except Exception as exc:  # noqa: BLE001 - CLI §4: exit 1 after an engine-error record
        _engine_error(exc)
        err.write(f"tempergraph: internal error ({type(exc).__name__})\n")
        return int(ExitCode.INTERNAL)


def _engine_error(exc: BaseException) -> None:
    """The engine-error record in the engine code log (LOS §2.3); best effort (contract C2)."""
    try:
        logging.getLogger("tempergraph").error("engine_error", exc_info=exc)
    except Exception:  # noqa: BLE001
        traceback.print_exception(exc, file=sys.stderr)


def entry() -> None:
    raise SystemExit(main())
