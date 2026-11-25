"""The tool's entry point."""
from pathlib import Path


def main() -> int:
    return run(Path.cwd() / "tool.toml")
