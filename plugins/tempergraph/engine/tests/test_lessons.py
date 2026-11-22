"""Workflow lessons: file, validation, rendering to the step only, digest (LSN-B1, B2, B3, AC-1 to AC-3)."""

from __future__ import annotations

import dataclasses
import json
from pathlib import Path
from typing import Any

import pytest

from tempergraph.constants import ExitCode
from tempergraph.executors.capabilities import DECLARED
from tempergraph.executors.standins import standin
from tempergraph.improve import lessons
from tempergraph.model.validate import validate

from .fixtures.workflows import two_step
from .test_run import DRAFT, REVIEW, go, judge, records

RULE = "Read the test command from the plan, not from the repository's README."


def entry(n: int, text: str = RULE, status: str = "active", source: str = "person") -> dict[str, Any]:
    return {"id": f"L-{n}", "text": text, "status": status, "source": source,
            "evidence": {"cluster_id": "c", "runs": 3, "distinct_requests": 3}, "added_in": "0.1.0"}


def package(tmp: Path, unit: str, entries: list[dict[str, Any]]) -> Any:
    (tmp / "lessons").mkdir(parents=True, exist_ok=True)
    (tmp / "lessons" / f"{unit}.json").write_text(json.dumps({"schema_version": 1, "lessons": entries}))
    return dataclasses.replace(two_step(), package_root=tmp)


def codes(spec: Any) -> list[str]:
    return [f.code for f in validate(spec, DECLARED) if f.code.startswith("lessons")]


def test_rendered_to_the_step_only_with_digest(repo: Path, tmp_path: Path) -> None:  # LSN-B1, AC-1, AC-3
    spec = package(tmp_path / "pkg", "draft", [entry(2, "Name every file the step changed."), entry(1),
                                               entry(3, "Never print secrets.", status="retired")])
    ex = standin("claude", steps=[DRAFT, REVIEW], judges=[judge(), judge()])
    assert go(repo, ex, spec=spec).exit_code is ExitCode.FINISHED
    step = next(c.request.prompt for c in ex.calls if c.kind == "step")
    assert "L-1: " + RULE in step and step.index("L-1") < step.index("L-2") and "Never print" not in step
    assert all(RULE not in c.request.prompt for c in ex.calls if c.kind == "judge")
    runs = [r for r in records(repo) if r["kind"] == "agent_run"]
    want = lessons.digest(lessons.block(lessons.load(spec, "draft")))
    tagged = {(r["session_key"].split(".")[0], r.get("session_kind")) for r in runs if r.get("lessons_digest") == want}
    assert want and tagged == {("draft", "step")}, [(r["session_key"], r.get("session_kind")) for r in runs]

def test_budget_literal_unknown_unit_malformed(tmp_path: Path) -> None:  # LSN-B2, LSN-B6, LSN-B7, AC-2
    assert codes(package(tmp_path / "a", "draft", [entry(n, f"Rule number {chr(97 + n)} holds.")
                                                  for n in range(1, 14)])) == ["lessons-budget"]
    spec = package(tmp_path / "b", "draft", [entry(1, "Check RN-1423 first."), entry(2, "See https://x.example."),
                                             entry(3, 'Say "the build is green now" always.')])
    assert codes(spec).count("lessons-literal") == 3
    assert codes(package(tmp_path / "c", "ghost", [entry(1)])) == ["lessons-unknown-unit"]
    bad = tmp_path / "d"
    (bad / "lessons").mkdir(parents=True)
    (bad / "lessons" / "draft.json").write_text("{nope")
    spec = dataclasses.replace(two_step(), package_root=bad)
    assert codes(spec) == ["lessons-malformed"]
    with pytest.raises(lessons.LessonsError):
        lessons.load(spec, "draft")
    assert codes(package(tmp_path / "e", "draft", [entry(1), entry(1, "Another rule.")])) == ["lessons-id"]
    assert codes(package(tmp_path / "f", "draft", [entry(1)])) == []


def test_delta_only_and_criterion_restated() -> None:  # LSN-B3, LSN-B9
    old = [entry(n, f"Rule {chr(97 + n)} applies here.") for n in range(1, 6)]
    rewrite = [dict(e, text=e["text"] + " Always.") for e in old]
    assert lessons.classify_change(old, rewrite, []) == "lessons_rewrite"
    assert lessons.classify_change(old, list(reversed(old)), []) == "lessons_rewrite"
    assert lessons.classify_change(old, old[1:], []) == "lessons_rewrite"  # removed, not retired
    assert lessons.classify_change(old, old + [entry(6)], []) is None
    retired = [dict(old[0], status="retired")] + old[1:]
    assert lessons.classify_change(old, retired, []) is None
    crit = ["The notes read the test command from the plan, not from the README of the repository."]
    assert lessons.classify_change(old, old + [entry(6)], crit) == "lesson_is_criterion"
