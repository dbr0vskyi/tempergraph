"""`tempergraph audit <workflow>` and `audit prompts <workflow>` (AUD-B11, AUD-B6, AUD-B9, PRA-B11).

Advisory: exit 0 whatever is found, 6 with `--fail-on` when a finding not ignored is at or above the level,
2 for an unknown workflow or option. Output goes to stdout only; nothing is written (AUD-B6).
`--layer history` reads the workflow's local run records in `--window` days and `--version` (read-only); a bare
`audit` reads them when the history layer is asked for by default and runs it when runs exist (AUD-B1, AUD-B11).
`audit tools <workflow> [--executor <name>] [--step <unit>]` prints the tool surface matrix of TSA instead of
findings, from the surface the audit builds once; `--fail-on` counts the tool findings (TSA-B8, TSA-B5).
`audit prompts` reads `changed` from the same history facts (PRA-B11).
"""

from __future__ import annotations

import argparse
import datetime as dt
import json
from pathlib import Path
from typing import Any

from tempergraph.audit import AuditContext, audit, audit_layers
from tempergraph.audit.catalog import BY_ID
from tempergraph.audit.history import HistoryFacts, read_history
from tempergraph.audit.prompts import prompt_rows
from tempergraph.audit.report import AuditFinding, AuditReport, render
from tempergraph.audit.tools import matrix, render_matrix
from tempergraph.constants import ENGINE_VERSION, ExitCode
from tempergraph.executors.capabilities import DECLARED


def add_parsers(sub: Any) -> None:
    p = sub.add_parser("audit", help="advisory, read-only audit of a workflow (no model call)")
    p.add_argument("first", metavar="workflow",
                   help="a workflow, or `prompts` / `tools` / `decisions` then a workflow")
    p.add_argument("second", nargs="?", default=None, help=argparse.SUPPRESS)
    p.add_argument("--layer", action="append", choices=("definition", "host", "history"), default=None)
    p.add_argument("--target", default=None)
    p.add_argument("--executor", default=None)
    p.add_argument("--step", action="append", default=[])
    p.add_argument("--window", type=int, default=30)
    p.add_argument("--version", default="current")
    p.add_argument("--all", action="store_true", dest="show_all")
    p.add_argument("--format", choices=("text", "json", "sarif"), default="text")
    p.add_argument("--fail-on", choices=("error", "warning", "never"), default="never")


def _probe(env: Any) -> Any:
    def probe(name: str) -> str | None:
        try:
            got = env.registry.get(name).probe()
        except Exception:  # noqa: BLE001 - an unknown or failing executor skips the rule (AUD-B15, AUD-B9, AUD-B2)
            return None
        return got.version if got.ok and got.version else None

    return probe


def _issue_state(spec: Any) -> Any:
    """DRV-B2: an issue of the workflow's issue repository, read through `gh` once per number."""
    repo = getattr(spec, "issue_repository", None)
    if not repo:
        return None
    seen: dict[int, str | None] = {}

    def read(n: int) -> str | None:
        if n not in seen:
            from tempergraph.improve.codehost import GhCodeHost

            seen[n] = GhCodeHost(timeout_s=20).issue_state(str(repo), n)
        return seen[n]

    return read


def cmd_audit(env: Any, a: argparse.Namespace) -> int:
    view, name = ("findings", a.first) if a.second is None else (a.first, a.second)
    if view not in ("findings", "prompts", "tools", "decisions"):
        env.err.write(f"tempergraph: audit takes a workflow, or prompts, tools or decisions then a workflow; got "
                      f"{view!r}\n")
        return int(ExitCode.USAGE)
    if view == "tools" and a.executor and a.executor not in DECLARED and a.executor not in env.registry.available():
        env.err.write(f"tempergraph: unknown executor {a.executor!r} for audit tools\n")
        return int(ExitCode.USAGE)
    target = Path(a.target) if a.target else env.cwd
    target = target if target.is_absolute() else env.cwd / target
    if not target.is_dir():
        env.err.write(f"tempergraph: --target {a.target!r} is not a directory\n")
        return int(ExitCode.USAGE)
    got = _workflow(env, name)
    if got is None:
        env.err.write(f"tempergraph: unknown workflow {name!r}; `tempergraph workflows list` shows them\n")
        return int(ExitCode.USAGE)
    if isinstance(got, AuditReport):  # not loaded: one finding, the manifest row only (AUD-B15, AUD-B9, AUD-B2)
        env.out.write(render(got, a.format))
        return got.exit_code(a.fail_on)
    spec, manifest, stamp = got
    caps = {n: env.registry.get(n).capabilities() for n in env.registry.available()}
    layers = audit_layers(a.layer)
    facts = _history(env, spec, a) if "history" in layers or view != "findings" else None
    tools = view == "tools"
    ctx = AuditContext(target=target, caps=caps, probe=_probe(env), window_days=a.window, version=a.version,
                       executor=None if tools else a.executor, steps=tuple(a.step), show_all=a.show_all, history=facts,
                       tool_executor=a.executor if tools else None, mcp_servers=_operator_mcp,
                       issue_state=_issue_state(spec))
    rep = audit(spec, layers, ctx, manifest=manifest, stamp=stamp)
    if tools:
        return _tools(env, a, spec, rep)
    if view == "decisions":  # DRV-B4
        from tempergraph.audit import readers
        from tempergraph.audit.revisit import rows

        env.out.write(json.dumps({"schema_version": 1, "workflow": spec.name, "stamped": stamp is not None,
                                  "triggers": rows(spec, stamp, readers(ctx))}, indent=2) + "\n")
        return 0
    if view == "prompts":
        env.out.write(json.dumps({"schema_version": 1, "workflow": spec.name, "files": prompt_rows(spec, rep, facts)},
                                 indent=2) + "\n")
        return 0
    env.out.write(render(rep, a.format))
    return rep.exit_code(a.fail_on)


def _tools(env: Any, a: argparse.Namespace, spec: Any, rep: AuditReport) -> int:
    """TSA-B8, TSA-B5: the matrix from the surface the audit built once, the history rules listed as skipped, and the
    exit code of `--fail-on` over the tool findings only."""
    c4 = [f for f in rep.findings if f.rule in BY_ID and BY_ID[f.rule].family == "C4"]
    rows = matrix(rep.surface, c4) if rep.surface is not None else []
    if a.step:
        rows = [r for r in rows if r["unit"] in set(a.step)]
    skipped = [s for s in rep.rules_skipped if s["rule"] in BY_ID and BY_ID[s["rule"]].layer == "history"]
    extra = {"workflow": spec.name, "executor": a.executor, "history": bool(rep.surface and rep.surface.history),
             "rules_skipped": skipped}
    env.out.write(render_matrix(rows, "json" if a.format == "json" else "text", extra=extra))
    rep.findings = c4
    return rep.exit_code(a.fail_on)


def _operator_mcp() -> set[str] | None:
    """The MCP servers of the operator's own configuration (`~/.claude.json`); a project file is never read (TSA-B12)."""
    try:
        doc = json.loads((Path.home() / ".claude.json").read_text(encoding="utf-8"))
    except FileNotFoundError:
        return set()
    except (OSError, ValueError):
        return None
    servers = doc.get("mcpServers") if isinstance(doc, dict) else None
    return set(servers) if isinstance(servers, dict) else set()


def _history(env: Any, spec: Any, a: argparse.Namespace) -> HistoryFacts | None:
    """The facts of the workflow's runs in the window and version; none outside a state root (AUD-B11, AUD-B15)."""
    from tempergraph.store.layout import NotInRepository, state_root_path

    try:
        root = state_root_path(env.cwd)
    except NotInRepository:
        return None
    return read_history(root, spec.name, a.version, a.window, dt.date.today(), current=spec.version)


def _workflow(env: Any, name: str) -> tuple[Any, Any, dict[str, Any] | None] | AuditReport | None:
    from tempergraph.package.loader import PackageNotLoaded, load_package
    from tempergraph.package.manifest import read_manifest
    from tempergraph.package.stamp import read_stamp

    spec = env.catalog.specs.get(name)
    if spec is not None:
        root = spec.package_root
        manifest = read_manifest(root) if root is not None else None
        return spec, (None if isinstance(manifest, list) else manifest), (read_stamp(root) if root else None)
    p = Path(name)
    p = p if p.is_absolute() else env.cwd / p
    broken = env.catalog.broken.get(name)
    if not (p / "tempergraph.json").is_file():
        return _not_loaded(name, broken) if broken else None
    try:
        lp = load_package(p)
    except PackageNotLoaded as exc:
        return _not_loaded(name, str(exc))
    return lp.spec, lp.manifests.engine, read_stamp(lp.root)


def _not_loaded(name: str, reason: str) -> AuditReport:
    rep = AuditReport(workflow=name, version="", engine_version=ENGINE_VERSION)
    rep.layers_skipped = [{"layer": layer, "reason": "the workflow is not loaded"}
                          for layer in ("definition", "host", "history")]
    rep.findings = [AuditFinding(rule="validate:not_loaded", layer="definition", severity="error",
                                 confidence="high", owner="validate", statement=reason,
                                 remedy="Fix what stops the package loading (PKG-B11, PKG-B13, PKG-B14, PKG-B17, PKG-B18, PKG-B19, PKG-B20, PKG-B23)",
                                 location={"file": "tempergraph.json"})]
    return rep
