"""The run detail document (RDD §2): one thread in full, built on demand, never stored.

Sources, all opened read-only: the diagram model, the run log, the checkpoint (through the status row and
an observer graph) and each running session's live file. It calls no model and creates nothing (contract
C13). Text is scrubbed and clipped; paths are local. Facts the run has not recorded are left out or null,
never zero (CON §2.10).
"""

from __future__ import annotations

import json
from collections.abc import Mapping
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

from tempergraph.constants import SCHEMA
from tempergraph.contracts import WorkflowSpec
from tempergraph.durability.checkpoint import Snapshot, observer_graph, open_readonly, snapshot
from tempergraph.durability.status import row as status_row
from tempergraph.durability.status import split_thread
from tempergraph.model import flow
from tempergraph.model.diagram import diagram_model
from tempergraph.run.events import records, route_unit, tail
from tempergraph.security.scrub import clip, scrub
from tempergraph.store.layout import checkpoint_path, now_iso, run_dir, session_dir

TEXT_CLIP = 200
EVIDENCE_CLIP = 400
MAX_BYTES = 1_000_000
STEP_KINDS = frozenset({"step", "retry"})
JUDGE_KINDS = frozenset({"judge", "judge_reask"})
ENTERED_WORDS = ("start", "proceed", "retry", "resume", "rerun")


def _ts(value: Any) -> datetime | None:
    if not isinstance(value, str):
        return None
    try:
        return datetime.fromisoformat(value.replace("Z", "+00:00"))
    except ValueError:
        return None


def _secs(a: Any, b: Any) -> float | None:
    ta, tb = (_ts(a) if not isinstance(a, datetime) else a), (_ts(b) if not isinstance(b, datetime) else b)
    if ta is None or tb is None:
        return None
    return round((tb - ta).total_seconds(), 3)


def _text(v: Any, limit: int = TEXT_CLIP) -> str | None:
    return clip(scrub(str(v)), limit) if v not in (None, "") else None


def _entered_from(value: Any, units: Mapping[str, Any]) -> str:
    """The run log's `entered_from`, in the words of EVT §2.2 (a bare unit name is a trip back from it)."""
    v = str(value or "start")
    if v in ENTERED_WORDS or ":" in v:
        return v
    return f"back:{v}" if v in units else v


def _unit_of(node: Any) -> str | None:
    if not isinstance(node, str) or not node:
        return None
    if node in (flow.FINALIZER, flow.END):
        return node
    return node.split(".", 1)[0]


# -- plan ----------------------------------------------------------------------------------------------


def _plan(spec: WorkflowSpec, model: Mapping[str, Any]) -> list[dict[str, Any]]:
    by_unit: dict[str, list[dict[str, Any]]] = {}
    for a, b, token in model.get("edges") or []:
        if not a.endswith(".gate"):
            continue  # a human node's edges are its decision words, shown on the pause
        src, dst = a.split(".", 1)[0], route_unit(b)
        if dst is None or (dst == src and token == "RETRY"):
            continue
        by_unit.setdefault(src, [])
        edge = {"target": dst, "on": token}
        if edge not in by_unit[src]:
            by_unit[src].append(edge)
    out = []
    for u in model.get("units") or []:
        name = u["name"]
        us = spec.units.get(name)
        gated = bool(us is not None and (us.gate.judge is not None or us.gate.check is not None or us.gate.approval))
        step = us.step if us is not None else None
        judge = us.gate.judge if us is not None else None
        out.append({"name": name, "kind": u.get("kind"), "gated": gated,
                    "executor": (step.executor if step else None) or (spec.default_executor if step else None),
                    "judge_executor": (judge.executor if judge else None) or (spec.default_executor if judge else None),
                    "alias": _alias(step.model if step else None), "edges": by_unit.get(name, []), "items": None})
    out.append({"name": flow.FINALIZER, "kind": "finalizer", "gated": False, "executor": None,
                "judge_executor": None, "alias": None, "edges": [], "items": None})
    return out


def _alias(model: Any) -> str | None:
    if isinstance(model, str):
        return model
    if isinstance(model, tuple | list) and model:
        return str(model[0])
    return None


# -- folding the run log -------------------------------------------------------------------------------


class _Fold:
    """Walks the records once and builds units, sessions, budgets, touches and the open pause."""

    def __init__(self, units: Mapping[str, Any]) -> None:
        self.units_spec = units
        self.units: dict[str, dict[str, Any]] = {}
        self.sessions: dict[str, dict[str, Any]] = {}
        self.current: dict[str, dict[str, Any]] = {}  # unit -> its open attempt
        self.budgets: dict[str, dict[str, Any]] = {}
        self.touches: list[dict[str, Any]] = []
        self.pause: dict[str, Any] | None = None
        self.supervision: dict[str, Any] | None = None
        self.segment_start: dict[str, Any] | None = None
        self.segment_exit: dict[str, Any] | None = None
        self.last_unit: str | None = None
        self.plan_digest: str | None = None

    def _unit(self, name: str) -> dict[str, Any]:
        return self.units.setdefault(name, {"visits": []})

    def _visit(self, unit: str, entered_from: str = "resume") -> dict[str, Any]:
        u = self._unit(unit)
        if not u["visits"]:
            u["visits"].append({"visit": 1, "entered_from": entered_from, "attempts": []})
        return u["visits"][-1]

    def _attempt(self, unit: str, number: Any, item: Any, ts: Any) -> dict[str, Any]:
        visit = self._visit(unit)
        for a in visit["attempts"]:
            if a["attempt"] == number and a["item"] == item:
                return a
        att: dict[str, Any] = {"attempt": number, "item": item, "started_at": ts, "ended_at": None, "step": None,
                               "check": None, "judge": None, "gate": None, "repeat_cause": None}
        visit["attempts"].append(att)
        self.current[unit] = att
        return att

    def _open(self, unit: str) -> dict[str, Any] | None:
        return self.current.get(unit)

    def feed(self, r: Mapping[str, Any]) -> None:
        kind = r.get("kind")
        unit = r.get("unit") if isinstance(r.get("unit"), str) else None
        handler = getattr(self, f"_on_{kind}", None)
        if handler is not None:
            handler(r, unit)
        if unit:
            self.last_unit = unit

    def _on_run_started(self, r: Mapping[str, Any], unit: str | None) -> None:
        self.segment_start, self.segment_exit = dict(r), None
        if isinstance(r.get("plan_digest"), str):
            self.plan_digest = r["plan_digest"]

    def _on_run_exit(self, r: Mapping[str, Any], unit: str | None) -> None:
        self.segment_exit = dict(r)

    def _on_unit_entered(self, r: Mapping[str, Any], unit: str | None) -> None:
        if not unit:
            return
        u = self._unit(unit)
        u["visits"].append({"visit": r.get("visit") or len(u["visits"]) + 1,
                            "entered_from": _entered_from(r.get("entered_from"), self.units_spec), "attempts": []})
        self.current.pop(unit, None)

    def _on_attempt_start(self, r: Mapping[str, Any], unit: str | None) -> None:
        key = r.get("session_key")
        if not unit or not isinstance(key, str):
            return
        kind = r.get("session_kind")
        att = self._attempt(unit, r.get("attempt"), r.get("item"), r.get("ts"))
        s = self.sessions.get(key)
        if s is None:
            s = {"session_key": key, "kind": kind, "executor": r.get("executor"), "alias": r.get("alias"),
                 "model": None, "session_id": None, "transcript": None, "activity_path": None, "live_path": None,
                 "usage": None, "tool_calls": None, "outcome": None, "started_at": r.get("ts"), "ended_at": None,
                 "timeout_s": r.get("timeout_s"), "idle_s": r.get("idle_s"), "infra_tries": 0}
            self.sessions[key] = s
            if kind in JUDGE_KINDS:
                att["judge"] = att["judge"] or {"sessions": []}
                att["judge"]["sessions"].append(s)
            else:
                att["step"] = att["step"] or {"sessions": []}
                att["step"]["sessions"].append(s)
        else:  # an infra retry of the same session (BUD-B1): the same folder, a new process
            s["infra_tries"] += 1
            s["ended_at"] = None

    def _on_session_opened(self, r: Mapping[str, Any], unit: str | None) -> None:
        s = self.sessions.get(str(r.get("session_key")))
        if s is not None:
            s.update(model=r.get("model"), session_id=r.get("session_id"), transcript=r.get("transcript"),
                     pgid=r.get("pgid"))

    def _on_agent_run(self, r: Mapping[str, Any], unit: str | None) -> None:
        s = self.sessions.get(str(r.get("session_key")))
        if s is None:
            return
        tools = r.get("tools")
        s.update(usage=r.get("usage"), tool_calls=len(tools) if isinstance(tools, list) else None,
                 session_id=s.get("session_id") or r.get("session_id"), ended_at=r.get("ts"),
                 outcome={"ok": r.get("ok"), "timed_out": r.get("timed_out"), "stalled": r.get("stalled"),
                          "partial": r.get("partial"), "infra_cause": r.get("infra_cause"),
                          "error_kind": r.get("error_kind")})

    def _on_script(self, r: Mapping[str, Any], unit: str | None) -> None:
        if not unit:
            return
        if r.get("phase") in (None, "unit"):
            visit = self._visit(unit)
            att = self._attempt(unit, len(visit["attempts"]) + 1, r.get("item"), r.get("ts"))
            att["ended_at"] = r.get("ts")
        else:
            att = self._open(unit) or self._attempt(unit, 1, r.get("item"), r.get("ts"))
        att.setdefault("scripts", []).append({k: r.get(k) for k in (
            "name", "phase", "exit_code", "duration_s", "cached", "environmental")})

    def _on_check(self, r: Mapping[str, Any], unit: str | None) -> None:
        att = self._open(unit) if unit else None
        if att is not None:
            att["check"] = {"result": r.get("result"), "environmental": r.get("environmental"),
                            "duration_s": r.get("duration_s"), "output_path": r.get("output_path"),
                            "evidence": _text(r.get("evidence"), EVIDENCE_CLIP)}

    def _on_judgement(self, r: Mapping[str, Any], unit: str | None) -> None:
        att = self._open(unit) if unit else None
        if att is None:
            return
        statuses = [{"n": s.get("n"), "id": s.get("id"), "status": s.get("status")}
                    for s in r.get("statuses") or [] if isinstance(s, Mapping)]
        met = r.get("met") if isinstance(r.get("met"), int) else sum(1 for s in statuses if s["status"] == "MET")
        total = r.get("total") if isinstance(r.get("total"), int) else len(statuses)
        att["judge"] = att["judge"] or {"sessions": []}
        att["judge"].update(criteria=statuses, met=met, total=total, gap=r.get("gap"),
                            blockers=[{"id": b, "evidence": None, "fix": None} for b in r.get("blockers") or []],
                            confidence=r.get("confidence"), confidence_source=r.get("confidence_source"),
                            guard=r.get("guard"))

    def _on_gate(self, r: Mapping[str, Any], unit: str | None) -> None:
        att = self._open(unit) if unit else None
        if att is None:
            return
        verdict = r.get("verdict") or r.get("token")
        target = route_unit(r.get("route_target"))
        att["gate"] = {"verdict": verdict, "route_target": target, "token": r.get("token"),
                       "guard": (att.get("judge") or {}).get("guard")}
        att["ended_at"] = r.get("ts")
        if verdict == "RETRY":
            blockers = (att.get("judge") or {}).get("blockers") or []
            chk = att.get("check") or {}
            if blockers:
                att["repeat_cause"] = f"blocker:{blockers[0]['id']}"
            elif chk.get("result") == "FAIL":
                att["repeat_cause"] = "check:FAIL"
            else:
                att["repeat_cause"] = "retry"

    def _on_pause(self, r: Mapping[str, Any], unit: str | None) -> None:
        self.pause = dict(r)

    def _on_human(self, r: Mapping[str, Any], unit: str | None) -> None:
        raw = r.get("caller")
        caller: Mapping[str, Any] = raw if isinstance(raw, Mapping) else {}
        waited = _secs((self.pause or {}).get("ts"), r.get("ts")) if self.pause else None
        self.touches.append({"ts": r.get("ts"), "unit": unit, "class": r.get("touch_class") or (
            (self.pause or {}).get("pause_kind")), "action": r.get("decision"), "caller_kind": caller.get("kind"),
            "decider": r.get("decider") or caller.get("decider"), "relay": caller.get("relay"),
            "wait_s": waited, "feedback": bool(r.get("feedback"))})
        self.pause = None

    def _on_budget(self, r: Mapping[str, Any], unit: str | None) -> None:
        name = f"{unit}.{r.get('counter')}" if unit else str(r.get("counter"))
        self.budgets[name] = {"used": r.get("used"), "limit": r.get("limit"), "cause": r.get("cause")}

    def _on_supervision(self, r: Mapping[str, Any], unit: str | None) -> None:
        self.supervision = dict(r)


# -- live sessions ---------------------------------------------------------------------------------------


def _read_live(path: Path, now: datetime) -> dict[str, Any] | None:
    """The live block of RDD §2.2; a file mid-replace is never read partially (writes are atomic)."""
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return None
    if not isinstance(data, dict) or data.get("ended"):
        return None
    tool = data.get("open_tool") if isinstance(data.get("open_tool"), dict) else None
    open_tool = None
    if tool is not None:
        open_tool = {"name": tool.get("name"), "capability": tool.get("capability"),
                     "input_summary": _text(tool.get("input_summary")),
                     "elapsed": _elapsed(tool.get("started_at"), now)}
    recent = [{"name": c.get("name"), "input_summary": _text(c.get("input_summary")), "ok": c.get("ok"),
               "duration_s": c.get("duration_s")} for c in (data.get("recent") or [])[-10:] if isinstance(c, dict)]
    return {"open_tool": open_tool, "recent": recent, "last_text": _text(data.get("last_text")),
            "tokens_so_far": data.get("tokens_so_far"), "turns_so_far": data.get("turns_so_far"),
            "pgid": data.get("pgid"), "last_event_age_s": _elapsed(data.get("last_event_at"), now)}


def _elapsed(ts: Any, now: datetime) -> float | None:
    t = _ts(ts)
    return None if t is None else round(max(0.0, (now - t).total_seconds()), 1)


# -- the document ------------------------------------------------------------------------------------------


def _usage_cost(usage: Any) -> tuple[float | None, float | None]:
    if not isinstance(usage, Mapping):
        return None, None
    rep, est = usage.get("reported_cost_usd"), usage.get("estimated_cost_usd")
    return (float(rep) if isinstance(rep, int | float) else None, float(est) if isinstance(est, int | float) else None)


def _unit_cost(sessions: list[dict[str, Any]]) -> dict[str, Any]:
    rep = est = 0.0
    n_rep = n_est = unmeasured = 0
    for s in sessions:
        r, e = _usage_cost(s.get("usage"))
        if r is not None:
            rep, n_rep = rep + r, n_rep + 1
        if e is not None:
            est, n_est = est + e, n_est + 1
        if r is None and e is None and s.get("usage") is not None:
            unmeasured += 1
    figure = rep + sum(e for s in sessions for r, e in [_usage_cost(s.get("usage"))] if r is None and e is not None)
    flag = "incomplete" if unmeasured else ("complete" if sessions and n_rep == len(sessions) else "estimated")
    return {"reported": round(rep, 6) if n_rep else None, "estimated": round(est, 6) if n_est else None,
            "figure": round(figure, 6), "completeness": flag if sessions else None}


def _sessions_of(unit: dict[str, Any]) -> list[dict[str, Any]]:
    out: list[dict[str, Any]] = []
    for v in unit["visits"]:
        for a in v["attempts"]:
            for part in ("step", "judge"):
                out.extend((a.get(part) or {}).get("sessions") or [])
    return out


def _state(name: str, unit: dict[str, Any] | None, row: Mapping[str, Any], current: str | None) -> str:
    if name in {g.get("unit") for g in row.get("pending_gates") or []}:
        return "paused"
    last = next((a for v in reversed((unit or {}).get("visits") or []) for a in reversed(v["attempts"])), None)
    if last is None:
        return "skipped" if row.get("state") == "finished" else "not_reached"
    verdict = (last.get("gate") or {}).get("verdict")
    live_here = bool(row.get("alive")) and name == current
    if live_here and verdict in (None, "RETRY"):
        return "running"
    if verdict == "PROCEED":
        return "passed"
    if verdict is None and last.get("scripts") and all(sc.get("exit_code") == 0 for sc in last["scripts"]):
        return "passed"
    return "running" if live_here else "failed"


def _public_session(s: dict[str, Any], root: Path, workflow: str, task: str, live: dict[str, Any] | None
                    ) -> dict[str, Any]:
    sdir = session_dir(root, workflow, task, s["session_key"])
    out = {k: s.get(k) for k in ("session_key", "kind", "executor", "alias", "model", "session_id", "transcript",
                                  "usage", "tool_calls", "outcome", "started_at", "ended_at")}
    out["activity_path"] = str(sdir / "activity.jsonl")
    out["live_path"] = str(sdir / "live.json")
    if s.get("infra_tries"):
        out["infra_tries"] = s["infra_tries"]
    if live is not None:
        out["live"] = live
    return out


def _snapshot(root: Path, spec: WorkflowSpec, tid: str) -> Snapshot:
    with open_readonly(checkpoint_path(root, spec.name)) as saver:
        if saver is None:
            return Snapshot(exists=False)
        return snapshot(observer_graph(spec, saver), tid)


def detail(root: Path, spec: WorkflowSpec, tid: str, *, unit: str | None = None, with_live: bool = True,
           now: datetime | None = None) -> dict[str, Any] | None:
    """`status --detail <selector> --json` (RDD §2). None when `unit` names no unit of the workflow."""
    now = now or datetime.now(UTC)
    _, task = split_thread(tid)
    model = diagram_model(spec)
    if unit is not None and unit not in {u["name"] for u in model["units"]}:
        return None
    row = status_row(root, spec, tid)
    snap = _snapshot(root, spec, tid)
    values = snap.values or {}
    log = run_dir(root, spec.name, task) / "run.jsonl"
    truncated: list[str] = []
    try:
        recs = records(log) if log.exists() else None
    except Exception:  # noqa: BLE001 - RDD §4
        recs = None
    if recs is None:
        truncated.append("run_log_unreadable")
        recs = []
    fold = _Fold(spec.units)
    for r in recs:
        fold.feed(r)

    current = fold.last_unit
    alive = bool(row.get("alive"))
    open_keys = {k for k, s in fold.sessions.items() if s.get("ended_at") is None}
    units_out = []
    total_figure = 0.0
    per_unit: list[tuple[dict[str, Any], dict[str, Any]]] = []
    judgements = values.get("judgements") or {}
    for p in model["units"]:
        name = p["name"]
        u = fold.units.get(name, {"visits": []})
        _add_evidence(u, judgements.get(name) or {})
        sessions = _sessions_of(u)
        cost = _unit_cost(sessions)
        total_figure += cost["figure"]
        durations = [d for v in u["visits"] for a in v["attempts"]
                     for d in [_secs(a.get("started_at"), a.get("ended_at"))] if d is not None]
        visits = []
        for v in u["visits"]:
            attempts = []
            for a in v["attempts"]:
                out = dict(a)
                for part in ("step", "judge"):
                    if out.get(part):
                        out[part] = {**out[part], "sessions": [
                            _public_session(s, root, spec.name, task,
                                            _read_live(session_dir(root, spec.name, task, s["session_key"]) /
                                                       "live.json", now)
                                            if with_live and alive and s["session_key"] in open_keys else None)
                            for s in out[part].get("sessions") or []]}
                attempts.append(out)
            visits.append({**v, "attempts": attempts})
        entry = {"name": name, "state": _state(name, u, row, current), "visits": visits, "cost": cost,
                 "duration_s": round(sum(durations), 3) if durations else None, "share": None}
        per_unit.append((entry, cost))
        units_out.append(entry)
    for entry, cost in per_unit:
        entry["share"] = round(cost["figure"] / total_figure, 4) if total_figure > 0 else None

    doc: dict[str, Any] = {
        "schema_version": SCHEMA["detail"], "generated_at": now_iso(),
        "run": {**row, "segment": (fold.segment_start or {}).get("segment"),
                "last_seq": recs[-1]["seq"] if recs else None, "run_dir": str(run_dir(root, spec.name, task)),
                "plan_digest": model["digest"]},
        "plan": _plan(spec, model),
        "plan_stale": bool(fold.plan_digest and fold.plan_digest != model["digest"]),
        "units": units_out,
        "pause": _pause(spec, row, snap, fold.pause, now),
        "budgets": _budgets(spec, values, fold.budgets, total_figure),
        "health": _health(row, recs, fold, units_out, spec, now, root, task),
        "supervision": {"touches": fold.touches, "record": fold.supervision,
                        "hosts": (fold.supervision or {}).get("hosts")
                        or ((fold.supervision or {}).get("supervisors") or {}).get("hosts"),
                        "level": (fold.supervision or {}).get("level"),
                        "level_by": (fold.supervision or {}).get("level_by"),
                        "designed_by": (fold.supervision or {}).get("designed_by"),
                        "cost": _closed_cost(root, f"{spec.name}/{task}")
                        or (fold.supervision or {}).get("supervision_cost", (fold.supervision or {}).get("cost"))},
        "events_tail": tail(recs),
        "truncated": truncated,
    }
    if unit is not None:
        doc["units"] = [u for u in units_out if u["name"] == unit]
        doc["plan"] = [p for p in doc["plan"] if p["name"] == unit]
        return doc
    return cut(doc)


def _add_evidence(unit: dict[str, Any], judged: Mapping[str, Any]) -> None:
    """Evidence and fix lines for the unit's last judged attempt, from the checkpoint's local judgement."""
    blockers = {str(b.get("criterion")): b for b in judged.get("blockers") or [] if isinstance(b, Mapping)}
    if not blockers:
        return
    last = next((a for v in reversed(unit["visits"]) for a in reversed(v["attempts"]) if a.get("judge")), None)
    for b in ((last or {}).get("judge") or {}).get("blockers") or []:
        src = blockers.get(str(b["id"]))
        if src is not None:
            b["evidence"] = _text(src.get("evidence") or src.get("problem"), EVIDENCE_CLIP)
            b["fix"] = _text(src.get("fix"), EVIDENCE_CLIP)


def _artifact_path(spec: WorkflowSpec, values: Mapping[str, Any], unit: Any, key: str) -> str | None:
    """The local path of a file artifact, resolved against the run's workspace; None for a value."""
    us = spec.units.get(str(unit))
    if us is None or us.step is None or us.step.produces.get(key) != "file":
        return None
    v = ((values.get("artifacts") or {}).get(unit) or {}).get(key)
    path = v.get("path") if isinstance(v, Mapping) else v
    if not isinstance(path, str) or not path:
        return None
    ws = (values.get("workspace") or {}).get("path")
    p = Path(path)
    return str(p if p.is_absolute() or not ws else Path(ws) / p)


def _pause(spec: WorkflowSpec, row: Mapping[str, Any], snap: Snapshot, rec: Mapping[str, Any] | None, now: datetime
           ) -> dict[str, Any] | None:
    if row.get("state") != "paused" or not snap.interrupts:
        return None
    node, payload = snap.interrupts[0]
    p = payload if isinstance(payload, Mapping) else {}
    unit = p.get("unit") or _unit_of(node)
    since = (rec or {}).get("ts")
    resume = p.get("resume") or (row.get("pending_gates") or [{}])[0].get("resume")
    return {"unit": unit, "kind": p.get("kind") or (rec or {}).get("pause_kind"),
            "question": _text(p.get("question") or p.get("reason")),
            "artifacts": [{"key": k, "path": _artifact_path(spec, snap.values or {}, unit, k)}
                          for k in p.get("artifacts") or []],
            "decisions": list(p.get("decisions") or []), "resume": [resume] if resume else [],
            "waiting_since": since, "waiting_s": _elapsed(since, now)}


def _budgets(spec: WorkflowSpec, values: Mapping[str, Any], recorded: Mapping[str, Any], spent: float
             ) -> dict[str, Any]:
    counters = values.get("counters") or {}
    out: dict[str, Any] = {}
    for name, u in spec.units.items():
        c = counters.get(name) or {}
        if "retries" in c:
            out[f"{name}.retries"] = {"used": c.get("retries"), "limit": u.gate.retry_budget}
        for target, used in (c.get("loops") or {}).items():
            out[f"{name}.loops.{target}"] = {"used": used, "limit": u.gate.loop_budget}
    out.update({k: dict(v) for k, v in recorded.items()})
    cap = spec.run_cost_cap_usd
    return {"counters": out, "run_cost_cap": {"limit": cap, "left": round(cap - spent, 6) if cap is not None else None}}


def _health(row: Mapping[str, Any], recs: list[dict[str, Any]], fold: _Fold, units: list[dict[str, Any]],
            spec: WorkflowSpec, now: datetime, root: Path, task: str) -> dict[str, Any]:
    alive = bool(row.get("alive"))
    newest = recs[-1].get("ts") if recs else None
    silent = _elapsed(newest, now)
    stall = False
    for u in units:
        for v in u["visits"]:
            for a in v["attempts"]:
                for part in ("step", "judge"):
                    for s in (a.get(part) or {}).get("sessions") or []:
                        live = s.get("live")
                        if live is None:
                            continue
                        age = live.get("last_event_age_s")
                        silent = min(silent, age) if silent is not None and age is not None else silent
                        limit = _idle_limit(spec, u["name"], fold.sessions.get(s["session_key"]) or {})
                        if age is not None and limit and age >= 0.8 * limit:
                            stall = True
    started = fold.segment_start
    orphaned = bool(started and fold.segment_exit is None and not alive)
    cost_seg = sum(c for c in (_segment_cost(recs, (started or {}).get("seq")),) if c is not None)
    wall = _secs((started or {}).get("ts"), (fold.segment_exit or {}).get("ts") or now)
    burn = round(cost_seg / wall * 3600, 4) if wall and wall > 0 and started else None
    cap = spec.run_cost_cap_usd
    spent = sum((u["cost"] or {}).get("figure") or 0.0 for u in units)
    eta = round((cap - spent) / burn * 60, 1) if cap is not None and burn and alive else None
    waiting = _elapsed((fold.pause or {}).get("ts"), now) if row.get("state") == "paused" and fold.pause else None
    return {"alive": alive, "silent_s": silent, "suspect_stall": alive and stall, "orphaned": orphaned,
            "waiting_for_person_s": waiting, "burn_usd_per_h": burn, "cap_eta_min": eta}


def _idle_limit(spec: WorkflowSpec, unit: str, s: Mapping[str, Any]) -> float | None:
    if isinstance(s.get("idle_s"), int | float):
        return float(s["idle_s"])
    us = spec.units.get(unit)
    if us is not None and us.step is not None and us.step.idle_s:
        return float(us.step.idle_s)
    return None


def _segment_cost(recs: list[dict[str, Any]], since: Any) -> float | None:
    if not isinstance(since, int):
        return None
    total = 0.0
    for r in recs:
        if r.get("kind") == "agent_run" and isinstance(r.get("seq"), int) and r["seq"] > since:
            rep, est = _usage_cost(r.get("usage"))
            total += rep if rep is not None else (est or 0.0)
    return total


def cut(doc: dict[str, Any], limit: int = MAX_BYTES) -> dict[str, Any]:
    """RDD §2.1: above `limit` bytes drop `events_tail`, then the attempt detail of passed units."""
    def size() -> int:
        return len(json.dumps(doc, ensure_ascii=False, default=str).encode("utf-8"))

    if size() <= limit:
        return doc
    doc["events_tail"] = []
    doc["truncated"] = [*doc.get("truncated", []), "events_tail"]
    if size() <= limit:
        return doc
    for u in doc["units"]:
        if u["state"] == "passed":
            for v in u["visits"]:
                v["attempts_count"] = len(v["attempts"])
                v["attempts"] = []
    doc["truncated"].append("passed_attempts")
    return doc


def _closed_cost(root: Path, tid: str) -> dict[str, Any] | None:
    """SCO §2.5's closed figures for the thread, when its supervision has closed; else the record's null."""
    from tempergraph.observe.supervision_cost import closed_for

    line = closed_for(root).get(tid)
    return {k: line.get(k) for k in ("marginal", "turn", "completeness", "observations")} if line else None
