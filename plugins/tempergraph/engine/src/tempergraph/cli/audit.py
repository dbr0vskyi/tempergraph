"""`tempergraph audit <workflow>` and `audit prompts <workflow>` (AUD-B11, AUD-B6, AUD-B9, PRA-B11).

Advisory: exit 0 whatever is found, 6 with `--fail-on` when a finding not ignored is at or above the level,
2 for an unknown workflow or option. Output goes to stdout only; nothing is written (AUD-B6).
`audit tools` (TSA) and `--layer history` are release 3 and refused with `not_in_release`.
"""

from __future__ import annotations

import argparse
from pathlib import Path
from typing import Any

from tempergraph.audit import AuditContext, audit, audit_layers
from tempergraph.audit.prompts import prompt_rows
from tempergraph.audit.report import AuditFinding, AuditReport, render
from tempergraph.constants import ENGINE_VERSION, ExitCode


def add_parsers(sub: Any) -> None:
    p = sub.add_parser("audit", help="advisory, read-only audit of a workflow (no model call)")
    p.add_argument("first", metavar="workflow", help="a workflow, or `prompts` / `tools` then a workflow")
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


def cmd_audit(env: Any, a: argparse.Namespace) -> int:
    view, name = ("findings", a.first) if a.second is None else (a.first, a.second)
    if view == "tools":
        env.err.write("tempergraph: audit tools (the tool surface audit, TSA) is not_in_release (release 3)\n")
        return int(ExitCode.USAGE)
    if view not in ("findings", "prompts"):
        env.err.write(f"tempergraph: audit takes a workflow, or prompts <workflow>; got {view!r}\n")
        return int(ExitCode.USAGE)
    if a.layer and "history" in a.layer:
        env.err.write("tempergraph: audit --layer history is not_in_release (release 3); this release audits the "
                      "definition and host layers\n")
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
    ctx = AuditContext(target=target, caps=caps, probe=_probe(env), window_days=a.window, version=a.version,
                       executor=a.executor, steps=tuple(a.step), show_all=a.show_all)
    rep = audit(spec, audit_layers(a.layer), ctx, manifest=manifest, stamp=stamp)
    if view == "prompts":
        import json

        env.out.write(json.dumps({"schema_version": 1, "workflow": spec.name, "files": prompt_rows(spec, rep)},
                                 indent=2) + "\n")
        return 0
    env.out.write(render(rep, a.format))
    return rep.exit_code(a.fail_on)


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
