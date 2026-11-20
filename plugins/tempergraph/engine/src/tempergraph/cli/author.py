"""`blueprint check|draw|compare` and `literals` (SCF §2.1 to §2.3, §2.6). Model-free and read-only;
output is JSON (draw prints its format). A failed check exits 2 (CON §2.9)."""

from __future__ import annotations

import argparse
import contextlib
import json
from pathlib import Path
from typing import Any

from tempergraph.author import blueprint as bpm
from tempergraph.author.compare import compare
from tempergraph.author.draw import draw
from tempergraph.author.literals import scan
from tempergraph.constants import ExitCode
from tempergraph.docs import write_json
from tempergraph.store.layout import now_iso


def add_parsers(sub: Any) -> None:
    bp = sub.add_parser("blueprint", help="check, draw or compare a workflow blueprint (no model)")
    bsub = bp.add_subparsers(dest="action")
    for action in ("check", "draw"):
        p = bsub.add_parser(action)
        p.add_argument("file")
        p.add_argument("--outcome", default=None)
        if action == "draw":
            p.add_argument("--format", choices=("md", "svg", "mermaid"), default="md")
    p = bsub.add_parser("compare")
    p.add_argument("workflow")
    sc = sub.add_parser("scaffold", help="write a workflow package from an approved authoring session (no model)")
    sc.add_argument("session", help="a session id under <state root>/authoring/, or its folder")
    sc.add_argument("--out", required=True)
    sc.add_argument("--update", action="store_true")
    sc.add_argument("--update-docs", action="store_true")
    au = sub.add_parser("author", help="check an authored workflow (`author verify`); the other author verbs "
                        "come with the authoring skill (plan T9)")
    asub = au.add_subparsers(dest="action")
    st = asub.add_parser("start")
    st.add_argument("name")
    st.add_argument("paths", nargs="*")
    st.add_argument("--from", dest="from_", action="append", choices=("solution", "sources", "chat"), default=None)
    st.add_argument("--revise", action="store_true", help="revise an existing workflow's outcome (AUT §2.7)")
    it = asub.add_parser("intake")
    it.add_argument("id")
    it.add_argument("paths", nargs="+")
    it.add_argument("--kind", default=None)
    it.add_argument("--artifact", default=None)
    it.add_argument("--unit", default=None)
    it.add_argument("--outside", action="store_true", help="a path outside the workspace the person named")
    for verb in ("check", "show", "drop"):
        x = asub.add_parser(verb)
        x.add_argument("id")
        if verb == "show":
            x.add_argument("--json", action="store_true")
    asub.add_parser("list")
    ap = asub.add_parser("approve")
    ap.add_argument("id")
    ap.add_argument("phase", type=int)
    v = asub.add_parser("verify")
    v.add_argument("workflow")
    v.add_argument("--judge-seeds", action="store_true")
    v.add_argument("--trial", action="store_true")
    v.add_argument("--case", default=None)
    v.add_argument("--cap", type=float, default=5.0)
    v.add_argument("--json", action="store_true")
    from tempergraph.cli.main import _caller_options

    _caller_options(v)
    tr = asub.add_parser("trial", help="the first trial's report: each criterion's status and the person's grade")
    tr.add_argument("workflow")
    tr.add_argument("--json", action="store_true")
    gr = asub.add_parser("grade", help="the person's grade on one criterion of the trial's output")
    gr.add_argument("workflow")
    gr.add_argument("--unit", default="outcome", help="the criterion's unit; `outcome` for a final criterion")
    gr.add_argument("--criterion", required=True)
    gr.add_argument("--status", required=True, choices=("MET", "PARTIAL", "UNMET", "N/A", "UNVERIFIABLE"))
    gr.add_argument("--reason", required=True)
    gr.add_argument("--reviewer", default=None)
    gr.add_argument("--json", action="store_true")
    _caller_options(gr)
    lit = sub.add_parser("literals", help="scan a workflow for case literals (no model)")
    lit.add_argument("workflow")
    lit.add_argument("--cases", action="store_true", help="also match runs of six words from case requests")


def _emit(env: Any, doc: Any) -> None:
    env.out.write(json.dumps(doc, indent=2, default=str) + "\n")


def _path(env: Any, name: str) -> Path:
    p = Path(name)
    return p if p.is_absolute() else env.cwd / p


def _outcome(env: Any, given: str | None, beside: Path) -> tuple[Any, Any, list[dict[str, Any]]]:
    from tempergraph.run.outcome import parse_outcome

    path = _path(env, given) if given else beside.parent / "outcome.json"
    if not path.is_file():
        return None, None, ([{"code": "outcome-missing", "unit": None, "message": f"{path.name} not found"}]
                            if given else [])
    doc = json.loads(path.read_text(encoding="utf-8"))
    got = parse_outcome(doc)
    if isinstance(got, list):
        return None, doc, [{"code": f.code, "unit": f.unit, "message": f.message} for f in got if f.severity == "error"]
    return got, doc, []


def cmd_blueprint(env: Any, a: argparse.Namespace) -> int:
    if a.action == "compare":
        return _compare(env, a.workflow)
    if a.action not in ("check", "draw"):
        env.err.write("tempergraph: blueprint needs check, draw or compare\n")
        return int(ExitCode.USAGE)
    file = _path(env, a.file)
    got = bpm.read(file)
    if isinstance(got, list):
        _emit(env, {"schema_version": 1, "ok": False, "findings": [_row(f) for f in got]})
        return int(ExitCode.USAGE)
    outcome, doc, problems = _outcome(env, a.outcome, file)
    caps = {n: env.registry.get(n).capabilities() for n in env.registry.available()}
    found = [_row(f) for f in bpm.check(got, caps, outcome, doc)] + problems
    if a.action == "check" or found:
        _emit(env, {"schema_version": 1, "workflow": got.name, "ok": not found, "findings": found})
        return 0 if not found else int(ExitCode.USAGE)
    env.out.write(draw(got, outcome, a.format))
    return 0


def _row(f: Any) -> dict[str, Any]:
    return {"code": f.code, "unit": f.unit, "message": f.message}


def _compare(env: Any, name: str) -> int:
    spec = _spec(env, name)
    if spec is None or spec.package_root is None:
        env.err.write(f"tempergraph: unknown workflow {name!r}\n")
        return int(ExitCode.USAGE)
    root = Path(spec.package_root)
    got = bpm.read(root / bpm.BLUEPRINT_FILE)
    if isinstance(got, list):
        _emit(env, {"schema_version": 1, "ok": False, "findings": [_row(f) for f in got]})
        return int(ExitCode.USAGE)
    doc = None
    if (root / "outcome.json").is_file():
        doc = json.loads((root / "outcome.json").read_text(encoding="utf-8"))
    diffs = compare(got, spec, doc)
    _emit(env, {"schema_version": 1, "workflow": spec.name, "ok": not diffs, "differences": [d.to_json() for d in diffs]})
    return 0 if not diffs else int(ExitCode.USAGE)


def _spec(env: Any, name: str) -> Any:
    from tempergraph.package.loader import load_package

    spec = env.catalog.specs.get(name)
    if spec is not None:
        return spec
    p = _path(env, name)
    return load_package(p).spec if (p / "tempergraph.json").is_file() else None


def cmd_literals(env: Any, a: argparse.Namespace) -> int:
    spec = _spec(env, a.workflow)
    if spec is None:
        env.err.write(f"tempergraph: unknown workflow {a.workflow!r}\n")
        return int(ExitCode.USAGE)
    hits = scan(spec, cases=a.cases)
    _emit(env, {"schema_version": 1, "workflow": spec.name, "ok": not hits, "hits": [h.to_json() for h in hits]})
    return 0 if not hits else int(ExitCode.ADVISORY)


def cmd_scaffold(env: Any, a: argparse.Namespace) -> int:
    from tempergraph.author.scaffold import ScaffoldRefused, read_session, scaffold

    folder = _path(env, a.session)
    if not folder.is_dir():
        from tempergraph.store.layout import NotInRepository, state_root_path

        with contextlib.suppress(NotInRepository):
            folder = state_root_path(env.cwd) / "authoring" / a.session
    if not folder.is_dir():
        env.err.write(f"tempergraph: no authoring session {a.session!r}\n")
        return int(ExitCode.USAGE)
    try:
        rep = scaffold(read_session(folder), _path(env, a.out), update=a.update or a.update_docs,
                       docs_only=a.update_docs)
    except ScaffoldRefused as exc:
        env.err.write(f"tempergraph: {exc}\n")
        _emit(env, {"schema_version": 1, "ok": False, "refused": exc.code, "message": str(exc)})
        return int(ExitCode.USAGE)
    record = folder / "authoring.json"  # the session is finished once scaffolded (AUT §4: one open per name)
    try:
        doc = json.loads(record.read_text(encoding="utf-8"))
        doc["scaffolded"] = {"out": str(_path(env, a.out)), "at": now_iso()}
        write_json(record, doc, mode=0o644)
    except (OSError, ValueError):
        pass
    _emit(env, {"ok": True, **rep.to_json()})
    return 0


def _package(env: Any, workflow: str) -> Path | None:
    spec = _spec(env, workflow)
    if spec is not None and spec.package_root is not None:
        return Path(spec.package_root)
    p = _path(env, workflow)
    return p if (p / "tempergraph.json").is_file() else None


def cmd_author(env: Any, a: argparse.Namespace) -> int:
    """`author verify|trial|grade <workflow>` (SCF §2.5) and the session verbs (AUT §2.1)."""
    from tempergraph.author.verify import verify
    from tempergraph.cli.audit import _probe

    if a.action in ("start", "intake", "check", "show", "list", "drop", "approve"):
        return _session_verb(env, a)
    if a.action in ("trial", "grade"):
        return _trial_verb(env, a)
    if a.action != "verify":
        env.err.write("tempergraph: author needs start, intake, check, show, list, drop, approve, verify, trial "
                      "or grade\n")
        return int(ExitCode.USAGE)
    root = _package(env, a.workflow)
    if root is None:
        env.err.write(f"tempergraph: unknown workflow {a.workflow!r}\n")
        return int(ExitCode.USAGE)
    caps = {n: env.registry.get(n).capabilities() for n in env.registry.available()}
    spending = a.judge_seeds or a.trial
    caller = env.caller(a) if spending else None  # a deciding call: the person's yes on the stated cost

    def executor_for(gate: str) -> Any:
        from tempergraph.improve import calibration as cal
        from tempergraph.package.loader import load_package

        spec = load_package(root).spec
        g, _, step_ex = cal.gate_spec(spec, gate)
        return env.registry.get((g.judge.executor if g.judge else None)
                                or env.registry.judge_executor(step_ex, None, None))

    rep = verify(root, caps, target=env.cwd, probe=_probe(env), judge_seeds=a.judge_seeds, trial=a.trial,
                 case=a.case, cap=a.cap, executor_for=executor_for, registry=env.registry, caller=caller)
    if a.json:
        _emit(env, rep.to_json())
    else:
        for r in rep.rungs:
            env.out.write(f"{r.n:>2} {r.name:<16} {r.state:<8} {r.note}\n")
            for f in r.findings:
                env.out.write(f"     {f['code']}: {f['message']}" + (f" ({f['remedy']})" if f["remedy"] else "") + "\n")
        for w in rep.warnings:
            env.out.write(f"   warning {w['code']}: {w['message']}\n")
        env.out.write(("verify passed" if rep.ok else "verify waiting on the trial" if rep.exit_code == 3
                       else "verify failed") + "\n")
    return rep.exit_code


def _trial_verb(env: Any, a: argparse.Namespace) -> int:
    """`author trial` (read-only) and `author grade` (one grade: a label and a calibration case candidate)."""
    import os

    from tempergraph.author import trial as tr
    from tempergraph.package.loader import load_package

    root = _package(env, a.workflow)
    if root is None:
        env.err.write(f"tempergraph: unknown workflow {a.workflow!r}\n")
        return int(ExitCode.USAGE)
    record = root / "authoring.json"
    try:
        authoring = json.loads(record.read_text(encoding="utf-8"))
    except (OSError, ValueError):
        authoring = {}
    trial = authoring.get("trial") if isinstance(authoring, dict) else None
    if not isinstance(trial, dict) or not trial.get("task"):
        env.err.write(f"tempergraph: {a.workflow} has no trial; run `tempergraph author verify {a.workflow} "
                      "--trial --case <id>`\n")
        return int(ExitCode.USAGE)
    spec = load_package(root).spec
    if a.action == "grade":
        caller = env.caller(a)
        try:
            got = tr.grade(spec, root, env.cwd, trial, a.unit, a.criterion, a.status, a.reason, caller,
                           relayed=bool(a.relayed), reviewer=a.reviewer or os.environ.get("USER") or "unknown")
        except tr.TrialRefused as exc:
            env.err.write(f"tempergraph: {exc}\n")
            return int(ExitCode.USAGE)
        authoring["trial"] = trial
        write_json(record, authoring, mode=0o644)
        if a.json:
            _emit(env, got)
        else:
            env.out.write(f"grade {a.status} on {a.unit}/{a.criterion} recorded (verifier said {got['verifier']})"
                          + (f"; label {got['label']['value']}" if got["label"] else "")
                          + (f"; calibration candidate {got['case']}" if got["case"] else "") + "\n")
        return 0
    doc = tr.report(spec, trial, env.cwd)
    if a.json:
        _emit(env, doc)
    else:
        env.out.write(f"trial {doc['thread']} ({doc['state']}, outcome {doc['verdict']})\n")
        for r in doc["criteria"]:
            mark = "DISAGREES " if r["disagrees"] else ""
            env.out.write(f"  {mark}{r['unit']}/{r['criterion']}: {r['class']} said {r['status']}, person "
                          f"{r['grade'] or 'not graded yet'}\n")
            if r["disagrees"]:
                env.out.write(f"    {r['text']} (method: {r['check_method'] or r['class']})\n")
    return 0


def _session_verb(env: Any, a: argparse.Namespace) -> int:
    """AUT §2.1 and §2.8: the session verbs; each writes only its session folder (AUT-AC-4)."""
    from tempergraph.author import session as ses
    from tempergraph.store.layout import NotInRepository, state_root_path

    try:
        root = state_root_path(env.cwd)
    except NotInRepository:
        env.err.write("tempergraph: author sessions live in a repository's state root; run it inside one\n")
        return int(ExitCode.USAGE)
    caps = {n: env.registry.get(n).capabilities() for n in env.registry.available()}
    try:
        if a.action == "start":
            if a.revise:
                pkg = _spec(env, a.name)
                where = Path(pkg.package_root) if pkg is not None and pkg.package_root else _path(env, a.name)
                s = ses.revise(root, where)
            else:
                s = ses.start(root, a.name, a.from_ or [])
                if a.paths:
                    ses.intake(s, [_path(env, p) for p in a.paths], root.parent)
            _emit(env, ses.show(s, caps))
        elif a.action == "intake":
            s = ses.open_session(root, a.id)
            added = ses.intake(s, [_path(env, p) for p in a.paths], root.parent, kind=a.kind, artifact=a.artifact,
                               unit=a.unit, outside=a.outside)
            _emit(env, {"schema_version": 1, "id": s.id, "added": added})
        elif a.action == "check":
            rep = ses.check(ses.open_session(root, a.id), caps)
            _emit(env, rep)
            return 0 if rep["ok"] else int(ExitCode.USAGE)
        elif a.action == "show":
            _emit(env, ses.show(ses.open_session(root, a.id), caps))
        elif a.action == "list":
            _emit(env, {"schema_version": 1, "sessions": ses.listing(root)})
        elif a.action == "drop":
            s = ses.open_session(root, a.id)
            ses.drop(s)
            _emit(env, {"schema_version": 1, "dropped": s.id})
        else:
            s = ses.open_session(root, a.id)
            entry = ses.approve(s, a.phase, env.caller(a), caps)
            _emit(env, {"schema_version": 1, "id": s.id, "approved": entry, "next_phase": ses.next_phase(s)})
    except ses.AuthorRefused as exc:
        env.err.write(f"tempergraph: {exc}\n")
        _emit(env, {"schema_version": 1, "ok": False, "refused": exc.code, "message": str(exc)})
        return int(ExitCode.USAGE)
    return 0
