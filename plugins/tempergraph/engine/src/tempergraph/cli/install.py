"""`tempergraph install` through the shim (UPD-B18, UPD-B19: the same code as the plugin's launcher runs)."""

from __future__ import annotations

import argparse
from typing import Any

from tempergraph.install.bootstrap import install, parser


def add_parsers(sub: Any) -> None:
    sub.add_parser("install", help="first install of the engine (UPD-B18, UPD-B19)", parents=[parser()], add_help=False)
    add_update(sub)


def add_update(sub: Any) -> None:
    from tempergraph.install.update import parser as update_parser

    sub.add_parser("update", help="move to the plugin copy's engine release; rollback; prune (UPD-B14, UPD-B6)",
                   parents=[update_parser()], add_help=False)


def cmd_update(env: Any, a: argparse.Namespace) -> int:
    from tempergraph.install.update import update

    argv = [f"--{k.replace('_', '-')}" for k in ("check", "dry_run", "json", "rollback", "restore_backups",
                                                 "prune_engines") if getattr(a, k)]
    return update(argv + [x for e in a.extras for x in ("--with", e)], out=env.out)


def cmd_install(env: Any, a: argparse.Namespace) -> int:
    argv = (["--check"] if a.check else []) + (["--json"] if a.json else []) + \
        [x for e in a.extras for x in ("--with", e)] + (["--add-to-path"] if a.add_to_path else []) + \
        (["--repair"] if a.repair else [])
    return install(argv, out=env.out)
