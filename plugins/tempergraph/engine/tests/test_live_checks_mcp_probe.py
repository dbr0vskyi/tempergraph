"""The runbook, the live probe and the recorded probe state for P-CC-13 (AC 6 of task i21)."""

from __future__ import annotations

import json
import re
from pathlib import Path

ENGINE = Path(__file__).resolve().parents[1]
DOCS = ENGINE.parent / "docs"
CHECKS = DOCS / "plans" / "live-checks.plan.md"


def _section4(text: str) -> str:
    start = text.index("## 4. Results\n")
    rest = text[start + len("## 4. Results\n"):]
    end = re.search(r"^## ", rest, re.M)
    return rest[:end.start()] if end else rest


def test_ac_6_runbook_has_one_row_for_the_p_cc_13_probe() -> None:
    rows = [ln for ln in CHECKS.read_text(encoding="utf-8").splitlines() if ln.startswith("| L-43") and "P-CC-13" in ln]
    assert len(rows) == 1
    for needle in ("P-CC-13", "ECC-B13", "ECC-B18", "ECC-B20", "test_p_cc_13_"):
        assert needle in rows[0]
    assert "ECC-B3" not in rows[0]


def test_ac_6_results_record_the_operators_run_of_2026_11_25() -> None:
    results = _section4(CHECKS.read_text(encoding="utf-8"))
    rows = [ln for ln in results.splitlines() if ln.startswith("| L-43 ")]
    assert len(rows) == 1
    assert "2026-11-25" in rows[0] and "2.1.332" in rows[0] and "operator" in rows[0]
    lead = results.split("\n\n")[0] if results.startswith("\n") is False else results.strip().split("\n\n")[0]
    assert "All rows below were run" not in lead
    assert "L-43" in lead


def test_ecc_ac5_every_confirmed_probe_is_recorded_with_a_date_and_the_cli_version() -> None:
    # ECC-AC5, ECC-B13: a probe listed `confirmed` has a dated, versioned, passed result row in the runbook
    from tempergraph.executors.claude import LIVE_FACTS

    text = CHECKS.read_text(encoding="utf-8")
    section3 = text[text.index("## 3. Manual rows"):text.index("## 4. Results")]
    results = _section4(text)
    facts = json.loads((ENGINE / "src" / "tempergraph" / "data" / "executor_compat.json").read_text("utf-8"))[
        "executors"]["claude"]["facts"]
    confirmed = [p for p, state in LIVE_FACTS.items() if state == "confirmed"]
    assert confirmed
    for probe in confirmed:
        rows = [ln for ln in section3.splitlines() if re.match(r"\| L-\d+ ", ln) and re.search(rf"{probe}\b", ln)]
        assert len(rows) == 1, probe
        row_id = rows[0].split("|")[1].strip()
        found = [ln for ln in results.splitlines() if ln.startswith(f"| {row_id} ")]
        assert len(found) == 1, row_id
        cells = [c.strip() for c in found[0].split("|")[1:-1]]
        assert re.fullmatch(r"\d{4}-\d{2}-\d{2}", cells[1]), cells
        assert re.fullmatch(r"\d+\.\d+\.\d+", cells[2]), cells
        assert "passed" in cells[3]
        assert f"{probe} confirmed on {cells[2]}" in facts
    for probe, state in LIVE_FACTS.items():
        if state == "not run":
            assert f"{probe} confirmed" not in facts


def test_ac_6_a_live_probe_for_p_cc_13_exists() -> None:
    probes = (ENGINE / "tests" / "live" / "test_probes.py").read_text(encoding="utf-8")
    assert re.search(r"^def test_p_cc_13_\w+\(", probes, re.M)


def test_ac_6_compat_table_facts_name_p_cc_13_confirmed_and_the_rest_not_run() -> None:
    data = json.loads((ENGINE / "src" / "tempergraph" / "data" / "executor_compat.json").read_text("utf-8"))
    facts = data["executors"]["claude"]["facts"]
    assert "P-CC-13 confirmed" in facts
    assert "P-CC-1 to P-CC-12 not yet run" in facts
