"""`blueprint check|draw|compare` and `literals` (SCF §2.1 to §2.3, §2.6). Model-free and read-only;
output is JSON (draw prints its format). A failed check exits 2 (CON §2.9)."""

from __future__ import annotations

import argparse
import json
from pathlib import Path
from typing import Any

from tempergraph.author import blueprint as bpm
from tempergraph.author.compare import compare
from tempergraph.author.draw import draw
from tempergraph.author.literals import scan
from tempergraph.constants import ExitCode


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
