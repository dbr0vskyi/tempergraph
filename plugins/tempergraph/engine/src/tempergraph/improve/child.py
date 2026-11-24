"""The loop child: judged lenses after a final exit, then filing (SIL-B1, SIL-B10, SIL-B17, SIL-B18; T12.1.5).

The run's exit writes a hand-off ticket (ids, enums and paths only, never request text) under the home and
starts `python -m tempergraph.improve.child drain` through the detached child launcher (SEC-B7). The child
claims each ticket, runs the friction judge over the findings' metadata, decides each candidate with the filing
rules and files. Its failure never reaches the parent: the parent has exited and its exit code is written.

Release 1 shape: a fixed engine program of one judged session per ticket, not a compiled workflow; the judge
follows the run's judge executor on the mid-tier alias for 1800 s. The outcome lens spends no session: its
candidates are the final criteria the outcome gate's own judge graded unmet, and they file only while that judge
is `accepted` by calibration (SIL-B7, JCL); until then they are recorded `uncalibrated`. Like all filing code,
this module never opens the evidence file.
"""

from __future__ import annotations

import contextlib
import dataclasses
import json
import os
import re
import sys
import time
import uuid
from collections.abc import Callable, Mapping, Sequence
from pathlib import Path
from typing import Any

from tempergraph.contracts import SessionOptions, SessionRequest, ViewSet, WorkflowSpec
from tempergraph.docs import append_jsonl, write_json
from tempergraph.executors.registry import Registry, default_registry
from tempergraph.improve import autonomy, filing, params
from tempergraph.improve.codehost import CodeHost, GhCodeHost
from tempergraph.improve.record import read_findings
from tempergraph.run.log import Ledger, LiveSink, estimate
from tempergraph.store.layout import home_path, now_iso, run_dir

ALIAS = "medium"
EFFORT = "max"  # the loop reads session logs: Sonnet thinks at its most (SIL-B17)
TIMEOUT_S = 1800
clock = time.time  # replaceable, so a test runs the wait of SIL-B25 on a fake clock
sleep = time.sleep
FENCE = re.compile(r"```(?:json)?\s*\n(.*?)\n```", re.S)
BRIEF = """You review the friction of one workflow run for a self-improvement loop.

Each finding below was derived by rules from the run's records: a cause code, the side the rule blames
(`engine`, `workflow`, `executor:<name>` or `host`), the unit and a count. You see metadata only, never the
request or the outputs. For each finding decide whether the fault really lies on the side named, and how sure
you are (0 to 1). Say `attributed: false` when the records point elsewhere, for example a retry burst that
follows an infrastructure failure, or a check failure that a person's ruling caused.

End with one fenced JSON block:
```json
{"findings": [{"fingerprint": "<id>", "attributed": true, "confidence": 0.8}]}
```"""


def tickets_dir(home: Path) -> Path:
    return home / "improve" / "tickets"


def loop_log(root: Path, workflow: str, task_id: str) -> Path:
    return run_dir(root, workflow, task_id) / "loop.jsonl"  # LOS-B7, LOS-B8, LOS-B9


def alias_of(t: Mapping[str, Any]) -> str:
    """The alias of the loop's own sessions: the run setting `loop_model` the ticket carries, else `medium`."""
    return str(t.get("alias") or ALIAS)


def options_of(t: Mapping[str, Any]) -> SessionOptions:
    """The options of the loop's own sessions: the run setting `loop_effort` the ticket carries, else `max`."""
    return SessionOptions(effort=t.get("effort") or EFFORT)  # type: ignore[arg-type]


def mode() -> str:
    return os.environ.get("TEMPERGRAPH_LOOP", "detached")


def hand_off(root: Path, spec: WorkflowSpec, task_id: str, thread: str, summary: Mapping[str, Any], *,
             dry_run: bool, judge_executor: str, home: Path | None = None, operator_review: str | None = None,
             run_cost_usd: float = 0.0, trial: bool = False, daily_cap_usd: float | None = None,
             loop_model: str | None = None, loop_effort: str | None = None) -> Path | None:
    """Writes the ticket when a judged lens fired at this final exit and there is a fault to judge, when the
    outcome lens has candidates, or when the session review (SRV-B13, SRV-B14, SRV-B15) has a depth other than none;
    a `signals` review whose plan has no depth (a clean first-pass stable run) writes none (SIL-B1, SRV-B4)."""
    from tempergraph.improve import proposals as prp
    from tempergraph.improve import review
    from tempergraph.improve.calibration import has_score
    from tempergraph.improve.record import unit_decls

    lenses = summary.get("lenses") or {}
    friction = bool(lenses.get("friction")) and bool(summary.get("fault_fingerprints"))
    outcome = bool(summary.get("outcome_fingerprints"))  # graded by the outcome gate's own judge: no new session
    final = "lenses" in summary  # a final exit (SIL-B8)
    prob = review.probation(root, spec.name, spec.version)
    depth = review.effective(spec.session_review, operator_review, spec.improvement_mode, prob, trial) \
        if final else "off"
    reason = "trial" if trial else "probation" if prob and spec.improvement_mode != "dev" else \
        "dev" if spec.improvement_mode == "dev" else "signal"
    if depth == "signals":  # SIL-B1, SRV-B4: a `signals` plan with no depth is no review, so it starts no child
        try:
            probe = review.plan_for(
                {"state_root": str(root), "workflow": spec.name, "task_id": task_id, "workflow_version": spec.version,
                 "review": "signals", "mode": spec.improvement_mode, "run_cost_usd": float(run_cost_usd or 0.0),
                 "fingerprints": list(summary.get("fingerprints") or []),
                 "daily_cap_usd": autonomy.daily_cap(spec.improvement_mode, daily_cap_usd)}, reason=reason)
            if probe["depth"] == "none":
                depth = "off"
        except Exception:  # noqa: BLE001 - the loop is best effort: when the plan cannot be made, keep the setting
            pass
    if not (friction or outcome) and depth == "off":
        return None
    tid = uuid.uuid4().hex[:16]
    ticket = {"schema_version": 1, "ticket_id": tid, "thread": thread, "workflow": spec.name,
              "workflow_version": spec.version, "task_id": task_id, "state_root": str(root),
              "issue_repository": spec.issue_repository, "mode": spec.improvement_mode, "dry_run": dry_run,
              "executor": judge_executor, "fingerprints": list(summary.get("fingerprints") or []),
              "lenses": {"friction": friction, "outcome": outcome},
              "outcome_calibrated": outcome and has_score(spec, "outcome", root), "at": now_iso(),
              "review": depth, "review_reason": reason, "run_cost_usd": round(float(run_cost_usd or 0.0), 6),
              "units": unit_decls(spec) if depth != "off" else {},
              "autonomy": prp.autonomy(spec, os.environ.get("TEMPERGRAPH_AUTONOMY")),
              "daily_cap_usd": autonomy.daily_cap(spec.improvement_mode, daily_cap_usd),
              "alias": loop_model or ALIAS, "effort": loop_effort or EFFORT,
              "package_root": str(spec.package_root) if spec.package_root else None}
    path = tickets_dir(home or home_path()) / f"{tid}.json"
    write_json(path, ticket)
    return path


def launch(home: Path | None = None) -> bool:
    from tempergraph import detach

    return detach.start("tempergraph.improve.child", ("drain",), home or home_path())


def drain(home: Path | None = None, registry: Registry | None = None,
          host: Callable[[], CodeHost] = GhCodeHost) -> list[dict[str, Any]]:
    """Claims and processes every waiting ticket, oldest first; one ticket's failure never stops the next."""
    folder = tickets_dir(home or home_path())
    done: list[dict[str, Any]] = []
    for path in sorted(folder.glob("*.json"), key=lambda p: p.stat().st_mtime) if folder.is_dir() else ():
        claim = path.with_suffix(".claimed")
        try:
            os.replace(path, claim)  # one child per ticket
        except OSError:
            continue
        try:
            t = json.loads(claim.read_text(encoding="utf-8"))
            done.append(process(t, registry or default_registry(), host()))
        except Exception as exc:  # noqa: BLE001 - the loop is best effort (SIL-B1)
            done.append({"ticket": path.stem, "error": type(exc).__name__})
        finally:
            claim.unlink(missing_ok=True)
    return done


def _history(root: Path, workflow: str, thread: str) -> list[dict[str, Any]]:
    out: list[dict[str, Any]] = []
    base = root / "runs" / workflow
    for d in sorted(base.iterdir()) if base.is_dir() else ():
        out += [f for f in read_findings(root, workflow, d.name) if f.get("thread") != thread]
    return out


def _records(root: Path, workflow: str, task_id: str) -> list[dict[str, Any]]:
    try:
        lines = (run_dir(root, workflow, task_id) / "run.jsonl").read_text(encoding="utf-8").splitlines()
    except OSError:
        return []
    out = []
    for ln in lines:
        with contextlib.suppress(ValueError):
            r = json.loads(ln)
            if isinstance(r, dict):
                out.append(r)
    return out


def prompt(findings: Sequence[Mapping[str, Any]], records: Sequence[Mapping[str, Any]]) -> str:
    """Metadata only: findings, and the last segment's record kinds per unit with criterion ids."""
    start = max((i for i, r in enumerate(records) if r.get("kind") == "run_started"), default=0)
    counts: dict[str, dict[str, int]] = {}
    blockers: dict[str, set[str]] = {}
    for r in records[start:]:
        unit = f"{r['child']}/{r.get('unit') or '-'}" if r.get("child") else str(r.get("unit") or "-")  # SWF-B9
        k = str(r.get("kind") or "")
        counts.setdefault(unit, {})[k] = counts.get(unit, {}).get(k, 0) + 1
        for cid in r.get("blockers") or () if k == "judgement" else ():
            blockers.setdefault(unit, set()).add(str(cid))
    rows = [f"- `{f.get('fingerprint')}` cause `{f.get('cause')}` class {f.get('class')} side `{f.get('side')}` "
            f"unit `{(f['child'] + '/') if f.get('child') else ''}{f.get('unit') or '-'}` count {f.get('count')}"
            + (f" (a child of `{f.get('parent')}`: workflow `{f.get('workflow')}`)" if f.get("child") else "")
            for f in findings]
    seg = [f"- `{u}`: " + ", ".join(f"{k} {n}" for k, n in sorted(c.items()))
           + (f"; blocked on {', '.join(sorted(blockers[u]))}" if u in blockers else "") for u, c in counts.items()]
    return BRIEF + "\n\n## Findings\n" + "\n".join(rows) + "\n\n## The segment's records\n" + "\n".join(seg) + "\n"


def parse(text: str) -> dict[str, dict[str, Any]]:
    blocks = FENCE.findall(text or "")
    if not blocks:
        return {}
    try:
        doc = json.loads(blocks[-1])
    except ValueError:
        return {}
    out: dict[str, dict[str, Any]] = {}
    for row in doc.get("findings") or [] if isinstance(doc, dict) else []:
        if isinstance(row, dict) and isinstance(row.get("confidence"), (int, float)):
            out[str(row.get("fingerprint"))] = {"attributed": row.get("attributed") is True,
                                                "confidence": max(0.0, min(1.0, float(row["confidence"])))}
    return out


def _latest(findings: Sequence[Mapping[str, Any]], fps: set[str]) -> list[Mapping[str, Any]]:
    by: dict[str, Mapping[str, Any]] = {}
    for f in findings:
        if str(f.get("fingerprint")) in fps:
            by[str(f.get("fingerprint"))] = f
    return list(by.values())


def _retry_usage_limited(t: Mapping[str, Any], registry: Registry, log: Path, limited: Sequence[Mapping[str, Any]],
                         cost: dict[str, float], left: float | None) -> None:
    """SIL-B25, SIL-B26: wait for the latest reset reported within `review.retry_wait_hours` and run those reviews once
    more, every record marked `retry`, within the money caps. Never waits in the foreground (`TEMPERGRAPH_LOOP=inline`)
    or for an unknown or distant reset, and never runs a third time. A retry's failure is recorded and stops nothing."""
    if mode() == "inline":
        return
    bound = clock() + float(params.value("review.retry_wait_hours")) * 3600
    due = [e for e in limited if isinstance(e.get("resets_at"), int | float) and not isinstance(e.get("resets_at"), bool)
           and float(e["resets_at"]) <= bound]
    if not due:
        return
    try:
        from tempergraph.improve import review

        wait = max(float(e["resets_at"]) for e in due) - clock()
        if wait > 0:
            sleep(wait)
        spent = cost["reported"] + cost["estimated_only"]
        rv = review.run(t, registry, reason=str(t.get("review_reason") or "dev"),
                        keys=[str(e["session_key"]) for e in due], force_full=True, retry=True,
                        room=None if left is None else round(left - spent, 6))
        cost["reported"] += rv["cost"]["reported"]
        cost["estimated_only"] += rv["cost"]["estimated_only"]
    except Exception as exc:  # noqa: BLE001 - best effort (SIL-B1); the failure is a review that raised (SRV-B29)
        append_jsonl(log, {"ts": now_iso(), "kind": "review_failed", "error_class": "error",
                           "error": type(exc).__name__, "retry": True})


def process(t: Mapping[str, Any], registry: Registry, host: CodeHost) -> dict[str, Any]:
    root = Path(str(t["state_root"]))
    wf, task, thread = str(t["workflow"]), str(t["task_id"]), str(t["thread"])
    log = loop_log(root, wf, task)
    mine = _latest(read_findings(root, wf, task), set(t.get("fingerprints") or ()))
    faults = [f for f in mine if f.get("class") == "fault" and f.get("lens") not in ("outcome", "review")]
    append_jsonl(log, {"ts": now_iso(), "kind": "loop_started", "ticket": t.get("ticket_id"),
                       "lenses": t.get("lenses"), "findings": len(mine)})
    judged: dict[str, dict[str, Any]] = {}
    cost = {"reported": 0.0, "estimated_only": 0.0}
    left = autonomy.room(t, root)  # SIL-B19, SIL-B20: stable mode's daily cap skips the judges; records are still written
    capped = left is not None and left <= 0
    if capped:
        append_jsonl(log, {"ts": now_iso(), "kind": "loop_skipped", "step": "judges", "reason": "daily_cap"})
    if (t.get("lenses") or {}).get("friction") and faults and not capped:
        ex = registry.get(str(t.get("executor") or "claude"))
        sdir = run_dir(root, wf, task) / "loop" / "sessions" / f"friction-{t.get('ticket_id')}"
        req = SessionRequest(kind="judge", prompt=prompt(faults, _records(root, wf, task)), workdir=root,
                             alias=alias_of(t), session_key=f"loop.{t.get('ticket_id')}.judge", timeout_s=TIMEOUT_S,
                             session_dir=sdir, options=options_of(t))
        res = ex.run_judge(req, ViewSet(), LiveSink(sdir))
        if res.usage.reported_cost_usd is not None:
            cost["reported"] += res.usage.reported_cost_usd
        else:
            cost["estimated_only"] += float(res.usage.estimated_cost_usd or estimate(res.usage, res.model) or 0.0)
        judged = parse(res.text) if res.ok else {}
        append_jsonl(log, {"ts": now_iso(), "kind": "loop_judged", "lens": "friction", "executor": ex.name,
                           "alias": alias_of(t), "effort": options_of(t).effort, "ok": res.ok, "parsed": bool(judged), "usage": dataclasses.asdict(res.usage),
                           "session_id": res.session_id})
    cands: list[filing.Candidate] = []
    for f in mine:
        if f.get("lens") == "review":  # SRV-B28: a finding made of review observations never files, in any run
            continue
        if f.get("lens") == "outcome":  # SIL-B7: files only once the outcome gate's judge is `accepted` (JCL)
            cands.append(filing.Candidate(finding=f, lens="outcome", calibrated=bool(t.get("outcome_calibrated")),
                                          request_digest=f.get("request_digest")))
            continue
        if not (t.get("lenses") or {}).get("friction"):  # a review-only ticket files no friction finding
            continue
        j = judged.get(str(f.get("fingerprint")))
        cands.append(filing.Candidate(finding=f, lens="friction", confidence=j["confidence"] if j else None,
                                      attributed=bool(j and j["attributed"]), request_digest=f.get("request_digest")))
    history = _history(root, wf, thread)
    decisions = [filing.decide(c, history, str(t.get("issue_repository") or "")) for c in cands]
    if t.get("autonomy") == "record":  # PRP-B11: findings, evidence and ledger rows only
        results = [{"op": "recorded", "fingerprint": d.candidate.finding.get("fingerprint"), "reason": "autonomy_record"}
                   for d in decisions]
    else:
        results = filing.file(decisions, host, filing.Outbox.at(root), dry_run=bool(t.get("dry_run")))
    for r in results:  # IMD-B21 loop events, ids and enums only
        kind = {"filed": "issue_filed", "commented": "issue_commented"}.get(str(r.get("op")), "loop_result")
        append_jsonl(log, {"ts": now_iso(), "kind": kind, **r})
    limited: list[dict[str, Any]] = []  # SIL-B25: the reviews that failed as `usage_limit`, with the reported reset
    if str(t.get("review") or "off") != "off" and not capped:  # SRV-B13, SRV-B14, SRV-B15: after filing; its results never file (SRV-B7)
        try:
            from tempergraph.improve import review

            spent = cost["reported"] + cost["estimated_only"]  # the judges above came out of the day's room too
            rv = review.run(t, registry, reason=str(t.get("review_reason") or "dev"),
                            room=None if left is None else round(left - spent, 6))  # SRV-B21, SIL-B20
            cost["reported"] += rv["cost"]["reported"]
            cost["estimated_only"] += rv["cost"]["estimated_only"]
            limited = list(rv.get("usage_limit") or [])
        except Exception as exc:  # noqa: BLE001 - the review is best effort (SRV-B1, SRV-B20, SRV-B21, SRV-B22, SRV-B18)
            append_jsonl(log, {"ts": now_iso(), "kind": "review_failed", "error_class": "error",
                               "error": type(exc).__name__})  # SRV-B29: names no session, counts as one review
    acted: dict[str, Any] = {}
    try:  # PRP-B11: the loop's own proposal and trial, after its judges and within the day's room
        acted = autonomy.act(t, registry, host, log)
    except Exception as exc:  # noqa: BLE001 - best effort (SIL-B1)
        append_jsonl(log, {"ts": now_iso(), "kind": "loop_skipped", "step": "propose", "reason": "error",
                           "error": type(exc).__name__})
    _retry_usage_limited(t, registry, log, limited, cost, left)  # SIL-B25, SIL-B26: once, before the summary
    try:  # SIL-B22: one summary per ticket for `attention` and the detail document; never stops the loop
        from tempergraph.improve import loop_summary

        append_jsonl(log, loop_summary.build(root, wf, task, results))
    except Exception:  # noqa: BLE001 - best effort (SIL-B1)
        pass
    Ledger(path=root / "ledger.jsonl").append({"kind": "loop", "thread_id": thread, "workflow": wf,
                                               "workflow_version": t.get("workflow_version"), "cost": cost,
                                               "ops": sorted({str(r.get("op")) for r in results})})
    return {"ticket": t.get("ticket_id"), "thread": thread, "results": results, "cost": cost, "acted": acted}


def main(argv: Sequence[str]) -> int:
    if list(argv) != ["drain"]:
        return 2
    drain()
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
