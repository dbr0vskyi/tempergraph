"""The issue body of an answered-pause cause shows what was answered (ISS-B19, ISS-AC18)."""

from __future__ import annotations

import pytest

from tempergraph.improve import filing
from tempergraph.improve.filing import Candidate, Decision

from .test_filing import CANARY, finding

CAUSES = ["answer_overrode:check", "upstream_confirmed:draft", "retry_passed_unchanged:unresolved_gap",
          "retry_same_failure", "resume_no_progress"]


def _decision(**kw: object) -> Decision:
    f = finding(**kw)
    return Decision(action="file", reason="pattern_met", candidate=Candidate(finding=f, lens="friction"),
                    repo="team/notes", counts={"runs": 3, "requests": 3, "machines": 1})


def _answered_fields() -> dict[str, object]:
    return {"decisions": {"proceed": 2, "retry": 1}, "reasons": {"plan": 2, "not given": 1},
            "criteria": {"c1": 2, "c2": 1}, "items": 2, "wait_s_median": 42}


@pytest.mark.parametrize("cause", CAUSES)
def test_section_for_each_cause(cause: str) -> None:  # ISS-AC18
    text = filing.body(_decision(cause=cause, **_answered_fields()))
    assert text.index("## Evidence") < text.index("## What was answered") < text.index("## Fingerprint")
    section = text.split("## What was answered", 1)[1].split("## Fingerprint", 1)[0]
    for word in ("`proceed` 2", "`retry` 1", "`plan` 2", "`not given` 1", "`c1` 2", "`c2` 1", "runs 3", "42"):
        assert word in section
    assert "`draft`" in section


def test_no_free_text() -> None:  # ISS-AC18, ISS-B10 canary
    fields = {**_answered_fields(), "reasons": {f"{CANARY} with space": 1, "plan": 1},
              "criteria": {f"bad criterion {CANARY}": 1, "c1": 1}}
    text = filing.body(_decision(cause="answer_overrode:check", **fields))
    section = text.split("## What was answered", 1)[1].split("## Fingerprint", 1)[0]
    assert "with space" not in section and "bad criterion" not in section
    assert "`plan` 1" in section and "`c1` 1" in section


def test_other_cause_has_no_section() -> None:  # ISS-AC18
    d = _decision(cause="retry_burst", **_answered_fields())
    assert "## What was answered" not in filing.body(d)


def test_seen_again_comment_has_none() -> None:  # ISS-AC18
    d = _decision(cause="answer_overrode:check", **_answered_fields())
    assert "## What was answered" not in filing.comment_body([d])
