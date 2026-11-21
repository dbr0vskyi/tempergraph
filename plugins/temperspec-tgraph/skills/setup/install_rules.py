#!/usr/bin/env python3
"""Copy the temperspec rule files into a repository (`.claude/rules/temperspec/`) or the home folder.

Usage: install_rules.py [--global] [--update] [--target <folder>]
Prints one line per rule file: installed, current, updated, or kept (differs)."""

from __future__ import annotations

import argparse
import sys
from pathlib import Path

RULES = Path(__file__).resolve().parents[2] / "rules"
PLACE = Path(".claude") / "rules" / "temperspec"


def install(target: Path, update: bool) -> list[str]:
    lines = []
    target.mkdir(parents=True, exist_ok=True)
    for src in sorted(RULES.glob("*.rule.md")):
        dst = target / src.name
        want = src.read_bytes()
        if not dst.exists():
            dst.write_bytes(want)
            lines.append(f"installed {dst}")
        elif dst.read_bytes() == want:
            lines.append(f"current {dst}")
        elif update:
            dst.write_bytes(want)
            lines.append(f"updated {dst}")
        else:
            lines.append(f"kept (differs) {dst}")
    return lines


def main(argv: list[str]) -> int:
    ap = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    ap.add_argument("--global", dest="home", action="store_true", help="install for the whole machine")
    ap.add_argument("--update", action="store_true", help="replace rule files that differ")
    ap.add_argument("--target", type=Path, default=None, help="the repository root (default: the current folder)")
    args = ap.parse_args(argv)
    base = Path.home() if args.home else (args.target or Path.cwd())
    if not RULES.is_dir():
        print(f"no rule files at {RULES}", file=sys.stderr)
        return 1
    print("\n".join(install(base / PLACE, args.update)))
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
