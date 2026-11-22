"""Harvest of judge misses into calibration case candidates, and replay of judges on kept cases (LIF-B7 to LIF-B16,
JCL-B9, JCL-B10, EVS-B13, EVS-B14).

A harvested candidate is local: it is written under the state root, holds ids, paths and statuses only, and
enters a package's gold set only after a person reviewed it and wrote its labels.
"""

from __future__ import annotations

import hashlib
import json
import uuid
from collections import defaultdict
from pathlib import Path
from typing import Any

from tempergraph.contracts import WorkflowSpec
from tempergraph.docs import append_jsonl, write_json
from tempergraph.improve import calibration
from tempergraph.store.layout import now_iso, run_dir

REPLAY_CAP_USD = 20.0


def harvest_dir(root: Path, gate: str) -> Path:
    return root / "evals" / "harvest" / gate


def _workspace(root: Path, workflow: str, thread: str) -> dict[str, Any]:
    from tempergraph.run.events import records

    task = thread.split("/", 1)[-1]
    try:
        recs = records(run_dir(root, workflow, task) / "run.jsonl")
    except OSError:
        return {}
    ws: dict[str, Any] = next((r for r in reversed(recs) if r.get("kind") == "workspace"), {})
    return {k: ws.get(k) for k in ("mode", "branch", "base_commit", "path") if ws.get(k)}


def harvest(root: Path, spec: WorkflowSpec, gate: str) -> list[dict[str, Any]]:
    """`evals harvest`: one candidate per judged attempt a recorded label disagreed with (a gate escape, a
    person's override or pushback, an audit disagreement, a rerun). The expected status is the opposite of what
    the gate said: `UNMET` where it proceeded, `MET` where it blocked."""
    from tempergraph.improve import reliability

    g, step, _ = calibration.gate_spec(spec, gate)
    misses: dict[tuple[str, Any], list[dict[str, Any]]] = defaultdict(list)
    for lab in reliability.read_labels(root, spec.name):
        if lab.get("unit") == gate and lab.get("value") == "disagree":
            misses[(str(lab.get("thread")), lab.get("gate_record"))].append(lab)
    produced = sorted(step.produces) if step is not None else []
    blockers = sorted(calibration.judged_blockers(g))
    out = []
    for (thread, seq), labs in sorted(misses.items(), key=lambda kv: (kv[0][0], str(kv[0][1]))):
        cid = "h-" + hashlib.sha256(f"{thread}\0{seq}".encode()).hexdigest()[:10]
        proceeded = str(labs[0].get("gate_verdict")) in ("PROCEED", "NEXT")
        named = sorted({str(x["criterion_id"]) for x in labs if x.get("criterion_id")})
        case = {"schema_version": 1, "case_id": cid, "gate": gate, "provenance": "harvested", "state": "candidate",
                "origin": {"thread": thread, "run_id": labs[0].get("run_id"), "attempt": labs[0].get("attempt"),
                           "gate_verdict": labs[0].get("gate_verdict"),
                           "labels": [{"label_id": x.get("label_id"), "kind": x.get("label_kind")} for x in labs]},
                "suggested": [{"criterion": c, "expected": "UNMET" if proceeded else "MET"}
                              for c in (named or blockers)],
                "subject": {"produces": produced, "workspace": _workspace(root, spec.name, thread)},
                "labels": [], "harvested_at": now_iso()}
        path = harvest_dir(root, gate) / cid / "case.json"
        new = not path.exists()
        if new:
            path.parent.mkdir(parents=True, exist_ok=True)
            write_json(path, case)
        out.append({"case_id": cid, "path": str(path), "new": new, "thread": thread,
                    "suggested": case["suggested"]})
    return out


def replay(spec: WorkflowSpec, root: Path, executor: Any, *, cap_usd: float | None = None,
           write: bool = True) -> dict[str, Any]:
    """`evals replay`: each judged gate's judge once on every kept case, compared with the statuses its latest
    complete score recorded. Judge sessions only; a cap reached keeps the record `partial`."""
    from tempergraph.improve import suites

    suites.refuse_live("judge", executor)
    cap = REPLAY_CAP_USD if cap_usd is None else float(cap_usd)
    spent, partial = 0.0, False
    gates = []
    for gate in calibration.judged_gates(spec):
        if spec.package_root is None:
            break
        g, _, _ = calibration.gate_spec(spec, gate)
        us, _ = calibration.usable(spec, gate)
        complete = [s for s in calibration.scores(spec.package_root, gate) if not s.get("partial")
                    and not s.get("level")]
        if not us or not complete:
            continue
        recorded = {r["case"]: r for r in complete[-1].get("results") or []
                    if r.get("variant") == "base" and r.get("repeat") == 1}
        same = compared = verdict_same = cases = 0
        flips = []
        for u in us:
            was = recorded.get(u.case.case_id)
            if was is None:
                continue
            if spent >= cap:
                partial = True
                break
            jd = calibration.judge_once(spec, gate, calibration.base_subject(u.case, g.criteria), executor,
                                        f"replay.{u.case.case_id}")
            spent += jd.cost
            cases += 1
            verdict_same += int(jd.verdict == was.get("verdict"))
            for cid, status in sorted(jd.statuses.items()):
                before = (was.get("statuses") or {}).get(cid)
                compared += 1
                same += int(status == before)
                if status != before:
                    flips.append({"case": u.case.case_id, "criterion": cid, "was": before, "now": status})
        gates.append({"gate": gate, "score_id": complete[-1].get("score_id"), "cases": cases,
                      "statuses_compared": compared, "agreement": round(same / compared, 4) if compared else None,
                      "verdict_agreement": round(verdict_same / cases, 4) if cases else None, "flips": flips})
    rec = {"schema_version": 1, "replay_id": uuid.uuid4().hex[:12], "at": now_iso(), "workflow": spec.name,
           "partial": partial, "cost_usd": round(spent, 6), "cap_usd": cap, "gates": gates}
    if write:
        append_jsonl(root / "evals" / "replays.jsonl", rec)
    return rec


def read_candidate(path: Path) -> dict[str, Any]:
    return dict(json.loads(path.read_text(encoding="utf-8")))
