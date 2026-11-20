"""`tempergraph workflows list|register|unregister|reinstall` (UPD §2.8, CLI §2).

`list` and `register --check` are read-only and call no model (C13). Output is JSON with `schema_version`.
Exit codes: 0 done, 2 a refusal (nothing written), 1 an engine error.
"""

from __future__ import annotations

import argparse
import json
from pathlib import Path
from typing import Any

from tempergraph.constants import ExitCode
from tempergraph.model.validate import Finding
from tempergraph.package import registry as reg
from tempergraph.store.layout import NotInRepository, state_root_path


def add_parsers(sub: Any) -> None:
    wf = sub.add_parser("workflows", help="the workflow registry")
    act = wf.add_subparsers(dest="action", parser_class=type(wf))
    ls = act.add_parser("list", help="the registry, with state and pins")
    ls.add_argument("--json", action="store_true")
    rg = act.add_parser("register", help="register a local workflow package")
    rg.add_argument("path")
    rg.add_argument("--check", action="store_true", help="load and validate only; nothing is written")
    ur = act.add_parser("unregister", help="remove a registry entry, never files")
    ur.add_argument("name")
    ri = act.add_parser("reinstall", help="dependencies, then load and validate")
    ri.add_argument("name", nargs="?")
    ri.add_argument("--all", action="store_true")


def _findings(fs: list[Finding]) -> list[dict[str, Any]]:
    return [{"severity": f.severity, "code": f.code, "unit": f.unit, "message": f.message} for f in fs]


def _emit(env: Any, doc: Any) -> None:
    env.out.write(json.dumps(doc, indent=2, default=str) + "\n")


def cmd_workflows(env: Any, a: argparse.Namespace) -> int:
    caps = {n: env.registry.get(n).capabilities() for n in env.registry.available()}
    try:
        if a.action == "list":
            _emit(env, reg.listing())
        elif a.action == "register":
            got = reg.register(Path(a.path) if Path(a.path).is_absolute() else env.cwd / a.path, caps,
                               check_only=a.check)
            _emit(env, {"schema_version": 1, "registered": not a.check, "entry": got.entry,
                        "findings": _findings(got.findings)})
        elif a.action == "unregister":
            try:
                roots = [state_root_path(env.cwd)]
            except NotInRepository:
                roots = []  # outside a repository only the registry is checked
            entry = reg.unregister(a.name, roots)
            _emit(env, {"schema_version": 1, "unregistered": entry["name"], "path": entry.get("path")})
        elif a.action == "reinstall":
            if bool(a.name) == bool(a.all):
                env.err.write("tempergraph: workflows reinstall needs a name or --all\n")
                return int(ExitCode.USAGE)
            done = reg.reinstall(None if a.all else [a.name], caps)
            _emit(env, {"schema_version": 1, "workflows": [
                {"entry": c.entry, "findings": _findings(c.findings), "remedy": c.remedy} for c in done]})
            return 0 if all(c.ok for c in done) else int(ExitCode.USAGE)
        else:
            env.err.write("tempergraph: workflows needs list, register, unregister or reinstall\n")
            return int(ExitCode.USAGE)
    except reg.RegistryRefusal as exc:
        env.err.write(f"tempergraph: {exc}\n")
        if exc.findings:
            _emit(env, {"schema_version": 1, "refused": exc.code, "findings": _findings(exc.findings)})
        return int(ExitCode.USAGE)
    return 0
