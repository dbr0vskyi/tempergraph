"""Entry point of the tool."""

import sys

from tool.config import load_settings

VERSION = "1.4.0"


def main(argv: list[str]) -> int:
    if "--version" in argv:
        print(VERSION)
        return 0
    settings = load_settings()
    if settings is None:
        settings = {}
    print(f"running with {len(settings)} settings")
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
