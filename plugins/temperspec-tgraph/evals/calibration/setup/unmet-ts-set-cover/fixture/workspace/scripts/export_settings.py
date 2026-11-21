"""Print the settings of `tool.toml` as JSON."""

import json
import tomllib
from pathlib import Path

print(json.dumps(tomllib.loads(Path("tool.toml").read_text())))
