"""The engine CLI's release 1 core verbs (CLI §2, §4; milestone M1).

Exit codes are the caller contract (CON §2.9, ADR-0015). Read-only verbs create nothing and call no model
(contract C13). Machine output is JSON with `schema_version`; a run's one-line outcome goes to stderr.
"""

from __future__ import annotations

import argparse
import dataclasses
import json
import logging
import os
import sys
import traceback
from collections.abc import Callable, Mapping, Sequence
from pathlib import Path
from typing import IO, Any

from tempergraph import executor_compat
from tempergraph.catalog import Catalog, PackageNotLoaded, from_registry, resolve_request
from tempergraph.cli import audit as audit_cli
from tempergraph.cli import author as author_cli
from tempergraph.cli import install as install_cli
from tempergraph.cli import observe_cli
from tempergraph.cli import upgrade as upgrade_cli
from tempergraph.cli import workflows as workflows_cli
from tempergraph.constants import SCHEMA, ExitCode
from tempergraph.contracts import WorkflowSpec, thread_id
from tempergraph.executors.registry import Registry, default_registry

# Every verb word of CLI §2, reserved so it is never read as a workflow or a request (CLI-B2, AC-3).
VERBS = ("attention", "audit", "author", "batch", "blueprint", "carry", "config", "evals", "events", "executors", "facts",
         "graph", "hooks", "improve", "install", "label", "labels", "list", "literals", "logs", "orchestrate",
         "outcome", "promote-check", "report", "rerun", "resume", "run", "scaffold", "schedule", "self-check",
         "stats", "status", "stop", "store", "supervision", "update", "upgrade", "upgrade-check", "validate", "wait",
         "workflows", "worktree", "help")
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
    res.add_argument("--escalate", action="store_true",
                     help="take the offered one-step model escalation for the next attempt (LAD §2.4)")
    fb = res.add_mutually_exclusive_group()
    fb.add_argument("--feedback")
    fb.add_argument("--feedback-file")
    res.add_argument("--ruling", action="store_true", help="the feedback is a lasting ruling (RRN §2.2)")
    res.add_argument("--ruling-for", metavar="UNITS", help="comma-separated units the ruling applies to")
    res.add_argument("--revoke-ruling", action="append", default=[], metavar="ID")
    res.add_argument("--accept-external", action="store_true")
    _run_options(res, start=False)

    rr = sub.add_parser("rerun", help="a new thread forked from an earlier one, linked to it (RRN §2.4)")
    rr.add_argument("workflow")
    rr.add_argument("thread")
    rr.add_argument("--from", dest="start_at", required=True, metavar="UNIT|start")
    rr.add_argument("--check", action="store_true")
    rfb = rr.add_mutually_exclusive_group()
    rfb.add_argument("--feedback")
    rfb.add_argument("--feedback-file")
    rr.add_argument("--task-id")
    rr.add_argument("--workspace", dest="rerun_workspace", choices=("current", "at-unit"), default="current")
    rr.add_argument("--same-branch", action="store_true")
    rr.add_argument("--drop-rulings", action="store_true")
    rr.add_argument("--ruling", action="store_true")
    rr.add_argument("--accept-external", action="store_true")
    _spellings(rr)
    _caller_options(rr)
    rr.add_argument("--json", action="store_true")
    _settings_options(rr, resume=True)
    st = sub.add_parser("status", help="the status document, or one thread's detail document")
    st.add_argument("selector", nargs="?")
    st.add_argument("--detail", action="store_true", help="the run detail document of one thread (RDD)")
    st.add_argument("--unit", help="with --detail: one unit in full")
    st.add_argument("--no-live", action="store_true", help="with --detail: leave out the live session blocks")
    st.add_argument("--json", action="store_true", help="machine output (the default for status)")
    st.add_argument("--all-roots", action="store_true", help="every state root of the machine index (CST §2.1)")
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
    gr.add_argument("--overlay", metavar="THREAD", help="a thread's counts on the diagram (OBS §2.4); read-only")
    wa = sub.add_parser("wait", help="block until a thread's outcome")
    wa.add_argument("selector")
    wa.add_argument("--timeout", type=float, default=3600.0)
    so = sub.add_parser("stop", help="ask a live run to stop")
    so.add_argument("selector")
    so.add_argument("--now", action="store_true", help="stop the open session now instead of draining")
    _caller_options(so)
    wt = sub.add_parser("worktree", help="run worktrees")
    wsub = wt.add_subparsers(dest="action", parser_class=_Parser)
    wsub.add_parser("list")
    wp = wsub.add_parser("path")
    wp.add_argument("thread")
    observe_cli.add_parsers(sub)
    co = sub.add_parser("config", help="resolved run settings and the settings files (RST §2.9)")
    csub = co.add_subparsers(dest="action", parser_class=_Parser)
    cs = csub.add_parser("show")
    cs.add_argument("workflow")
    cs.add_argument("--thread")
    cs.add_argument("--key", help="a glob over the keys shown")
    _spellings(cs)
    _settings_options(cs)
    cs.add_argument("--json", action="store_true")
    cv = csub.add_parser("validate")
    cv.add_argument("--file")
    csub.add_parser("paths")
    workflows_cli.add_parsers(sub)
    audit_cli.add_parsers(sub)
    author_cli.add_parsers(sub)
    install_cli.add_parsers(sub)
    upgrade_cli.add_parsers(sub)
    from tempergraph.cli import outcome as outcome_cli

    outcome_cli.add_parser(sub, _Parser)
    from tempergraph.cli import improve as improve_cli

    improve_cli.add_parsers(sub, _Parser)
    return p


def _settings_options(p: argparse.ArgumentParser, resume: bool = False) -> None:
    p.add_argument("--set", action="append", default=[], metavar="KEY=VALUE", dest="set_")
    p.add_argument("--settings", metavar="FILE", help="a JSON map of keys to values, recorded as flags")
    p.add_argument("--profile", action="append", default=None)
    if resume:
        p.add_argument("--unset", action="append", default=[], metavar="KEY")
        p.add_argument("--reload-settings", action="store_true")


# Named run options that are spellings of `--set` (CLI §2.1): option dest -> key, or a `<unit>=<value>` pair.
SPELLINGS = {"executor": "steps.executor", "judge_executor": "judges.executor", "model": "steps.model",
             "judge_model": "judges.model", "timeout": "steps.timeout_s", "judge_timeout": "judges.timeout_s",
             "idle": "steps.idle_s", "run_cost_cap": "run.run_cost_cap_usd", "worktree_root": "run.worktree.root",
             "worktree_base": "run.worktree.base", "worktree_cleanup": "run.worktree.cleanup",
             "auto_reopen": "run.auto_reopen", "daily_cap": "run.daily_cap_usd"}
PER_UNIT = {"step_executor": "executor", "step_model": "model"}


def _caller_options(p: argparse.ArgumentParser) -> None:
    """PRV §2.6: run options, never settings; each call is classified on its own."""
    p.add_argument("--caller", choices=("person", "agent", "pipeline", "orchestrator", "scheduler", "engine"))
    p.add_argument("--as-agent", action="store_true")
    p.add_argument("--caller-app")
    p.add_argument("--relayed", action="store_true")


def _spellings(p: argparse.ArgumentParser) -> None:
    for opt in ("executor", "judge-executor", "model", "judge-model", "timeout", "judge-timeout", "idle",
                "run-cost-cap", "daily-cap", "auto-reopen"):
        p.add_argument(f"--{opt}")
    p.add_argument("--step-executor", action="append", default=[], metavar="STEP=NAME")
    p.add_argument("--step-model", action="append", default=[], metavar="STEP=ALIAS")
    p.add_argument("--approve", action="append", default=[], metavar="STEP")
    p.add_argument("--grant", action="append", default=[], metavar="UNIT=CAPABILITY[,…]")
    p.add_argument("--allow-command", action="append", default=[], metavar="UNIT=PREFIX")
    p.add_argument("--enforce-tools", action="store_true")
    p.add_argument("--strict-permissions", action="store_true")


def _run_options(p: argparse.ArgumentParser, start: bool = True) -> None:
    _spellings(p)
    _caller_options(p)
    p.add_argument("--json", action="store_true")
    _settings_options(p, resume=not start)
    p.add_argument("--pause-before", action="append", default=[], metavar="UNIT")
    if start:
        p.add_argument("--dry-run", action="store_true", help="self-improvement files nothing; every step runs")
        p.add_argument("--alias")
        p.add_argument("--label")
        for opt in ("worktree-root", "worktree-base", "worktree-cleanup"):
            p.add_argument(f"--{opt}")
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
    signals: tuple[Mapping[str, str], bool] | None = None  # (environment, terminal); tests stub them (PRV-AC-1)

    def caller(self, a: argparse.Namespace) -> dict[str, Any]:
        """PRV §2.3, once per mutating call, before any write; read-only verbs never call this."""
        from tempergraph.provenance import CallerRefused, classify

        env, tty = self.signals or (os.environ, sys.stdin.isatty() and sys.stdout.isatty())
        declared = getattr(a, "caller", None) or ("agent" if getattr(a, "as_agent", False) else None)
        try:
            return classify(env, tty, declared=declared, caller_app=getattr(a, "caller_app", None))
        except CallerRefused as exc:
            raise UsageError(f"{exc.code}: {exc}") from exc


def _emit(env: Env, doc: Any) -> None:
    env.out.write(json.dumps(doc, indent=2, sort_keys=False, default=str) + "\n")


def _spec(env: Env, name: str) -> WorkflowSpec:
    if name in VERBS:
        raise UsageError(f"{name!r} is a reserved verb, not a workflow (CLI-B2)")
    if name not in env.catalog.specs and name not in env.catalog.broken:
        from tempergraph.package.manifest import workflow_name

        name = workflow_name(name)  # the plugin name `<workflow>-tgraph` names the same workflow (ADR-0120)
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


def _flags(env: Env, a: argparse.Namespace) -> dict[str, Any]:
    """`--settings`, then `--set`, then the named spellings: every one lands on the flag layer (RST §2.3)."""
    from tempergraph.settings import parse_value

    flags: dict[str, Any] = {}
    if getattr(a, "settings", None):
        try:
            doc = json.loads((env.cwd / a.settings).read_text(encoding="utf-8"))
        except (OSError, ValueError) as exc:
            raise UsageError(f"--settings {a.settings}: {type(exc).__name__}") from exc
        if not isinstance(doc, dict):
            raise UsageError(f"--settings {a.settings}: not a JSON object of keys to values")
        flags.update(doc)
    for pair in getattr(a, "set_", None) or []:
        k, sep, v = pair.partition("=")
        if not sep or not k:
            raise UsageError(f"--set {pair!r}: expected key=value")
        flags[k] = parse_value(v)
    for dest, key in SPELLINGS.items():
        v = getattr(a, dest, None)
        if v is not None:
            flags[key] = parse_value(v)
    for dest, name in PER_UNIT.items():
        for pair in getattr(a, dest, None) or []:
            unit, sep, v = pair.partition("=")
            if not sep or not unit:
                raise UsageError(f"--{dest.replace('_', '-')} {pair!r}: expected <step>=<value>")
            flags[f"{unit}.{name}"] = parse_value(v)
    for unit in getattr(a, "approve", None) or []:
        flags[f"{unit}.approve"] = True
    for opt, pairs in (("grant", getattr(a, "grant", None)), ("allow-command", getattr(a, "allow_command", None))):
        for pair in pairs or []:  # a person's tool grant for this run (RST §2.8)
            unit, sep, v = pair.partition("=")
            if not sep or not unit or not v:
                raise UsageError(f"--{opt} {pair!r}: expected <unit>=<value>")
            if opt == "allow-command":
                key, items = f"{unit}.commands.add", [v]
            else:
                key = f"{unit}.views.add" if unit.startswith("judge:") else f"{unit}.tools.add"
                items = [c.strip() for c in v.split(",") if c.strip()]
            flags[key] = list(dict.fromkeys(list(flags.get(key) or []) + items))
    if getattr(a, "workspace", None):
        flags["run.workspace"] = a.workspace
    if getattr(a, "enforce_tools", False):
        flags["run.enforce_tools"] = True
    if getattr(a, "strict_permissions", False):
        flags["run.strict_permissions"] = True
    return flags


def _settings(env: Env, a: argparse.Namespace, mutating: bool = True) -> Any:
    from tempergraph.run.runner import RunSettings

    if getattr(a, "pause_before", None):  # FLX §2.5 breakpoints are release 2 (X2-13)
        raise UsageError("not_in_release: --pause-before is a release 2 option (FLX §2.5)")
    fields: dict[str, Any] = {"flags": _flags(env, a), "caller": env.caller(a) if mutating else {},
                              "relayed": bool(getattr(a, "relayed", False)),
                              "profiles": tuple(a.profile) if getattr(a, "profile", None) is not None else None}
    if hasattr(a, "alias"):
        fields.update(alias=a.alias, label=a.label, dry_run=bool(getattr(a, "dry_run", False)))
    if getattr(a, "escalate", False):
        fields["escalate"] = True
    if hasattr(a, "unset"):
        fields.update(unset=tuple(a.unset), reload_settings=a.reload_settings)
    if hasattr(a, "ruling"):
        if getattr(a, "ruling_for", None) and not a.ruling:
            raise UsageError("--ruling-for needs --ruling")
        fields.update(ruling=a.ruling, revoke_rulings=tuple(getattr(a, "revoke_ruling", None) or ()),
                      accept_external=bool(getattr(a, "accept_external", False)),
                      ruling_for=tuple(u.strip() for u in (getattr(a, "ruling_for", None) or "").split(",")
                                       if u.strip()))
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
    from tempergraph.run.runner import SettingsRefused, settle_start, start

    try:
        spec = _spec(env, a.workflow)
    except PackageNotLoaded as exc:
        if a.check:
            _emit(env, {"schema_version": 1, "status": "broken", "workflow": a.workflow, "reason": exc.reason})
        else:
            env.err.write(f"{a.workflow}: {exc}\n")
        return int(CHECK_EXIT["broken"])
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
            doc.update(task_id=res.task_id, thread_id=thread_id(spec.name, res.task_id))
            try:
                settled = settle_start(spec, _settings(env, a, mutating=False), _root_or_none(env))
            except SettingsRefused as exc:  # the same refusals `run` gives (CLI-AC-2, RST-B9)
                doc.update(status="error", refusals=[{"code": f.code, "unit": f.unit, "message": f.message}
                                                     for f in exc.findings], warnings=[])
                _emit(env, doc)
                return int(CHECK_EXIT["error"])
            rv = settled.run
            rep = preflight(settled.spec, env.registry, enforce_tools=bool(rv["enforce_tools"]),
                            strict_permissions=bool(rv["strict_permissions"]))
            doc.update(refusals=[{"code": f.code, "unit": f.unit, "message": f.message} for f in rep.refusals],
                       warnings=[{"code": f.code, "unit": f.unit, "message": f.message} for f in rep.warnings],
                       judges=rep.judges, settings_digest=settled.resolved.digest)
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


def _feedback_text(env: Env, a: argparse.Namespace) -> str | None:
    if getattr(a, "feedback_file", None):
        try:
            return (env.cwd / a.feedback_file).read_text(encoding="utf-8")
        except OSError as exc:
            raise UsageError(f"--feedback-file {a.feedback_file}: {type(exc).__name__}") from exc
    return getattr(a, "feedback", None)


def cmd_rerun(env: Env, a: argparse.Namespace) -> int:
    from tempergraph.run.rerun import rerun

    spec = _spec(env, a.workflow)
    task = a.thread.split("/", 1)[1] if a.thread.startswith(spec.name + "/") else a.thread
    out = rerun(spec, task, env.cwd, env.registry, start_at=a.start_at, feedback=_feedback_text(env, a),
                settings=_settings(env, a, mutating=not a.check), task_id=a.task_id, workspace_from=a.rerun_workspace,
                same_branch=a.same_branch, drop_rulings=a.drop_rulings, accept_external=a.accept_external,
                check=a.check)
    if isinstance(out, dict):
        _emit(env, out)
        return 0
    if a.check:  # `rerun --check` refuses as `rerun` does, and prints one document (RRN-AC-4)
        _emit(env, {"schema_version": 1, "status": "error", "reason": out.reason, "message": out.message,
                    "refusals": out.refusals or [out.message]})
        return int(out.exit_code)
    return _report(env, out, a.json)


def _root(env: Env) -> Path:
    from tempergraph.store.layout import NotInRepository, state_root_path

    try:
        return state_root_path(env.cwd)
    except NotInRepository as exc:
        raise UsageError("not inside a git repository") from exc


def _root_or_none(env: Env) -> Path | None:
    from tempergraph.store.layout import NotInRepository, state_root_path

    try:
        return state_root_path(env.cwd)
    except NotInRepository:
        return None


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
    if a.all_roots:
        from tempergraph.observe.rows import index_roots

        doc = status(_root(env), env.catalog.specs, Selector(value=a.selector))
        here = str(_root(env).resolve())
        for r in doc["threads"]:
            r["state_root"] = here
        doc["roots"] = [{"path": here, "missing": False}]
        for entry in index_roots():
            if entry["path"] == here:
                continue
            doc["roots"].append({"path": entry["path"], "missing": entry["missing"]})
            if entry["missing"]:
                continue
            for r in status(Path(entry["path"]), env.catalog.specs, Selector(value=a.selector))["threads"]:
                doc["threads"].append({**r, "state_root": entry["path"]})
        _emit(env, doc)
        return 0
    doc = status(_root(env), env.catalog.specs, Selector(value=a.selector))
    from tempergraph.observe.sinks import warnings
    from tempergraph.store.layout import home_path

    lines = warnings(home_path())
    if lines:
        doc["warnings"] = lines  # CST §2.3: a sink failing for 7 days
    _emit(env, doc)
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
        row["compat"] = executor_compat.row(name, row["probe"]["version"] if a.probe else caps.version)  # LIF-AC-4
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
    if a.overlay:
        from tempergraph.durability.status import split_thread
        from tempergraph.observe.overlay import overlay
        from tempergraph.store.layout import run_dir

        spec, tid = _one(env, a.overlay)
        if spec.name != a.workflow:
            raise UsageError(f"{tid} is a run of {spec.name!r}, not of {a.workflow!r}")
        if not (run_dir(_root(env), spec.name, split_thread(tid)[1]) / "run.jsonl").exists():
            raise UsageError(f"{tid} has no run log to overlay")
        model["overlay"] = overlay(_root(env), spec.name, split_thread(tid)[1])
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
                            caller=_stop_caller(env, a))
    except NotLive as exc:
        raise UsageError(str(exc)) from exc
    _emit(env, {"schema_version": 1, "thread_id": tid, "mode": mode})
    return 0


def _stop_caller(env: Env, a: argparse.Namespace) -> dict[str, Any]:
    from tempergraph.provenance import decide
    from tempergraph.store.layout import home_path

    return decide(env.caller(a), relayed=bool(getattr(a, "relayed", False)), words=("stop",), home=home_path())


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


def cmd_config(env: Env, a: argparse.Namespace) -> int:
    """RST §2.9: read-only, model-free; `show` calls the same resolver a start or resume does (RST-B9)."""
    import fnmatch

    from tempergraph import settings as rst
    from tempergraph.store.layout import home_path

    root = _root_or_none(env)
    if a.action == "paths":
        pp, up = rst.config_paths(root, home_path())
        _emit(env, {"schema_version": 1, "files": [{"layer": "project", "path": str(pp) if pp else None,
                                                    "exists": bool(pp and pp.exists())},
                                                   {"layer": "user", "path": str(up), "exists": up.exists()}]})
        return 0
    if a.action == "validate":
        return _config_validate(env, a, root)
    if a.action != "show":
        raise UsageError("config needs show, validate or paths")
    from tempergraph.run.runner import SettingsRefused, settle_resume, settle_start

    spec = _spec(env, a.workflow)
    settings = _settings(env, a, mutating=False)
    findings: list[Any] = []
    try:
        if a.thread:
            from tempergraph.durability.checkpoint import thread_values
            from tempergraph.store.layout import checkpoint_path

            if root is None:
                raise UsageError("--thread needs a git repository")
            task = a.thread.split("/", 1)[1] if "/" in a.thread else a.thread
            values = thread_values(checkpoint_path(root, spec.name), spec, thread_id(spec.name, task))
            if not values:
                raise UsageError(f"no thread {thread_id(spec.name, task)}")
            settled = settle_resume(spec, settings, root, values)
        else:
            settled = settle_start(spec, settings, root)
        rows = rst.rows_json(settled.resolved)
        digest = settled.resolved.digest
    except SettingsRefused as exc:
        findings, rows, digest = exc.findings, [], None
    if a.key:
        rows = [r for r in rows if fnmatch.fnmatch(r["key"], a.key)]
    _emit(env, {"schema_version": 1, "workflow": spec.name, "settings_digest": digest, "rows": rows,
                "findings": [{"code": f.code, "message": f.message} for f in findings]})
    return int(ExitCode.USAGE) if findings else 0


def _config_validate(env: Env, a: argparse.Namespace, root: Path | None) -> int:
    from tempergraph import settings as rst
    from tempergraph.store.layout import home_path

    if a.file:
        p = (env.cwd / a.file).resolve()
        files = rst.ConfigFiles()
        try:
            doc = json.loads(p.read_text(encoding="utf-8"))
            files = dataclasses.replace(files, user=doc if isinstance(doc, dict) and doc.get("schema_version") == 1
                                        else None, user_path=p)
            errs = [] if files.user is not None else [{"code": "config_file", "message": f"{p}: not schema 1"}]
        except (OSError, ValueError) as exc:
            errs = [{"code": "config_file", "message": f"{p}: {exc}"}]
    else:
        files = rst.load_files(root, home_path())
        errs = [{"code": f.code, "message": f.message} for f in files.errors]
    named = {str(e.get("workflow")) for doc in (files.project, files.user) if doc
             for e in (doc.get("overrides") or []) if isinstance(e, dict)}
    for name, spec in env.catalog.specs.items():  # defaults reach every workflow, so every one is checked
        _, found = rst.options_snapshot(spec, {}, (), dataclasses.replace(files, errors=()))
        errs += [{"code": f.code, "workflow": name, "message": f.message} for f in found]
    for wf in sorted(named - set(env.catalog.specs) - {"*"}):
        errs.append({"code": "unknown_workflow", "workflow": wf, "message": f"no registered workflow {wf!r}"})
    _emit(env, {"schema_version": 1, "ok": not errs, "findings": errs})
    return int(ExitCode.USAGE) if errs else 0


def cmd_outcome(env: Env, a: argparse.Namespace) -> int:
    from tempergraph.cli.outcome import cmd_outcome as run_outcome

    return run_outcome(env, a)


COMMANDS: dict[str, Callable[[Env, argparse.Namespace], int]] = {
    "run": cmd_run, "resume": cmd_resume, "status": cmd_status, "list": cmd_list, "validate": cmd_validate,
    "executors": cmd_executors, "events": cmd_events, "facts": cmd_facts, "graph": cmd_graph, "wait": cmd_wait,
    "stop": cmd_stop, "worktree": cmd_worktree, "config": cmd_config, "rerun": cmd_rerun, "outcome": cmd_outcome,
    **observe_cli.COMMANDS,
    "workflows": workflows_cli.cmd_workflows,
    "audit": audit_cli.cmd_audit,
    "blueprint": author_cli.cmd_blueprint,
    "literals": author_cli.cmd_literals,
    "scaffold": author_cli.cmd_scaffold,
    "author": author_cli.cmd_author,
    "install": install_cli.cmd_install,
    "upgrade": upgrade_cli.cmd_upgrade,
    "upgrade-check": upgrade_cli.cmd_upgrade,
    "evals": lambda env, a: _improve().cmd_evals(env, a),
    "labels": lambda env, a: _improve().cmd_labels(env, a),
    "improve": lambda env, a: _improve().cmd_improve(env, a),
    "promote-check": lambda env, a: _improve().cmd_promote_check(env, a),
}


def _improve() -> Any:
    from tempergraph.cli import improve

    return improve


def main(argv: Sequence[str] | None = None, *, catalog: Catalog | None = None, registry: Registry | None = None,
         cwd: Path | None = None, out: IO[str] | None = None, err: IO[str] | None = None,
         run_settings: Callable[..., Any] | None = None, signals: tuple[Mapping[str, str], bool] | None = None
         ) -> int:
    out, err = out or sys.stdout, err or sys.stderr
    try:
        a = _parser().parse_args(list(argv if argv is not None else sys.argv[1:]))
        if not a.verb:
            raise UsageError("a verb is needed; `tempergraph --help` lists them")
        if a.verb not in COMMANDS:
            raise UsageError(f"{a.verb}: not in this release")
        light = a.verb == "supervision" and getattr(a, "action", None) in ("hook", "log", "close")
        env = Env(catalog=catalog if catalog is not None else Catalog() if light else from_registry(),
                  registry=registry if registry is not None else default_registry(),
                  cwd=(cwd or Path.cwd()).resolve(), out=out, err=err, run_settings=run_settings,
                  signals=signals)
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
