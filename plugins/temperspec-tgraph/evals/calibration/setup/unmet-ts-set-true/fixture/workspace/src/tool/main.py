"""Entry point of the tool."""

import sys
import tomllib
from pathlib import Path

VERSION = "1.4.0"


def main(argv: list[str]) -> int:
    if "--version" in argv:
        print(VERSION)
        return 0
    settings = tomllib.loads(Path("tool.toml").read_text())
    print(f"running with {len(settings)} settings")
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
