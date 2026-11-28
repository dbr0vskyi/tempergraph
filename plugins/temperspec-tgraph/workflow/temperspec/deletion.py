"""After-script that deletes files named by `chore` rows whose Change describes an explicit file deletion (COD-B1)."""

from __future__ import annotations

import re
from pathlib import Path
from typing import Any

from . import specfmt

DELETE_PATH = re.compile(r"\bDelete\s+(\S+)", re.IGNORECASE)


def delete_chore_files(ctx: Any) -> dict[str, str]:
    """Runs after the code step's session: finds every `chore` row whose Change starts with an explicit
    `Delete <path>` command and deletes that file from the workspace (COD-B1).  Returns `{}`."""
    plan_path = (ctx.artifacts or {}).get("plan", {}).get("plan")
    if not plan_path:
        return {}
    workdir = Path(ctx.workdir)
    try:
        plan_text = (workdir / plan_path).read_text(encoding="utf-8")
    except OSError:
        return {}
    plan = specfmt.parse_plan(plan_text)
    resolved_workdir = workdir.resolve()
    for row in plan.rows:
        if row.kind != "chore":
            continue
        m = DELETE_PATH.search(row.change)
        if m is None:
            continue
        try:
            target = (workdir / m.group(1)).resolve()
            if target.is_relative_to(resolved_workdir) and target.is_file():
                target.unlink()
        except OSError:
            pass
    return {}
