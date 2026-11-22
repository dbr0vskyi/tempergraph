"""The history reader of the audit (AUD-B3, AUD-B5, AUD-B10, AUD-B11, AUD-B12, AUD-B15): the workflow's local run
records turned into per-unit facts that every history rule reads and nothing else.

It reads `runs/<workflow>/<task>/run.jsonl`, the activity journals of the sessions and the findings documents of the
runs in `--window` days and in `--version`, read-only. A log it cannot read (no parseable `run_started`) is counted in
`unreadable` and left out, a line it cannot parse is counted and skipped, never raised. A run whose sessions have no
activity journal (an older engine) is counted in `unclassified`: what needs input summaries is then `unclassified`,
never 0 (AUD-B10). It writes nothing and starts nothing (AUD-B6).

Record shapes it reads beyond the run log's own (`run_started`, `unit_entered`, `attempt_start`, `agent_run`,
`check`, `judgement`, `gate`, `pause`, `human`, `supervision`, `outcome`): `judgement.no_change` (the blockers that
are `no_change`), `attempt_start.prompt_cut` (the renderer cut the prompt), `council` (CNL-B10, CNL-B12: `rounds`
with `choices` and `changed` per member, and the `outcome`) and `contest` (CTS-B7: `slots` with their keys, and the
`winner`). A fact the log does not carry leaves the rule that needs it quiet and its sample empty.
"""

from __future__ import annotations

import datetime as dt
import json
import re
import statistics
from collections.abc import Mapping, Sequence
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

from tempergraph.run.log import split_session_key

MISSING = re.compile(r"⟨missing:[^⟩]*⟩")
STEP_KINDS = frozenset({"step", "retry"})
PASS_TOKENS = frozenset({"PROCEED", "NEXT"})


@dataclass(kw_only=True)
class Attempt:
    """One `agent_run` record: a session and how it ended."""

    run: str
    unit: str
    kind: str
    ok: bool | None
    timed_out: bool
    stalled: bool
    duration_s: float | None
    timeout_s: float | None
    infra_cause: str | None
    tool_wall_share: float
    cost: float | None
    peak_context: int | None
    output_tokens: int | None
    end_shape: str | None = None


@dataclass(kw_only=True)
class Visit:
    """One entry of a unit: the gate's tokens in order."""

    run: str
    unit: str
    ts: str
    version: str
    tokens: list[str] = field(default_factory=list)
    attempts: int = 0
    fallback: bool = False

    @property
    def first_pass(self) -> bool:
        return bool(self.tokens) and self.tokens[0] in PASS_TOKENS


@dataclass(kw_only=True)
class Retry:
    run: str
    unit: str
    blockers: list[str]
    no_change: list[str]


@dataclass(kw_only=True)
class Check:
    run: str
    unit: str
    visit: int
    result: str
    evidence: str
    ran_nothing: bool
    attempts_after: bool = False


@dataclass(kw_only=True)
class Pause:
    run: str
    unit: str
    kind: str
    decision: str | None
    feedback: bool
    changed: bool


@dataclass(kw_only=True)
class Call:
    name: str
    capability: str | None
    input_summary: str | None
    ok: bool | None
    subagent: bool = False


@dataclass(kw_only=True)
class Session:
    """One session as the activity journal and the run log show it (TSA-B6)."""

    run: str
    key: str
    unit: str
    kind: str
    started_tools: tuple[str, ...] | None  # None: no journal
    calls: list[Call]
    denied: list[tuple[str, str | None]]  # (name, scrubbed input summary)
    journal: bool

    @property
    def judge(self) -> bool:
        return self.kind.startswith("judge")


@dataclass(kw_only=True)
class Grant:
    run: str
    unit: str
    capability: str | None
    prefix: str | None
    action: str


@dataclass(kw_only=True)
class HistoryFacts:
    workflow: str = ""
    version: str = "all"
    window_days: int = 30
    root: Path | None = None  # the state root the facts were read from (the owners of rendered rules read it too)
    today: dt.date | None = None
    runs: int = 0
    unreadable: int = 0
    unclassified: int = 0  # runs with sessions and no activity journal
    bad_records: int = 0
    run_ids: list[str] = field(default_factory=list)
    attempts: list[Attempt] = field(default_factory=list)
    visits: list[Visit] = field(default_factory=list)
    retries: list[Retry] = field(default_factory=list)
    checks: list[Check] = field(default_factory=list)
    missing: list[tuple[str, str, str]] = field(default_factory=list)  # (run, unit, marker)
    cut_prompts: list[tuple[str, str]] = field(default_factory=list)  # (run, unit)
    pauses: list[Pause] = field(default_factory=list)
    supervision: list[dict[str, Any]] = field(default_factory=list)
    outcomes: list[tuple[str, str]] = field(default_factory=list)  # (run, verdict)
    rerun_sources: set[str] = field(default_factory=set)
    councils: list[dict[str, Any]] = field(default_factory=list)
    contests: list[dict[str, Any]] = field(default_factory=list)
    sessions: list[Session] = field(default_factory=list)
    grants: list[Grant] = field(default_factory=list)
    findings: list[dict[str, Any]] = field(default_factory=list)  # the runs' findings documents, with `run`
    digests: list[tuple[str, str, str, str, str]] = field(default_factory=list)  # (ts, run, unit, role, digest)

    @property
    def journal_runs(self) -> int:
        return self.runs - self.unclassified

    def refusal_counts(self) -> int | str:
        """Refusals recorded, or `unclassified` when no run in the window has an activity journal (AUD-B10)."""
        if self.runs and self.journal_runs == 0:
            return "unclassified"
        return sum(len(s.denied) for s in self.sessions if s.journal)

    def units(self) -> list[str]:
        return list(dict.fromkeys([a.unit for a in self.attempts] + [v.unit for v in self.visits]))


def _read(path: Path) -> tuple[list[dict[str, Any]], int] | None:
    try:
        text = path.read_text(encoding="utf-8", errors="replace")
    except OSError:
        return None
    out: list[dict[str, Any]] = []
    bad = 0
    for line in text.splitlines():
        if not line.strip():
            continue
        try:
            rec = json.loads(line)
        except ValueError:
            bad += 1
            continue
        if isinstance(rec, dict):
            out.append(rec)
        else:
            bad += 1
    return out, bad


def _ts(value: Any) -> dt.datetime | None:
    try:
        got = dt.datetime.fromisoformat(str(value))
    except ValueError:
        return None
    return got if got.tzinfo else got.replace(tzinfo=dt.UTC)


def _cost(usage: Mapping[str, Any] | None) -> float | None:
    u = usage or {}
    rep, est = u.get("reported_cost_usd"), u.get("estimated_cost_usd")
    return float(rep) if rep is not None else float(est) if est is not None else None


def _num(value: Any) -> float | None:
    return float(value) if isinstance(value, int | float) and not isinstance(value, bool) else None


def read_history(root: Path, workflow: str, version: str, window_days: int, today: dt.date, *,
                 current: str | None = None) -> HistoryFacts:
    """AUD-B3, AUD-B11, AUD-B12, AUD-B15: the facts of the workflow's runs in the window and version."""
    facts = HistoryFacts(workflow=workflow, version=version, window_days=window_days, root=root, today=today)
    base = root / "runs" / workflow
    since = dt.datetime.combine(today - dt.timedelta(days=window_days), dt.time.min, tzinfo=dt.UTC)
    want = current if version == "current" else None if version == "all" else version
    try:
        tasks = sorted(p for p in base.iterdir() if p.is_dir()) if base.is_dir() else []
    except OSError:
        tasks = []
    for task in tasks:
        log = task / "run.jsonl"
        if not log.exists():
            if any(task.iterdir()):
                facts.unreadable += 1
            continue
        got = _read(log)
        start = next((r for r in got[0] if r.get("kind") == "run_started"), None) if got else None
        started = _ts(start.get("ts")) if start else None
        if got is None or start is None or started is None:
            facts.unreadable += 1
            continue
        if started < since or (want is not None and start.get("workflow_version") != want):
            continue
        facts.bad_records += got[1]
        facts.runs += 1
        facts.run_ids.append(task.name)
        _ingest(facts, root, workflow, task, got[0], start)
    return facts


def _ingest(facts: HistoryFacts, root: Path, workflow: str, task: Path, recs: Sequence[Mapping[str, Any]],
            start: Mapping[str, Any]) -> None:
    run = task.name
    ts = str(start.get("ts"))
    ver = str(start.get("workflow_version") or "")
    source = (start.get("rerun_of") or {}) if isinstance(start.get("rerun_of"), Mapping) else {}
    src = source.get("task_id") or source.get("thread_id") or source.get("thread")
    if src:
        facts.rerun_sources.add(str(src).rsplit("/", 1)[-1])
    visit: Visit | None = None
    judged: dict[str, Retry] = {}
    pending: dict[str, Pause] = {}
    fails: dict[str, list[str]] = {}
    timeouts: dict[str, float | None] = {}
    sessions = 0
    for r in recs:
        kind = r.get("kind")
        unit = str(r.get("unit") or split_session_key(str(r.get("session_key") or ""))[0] or "")
        line = json.dumps(r, ensure_ascii=False)
        if kind in ("attempt_start", "agent_run") and MISSING.search(line):
            facts.missing.append((run, unit, MISSING.search(line).group(0)))  # type: ignore[union-attr]
        if kind == "unit_entered":
            visit = Visit(run=run, unit=unit, ts=str(r.get("ts") or ts), version=ver)
            facts.visits.append(visit)
            fails[unit] = []
        elif kind == "attempt_start":
            timeouts[str(r.get("session_key"))] = _num(r.get("timeout_s"))
            if r.get("prompt_cut"):
                facts.cut_prompts.append((run, unit))
            if str(r.get("session_kind") or "step") not in STEP_KINDS:
                continue  # a judge session is not a visit's attempt
            if r.get("prompt_digest"):
                facts.digests.append((str(r.get("ts") or ts), run, unit, "step", str(r["prompt_digest"])))
            if visit is not None and visit.unit == unit:
                visit.attempts += 1
        elif kind == "agent_run":
            sessions += 1
            key = str(r.get("session_key") or "")
            sk = str(r.get("session_kind") or "step")
            if sk in STEP_KINDS:
                facts.attempts.append(Attempt(
                    run=run, unit=unit, kind=sk, ok=r.get("ok"), timed_out=bool(r.get("timed_out")),
                    stalled=bool(r.get("stalled")), duration_s=_num(r.get("duration_s")),
                    timeout_s=timeouts.get(key), infra_cause=r.get("infra_cause"),
                    tool_wall_share=float(r.get("tool_wall_share") or 0.0), cost=_cost(r.get("usage")),
                    peak_context=int((r.get("usage") or {}).get("peak_context_tokens") or 0) or None,
                    output_tokens=int((r.get("usage") or {}).get("output_tokens") or 0) or None,
                    end_shape=r.get("end_shape") or _digest_shape(task, key)))
            else:
                facts.attempts.append(Attempt(
                    run=run, unit=unit, kind=sk, ok=r.get("ok"), timed_out=bool(r.get("timed_out")),
                    stalled=bool(r.get("stalled")), duration_s=_num(r.get("duration_s")), timeout_s=None,
                    infra_cause=r.get("infra_cause"), tool_wall_share=0.0, cost=_cost(r.get("usage")),
                    peak_context=None, output_tokens=None))
        elif kind == "check":
            res = str(r.get("result") or "")
            ev = str(r.get("evidence") or "")
            ran_nothing = ((r.get("commands_run") == 0 and int(r.get("commands_declared") or 1) > 0)
                           or "not run" in ev.lower())
            facts.checks.append(Check(run=run, unit=unit, visit=len(facts.visits), result=res, evidence=ev,
                                      ran_nothing=ran_nothing))
            if res == "FAIL":
                fails.setdefault(unit, []).append(ev)
        elif kind == "judgement":
            blockers = [str(b) for b in r.get("blockers") or []]
            judged[unit] = Retry(run=run, unit=unit, blockers=blockers,
                                 no_change=[str(b) for b in r.get("no_change") or []])
            if r.get("brief_digest"):
                facts.digests.append((str(r.get("ts") or ts), run, unit, "judge", str(r["brief_digest"])))
        elif kind == "gate":
            token = str(r.get("token") or r.get("verdict") or "")
            if visit is not None and visit.unit == unit:
                visit.tokens.append(token)
                visit.fallback = visit.fallback or token == "FALLBACK"
            if str(r.get("verdict")) == "RETRY" and unit in judged:
                facts.retries.append(judged[unit])
        elif kind == "route" and r.get("chosen_by") == "fallback" and visit is not None:
            visit.fallback = True
        elif kind == "pause":
            pending[unit] = Pause(run=run, unit=unit, kind=str(r.get("pause_kind") or ""), decision=None,
                                  feedback=False, changed=False)
            facts.pauses.append(pending[unit])
        elif kind == "human" and unit in pending:
            p = pending.pop(unit)
            p.decision, p.feedback, p.changed = (str(r.get("decision") or ""), bool(r.get("feedback")),
                                                 bool(r.get("workspace_changed")))
        elif kind == "supervision":
            facts.supervision.append(dict(r))
        elif kind == "outcome":
            facts.outcomes = [o for o in facts.outcomes if o[0] != run] + [(run, str(r.get("verdict") or ""))]
        elif kind == "grant":
            facts.grants.append(Grant(run=run, unit=unit, capability=r.get("capability"), prefix=r.get("prefix"),
                                      action=str(r.get("action") or "")))
        elif kind == "council":
            facts.councils.append({"run": run, **dict(r)})
        elif kind == "contest":
            facts.contests.append({"run": run, **dict(r)})
    # repeated check evidence needs the visit's attempts after the repeat
    for c in facts.checks:
        if c.run == run and c.result == "FAIL":
            same = [x for x in facts.checks if x.run == run and x.unit == c.unit and x.visit == c.visit
                    and x.result == "FAIL" and x.evidence == c.evidence]
            visit_of = [v for v in facts.visits if v.run == run and v.unit == c.unit]
            c.attempts_after = len(same) >= 2 and bool(visit_of) and visit_of[-1].attempts > len(same)
    _sessions(facts, task, run, recs)
    if sessions and not any(s.journal for s in facts.sessions if s.run == run):
        facts.unclassified += 1
    from tempergraph.improve import record

    for f in record.read_findings(root, workflow, run):
        facts.findings.append({"run": run, **f})


def _digest_shape(task: Path, key: str) -> str | None:
    """The timeout shape the session digest recorded (`hung`, `slow_host`, `model_silent`), read-only."""
    try:
        doc = json.loads((task / "sessions" / key / "digest.json").read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return None
    end = doc.get("end") if isinstance(doc, dict) else None
    shape = end.get("timeout_shape") if isinstance(end, dict) else None
    return str(shape) if shape else None


def _sessions(facts: HistoryFacts, task: Path, run: str, recs: Sequence[Mapping[str, Any]]) -> None:
    """TSA-B6: per session the start tool list, the calls with their scrubbed input summaries, the denied names."""
    for r in recs:
        if r.get("kind") != "agent_run" or not r.get("session_key"):
            continue
        key = str(r["session_key"])
        unit = str(r.get("unit") or split_session_key(key)[0] or "")
        journal = task / "sessions" / key / "activity.jsonl"
        got = _read(journal) if journal.is_file() else None
        calls: list[Call] = []
        denied: list[tuple[str, str | None]] = []
        started: tuple[str, ...] | None = None
        if got is not None:
            done = {str(x.get("call_id")): x for x in got[0] if x.get("ev") == "tool_finished"}
            for row in got[0]:
                ev = row.get("ev")
                if ev == "session_started":
                    started = tuple(str(t) for t in row.get("tools") or ())
                elif ev == "tool_started":
                    fin = done.get(str(row.get("call_id")))
                    calls.append(Call(name=str(row.get("name") or ""), capability=row.get("capability"),
                                      input_summary=row.get("input_summary"),
                                      ok=None if fin is None else fin.get("ok"), subagent=bool(row.get("subagent"))))
                elif ev == "denied":
                    summary = row.get("input_summary")
                    denied.append((str(row.get("name") or ""), str(summary) if summary else None))
        else:
            calls = [Call(name=str(n), capability=None, input_summary=None, ok=None) for n in r.get("tools") or ()]
        facts.sessions.append(Session(run=run, key=key, unit=unit, kind=str(r.get("session_kind") or "step"),
                                      started_tools=started, calls=calls, denied=denied, journal=got is not None))


def p90(values: Sequence[float]) -> float:
    """The 90th percentile with linear interpolation between ranks (inclusive method)."""
    if not values:
        return 0.0
    if len(values) == 1:
        return float(values[0])
    return float(statistics.quantiles(sorted(values), n=10, method="inclusive")[-1])
