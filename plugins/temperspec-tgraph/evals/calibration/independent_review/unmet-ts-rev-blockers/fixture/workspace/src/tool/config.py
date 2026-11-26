import sys
from pathlib import Path


def load(path):
    try:
        return Path(path).read_text()
    except FileNotFoundError:
        print(f"missing config file: {path}", file=sys.stderr)
        sys.exit(1)
