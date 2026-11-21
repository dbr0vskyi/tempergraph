"""`report` (OBS §2.4): read-only, model-free cost and friction reports over a state root's run logs.

Every figure keeps reported and estimated money apart and says when a part is unmeasured (OBS §2.2): a total is a
pair of sums with session counts, never one number. Activity journals feed the time profile and the loop signal.
"""

from __future__ import annotations

import json
from collections import defaultdict
from collections.abc import Iterable, Iterator
from dataclasses import dataclass, field
from datetime import UTC, datetime, timedelta
from pathlib import Path
from typing import Any

from tempergraph.run.events import records as read_records

STEP_KINDS = ("step", "retry")
JUDGE_KINDS = ("judge", "judge_reask", "grouping")
LOOP_REPEAT = 5


@dataclass(kw_only=True)
class Money:
    """Reported and estimated money apart, with how many sessions each covers (OBS §2.2)."""

    reported: float = 0.0
    estimated: float = 0.0
    sessions: int = 0
    reported_sessions: int = 0
    estimated_sessions: int = 0
    unmeasured: int = 0

    def add(self, usage: dict[str, Any] | None) -> None:
        u = usage or {}
        self.sessions += 1
        rep, est = u.get("reported_cost_usd"), u.get("estimated_cost_usd")
        if isinstance(rep, int | float):
            self.reported += float(rep)
            self.reported_sessions += 1
        if isinstance(est, int | float):
            self.estimated += float(est)
            self.estimated_sessions += 1
        if not isinstance(rep, int | float) and not isinstance(est, int | float):
            self.unmeasured += 1

    @property
    def completeness(self) -> str:
        if self.unmeasured:
            return "incomplete"
        return "complete" if self.reported_sessions == self.sessions else "estimated"

    def to_json(self) -> dict[str, Any]:
        return {"reported_usd": round(self.reported, 6) if self.reported_sessions else None,
                "estimated_usd": round(self.estimated, 6) if self.estimated_sessions else None,
                "sessions": self.sessions, "reported_sessions": self.reported_sessions,
                "estimated_sessions": self.estimated_sessions, "unmeasured": self.unmeasured,
                "completeness": self.completeness}


@dataclass(kw_only=True)
class Session:
    thread_id: str
    workflow: str
    version: str | None
    unit: str
    attempt: int | None
    visit: int
    kind: str
    executor: str | None
    usage: dict[str, Any]
    timed_out: bool
    stalled: bool
    session_key: str | None
    cause: str | None  # why this attempt ran again; None on a unit's first visit's first attempt
    duration_s: float | None = None
    slow_host: bool = False
    prompt_digest: str | None = None


@dataclass(kw_only=True)
class Thread:
    thread_id: str
    workflow: str
    version: str | None
    started_at: str | None
    sessions: list[Session] = field(default_factory=list)
    gates: list[dict[str, Any]] = field(default_factory=list)
    judgements: list[dict[str, Any]] = field(default_factory=list)
    routes: list[dict[str, Any]] = field(default_factory=list)
    humans: list[dict[str, Any]] = field(default_factory=list)
    exit: dict[str, Any] | None = None
    outcome: dict[str, Any] | None = None  # the latest `outcome` record (OUT §2.5)
    folder: Path | None = None


def fold(recs: Iterable[dict[str, Any]], folder: Path | None = None) -> Thread | None:
    """One thread's records into sessions with their repeat causes, gates, judgements, routes and its exit."""
    t: Thread | None = None
    visit: dict[str, int] = defaultdict(lambda: 1)
    entered: dict[str, str] = {}
    first_seen: set[tuple[str, int]] = set()
    last_gate: dict[str, dict[str, Any]] = {}
    last_check: dict[str, str] = {}
    judged: dict[str, dict[str, Any]] = {}
    digests: dict[str, str] = {}
    for r in recs:
        kind = r.get("kind")
        if t is None:
            tid = str(r.get("thread_id") or "")
            t = Thread(thread_id=tid, workflow=tid.split("/", 1)[0], version=None, started_at=r.get("ts"),
                       folder=folder)
        unit = r.get("unit")
        if kind == "run_started":
            t.version = r.get("workflow_version") or t.version
            t.started_at = t.started_at or r.get("ts")
        elif kind == "attempt_start" and r.get("prompt_digest"):
            digests[str(r.get("session_key"))] = str(r["prompt_digest"])
        elif kind == "unit_entered" and unit:
            visit[unit] = int(r.get("visit") or visit[unit])
            entered[unit] = str(r.get("entered_from") or "")
        elif kind == "check" and unit:
            last_check[unit] = str(r.get("result") or "")
        elif kind == "agent_run" and unit:
            sk = str(r.get("session_kind") or r.get("kind_") or "step")
            v = visit[unit]
            cause: str | None = None
            if sk in STEP_KINDS:
                key = (unit, v)
                if key in first_seen:
                    g = last_gate.get(unit) or {}
                    cause = "retry: check" if last_check.get(unit) == "FAIL" and g.get("verdict") == "RETRY" \
                        else "retry: judge" if g.get("verdict") == "RETRY" else "retry"
                elif v > 1:
                    cause = entered.get(unit) or "revisit"
                first_seen.add(key)
            elif sk == "judge_reask":
                cause = "re-ask"
            t.sessions.append(Session(thread_id=t.thread_id, workflow=t.workflow, version=t.version, unit=unit,
                                      attempt=r.get("attempt"), visit=v, kind=sk, executor=r.get("executor"),
                                      usage=r.get("usage") or {}, timed_out=bool(r.get("timed_out")),
                                      stalled=bool(r.get("stalled")), session_key=r.get("session_key"), cause=cause,
                                      duration_s=float(r["duration_s"]) if isinstance(r.get("duration_s"), int | float)
                                      else None, slow_host=bool(r.get("slow_host")),
                                      prompt_digest=digests.get(str(r.get("session_key")))))
        elif kind == "gate" and unit:
            last_gate[unit] = r
            t.gates.append(r)
            j = judged.pop(unit, None)
            if j is not None:
                j["gate_verdict"] = r.get("verdict")
        elif kind == "judgement" and unit:
            j = dict(r)
            judged[unit] = j
            t.judgements.append(j)
        elif kind == "route":
            t.routes.append(r)
        elif kind == "human":
            t.humans.append(r)
        elif kind == "outcome":
            t.outcome = r
        elif kind == "run_exit":
            t.exit = r
    # a judge's sessions carry the cause of the attempt they judged
    causes = {(s.unit, s.attempt): s.cause for s in t.sessions if s.kind in STEP_KINDS} if t else {}
    for s in t.sessions if t else []:
        if s.kind in ("judge", "grouping"):
            s.cause = causes.get((s.unit, s.attempt))
    return t


def threads(root: Path, since: datetime | None = None) -> Iterator[Thread]:
    runs = root / "runs"
    if not runs.is_dir():
        return
    for log in sorted(runs.glob("*/*/run.jsonl")):
        t = fold(read_records(log), log.parent)
        if t is None:
            continue
        if since is not None and t.started_at:
            try:
                if datetime.fromisoformat(t.started_at.replace("Z", "+00:00")) < since:
                    continue
            except ValueError:
                pass
        yield t


def window(text: str | None, now: datetime | None = None) -> datetime | None:
    """`7d`, `24h`, `30d` (the default), or `all`."""
    now = now or datetime.now(UTC)
    text = (text or "30d").strip().lower()
    if text == "all":
        return None
    unit = text[-1:]
    try:
        n = float(text[:-1])
    except ValueError as exc:
        raise ValueError(f"window {text!r}: a number with d or h, or all") from exc
    if unit == "d":
        return now - timedelta(days=n)
    if unit == "h":
        return now - timedelta(hours=n)
    raise ValueError(f"window {text!r}: a number with d or h, or all")


def _money(sessions: Iterable[Session]) -> dict[str, Any]:
    m = Money()
    for s in sessions:
        m.add(s.usage)
    return m.to_json()


def _group(sessions: list[Session], key: Any) -> dict[str, dict[str, Any]]:
    out: dict[str, list[Session]] = defaultdict(list)
    for s in sessions:
        out[str(key(s))].append(s)
    return {k: _money(v) for k, v in sorted(out.items())}


def by_unit(ts: list[Thread]) -> list[dict[str, Any]]:
    """First visit against repeats, each repeat with one cause (OBS §2.4); per workflow and unit."""
    rows: dict[tuple[str, str], list[Session]] = defaultdict(list)
    for t in ts:
        for s in t.sessions:
            rows[(t.workflow, s.unit)].append(s)
    out = []
    for (wf, unit), ss in sorted(rows.items()):
        first = [s for s in ss if s.cause is None]
        repeats = [s for s in ss if s.cause is not None]
        times = [s.duration_s for s in ss if s.duration_s is not None]
        out.append({"workflow": wf, "unit": unit, "threads": len({s.thread_id for s in ss}),
                    "first_visit": _money(first), "repeats": _group(repeats, lambda s: s.cause),
                    "total": _money(ss), "agent_s": round(sum(times), 3) if times else None})
    return out


def prompts(ts: list[Thread]) -> list[dict[str, Any]]:
    """Each rendered step prompt's digest beside its rates, so a prompt change shows (OBS §2.4)."""
    rows: dict[tuple[str, str, str], list[Session]] = defaultdict(list)
    for t in ts:
        for s in t.sessions:
            if s.prompt_digest and s.kind in STEP_KINDS:
                rows[(t.workflow, s.unit, s.prompt_digest)].append(s)
    out = []
    for (wf, unit, digest), ss in sorted(rows.items()):
        repeats = sum(1 for s in ss if s.cause is not None)
        out.append({"workflow": wf, "unit": unit, "prompt_digest": digest, "sessions": len(ss),
                    "threads": len({s.thread_id for s in ss}), "repeat_rate": round(repeats / len(ss), 4),
                    "timeouts": sum(1 for s in ss if s.timed_out), "cost": _money(ss)})
    return out


def criteria(ts: list[Thread]) -> list[dict[str, Any]]:
    """Pass, fail and UNVERIFIABLE counts per criterion id, and gate escapes (OBS §2.4)."""
    counts: dict[tuple[str, str], dict[str, int]] = defaultdict(lambda: defaultdict(int))
    escapes: dict[tuple[str, str], int] = defaultdict(int)
    for t in ts:
        passed: set[str] = set()
        for j in t.judgements:
            for c in j.get("statuses") or []:
                cid = str(c.get("id") or c.get("n"))
                st = str(c.get("status") or "?")
                counts[(t.workflow, cid)][st] += 1
                if st == "MET" and j.get("gate_verdict") == "PROCEED":
                    passed.add(cid)
                elif st in ("UNMET", "PARTIAL") and cid in passed:
                    escapes[(t.workflow, cid)] += 1
                    passed.discard(cid)
    return [{"workflow": wf, "criterion": cid, "statuses": dict(st), "escapes": escapes.get((wf, cid), 0)}
            for (wf, cid), st in sorted(counts.items())]


def arms(ts: list[Thread]) -> list[dict[str, Any]]:
    """Counts per route and switch arm, and per gate verdict (OBS §2.4 per arm)."""
    route: dict[tuple[str, str, str], int] = defaultdict(int)
    for t in ts:
        for r in t.routes:
            route[(t.workflow, str(r.get("unit")), str(r.get("arm")))] += 1
        for g in t.gates:
            route[(t.workflow, str(g.get("unit")), f"gate:{g.get('verdict')}")] += 1
    return [{"workflow": wf, "unit": u, "arm": a, "count": n} for (wf, u, a), n in sorted(route.items())]


def timeouts(ts: list[Thread]) -> list[dict[str, Any]]:
    """Stalled sessions as their own class; timeouts sorted as far as the records say (OBS-B6)."""
    out = []
    for t in ts:
        for s in t.sessions:
            if s.stalled or s.timed_out:
                cls = "stalled" if s.stalled and not s.timed_out else "hung" if s.stalled \
                    else "slow_host" if s.slow_host else "model_silent"
                out.append({"thread_id": t.thread_id, "unit": s.unit, "attempt": s.attempt, "kind": s.kind,
                            "class": cls})
    return out


def _journal(folder: Path, key: str | None) -> list[dict[str, Any]]:
    if not key:
        return []
    path = folder / "sessions" / key / "activity.jsonl"
    try:
        lines = path.read_text(encoding="utf-8").splitlines()
    except OSError:
        return []
    out = []
    for ln in lines:
        try:
            out.append(json.loads(ln))
        except ValueError:
            continue
    return out


def profile_and_loops(ts: list[Thread]) -> tuple[dict[str, Any], list[dict[str, Any]]]:
    """Wall time per tool name and shell program word, and the loop signal (OBS-B5, §2.4); numbers and names only."""
    tool_s: dict[str, float] = defaultdict(float)
    word_s: dict[str, float] = defaultdict(float)
    loops = []
    sessions_read = 0
    for t in ts:
        if t.folder is None:
            continue
        for s in t.sessions:
            lines = _journal(t.folder, s.session_key)
            if not lines:
                continue
            sessions_read += 1
            started: dict[str, dict[str, Any]] = {}
            run_key: tuple[str, str] | None = None
            run_len = 0
            for ln in lines:
                if ln.get("ev") == "tool_started":
                    started[str(ln.get("call_id"))] = ln
                    key = (str(ln.get("name")), str(ln.get("input_summary")))
                    run_len = run_len + 1 if key == run_key else 1
                    run_key = key
                    if run_len == LOOP_REPEAT:
                        loops.append({"thread_id": t.thread_id, "session_key": s.session_key, "tool": key[0],
                                      "repeats": LOOP_REPEAT})
                elif ln.get("ev") == "tool_finished":
                    st = started.pop(str(ln.get("call_id")), None)
                    d = ln.get("duration_s")
                    if st is None or not isinstance(d, int | float):
                        continue
                    tool_s[str(st.get("name"))] += float(d)
                    if st.get("capability") == "shell" and st.get("input_summary"):
                        word = str(st["input_summary"]).split()[0].rsplit("/", 1)[-1]
                        word_s[word] += float(d)
    return ({"sessions": sessions_read, "tool_s": {k: round(v, 3) for k, v in sorted(tool_s.items())},
             "program_s": {k: round(v, 3) for k, v in sorted(word_s.items())}}, loops)


def report(root: Path, since: datetime | None = None, by: str = "unit") -> dict[str, Any]:
    ts = list(threads(root, since))
    sessions = [s for t in ts for s in t.sessions]
    profile, loops = profile_and_loops(ts)
    doc: dict[str, Any] = {
        "schema_version": 1, "since": since.isoformat() if since else None, "threads": len(ts),
        "total": _money(sessions),
        "steps_and_judges": {"steps": _money(s for s in sessions if s.kind in STEP_KINDS),
                             "judges": _money(s for s in sessions if s.kind in JUDGE_KINDS)},
        "by_executor": _group(sessions, lambda s: s.executor or "unknown"),
        "by_version": _group(sessions, lambda s: f"{s.workflow}@{s.version or '?'}"),
        "units": by_unit(ts), "criteria": criteria(ts), "arms": arms(ts), "timeouts": timeouts(ts), "prompts": prompts(ts),
        "time_profile": profile, "loops": loops,
    }
    doc["by"] = by
    return doc
