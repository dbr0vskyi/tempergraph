"""Parallel reading (spec parallel-reading, PRL-*): the gap and component lists, the declarations of the reading units,
the reading and writing prompts, the records that agree with the units, and stand-in runs of the full discovery step and
of the setup step, with the reading sessions counted, held open and ended out of order."""

from __future__ import annotations

import dataclasses
import importlib
import json
import re
import subprocess
import threading
import time
from pathlib import Path
from types import SimpleNamespace
from typing import Any

import pytest

from tempergraph.api import CheckResult
from tempergraph.author import blueprint as bpm
from tempergraph.author.compare import compare
from tempergraph.constants import ExitCode
from tempergraph.contracts import CallableRef, JudgeSpec, SessionRequest, SessionResult
from tempergraph.docs import write_json
from tempergraph.executors.registry import Registry
from tempergraph.executors.standins import answer, standin
from tempergraph.model.diagram import diagram_model, to_mermaid
from tempergraph.package.loader import load_package
from tempergraph.run.runner import RunSettings, start

ROOT = Path(__file__).resolve().parents[1]
SPEC = load_package(ROOT).spec
routing = importlib.import_module("tgwf_temperspec.routing")
fmt = importlib.import_module("tgwf_temperspec.specfmt")
OUTCOME = json.loads((ROOT / "outcome.json").read_text(encoding="utf-8"))
UNSEEN = re.compile(r"\b(prompts?|sessions?|command runs?|reused|run once|runs once)\b", re.I)  # as test_temperspec.py
TASK = "I-1"


def _said(text: str) -> str:
    return " ".join(text.split()).lower()


def _prompt(name: str) -> str:
    return (ROOT / "prompts" / f"{name}.md").read_text(encoding="utf-8")


# -- the list of gaps (PRL-B2) ---------------------------------------------------------------------------------


def _note(rows: list[str], *, gaps: str | None = None, owner: str | None = None) -> str:
    body = gaps if gaps is not None else "\n".join(rows)
    section = "" if owner is None else f"## Owner decisions\n\n{owner}\n\n"
    return ("# Triage: I-1\n\n## Task\n\nThe task.\n\n## Acceptance criteria\n\n1. A thing.\n\n## Existing documents\n\n"
            f"- none\n\n## Gaps\n\n{body}\n\n{section}## Route\n\n- Deliver: code\n- Route: discovery\n")


def _items(tmp_path: Path, note: str) -> list[dict[str, str]]:
    path = tmp_path / "note.md"
    path.write_text(note, encoding="utf-8")
    return routing.gap_items(SimpleNamespace(artifact=path, workdir=tmp_path, values={}))


def test_each_gap_row_is_one_item_in_the_order_of_the_rows(tmp_path: Path) -> None:  # AC 4, PRL-AC2 (PRL-B2)
    rows = ["- G1 spec gap: first", "- G2 spec update: second", "- G3 decision needed: third"]
    got = _items(tmp_path, _note(rows))
    assert [i["id"] for i in got] == ["G1", "G2", "G3"]
    assert [i["text"] for i in got] == rows


def test_a_repeated_gap_number_keeps_its_first_row(tmp_path: Path) -> None:  # AC 4, PRL-AC2 (PRL-B2)
    got = _items(tmp_path, _note(["- G1 spec gap: first", "- G2 spec gap: second", "- G1 spec gap: again"]))
    assert [(i["id"], i["text"]) for i in got] == [("G1", "- G1 spec gap: first"), ("G2", "- G2 spec gap: second")]


def test_fewer_than_two_gap_rows_give_no_item(tmp_path: Path) -> None:  # AC 4, PRL-AC2 (PRL-B2)
    assert _items(tmp_path, _note([], gaps="None")) == []
    assert _items(tmp_path, _note(["- G1 spec gap: only one"])) == []
    assert _items(tmp_path, "# Triage: I-1\n\n## Task\n\nx\n") == []  # no Gaps section


def test_a_covered_row_is_a_row_like_any_other(tmp_path: Path) -> None:  # AC 4, PRL-AC2 (PRL-B2)
    got = _items(tmp_path, _note(["- G1 spec gap: first. Covered by ABC-B1 and ABC-AC1", "- G2 spec gap: second"]))
    assert [i["id"] for i in got] == ["G1", "G2"]


# -- the declaration of the reading unit of discovery (PRL-B6, PRL-B7) ---------------------------------------------


def test_the_gap_reading_unit_is_a_concurrent_read_only_map() -> None:  # AC 1, PRL-AC6, PRL-AC7 (PRL-B6, PRL-B7), PRL-AC1
    unit = SPEC.units["read_gap"]
    assert unit.kind == "map" and unit.map is not None and unit.step is not None
    assert unit.map.items_from == ("triage", "triage_note")
    assert (unit.map.mode, unit.map.concurrency, unit.map.on_empty) == ("concurrent", 3, "skip")
    assert unit.map.extract is not None and not unit.gate.back_targets
    assert sorted(unit.step.tools) == ["list", "read", "search", "web_fetch", "web_search"]  # none writes or runs
    assert set(unit.step.produces) == {"gap_finding"} and unit.step.produces["gap_finding"].max_chars == 1500
    assert isinstance(unit.gate.judge, JudgeSpec) and unit.gate.check is None
    order = list(SPEC.order)
    assert order.index("discovery_short") < order.index("read_gap") < order.index("owner_questions")
    assert order.index("owner_questions") < order.index("ask_route") < order.index("ask_owner") < order.index("discovery")
    triage_targets = SPEC.units["triage"].route_targets
    assert "read_gap" in triage_targets and "owner_questions" not in triage_targets and "discovery" not in triage_targets
    assert "discovery" in SPEC.units["ask_route"].route_targets
    assert "read_gap" in SPEC.units["discovery_short"].route_targets
    assert "discovery" not in SPEC.units["discovery_short"].route_targets
    writer = SPEC.units["discovery"]
    assert writer.step is not None and set(writer.step.produces) == {"handoff"}
    for later in ("plan", "expand", "code"):
        assert "discovery" in SPEC.units[later].gate.back_targets


# -- the prompts (PRL-B8, PRL-B9, PRL-B12) -------------------------------------------------------------------------


def test_the_gap_reading_prompt_is_briefed_on_one_gap_and_asks_for_one_line() -> None:
    # AC 1, PRL-AC8, PRL-AC9 (PRL-B8, PRL-B9)
    text = _prompt("read_gap")
    assert "{item}" in text and "{triage_note}" in text and "{gap_finding}" not in text
    said = _said(text)
    assert "only read" in said and "no file is written" in said
    assert "one line" in said and "1,500 characters" in said
    assert "line ranges or ids" in said and "what you searched" in said
    assert "ARTIFACT gap_finding:" in text
    assert not re.fullmatch(r"discovery.*\.md", "read_gap.md")  # outside the glob `ts-dis-narrow` reads


def test_the_discovery_prompt_takes_the_findings_as_claims_to_confirm() -> None:  # AC 1, PRL-AC12 (PRL-B12)
    text = _prompt("discovery")
    assert "{gap_finding}" in text
    said = _said(text)
    assert "a finding is a claim to confirm in the file it names before a document rests on it" in said
    assert "no reading session ran" in said and "yourself" in said
    for phrase in ("grep", "read the line ranges", "stop reading once"):  # what `ts-dis-narrow` reads stays
        assert phrase in said


# -- the harness: stand-in sessions that are counted, held open and ended out of order ------------------------------


def ready(ctx: Any) -> dict[str, str]:
    return {"setup_ready": "yes"}


def needed(ctx: Any) -> dict[str, str]:
    return {"setup_needed": "yes"}


def _met(unit: str, status: str = "MET") -> str:
    rows = [{"n": i, "status": status, "evidence": "stand-in", "defect_in": None, "no_change": False}
            for i in range(1, max(len(SPEC.units[unit].gate.criteria), 1) + 1)]
    return "Reviewed.\n```json\n" + json.dumps({"criteria": rows, "gap": False, "confidence": 0.9}) + "\n```"


def _claim_met() -> str:
    rows = [{"n": 1, "status": "MET", "evidence": "stand-in", "defect_in": None, "no_change": False}]
    return "Reviewed.\n```json\n" + json.dumps({"criteria": rows, "gap": False, "confidence": 0.9}) + "\n```"


class Stop(AssertionError):
    """The stand-in ends the run where the test has seen what it needs."""


class Stand:
    """A stand-in executor that answers by the unit of the session key. It records every session with its start and
    end, the peak of reading sessions open at once and each prompt, and holds a reading session open for a moment."""

    def __init__(self, *, gaps: int = 3, route: str = "discovery-only", covered: str = "no",
                 hold: dict[str, float] | None = None, no_line: dict[str, int] | None = None,
                 unmet: dict[str, int] | None = None, upstream: str | None = None, stop_plan_after: int = 99) -> None:
        self.inner = standin("claude")
        self.name = self.inner.name
        self.gaps, self.route, self.covered = gaps, route, covered
        self.hold = hold or {}
        self.no_line = dict(no_line or {})  # item -> how many of its first sessions end with no findings line
        self.unmet = dict(unmet or {})  # item -> how many of its first judge sessions say UNMET
        self.upstream = upstream  # `plan` or `code`: that unit sends the run back to discovery once
        self.stop_plan_after = stop_plan_after
        self.lock = threading.Lock()
        self.open = 0
        self.peak = 0
        self.sessions: list[dict[str, Any]] = []
        self.counts: dict[str, int] = {}
        self.clock = time.monotonic

    def __getattr__(self, name: str) -> Any:
        return getattr(self.inner, name)

    @staticmethod
    def whose(req: SessionRequest) -> tuple[str, str | None]:
        parts = req.session_key.split(".")
        return parts[0], (parts[1] if parts[0] in ("read_gap", "read_component") else None)

    def _enter(self, kind: str, req: SessionRequest) -> dict[str, Any]:
        unit, item = self.whose(req)
        with self.lock:
            self.open += 1
            if kind == "step" and item is not None:
                self.peak = max(self.peak, self.open)
            row = {"kind": kind, "unit": unit, "item": item, "start": self.clock(), "end": None,
                   "prompt": req.prompt, "key": req.session_key}
            self.sessions.append(row)
            self.counts[f"{kind}.{unit}.{item}"] = self.counts.get(f"{kind}.{unit}.{item}", 0) + 1
        return row

    def _leave(self, row: dict[str, Any]) -> None:
        with self.lock:
            self.open -= 1
            row["end"] = self.clock()

    def count(self, kind: str, unit: str, item: str | None = None) -> int:
        return sum(1 for s in self.sessions if (s["kind"], s["unit"]) == (kind, unit) and item in (None, s["item"]))

    def prompts(self, unit: str, kind: str = "step") -> list[str]:
        return [str(s["prompt"]) for s in self.sessions if (s["kind"], s["unit"]) == (kind, unit)]

    def run_step(self, req: SessionRequest, sink: Any) -> SessionResult:
        row = self._enter("step", req)
        unit, item = row["unit"], row["item"]
        try:
            if item is not None and self.hold.get(item):
                time.sleep(self.hold[item])
            work = Path(req.workdir)
            if unit == "triage":
                return self._triage(work)
            if unit == "read_gap" or unit == "read_component":
                key = "gap_finding" if unit == "read_gap" else "component_finding"
                if self.no_line.get(str(item), 0) > 0:
                    self.no_line[str(item)] -= 1
                    return answer("Read it, nothing to report.", session_id=f"s-{unit}-{item}")
                return answer(f"Read.\nARTIFACT {key}: finding of {item}", session_id=f"s-{unit}-{item}")
            if unit == "setup":
                (work / "docs" / "specs").mkdir(parents=True, exist_ok=True)
                (work / "docs" / "tasks").mkdir(parents=True, exist_ok=True)
                (work / "docs" / "specs" / "overview.spec.md").write_text("# Overview\n")
                (work / "docs" / "tasks" / f"{TASK}.setup.md").write_text("# Setup\n")
                return answer(f"Set up.\nARTIFACT overview: docs/specs/overview.spec.md\n"
                              f"ARTIFACT setup_note: docs/tasks/{TASK}.setup.md", session_id="s-setup")
            if unit == "discovery":
                (work / "docs" / "tasks").mkdir(parents=True, exist_ok=True)
                path = f"docs/tasks/{TASK}.handoff.md"
                (work / path).write_text(f"# Hand-off: {TASK}\n")
                return answer(f"Closed the gaps.\nARTIFACT handoff: {path}", session_id="s-discovery")
            if unit == "plan":
                n = self.count("step", "plan")
                if n > self.stop_plan_after:
                    raise Stop("the second plan session")
                if self.upstream == "plan" and n == 1:
                    return answer("Cannot plan.\nUPSTREAM discovery: a gap is still open", session_id="s-plan-up")
                (work / "docs" / "plans").mkdir(parents=True, exist_ok=True)
                (work / "docs" / "plans" / f"{TASK}.plan.md").write_text("# Plan\n")
                return answer(f"Planned.\nARTIFACT plan: docs/plans/{TASK}.plan.md\nARTIFACT complexity: simple",
                              session_id="s-plan")
            if unit == "code":
                if self.upstream == "code" and self.count("step", "code") == 1:
                    return answer("Cannot build.\nUPSTREAM discovery: a gap is still open", session_id="s-code-up")
                raise Stop("code reached")
            raise Stop(f"a session of {unit} that the stand-in does not answer")
        finally:
            self._leave(row)

    def _triage(self, work: Path) -> SessionResult:
        (work / "docs" / "tasks").mkdir(parents=True, exist_ok=True)
        # each row is sorted and the note lists no owner decision, so a run on the default `blocking` asks nothing
        rows = "\n".join(f"- G{n} spec gap: subject {n}. Findable" for n in range(1, self.gaps + 1)) or "None"
        path = f"docs/tasks/{TASK}.triage.md"
        (work / path).write_text(_note([], gaps=rows, owner="None"))
        some = "some" if self.gaps else "none"
        return answer(f"Triaged.\nARTIFACT triage_note: {path}\nARTIFACT gaps: {some}\nARTIFACT route: {self.route}\n"
                      f"ARTIFACT covered: {self.covered}", session_id="s-triage")

    def run_judge(self, req: SessionRequest, views: Any, sink: Any) -> SessionResult:
        row = self._enter("judge", req)
        unit, item = row["unit"], row["item"]
        try:
            if item is not None and self.hold.get(item):
                time.sleep(self.hold[item] / 2)
            if "upstream-claim" in req.prompt:
                return answer(_claim_met(), tools=("Read",), session_id="j-claim")
            status = "MET"
            if item is not None and self.unmet.get(item, 0) > 0:
                self.unmet[item] -= 1
                status = "UNMET"
            return answer(_met(unit, status), tools=("Read",), session_id=f"j-{unit}-{item}")
        finally:
            self._leave(row)


def _repo(root: Path, files: dict[str, str] | None = None) -> Path:
    root.mkdir(parents=True, exist_ok=True)

    def git(*args: str) -> None:
        subprocess.run(["git", "-c", "user.name=t", "-c", "user.email=t@example.invalid", *args], cwd=root,
                       check=True, capture_output=True)

    git("init", "-q", "-b", "main")
    (root / "README.md").write_text("scratch\n")
    for name, body in (files or {}).items():
        (root / name).parent.mkdir(parents=True, exist_ok=True)
        (root / name).write_text(body)
    git("add", "-f", "-A")
    git("commit", "-q", "-m", "start")
    return root


def passes(ctx: Any) -> CheckResult:
    return CheckResult(result="PASS", evidence="stand-in")


def _spec(prepare: Any = ready) -> Any:
    """The package's spec with `prepare` answered by a callable, a check that passes on each gate that has one, and no
    outcome gate."""
    units = {}
    for name, u in SPEC.units.items():
        check = CallableRef(module=__name__, qualname="passes", func=passes) if u.gate.check is not None else None
        units[name] = dataclasses.replace(u, gate=dataclasses.replace(u.gate, check=check))
    script = dataclasses.replace(SPEC.units["prepare"].script, run=None, call=CallableRef(
        module=__name__, qualname=prepare.__name__, func=prepare))
    units["prepare"] = dataclasses.replace(units["prepare"], script=script)
    return dataclasses.replace(SPEC, units=units, outcome=None)


def _run(tmp_path: Path, ex: Stand, *, prepare: Any = ready, files: dict[str, str] | None = None) -> Any:
    repo = _repo(tmp_path / "repo", files)
    reg = Registry()
    reg.register(ex)
    try:
        # the stand-in plan is simple, so the run takes the `single` arm of code_mode straight to code
        settings = RunSettings(sleep=lambda s: None, flags={"code_mode.arm": "single"})
        return start(_spec(prepare), TASK, {"request": "x"}, repo, reg, settings)
    except Stop:
        return None


# -- the full discovery step on stand-ins (PRL-B1, PRL-B2, PRL-B7) ---------------------------------------------


def test_each_of_three_gaps_gets_a_reading_session_then_one_writing_session(tmp_path: Path) -> None:
    # AC 1, PRL-AC1 (PRL-B1)
    ex = Stand(gaps=3)
    out = _run(tmp_path, ex)
    assert out is not None and out.exit_code is ExitCode.FINISHED, getattr(out, "message", None)
    assert sorted(s["item"] for s in ex.sessions if (s["kind"], s["unit"]) == ("step", "read_gap")) == ["G1", "G2", "G3"]
    assert ex.count("step", "discovery") == 1


def test_two_gaps_start_two_reading_sessions(tmp_path: Path) -> None:  # AC 1, PRL-AC1 (PRL-B1)
    ex = Stand(gaps=2)
    out = _run(tmp_path, ex)
    assert out is not None and out.exit_code is ExitCode.FINISHED, getattr(out, "message", None)
    assert ex.count("step", "read_gap") == 2 and ex.count("step", "discovery") == 1


def test_the_short_visit_starts_no_reading_session(tmp_path: Path) -> None:  # AC 1, PRL-AC1 (PRL-B1)
    ex = Stand(gaps=4, route="discovery", covered="yes")
    _run(tmp_path, ex)
    assert ex.count("step", "discovery_short") >= 1 and ex.count("step", "read_gap") == 0


def test_one_gap_and_no_gap_start_no_reading_session(tmp_path: Path) -> None:  # AC 4, PRL-AC2 (PRL-B2)
    one = Stand(gaps=1)
    out = _run(tmp_path / "one", one)
    assert out is not None and out.exit_code is ExitCode.FINISHED, getattr(out, "message", None)
    assert one.count("step", "discovery") == 1 and one.count("step", "read_gap") == 0
    none = Stand(gaps=0)  # a docs delivery whose note lists no gap
    out = _run(tmp_path / "none", none)
    assert out is not None and out.exit_code is ExitCode.FINISHED, getattr(out, "message", None)
    assert none.count("step", "discovery") == 1 and none.count("step", "read_gap") == 0


def test_never_more_than_three_reading_sessions_are_open_at_once(tmp_path: Path) -> None:  # AC 1, PRL-AC7 (PRL-B7)
    # Each session is held long enough that a loaded machine (CI, the nested package run beside the engine suite's
    # workers) still starts the next one while it is open: at 0.1 s the two of the second case once ran one by one.
    five = Stand(gaps=5, hold={f"G{n}": 0.4 for n in range(1, 6)})
    out = _run(tmp_path / "five", five)
    assert out is not None and out.exit_code is ExitCode.FINISHED, getattr(out, "message", None)
    assert five.count("step", "read_gap") == 5 and 2 <= five.peak <= 3, five.peak
    two = Stand(gaps=2, hold={"G1": 1.0, "G2": 1.0})
    _run(tmp_path / "two", two)
    assert two.peak == 2  # both are open at the same time


def test_the_writing_session_starts_after_every_reading_session_has_ended(tmp_path: Path) -> None:
    # AC 1, PRL-AC10 (PRL-B10)
    ex = Stand(gaps=3, hold={"G1": 0.3})
    out = _run(tmp_path, ex)
    assert out is not None and out.exit_code is ExitCode.FINISHED, getattr(out, "message", None)
    reading = [s for s in ex.sessions if s["unit"] == "read_gap"]
    first = next(s for s in ex.sessions if (s["kind"], s["unit"]) == ("step", "discovery"))
    assert max(s["end"] for s in reading) <= first["start"]
    g1 = next(s for s in reading if (s["kind"], s["item"]) == ("step", "G1"))
    assert g1["end"] == max(s["end"] for s in reading if s["kind"] == "step")  # the first to start ended last


def test_a_reading_session_with_no_findings_line_runs_again_alone(tmp_path: Path) -> None:  # AC 1, PRL-AC10 (PRL-B10)
    ex = Stand(gaps=3, no_line={"G2": 1})
    out = _run(tmp_path, ex)
    assert out is not None and out.exit_code is ExitCode.FINISHED, getattr(out, "message", None)
    assert [ex.count("step", "read_gap", g) for g in ("G1", "G2", "G3")] == [1, 2, 1]
    again = [s for s in ex.sessions if (s["kind"], s["unit"], s["item"]) == ("step", "read_gap", "G2")]
    first = next(s for s in ex.sessions if (s["kind"], s["unit"]) == ("step", "discovery"))
    assert all(s["end"] <= first["start"] for s in again)  # the writing session waited for the second try


def test_the_writing_session_lists_the_findings_in_the_order_of_the_gaps(tmp_path: Path) -> None:
    # AC 1, PRL-AC11 (PRL-B11, PRL-B12)
    ex = Stand(gaps=3, hold={"G1": 0.2, "G2": 0.4})  # they end in the order G3, G1, G2
    out = _run(tmp_path, ex)
    assert out is not None and out.exit_code is ExitCode.FINISHED, getattr(out, "message", None)
    (prompt,) = ex.prompts("discovery")
    lines = [ln for ln in prompt.splitlines() if re.match(r"G\d: ", ln)]
    assert lines == ["G1: finding of G1", "G2: finding of G2", "G3: finding of G3"]
    assert "claim to confirm" in _said(prompt)


def test_with_no_reading_session_the_writing_session_is_told_to_read_for_itself(tmp_path: Path) -> None:
    # AC 4, PRL-AC11 (PRL-B11)
    ex = Stand(gaps=1)
    _run(tmp_path, ex)
    (prompt,) = ex.prompts("discovery")
    assert not re.search(r"^G\d: ", prompt, re.M)
    said = _said(prompt)
    assert "none" in said and "no reading session ran" in said and "yourself" in said


@pytest.mark.parametrize("sender", ["plan", "code"])
def test_a_return_to_discovery_starts_no_reading_session_and_keeps_the_findings(tmp_path: Path, sender: str) -> None:
    # AC 1, PRL-AC3 (PRL-B3, PRL-B11)
    ex = Stand(gaps=3, route="discovery", upstream=sender, stop_plan_after=2 if sender == "plan" else 1)
    _run(tmp_path, ex)
    assert ex.count("step", "discovery") == 2  # one more writing session
    assert ex.count("step", "read_gap") == 3  # and no reading session again
    first, second = ex.prompts("discovery")
    for prompt in (first, second):
        lines = [ln for ln in prompt.splitlines() if re.match(r"G\d: ", ln)]
        assert lines == ["G1: finding of G1", "G2: finding of G2", "G3: finding of G3"]


def test_every_reading_session_has_a_judge_session_of_its_own(tmp_path: Path) -> None:
    # AC 3, PRL-AC13, PRL-AC14 (PRL-B13, PRL-B14, JDG-B2)
    ex = Stand(gaps=3)
    _run(tmp_path, ex)
    assert [ex.count("judge", "read_gap", g) for g in ("G1", "G2", "G3")] == [1, 1, 1]
    assert ex.count("judge", "discovery") == ex.count("step", "discovery") == 1  # one for the writing attempt


def test_a_reading_session_the_judge_does_not_accept_is_the_only_one_that_runs_again(tmp_path: Path) -> None:
    # AC 3, PRL-AC13 (PRL-B13)
    ex = Stand(gaps=3, unmet={"G2": 1})
    out = _run(tmp_path, ex)
    assert out is not None and out.exit_code is ExitCode.FINISHED, getattr(out, "message", None)
    assert [ex.count("step", "read_gap", g) for g in ("G1", "G2", "G3")] == [1, 2, 1]
    assert [ex.count("judge", "read_gap", g) for g in ("G1", "G2", "G3")] == [1, 2, 1]  # one for each attempt
    assert ex.count("judge", "discovery") == 1


def test_every_unit_with_a_model_session_has_one_judge() -> None:  # AC 3, PRL-AC14 (PRL-B14)
    for name, unit in SPEC.units.items():
        if unit.kind in ("step", "map"):
            assert isinstance(unit.gate.judge, JudgeSpec), name  # a gate holds one judge, not a list
    text = (ROOT / "docs" / "specs" / "parallel-reading.spec.md").read_text(encoding="utf-8")
    assert "- Judges of one gate." in text and "Default:" in text.split("- Judges of one gate.", 1)[1].split("\n- ")[0]


# -- the list of component folders (PRL-B4, PRL-B5) ----------------------------------------------------------------


def _folders(root: Path, names: list[str], *, files: tuple[str, ...] = ("README.txt",)) -> Path:
    for name in names:
        (root / name).mkdir(parents=True)
        for f in files:
            (root / name / f).write_text("x\n")
    (root / "loose.txt").write_text("a file, not a folder\n")
    return root


def _listed(root: Path) -> tuple[dict[str, str], list[dict[str, str]]]:
    got = routing.list_components(SimpleNamespace(workdir=root, unit="list_components", request={}))
    return got, json.loads((root / ".tempergraph" / "component_list.json").read_text(encoding="utf-8"))


def test_the_list_holds_the_component_folders_only_in_alphabetical_order(tmp_path: Path) -> None:
    # AC 2, PRL-AC4 (PRL-B4)
    _folders(tmp_path, ["tests", "src", "docs", "node_modules", ".github", ".venv", "venv", "vendor", "dist", "build",
                        "target", "out", "__pycache__"])
    got, items = _listed(tmp_path)
    assert got == {"component_list": ".tempergraph/component_list.json"}
    assert items == [{"id": "src", "text": "src"}, {"id": "tests", "text": "tests"}]
    assert (tmp_path / ".tempergraph" / ".gitignore").read_text(encoding="utf-8").strip() == "*"


def test_a_folder_name_outside_the_id_pattern_gets_a_cut_id_and_keeps_its_name(tmp_path: Path) -> None:
    # AC 2, PRL-AC4 (PRL-B4)
    long = "x" * 50
    _folders(tmp_path, ["my.package", long, "my-package"])
    _, items = _listed(tmp_path)
    by_text = {i["text"]: i["id"] for i in items}
    assert by_text["my.package"] != by_text["my-package"] and by_text[long] == "x" * 40
    pattern = re.compile(r"^[A-Za-z0-9][A-Za-z0-9_-]{0,39}$")
    assert all(pattern.match(i["id"]) for i in items) and len({i["id"] for i in items}) == 3


@pytest.mark.parametrize("names", [["src", "docs"], [], ["src"], ["docs", "node_modules", ".git"]])
def test_fewer_than_two_component_folders_give_an_empty_list(tmp_path: Path, names: list[str]) -> None:
    # AC 2, PRL-AC5 (PRL-B5)
    _folders(tmp_path, names)
    _, items = _listed(tmp_path)
    assert items == []


# -- the declarations of the setup survey (PRL-B6, PRL-B7) ---------------------------------------------------------


def test_the_setup_survey_is_a_list_script_and_a_concurrent_read_only_map() -> None:  # AC 2, PRL-AC6 (PRL-B6, PRL-B7)
    lister = SPEC.units["list_components"]
    assert lister.kind == "script" and lister.script is not None and 0 < len(lister.script.summary) <= 60
    assert set(lister.script.produces) == {"component_list"}
    unit = SPEC.units["read_component"]
    assert unit.kind == "map" and unit.map is not None and unit.step is not None
    assert unit.map.items_from == ("list_components", "component_list") and unit.map.extract is None
    assert (unit.map.mode, unit.map.concurrency, unit.map.on_empty) == ("concurrent", 3, "skip")
    assert sorted(unit.step.tools) == ["list", "read", "search"]  # no web, no write, no command
    assert set(unit.step.produces) == {"component_finding"}
    assert unit.step.produces["component_finding"].max_chars == 1500
    assert isinstance(unit.gate.judge, JudgeSpec) and unit.gate.check is None
    assert SPEC.order[:6] == ("prepare", "setup_route", "list_components", "read_component", "setup", "triage")
    assert set(SPEC.units["setup_route"].route_targets) == {"list_components", "triage"}
    setup = SPEC.units["setup"].step
    assert setup is not None and set(setup.produces) == {"overview", "setup_note"} and setup.tools


def test_the_component_prompts_brief_one_folder_and_take_the_findings() -> None:
    # AC 2, PRL-AC8, PRL-AC9, PRL-AC12
    reading = _prompt("read_component")
    assert "{item}" in reading and "{component_finding}" not in reading
    said = _said(reading)
    assert "only read" in said and "no file is written" in said
    assert "one line" in said and "1,500 characters" in said
    assert "line ranges or ids" in said and "what you searched" in said
    writing = _prompt("setup")
    assert "{component_finding}" in writing
    said = _said(writing)
    assert "a finding is a claim to confirm in the file it names before a spec rests on it" in said
    assert "survey" in said and "yourself" in said and "none" in said


# -- the setup step on stand-ins (PRL-B4, PRL-B5, PRL-B8, PRL-B11) -------------------------------------------------

REPOSITORY = {"src/a.py": "x = 1\n", "tests/test_a.py": "def test_a(): ...\n", "docs/guide.md": "# Guide\n",
              "node_modules/pkg/index.js": "1\n", ".github/ci.yml": "on: push\n"}


def test_setup_reads_each_component_folder_and_briefs_the_writer_in_folder_order(tmp_path: Path) -> None:
    # AC 2, PRL-AC4, PRL-AC8, PRL-AC11 (PRL-B4, PRL-B8, PRL-B11)
    ex = Stand(gaps=0, hold={"src": 0.3})  # `tests` ends first
    out = _run(tmp_path, ex, prepare=needed, files=REPOSITORY)
    assert out is not None and out.exit_code is ExitCode.FINISHED, getattr(out, "message", None)
    assert sorted(s["item"] for s in ex.sessions if (s["kind"], s["unit"]) == ("step", "read_component")) == [
        "src", "tests"]
    (prompt,) = ex.prompts("setup")
    lines = [ln for ln in prompt.splitlines() if re.match(r"(src|tests): ", ln)]
    assert lines == ["src: finding of src", "tests: finding of tests"]
    tests_brief = next(s["prompt"] for s in ex.sessions if (s["kind"], s["item"]) == ("step", "tests"))
    assert re.search(r"\btests\b", tests_brief) and not re.search(r"\bsrc\b", tests_brief)
    assert ex.count("step", "setup") == 1 and ex.count("step", "triage") == 1  # the run goes on to triage


@pytest.mark.parametrize("files", [{"src/a.py": "x\n", "docs/guide.md": "# Guide\n"}, {}])
def test_setup_of_fewer_than_two_component_folders_starts_no_reading_session(
        tmp_path: Path, files: dict[str, str]) -> None:  # AC 2, PRL-AC5 (PRL-B5)
    ex = Stand(gaps=0)
    out = _run(tmp_path, ex, prepare=needed, files=files)
    assert out is not None and out.exit_code is ExitCode.FINISHED, getattr(out, "message", None)
    assert ex.count("step", "read_component") == 0 and ex.count("step", "setup") == 1
    (prompt,) = ex.prompts("setup")
    assert not re.search(r"^\w+: finding of", prompt, re.M) and "none" in _said(prompt)
    assert ex.count("step", "triage") == 1  # the run goes on to triage


def test_each_component_reading_has_a_judge_session_and_only_the_refused_one_runs_again(tmp_path: Path) -> None:
    # AC 2, PRL-AC13, PRL-AC14 (PRL-B14)
    files = {f"{n}/a.txt": "x\n" for n in ("alpha", "beta", "gamma")}
    ex = Stand(gaps=0, unmet={"beta": 1})
    out = _run(tmp_path, ex, prepare=needed, files=files)
    assert out is not None and out.exit_code is ExitCode.FINISHED, getattr(out, "message", None)
    assert [ex.count("step", "read_component", n) for n in ("alpha", "beta", "gamma")] == [1, 2, 1]
    assert [ex.count("judge", "read_component", n) for n in ("alpha", "beta", "gamma")] == [1, 2, 1]
    assert ex.count("judge", "setup") == ex.count("step", "setup") == 1  # one for the one attempt of the writer


# -- one judge for each gate (PRL-B14) and the README ---------------------------------------------------------------


def test_every_gate_holds_one_judge_and_each_attempt_starts_one_judge_session(tmp_path: Path) -> None:
    # AC 3, PRL-AC14, PRL-AC13 (PRL-B13, PRL-B14)
    files = []
    for name, unit in SPEC.units.items():
        if unit.kind in ("step", "map"):
            judge = unit.gate.judge
            assert isinstance(judge, JudgeSpec), name  # one judge, not a list
            files.append(judge.file)
    assert len(files) == len(set(files)) and None not in files  # no judge file is shared by two units
    earlier = {"setup": ("medium", "medium", None), "triage": ("medium", "medium", None),
               "discovery_short": ("medium", "high", None), "discovery": ("medium", "high", None),
               "plan": ("medium", "high", None), "expand": ("medium", "medium", None),
               "code": ("medium", "high", 1800)}
    for name, want in earlier.items():
        judge = SPEC.units[name].gate.judge
        assert judge is not None and judge.session_options is not None
        assert (judge.model, judge.session_options.effort, judge.timeout_s) == want, name
    ex = Stand(gaps=3)
    out = _run(tmp_path, ex)
    assert out is not None and out.exit_code is ExitCode.FINISHED, getattr(out, "message", None)
    for unit in ("triage", "discovery"):
        assert ex.count("judge", unit) == ex.count("step", unit) >= 1, unit
    for item in ("G1", "G2", "G3"):
        assert ex.count("judge", "read_gap", item) == ex.count("step", "read_gap", item) == 1


def test_the_readme_names_the_reading_sessions_and_what_they_ask_of_the_engine() -> None:  # AC 3
    text = (ROOT / "README.md").read_text(encoding="utf-8")
    rows = {ln.split("|")[1].strip(): _said(ln) for ln in text.splitlines()
            if ln.startswith("| ") and ln.count("|") >= 4}
    for step in ("setup", "discovery"):
        assert "read-only" in rows[step] and "three at a time" in rows[step], step
    assert "component folder" in rows["setup"] and "each gap" in rows["discovery"]
    limits = _said(text.split("## Limits of this version", 1)[1].split("\n## ", 1)[0])
    assert "val-b9" in limits  # the need for a map's items in a later template
    assert "judges of one gate" in limits and "first values" in limits
    asks = _said(text.split("## What it asks of the engine", 1)[1])
    assert "map" in asks and "later template" in asks


# -- the records agree with the units -----------------------------------------------------------------------------


def _sizing(unit: str) -> dict[str, Any]:
    entry = next(u for u in json.loads((ROOT / "blueprint.json").read_text())["units"] if u["name"] == unit)
    return entry


def _check_unit_records(name: str, produces: list[str], judged: bool) -> None:
    entry = _sizing(name)
    assert entry["kind"] == "map" and entry["produces"] == produces
    assert entry["gate"] == {"check": False, "judge": True} and entry["on_budget_spent"] == "stop"
    step = SPEC.units[name].step
    judge = SPEC.units[name].gate.judge
    assert step is not None and judge is not None
    assert step.session_options is not None and judge.session_options is not None
    assert entry["sizing"] == {"model": step.model, "effort": step.session_options.effort, "why": step.sizing}
    assert entry["judge_sizing"] == {"model": judge.model, "effort": judge.session_options.effort, "why": judge.sizing}
    assert len(step.sizing.split()) >= 4 and len(judge.sizing.split()) >= 4
    assert (step.model, judge.model) == ("medium", "medium")
    criteria = OUTCOME["intermediate"][name]["criteria"]
    assert criteria and all(c["verified_by"] == "judge" for c in criteria)
    for c in criteria:
        assert not UNSEEN.search(c["text"] + " " + c.get("check_method", "")), c["id"]


def test_the_records_agree_with_the_gap_reading_unit() -> None:  # AC 5, PRL-AC13
    bp = bpm.read(ROOT / "blueprint.json")
    assert not isinstance(bp, list), bp
    assert compare(bp, SPEC, OUTCOME) == []
    _check_unit_records("read_gap", ["gap_finding"], True)
    flow = json.loads((ROOT / "blueprint.json").read_text())["flow"]
    assert flow["read_gap"] == {"map": {"over": "triage.triage_note"}}
    assert "read_gap" in flow["triage"]["route"] and "owner_questions" not in flow["triage"]["route"]
    assert "discovery" in flow["ask_route"]["route"] and "read_gap" in flow["discovery_short"]["route"]
    assert _sizing("discovery")["reads"] == ["answers", "gap_finding", "triage_note"]  # sorted, as compare.py reads it


def test_the_records_agree_with_the_setup_survey() -> None:  # AC 5, PRL-AC13
    bp = bpm.read(ROOT / "blueprint.json")
    assert not isinstance(bp, list), bp
    assert compare(bp, SPEC, OUTCOME) == []
    _check_unit_records("read_component", ["component_finding"], True)
    entry = json.loads((ROOT / "blueprint.json").read_text())
    units = {u["name"]: u for u in entry["units"]}
    assert not units["read_component"].get("reads") and units["setup"]["reads"] == ["component_finding"]
    assert units["list_components"]["kind"] == "script" and units["list_components"]["produces"] == ["component_list"]
    assert entry["flow"]["read_component"] == {"map": {"over": "list_components.component_list"}}
    assert entry["flow"]["setup_route"]["route"] == ["list_components", "triage"]


def test_diagram_files_follow_the_spec() -> None:  # AC 5, SCF-B16
    model = diagram_model(SPEC)
    path = ROOT / "diagram" / "model.json"
    try:
        have = json.loads(path.read_text(encoding="utf-8")).get("digest")
    except (OSError, ValueError):
        have = None
    drawn = "```mermaid\n" + to_mermaid(model) + "\n```\n"
    if have != model["digest"] or not (ROOT / "diagram" / "workflow.md").is_file() \
            or (ROOT / "diagram" / "workflow.md").read_text(encoding="utf-8") != drawn:
        write_json(path, model, mode=0o644)
        (ROOT / "diagram" / "workflow.md").write_text(drawn, encoding="utf-8")
    assert json.loads(path.read_text(encoding="utf-8"))["digest"] == model["digest"]
    assert (ROOT / "diagram" / "workflow.md").read_text(encoding="utf-8") == drawn
