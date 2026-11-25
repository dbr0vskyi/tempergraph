"""The list of questions of the one pause (spec `owner-questions`, OWQ-B2 to OWQ-B6; task i63-64)."""

from __future__ import annotations

import importlib
import json
from pathlib import Path
from types import SimpleNamespace
from typing import Any

import pytest
from tempergraph.package.loader import load_package
from tempergraph.run import asking

ROOT = Path(__file__).resolve().parents[1]
SPEC = load_package(ROOT).spec
routing = importlib.import_module("tgwf_temperspec.routing")
checks = importlib.import_module("tgwf_temperspec.checks")

HEAD = ("# Triage: T\n\n## Task\n\nx\n\n## Acceptance criteria\n\n1. One\n\n## Existing documents\n\n- None\n\n"
        "## Gaps\n\n")
TAIL = "\n## Route\n\n- Deliver: code\n- Route: discovery\n"


def _row(n: int, sort: str, covered: bool = False) -> str:
    kind = "decision needed" if sort == "Owner decision" else "spec gap"
    cover = " Covered by SES-B1 and SES-AC1." if covered else ""
    return f"- G{n} {kind}: concept {n}. Searched `docs/`: nothing.{cover} {sort}\n"


def _entry(n: int, options: list[tuple[str, str]] | None = None, default: str = "a") -> str:
    opts = options or [("a", "2"), ("b", "1"), ("c", "78")]
    joined = "; ".join(f"{lab}) {text}" for lab, text in opts)
    return f"- G{n}: Question number {n}?\n  - Options: {joined}\n  - Default: {default}\n  - If wrong: cost {n}\n"


def _note(rows: str, owner: str | None) -> str:
    return HEAD + rows + ("" if owner is None else f"\n## Owner decisions\n\n{owner}") + TAIL


def _ctx(work: Path, note: str, conversation: str | None) -> Any:
    work.mkdir(parents=True, exist_ok=True)
    (work / "triage_note.md").write_text(note, encoding="utf-8")
    return SimpleNamespace(unit="owner_questions", workdir=work, request={}, values={},
                           artifacts={"triage": {"triage_note": "triage_note.md"}},
                           settings={} if conversation is None else {"conversation": conversation})


def _ask(work: Path, note: str, conversation: str | None) -> tuple[dict[str, str], list[Any]]:
    """The callable's result, and the questions the engine's own reader finds in the file it wrote."""
    got = routing.owner_questions(_ctx(work, note, conversation))
    listed = asking.from_list((work / got["question_list"]).read_text(encoding="utf-8")) if "empty" not in got else []
    return got, listed


def _names(listed: list[Any]) -> list[str]:
    return [q.name for q in listed]


def _fixture_note() -> str:
    return (ROOT / "evals" / "checks" / "triage" / "must-pass" / "6-owner-decisions" / "triage_note.md").read_text(
        encoding="utf-8")


# -- OWQ-AC3: one choice question for each owner decision ------------------------------------------------------


def test_owq_ac3_an_owner_decision_is_one_choice_question_named_by_its_gap(tmp_path: Path) -> None:  # AC 2
    got, listed = _ask(tmp_path, _fixture_note(), "blocking")
    assert "empty" not in got and got["question_list"].endswith("question_list.json")
    assert _names(listed) == ["g2", "g3"]  # the order of the note; the findable G1 is no question
    first, second = listed
    assert first.kind == "choice" and first.choices == ("a", "b", "c") and first.default == "a"
    assert second.kind == "choice" and second.choices == ("a", "b") and second.default == "a"
    for gap, q, words in (("G2", first, ["a) 2", "b) 1", "c) 78"]), ("G3", second, ["a) standard error",
                                                                                  "b) standard output"])):
        assert gap in q.text and "?" in q.text
        positions = [q.text.index(w) for w in words]
        assert positions == sorted(positions)  # each option with its label, in the order of the note
    assert "Which exit code does the tool give" in first.text


def test_owq_ac3_the_default_may_be_written_as_the_words_of_an_option(tmp_path: Path) -> None:  # AC 2
    note = _note(_row(1, "Owner decision"), _entry(1, default="78"))
    _, listed = _ask(tmp_path, note, "blocking")
    assert listed[0].default == "c"


def test_owq_ac3_the_wording_is_at_most_500_characters_and_every_label_stays(tmp_path: Path) -> None:  # AC 2
    long = "x" * 400
    note = _note(_row(1, "Owner decision"), _entry(1, options=[("a", long), ("b", long), ("c", long)]))
    _, listed = _ask(tmp_path, note, "blocking")  # the engine's reader refuses a wording over 500
    text = listed[0].text
    assert len(text) <= 500 and listed[0].choices == ("a", "b", "c")
    for label in ("a)", "b)", "c)"):
        assert label in text
    assert "G1" in text and "Question number 1?" in text


def test_owq_ac3_the_list_is_a_file_that_git_ignores(tmp_path: Path) -> None:  # AC 2
    got, _ = _ask(tmp_path, _fixture_note(), "blocking")
    assert (tmp_path / got["question_list"]).parent.name == ".tempergraph"
    assert (tmp_path / ".tempergraph" / ".gitignore").read_text(encoding="utf-8").strip() == "*"
    assert isinstance(json.loads((tmp_path / got["question_list"]).read_text(encoding="utf-8")), list)


# -- OWQ-AC6: at most twenty questions -------------------------------------------------------------------------


def test_owq_ac6_a_pause_for_22_owner_decisions_holds_the_first_20(tmp_path: Path) -> None:  # AC 2
    rows = "".join(_row(n, "Owner decision") for n in range(1, 23))
    owner = "".join(_entry(n) for n in range(1, 23))
    _, listed = _ask(tmp_path, _note(rows, owner), "blocking")
    assert _names(listed) == [f"g{n}" for n in range(1, 21)]


def test_owq_b2_never_lists_no_question_and_says_so(tmp_path: Path) -> None:  # AC 2
    got, listed = _ask(tmp_path, _fixture_note(), "never")
    assert got.get("empty") == "yes" and listed == []
    assert json.loads((tmp_path / got["question_list"]).read_text(encoding="utf-8")) == []


def test_owq_b2_blocking_with_no_owner_decision_lists_no_question(tmp_path: Path) -> None:  # AC 2
    got, _ = _ask(tmp_path, _note(_row(1, "Findable") + _row(2, "Findable"), "None\n"), "blocking")
    assert got.get("empty") == "yes"


# -- OWQ-AC4: `always` also asks the reading of each findable gap ----------------------------------------------


def _mixed() -> str:
    rows = _row(1, "Findable") + _row(2, "Owner decision") + _row(3, "Findable", covered=True)
    return _note(rows, _entry(2))


def test_owq_ac4_always_adds_a_reading_for_each_findable_gap_without_covered_by(tmp_path: Path) -> None:  # AC 3
    _, listed = _ask(tmp_path, _mixed(), "always")
    assert _names(listed) == ["g2", "g1"]  # the owner decision first, the reading second, none for G3 (`Covered by`)
    reading = listed[1]
    assert reading.kind == "choice" and reading.choices == ("right", "wrong") and reading.default == "right"
    assert "G1" in reading.text and "right" in reading.text.lower()


def test_owq_ac4_blocking_holds_the_decisions_only(tmp_path: Path) -> None:  # AC 3
    _, listed = _ask(tmp_path, _mixed(), "blocking")
    assert _names(listed) == ["g2"]


def test_owq_ac2_always_with_no_owner_decision_and_two_findable_gaps_asks_two_readings(tmp_path: Path) -> None:  # OWQ-AC2, AC 3
    got, listed = _ask(tmp_path, _note(_row(1, "Findable") + _row(2, "Findable"), "None\n"), "always")
    assert "empty" not in got and _names(listed) == ["g1", "g2"]


@pytest.mark.parametrize("rows", ["", _row(1, "Findable", covered=True) + _row(2, "Findable", covered=True)],
                         ids=["no gap", "every gap covered"])
def test_owq_ac2_always_with_no_gap_or_only_covered_gaps_asks_nothing(rows: str, tmp_path: Path) -> None:  # OWQ-AC2, AC 3
    note = _note(rows or "None\n", "None\n")
    got, _ = _ask(tmp_path, note, "always")
    assert got.get("empty") == "yes"


def test_owq_ac2_blocking_with_none_asks_nothing(tmp_path: Path) -> None:  # OWQ-AC2, AC 3
    got, _ = _ask(tmp_path, _note(_row(1, "Findable"), "None\n"), "blocking")
    assert got.get("empty") == "yes"


def test_owq_ac6_15_decisions_and_10_readings_give_the_15_and_five_readings(tmp_path: Path) -> None:  # AC 3
    rows = "".join(_row(n, "Owner decision") for n in range(1, 16)) + "".join(
        _row(n, "Findable") for n in range(16, 26))
    owner = "".join(_entry(n) for n in range(1, 16))
    _, listed = _ask(tmp_path, _note(rows, owner), "always")
    assert _names(listed) == [f"g{n}" for n in range(1, 21)]
    assert [q.choices for q in listed[:15]] == [("a", "b", "c")] * 15
    assert [q.choices for q in listed[15:]] == [("right", "wrong")] * 5


# -- OWQ-AC5: a reading called wrong keeps the pause open -------------------------------------------------------


def test_owq_ac5_the_answers_check_refuses_a_reading_called_wrong_and_names_the_gap() -> None:  # AC 3
    problems = checks.owner_answers_check({"g2": "a", "g1": "wrong"})
    assert len(problems) == 1 and "G1" in problems[0] and "right" in problems[0]
    assert checks.owner_answers_check({"g2": "a", "g1": "right"}) in (None, [])
    assert checks.owner_answers_check({"g2": "b"}) in (None, [])  # an owner decision is never refused
