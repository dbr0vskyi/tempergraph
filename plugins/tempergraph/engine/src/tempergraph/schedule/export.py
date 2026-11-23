"""`schedule export`: a snippet for a pipeline system, printed and kept nowhere (TCK-B20, TCK-B11).

The rule becomes five-field cron in UTC; a calendar rule in a zone with daylight saving is refused (`export_needs_utc`) unless
`--pin-offset` pins today's offset and says what the other season does. The command is `tempergraph run <workflow> …` with
the schedule's options, its run cost cap, a label and `--caller pipeline`; the request is read from a file in the repository,
never inlined; the secrets are of kind `api_key` or `cloud` only, named and never valued; the pipeline's own concurrency
group stands for `overlap`. No credential value and no person's text goes into a snippet.
"""

from __future__ import annotations

import shlex
from datetime import UTC, datetime, timedelta
from typing import Any

from tempergraph.schedule.model import ScheduleError, When, parse_rule, utc_offset, wall_to_utc, zone_of

TARGETS = ("github-actions", "gitlab-ci", "crontab")
SECRETS = {"claude": "ANTHROPIC_API_KEY", "agent-sdk": "ANTHROPIC_API_KEY", "messages-api": "ANTHROPIC_API_KEY",
           "antigravity": "GEMINI_API_KEY"}  # kind `api_key`; `cloud` is the pipeline's own workload identity
CRON_DAYS = "0123456"


def _minutes(zone: Any, at: datetime) -> int:
    off = at.astimezone(zone).utcoffset() or timedelta(0)
    return int(off.total_seconds() // 60)


def moves(zone: Any, now: datetime) -> bool:
    """The zone's offset differs between two seasons of this year (daylight saving)."""
    return _minutes(zone, datetime(now.year, 1, 15, tzinfo=UTC)) != _minutes(zone, datetime(now.year, 7, 15, tzinfo=UTC))


def _ranges(values: list[int]) -> str:
    out: list[str] = []
    run = sorted(set(values))
    i = 0
    while i < len(run):
        j = i
        while j + 1 < len(run) and run[j + 1] == run[j] + 1:
            j += 1
        out.append(str(run[i]) if j == i else (f"{run[i]},{run[j]}" if j == i + 1 else f"{run[i]}-{run[j]}"))
        i = j + 1
    return ",".join(out)


def to_cron(entry: dict[str, Any], pin_offset: bool, now: datetime) -> tuple[str, list[str]]:
    """The five-field UTC cron line of the schedule's rule and the comments that go with it."""
    when = When.from_doc(entry["when"])
    zone = zone_of(when.zone)
    notes: list[str] = []
    if when.kind == "once":
        utc = wall_to_utc(datetime.fromisoformat(str(when.at)), zone)
        notes.append("a one-time schedule: cron repeats this date every year, so remove the job after it has run")
        return f"{utc.minute} {utc.hour} {utc.day} {utc.month} *", notes
    rule = parse_rule(str(when.rule))
    needs_zone = rule.freq != "HOURLY" or rule.interval > 1 or bool(rule.byday)
    if needs_zone and moves(zone, now):
        if not pin_offset:
            raise ScheduleError("export_needs_utc", f"{when.zone} changes its UTC offset with daylight saving, which cron cannot follow: "
                                                    "give the rule in UTC (`--tz UTC`) or pass --pin-offset to pin today's offset")
        other = datetime(now.year, 7, 15, tzinfo=UTC) if _minutes(zone, now) == _minutes(zone, datetime(now.year, 1, 15, tzinfo=UTC)) \
            else datetime(now.year, 1, 15, tzinfo=UTC)
        pinned = _minutes(zone, now)
    else:
        other, pinned = None, _minutes(zone, now)
    if rule.byday and any(o for o, _ in rule.byday):
        raise ScheduleError("export_not_expressible", "an nth weekday of the month cannot be written as a cron line")
    if rule.freq == "HOURLY":
        if rule.interval > 1 and 24 % rule.interval:
            raise ScheduleError("export_not_expressible", f"every {rule.interval} hours does not divide the day, so cron cannot keep it")
        if pinned % 60 and rule.interval > 1:
            raise ScheduleError("export_needs_utc", f"{when.zone} is not a whole-hour offset: give the rule in UTC")
        minutes = sorted({(m - pinned) % 60 for m in (rule.byminute or (0,))})
        hour_field = "*" if rule.interval == 1 else f"*/{rule.interval}"
        return f"{','.join(map(str, minutes))} {hour_field} * * *", notes
    if not rule.byhour:
        raise ScheduleError("export_not_expressible", "this rule names no hour of the day")
    times = [(h * 60 + m - pinned) for h in rule.byhour for m in (rule.byminute or (0,))]
    shifts = {t // 1440 for t in times}
    if len(shifts) != 1:
        raise ScheduleError("export_not_expressible", "the times of this rule fall on different UTC days; give the rule in UTC")
    shift = shifts.pop()
    hours = sorted({(t % 1440) // 60 for t in times})
    minutes = sorted({t % 60 for t in times})
    dom, dow = "*", "*"
    if rule.freq == "WEEKLY":
        days = [((wd + 1) % 7 + shift) % 7 for _, wd in rule.byday]  # rule weekday 0 is Monday, cron 0 is Sunday
        dow = _ranges(days) if days else "*"
    elif rule.freq == "MONTHLY":
        if rule.bymonthday and shift == 0 and all(1 <= d <= 31 for d in rule.bymonthday):
            dom = _ranges(list(rule.bymonthday))
        else:
            raise ScheduleError("export_not_expressible", "this monthly rule cannot be written as a cron line in UTC")
    elif rule.freq != "DAILY":
        raise ScheduleError("export_not_expressible", f"{rule.freq} cannot be written as a cron line")
    if other is not None:
        was = datetime(2000, 1, 1, hours[0], minutes[0], tzinfo=UTC) + timedelta(minutes=_minutes(zone, other))
        mine = datetime(2000, 1, 1, hours[0], minutes[0], tzinfo=UTC) + timedelta(minutes=pinned)
        season = "summer" if other.month == 7 else "winter"
        notes.append(f"pinned to today's offset ({utc_offset(zone, now)}): in {season} ({utc_offset(zone, other)}) this job "
                     f"runs at {was:%H:%M} local instead of {mine:%H:%M}")
    return f"{','.join(map(str, minutes))} {','.join(map(str, hours))} {dom} * {dow}", notes


def _command(entry: dict[str, Any], system: str) -> list[str]:
    """`tempergraph run <workflow> …`: the schedule's options, its cap, a label and `--caller pipeline`; the request from a file."""
    t = entry["target"]
    sid = str(entry["schedule_id"])
    words = ["tempergraph", "run", shlex.quote(str(t["workflow"]))]
    flags = {k: c["value"] for k, c in ((entry.get("options") or {}).get("flag") or {}).items()}
    cap = flags.pop("run.run_cost_cap_usd", entry.get("run_cost_cap_usd"))
    words += ["--run-cost-cap", shlex.quote(f"{float(cap):g}")]
    for k, v in sorted(flags.items()):
        words += ["--set", shlex.quote(f"{k}={v}")]
    for p in (entry.get("options") or {}).get("profiles") or []:
        words += ["--profile", shlex.quote(str(p))]
    for k, v in sorted((t.get("inputs") or {}).items()):
        words += ["--input", shlex.quote(f"{k}={v}")]
    words += ["--label", shlex.quote(f"schedule-{sid}"), "--caller", "pipeline", f'"$(cat {request_file(sid)})"']
    return words


def request_file(schedule_id: str) -> str:
    return f".tempergraph/schedules/{schedule_id}.request.md"


def _secrets(entry: dict[str, Any]) -> list[str]:
    """Secret names for kind `api_key` only; never `oauth_token`, never a cached sign-in."""
    names: list[str] = []
    for c in entry.get("executors_checked") or []:
        if "api_key" in (c.get("kinds") or []) or not c.get("kinds"):
            n = SECRETS.get(str(c.get("executor")))
            if n and n not in names:
                names.append(n)
    return names


def render(entry: dict[str, Any], target: str, pin_offset: bool, now: datetime) -> str:
    if target not in TARGETS:
        raise ScheduleError("export_target", f"--for takes {', '.join(TARGETS)}")
    sid, cron_line, notes = str(entry["schedule_id"]), *to_cron(entry, pin_offset, now)
    fields = cron_line
    overlap = str(entry.get("overlap") or "skip")
    command = " ".join(_command(entry, target))
    secrets = _secrets(entry)
    records = f"records: origin ci, schedule {{schedule_id: {sid}, declared: true}}; host ci:{target}; the tie is the pipeline's word, not attested"
    head = [f"# tempergraph schedule {sid}, exported for {target}: nothing is kept; commit this to the pipeline's configuration",
            f"# the request is read from {request_file(sid)} in the repository: commit it there (never inline)",
            f"# {records}", "# a run that pauses exits 3 as any pipeline run does; resume it where the engine runs"]
    head += [f"# {n}" for n in notes]
    if target == "github-actions":
        env = "        env:\n" + "".join(f"          {n}: ${{{{ secrets.{n} }}}}\n" for n in secrets) if secrets else ""
        return ("\n".join(head) + f"\nname: tempergraph-{sid}\non:\n  schedule:\n    - cron: \"{fields}\"  # UTC\n"
                f"concurrency:\n  group: tempergraph-{sid}\n  cancel-in-progress: false  # overlap {overlap}: a new job waits\n"
                "jobs:\n  run:\n    runs-on: ubuntu-latest\n    steps:\n      - uses: actions/checkout@v4\n"
                f"      - name: run\n{env}        run: {command}\n")
    if target == "gitlab-ci":
        var = "".join(f"# CI/CD variable (masked): {n}\n" for n in secrets)
        return ("\n".join(head) + f"\n# create a pipeline schedule with the cron `{fields}` (UTC) under CI/CD > Schedules\n{var}"
                f"tempergraph-{sid}:\n  rules:\n    - if: $CI_PIPELINE_SOURCE == \"schedule\"\n  resource_group: tempergraph-{sid}\n"
                f"  script:\n    - {command}\n")
    lock = f"flock -n /tmp/tempergraph-{sid}.lock" if overlap == "skip" else f"flock /tmp/tempergraph-{sid}.lock"
    return ("\n".join(head) + f"\n{fields} cd {shlex.quote(str(entry['target']['repo']))} && {lock} {command}\n")
