"""Stages of a run, the promotion check and the promotion stamp (PRO §2.1 to §2.4). Model-free.

The check reads the functions the reports read (`report`, `report --supervision`, `evals bar`, `evals report`),
so a number never differs between two verbs. Release 2 measures and stamps `local-stable`; `pipeline` is
refused with `not_in_release`.
"""

from __future__ import annotations

import hashlib
import json
from collections import defaultdict
from collections.abc import Mapping, Sequence
from dataclasses import dataclass, field
from importlib import resources
from pathlib import Path
from typing import Any

from tempergraph.contracts import STAGES, WorkflowSpec

PROMOTION = "promotion.json"
BUILT = ("local-stable",)  # the targets this release measures and stamps
EXCLUDED_ORIGINS = frozenset({"trial", "scenario", "evals"})
STAMP_CALLERS = frozenset({"person"})  # who may decide a stamp; a pipeline caller arrives with pipelines
FINAL_EXITS = frozenset({0, 4, 5})
FAULT_SIDES = ("engine", "executor")


class PromotionRefused(ValueError):
    def __init__(self, code: str, message: str) -> None:
        super().__init__(message)
        self.code = code


def stage_of(spec: WorkflowSpec, caller: Mapping[str, Any] | None = None) -> tuple[str, bool]:
    """PRO §2.1: the stage of a run, and whether a pipeline caller runs it unpromoted. No run has stage
    `pipeline` in this release, so a pipeline caller always runs at the local stage."""
    stage = "local-stable" if spec.improvement_mode == "stable" else "local-dev"
    return stage, (caller or {}).get("kind") == "pipeline"


def bars(stage: str) -> dict[str, float]:
    """The stage's bars, from the one engine config file (PRO §2.3)."""
    doc = json.loads(resources.files("tempergraph.data").joinpath(PROMOTION).read_text(encoding="utf-8"))
    return {str(k): float(v) for k, v in doc["stages"][stage].items()}


def current_version(spec: WorkflowSpec) -> str:
    """The workflow version with its content digest (VER §2.4) for a package, else the declared version."""
    if spec.package_root is None:
        return spec.version
    from tempergraph.package.loader import load_package

    return load_package(spec.package_root).workflow_version  # read anew: a changed file voids a stamp


@dataclass(kw_only=True)
class WindowRun:
    thread: Any  # observe.report.Thread
    records: list[dict[str, Any]]
    request: str | None
    escapes: int = 0


def _escapes(t: Any) -> int:
    from tempergraph.observe import report

    return sum(int(c["escapes"]) for c in report.criteria([t]))


def window(root: Path, spec: WorkflowSpec, version: str, size: int, *, restart_on_escape: bool = False
           ) -> list[WindowRun]:
    """PRO §2.2: the last `size` finished runs of this workflow version, oldest first. Trial, scenario, eval
    and dry runs and reruns of a trial are left out. With `restart_on_escape` (a stage whose escape bar is 0)
    the window starts after the last run that held a gate escape."""
    from tempergraph.observe import report
    from tempergraph.run.events import records as read_records

    out: list[WindowRun] = []
    base = root / "runs" / spec.name
    for log in sorted(base.glob("*/run.jsonl")) if base.is_dir() else []:
        recs = list(read_records(log))
        t = report.fold(recs, log.parent)
        starts = [r for r in recs if r.get("kind") == "run_started"]
        if t is None or not starts or t.exit is None or int(t.exit.get("exit_code") or 0) not in FINAL_EXITS:
            continue
        first = starts[0]
        rerun = first.get("rerun_of") or {}
        if any(s.get("origin") in EXCLUDED_ORIGINS or s.get("dry_run") for s in starts) \
                or (isinstance(rerun, Mapping) and rerun.get("origin") == "trial"):
            continue
        ran = next((s.get("content_version") for s in reversed(starts) if s.get("content_version")), None) \
            or t.version
        if ran != version and not (ran == spec.version and "+" not in str(ran)):
            continue
        task = next((r for r in recs if r.get("kind") == "task"), {})
        req = str(task.get("request") or "")
        out.append(WindowRun(thread=t, records=recs, escapes=_escapes(t),
                             request=hashlib.sha256(req.encode()).hexdigest()[:16] if req else None))
    out.sort(key=lambda w: str(w.thread.exit.get("ts") or w.thread.started_at or ""))
    if restart_on_escape:
        last = max((i for i, w in enumerate(out) if w.escapes), default=-1)
        out = out[last + 1:]
    return out[-size:] if size > 0 else []


def _row(pid: str, name: str, value: Any, bar: Any, met: bool | None, *, detail: str = "") -> dict[str, Any]:
    """`met` None is a reported row; a missing value is `unmeasured`, which is not met (PRO §2.3)."""
    verdict = "reported" if met is None else "unmeasured" if value is None else "met" if met else "not_met"
    return {"id": pid, "criterion": name, "value": value, "bar": bar, "verdict": verdict,
            **({"detail": detail} if detail else {})}


def _at_most(v: float | None, bar: float) -> bool:
    return v is not None and v <= bar


def _at_least(v: float | None, bar: float) -> bool:
    return v is not None and v >= bar


def _supervision(root: Path, ids: set[str], b: Mapping[str, float]) -> list[dict[str, Any]]:
    """P5: the rows of SUP §2.7 over the window, from `report --supervision`'s own aggregate."""
    from tempergraph.observe import supervision_report as sr

    rs = [r for r in sr.runs(root) if r.thread_id in ids]
    n = len(ids)
    a = sr.aggregate(rs)
    recorded = len(rs) / n if n else 0.0
    und = a["undesigned_per_run"] if rs and recorded == 1.0 else None
    lower = (a["unattended_interval"] or [None])[0] if rs and recorded == 1.0 else None
    share = a["supervision_share"]
    measured = round(share["measured"] / n, 4) if n else None
    median = share["median"] if measured is not None and measured >= b["share_measured"] else None
    known = a["data_quality"]["callers_known"] if rs and recorded == 1.0 else None
    cost = round(a["supervision_cost_per_run"]["measured"] / n, 4) if n else None
    note = "" if recorded == 1.0 else f"{n - len(rs)} of {n} runs have no supervision record"
    rows = [
        _row("P5.undesigned", "undesigned touches per run, every decider", und, f"<= {b['undesigned_per_run']:g}",
             _at_most(und, b["undesigned_per_run"]), detail=note),
        _row("P5.unattended", "unattended rate, lower bound of the interval", lower,
             f">= {b['unattended_lower_bound']:g}", _at_least(lower, b["unattended_lower_bound"]), detail=note),
        _row("P5.agent_rescues", "agent's own rescue share", a["agent_own_rescue_share"],
             f"<= {b['agent_own_rescue_share']:g}" if "agent_own_rescue_share" in b else "reported",
             _at_most(a["agent_own_rescue_share"], b["agent_own_rescue_share"])
             if "agent_own_rescue_share" in b and a["agent_own_rescue_share"] is not None else None),
        _row("P5.share", "supervision share, median", median, f"<= {b['supervision_share_median']:g}",
             _at_most(median, b["supervision_share_median"]),
             detail=f"measured on {share['measured']} of {n} runs; at least {b['share_measured']:g} of them needed"),
        _row("P5.callers", "runs with every caller known", known, f">= {b['callers_known']:g}",
             _at_least(known, b["callers_known"]), detail=note),
    ]
    if "cost_measured" in b:
        rows.append(_row("P5.cost_measured", "runs with supervision cost measured",
                         cost if cost is not None and cost >= b["cost_measured"] else None,
                         f">= {b['cost_measured']:g}", cost is not None and cost >= b["cost_measured"],
                         detail=f"measured on {cost if cost is not None else 0:g} of the runs"))
    else:
        rows.append(_row("P5.cost_measured", "runs with supervision cost measured", cost, "reported", None))
    return rows


def _judges(spec: WorkflowSpec, root: Path) -> dict[str, Any]:
    """P4: every judged gate's binding `accepted`, each routed risk level included (JRK §2.4)."""
    from tempergraph.improve import calibration as cal

    bad: list[str] = []
    bindings: dict[str, Any] = {}
    gates = cal.judged_gates(spec)
    try:
        for st in cal.states(spec, state_root=root):
            bindings[st.gate] = {k: st.binding.get(k) for k in ("executor", "alias")}
            if st.state != "accepted":
                bad.append(f"{st.gate}: {st.state}")
        for gate in gates:
            bad += [f"{gate}@{lv}: {name}" for lv, name in cal.unaccepted_levels(spec, gate)]
    except (cal.CalibrationError, OSError, ValueError) as exc:
        bad.append(f"unreadable: {type(exc).__name__}")
    row = _row("P4", "every gate's judge binding accepted, routed risk levels included",
               len(gates) - len({b.split(":")[0].split("@")[0] for b in bad} & set(gates)),
               f"{len(gates)} of {len(gates)} gates", not bad, detail="; ".join(bad))
    return {"row": row, "bindings": bindings}


def _p90(xs: Sequence[float]) -> float | None:
    from tempergraph.observe.supervision_report import _pct

    return _pct(list(xs), 0.9)


def _escalations(root: Path, spec: WorkflowSpec, ids: set[str]) -> dict[str, dict[str, Any]]:
    """P9: escalated attempts per unit in the window, from the escalation record (LAD §2.7)."""
    from tempergraph.improve.calibration import wilson_lb

    by: dict[str, list[bool]] = defaultdict(list)
    try:
        lines = (root / "ledger.jsonl").read_text(encoding="utf-8").splitlines()
    except OSError:
        lines = []
    for ln in lines:
        try:
            r = json.loads(ln)
        except ValueError:
            continue
        if isinstance(r, dict) and r.get("kind") == "escalation" and r.get("workflow") == spec.name \
                and r.get("thread_id") in ids:
            by[str(r.get("unit"))].append(bool(r.get("passed")))
    return {u: {"attempts": len(v), "passed": sum(v), "pass_lower_bound": round(wilson_lb(sum(v), len(v)), 4)}
            for u, v in sorted(by.items())}


def _ladders(spec: WorkflowSpec, runs: Sequence[WindowRun]) -> dict[str, dict[str, Any]]:
    """P10: per unit with an effort ladder, the share of its attempts that ran above rung 0."""
    out: dict[str, dict[str, Any]] = {}
    for name, u in spec.units.items():
        if u.step is None or not u.step.effort_ladder:
            continue
        ss = [s for w in runs for s in w.thread.sessions if s.unit == name and s.kind in ("step", "retry")]
        climbed = sum(1 for s in ss if s.climbed)
        out[name] = {"attempts": len(ss), "climbed": climbed, "share": round(climbed / len(ss), 4) if ss else None,
                     **({"ladder_unseen": True} if not climbed else {})}
    return out


def _arms(runs: Sequence[WindowRun]) -> dict[str, dict[str, int]]:
    """P11: runs per switch arm in the window."""
    by: dict[str, dict[str, set[str]]] = defaultdict(lambda: defaultdict(set))
    for w in runs:
        for r in w.thread.routes:
            by[str(r.get("unit"))][str(r.get("arm"))].add(w.thread.thread_id)
    return {u: {a: len(ts) for a, ts in sorted(arms.items())} for u, arms in sorted(by.items())}


@dataclass(kw_only=True)
class Report:
    workflow: str
    to: str
    workflow_version: str
    executor: str
    window: dict[str, Any] = field(default_factory=dict)
    criteria: list[dict[str, Any]] = field(default_factory=list)
    alias_bindings: dict[str, Any] = field(default_factory=dict)
    ladder_seen: dict[str, Any] = field(default_factory=dict)
    escalation_covered: dict[str, Any] = field(default_factory=dict)
    arms_covered: dict[str, Any] = field(default_factory=dict)
    stamp: dict[str, Any] | None = None
    stamped: bool = False
    refused: str | None = None

    @property
    def met(self) -> bool:
        return bool(self.criteria) and all(c["verdict"] in ("met", "reported") for c in self.criteria)

    @property
    def exit_code(self) -> int:
        return 0 if self.met and not self.refused else 6

    def to_json(self) -> dict[str, Any]:
        return {"schema_version": 1, "workflow": self.workflow, "to": self.to,
                "workflow_version": self.workflow_version, "executor": self.executor, "met": self.met,
                "window": self.window, "criteria": self.criteria, "alias_bindings": self.alias_bindings,
                "ladder_seen": self.ladder_seen, "escalation_covered": self.escalation_covered,
                "arms_covered": self.arms_covered, "stamp": self.stamp, "stamped": self.stamped,
                **({"refused": self.refused} if self.refused else {})}


def check(spec: WorkflowSpec, root: Path, *, to: str, executor: str | None = None, size: int | None = None
          ) -> Report:
    """PRO §2.3: every criterion's number, bar and verdict for the target stage. Reads only."""
    from tempergraph.improve import record, suites
    from tempergraph.improve.trials import run_cost
    from tempergraph.observe import report as rep

    if to not in STAGES or to == "local-dev":
        raise PromotionRefused("usage", "`--to` is `local-stable` or `pipeline`")
    if to not in BUILT:
        raise PromotionRefused("not_in_release", f"`--to {to}` arrives with pipelines in a later release "
                                                 "(not_in_release); `--to local-stable` is built")
    b = bars(to)
    size = int(size if size is not None else b["window"])
    if size < 1:
        raise PromotionRefused("usage", "`--window` takes a whole number of runs, 1 or more")
    version = current_version(spec)
    runs = window(root, spec, version, size, restart_on_escape=b["gate_escapes"] == 0)
    ts = [w.thread for w in runs]
    ids = {t.thread_id for t in ts}
    out = Report(workflow=spec.name, to=to, workflow_version=version, executor=executor or spec.default_executor)
    out.window = {"size": size, "runs": len(runs), "threads": sorted(ids),
                  "stamp": read_stamps(spec.package_root, version) if spec.package_root else {}}
    requests = {w.request for w in runs if w.request}
    need = int(b["runs"])  # a smaller `--window` never lowers the bar
    out.criteria.append(_row(
        "P1", "runs in the window, with distinct requests", len(runs) or None,
        f">= {need} runs, {int(b['distinct_requests'])} distinct requests",
        len(runs) >= need and len(requests) >= b["distinct_requests"], detail=f"{len(requests)} distinct requests"))
    first = next(iter(rep.ladder(ts)), {}).get("first_pass") or {}
    gates = int(first.get("gates") or 0)
    fpy = round(int(first.get("passed") or 0) / gates, 4) if gates else None
    out.criteria.append(_row("P2", "first-pass yield of rung-0 attempts", fpy, f">= {b['first_pass_yield']:g}",
                             _at_least(fpy, b["first_pass_yield"]), detail=f"{gates} gates"))
    escapes = sum(w.escapes for w in runs) if runs else None
    out.criteria.append(_row("P3", "gate escapes in the window", escapes, f"<= {int(b['gate_escapes'])}",
                             _at_most(escapes, b["gate_escapes"])))
    judges = _judges(spec, root)
    out.criteria.append(judges["row"] if runs else {**judges["row"], "value": None, "verdict": "unmeasured"})
    out.alias_bindings = judges["bindings"]
    out.criteria += _supervision(root, ids, b)
    costs = [run_cost(w.records) for w in runs]
    cap = spec.run_cost_cap_usd
    out.criteria.append(_row("P6", "run cost per run, p90", _p90(costs), "reported", None,
                             detail=f"run_cost_cap_usd {cap:g}" if cap is not None else "no run_cost_cap_usd"))
    faults = sorted({str(f.get("fingerprint")) for t in ts
                     for f in record.read_findings(root, spec.name, t.thread_id.split("/", 1)[-1])
                     if f.get("class") == "fault" and str(f.get("side") or "").split(":")[0] in FAULT_SIDES})
    out.criteria.append(_row("P7", "engine or executor fault findings of the window's runs", len(faults),
                             "reported", None, detail=", ".join(faults[:5])))
    states: dict[str, int] = defaultdict(int)
    for s in suites.report(spec, root)["suites"]:
        states[str(s["status"])] += 1
    out.criteria.append(_row("P8", "eval suites of the workflow", dict(sorted(states.items())) or None,
                             "reported", None))
    out.escalation_covered = _escalations(root, spec, ids)
    out.criteria.append(_row("P9", "escalated attempts: count and pass rate per unit",
                             out.escalation_covered or None, "reported", None))
    out.ladder_seen = _ladders(spec, runs)
    unseen = sorted(u for u, v in out.ladder_seen.items() if v.get("ladder_unseen"))
    out.criteria.append(_row("P10", "effort ladder seen: share of climbed attempts per unit",
                             {u: v["share"] for u, v in out.ladder_seen.items()} or None, "reported", None,
                             detail=f"ladder_unseen: {', '.join(unseen)}" if unseen else ""))
    out.arms_covered = _arms(runs)
    out.criteria.append(_row("P11", "switch arms: runs per arm", out.arms_covered or None, "reported", None))
    return out


def _doc(root: Path) -> tuple[dict[str, Any], bool]:
    """The package's `promotion.json` and whether it could be read; an unreadable file is no stamp."""
    try:
        doc = json.loads((root / PROMOTION).read_text(encoding="utf-8"))
    except FileNotFoundError:
        return {}, True
    except (OSError, ValueError):
        return {}, False
    ok = isinstance(doc, dict) and isinstance(doc.get("stamps"), dict)
    return (doc if ok else {}), ok


def read_stamps(root: Path | None, version: str) -> dict[str, Any]:
    """Each stage's stamp and whether it stands: a stamp of another workflow version is void (PRO §2.4)."""
    if root is None:
        return {}
    doc, ok = _doc(root)
    out: dict[str, Any] = {} if ok else {"warning": f"{PROMOTION} is unreadable: treated as no stamp"}
    for stage, e in (doc.get("stamps") or {}).items():
        if isinstance(e, dict):
            out[str(stage)] = {"workflow_version": e.get("workflow_version"), "stamped_at": e.get("stamped_at"),
                               "state": "current" if e.get("workflow_version") == version else "void"}
    return out


def stamped(spec: WorkflowSpec, stage: str) -> bool:
    """Whether the current workflow version holds the stage's stamp."""
    if spec.package_root is None:
        return False
    return (read_stamps(spec.package_root, current_version(spec)).get(stage) or {}).get("state") == "current"


def stamp(spec: WorkflowSpec, rep: Report, caller: Mapping[str, Any]) -> Report:
    """`--stamp`: writes the stage's entry only when every criterion is met, for a person, into a package
    that is not an installed copy (PRO §2.4, §4). A void entry of another stage is dropped."""
    from tempergraph.docs import write_json
    from tempergraph.package.registry import plugin_cache
    from tempergraph.store.layout import now_iso

    root = spec.package_root
    kind = str(caller.get("kind") or "unknown")
    if kind == "pipeline":
        raise PromotionRefused("not_in_release", "a pipeline caller's stamp arrives with pipelines in a later "
                                                 "release (not_in_release)")
    if root is None:
        raise PromotionRefused("usage", "only a workflow package can be stamped")
    if root.resolve().is_relative_to(plugin_cache().resolve()):
        raise PromotionRefused("usage", "stamp the workflow's source; this is an installed copy")
    if caller.get("decided_by") not in STAMP_CALLERS:
        raise PromotionRefused("usage", "a promotion stamp needs a person: run it yourself, or pass --relayed "
                                        "with the person's words")
    if not rep.met:
        return rep
    doc, _ = _doc(root)
    kept = {s: e for s, e in (doc.get("stamps") or {}).items()
            if isinstance(e, dict) and e.get("workflow_version") == rep.workflow_version}
    rep.stamp = {"stage": rep.to, "workflow_version": rep.workflow_version, "executor": rep.executor,
                 "alias_bindings": rep.alias_bindings, "criteria": rep.criteria, "ladder_seen": rep.ladder_seen,
                 "escalation_covered": rep.escalation_covered, "arms_covered": rep.arms_covered,
                 "stamped_at": now_iso(),
                 "caller": {k: caller.get(k) for k in ("kind", "confidence", "decided_by", "relay", "host")}}
    write_json(root / PROMOTION, {"schema_version": 1, "stamps": {**kept, rep.to: rep.stamp}}, mode=0o644)
    rep.stamped = True
    return rep


def text(rep: Report) -> str:
    lines = [f"{rep.workflow} {rep.workflow_version} to {rep.to}: "
             f"{'every criterion met' if rep.met else 'not met'} ({rep.window.get('runs')} runs in the window)"]
    for c in rep.criteria:
        val = "-" if c["value"] is None else json.dumps(c["value"]) if isinstance(c["value"], dict) else c["value"]
        lines.append(f"  {c['id']:<17} {c['verdict']:<10} {val}  (bar: {c['bar']})  {c['criterion']}"
                     + (f"  [{c['detail']}]" if c.get("detail") else ""))
    if rep.stamped:
        lines.append(f"stamped: {PROMOTION}")
    return "\n".join(lines) + "\n"
