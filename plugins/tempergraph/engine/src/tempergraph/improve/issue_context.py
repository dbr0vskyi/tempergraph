"""What a loop issue tells its reader about the run behind a finding (ISS-B8 to ISS-B10).

Built by the loop child from the run's own log (`run.jsonl`) and the machine it runs on, never from the evidence
file. Every value is taken from a fixed list of record keys whose values the engine writes itself: ids, enums,
numbers, versions and model names. A value that does not look like one of those (any text with a space in it, a
path, a long string) is left out, so no request text, model output, judge note or check output can reach an issue.
"""

from __future__ import annotations

import platform
import re
from collections.abc import Mapping, Sequence
from typing import Any

from tempergraph.constants import ENGINE_VERSION
from tempergraph.improve import pause_facts

LOG_LINES = 40  # the most run-log lines an issue or comment shows (ISS-B10)
SAFE = re.compile(r"^[A-Za-z0-9_.:@+\-]{1,64}$")  # an id, enum, version or model name: no space, no slash
# The record keys a run-log line may show; anything else (request, notes, evidence, gap, transcript, paths) never.
LOG_KEYS = ("attempt", "visit", "entered_from", "session_key", "executor", "alias", "model", "effort", "cli_version",
            "ok", "error_kind", "infra_cause", "timed_out", "stalled", "slow_host", "duration_s", "result",
            "environmental", "verdict", "route_target", "blockers", "statuses", "confidence", "confidence_source",
            "cause", "counter", "limit", "used", "exit_code", "reason", "cost", "cost_so_far", "unknown_tools")
RUN_KINDS = frozenset({"run_started", "run_exit"})  # shown whatever unit they name


def _safe(v: Any) -> Any:
    """The value when it is a number, a bool or an id-like string; lists and maps of those, clipped; else None."""
    if isinstance(v, bool) or v is None:
        return v
    if isinstance(v, int | float):
        return round(v, 4) if isinstance(v, float) else v
    if isinstance(v, str):
        return v if SAFE.match(v) else None
    if isinstance(v, list | tuple):
        got = [x for x in (_safe(x) for x in list(v)[:10]) if x is not None and not isinstance(x, list | dict)]
        return got or None
    if isinstance(v, Mapping):
        kept: dict[str, Any] = {}
        for k, x in list(v.items())[:12]:
            y = _safe(x)
            if SAFE.match(str(k)) and y is not None and not isinstance(y, list | dict):
                kept[str(k)] = y
        return kept or None
    return None


def _unit_of(r: Mapping[str, Any]) -> str:
    return f"{r['child']}/{r.get('unit') or '-'}" if r.get("child") else str(r.get("unit") or "")


def segment(records: Sequence[Mapping[str, Any]], started: str | None = None) -> list[Mapping[str, Any]]:
    """The segment that starts at the `run_started` whose `ts` is `started`; the last one when None or not found."""
    starts = [i for i, r in enumerate(records) if r.get("kind") == "run_started"]
    if started:
        for n, i in enumerate(starts):
            if str(records[i].get("ts") or "") == started:
                return list(records[i:starts[n + 1] if n + 1 < len(starts) else len(records)])
    return list(records[max(starts, default=0):])


def log_lines(records: Sequence[Mapping[str, Any]], units: Sequence[str], *,
              segment_started: str | None = None, facts: Mapping[str, str] | None = None) -> tuple[list[str], int]:
    """ISS-B10: the segment's records of the finding's units and its start and exit, one line each, at most
    `LOG_LINES`; returns the lines and how many earlier matching records were left out. `facts` is accepted for the
    same call shape as `run_facts`; the log lines never show it."""
    want = set(units)
    rows: list[str] = []
    for r in segment(records, segment_started):
        kind = str(r.get("kind") or "")
        if kind not in RUN_KINDS and _unit_of(r) not in want:
            continue
        if not SAFE.match(kind):
            continue
        parts = [str(r.get("ts") or "")[:19], kind]
        if r.get("unit") and kind not in RUN_KINDS:
            parts.append(f"unit={_unit_of(r)}" if SAFE.match(_unit_of(r).replace("/", "-")) else "")
        for k in LOG_KEYS:
            if k not in r:
                continue
            v = _safe(r[k])
            if v is None or v == [] or v == {}:
                continue
            if isinstance(v, list):
                v = ",".join(str(x) for x in v)
            elif isinstance(v, dict):
                v = ",".join(f"{a}:{b}" for a, b in v.items())
            parts.append(f"{k}={v}")
        if kind == "agent_run":
            cost = _safe((r.get("usage") or {}).get("reported_cost_usd")) if isinstance(r.get("usage"), Mapping) else None
            if isinstance(cost, int | float):
                parts.append(f"cost_usd={cost}")
            if isinstance(r.get("changed_paths"), list):
                parts.append(f"changed_paths={len(r['changed_paths'])}")
        rows.append(" ".join(p for p in parts if p))
    left = max(0, len(rows) - LOG_LINES)
    return rows[left:], left


def environment(records: Sequence[Mapping[str, Any]], units: Sequence[str], mode: str | None = None,
                judge_executor: str | None = None, *, segment_started: str | None = None,
                facts: Mapping[str, str] | None = None) -> dict[str, Any]:
    """ISS-B8: the versions and machine behind a finding, as names and numbers. `facts` is accepted for the same
    call shape as `run_facts`; the environment never shows it."""
    seg = segment(records, segment_started)
    started: Mapping[str, Any] = next((r for r in seg if r.get("kind") == "run_started"), {})
    want = set(units)
    mine = [r for r in seg if _unit_of(r) in want]
    executors = sorted({str(x) for r in mine if (x := _safe(r.get("executor")))})
    cli = sorted({str(x) for r in mine if r.get("kind") == "agent_run" and (x := _safe(r.get("cli_version")))})
    models = sorted({str(x) for r in mine if r.get("kind") == "session_opened" and (x := _safe(r.get("model")))})
    aliases = sorted({str(x) for r in mine if r.get("kind") == "attempt_start" and (x := _safe(r.get("alias")))})
    efforts = sorted({str(x) for r in mine if (x := _safe(r.get("effort")))})
    out: dict[str, Any] = {
        "engine_version": _safe(started.get("engine_version")) or ENGINE_VERSION,
        "loop_engine_version": ENGINE_VERSION,
        "workflow_version": _safe(started.get("workflow_version")),
        "executors": executors, "executor_cli": cli, "models": models, "aliases": aliases, "efforts": efforts,
        "judge_executor": _safe(judge_executor), "improvement_mode": _safe(mode),
        "python": platform.python_version(), "os": f"{platform.system()} {platform.release()}".strip(),
        "arch": platform.machine(),
    }
    return {k: v for k, v in out.items() if v not in (None, "", [])}


def run_facts(records: Sequence[Mapping[str, Any]], finding: Mapping[str, Any],
              units: Sequence[str], *, segment_started: str | None = None,
              facts: Mapping[str, str] | None = None) -> dict[str, Any]:
    """ISS-B8: the run's id, how its segment ended, and the units' attempts and cost; with `facts` (SIL-B37) the
    line that says what answered the segment's pause."""
    seg = segment(records, segment_started)
    started: Mapping[str, Any] = next((r for r in seg if r.get("kind") == "run_started"), {})
    ended: Mapping[str, Any] = next((r for r in reversed(seg) if r.get("kind") == "run_exit"), {})
    want = set(units)
    attempts = {u: max([int(r.get("attempt") or 1) for r in seg if r.get("kind") == "attempt_start"
                        and _unit_of(r) == u] or [0]) for u in units}
    cost = sum(float((r.get("usage") or {}).get("reported_cost_usd") or 0.0) for r in seg
               if r.get("kind") == "agent_run" and _unit_of(r) in want and isinstance(r.get("usage"), Mapping))
    reason = pause_facts.pause_reason(seg, [finding]) if ended.get("exit_code") == 3 else ended.get("reason")
    out: dict[str, Any] = {
        "thread": _safe(str(finding.get("thread") or "").replace("/", ":")) and str(finding.get("thread")),
        "started": _safe(str(started.get("ts") or "")[:19]),
        "exit_code": _safe(ended.get("exit_code", finding.get("segment_exit"))),
        "exit_reason": _safe(reason),
        "run_cost_usd": _safe(ended.get("cost_so_far") if ended.get("cost_so_far") is not None else ended.get("cost")),
        "unit_cost_usd": round(cost, 4) if cost else None,
        "attempts": {u: n for u, n in attempts.items() if n} or None,
        "request_digest": _safe(finding.get("request_digest")),
        "rerun_of": _safe(str(finding.get("rerun_of") or "").replace("/", ":")) and finding.get("rerun_of"),
        "machine": _safe(finding.get("machine")),
        "facts": _facts_line(facts) if facts else None,
    }
    return {k: v for k, v in out.items() if v not in (None, "", {}, [])}


FACT_KEYS = (("pause", "reason"), ("unit", "unit"), ("item", "item"), ("decision", "decision"), ("caller", "caller"),
             ("ruling", "ruling"), ("feedback", "feedback"), ("touch", "touch"), ("workspace", "workspace"),
             ("next_gate", "next_gate"))


def _fact_value(raw: Any) -> str | None:
    """A fact as one id-like word, or a list of such words joined by `,` (the classes of a decision's touches, SIL-B43);
    None when any word of it is not an id or enum."""
    words = [_safe(w.replace(" ", "_")) for w in str(raw or "").split(",")]
    return ",".join(words) if words and all(isinstance(w, str) and w for w in words) else None


def _facts_line(facts: Mapping[str, str]) -> str | None:
    """The facts of the segment's pause (SIL-B37) as `key=id` words; a value that is not an id or enum is left out."""
    parts = []
    for name, key in FACT_KEYS:
        v = _fact_value(facts.get(key))
        if v:
            parts.append(f"{name}={v}")
    return " ".join(parts) or None


def build(records: Sequence[Mapping[str, Any]], findings: Sequence[Mapping[str, Any]], *, mode: str | None = None,
          judge_executor: str | None = None, segment_started: str | None = None,
          facts: Mapping[str, str] | None = None) -> dict[str, Any]:
    """The context of one issue or comment: the findings' units, their environment, run facts and log lines."""
    first = findings[0]
    units = [u for u in dict.fromkeys(
        (f"{f['child']}/{f.get('unit') or '-'}" if f.get("child") else str(f.get("unit") or "")) for f in findings) if u]
    lines, left = log_lines(records, units, segment_started=segment_started, facts=facts)
    return {"environment": environment(records, units, mode, judge_executor, segment_started=segment_started,
                                       facts=facts),
            "run": run_facts(records, first, units, segment_started=segment_started, facts=facts),
            "log": lines, "log_left_out": left}
