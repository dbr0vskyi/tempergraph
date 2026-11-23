"""The audit's `contest-identical-slots` (ARC-B15, ARC-AC2): raised when every slot shares executor, model and prompt, quiet
when one differs, no longer skipped as not built, and the same condition as validation's warning (CTS-B10)."""

from __future__ import annotations

from pathlib import Path
from typing import Any

from tempergraph.api import Contest, Slot
from tempergraph.audit import catalog as cat
from tempergraph.model.validate import identical_slots, validate

from .test_audit import CAPS, clean_step, own_rules, run, wf


def contested(slots: Any) -> Any:
    return wf({"pick": Contest(step=clean_step(), slots=slots)}, allow_commands=["git status"])


def test_identical_slots_are_raised_with_the_catalog_record(tmp_path: Path) -> None:  # ARC-AC2 (ARC-B15)
    rep = run(contested([Slot("a"), Slot("b")]), tmp_path)
    (f,) = [x for x in rep.findings if x.rule == "contest-identical-slots"]
    r = cat.BY_ID["contest-identical-slots"]
    assert (f.layer, f.severity, f.confidence, f.cause, f.remedy) == ("definition", r.severity, r.confidence, r.cause,
                                                                      r.remedy)
    assert f.unit == "pick" and f.evidence == {"slots": 2} and f.location["field"] == "units.pick.contest.slots"


def test_a_slot_count_runs_the_base_step_unchanged_and_is_raised_too(tmp_path: Path) -> None:  # ARC-AC2 (ARC-B15)
    assert "contest-identical-slots" in own_rules(run(contested(3), tmp_path))


def test_it_is_quiet_when_one_slot_differs_in_model_executor_or_prompt(tmp_path: Path) -> None:  # ARC-AC2 (ARC-B15)
    for slots in ([Slot("a"), Slot("b", model="large")], [Slot("a"), Slot("b", prompt_variant="Start from the tests.")],
                  [Slot("a", executor="claude"), Slot("b")]):
        assert "contest-identical-slots" not in own_rules(run(contested(slots), tmp_path)), slots


def test_it_is_no_longer_listed_among_the_skipped_rules(tmp_path: Path) -> None:  # ARC-AC2 (ARC-B15)
    rep = run(contested([Slot("a"), Slot("b", model="large")]), tmp_path)
    assert "contest-identical-slots" not in {s["rule"] for s in rep.rules_skipped}
    assert {"council-one-family", "council-even-majority"} <= {s["rule"] for s in rep.rules_skipped}  # the council's stay


def test_the_audit_and_validation_ask_one_question(tmp_path: Path) -> None:  # ARC-AC2 (ARC-B15, CTS-B10)
    for slots in ([Slot("a"), Slot("b")], [Slot("a"), Slot("b", model="large")], 3):
        spec = contested(slots)
        warned = "contest-identical-slots" in {f.code for f in validate(spec, CAPS) if f.severity == "warning"}
        audited = "contest-identical-slots" in own_rules(run(spec, tmp_path))
        assert warned == audited == identical_slots(spec, "pick"), slots
