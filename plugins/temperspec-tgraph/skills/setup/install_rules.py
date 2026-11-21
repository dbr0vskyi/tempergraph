#!/usr/bin/env python3
"""Copy the temperspec rule files into a repository (`.claude/rules/temperspec/`) or the home folder, and, in a
repository, write the fill-in templates generated from the rules' examples into `docs/templates/`.

Usage: install_rules.py [--global] [--update] [--target <folder>]
Prints one line per file: installed, current, updated, or kept (differs)."""

from __future__ import annotations

import argparse
import importlib.util
import sys
from pathlib import Path

PLUGIN = Path(__file__).resolve().parents[2]
RULES = PLUGIN / "rules"
PLACE = Path(".claude") / "rules" / "temperspec"


def _specfmt():  # type: ignore[no-untyped-def]
    """The package's format module, loaded by path: this script runs without the engine installed."""
    spec = importlib.util.spec_from_file_location("temperspec_specfmt", PLUGIN / "workflow" / "temperspec" / "specfmt.py")
    assert spec is not None and spec.loader is not None
    mod = importlib.util.module_from_spec(spec)
    sys.modules[spec.name] = mod
    spec.loader.exec_module(mod)
    return mod


def templates() -> dict[str, bytes]:
    """Template file name -> its text, generated from the rule files' examples."""
    fmt = _specfmt()
    out: dict[str, bytes] = {}
    for src in sorted(RULES.glob("*.rule.md")):
        for name, body in fmt.rule_templates(src.name.split(".")[0], src.read_text(encoding="utf-8")).items():
            out[name] = body.encode("utf-8")
    return out


def install(target: Path, update: bool, template_dir: Path | None = None) -> list[str]:
    lines = []
    target.mkdir(parents=True, exist_ok=True)
    wanted = [(target / src.name, src.read_bytes()) for src in sorted(RULES.glob("*.rule.md"))]
    if template_dir is not None:
        template_dir.mkdir(parents=True, exist_ok=True)
        wanted += [(template_dir / name, body) for name, body in templates().items()]
    for dst, want in wanted:
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
    template_dir = None if args.home else base / "docs" / "templates"
    print("\n".join(install(base / PLACE, args.update, template_dir)))
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
