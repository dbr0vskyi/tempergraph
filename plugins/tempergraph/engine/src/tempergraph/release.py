"""The engine release record, `release.json` (VER-B8); plain data in the package, stdlib only."""

from __future__ import annotations

import json
from functools import cache
from pathlib import Path
from typing import Any

RELEASE_JSON = Path(__file__).parent / "data" / "release.json"


@cache
def release() -> dict[str, Any]:
    data = json.loads(RELEASE_JSON.read_text(encoding="utf-8"))
    assert isinstance(data, dict)
    return data
