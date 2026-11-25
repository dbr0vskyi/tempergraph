import sys


def load(path):
    try:
        return open(path).read()
    except FileNotFoundError:
        print(f"missing file: {path}", file=sys.stderr)
        raise SystemExit(2)
