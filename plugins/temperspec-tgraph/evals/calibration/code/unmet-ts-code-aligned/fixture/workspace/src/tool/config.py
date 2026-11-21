"""Reading the tool's settings."""

import sys
import tomllib
from pathlib import Path

CONFIG_FILE = "tool.toml"
EXIT_NO_CONFIG = 2


def load_settings() -> dict[str, object] | None:
    """The settings, or None after reporting that the file is missing."""
    path = Path(CONFIG_FILE)
    if not path.exists():
        print(f"config file {CONFIG_FILE} not found in {Path.cwd()}", file=sys.stderr)
        print("create one with `tool init`", file=sys.stderr)
        return None
    return tomllib.loads(path.read_text())
