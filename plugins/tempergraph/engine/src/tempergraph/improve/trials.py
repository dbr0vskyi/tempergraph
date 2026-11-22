"""Case sets, paired trials, the A/A noise floor and the trial caps (PRP-B17, PRP-B4, PRP-B12, PRP-B18, PRP-B21, PRP-B8, PRP-B22, B5 to B7, B9;
plan T12.6).

Release 1 (ADR-0090 S4): before `batch` exists, each case runs as one engine child run at a time, arm A (the
base package) then arm B (the patched copy), each in its own engine worktree at the case's base commit
(`run.worktree.base = ref:<base>`), with `--dry-run` so the loop files nothing for them. A case that stops at
a pause is a tie (PRP open question default). A trial writes no code: only the proposer writes, on its own
branch (OVR-B16). Trial child runs are ordinary threads with `origin: trial`, so their spend is logged per session
like any run and joins no workflow run's cost line (PRP-AC6).
"""

from __future__ import annotations

import json
import math
import re
import tempfile
import uuid
from collections.abc import Callable, Mapping, Sequence
from dataclasses import dataclass, field
from datetime import UTC, datetime, timedelta
from pathlib import Path
from typing import Any

from tempergraph.contracts import WorkflowSpec
from tempergraph.docs import read_json, write_json
from tempergraph.improve import params
from tempergraph.store.layout import now_iso, run_dir

TARGET = re.compile(r"^(first_pass_yield|gate_pass|criterion_met|run_cost|outcome_met|label_agreement)"
                    r"(?:\(([A-Za-z0-9_.-]+)(?:,\s*([A-Za-z0-9_.-]+))?\))?$")
JUDGE_GRADED = frozenset({"gate_pass", "criterion_met", "outcome_met"})
DECISIONS = ("shown_better", "not_shown", "regressed", "aborted")


class TrialRefused(ValueError):
    """Refused before spend (exit 2)."""


# -- case sets (PRP-B17) ------------------------------------------------------------------------------------

@dataclass(frozen=True, kw_only=True)
class TrialCase:
    case_id: str
    base: str
    request: str
    expected_scope: str = ""
    origin: str = "authored"
    reviewed_by: str | None = None


def case_set(spec: WorkflowSpec) -> tuple[list[TrialCase], str]:
    """The package's `evals/cases.json`, reviewed cases only (harvested ones need `reviewed_by`)."""
    root = spec.package_root
    path = root / "evals" / "cases.json" if root is not None else None
    if path is None or not path.is_file():
        return [], ""
    try:
        doc = json.loads(path.read_text(encoding="utf-8"))
    except ValueError:
        return [], ""
    rows = doc.get("cases") if isinstance(doc, dict) else doc
    out = []
    for r in rows or []:
        cid = r.get("case_id") or r.get("id") if isinstance(r, dict) else None  # PKG-B25's minimal set uses `id`
        if not isinstance(r, dict) or not cid:
            continue
        c = TrialCase(case_id=str(cid), base=str(r.get("base") or "HEAD"), request=str(r.get("request") or ""),
                      expected_scope=str(r.get("expected_scope") or ""), origin=str(r.get("origin") or "authored"),
                      reviewed_by=r.get("reviewed_by"))
        if c.origin.startswith("harvested:") and not c.reviewed_by:
            continue
        out.append(c)
    import hashlib

    digest = hashlib.sha256(json.dumps([c.__dict__ for c in out], sort_keys=True).encode()).hexdigest()[:16]
    return out, digest


def in_sample(c: TrialCase, cluster_threads: Sequence[str]) -> bool:
    """A case harvested from a run of the proposal's cluster (PRP-B17)."""
    if not c.origin.startswith("harvested:"):
        return False
    run = c.origin.split(":", 1)[1]
    return any(run == t or run.startswith(t + "#") for t in cluster_threads)


# -- the decision rule (PRP-B18, PRP-B19, PRP-B20, ADR-0034) ------------------------------------------------------------------

def sign_count(n: int, alpha: float | None = None) -> int | None:
    """The fewest wins of `n` non-tied pairs with a one-sided sign-test p ≤ alpha (R-031 F3); None if none."""
    alpha = params.value("trial.alpha") if alpha is None else alpha
    for k in range(n + 1):
        p = sum(math.comb(n, i) for i in range(k, n + 1)) / 2 ** n
        if p <= alpha:
            return k
    return None


def decide(pairs: Sequence[Mapping[str, Any]], guards: Sequence[Mapping[str, Any]],
           noise_floor: float | str = "unknown", *, aborted: bool = False) -> dict[str, Any]:
    out_pairs = [p for p in pairs if not p.get("in_sample")]
    wins = sum(1 for p in out_pairs if p["result"] == "win")
    losses = sum(1 for p in out_pairs if p["result"] == "loss")
    ties = sum(1 for p in out_pairs if p["result"] == "tie")
    n = wins + losses
    counts = {"wins": wins, "losses": losses, "ties": ties, "in_sample": len(pairs) - len(out_pairs)}
    warnings = []
    if isinstance(noise_floor, int | float) and noise_floor > params.value("trial.noisy_floor"):
        warnings.append("noisy_case_set")
    base = {"counts": counts, "warnings": warnings, "need": sign_count(n) if n else None}
    if aborted:
        return {**base, "decision": "aborted", "reason": "cap_reached"}
    need = sign_count(n)
    if any(g["state"] == "failed" for g in guards):
        return {**base, "decision": "regressed", "reason": "guard:" + ",".join(g["name"] for g in guards
                                                                             if g["state"] == "failed")}
    if need is not None and n >= params.value("trial.min_pairs") and losses >= need:
        return {**base, "decision": "regressed", "reason": "losses"}
    if n < params.value("trial.min_pairs"):
        return {**base, "decision": "not_shown", "reason": "too_few_pairs"}
    if need is not None and wins >= need:
        return {**base, "decision": "shown_better", "reason": None}
    return {**base, "decision": "not_shown", "reason": None}


def guard_states(a: Mapping[str, float], b: Mapping[str, float]) -> list[dict[str, Any]]:
    """The default guards: run cost +15%, outcome met −1 case, check pass −1 case, gate escapes +1."""
    out = []
    cost_a, cost_b = float(a.get("cost") or 0), float(b.get("cost") or 0)
    limit = cost_a * (1 + params.value("trial.guard_cost"))
    out.append({"name": "run_cost", "a": round(cost_a, 4), "b": round(cost_b, 4),
                "state": "failed" if cost_a > 0 and cost_b > limit else "held"})
    for name, key, margin, worse in (("outcome_met", "outcome_met", "trial.guard_outcome_cases", -1),
                                     ("check_pass", "check_pass", "trial.guard_check_cases", -1),
                                     ("gate_escapes", "escapes", "trial.guard_escapes", 1)):
        va, vb = float(a.get(key) or 0), float(b.get(key) or 0)
        bad = (vb - va) * worse >= params.value(margin)
        out.append({"name": name, "a": va, "b": vb, "state": "failed" if bad else "held"})
    return out


# -- metrics of one child run --------------------------------------------------------------------------------

def parse_target(target: str) -> tuple[str, str | None, str | None]:
    m = TARGET.match(target.replace(" ", ""))
    if not m:
        raise TrialRefused(f"target {target!r} is not one of first_pass_yield(unit), gate_pass(unit), "
                           "criterion_met(unit, id), run_cost, outcome_met, label_agreement(gate)")
    return m.group(1), m.group(2), m.group(3)


def _records(root: Path, workflow: str, task: str) -> list[dict[str, Any]]:
    from tempergraph.run.events import records

    return records(run_dir(root, workflow, task) / "run.jsonl")


def run_cost(recs: Sequence[Mapping[str, Any]]) -> float:
    ex: Mapping[str, Any] = next((r for r in reversed(recs) if r.get("kind") == "run_exit"), {})
    c = ex.get("cost") or {}
    reported = float(c.get("reported") or 0)
    return reported + float(c.get("estimated_only") or 0) if reported else float(c.get("estimated") or 0)


def measures(recs: Sequence[Mapping[str, Any]], metric: str, unit: str | None, crit: str | None) -> dict[str, Any]:
    """The target value of one child run and the guard inputs; higher is better except `run_cost`."""
    ex: Mapping[str, Any] = next((r for r in reversed(recs) if r.get("kind") == "run_exit"), {})
    paused = ex.get("exit_code") == 3
    gates = [r for r in recs if r.get("kind") == "gate" and (unit is None or r.get("unit") == unit)]
    value: float | None
    if metric == "first_pass_yield":
        value = 1.0 if gates and gates[0].get("verdict") == "PROCEED" else 0.0
    elif metric == "gate_pass":
        value = sum(g.get("verdict") == "PROCEED" for g in gates) / len(gates) if gates else 0.0
    elif metric == "criterion_met":
        j: Mapping[str, Any] = next((r for r in reversed(recs) if r.get("kind") == "judgement" and r.get("unit") == unit), {})
        value = 1.0 if any(s.get("id") == crit and s.get("status") == "MET" for s in j.get("statuses") or []) else 0.0
    elif metric == "run_cost":
        value = run_cost(recs)
    elif metric == "outcome_met":
        oc: Mapping[str, Any] = next((r for r in reversed(recs) if r.get("kind") == "outcome"), {})
        value = 1.0 if oc.get("verdict") in ("met", "met_with_open") else 0.0
    else:
        value = None
    o: Mapping[str, Any] = next((r for r in reversed(recs) if r.get("kind") == "outcome"), {})
    checks = [r for r in recs if r.get("kind") == "check"]
    proceeded: set[str] = set()
    escapes = 0
    for g in (r for r in recs if r.get("kind") == "gate"):
        if g.get("verdict") == "PROCEED":
            proceeded.add(str(g.get("unit")))
        elif g.get("verdict") == "BACK":
            escapes += 1 if any(str(r.get("unit")) in proceeded for r in recs
                                if r.get("kind") == "unit_entered" and r.get("entered_from") == f"back:{g.get('unit')}"
                                and int(r.get("seq") or 0) > int(g.get("seq") or 0)) else 0
    return {"value": value, "paused": paused, "cost": run_cost(recs),
            "outcome_met": 1.0 if o.get("verdict") in ("met", "met_with_open") else 0.0,
            "check_pass": 1.0 if checks and all(c.get("result") == "PASS" for c in checks) else 0.0,
            "escapes": float(escapes), "exit_code": ex.get("exit_code")}


def pair_result(metric: str, a: Mapping[str, Any], b: Mapping[str, Any]) -> str:
    if a.get("paused") or b.get("paused") or a.get("value") is None or b.get("value") is None:
        return "tie"  # a case that stops at a pause is a tie
    va, vb = float(a["value"]), float(b["value"])
    if abs(va - vb) < 1e-9:
        return "tie"
    better = vb < va if metric == "run_cost" else vb > va
    return "win" if better else "loss"


# -- records and caps ----------------------------------------------------------------------------------------

def trials_dir(root: Path) -> Path:
    return root / "improve" / "trials"


def save(root: Path, rec: Mapping[str, Any]) -> None:
    write_json(trials_dir(root) / f"{rec['trial_id']}.json", dict(rec))


def load_trial(root: Path, trial_id: str) -> dict[str, Any]:
    if not re.match(r"^[A-Za-z0-9_-]{1,64}$", trial_id):
        raise TrialRefused(f"{trial_id!r} is not a trial id")
    path = trials_dir(root) / f"{trial_id}.json"
    if not path.is_file():
        raise TrialRefused(f"no trial {trial_id}")
    return dict(read_json(path, "trial"))


def all_trials(root: Path) -> list[dict[str, Any]]:
    d = trials_dir(root)
    out = []
    for p in sorted(d.glob("*.json")) if d.is_dir() else []:
        try:
            out.append(json.loads(p.read_text(encoding="utf-8")))
        except (OSError, ValueError):
            continue
    return out


def _improvement(spec: WorkflowSpec) -> dict[str, Any]:
    root = spec.package_root
    try:
        doc = json.loads((root / "tempergraph.json").read_text(encoding="utf-8")) if root else {}
    except (OSError, ValueError):
        return {}
    return dict(doc.get("improvement") or {}) if isinstance(doc, dict) else {}


def caps(spec: WorkflowSpec, requested: float | None) -> tuple[float, float]:
    imp = _improvement(spec)
    per = float(imp.get("trial_cap_usd") or params.value("trial.cap_usd"))
    monthly = float(imp.get("monthly_trial_cap_usd") or params.value("trial.monthly_cap_usd"))
    return (min(per, requested) if requested is not None else per), monthly


def month_spend(root: Path, workflow: str, now: datetime | None = None) -> float:
    since = ((now or datetime.now(UTC)) - timedelta(days=30)).isoformat()
    return sum(float((t.get("spend") or {}).get("total") or 0) for t in all_trials(root)
               if t.get("workflow") == workflow and str(t.get("at") or "") >= since)


def noise_floor(root: Path, workflow: str, digest: str) -> float | str:
    aa = [t for t in all_trials(root) if t.get("kind") == "aa" and t.get("workflow") == workflow
          and t.get("case_set_digest") == digest]
    return aa[-1].get("noise_floor", "unknown") if aa else "unknown"


# -- running arms --------------------------------------------------------------------------------------------

ArmRunner = Callable[[WorkflowSpec, TrialCase, str, str], list[dict[str, Any]]]


@dataclass(kw_only=True)
class ChildRuns:
    """Runs one case of one arm as an engine child run in `repo`, at the case's base, dry-run."""

    repo: Path
    registry: Any
    settings: Callable[..., Any] | None = None
    tasks: list[str] = field(default_factory=list)

    def __call__(self, spec: WorkflowSpec, case: TrialCase, arm: str, trial_id: str) -> list[dict[str, Any]]:
        from tempergraph.run.runner import RunSettings, start
        from tempergraph.store.layout import state_root_path

        task = re.sub(r"[^A-Za-z0-9._-]", "-", f"tr-{trial_id[:10]}-{case.case_id}-{arm}")[:64]
        base = case.base if case.base.startswith("ref:") else f"ref:{case.base}"
        rs = RunSettings(origin="trial", dry_run=True, workspace="worktree",
                         flags={"run.worktree.base": base}, caller={"kind": "engine", "decided_by": "engine"})
        if self.settings is not None:
            rs = self.settings(rs)
        start(spec, task, {"request": case.request}, self.repo, self.registry, rs)
        self.tasks.append(task)
        return _records(state_root_path(self.repo), spec.name, task)


def _load(path: Path) -> WorkflowSpec:
    from tempergraph.package.loader import load

    return load(path)


def _judge_ready(root: Path, spec: WorkflowSpec, gate: str) -> tuple[bool, str]:
    """PRP-B18, PRP-B19, PRP-B20: a judge-graded target needs FBK `reliable` and JCL `accepted` for that gate's judge."""
    from tempergraph.improve import calibration as cal
    from tempergraph.improve import reliability as rel

    try:
        accepted = cal.has_score(spec, gate, root)
        grade = rel.report(root, spec.name, [gate], lambda g, b: cal.passing(spec, g))[0]["grade"]
    except (cal.CalibrationError, OSError, ValueError):
        return False, "unscored"
    if grade != "reliable":
        return False, f"judge {gate} is {grade} (FBK)"
    if not accepted:
        return False, f"judge {gate} is not accepted (JCL)"
    return True, ""


def trial(root: Path, spec: WorkflowSpec, proposal_id: str, run_arm: ArmRunner, *, target: str | None = None,
          cap_usd: float | None = None, now: datetime | None = None, judge_executor: Any = None) -> dict[str, Any]:
    """`improve trial`: both arms on the case set, then the decision. Refusals spend nothing."""
    from tempergraph.improve import proposals as prp

    rec = prp.load_proposal(root, proposal_id)
    if rec.get("state") not in ("drafted", "not_shown", "aborted"):
        raise TrialRefused(f"proposal {proposal_id} is {rec.get('state')}; only a drafted proposal is trialled")
    if rec.get("review_only"):
        raise TrialRefused("a widening tools proposal is opened for review, never trialled alone (ADR-0080)")
    unit = (rec.get("cluster") or {}).get("unit")
    if rec.get("side") == "grader":
        target = target or f"label_agreement({unit})"
    target = target or (f"first_pass_yield({unit})" if unit else "run_cost")
    metric, tunit, crit = parse_target(target)
    if "weakening" in (rec.get("classes") or []) and metric not in ("label_agreement",):
        raise TrialRefused("a weakening proposal is trialled on grader metrics only (PRP-B2)")
    if metric in JUDGE_GRADED:
        ok, why = _judge_ready(root, spec, "outcome" if metric == "outcome_met" else str(tunit))
        if not ok:
            raise TrialRefused(f"judge-graded target refused before spend: {why}")
    per_cap, monthly = caps(spec, cap_usd)
    if month_spend(root, spec.name, now) >= monthly:
        raise TrialRefused(f"monthly trial cap ${monthly:.0f} reached for {spec.name}")
    if prp.package_digest(spec.package_root) != rec.get("base_digest"):  # type: ignore[arg-type]
        raise TrialRefused("stale_base: the package changed since the proposal; rerun the proposer")
    tid = uuid.uuid4().hex[:12]
    out: dict[str, Any] = {"schema_version": 1, "kind": "trial", "trial_id": tid, "proposal_id": proposal_id,
                           "workflow": spec.name, "target_metric": target, "at": (now or datetime.now(UTC)).isoformat()}
    if metric == "label_agreement":
        if judge_executor is None:
            raise TrialRefused("a label_agreement trial needs the gate's judge executor")
        return trial_grader(root, spec, proposal_id, judge_executor, gate=str(tunit), now=now)
    cases, digest = case_set(spec)
    if not cases:
        raise TrialRefused("no reviewed case set (evals/cases.json)")
    out["case_set_digest"] = digest
    out["noise_floor"] = noise_floor(root, spec.name, digest)
    rec["state"], rec["trial_id"] = "trialling", tid
    prp.save(root, rec)
    pairs: list[dict[str, Any]] = []
    spend = {"A": 0.0, "B": 0.0}
    sums = {"A": {"cost": 0.0, "outcome_met": 0.0, "check_pass": 0.0, "escapes": 0.0},
            "B": {"cost": 0.0, "outcome_met": 0.0, "check_pass": 0.0, "escapes": 0.0}}
    aborted = False
    threads = list((rec.get("cluster") or {}).get("threads") or [])
    with tempfile.TemporaryDirectory(prefix="tg-trial-") as tmp:
        assert spec.package_root is not None
        b_root = prp.apply_patch(spec.package_root, str(rec.get("patch") or ""), Path(tmp) / spec.package_root.name)
        for case in cases:
            if spend["A"] + spend["B"] >= per_cap:
                aborted = True  # PRP-B7: no further case starts; the pairs so far are kept
                break
            got = {}
            for arm, path in (("A", spec.package_root), ("B", b_root)):
                arm_spec = _load(path)  # loaded afresh per arm: callables resolve against this arm's code
                recs = run_arm(arm_spec, case, arm, tid)
                got[arm] = measures(recs, metric, tunit, crit)
                spend[arm] += got[arm]["cost"]
                for k in sums[arm]:
                    sums[arm][k] += float(got[arm][k])
            pairs.append({"case": case.case_id, "a": got["A"]["value"], "b": got["B"]["value"],
                          "result": pair_result(metric, got["A"], got["B"]), "in_sample": in_sample(case, threads),
                          "stopped": bool(got["A"]["paused"] or got["B"]["paused"])})
        _load(spec.package_root)  # the import map points at the live package again
    guards = guard_states(sums["A"], sums["B"])
    out.update(pairs=pairs, guards=guards, spend={**{k: round(v, 6) for k, v in spend.items()},
                                                  "total": round(spend["A"] + spend["B"], 6), "cap": per_cap})
    out.update(decide(pairs, guards, out["noise_floor"], aborted=aborted))
    save(root, out)
    rec["state"] = out["decision"]
    prp.save(root, rec)
    return out


def trial_grader(root: Path, spec: WorkflowSpec, proposal_id: str, executor: Any, *, gate: str | None = None,
                 now: datetime | None = None) -> dict[str, Any]:
    """PRP-B5 for a grader proposal: per calibration case, the share of labelled criteria whose judged status
    class matches the label, A against B."""
    from tempergraph.improve import calibration as cal
    from tempergraph.improve import proposals as prp

    rec = prp.load_proposal(root, proposal_id)
    if rec.get("state") not in ("drafted", "not_shown", "aborted"):
        raise TrialRefused(f"proposal {proposal_id} is {rec.get('state')}")
    gate = gate or str((rec.get("cluster") or {}).get("unit"))
    assert spec.package_root is not None
    tid = uuid.uuid4().hex[:12]
    out: dict[str, Any] = {"schema_version": 1, "kind": "trial", "trial_id": tid, "proposal_id": proposal_id,
                           "workflow": spec.name, "target_metric": f"label_agreement({gate})",
                           "at": (now or datetime.now(UTC)).isoformat(), "noise_floor": "unknown"}
    with tempfile.TemporaryDirectory(prefix="tg-trial-") as tmp:
        b_root = prp.apply_patch(spec.package_root, str(rec.get("patch") or ""), Path(tmp) / spec.package_root.name)
        scored = {}
        for arm, path in (("A", spec.package_root), ("B", b_root)):
            arm_spec = _load(path)
            try:
                scored[arm] = (cal.score(arm_spec, gate, executor, repeats=1, variants=(), write=False),
                               {u.case.case_id: u.labels for u in cal.usable(arm_spec, gate)[0]})
            except cal.CalibrationError as exc:
                raise TrialRefused(str(exc)) from exc
        _load(spec.package_root)

    def agreement(arm: str) -> dict[str, float]:
        res, labels = scored[arm]
        out_: dict[str, float] = {}
        for r in res["results"]:
            lab = labels.get(r["case"]) or {}
            if not lab:
                continue
            same = [cal._klass(str(r["statuses"].get(c, cal.DISCARDED))) == cal._klass(e) for c, e in lab.items()]
            out_[r["case"]] = sum(same) / len(same)
        return out_

    a, b = agreement("A"), agreement("B")
    pairs = [{"case": c, "a": a[c], "b": b[c], "result": pair_result("label_agreement", {"value": a[c]},
                                                                     {"value": b[c]}), "in_sample": False}
             for c in sorted(set(a) & set(b))]
    spend = {"A": scored["A"][0]["usage"]["cost_usd"], "B": scored["B"][0]["usage"]["cost_usd"]}
    out.update(pairs=pairs, guards=[], spend={**spend, "total": round(spend["A"] + spend["B"], 6)})
    out.update(decide(pairs, []))
    save(root, out)
    rec["state"], rec["trial_id"] = out["decision"], tid
    prp.save(root, rec)
    return out


def aa(root: Path, spec: WorkflowSpec, run_arm: ArmRunner, *, cap_usd: float | None = None) -> dict[str, Any]:
    """`improve aa`: the case set twice on the current version; the share of differing pairs is the floor."""
    cases, digest = case_set(spec)
    if not cases:
        raise TrialRefused("no reviewed case set (evals/cases.json)")
    per_cap, monthly = caps(spec, cap_usd)
    if month_spend(root, spec.name) >= monthly:
        raise TrialRefused(f"monthly trial cap ${monthly:.0f} reached for {spec.name}")
    tid = uuid.uuid4().hex[:12]
    pairs: list[dict[str, Any]] = []
    spent = 0.0
    aborted = False
    for case in cases:
        if spent >= per_cap:
            aborted = True
            break
        vals = []
        for arm in ("A1", "A2"):
            m = measures(run_arm(_load(spec.package_root), case, arm, tid), "run_cost", None, None)  # type: ignore[arg-type]
            spent += m["cost"]
            vals.append(m)
        differ = (vals[0]["exit_code"], vals[0]["outcome_met"], vals[0]["check_pass"]) != (
            vals[1]["exit_code"], vals[1]["outcome_met"], vals[1]["check_pass"])
        pairs.append({"case": case.case_id, "differ": differ})
    floor: float | str = (sum(1 for p in pairs if p["differ"]) / len(pairs)) if pairs else "unknown"
    out = {"schema_version": 1, "kind": "aa", "trial_id": tid, "workflow": spec.name, "case_set_digest": digest,
           "pairs": pairs, "noise_floor": floor, "aborted": aborted, "spend": {"total": round(spent, 6)},
           "at": now_iso()}
    save(root, out)
    return out
