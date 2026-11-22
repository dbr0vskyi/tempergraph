"""`tempergraph schedule` (SCH-B1, SCH-B8, SCH-B10, SCH-B12, SCH-B13, SCH-B22, SCH-B24, SCH-B25, SCH-B27, SCH-B33).

Release 3, phase R3-T5.1: `parse`, `add` (a workflow target), `list`, `show`, `history`, `edit`, `pause`, `resume`,
`skip` and `remove`. `parse`, `list`, `show` and `history` write nothing and start no process. `fire`, `tick`, `loop`,
`trigger`, `runs` and `export`, and `add --orchestration`, are refused `not_in_release` (SCH-B33); the tick, the fire
token and the credential check come with TCK (R3-T5.2). Every refusal exits 2 with its reason code and writes nothing;
a `needs` (an ambiguous phrase, a confirmation, a missing request) exits 3 with the choices as JSON on stdout.
"""

from __future__ import annotations

import argparse
import json
import sys
from datetime import UTC, date, datetime, time, timedelta
from pathlib import Path
from typing import Any

from tempergraph.constants import ExitCode
from tempergraph.schedule import policies, store
from tempergraph.schedule.echo import Echo, build_echo
from tempergraph.schedule.exact import ISO_MINUTE, Parsed, build_recur, parse_exact, parse_wall, with_bounds
from tempergraph.schedule.model import (
    Clock,
    Needs,
    ScheduleError,
    When,
    floor_minute,
    machine_zone,
    next_slots,
    parse_rule,
    slots_between,
    system_clock,
    wall_to_utc,
    zone_of,
)
from tempergraph.schedule.words import parse_words
from tempergraph.security.scrub import scrub

CLOCK: Clock = system_clock  # tests replace it: the pure modules take the clock, only this module reads it
NOT_IN_RELEASE = ("fire", "tick", "loop", "trigger", "runs", "export")
CATCH_UP = ("latest", "none", "all")
OVERLAP = ("skip", "queue", "parallel")
SCHEMA = 1


class _Stop(Exception):
    """End the verb with a document on stdout and an exit code (a `needs` or a check's own refusal)."""

    def __init__(self, code: int, doc: dict[str, Any]) -> None:
        super().__init__(str(doc.get("status")))
        self.code, self.doc = code, doc


def add_parsers(sub: Any) -> None:
    from tempergraph.cli.main import WORKSPACES, _caller_options, _settings_options, _spellings

    p = sub.add_parser("schedule", help="schedule a workflow once or on a recurrence (SCH)")
    s = p.add_subparsers(dest="action", parser_class=type(p))

    def timing(q: argparse.ArgumentParser) -> None:
        q.add_argument("--when", help="a phrase such as 'every weekday at 8:00'")
        q.add_argument("--at", help="ISO 8601 local, or with an offset or Z: once")
        q.add_argument("--rrule", help="an RFC 5545 RECUR of the stored subset")
        q.add_argument("--every", help="an ISO 8601 duration of at least PT15M")
        q.add_argument("--cron", help="five fields, read in the schedule's zone")
        q.add_argument("--tz", help="an IANA zone name")
        q.add_argument("--starts")
        q.add_argument("--until")
        q.add_argument("--count", type=int)
        q.add_argument("--choose", type=int, help="the reading of an ambiguous phrase")

    def run_options(q: argparse.ArgumentParser) -> None:
        _spellings(q)
        _settings_options(q)
        ws = q.add_mutually_exclusive_group()
        ws.add_argument("--workspace", choices=WORKSPACES)
        ws.add_argument("--worktree", dest="workspace", action="store_const", const="worktree")
        ws.add_argument("--in-place", dest="workspace", action="store_const", const="in_place")

    def policy(q: argparse.ArgumentParser) -> None:
        q.add_argument("--budget", metavar="PERIOD:USD", help="day, week or month, and the cap over that period")
        q.add_argument("--catch-up", dest="catch_up", choices=CATCH_UP)
        q.add_argument("--overlap", choices=OVERLAP)
        q.add_argument("--max-live", dest="max_live", type=int)
        q.add_argument("--pause-after-failures", dest="pause_after_failures", type=int)

    pa = s.add_parser("parse", help="the echo of a timing, or its question or refusal; writes nothing")
    pa.add_argument("phrase", nargs="?", help="a phrase (or use --when or an exact format)")
    timing(pa)
    pa.add_argument("--json", action="store_true")

    ad = s.add_parser("add", help="schedule a workflow")
    ad.add_argument("workflow", nargs="?")
    ad.add_argument("request", nargs="*")
    timing(ad)
    run_options(ad)
    policy(ad)
    ad.add_argument("--name")
    ad.add_argument("--input", action="append", default=[], metavar="K=V")
    ad.add_argument("--orchestration", metavar="FILE", help="not in this release")
    ad.add_argument("--arg", action="append", default=[], metavar="K=V")
    ad.add_argument("--program", nargs="?", const="*", help="reserved")
    ad.add_argument("--check", action="store_true", help="parse and check; save nothing")
    ad.add_argument("--yes", action="store_true")
    ad.add_argument("--json", action="store_true")
    _caller_options(ad)

    ls = s.add_parser("list", help="every schedule on this machine")
    ls.add_argument("--all", action="store_true", dest="show_all")
    ls.add_argument("--json", action="store_true")
    sh = s.add_parser("show", help="one schedule: entry, echo, next ten slots, last 20 fires")
    sh.add_argument("id")
    sh.add_argument("--json", action="store_true")
    hi = s.add_parser("history", help="a schedule's fire log")
    hi.add_argument("id")
    hi.add_argument("--since", metavar="DATE")
    hi.add_argument("--json", action="store_true")

    ed = s.add_parser("edit", help="change a schedule's timing or options (its target is fixed)")
    ed.add_argument("id")
    ed.add_argument("phrase", nargs="?")
    timing(ed)
    run_options(ed)
    policy(ed)
    ed.add_argument("--workflow")
    ed.add_argument("--repo")
    ed.add_argument("--orchestration")
    ed.add_argument("--program", nargs="?", const="*")
    ed.add_argument("--yes", action="store_true")
    ed.add_argument("--json", action="store_true")
    _caller_options(ed)

    pu = s.add_parser("pause", help="stop firing a schedule")
    pu.add_argument("id")
    pu.add_argument("--reason")
    pu.add_argument("--json", action="store_true")
    _caller_options(pu)
    re_ = s.add_parser("resume", help="start a paused schedule again")
    re_.add_argument("id")
    re_.add_argument("--catch-up", dest="catch_up", action="store_true", help="the slots passed while paused may still fire")
    re_.add_argument("--json", action="store_true")
    _caller_options(re_)
    sk = s.add_parser("skip", help="skip the next slot, or every slot until a date")
    sk.add_argument("id")
    sk.add_argument("--next", action="store_true", dest="next_")
    sk.add_argument("--until", metavar="DATE")
    sk.add_argument("--json", action="store_true")
    _caller_options(sk)
    rm = s.add_parser("remove", help="remove a schedule; its history stays")
    rm.add_argument("id")
    rm.add_argument("--yes", action="store_true")
    rm.add_argument("--json", action="store_true")
    _caller_options(rm)

    for verb in NOT_IN_RELEASE:  # SCH-B33: parsed so that the refusal can name the verb, whatever follows it
        q = s.add_parser(verb, help="not in this release (R3-T5.2)")
        q.add_argument("rest", nargs="*")
        for flag in ("--detach", "--stop", "--yes", "--json", "--all"):
            q.add_argument(flag, action="store_true")
        for option in ("--for", "--since"):
            q.add_argument(option)


# --- output ------------------------------------------------------------------------------------------------------


def _emit(env: Any, doc: Any) -> None:
    env.out.write(json.dumps(doc, indent=2, default=str) + "\n")


def _refuse(env: Any, a: argparse.Namespace, exc: ScheduleError) -> int:
    env.err.write(f"tempergraph: schedule {a.action}: {exc.code}: {exc.message}\n")
    if getattr(a, "json", False):
        _emit(env, {"schema_version": SCHEMA, "status": "error", "refusals": [{"code": exc.code, "message": exc.message}]})
    return exc.exit_code


def _needs(env: Any, ask: Needs) -> int:
    _emit(env, {"schema_version": SCHEMA, "status": "needs",
                "questions": [{"name": "when", "question": ask.question, "choices": [r.label for r in ask.readings]}],
                "readings": [{"choose": i, "label": r.label, "phrase": r.phrase}
                             for i, r in enumerate(ask.readings, start=1)]})
    return int(ExitCode.PAUSED)


def _tty(env: Any) -> bool:
    return bool(env.signals[1]) if env.signals else bool(sys.stdin.isatty() and sys.stdout.isatty())


def _confirm(env: Any, a: argparse.Namespace, echo: Echo | None, what: str) -> None:
    """A yes from `--yes` or from a person at a terminal; else exit 3 with the echo as the `needs`, saving nothing."""
    if getattr(a, "yes", False):
        return
    if _tty(env):
        env.err.write((echo.text() if echo else "") + f"{what} [y/N] ")
        env.err.flush()
        try:
            if sys.stdin.readline().strip().lower() in ("y", "yes"):
                return
        except (OSError, ValueError):
            pass
    doc: dict[str, Any] = {"schema_version": SCHEMA, "status": "needs", "questions": [
        {"name": "confirm", "question": f"{what} {echo.sentence if echo else ''}".strip(), "choices": ["yes"]}]}
    if echo:
        doc["echo"] = echo.to_doc()
    raise _Stop(int(ExitCode.PAUSED), doc)


def _now() -> datetime:
    return CLOCK()


# --- timing ------------------------------------------------------------------------------------------------------


def _ends(when: When) -> tuple[str | None, int | None]:
    if when.kind != "recur":
        return None, None
    rule = parse_rule(str(when.rule))
    ends = rule.until.astimezone(zone_of(when.zone)).strftime(ISO_MINUTE) if rule.until else None
    return ends, rule.count


def _apply_bounds(parsed: Parsed, a: argparse.Namespace, now: datetime) -> Parsed:
    """`--starts`, `--until` and `--count` beside a phrase bound the recurrence it gave."""
    if a.starts is None and a.until is None and a.count is None:
        return parsed
    when = parsed.when
    if when.kind != "recur":
        raise ScheduleError("when_malformed", "--starts, --until and --count belong to a recurrence, not to a single time")
    notes = list(parsed.assumptions)
    rule = with_bounds(parse_rule(str(when.rule)), a.until, a.count, when.zone, notes)
    starts = parse_wall(a.starts, when.zone, "--starts", notes, need_time=False)[0] if a.starts else datetime.fromisoformat(
        str(when.starts))
    again = build_recur(rule, when.zone, starts, now, notes)
    again.phrase, again.given = parsed.phrase, parsed.given
    return again


def _timing(a: argparse.Namespace, now: datetime, *, phrase: str | None = None) -> Parsed:
    exact = {"at": a.at, "rrule": a.rrule, "every": a.every, "cron": a.cron}
    given = [k for k, v in exact.items() if v is not None]
    phrase = phrase or getattr(a, "phrase", None) or a.when
    if given and phrase:
        raise ScheduleError("when_malformed", "give the timing once: a phrase or one exact format, not both")
    machine = machine_zone()
    if given:
        if a.choose is not None:
            raise ScheduleError("choose_invalid", "--choose answers a phrase; an exact format has one reading")
        return parse_exact(**exact, tz=a.tz, starts=a.starts, until=a.until, count=a.count, now=now, machine=machine)
    if phrase:
        return _apply_bounds(parse_words(phrase, now=now, tz=a.tz, machine=machine, choose=a.choose), a, now)
    raise ScheduleError("when_malformed", "timing is needed: a phrase (--when) or --at, --rrule, --every or --cron")


def _when_doc(parsed: Parsed) -> dict[str, Any]:
    ends, count = _ends(parsed.when)
    return {"input": parsed.given or {"format": "--when", "value": parsed.phrase}, "phrase": parsed.phrase,
            **parsed.when.to_doc(), "ends": ends, "count": count}


def _echo_doc(env: Any, a: argparse.Namespace, echo: Echo) -> None:
    if getattr(a, "json", False):
        _emit(env, {"schema_version": SCHEMA, "status": "ok", "echo": echo.to_doc(), **echo.to_doc()})
    else:
        env.out.write(echo.text())


def cmd_parse(env: Any, a: argparse.Namespace) -> int:
    now = _now()
    parsed = _timing(a, now)
    _echo_doc(env, a, build_echo(parsed.when, parsed.assumptions, now))
    return 0


# --- reading the store -------------------------------------------------------------------------------------------


def _select(ident: str) -> dict[str, Any]:
    entries = store.list_entries()
    exact = [e for e in entries if e.get("schedule_id") == ident]
    if exact:
        return exact[0]
    named = [e for e in entries if e.get("name") == ident]
    pool = [e for e in named if e.get("state") != "removed"] or named
    if len(pool) == 1:
        return pool[0]
    if not pool:
        raise ScheduleError("schedule_unknown", f"no schedule {ident!r}; `tempergraph schedule list --all` shows them")
    raise ScheduleError("schedule_ambiguous", f"{ident!r} names {len(pool)} schedules ({', '.join(e['schedule_id'] for e in pool)}); "
                                              "give the id")


def _row(entry: dict[str, Any], log: list[dict[str, Any]], now: datetime, machine: str) -> dict[str, Any]:
    when = When.from_doc(entry["when"])
    nxt = next_slots(when, floor_minute(now), 1) if entry.get("state") == "active" else []
    ended = {e.get("fire_id") for e in log if e.get("kind") == "ended"}
    started = [e for e in log if e.get("kind") == "started"]
    return {
        "schedule_id": entry["schedule_id"], "name": entry["name"],
        "target": entry["target"].get("workflow") or entry["target"].get("orchestration_file"),
        "sentence": build_echo(when, [], now).sentence, "zone": when.zone, "zone_differs": when.zone != machine,
        "state": entry["state"], "next_slot": nxt[0].utc.strftime("%Y-%m-%dT%H:%M:%SZ") if nxt else None,
        "last_fire": started[-1].get("slot") if started else None,
        "live_runs": sum(1 for e in started if e.get("fire_id") not in ended), "failures": policies.failure_count(log),
        "period_spend": policies.period_spend(entry, log, now) if entry.get("budget") else None}


def cmd_list(env: Any, a: argparse.Namespace) -> int:
    now, machine = _now(), machine_zone()[0]
    rows = [_row(e, store.read_log(e["schedule_id"]), now, machine) for e in store.list_entries()
            if a.show_all or e.get("state") in ("active", "paused")]
    if a.json:
        _emit(env, {"schema_version": SCHEMA, "machine_zone": machine, "schedules": rows})
        return 0
    for r in rows:
        mark = " (differs from this machine)" if r["zone_differs"] else ""
        env.out.write(f"{r['schedule_id']}\t{r['name']}\t{r['target']}\t{r['sentence']}\t{r['zone']}{mark}\t{r['state']}\t"
                      f"next {r['next_slot'] or '-'}\tlast {r['last_fire'] or 'none'}\tlive {r['live_runs']}\t"
                      f"failures {r['failures']}\tspend {'-' if r['period_spend'] is None else r['period_spend']}\n")
    if not rows:
        env.out.write("no schedules\n")
    return 0


def cmd_show(env: Any, a: argparse.Namespace) -> int:
    entry, now = _select(a.id), _now()
    when = When.from_doc(entry["when"])
    echo = build_echo(when, [], now, n=10)
    log = store.read_log(entry["schedule_id"])[-20:]
    if a.json:
        _emit(env, {"schema_version": SCHEMA, "entry": entry, "echo": echo.to_doc(), "fires": log})
        return 0
    env.out.write(f"{entry['schedule_id']} ({entry['state']}) -> {entry['target'].get('workflow')}\n{echo.text()}")
    env.out.write("last fires:\n" + "".join(f"  {e.get('at')} {e.get('kind')} {e.get('slot') or ''}\n" for e in log))
    return 0


def cmd_history(env: Any, a: argparse.Namespace) -> int:
    entry = _select(a.id)
    log = store.read_log(entry["schedule_id"])
    if a.since:
        try:
            cut = datetime.combine(date.fromisoformat(a.since), time(0), tzinfo=UTC)
        except ValueError:
            raise ScheduleError("when_malformed", f"--since {a.since!r}: an ISO date such as 2026-11-01 is needed") from None
        log = [e for e in log if e.get("at") and datetime.fromisoformat(str(e["at"]).replace("Z", "+00:00")) >= cut]
    if a.json:
        _emit(env, {"schema_version": SCHEMA, "schedule_id": entry["schedule_id"], "fires": log})
    else:
        env.out.write("".join(f"{e.get('seq')}\t{e.get('at')}\t{e.get('kind')}\t{e.get('slot') or ''}\n" for e in log))
    return 0


# --- the settings check and the caps (SCH-B24, SCH-B25, SCH-B10, SCH-B22) --------------------------------------------


def _spec(env: Any, name: str) -> Any:
    from tempergraph.catalog import PackageNotLoaded
    from tempergraph.cli.main import UsageError
    from tempergraph.cli.main import _spec as resolve

    try:
        return resolve(env, name)
    except (UsageError, PackageNotLoaded) as exc:
        raise ScheduleError("workflow_unregistered", f"{name!r} is not a registered workflow ({exc}); "
                                                     "`tempergraph list` shows the catalog") from None


def _caps(spec: Any, flags: dict[str, Any], notes: list[str]) -> float:
    """A cap is required: the workflow's own satisfies it, and the flag only lowers it (SCH-B24, SCH-B8)."""
    key = "run.run_cost_cap_usd"
    flag, own = flags.get(key), spec.run_cost_cap_usd
    if flag is None and own is None:
        raise ScheduleError("cost_cap_required", "a schedule spends unattended: give --run-cost-cap, or use a workflow "
                                                 "that declares run_cost_cap_usd")
    if flag is not None and (isinstance(flag, bool) or not isinstance(flag, (int, float)) or flag <= 0):
        raise ScheduleError("cost_cap_required", f"--run-cost-cap {flag!r}: a number above 0 is needed")
    if flag is not None and own is not None and flag > own:
        notes.append(f"run cost cap stays {own:g}: the workflow's own cap, which --run-cost-cap only lowers")
        flags[key] = float(own)
        return float(own)
    cap = float(flag if flag is not None else own)
    flags[key] = cap
    return cap


def _check_run(env: Any, spec: Any, request: str, inputs: dict[str, str], flags: dict[str, Any],
               profiles: list[str] | None, overlap: str, repo: Path) -> None:
    """`run --check`'s own steps (resolve the request, settle the settings, preflight), refusing as it refuses."""
    from tempergraph.catalog import resolve_request
    from tempergraph.cli.main import CHECK_EXIT, _root_or_none
    from tempergraph.executors.preflight import preflight
    from tempergraph.run.runner import RunSettings, SettingsRefused, settle_start
    from tempergraph.workspace import WorkspaceRefused, resolve_workspace

    res = resolve_request(spec, request.split(), inputs, env.cwd, None)
    doc: dict[str, Any] = {"schema_version": SCHEMA, "status": res.status, "workflow": spec.name}
    if res.status == "needs":
        doc["questions"] = [{"name": q.name, "question": q.question, "choices": list(q.choices or [])} for q in res.questions]
        raise _Stop(int(ExitCode.PAUSED), doc)  # SCH-B25: exit 3 on `needs`, 2 on `error`, saving nothing
    if res.status != "ok":
        doc["message"] = res.message
        raise _Stop(int(CHECK_EXIT["error"]), doc)
    try:
        settled = settle_start(spec, RunSettings(flags=flags, profiles=tuple(profiles) if profiles else None,
                                                  origin="schedule", caller={}), _root_or_none(env))
    except SettingsRefused as exc:
        doc.update(status="error", refusals=[{"code": f.code, "unit": f.unit, "message": f.message} for f in exc.findings])
        raise _Stop(int(CHECK_EXIT["error"]), doc) from None
    rv = settled.run
    rep = preflight(settled.spec, env.registry, enforce_tools=bool(rv["enforce_tools"]),
                    strict_permissions=bool(rv["strict_permissions"]))
    if rep.refusals:
        doc.update(status="error", refusals=[{"code": f.code, "unit": f.unit, "message": f.message} for f in rep.refusals])
        raise _Stop(int(CHECK_EXIT["error"]), doc)
    if overlap == "parallel":  # SCH-B22: a parallel fire needs its own worktree
        try:
            plan = resolve_workspace(settled.spec, repo, rv.get("workspace"))
        except WorkspaceRefused as exc:
            raise ScheduleError(getattr(exc, "code", "workspace_refused"), str(exc)) from None
        if plan.mode != "worktree":
            raise ScheduleError("parallel_needs_worktree", "overlap parallel needs run.workspace to resolve to worktree; "
                                                           f"it resolves to {plan.mode}")


def _repo(env: Any) -> Path:
    from tempergraph import git
    from tempergraph.store.layout import NotInRepository, state_root_path

    main = git.main_checkout(env.cwd)
    if main is not None:
        return Path(main)
    try:
        return state_root_path(env.cwd).parent
    except NotInRepository as exc:
        raise ScheduleError("repo_unusable", str(exc)) from None


def _budget(text: str | None) -> dict[str, Any] | None:
    if text is None:
        return None
    period, sep, cap = text.partition(":")
    try:
        value = float(cap)
    except ValueError:
        value = 0.0
    if not sep or period not in ("day", "week", "month") or value <= 0:
        raise ScheduleError("budget_invalid", f"--budget {text!r}: day, week or month, a colon and a cap above 0, such as month:20")
    return {"period": period, "cap_usd": value}


def _limit(name: str, value: int | None, lo: int, hi: int, default: int) -> int:
    if value is None:
        return default
    if not lo <= value <= hi:
        raise ScheduleError("option_invalid", f"--{name.replace('_', '-')} {value}: {lo} to {hi}")
    return value


def _options(flags: dict[str, Any], profiles: list[str] | None) -> dict[str, Any]:
    return {"flag": {k: {"value": v, "ref": f"--set {k}", "via": "schedule"} for k, v in flags.items()},
            "profiles": list(profiles or [])}


def _flags_of(options: dict[str, Any]) -> dict[str, Any]:
    return {k: c["value"] for k, c in (options.get("flag") or {}).items()}


def _guard_flags(env: Any, a: argparse.Namespace) -> dict[str, Any]:
    from tempergraph.cli.main import _flags
    from tempergraph.settings import is_widening

    flags = _flags(env, a)
    for key in flags:
        if is_widening(key):  # a grant is a person's decision for one run (SCH-B10)
            raise ScheduleError("widening_in_schedule", f"{key}: a schedule cannot carry a grant; a person gives one to a "
                                                        "paused scheduled run on resume")
    return flags


def _inputs(pairs: list[str]) -> dict[str, str]:
    out: dict[str, str] = {}
    for p in pairs:
        k, sep, v = p.partition("=")
        if not sep or not k:
            raise ScheduleError("input_invalid", f"--input {p!r}: expected key=value")
        out[k] = v
    return out


# --- mutating verbs ----------------------------------------------------------------------------------------------


def cmd_add(env: Any, a: argparse.Namespace) -> int:
    if a.orchestration is not None:  # SCH-B33: with orchestration, release 4 (ADR-0132)
        raise ScheduleError("not_in_release", "schedule add --orchestration is not in this release: orchestration "
                                              "comes in release 4 (ADR-0132)")
    if a.program is not None:
        raise ScheduleError("program_target_reserved", "schedule add --program is reserved until a package can declare programs")
    if not a.workflow:
        raise ScheduleError("workflow_unregistered", "schedule add needs a workflow and a request")
    spec = _spec(env, a.workflow)
    caller, now = env.caller(a), _now()
    parsed = _timing(a, now)
    flags = _guard_flags(env, a)
    notes = list(parsed.assumptions)
    cap = _caps(spec, flags, notes)
    overlap = a.overlap or "skip"
    request, inputs, repo = " ".join(a.request).strip(), _inputs(a.input), _repo(env)
    _check_run(env, spec, request, inputs, flags, a.profile, overlap, repo)
    budget = _budget(a.budget)
    entries = store.list_entries()
    if sum(1 for e in entries if e.get("state") != "removed") >= store.MAX_SCHEDULES:
        raise ScheduleError("too_many_schedules", f"{store.MAX_SCHEDULES} schedules are the most on one machine")
    sid = store.new_schedule_id(a.name or spec.name, {str(e["schedule_id"]) for e in entries})
    echo = build_echo(parsed.when, notes, now)
    if a.check:
        _echo_doc(env, a, echo)
        return 0
    _confirm(env, a, echo, "Save this schedule?")
    when = _when_doc(parsed)
    entry = store.build_entry(
        schedule_id=sid, name=a.name or spec.name, target={"kind": "workflow", "workflow": spec.name, "repo": str(repo),
                                                             "request": request, "inputs": inputs},
        when=when, options=_options(flags, a.profile), run_cost_cap_usd=cap, budget=budget,
        catch_up=a.catch_up or "latest", catch_up_window_s=_window(when), overlap=overlap,
        max_live=_limit("max_live", a.max_live, 1, 4, 1),
        pause_after_failures=_limit("pause_after_failures", a.pause_after_failures, 1, 10, 3),
        created={"at": _stamp(now), "caller": caller, "from": "schedule add"}, now=now)
    store.write_entry(entry)
    store.append_event(sid, "created", now=now, caller=caller, when=parsed.when.to_doc(), target=spec.name,
                       err=env.err)
    if a.json:
        _emit(env, {"schema_version": SCHEMA, "status": "saved", "schedule_id": sid, "echo": echo.to_doc()})
    else:
        env.out.write(echo.text() + f"saved {sid}\n")
    return 0


def _stamp(now: datetime) -> str:
    return now.astimezone(UTC).strftime("%Y-%m-%dT%H:%M:%SZ")


def _window(when: dict[str, Any]) -> int:
    return policies.default_window_s({"when": when})


def cmd_edit(env: Any, a: argparse.Namespace) -> int:
    entry = _select(a.id)
    if a.orchestration is not None or a.program is not None:
        raise ScheduleError("target_fixed", "a schedule's target kind is fixed; remove it and add another")
    target = entry["target"]
    if (a.workflow and a.workflow != target.get("workflow")) or (a.repo and Path(a.repo).resolve() != Path(target["repo"])):
        raise ScheduleError("target_fixed", "a schedule's workflow, repo and target kind are fixed; remove it and add another")
    if entry.get("state") in ("removed", "done"):
        raise ScheduleError("schedule_state", f"{entry['schedule_id']} is {entry['state']}; it cannot be edited")
    caller, now = env.caller(a), _now()
    sid = str(entry["schedule_id"])
    old = When.from_doc(entry["when"])
    changed: list[str] = []
    notes: list[str] = []
    new_entry: dict[str, Any] = dict(entry)
    timing_given = any(v is not None for v in (a.phrase, a.when, a.at, a.rrule, a.every, a.cron))
    echo_when = old
    if timing_given:
        parsed = _timing(a, now)
        echo_when, notes = parsed.when, list(parsed.assumptions)
        new_entry["when"] = _when_doc(parsed)
        if entry.get("catch_up_window_s") == _window(entry["when"]):  # the default window follows the new recurrence
            new_entry["catch_up_window_s"] = _window(new_entry["when"])
        changed.append("when")
    elif any(v is not None for v in (a.tz, a.starts, a.until, a.count)):
        raise ScheduleError("when_malformed", "--tz, --starts, --until and --count change a timing: give it too")
    flags_new = _guard_flags(env, a)
    flags = {**_flags_of(entry["options"]), **flags_new}
    profiles = a.profile if a.profile is not None else entry["options"].get("profiles")
    spec = _spec(env, str(target["workflow"]))
    cap = _caps(spec, flags, notes)
    if flags_new or a.profile is not None:
        new_entry["options"] = _options(flags, profiles)
        changed.append("options")
    if cap != entry["run_cost_cap_usd"]:
        new_entry["run_cost_cap_usd"] = cap
        changed.append("run_cost_cap_usd")
    for key, value in (("catch_up", a.catch_up), ("overlap", a.overlap)):
        if value is not None and value != entry.get(key):
            new_entry[key] = value
            changed.append(key)
    for key, lo, hi in (("max_live", 1, 4), ("pause_after_failures", 1, 10)):
        value = getattr(a, key)
        if value is not None and value != entry.get(key):
            new_entry[key] = _limit(key, value, lo, hi, entry[key])
            changed.append(key)
    if a.budget is not None:
        new_entry["budget"] = _budget(a.budget)
        changed.append("budget")
    if not changed:
        raise ScheduleError("nothing_to_edit", "give a new timing or an option to change")
    _check_run(env, spec, str(target.get("request") or ""), dict(target.get("inputs") or {}), flags, profiles,
               str(new_entry["overlap"]), Path(target["repo"]))
    echo = build_echo(echo_when, notes, now)
    _confirm(env, a, echo, "Save these changes?")
    new_entry["edited"] = {"at": _stamp(now), "caller": caller, "from": "schedule edit"}
    first = next_slots(When.from_doc(new_entry["when"]), floor_minute(now), 1)
    new_entry["next_slot"] = _stamp(first[0].utc) if first else None
    store.write_entry(new_entry)
    store.append_event(sid, "edited", now=now, caller=caller, changed=changed, old=old.to_doc(), new=echo_when.to_doc(),
                       err=env.err)
    if a.json:
        _emit(env, {"schema_version": SCHEMA, "status": "saved", "schedule_id": sid, "changed": changed,
                    "echo": echo.to_doc()})
    else:
        env.out.write(echo.text() + f"saved {sid} (changed {', '.join(changed)})\n")
    return 0


def _set_state(env: Any, entry: dict[str, Any], state: str, now: datetime) -> None:
    entry = dict(entry, state=state)
    first = next_slots(When.from_doc(entry["when"]), floor_minute(now), 1) if state == "active" else []
    entry["next_slot"] = _stamp(first[0].utc) if first else None
    store.write_entry(entry)


def _done(env: Any, a: argparse.Namespace, sid: str, **fields: Any) -> int:
    if a.json:
        _emit(env, {"schema_version": SCHEMA, "status": "ok", "schedule_id": sid, **fields})
    else:
        env.out.write(f"{sid}: " + ", ".join(f"{k} {v}" for k, v in fields.items()) + "\n")
    return 0


def cmd_pause(env: Any, a: argparse.Namespace) -> int:
    entry = _select(a.id)
    sid = str(entry["schedule_id"])
    if entry["state"] == "paused":
        return _done(env, a, sid, state="paused", changed=False)
    if entry["state"] != "active":
        raise ScheduleError("schedule_state", f"{sid} is {entry['state']}; only an active schedule is paused")
    caller, now = env.caller(a), _now()
    _set_state(env, entry, "paused", now)
    extra: dict[str, Any] = {"note": scrub(a.reason)[:200]} if a.reason else {}
    store.append_event(sid, "paused", now=now, caller=caller, reason="person", err=env.err, **extra)
    return _done(env, a, sid, state="paused", changed=True)


def cmd_resume(env: Any, a: argparse.Namespace) -> int:
    entry = _select(a.id)
    sid = str(entry["schedule_id"])
    if entry["state"] == "active":
        return _done(env, a, sid, state="active", changed=False)
    if entry["state"] != "paused":
        raise ScheduleError("schedule_state", f"{sid} is {entry['state']}; only a paused schedule resumes")
    caller, now = env.caller(a), _now()
    log = store.read_log(sid)
    events = policies.resume_events(entry, log, now, catch_up=bool(a.catch_up))
    _set_state(env, entry, "active", now)
    for e in events:
        extra: dict[str, Any] = {k: v for k, v in e.items() if k not in ("kind", "slot", "fire_id")}
        if e["kind"] == "resumed":
            extra["caller"] = caller
        store.append_event(sid, e["kind"], now=now, slot=e["slot"], fire_id=e["fire_id"], err=env.err, **extra)
    return _done(env, a, sid, state="active", missed=sum(1 for e in events if e["kind"] == "missed"),
                 catch_up=bool(a.catch_up))


def cmd_skip(env: Any, a: argparse.Namespace) -> int:
    entry = _select(a.id)
    sid = str(entry["schedule_id"])
    if entry["state"] not in ("active", "paused"):
        raise ScheduleError("schedule_state", f"{sid} is {entry['state']}; nothing to skip")
    if a.next_ and a.until:
        raise ScheduleError("when_malformed", "--next and --until are alternatives")
    caller, now = env.caller(a), _now()
    when = When.from_doc(entry["when"])
    handled = policies.handled_slots(store.read_log(sid))
    start = floor_minute(now)
    if a.until:
        try:
            day = date.fromisoformat(a.until)
        except ValueError:
            raise ScheduleError("when_malformed", f"--until {a.until!r}: an ISO date such as 2026-12-01 is needed") from None
        stop = wall_to_utc(datetime.combine(day, time(0)), zone_of(when.zone)) - timedelta(minutes=1)
        slots = [s.utc for s in slots_between(when, start, stop)]
    else:
        slots = [s.utc for s in next_slots(when, start, 8) if _stamp(s.utc) not in handled][:1]
    slots = [s for s in slots if _stamp(s) not in handled]
    if not slots:
        raise ScheduleError("no_slot", "there is no slot to skip")
    for s in slots:
        store.append_event(sid, "skipped", now=now, slot=_stamp(s), fire_id=policies.fire_id(sid, s), reason="person",
                           caller=caller, err=env.err)
    return _done(env, a, sid, skipped=[_stamp(s) for s in slots])


def cmd_remove(env: Any, a: argparse.Namespace) -> int:
    entry = _select(a.id)
    sid = str(entry["schedule_id"])
    if entry["state"] == "removed":
        raise ScheduleError("schedule_state", f"{sid} is already removed")
    caller, now = env.caller(a), _now()
    _confirm(env, a, build_echo(When.from_doc(entry["when"]), [], now), f"Remove {sid}? Its history stays.")
    _set_state(env, entry, "removed", now)
    store.append_event(sid, "removed", now=now, caller=caller, err=env.err)
    return _done(env, a, sid, state="removed")


# --- dispatch ----------------------------------------------------------------------------------------------------

HANDLERS = {"parse": cmd_parse, "add": cmd_add, "list": cmd_list, "show": cmd_show, "history": cmd_history,
            "edit": cmd_edit, "pause": cmd_pause, "resume": cmd_resume, "skip": cmd_skip, "remove": cmd_remove}


def cmd_schedule(env: Any, a: argparse.Namespace) -> int:
    from tempergraph.cli.main import UsageError

    if a.action is None:
        raise UsageError("schedule needs a verb: parse, add, list, show, history, edit, pause, resume, skip, remove")
    try:
        if a.action in NOT_IN_RELEASE:  # SCH-B33: nothing is read, written or started
            raise ScheduleError("not_in_release", f"schedule {a.action} is not in this release; it comes with the tick "
                                                  "(R3-T5.2, TCK)")
        return HANDLERS[a.action](env, a)
    except ScheduleError as exc:
        return _refuse(env, a, exc)
    except Needs as ask:
        return _needs(env, ask)
    except _Stop as stop:
        _emit(env, stop.doc)
        return stop.code


COMMANDS = {"schedule": cmd_schedule}
