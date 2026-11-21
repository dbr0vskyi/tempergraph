"""Rungs 8 and 9 of `author verify` (SCF §2.5) and the trial report and grades (SCF §2.5, §2.7).

Rung 8 grades each judged criterion's seed fixtures (`scale.seeds`, OUT §2.2.1) with the gate's real judge,
twice, on scratch copies, with no step session (SCF-AC-5, AC-7). Rung 9 starts one run of a case from
`evals/cases.json` in a fresh worktree, as a dry run with `run.run_cost_cap_usd` set to what is left of the
cap. `author trial` shows each criterion's status beside the person's grade, disagreements first, and
`author grade` writes one grade: a ledger label (`source` from the caller's decider, `origin: authoring_trial`,
FBK §2.1) for a judged criterion, and the grade into a calibration case candidate for that gate (JCL §2.1).
The workflow's `improvement_mode` is never changed (SCF-AC-6).
"""

from __future__ import annotations

import json
import shutil
import uuid
from collections.abc import Callable, Mapping
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

from tempergraph.contracts import WorkflowSpec
from tempergraph.docs import append_jsonl, write_json
from tempergraph.store.layout import home_path, now_iso, run_dir

MAX_COPY_BYTES = 5 * 1024 * 1024  # a trial's workspace copied into a candidate case, as the inventory's limit


class TrialRefused(ValueError):
    def __init__(self, code: str, message: str) -> None:
        super().__init__(message)
        self.code = code


def _row(code: str, unit: str | None, message: str, remedy: str = "") -> dict[str, Any]:
    return {"code": code, "unit": unit, "message": message, "remedy": remedy}


LADDER = "return to the guidance ladder of AUT §2.4.1 for this criterion: its text or scale is not clear enough"


# -- rung 8: judge seeds ------------------------------------------------------------------------------------

@dataclass(kw_only=True)
class SeedResult:
    findings: list[dict[str, Any]] = field(default_factory=list)
    graded: list[dict[str, Any]] = field(default_factory=list)  # {gate, criterion, seed, expected, got[]}
    sessions: int = 0
    spent: float = 0.0
    shown: dict[str, dict[str, str]] = field(default_factory=dict)  # gate -> seed id -> gate digest when shown
    tuned: list[str] = field(default_factory=list)  # gate/seed ids moved to `tune`


def gate_digest(spec: WorkflowSpec, gate: str) -> str:
    """The criteria and the judge brief of a gate: what an author edits after seeing a seed."""
    import hashlib

    from tempergraph.improve import calibration as cal

    g, _, _ = cal.gate_spec(spec, gate)
    brief = ""
    if g.judge is not None and g.judge.file and spec.package_root is not None:
        try:
            brief = (Path(spec.package_root) / g.judge.file).read_text(encoding="utf-8")
        except OSError:
            brief = ""
    parts = [[c.id, c.text, c.check_method, json.dumps(c.verifier or {}, sort_keys=True)] for c in g.criteria]
    body = json.dumps([parts, brief, (g.judge.stance, g.judge.brief) if g.judge else None], sort_keys=True)
    return hashlib.sha256(body.encode("utf-8")).hexdigest()


def _seed_expected(doc: Mapping[str, Any], criterion: str) -> str | None:
    """The author's own expectation, stated in the case's `seed` block (one entry or a list of them). It serves
    rung 8 only, which writes no score; a person's label for the criterion comes first (SCF §2.5)."""
    block = doc.get("seed")
    for entry in block if isinstance(block, list) else [block]:
        if isinstance(entry, Mapping) and entry.get("criterion_id") == criterion and entry.get("expected"):
            return str(entry["expected"])
    return None


def seeds(spec: WorkflowSpec, executor_for: Callable[[str], Any], cap: float | None,
          shown: Mapping[str, Mapping[str, str]] | None = None) -> SeedResult:
    """Each judged criterion's seeds, graded twice by its gate's judge; one judge session grades every
    criterion of the gate for a seed, so a seed shared by two criteria is judged twice, not four times.

    `shown` holds the seeds a failing rung 8 showed the author, with the gate's digest then. A seed whose gate
    changed since was in front of someone editing that gate, so it moves to `tune` for good (JCL §2.1.1); a
    seed only graded and never edited against stays `holdout`."""
    from tempergraph.improve import calibration as cal

    out = SeedResult()
    root0 = spec.package_root
    for gate, by_seed in dict(shown or {}).items():
        try:
            now = gate_digest(spec, gate)
        except cal.CalibrationError:
            continue
        edited = [sid for sid, d in by_seed.items() if d != now]
        if edited and root0 is not None:
            out.tuned += [f"{gate}/{x}" for x in cal.mark_tune(Path(root0), gate, edited, by="author")]
        keep = {sid: d for sid, d in by_seed.items() if d == now}
        if keep:
            out.shown[gate] = keep
    root = spec.package_root
    if root is None:
        out.findings.append(_row("seeds-no-package", None, "the workflow has no package folder"))
        return out
    for gate in cal.judged_gates(spec):
        g, _, _ = cal.gate_spec(spec, gate)
        judged = [c for c in g.criteria if c.id and c.verified_by == "judge"]
        wanted: dict[str, list[tuple[str, str]]] = {}  # seed id -> [(criterion, expected)]
        for c in judged:
            scale = (c.verifier or {}).get("scale") if isinstance(c.verifier, Mapping) else None
            ids = [str(s) for s in (scale or {}).get("seeds") or [] if s] if isinstance(scale, Mapping) else []
            if len(ids) < 2:
                out.findings.append(_row("criterion-no-seed", gate, f"{c.id}: needs a met seed and an unmet or "
                                         f"partial seed (OUT §2.2.1)", "ask for one example of each, or offer a "
                                         "contrast pair, and save them under evals/calibration/" + gate))
                continue
            for sid in ids:
                folder = cal.calibration_dir(root, gate) / sid
                if not (folder / "case.json").is_file():
                    out.findings.append(_row("seed-not-found", gate, f"{c.id}: seed {sid} is not a case under "
                                             f"evals/calibration/{gate}/", "write the seed fixture"))
                    continue
                case = cal.load_case(folder, gate)
                exp = next((str(lab.get("expected")) for lab in case.labels
                            if lab.get("criterion_id") == c.id), None) or _seed_expected(case.doc, str(c.id))
                if exp is None:
                    out.findings.append(_row("seed-unlabelled", gate, f"{c.id}: seed {sid} has no expected "
                                             f"status for it", f"state it in the case's `seed` block, or "
                                             f"`tempergraph evals label {spec.name}/{gate}/{sid} "
                                             f"--criterion {c.id} --expected …`"))
                    continue
                wanted.setdefault(sid, []).append((str(c.id), exp))
        if not wanted:
            continue
        ex = executor_for(gate)
        for sid, pairs in sorted(wanted.items()):
            case = cal.load_case(cal.calibration_dir(root, gate) / sid, gate)
            subject = cal.base_subject(case, g.criteria)
            got: list[dict[str, str]] = []
            for r in (1, 2):
                if cap is not None and out.spent >= cap:
                    out.findings.append(_row("seeds-cap-reached", gate, f"the cap of ${cap:.2f} was reached "
                                             f"before seed {sid} was graded twice", "raise --cap, or grade fewer "
                                             "seeds"))
                    return out
                jd = cal.judge_once(spec, gate, subject, ex, f"author.seeds.{gate}.{sid}.{r}")
                out.sessions += 1
                out.spent += jd.cost
                got.append(jd.statuses)
            for cid, exp in pairs:
                a, b = got[0].get(cid, "missing"), got[1].get(cid, "missing")
                if a != b or a != exp:  # shown to the author, who now goes back to the guidance ladder
                    out.shown.setdefault(gate, {})[sid] = gate_digest(spec, gate)
                out.graded.append({"gate": gate, "criterion": cid, "seed": sid, "expected": exp, "got": [a, b]})
                if a != b:
                    out.findings.append(_row("seed-unstable", gate, f"{cid}: seed {sid} was graded {a} once and "
                                             f"{b} once (expected {exp})", LADDER))
                elif a != exp:
                    out.findings.append(_row("seed-misgraded", gate, f"{cid}: seed {sid} was graded {a} both "
                                             f"times; expected {exp}", LADDER))
    return out


# -- rung 9: the first trial --------------------------------------------------------------------------------

def _cases(root: Path) -> list[dict[str, Any]]:
    try:
        doc = json.loads((root / "evals" / "cases.json").read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return []
    return [c for c in doc.get("cases") or [] if isinstance(c, dict)] if isinstance(doc, dict) else []


def _records(path: Path) -> list[dict[str, Any]]:
    from tempergraph.run.events import records

    return list(records(path)) if path.is_file() else []


def start_trial(spec: WorkflowSpec, case_id: str, target: Path, registry: Any, caller: Mapping[str, Any],
                cap: float) -> dict[str, Any]:
    """One live run of the case: a fresh worktree, a dry run, the cap as the run's cost cap, the caller
    recorded (PRV). Returns the trial record kept in `authoring.json` (`trial`)."""
    from tempergraph.constants import ExitCode
    from tempergraph.run.runner import RunSettings, start

    case = next((c for c in _cases(spec.package_root or Path(".")) if str(c.get("id")) == case_id), None)
    if case is None:
        raise TrialRefused("trial-case-unknown", f"no case {case_id!r} in evals/cases.json")
    inputs = {"request": str(case.get("request") or "")}
    inputs.update({str(k): str(v) for k, v in dict(case.get("inputs") or {}).items()})
    task = f"trial-{case_id}-{uuid.uuid4().hex[:4]}"
    settings = RunSettings(workspace="worktree", dry_run=True, caller=dict(caller), label=f"authoring trial {case_id}",
                           flags={"run.run_cost_cap_usd": max(cap, 0.0)})
    got = start(spec, task, inputs, target, registry, settings)
    rec = {"case": case_id, "task": task, "thread": f"{spec.name}/{task}", "at": now_iso(),
           "exit_code": int(got.exit_code), "reason": got.reason, "cap_usd": cap, "grades": {}}
    if got.exit_code is ExitCode.PAUSED:
        rec["state"] = "paused"
    elif got.exit_code is ExitCode.BUDGET_OR_INFRA and got.reason == "cost_cap":
        rec["state"] = "partial"
    elif got.exit_code is ExitCode.USAGE:
        rec["state"] = "refused"
        rec["message"] = got.message
    else:
        rec["state"] = "ended"
    return rec


def _state_root(target: Path) -> Path:
    from tempergraph.store.layout import state_root_path

    return state_root_path(target)


def rows(spec: WorkflowSpec, target: Path, task: str) -> tuple[list[dict[str, Any]], dict[str, Any] | None]:
    """Each outcome criterion of the trial thread with the status its verifier gave, and the outcome record
    (None until the run reached the outcome gate). A check-verified criterion takes its unit's check result
    (PASS is MET, FAIL is UNMET); a criterion nobody graded yet is `not_judged`."""
    from tempergraph.model import flow

    recs = _records(run_dir(_state_root(target), spec.name, task) / "run.jsonl")
    judged: dict[str, dict[str, str]] = {}
    checks: dict[str, str] = {}
    outcome = None
    for r in recs:
        if r.get("kind") == "judgement":
            judged[str(r.get("unit"))] = {str(s.get("id")): str(s.get("status")) for s in r.get("statuses") or []
                                          if s.get("id")}
        elif r.get("kind") == "check":
            checks[str(r.get("unit"))] = str(r.get("result"))
        elif r.get("kind") == "outcome":
            outcome = r
    out: list[dict[str, Any]] = []
    o = spec.outcome
    if o is None:
        return out, outcome
    pairs = [(flow.OUTCOME_UNIT, c) for c in o.final] + [(u, c) for u, io in o.intermediate.items()
                                                         for c in io.criteria]
    for unit, c in pairs:
        status = judged.get(unit, {}).get(str(c.id))
        if status is None and c.verified_by == "check" and unit in checks:
            status = "MET" if checks[unit] == "PASS" else "UNMET"
        if status is None and unit == flow.OUTCOME_UNIT and outcome is not None:
            status = next((str(x.get("status")) for x in outcome.get("criteria") or [] if x.get("id") == c.id), None)
        out.append({"unit": unit, "criterion": c.id, "class": c.verified_by or "none", "severity": c.severity,
                    "text": c.text, "check_method": c.check_method, "status": status or "not_judged"})
    return out, outcome


def _norm(s: str) -> str:
    return "N/A" if s == "n_a" else s


def report(spec: WorkflowSpec, trial: Mapping[str, Any], target: Path) -> dict[str, Any]:
    """The trial report: per criterion the verifier's status and the person's grade; a disagreement is listed
    first, with the criterion's text and check method (SCF-B6)."""
    got, outcome = rows(spec, target, str(trial.get("task")))
    grades = dict(trial.get("grades") or {})
    for r in got:
        g = grades.get(f"{r['unit']}/{r['criterion']}")
        r["grade"] = (g or {}).get("status")
        r["disagrees"] = bool(r["grade"]) and r["status"] not in ("not_judged",) and _norm(r["status"]) != r["grade"]
    got.sort(key=lambda r: (not r["disagrees"], r["grade"] is not None, r["unit"] != "outcome"))
    left = [f"{r['unit']}/{r['criterion']}" for r in got if r["grade"] is None]
    return {"schema_version": 1, "workflow": spec.name, "thread": trial.get("thread"), "case": trial.get("case"),
            "state": trial.get("state"), "verdict": (outcome or {}).get("verdict") or "not_reached",
            "criteria": got, "ungraded": left}


def grade(spec: WorkflowSpec, root: Path, target: Path, trial: dict[str, Any], unit: str, criterion: str,
          status: str, reason: str, caller: Mapping[str, Any], *, relayed: bool = False,
          reviewer: str = "unknown") -> dict[str, Any]:
    """One grade of the person on one criterion of the trial's output."""
    from tempergraph.improve import calibration as cal
    from tempergraph.observe.labels import LabelRefused, label
    from tempergraph.provenance import decide

    if status not in cal.STATUSES:
        raise TrialRefused("grade-status", f"--status must be one of {', '.join(cal.STATUSES)}")
    got, _ = rows(spec, target, str(trial.get("task")))
    row = next((r for r in got if r["unit"] == unit and r["criterion"] == criterion), None)
    if row is None:
        raise TrialRefused("grade-criterion", f"{unit}/{criterion} is not a criterion of the outcome "
                           f"({', '.join(sorted(r['unit'] + '/' + str(r['criterion']) for r in got))})")
    decided = decide(caller, relayed=relayed, words=("author", "grade"), home=home_path())
    by_person = decided.get("decided_by") == "person"
    sroot = _state_root(target)
    out: dict[str, Any] = {"unit": unit, "criterion": criterion, "status": status, "verifier": row["status"],
                           "by_person": by_person, "label": None, "case": None}
    if row["class"] == "judge" and row["status"] != "not_judged":
        try:
            lab = label(sroot, str(trial["thread"]), unit, "agree" if _norm(row["status"]) == status else "disagree",
                        dict(caller), criterion=criterion, relayed=relayed)
        except LabelRefused:
            lab = None
        if lab is not None:
            lab["origin"] = "authoring_trial"
            append_jsonl(sroot / "ledger.jsonl", lab)
            out["label"] = {k: lab[k] for k in ("label_id", "value", "source", "origin")}
        out["case"] = _candidate(spec, root, target, trial, unit, criterion, status, reason, reviewer, by_person)
    trial.setdefault("grades", {})[f"{unit}/{criterion}"] = {"status": status, "by_person": by_person,
                                                               "at": now_iso()}
    return out


def _candidate(spec: WorkflowSpec, root: Path, target: Path, trial: Mapping[str, Any], gate: str, criterion: str,
               status: str, reason: str, reviewer: str, by_person: bool) -> str | None:
    """The trial's output as a calibration case candidate for the gate's judge: the request and the trial
    workspace's files, and the person's grade as its label (JCL §2.1, `provenance: harvested`)."""
    from tempergraph.improve import calibration as cal

    try:
        g, _, _ = cal.gate_spec(spec, gate)
    except cal.CalibrationError:
        return None
    case_id = f"trial-{trial.get('task')}"
    folder = cal.calibration_dir(root, gate) / case_id
    fixture = folder / "fixture"
    if not (folder / "case.json").is_file():
        (fixture / "workspace").mkdir(parents=True, exist_ok=True)
        case = next((c for c in _cases(root) if str(c.get("id")) == trial.get("case")), {})
        (fixture / "request.md").write_text(str(case.get("request") or ""), encoding="utf-8")
        _copy_workspace(spec, target, str(trial.get("task")), fixture / "workspace")
        write_json(folder / "case.json", {"schema_version": 1, "case_id": case_id, "gate": gate, "labels": [],
                                          "provenance": "harvested", "state": "candidate",
                                          "producer_family": "unknown", "source_thread": trial.get("thread")},
                   mode=0o644)
    c = cal.load_case(folder, gate)
    ids = {x.id: x for x in g.criteria if x.id}
    lab = {"criterion_id": criterion, "expected": status, "reason": " ".join(reason.split())[:300],
           "reviewer": reviewer, "by_person": by_person, "at": now_iso(), "origin": "authoring_trial",
           **({"criterion_digest": cal.criterion_digest(ids[criterion])} if criterion in ids else {})}
    c.labels = [x for x in c.labels if x.get("criterion_id") != criterion] + [lab]
    c.state = "candidate"  # a person confirms it with `evals label` before it is scored (JCL §2.1)
    c.save()
    return f"{gate}/{case_id}"


def _copy_workspace(spec: WorkflowSpec, target: Path, task: str, dest: Path) -> None:
    recs = _records(run_dir(_state_root(target), spec.name, task) / "run.jsonl")
    ws = next((r for r in reversed(recs) if r.get("kind") == "workspace" and r.get("path")), None)
    src = Path(str(ws["path"])) if ws else None
    if src is None or not src.is_dir():
        return
    total = 0
    for p in sorted(src.rglob("*")):
        rel = p.relative_to(src)
        if ".git" in rel.parts or ".tempergraph" in rel.parts or not p.is_file():
            continue
        total += p.stat().st_size
        if total > MAX_COPY_BYTES:
            break
        (dest / rel).parent.mkdir(parents=True, exist_ok=True)
        shutil.copyfile(p, dest / rel)
