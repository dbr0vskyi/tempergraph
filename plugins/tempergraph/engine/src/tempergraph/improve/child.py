"""The loop child: judged lenses after a final exit, then filing (SIL-B1, §2.2, §5; T12.1.5).

The run's exit writes a hand-off ticket (ids, enums and paths only, never request text) under the home and
starts `python -m tempergraph.improve.child drain` through the detached child launcher (SEC §2.2). The child
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
import uuid
from collections.abc import Callable, Mapping, Sequence
from pathlib import Path
from typing import Any

from tempergraph.contracts import SessionRequest, ViewSet, WorkflowSpec
from tempergraph.docs import append_jsonl, write_json
from tempergraph.executors.registry import Registry, default_registry
from tempergraph.improve import filing
from tempergraph.improve.codehost import CodeHost, GhCodeHost
from tempergraph.improve.record import read_findings
from tempergraph.run.log import Ledger, LiveSink, estimate
from tempergraph.store.layout import home_path, now_iso, run_dir

ALIAS = "medium"
TIMEOUT_S = 1800
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
    return run_dir(root, workflow, task_id) / "loop.jsonl"  # LOS §2.1


def mode() -> str:
    return os.environ.get("TEMPERGRAPH_LOOP", "detached")


def hand_off(root: Path, spec: WorkflowSpec, task_id: str, thread: str, summary: Mapping[str, Any], *,
             dry_run: bool, judge_executor: str, home: Path | None = None) -> Path | None:
    """Writes the ticket when a judged lens fired at this final exit and there is a fault to judge."""
    from tempergraph.improve.calibration import has_score

    lenses = summary.get("lenses") or {}
    friction = bool(lenses.get("friction")) and bool(summary.get("fault_fingerprints"))
    outcome = bool(summary.get("outcome_fingerprints"))  # graded by the outcome gate's own judge: no new session
    if not (friction or outcome):
        return None
    tid = uuid.uuid4().hex[:16]
    ticket = {"schema_version": 1, "ticket_id": tid, "thread": thread, "workflow": spec.name,
              "workflow_version": spec.version, "task_id": task_id, "state_root": str(root),
              "issue_repository": spec.issue_repository, "mode": spec.improvement_mode, "dry_run": dry_run,
              "executor": judge_executor, "fingerprints": list(summary.get("fingerprints") or []),
              "lenses": {"friction": friction, "outcome": outcome},
              "outcome_calibrated": outcome and has_score(spec, "outcome", root), "at": now_iso()}
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
        unit = str(r.get("unit") or "-")
        k = str(r.get("kind") or "")
        counts.setdefault(unit, {})[k] = counts.get(unit, {}).get(k, 0) + 1
        for cid in r.get("blockers") or () if k == "judgement" else ():
            blockers.setdefault(unit, set()).add(str(cid))
    rows = [f"- `{f.get('fingerprint')}` cause `{f.get('cause')}` class {f.get('class')} side `{f.get('side')}` "
            f"unit `{f.get('unit') or '-'}` count {f.get('count')}" for f in findings]
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


def process(t: Mapping[str, Any], registry: Registry, host: CodeHost) -> dict[str, Any]:
    root = Path(str(t["state_root"]))
    wf, task, thread = str(t["workflow"]), str(t["task_id"]), str(t["thread"])
    log = loop_log(root, wf, task)
    mine = _latest(read_findings(root, wf, task), set(t.get("fingerprints") or ()))
    faults = [f for f in mine if f.get("class") == "fault" and f.get("lens") != "outcome"]
    append_jsonl(log, {"ts": now_iso(), "kind": "loop_started", "ticket": t.get("ticket_id"),
                       "lenses": t.get("lenses"), "findings": len(mine)})
    judged: dict[str, dict[str, Any]] = {}
    cost = {"reported": 0.0, "estimated_only": 0.0}
    if (t.get("lenses") or {}).get("friction") and faults:
        ex = registry.get(str(t.get("executor") or "claude"))
        sdir = run_dir(root, wf, task) / "loop" / "sessions" / f"friction-{t.get('ticket_id')}"
        req = SessionRequest(kind="judge", prompt=prompt(faults, _records(root, wf, task)), workdir=root,
                             alias=ALIAS, session_key=f"loop.{t.get('ticket_id')}.judge", timeout_s=TIMEOUT_S,
                             session_dir=sdir)
        res = ex.run_judge(req, ViewSet(), LiveSink(sdir))
        if res.usage.reported_cost_usd is not None:
            cost["reported"] += res.usage.reported_cost_usd
        else:
            cost["estimated_only"] += float(res.usage.estimated_cost_usd or estimate(res.usage, res.model) or 0.0)
        judged = parse(res.text) if res.ok else {}
        append_jsonl(log, {"ts": now_iso(), "kind": "loop_judged", "lens": "friction", "executor": ex.name,
                           "alias": ALIAS, "ok": res.ok, "parsed": bool(judged), "usage": dataclasses.asdict(res.usage),
                           "session_id": res.session_id})
    cands: list[filing.Candidate] = []
    for f in mine:
        if f.get("lens") == "outcome":  # SIL-B7: files only once the outcome gate's judge is `accepted` (JCL)
            cands.append(filing.Candidate(finding=f, lens="outcome", calibrated=bool(t.get("outcome_calibrated")),
                                          request_digest=f.get("request_digest")))
            continue
        j = judged.get(str(f.get("fingerprint")))
        cands.append(filing.Candidate(finding=f, lens="friction", confidence=j["confidence"] if j else None,
                                      attributed=bool(j and j["attributed"]), request_digest=f.get("request_digest")))
    history = _history(root, wf, thread)
    decisions = [filing.decide(c, history, str(t.get("issue_repository") or "")) for c in cands]
    results = filing.file(decisions, host, filing.Outbox.at(root), dry_run=bool(t.get("dry_run")))
    for r in results:  # IMD §2.3 loop events, ids and enums only
        kind = {"filed": "issue_filed", "commented": "issue_commented"}.get(str(r.get("op")), "loop_result")
        append_jsonl(log, {"ts": now_iso(), "kind": kind, **r})
    Ledger(path=root / "ledger.jsonl").append({"kind": "loop", "thread_id": thread, "workflow": wf,
                                               "workflow_version": t.get("workflow_version"), "cost": cost,
                                               "ops": sorted({str(r.get("op")) for r in results})})
    return {"ticket": t.get("ticket_id"), "thread": thread, "results": results, "cost": cost}


def main(argv: Sequence[str]) -> int:
    if list(argv) != ["drain"]:
        return 2
    drain()
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
