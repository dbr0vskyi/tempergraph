"""`tempergraph upgrade <workflow> --check [--stamp]` and its alias `upgrade-check <workflow> [--stamp]`
(WUP §2.1, VER §2.5). Release 1 builds the check and the stamp only; `upgrade` without `--check` is
refused with `not_in_release` (ADR-0090: release 3)."""

from __future__ import annotations

import argparse
import json
from pathlib import Path
from typing import Any

from tempergraph.constants import ExitCode
from tempergraph.package.stamp import check


def add_parsers(sub: Any) -> None:
    for verb in ("upgrade", "upgrade-check"):
        p = sub.add_parser(verb, help="check a workflow against the running engine; stamp on a clean check")
        p.add_argument("workflow")
        if verb == "upgrade":
            p.add_argument("--check", action="store_true")
            p.add_argument("--fail-on", choices=("pending", "never"), default="never")
        p.add_argument("--stamp", action="store_true")
        p.add_argument("--format", choices=("text", "json"), default="json")


def cmd_upgrade(env: Any, a: argparse.Namespace) -> int:
    if a.verb == "upgrade" and not a.check:
        env.err.write("tempergraph: upgrade without --check is not_in_release (release 3); "
                      "`upgrade --check [--stamp]` checks and stamps\n")
        return int(ExitCode.USAGE)
    path = _source(env, a.workflow)
    if path is None:
        env.err.write(f"tempergraph: unknown workflow {a.workflow!r}; `tempergraph workflows list` shows them\n")
        return int(ExitCode.USAGE)
    caps = {n: env.registry.get(n).capabilities() for n in env.registry.available()}
    rep = check(path, caps, stamp=a.stamp, fail_on_pending=getattr(a, "fail_on", "never") == "pending")
    if rep.refused:
        env.err.write(f"tempergraph: {rep.refused}\n")
    env.out.write(json.dumps(rep.to_json(), indent=2, default=str) + "\n")
    return rep.exit_code


def _source(env: Any, name: str) -> Path | None:
    spec = env.catalog.specs.get(name)
    if spec is not None and spec.package_root is not None:
        return Path(spec.package_root)
    p = Path(name)
    p = p if p.is_absolute() else env.cwd / p
    return p if (p / "tempergraph.json").is_file() else None
