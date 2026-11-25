"""Reads tool.toml."""
import sys


def run(path):
    if not path.exists():
        print(f"missing {path.name}", file=sys.stderr)
        return 2
    return 0
