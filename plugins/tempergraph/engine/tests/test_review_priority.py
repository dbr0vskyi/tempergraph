"""The review plan lists targets in priority order, units in trouble first (SRV-B24, SRV-AC8)."""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any

import pytest

from tempergraph.improve import digest, review
from tempergraph.store.layout import run_dir

from .test_session_review import bash, fixture_run, rec, session, ticket

RUN_ORDER = ("triage.1.step", "triage.1.judge", "plan.1.step", "plan.1.judge", "code.1.step", "code.1.judge",
             "code.2.retry", "code.2.judge", "code.3.retry", "code.3.judge")


def digests(keys: tuple[str, ...] = RUN_ORDER) -> list[dict[str, Any]]:
    return [{"session_key": k, "unit": digest.parse_key(k)[0], "kind": digest.parse_key(k)[2], "capture": "full",
             "turns": 3} for k in keys]


def targets(p: dict[str, Any]) -> list[str]:
    return [t["session_key"] for t in p["targets"]]


def test_a_failed_unit_is_read_first_later_attempt_before_earlier() -> None:  # SRV-AC8
    p = review.plan({"review": "full"}, digests(), trouble={"code"})
    assert targets(p) == ["code.3.judge", "code.3.retry", "code.2.judge", "code.2.retry", "code.1.judge",
                          "code.1.step", "plan.1.judge", "plan.1.step", "triage.1.judge", "triage.1.step"]


def test_no_unit_in_trouble_lists_the_session_that_started_last_first() -> None:  # SRV-AC8
    p = review.plan({"review": "full"}, digests(), trouble=set())
    assert targets(p) == list(reversed(RUN_ORDER))


def test_a_plan_from_digests_alone_still_works() -> None:  # SRV-AC8
    assert targets(review.plan({"review": "full"}, digests())) == list(reversed(RUN_ORDER))


def test_two_units_in_trouble_keep_latest_start_first_in_their_group() -> None:  # SRV-AC8
    p = review.plan({"review": "full"}, digests(), trouble={"plan", "code"})
    assert targets(p) == ["code.3.judge", "code.3.retry", "code.2.judge", "code.2.retry", "code.1.judge",
                          "code.1.step", "plan.1.judge", "plan.1.step", "triage.1.judge", "triage.1.step"]
    q = review.plan({"review": "full"}, digests(), trouble={"triage"})
    assert targets(q)[:2] == ["triage.1.judge", "triage.1.step"]
    assert targets(q)[2] == "code.3.judge"


def test_named_sessions_come_before_the_rest_inside_a_plan() -> None:  # SRV-AC8
    keys = ("plan.1.step", "triage.1.step")
    p = review.plan({"review": "full"}, digests(), keys=keys, trouble={"code"})
    assert targets(p) == ["plan.1.step", "triage.1.step"]


def test_a_full_plan_has_no_count_cap() -> None:  # SRV-AC8, SRV-B21
    many = tuple(f"u{i}.1.step" for i in range(30))
    p = review.plan({"review": "full"}, digests(many))
    assert len(p["targets"]) == 30 and not any(s["reason"] == "budget" for s in p["skipped"])


@pytest.mark.parametrize(("records", "want"), [
    ([{"kind": "check", "unit": "code", "result": "FAIL"}], {"code"}),
    ([{"kind": "check", "unit": "code", "result": "PASS"}], set()),
    ([{"kind": "gate", "unit": "code", "verdict": "BACK", "token": "BACK"}], {"code"}),
    ([{"kind": "gate", "unit": "code", "verdict": None, "token": "ESCALATE"}], {"code"}),
    ([{"kind": "gate", "unit": "code", "verdict": "PROCEED", "token": "PROCEED"}], set()),
    ([{"kind": "pause", "unit": "plan", "pause_kind": "approval"}], {"plan"}),
    ([{"kind": "judgement", "unit": "code", "blockers": ["c-1"]}], {"code"}),
    ([{"kind": "judgement", "unit": "code", "blockers": []}], set()),
    ([{"kind": "route", "unit": "sw", "chosen_by": "rearm", "rearm_unit": "code"}], {"code"}),
    ([{"kind": "route", "unit": "sw", "chosen_by": "predicate"}], set()),
])
def test_the_run_records_name_the_units_in_trouble(tmp_path: Path, records: list[dict[str, Any]],
                                                    want: set[str]) -> None:  # SRV-AC8
    rd = run_dir(tmp_path, "demo", "P-1")
    rd.mkdir(parents=True)
    (rd / "run.jsonl").write_text("\n".join(json.dumps(r) for r in records) + "\n")
    assert review._trouble(tmp_path, "demo", "P-1") == want


def test_a_run_without_records_has_no_unit_in_trouble(tmp_path: Path) -> None:  # SRV-AC8
    assert review._trouble(tmp_path, "demo", "P-none") == set()


def test_the_review_reads_the_failed_unit_first(tmp_path: Path) -> None:  # SRV-AC8, no model call
    rd = run_dir(tmp_path, "demo", "P-2")
    lines = []
    for key in ("triage.1.step", "plan.1.step", "code.1.step", "code.2.retry"):
        session(tmp_path, "P-2", key, [bash("make")])
        r = rec(key, unit=key.split(".")[0])
        lines.append(json.dumps(r))
        d = digest.build(rd / "sessions" / key, r, {"tools": ["shell"]})
        (rd / "sessions" / key / "digest.json").write_text(json.dumps(d))
    lines.append(json.dumps({"kind": "check", "unit": "code", "result": "FAIL"}))
    lines.append(json.dumps({"kind": "gate", "unit": "code", "verdict": None, "token": "ESCALATE"}))
    (rd / "run.jsonl").write_text("\n".join(lines) + "\n")

    class NoCalls:
        def available(self) -> list[str]:
            raise AssertionError("a dry run starts no reviewer")

    out = review.run(ticket(tmp_path, "P-2"), NoCalls(), dry_run=True)  # type: ignore[arg-type]
    assert targets(out["plan"]) == ["code.2.retry", "code.1.step", "plan.1.step", "triage.1.step"]
    fixture_run(tmp_path, "P-3")  # a run with no unit in trouble: one session, nothing to reorder
    assert targets(review.run(ticket(tmp_path, "P-3"), NoCalls(), dry_run=True)["plan"]) == ["draft.1.step"]  # type: ignore[arg-type]
