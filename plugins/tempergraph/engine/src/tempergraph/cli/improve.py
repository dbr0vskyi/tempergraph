"""`evals score|bar|label` (JCL §2.6), `labels queue|grades` (FBK §2.3, §2.4) and the `improve` verbs (PRP §2.7).

Only `evals score`, `improve propose` (without `--patch`), `improve trial` and `improve aa` start sessions;
every other verb here is model-free.
"""

from __future__ import annotations

import argparse
import os
from typing import Any


def _caller(p: argparse.ArgumentParser) -> None:
    p.add_argument("--caller", choices=("person", "agent", "pipeline", "orchestrator", "scheduler", "engine"))
    p.add_argument("--as-agent", action="store_true")
    p.add_argument("--caller-app")
    p.add_argument("--relayed", action="store_true")


def add_parsers(sub: Any, parser_class: type[argparse.ArgumentParser]) -> None:
    ev = sub.add_parser("evals", help="judge calibration: score, bar and gold labels (JCL)")
    esub = ev.add_subparsers(dest="action", parser_class=parser_class)
    sc = esub.add_parser("score", help="score the gate's judge on its reviewed cases (spends)")
    sc.add_argument("workflow")
    sc.add_argument("gate")
    sc.add_argument("--executor")
    sc.add_argument("--repeat", type=int, default=3)
    sc.add_argument("--variants", default="persuasive_account,out_of_reach",
                    help="comma-separated kinds, or none")
    sc.add_argument("--cap", type=float, default=None, metavar="USD")
    sc.add_argument("--level", help="score the judge of this risk level (JRK §2.4)")
    sc.add_argument("--json", action="store_true")
    ba = esub.add_parser("bar", help="each gate's acceptance state, figures and failing rules")
    ba.add_argument("workflow", nargs="?")
    ba.add_argument("--json", action="store_true")
    ru = esub.add_parser("run", help="run the eval suites of one kind and record the results (EVS §2.7)")
    ru.add_argument("workflow")
    ru.add_argument("--kind", required=True, choices=("check", "judge", "step", "workflow"))
    ru.add_argument("--role", choices=("regression", "capability"))
    ru.add_argument("--trials", type=int)
    ru.add_argument("--executor")
    ru.add_argument("--cap", type=float, default=None, metavar="USD")
    ru.add_argument("--json", action="store_true")
    rep = esub.add_parser("report", help="figures per suite and case, graduation, stale and waiting results")
    rep.add_argument("workflow")
    rep.add_argument("--json", action="store_true")
    gr_ = esub.add_parser("grade", help="a person's grade for a trial no grader could decide")
    gr_.add_argument("result")
    verdict = gr_.add_mutually_exclusive_group(required=True)
    verdict.add_argument("--pass", dest="passed", action="store_true")
    verdict.add_argument("--fail", dest="failed", action="store_true")
    gr_.add_argument("--reason", required=True)
    gr_.add_argument("--json", action="store_true")
    hv = esub.add_parser("harvest", help="turn recorded judge misses into local calibration case candidates")
    hv.add_argument("workflow")
    hv.add_argument("gate")
    hv.add_argument("--json", action="store_true")
    rpl = esub.add_parser("replay", help="rerun the judges on kept cases and compare with the recorded score")
    rpl.add_argument("workflow")
    rpl.add_argument("--executor")
    rpl.add_argument("--cap", type=float, default=None, metavar="USD")
    rpl.add_argument("--json", action="store_true")
    la = esub.add_parser("label", help="write or confirm one gold label as a reviewer")
    la.add_argument("case", metavar="WORKFLOW/GATE/CASE")
    la.add_argument("--criterion", required=True)
    la.add_argument("--expected", required=True, choices=("MET", "PARTIAL", "UNMET", "N/A", "UNVERIFIABLE"))
    la.add_argument("--reason", required=True)
    la.add_argument("--reviewer")
    la.add_argument("--json", action="store_true")
    _caller(la)
    lq = sub.add_parser("labels", help="the labelling queue and judge reliability grades (FBK)")
    lsub = lq.add_subparsers(dest="action", parser_class=parser_class)
    qu = lsub.add_parser("queue")
    qu.add_argument("workflow")
    qu.add_argument("--json", action="store_true")
    gr = lsub.add_parser("grades")
    gr.add_argument("workflow")
    gr.add_argument("--json", action="store_true")
    im = sub.add_parser("improve", help="clusters, proposals and paired trials (PRP §2.7)")
    isub = im.add_subparsers(dest="action", parser_class=parser_class)
    bl = isub.add_parser("backlog")
    bl.add_argument("workflow", nargs="?")
    bl.add_argument("--json", action="store_true")
    pr = isub.add_parser("propose")
    pr.add_argument("workflow")
    pr.add_argument("cluster")
    pr.add_argument("--patch", metavar="FILE", help="a person's unified diff over the package")
    pr.add_argument("--rule", help="the general rule the change states (needed with --patch)")
    pr.add_argument("--executor")
    pr.add_argument("--json", action="store_true")
    tr = isub.add_parser("trial")
    tr.add_argument("proposal")
    tr.add_argument("--target", help="first_pass_yield(unit), run_cost, outcome_met, ...")
    tr.add_argument("--cap", type=float, default=None, metavar="USD")
    tr.add_argument("--executor")
    tr.add_argument("--json", action="store_true")
    aa = isub.add_parser("aa")
    aa.add_argument("workflow")
    aa.add_argument("--cap", type=float, default=None, metavar="USD")
    aa.add_argument("--json", action="store_true")
    op = isub.add_parser("open")
    op.add_argument("proposal")
    op.add_argument("--json", action="store_true")
    sh = isub.add_parser("show")
    sh.add_argument("record", metavar="PROPOSAL|TRIAL")
    from tempergraph.cli.improve_review import add_review_parser

    add_review_parser(isub)  # SRV §2.9


def _usage(msg: str) -> Exception:
    from tempergraph.cli.main import UsageError

    return UsageError(msg)


def _suites(env: Any, a: argparse.Namespace) -> int:
    """`evals run|report|grade` (EVS §2.7). Only `run` on a live kind makes a model call."""
    from tempergraph.cli.main import _emit, _root, _spec
    from tempergraph.improve import calibration as cal
    from tempergraph.improve import suites

    root = _root(env)
    try:
        if a.action == "grade":
            by = os.environ.get("USER") or "unknown"
            doc: dict[str, Any] = suites.person_grade(root, a.result, bool(a.passed), a.reason, by)
            text = f"result {a.result} graded {'passed' if a.passed else 'failed'}\n"
        elif a.action == "report":
            doc = suites.report(_spec(env, a.workflow), root)
            lines = [f"{s['kind']} {s['subject']} ({s['role']}): {s['status']}"
                     + (f", pass@1 {s['figures']['pass_at_1']:.2f}" if s["figures"]["pass_at_1"] is not None else "")
                     + (f", pass^k {s['figures']['pass_hat_k']:.2f}" if s["figures"]["pass_hat_k"] is not None else "")
                     for s in doc["suites"]]
            lines += [f"graduate: {g['kind']} {g['subject']} {g['case']}" for g in doc["graduation"]]
            lines += [f"needs a person: {w['command']}" for w in doc["needs_person"]]
            lines += [f"never passed, check the case first: {n['kind']} {n['subject']} {n['case']}"
                      for n in doc["never_passed"]]
            text = "\n".join(lines or [f"{a.workflow}: no eval result recorded"]) + "\n"
        else:
            spec = _spec(env, a.workflow)
            ex = None
            if a.kind != "check":
                name = a.executor or spec.default_executor
                if a.kind == "judge" and not a.executor:
                    name = env.registry.judge_executor(spec.default_executor, None, None)
                ex = env.registry.get(name)
            doc = suites.run(spec, a.kind, root, registry=env.registry, repo=env.cwd, executor=ex, role=a.role,
                             trials=a.trials, cap_usd=a.cap)
            done = sum(1 for r in doc["results"] if r["status"] == "passed")
            text = (f"{a.workflow} {a.kind}: {done} of {len(doc['results'])} trials passed"
                    + (" (partial: the cap was reached)" if doc["partial"] else "") + "\n")
    except (suites.SuiteRefused, cal.CalibrationError) as exc:
        raise _usage(str(exc)) from exc
    if a.json:
        _emit(env, doc)
    else:
        env.out.write(text)
    failed = a.action == "run" and any(r["status"] in ("failed", "invalid") and r["role"] == "regression"
                                       for r in doc["results"])
    return 1 if failed else 0


def cmd_evals(env: Any, a: argparse.Namespace) -> int:
    from tempergraph.cli.main import _emit, _root_or_none, _spec
    from tempergraph.improve import calibration as cal

    if a.action in ("run", "report", "grade"):
        return _suites(env, a)
    if a.action in ("harvest", "replay"):
        from tempergraph.cli.main import _root
        from tempergraph.improve import harvest as hv
        from tempergraph.improve import suites

        spec = _spec(env, a.workflow)
        try:
            if a.action == "harvest":
                rows = hv.harvest(_root(env), spec, a.gate)
                out: dict[str, Any] = {"schema_version": 1, "workflow": spec.name, "gate": a.gate, "candidates": rows}
                text = "".join(f"{'new' if r['new'] else 'kept'} {r['case_id']}: {r['path']}\n" for r in rows) or \
                    f"{a.gate}: no recorded judge miss to harvest\n"
                text += "Review each candidate, copy it into the package's evals/calibration and label it with " \
                        "`tempergraph evals label`.\n" if rows else ""
            else:
                name = a.executor or env.registry.judge_executor(spec.default_executor, None, None)
                out = hv.replay(spec, _root(env), env.registry.get(name), cap_usd=a.cap)
                text = "".join(f"{g['gate']}: {g['cases']} cases, agreement "
                               f"{g['agreement'] if g['agreement'] is not None else '-'}, {len(g['flips'])} changed\n"
                               for g in out["gates"]) or f"{spec.name}: no scored case to replay\n"
        except (cal.CalibrationError, suites.SuiteRefused) as exc:
            raise _usage(str(exc)) from exc
        if a.json:
            _emit(env, out)
        else:
            env.out.write(text)
        return 0
    if a.action == "bar":
        specs = [_spec(env, a.workflow)] if a.workflow else list(env.catalog.specs.values())
        root = _root_or_none(env)
        doc: dict[str, Any] = {"schema_version": 1, "workflows": []}
        for spec in specs:
            rows = []
            for st in cal.states(spec, root, every_level=True):
                rows.append({**st.to_json(), "needed": cal.needed(st)})
            doc["workflows"].append({"workflow": spec.name, "gates": rows})
        if a.json:
            _emit(env, doc)
        else:
            for w in doc["workflows"]:
                for g in w["gates"]:
                    env.out.write(f"{w['workflow']} {g['gate']}" + (f" level {g['level']}" if g.get("level") else "")
                                  + f": {g['state']}"
                                  + (f" ({'; '.join(g['failing'])})" if g["failing"] else "")
                                  + (f"; needs {', '.join(g['needed'])}" if g["needed"] else "") + "\n")
        return 0
    if a.action == "label":
        parts = a.case.split("/")
        if len(parts) != 3:
            raise _usage("evals label: the case is WORKFLOW/GATE/CASE")
        spec = _spec(env, parts[0])
        from tempergraph.provenance import decide
        from tempergraph.store.layout import home_path

        decided = decide(env.caller(a), relayed=bool(a.relayed), words=("evals", "label"), home=home_path())
        reviewer = a.reviewer or os.environ.get("USER") or "unknown"
        try:
            case = cal.write_label(spec, parts[1], parts[2], a.criterion, a.expected, a.reason, reviewer,
                                   person=decided.get("decided_by") == "person")
        except cal.CalibrationError as exc:
            raise _usage(str(exc)) from exc
        doc = {"case": case.case_id, "gate": case.gate, "state": case.state, "split": case.split,
               "criterion": a.criterion, "expected": a.expected, "by_person": decided.get("decided_by") == "person"}
        if a.json:
            _emit(env, doc)
        else:
            env.out.write(f"label {a.expected} on {a.case} {a.criterion} written; case is {case.state}\n")
        return 0
    if a.action == "score":
        spec = _spec(env, a.workflow)
        kinds = [] if a.variants in ("none", "") else [k.strip() for k in a.variants.split(",") if k.strip()]
        try:
            g, _, step_ex = cal.gate_spec(spec, a.gate)
            name = a.executor or (g.judge.executor if g.judge else None) or env.registry.judge_executor(
                step_ex, None, None)
            ex = env.registry.get(name)
            rec = cal.score(spec, a.gate, ex, repeats=a.repeat, variants=kinds, cap_usd=a.cap,
                            run_by="person", level=a.level)
            st = cal.state(spec, a.gate, level=a.level)
        except cal.CalibrationError as exc:
            raise _usage(str(exc)) from exc
        doc = {"score_id": rec["score_id"], "gate": a.gate, **({"level": a.level} if a.level else {}), "partial": rec["partial"], "usage": rec["usage"],
               "figures": rec["figures"], "state": st.state, "failing": st.failing}
        if a.json:
            _emit(env, doc)
        else:
            env.out.write(f"scored {a.workflow} {a.gate}: {st.state}, {rec['usage']['sessions']} sessions, "
                          f"${rec['usage']['cost_usd']:.2f}" + (" (partial: cap reached)" if rec["partial"] else "")
                          + "\n")
        return 0
    raise _usage("evals needs score, bar or label")


def _live(spec: Any) -> Any:
    from tempergraph.improve import calibration as cal

    return lambda gate, binding: cal.passing(spec, gate)


def cmd_labels(env: Any, a: argparse.Namespace) -> int:
    from tempergraph.cli.main import _emit, _root, _spec
    from tempergraph.improve import calibration as cal
    from tempergraph.improve import reliability as rel

    spec = _spec(env, a.workflow)
    root = _root(env)
    grades = rel.report(root, spec.name, cal.judged_gates(spec), _live(spec))
    if a.action == "grades":
        if a.json:
            _emit(env, {"schema_version": 1, "workflow": spec.name, "gates": grades})
        else:
            for g in grades:
                env.out.write(f"{g['gate']}: {g['grade']}" + (f" ({'; '.join(g['why'])})" if g["why"] else "") + "\n")
        return 0
    if a.action == "queue":
        rows = rel.queue(root, spec.name, {g["gate"]: g["grade"] for g in grades})
        if a.json:
            _emit(env, {"schema_version": 1, "workflow": spec.name, "queue": rows})
        else:
            for r in rows:
                env.out.write(f"{r['why']}: {r['command']}\n")
        return 0
    raise _usage("labels needs queue or grades")


def _host() -> Any:
    from tempergraph.improve.codehost import GhCodeHost

    return GhCodeHost()


def _arm_runner(env: Any) -> Any:
    from tempergraph.improve.trials import ChildRuns

    return ChildRuns(repo=env.cwd, registry=env.registry, settings=env.run_settings)


def cmd_improve(env: Any, a: argparse.Namespace) -> int:
    if a.action == "review":
        from tempergraph.cli.improve_review import cmd_review

        return cmd_review(env, a)
    from tempergraph.cli.main import _emit, _root, _spec
    from tempergraph.improve import proposals as prp
    from tempergraph.improve import trials as trl

    root = _root(env)
    try:
        if a.action == "backlog":
            specs = [_spec(env, a.workflow)] if a.workflow else list(env.catalog.specs.values())
            machine = os.environ.get("TEMPERGRAPH_AUTONOMY")
            doc: dict[str, Any] = {"schema_version": 1,
                                   "autonomy": {s.name: prp.autonomy(s, machine) for s in specs},
                                   "clusters": [c for s in specs for c in prp.clusters(root, s.name)]}
            if a.json:
                _emit(env, doc)
            else:
                for c in doc["clusters"]:
                    env.out.write(f"{c['cluster_id']} {c['workflow']} {c['side']} {c['unit'] or '-'} {c['cause']}: "
                                  f"score {c['score']:.2f}, {c['runs']} runs" + (" (twin folded)" if c["twin_of"] else "")
                                  + "\n")
            return 0
        if a.action == "propose":
            spec = _spec(env, a.workflow)
            cl = prp.cluster(root, spec.name, a.cluster)
            if a.patch:
                if not a.rule:
                    raise _usage("improve propose --patch needs --rule <the general rule the change states>")
                from pathlib import Path

                text = Path(a.patch).read_text(encoding="utf-8")
                rec = prp.record(root, spec, cl, text, author="person", rule=a.rule)
            else:
                name = a.executor or spec.default_executor
                rec = prp.propose(root, spec, cl, env.registry.get(name))
            _out(env, a, rec, f"proposal {rec['proposal_id']}: {rec['state']}"
                 + (f" ({rec['refusal']})" if rec.get("refusal") else "") + f", classes {rec.get('classes')}")
            return 0 if rec["state"] != "refused" else 2
        if a.action == "trial":
            rec = prp.load_proposal(root, a.proposal)
            spec = _spec(env, str(rec["workflow"]))
            judge = env.registry.get(a.executor or spec.default_executor) if rec.get("side") == "grader" else None
            out = trl.trial(root, spec, a.proposal, _arm_runner(env), target=a.target, cap_usd=a.cap,
                            judge_executor=judge)
            _out(env, a, out, f"trial {out['trial_id']}: {out['decision']}"
                 + (f" ({out['reason']})" if out.get("reason") else "")
                 + f", {out['counts']['wins']} wins {out['counts']['losses']} losses {out['counts']['ties']} ties")
            return 0
        if a.action == "aa":
            spec = _spec(env, a.workflow)
            out = trl.aa(root, spec, _arm_runner(env), cap_usd=a.cap)
            _out(env, a, out, f"A/A {out['trial_id']}: noise floor {out['noise_floor']}")
            return 0
        if a.action == "open":
            rec = prp.load_proposal(root, a.proposal)
            spec = _spec(env, str(rec["workflow"]))
            out = prp.open_pr(root, spec, a.proposal, _host())
            _out(env, a, out, f"proposal {a.proposal}: " + (f"draft pull request {out['pull_request']}"
                                                            if out.get("pull_request") else
                                                            f"not opened ({out.get('open_error')})"))
            return 0 if out.get("pull_request") else 1
        if a.action == "show":
            try:
                doc = prp.load_proposal(root, a.record)
            except prp.ProposalError:
                doc = trl.load_trial(root, a.record)
            _emit(env, doc)
            return 0
    except (prp.ProposalError, trl.TrialRefused) as exc:
        raise _usage(str(exc)) from exc
    raise _usage("improve needs backlog, propose, trial, aa, open or show")


def _out(env: Any, a: argparse.Namespace, doc: Any, line: str) -> None:
    from tempergraph.cli.main import _emit

    if getattr(a, "json", False):
        _emit(env, doc)
    else:
        env.out.write(line + "\n")


COMMANDS = {"evals": cmd_evals, "labels": cmd_labels, "improve": cmd_improve}
