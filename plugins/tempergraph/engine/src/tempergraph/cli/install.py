"""`tempergraph install` through the shim (UPD §2.7: the same code as the plugin's launcher runs)."""

from __future__ import annotations

import argparse
from typing import Any

from tempergraph.install.bootstrap import install, parser


def add_parsers(sub: Any) -> None:
    sub.add_parser("install", help="first install of the engine (UPD §2.7)", parents=[parser()], add_help=False)


def cmd_install(env: Any, a: argparse.Namespace) -> int:
    argv = (["--check"] if a.check else []) + (["--json"] if a.json else []) + \
        [x for e in a.extras for x in ("--with", e)] + (["--add-to-path"] if a.add_to_path else []) + \
        (["--repair"] if a.repair else [])
    return install(argv, out=env.out)
