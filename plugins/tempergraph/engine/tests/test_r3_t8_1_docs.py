"""The documents of R3-T8.1 say what is built and what is left (AC 4 of task r3-t8-1)."""

from __future__ import annotations

import re
from pathlib import Path

DOCS = Path(__file__).resolve().parents[2] / "docs"


def read(*parts: str) -> str:
    return (DOCS.joinpath(*parts)).read_text(encoding="utf-8")


def section(text: str, heading: str) -> str:
    """The text under `heading` up to the next heading of the same or a higher level."""
    level = len(heading) - len(heading.lstrip("#"))
    start = text.index(heading + "\n")
    rest = text[start + len(heading):]
    end = re.search(rf"^#{{1,{level}}} ", rest, re.M)
    return rest[:end.start()] if end else rest


def test_ac_4_spec_70_has_no_open_questions_section() -> None:
    # AC 4: the cache is built, so the only item of the section, "Not built yet: the script cache", is gone
    spec = read("specs", "70-script-units-and-hybrid-steps.spec.md")
    assert "## Open questions" not in spec
    assert "Not built yet" not in spec


def test_ac_4_spec_11_names_the_proxys_live_check_beside_the_probes_item() -> None:
    spec = read("specs", "11-executor-claude-code.spec.md")
    items = [ln for ln in section(spec, "## Open questions").splitlines() if ln.startswith("- ")]
    proxy = [ln for ln in items if ln.startswith("- Not built yet") and "proxy" in ln]
    assert len(proxy) == 1 and "dontAsk" in proxy[0] and "Owner: engine owner" in proxy[0]
    assert any(ln.startswith("- Not built yet: probes P-CC-1 to P-CC-11") for ln in items)  # that item stays


def test_ac_4_third_release_plan_records_r3_t8_1_as_built() -> None:
    plan = read("plans", "third-release.plan.md")
    body = section(plan, "#### R3-T8.1 Script cache, audit judge, judge MCP views")
    status = next(ln for ln in body.splitlines() if ln.startswith("Status: built."))
    for needle in ("SCR-B9", "SCR-AC4", "JDG-AC7", "ECC-AC7", "ECC-AC8", "ECC-AC9", "GRD-AC6"):
        assert needle in status
    for test_file in ("test_script_cache.py", "test_audit_judge.py", "test_mcp_proxy.py", "test_judge_mcp_deferral.py"):
        assert test_file in status
    line = next(ln for ln in plan.splitlines() if ln.startswith("**Status:"))
    assert "R3-T8.1" in line


def test_ac_4_live_checks_has_a_row_for_the_filtering_proxy() -> None:
    checks = read("plans", "live-checks.plan.md")
    rows = [ln for ln in checks.splitlines() if ln.startswith("| L-") and "ECC-B3" in ln and "ECC-B15" in ln]
    assert len(rows) == 1
