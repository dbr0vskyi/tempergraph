"""Labels derived from runs, judge reliability per binding, the labelling queue and the binding-shift watch
(FBK-B9, FBK-B14; plan T12.3).

Model-free and metadata only: a label is ids, enums, a verdict, a confidence and the judge binding, never
request, output or feedback text (FBK-AC3). The `explicit` kind is written by `label` (observe/labels.py);
every other kind is derived here from the run log and the ledger, at each exit, with a deterministic id so a
second derivation of the same judgement writes nothing new.

A run's ledger row holds the pull request it led to (FIN-B11) and the loop reads it into `later[]`; `pr_state`
labels are still not derived here; harvest (FBK-B6) is release 2. Audit labels come from `audit_judge` records when a run has them.
"""

from __future__ import annotations

import hashlib
import json
import random
from collections.abc import Callable, Iterable, Mapping, Sequence
from dataclasses import dataclass, field
from datetime import UTC, datetime, timedelta
from pathlib import Path
from typing import Any

from tempergraph.improve import params
from tempergraph.observe.labels import binding as binding_of
from tempergraph.run.events import records
from tempergraph.store.layout import now_iso, run_dir

BINDING_FIELDS = ("executor", "executor_version", "alias", "model_slug", "brief_digest", "criteria_digest")
EXECUTOR_FIELDS = frozenset({"executor", "executor_version", "alias", "model_slug"})
BLOCKS = frozenset({"RETRY", "BACK", "ESCALATE"})
ANCHORS = (1.0, 0.75, 0.5, 0.25)  # SSN-B8, SSN-B9, SSN-B10
GRADES = ("unmeasured", "unreliable", "reliable")


def _ts(text: Any) -> datetime | None:
    try:
        d = datetime.fromisoformat(str(text).replace("Z", "+00:00"))
    except ValueError:
        return None
    return d if d.tzinfo else d.replace(tzinfo=UTC)


def _jsonl(path: Path) -> list[dict[str, Any]]:
    try:
        lines = path.read_text(encoding="utf-8").splitlines()
    except OSError:
        return []
    out = []
    for ln in lines:
        try:
            row = json.loads(ln)
        except ValueError:
            continue
        if isinstance(row, dict):
            out.append(row)
    return out


def binding_key(b: Mapping[str, Any] | None) -> str:
    b = b or {}
    return hashlib.sha256(json.dumps([b.get(k) for k in BINDING_FIELDS]).encode()).hexdigest()[:12]


def _label_id(thread: str, gate_seq: Any, kind: str, criterion: str | None, extra: str = "") -> str:
    return hashlib.sha256(f"{thread}|{gate_seq}|{kind}|{criterion or ''}|{extra}".encode()).hexdigest()[:32]


def _source(caller: Mapping[str, Any] | None) -> str:
    return "person" if (caller or {}).get("decided_by") == "person" else "agent"  # FBK-B2


# -- derivation (FBK-B9) -----------------------------------------------------------------------------------

@dataclass(kw_only=True)
class _Gate:
    rec: dict[str, Any]
    judged: dict[str, Any]
    attempt: Any


def _gates(recs: Sequence[Mapping[str, Any]]) -> list[_Gate]:
    out: list[_Gate] = []
    for g in recs:
        if g.get("kind") != "gate" or not g.get("unit"):
            continue
        seq = int(g.get("seq") or 0)
        unit = g["unit"]
        child = g.get("child")  # SWF-B9: a child's gate of one name is not its parent's
        judged = next((dict(r) for r in reversed(recs) if r.get("kind") == "judgement" and r.get("unit") == unit
                       and r.get("child") == child and int(r.get("seq") or 0) < seq), {})
        starts = [r for r in recs if r.get("kind") == "attempt_start" and r.get("unit") == unit
                  and r.get("child") == child
                  and r.get("session_kind") in ("step", "retry") and int(r.get("seq") or 0) < seq]
        out.append(_Gate(rec=dict(g), judged=judged, attempt=starts[-1].get("attempt") if starts else None))
    return out


def _row(thread: str, recs: Sequence[Mapping[str, Any]], g: _Gate, kind: str, value: str, source: str, at: Any,
         keys: Mapping[str, Any], *, criterion: str | None = None, extra: str = "") -> dict[str, Any]:
    t0, t1 = _ts(g.rec.get("ts")), _ts(at)
    child = g.rec.get("child")
    return {"kind": "label", "schema_version": 1, **({"child": child} if child else {}),
            "label_id": _label_id(thread, g.rec.get("seq"), kind, criterion, extra), "thread": thread,
            "run_id": f"{thread}#{g.rec.get('segment')}", **keys, "unit": g.rec.get("unit"), "attempt": g.attempt,
            "gate_record": g.rec.get("seq"), "gate_verdict": g.rec.get("verdict"), "criterion_id": criterion,
            "label_kind": kind, "value": value, "source": source, "origin": "run", "at": at,
            "observed_after_s": round((t1 - t0).total_seconds(), 1) if t0 and t1 else None,
            "binding": binding_of([dict(r) for r in recs if r.get("child") == child], str(g.rec.get("unit")), g.attempt,
                                  g.rec.get("seq")),
            "confidence": g.judged.get("confidence"), "confidence_source": g.judged.get("confidence_source")}


def derive(recs: Sequence[Mapping[str, Any]], thread: str, *, keys: Mapping[str, Any] | None = None,
           earlier: Callable[[str], Sequence[Mapping[str, Any]]] | None = None) -> list[dict[str, Any]]:
    """Every FBK-B9 kind but `explicit` and `pr_state`, from one thread's run log, with no model call.

    ``earlier(thread)`` reads another thread's run log, for the `rerun` kind (the source thread's last PROCEED).
    """
    started = next((r for r in recs if r.get("kind") == "run_started"), {})
    keys = dict(keys or {"workflow": thread.partition("/")[0], "workflow_version": started.get("workflow_version")})
    gates = _gates(recs)
    out: list[dict[str, Any]] = []
    for h in (r for r in recs if r.get("kind") == "human"):
        hseq = int(h.get("seq") or 0)
        before = [g for g in gates if int(g.rec.get("seq") or 0) < hseq]
        if not before:
            continue
        pause: Mapping[str, Any] = next((r for r in reversed(recs) if r.get("kind") == "pause" and int(r.get("seq") or 0) < hseq), {})
        g = next((x for x in reversed(before) if x.rec.get("unit") == h.get("unit")), before[-1])
        word = str(h.get("decision") or "")
        src = _source(h.get("caller"))
        if pause.get("pause_kind") == "approval" and g.rec.get("verdict") == "PROCEED":  # accepted / declined
            out.append(_row(thread, recs, g, "approval", "agree" if word == "proceed" else "disagree", src,
                            h.get("ts"), keys))
        if pause.get("pause_kind") == "escalation" and g.rec.get("verdict") == "ESCALATE" and word == "proceed":
            check: Mapping[str, Any] = next((r for r in reversed(recs) if r.get("kind") == "check" and r.get("unit") == g.rec["unit"]
                          and int(r.get("seq") or 0) < int(g.rec.get("seq") or 0)), {})
            if check.get("result") == "PASS":
                out.append(_row(thread, recs, g, "override", "disagree", src, h.get("ts"), keys))
        target = word.split(":", 1)[1] if word.startswith(("back:", "rewind:")) else None
        if target:  # a gate escape: a person sent back work an earlier PROCEED let through (OBS)
            passed = next((x for x in reversed(before) if x.rec.get("unit") == target
                           and x.rec.get("verdict") == "PROCEED"), None)
            if passed is not None:
                out.append(_row(thread, recs, passed, "pushback", "disagree", src, h.get("ts"), keys))
    for a in (r for r in recs if r.get("kind") == "audit_judge"):
        ag = next((x for x in reversed(gates) if x.rec.get("unit") == a.get("unit")
                   and int(x.rec.get("seq") or 0) < int(a.get("seq") or 0)), None)
        if ag is None:
            continue
        mine = {str(s.get("id")): str(s.get("status")) for s in ag.judged.get("statuses") or []}
        for s in a.get("statuses") or []:
            cid = str(s.get("id"))
            if cid not in mine:
                continue
            same = (mine[cid] in ("MET", "N/A")) == (str(s.get("status")) in ("MET", "N/A"))
            out.append(_row(thread, recs, ag, "audit", "agree" if same else "disagree", "fact", a.get("ts"), keys,
                            criterion=cid))
    src_thread = ((started.get("rerun_of") or {}).get("thread")) if isinstance(started.get("rerun_of"), dict) else None
    if src_thread and earlier is not None:
        old = list(earlier(str(src_thread)))
        proceeds = [x for x in _gates(old) if x.rec.get("verdict") == "PROCEED"]
        if proceeds:
            last = proceeds[-1]
            t_old, t_new = _ts(last.rec.get("ts")), _ts(started.get("ts"))
            if t_old and t_new and t_new - t_old <= timedelta(days=int(params.value("labels.rerun_days"))):
                okeys = {**keys, "workflow_version": next((r.get("workflow_version") for r in old
                                                           if r.get("kind") == "run_started"), None)}
                out.append(_row(str(src_thread), old, last, "rerun", "disagree", _source(started.get("caller")),
                                started.get("ts"), okeys, extra=thread))
    return out


def read_labels(root: Path, workflow: str | None = None) -> list[dict[str, Any]]:
    rows = [r for r in _jsonl(root / "ledger.jsonl") if r.get("kind") == "label"]
    return [r for r in rows if workflow is None or r.get("workflow") == workflow]


def record_labels(root: Path, workflow: str, task_id: str, keys: Mapping[str, Any] | None = None
                  ) -> list[dict[str, Any]]:
    """Appends the labels of one thread not yet in the ledger (called after every exit, best-effort)."""
    from tempergraph.run.log import Ledger

    thread = f"{workflow}/{task_id}"
    recs = records(run_dir(root, workflow, task_id) / "run.jsonl")

    def earlier(t: str) -> list[dict[str, Any]]:
        wf, _, task = t.partition("/")
        return records(run_dir(root, wf, task) / "run.jsonl")

    have = {r.get("label_id") for r in read_labels(root, workflow)}
    new = [lab for lab in derive(recs, thread, keys=keys, earlier=earlier) if lab["label_id"] not in have]
    ledger = Ledger(path=root / "ledger.jsonl")
    for lab in new:
        ledger.append(lab)
    return new


# -- reliability (FBK-B11, FBK-B12) ----------------------------------------------------------------------------------

@dataclass(kw_only=True)
class Figures:
    gate: str
    binding: dict[str, Any]
    n: int = 0
    false_pass_rate: float | None = None
    false_block_rate: float | None = None
    audit_agreement: float | None = None
    audited: int = 0
    known_bad: int = 0
    last_label: str | None = None
    orphan_labels: int = 0
    confidence_bands: dict[str, float | None] = field(default_factory=dict)

    def to_json(self) -> dict[str, Any]:
        return dict(self.__dict__)


def _latest(rows: Iterable[Mapping[str, Any]]) -> list[Mapping[str, Any]]:
    """FBK-B10: two labels of one kind for one judgement (and criterion): the later wins."""
    by: dict[tuple[Any, ...], Mapping[str, Any]] = {}
    for r in sorted(rows, key=lambda r: str(r.get("at") or "")):
        by[(r.get("thread"), r.get("gate_record"), r.get("label_kind"), r.get("criterion_id"))] = r
    return list(by.values())


def figures(labels: Iterable[Mapping[str, Any]], gate: str, binding: Mapping[str, Any],
            now: datetime | None = None, child: str | None = None) -> Figures:
    now = now or datetime.now(UTC)
    since = now - timedelta(days=int(params.value("reliability.window_days")))
    key = binding_key(binding)
    fig = Figures(gate=gate, binding=dict(binding))
    rows = []
    for r in labels:
        if r.get("unit") != gate or r.get("child") != child or binding_key(r.get("binding")) != key:
            continue
        if r.get("gate_record") is None:
            fig.orphan_labels += 1  # FBK-B10: kept, never in a figure
            continue
        at = _ts(r.get("at"))
        if r.get("source") not in ("person", "fact") or at is None or at < since:
            continue
        rows.append(r)
    rows = list(_latest(rows))
    graded = [r for r in rows if r.get("label_kind") != "audit" and r.get("value") in ("agree", "disagree")]
    fig.n = len(graded)
    passes = [r for r in graded if r.get("gate_verdict") == "PROCEED"]
    blocks = [r for r in graded if r.get("gate_verdict") in BLOCKS]
    if passes:
        fig.false_pass_rate = sum(r["value"] == "disagree" for r in passes) / len(passes)
    if blocks:
        fig.false_block_rate = sum(r["value"] == "disagree" for r in blocks) / len(blocks)
    fig.known_bad = sum(r["value"] == "disagree" for r in passes) + sum(r["value"] == "agree" for r in blocks)
    audits = [r for r in rows if r.get("label_kind") == "audit" and r.get("value") in ("agree", "disagree")]
    fig.audited = len(audits)
    if audits:
        fig.audit_agreement = sum(r["value"] == "agree" for r in audits) / len(audits)
    fig.last_label = max((str(r.get("at")) for r in graded), default=None)
    def nearest(c: float) -> float:
        return min(ANCHORS, key=lambda a: abs(a - c))

    for anchor in ANCHORS:
        band = [r for r in passes if r.get("confidence_source") == "judge"
                and isinstance(r.get("confidence"), int | float) and nearest(float(r["confidence"])) == anchor]
        fig.confidence_bands[str(anchor)] = (sum(r["value"] == "disagree" for r in band) / len(band)) if band else None
    return fig


def grade(fig: Figures, live_score_passing: bool, now: datetime | None = None) -> tuple[str, list[str]]:
    """FBK-B11, FBK-B12. Too few labels is checked first, then the two `unreliable` rules, then the remaining
    `unmeasured` rules (recency, known-bad evidence, a passing live score), so a judge shown to pass bad work
    is `unreliable` even before its live score exists (the FBK-B3 table)."""
    now = now or datetime.now(UTC)
    if fig.n < params.value("reliability.min_labels"):
        return "unmeasured", [f"n {fig.n} < {int(params.value('reliability.min_labels'))}"]
    why: list[str] = []
    if fig.false_pass_rate is not None and fig.false_pass_rate > params.value("reliability.max_false_pass"):
        why.append(f"false_pass_rate {fig.false_pass_rate:.2f} > {params.value('reliability.max_false_pass')}")
    if (fig.audit_agreement is not None and fig.audited >= params.value("reliability.min_audited")
            and fig.audit_agreement < params.value("reliability.min_audit_agreement")):
        why.append(f"audit_agreement {fig.audit_agreement:.2f} < {params.value('reliability.min_audit_agreement')}")
    if why:
        return "unreliable", why
    last = _ts(fig.last_label)
    if last is None or now - last > timedelta(days=int(params.value("reliability.recent_days"))):
        why.append("no label in the last 30 days")
    if fig.known_bad < params.value("reliability.min_known_bad"):
        why.append(f"known-bad labels {fig.known_bad} < {int(params.value('reliability.min_known_bad'))}")
    if not live_score_passing:
        why.append("no passing live score on calibration cases with known-bad cases (JCL)")
    return ("unmeasured", why) if why else ("reliable", [])


def judgements(root: Path, workflow: str, child: str | None = None) -> list[dict[str, Any]]:
    """Every gate judgement of a workflow's threads, oldest first: unit, verdict, binding, ts and the counts
    the binding-shift watch compares. `child` is the sub-workflow unit path whose gates are read (SWF-B9); none reads the
    workflow's own, so a child's gate and a parent's gate of one name are never mixed."""
    out: list[dict[str, Any]] = []
    base = root / "runs" / workflow
    if not base.is_dir():
        return out
    for task in sorted(p.name for p in base.iterdir() if p.is_dir()):
        recs = records(run_dir(root, workflow, task) / "run.jsonl")
        mine = [r for r in recs if r.get("child") == child]
        for g in (x for x in _gates(recs) if x.rec.get("child") == child):
            judge: Mapping[str, Any] = next((r for r in reversed(mine) if r.get("kind") == "agent_run"
                                             and r.get("unit") == g.rec["unit"]
                          and r.get("session_kind") == "judge" and int(r.get("seq") or 0) < int(g.rec.get("seq") or 0)),
                         {})
            out.append({"thread": f"{workflow}/{task}", "unit": g.rec["unit"], "seq": g.rec.get("seq"),
                        "ts": g.rec.get("ts"), "verdict": g.rec.get("verdict"),
                        "binding": binding_of(mine, g.rec["unit"], g.attempt, g.rec.get("seq")),
                        "unverifiable": any(s.get("status") == "UNVERIFIABLE" for s in g.judged.get("statuses") or []),
                        "turns": ((judge.get("usage") or {}).get("turns")), "confidence": g.judged.get("confidence"),
                        "confidence_source": g.judged.get("confidence_source")})
    out.sort(key=lambda j: str(j.get("ts") or ""))
    return out


def report(root: Path, workflow: str, gates: Sequence[str], live: Callable[[str, Mapping[str, Any]], bool],
           now: datetime | None = None, child: str | None = None) -> list[dict[str, Any]]:
    """Each gate's current binding (its latest judgement's), its grade and figures, and earlier bindings'
    grades as history, never inherited (FBK-B4). ``live(gate, binding)`` answers whether the binding has a
    passing live score (JCL `accepted` or `provisional`). `child` names the sub-workflow unit path whose gates
    are read (SWF-B9); none reads the workflow's own."""
    labs = read_labels(root, workflow)
    js = judgements(root, workflow, child)
    out = []
    for gate in gates:
        mine = [j for j in js if j["unit"] == gate]
        bindings: list[dict[str, Any]] = []
        for j in mine:
            if not bindings or binding_key(bindings[-1]) != binding_key(j["binding"]):
                bindings.append(j["binding"])
        current = bindings[-1] if bindings else None
        row: dict[str, Any] = {"gate": gate, "binding": current, "grade": "unmeasured", "why": ["no judgement yet"],
                               "figures": None, "history": []}
        if current is not None:
            fig = figures(labs, gate, current, now, child)
            row["grade"], row["why"] = grade(fig, live(gate, current), now)
            row["figures"] = fig.to_json()
        for b in bindings[:-1]:
            fig = figures(labs, gate, b, now, child)
            row["history"].append({"binding": b, "grade": grade(fig, live(gate, b), now)[0]})
        out.append(row)
    return out


def grade_of(root: Path, workflow: str, gate: str, live: Callable[[str, Mapping[str, Any]], bool],
             child: str | None = None) -> str:
    return report(root, workflow, [gate], live, child=child)[0]["grade"]


# -- labelling queue (FBK-B13) ------------------------------------------------------------------------------

def queue(root: Path, workflow: str, grades: Mapping[str, str], *, seed: int = 0) -> list[dict[str, Any]]:
    """Gate judgements a person should label, most informative first; read-only."""
    labelled = {(r.get("thread"), r.get("gate_record")) for r in read_labels(root, workflow)
                if r.get("source") in ("person", "fact") and r.get("label_kind") != "audit"}
    audit_dis = {(r.get("thread"), r.get("gate_record")) for r in read_labels(root, workflow)
                 if r.get("label_kind") == "audit" and r.get("value") == "disagree"}
    escapes = {(r.get("thread"), r.get("gate_record")) for r in read_labels(root, workflow)
               if r.get("label_kind") == "pushback"}
    rng = random.Random(seed)  # noqa: S311 - a sample, not a secret
    tiers: list[list[dict[str, Any]]] = [[], [], [], [], []]
    for j in judgements(root, workflow):
        k = (j["thread"], j["seq"])
        row = {"thread": j["thread"], "gate": j["unit"], "gate_record": j["seq"], "verdict": j["verdict"],
               "command": f"tempergraph label {j['thread']} {j['unit']} --value agree|disagree"}
        if k in escapes and k not in labelled:
            tiers[0].append({**row, "why": "gate_escape"})
        elif k in audit_dis:
            tiers[1].append({**row, "why": "audit_disagreement"})
        elif k in labelled:
            continue
        elif j.get("confidence_source") == "judge" and isinstance(j.get("confidence"), int | float) \
                and float(j["confidence"]) <= params.value("reliability.queue_confidence"):
            tiers[2].append({**row, "why": "low_confidence"})
        elif j["verdict"] == "PROCEED" and grades.get(j["unit"], "unmeasured") == "unmeasured":
            tiers[3].append({**row, "why": "unmeasured_binding"})
        elif j["verdict"] == "PROCEED" and rng.random() < params.value("reliability.queue_sample"):
            tiers[4].append({**row, "why": "sample"})
    return [r for t in tiers for r in t]


# -- binding-shift watch (FBK-B14) --------------------------------------------------------------------------

def _rate(rows: Sequence[Mapping[str, Any]], pred: Callable[[Mapping[str, Any]], bool]) -> float:
    return sum(1 for r in rows if pred(r)) / len(rows) if rows else 0.0


def shifts(root: Path, workflow: str) -> list[dict[str, Any]]:
    """One `binding_shift` per gate and new binding whose first judgements differ from the old binding's last."""
    js = judgements(root, workflow)
    first_n, last_n = int(params.value("shift.first_n")), int(params.value("shift.last_n"))
    out = []
    for gate in sorted({j["unit"] for j in js}):
        mine = [j for j in js if j["unit"] == gate]
        runs: list[list[dict[str, Any]]] = []
        for j in mine:
            if not runs or binding_key(runs[-1][0]["binding"]) != binding_key(j["binding"]):
                runs.append([])
            runs[-1].append(j)
        for old, new in zip(runs, runs[1:], strict=False):
            if len(new) < first_n or not old:
                continue
            a, b = old[-last_n:], new[:first_n]
            pa, pb = _rate(a, lambda r: r["verdict"] == "PROCEED"), _rate(b, lambda r: r["verdict"] == "PROCEED")
            ua, ub = _rate(a, lambda r: bool(r["unverifiable"])), _rate(b, lambda r: bool(r["unverifiable"]))
            if abs(pa - pb) * 100 <= params.value("shift.pass_points") and \
                    abs(ua - ub) * 100 <= params.value("shift.unverifiable_points"):
                continue
            ob, nb = old[-1]["binding"], new[0]["binding"]
            changed = [k for k in BINDING_FIELDS if ob.get(k) != nb.get(k)]
            side = f"executor:{nb.get('executor')}" if set(changed) <= EXECUTOR_FIELDS else "workflow"
            turns = [[r["turns"] for r in rows if isinstance(r.get("turns"), int | float)] for rows in (a, b)]
            out.append({"gate": gate, "side": side, "changed": changed, "from": ob, "to": nb,
                        "thread": new[first_n - 1]["thread"],
                        "pass_rate": [round(pa, 3), round(pb, 3)], "unverifiable_rate": [round(ua, 3), round(ub, 3)],
                        "mean_turns": [round(sum(t) / len(t), 2) if t else None for t in turns],
                        "binding": binding_key(nb)})
    return out


def record_shifts(root: Path, workflow: str, keys: Mapping[str, Any]) -> list[dict[str, Any]]:
    """Writes each new shift as a finding of the thread that completed the comparison (FBK-B14): it enters
    the friction lens like any finding and is never a route or a pause."""
    from tempergraph.docs import write_json
    from tempergraph.improve.record import findings_path, fingerprint, read_findings

    written = []
    for s in shifts(root, workflow):
        task = s["thread"].partition("/")[2]
        have = read_findings(root, workflow, task)
        fp = fingerprint(s["side"], workflow, "binding_shift", s["gate"])
        if any(f.get("fingerprint") == fp and f.get("binding") == s["binding"] for f in have):
            continue
        line = {"kind": "finding", "thread": s["thread"], **{k: keys.get(k) for k in (
            "workflow", "workflow_version", "machine", "repo")}, "unit": s["gate"], "cause": "binding_shift",
            "class": "fault", "side": s["side"], "count": 1, "fingerprint": fp, "at": now_iso(),
            "remedy": "Re-score the judge on its calibration cases (JCL) and review the gate's criteria for the "
                      "new binding", "binding": s["binding"], "changed": s["changed"],
            "pass_rate": s["pass_rate"], "unverifiable_rate": s["unverifiable_rate"],
            **({"executor_version": [s["from"].get("executor_version"), s["to"].get("executor_version")]}
               if "executor_version" in s["changed"] else {})}
        write_json(findings_path(root, workflow, task), {"schema_version": 1, "thread": s["thread"],
                                                        "findings": [*have, line]})
        written.append(line)
    return written


def after_exit(root: Path, workflow: str, task_id: str, keys: Mapping[str, Any]) -> dict[str, int]:
    """The runner's one call after `record_exit`: labels, then the shift watch. Best-effort, no model call."""
    labs = record_labels(root, workflow, task_id, {k: keys.get(k) for k in (
        "workflow", "workflow_version", "machine", "repo")})
    return {"labels": len(labs), "shifts": len(record_shifts(root, workflow, keys))}
