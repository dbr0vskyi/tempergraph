"""The one pause after triage (spec `owner-questions`, OWQ-B1, OWQ-B2, OWQ-B5, OWQ-B7, OWQ-B8; task i63-64): the
declarations of the three units, stand-in runs that pause, keep partial answers, refuse a reading called `wrong`
and take the defaults at the deadline, and the records that agree with the units."""

from __future__ import annotations

import dataclasses
import importlib
import json
import sqlite3
import subprocess
import threading
from datetime import UTC, datetime, timedelta
from pathlib import Path
from typing import Any

from tempergraph.api import CheckResult
from tempergraph.author import blueprint as bpm
from tempergraph.author.compare import compare
from tempergraph.constants import ExitCode
from tempergraph.contracts import CallableRef, SessionRequest, SessionResult
from tempergraph.durability import engine_file
from tempergraph.executors.registry import Registry
from tempergraph.executors.standins import answer, standin
from tempergraph.package.loader import load_package
from tempergraph.run import asking
from tempergraph.run.runner import RunSettings, resume, start
from tempergraph.store.layout import run_dir, state_root_path

ROOT = Path(__file__).resolve().parents[1]
SPEC = load_package(ROOT).spec
OUTCOME = json.loads((ROOT / "outcome.json").read_text(encoding="utf-8"))
NAME = SPEC.name
TASK = "I-1"

HEAD = ("# Triage: I-1\n\n## Task\n\nThe task.\n\n## Acceptance criteria\n\n1. A thing.\n\n## Existing documents\n\n"
        "- none\n\n## Gaps\n\n")


def _row(n: int, sort: str, covered: bool = False) -> str:
    kind = "decision needed" if sort == "Owner decision" else "spec gap"
    cover = " Covered by SES-B1 and SES-AC1." if covered else ""
    return f"- G{n} {kind}: subject {n}.{cover} {sort}\n"


def _entry(n: int) -> str:
    return (f"- G{n}: Which way for subject {n}?\n  - Options: a) left; b) right\n  - Default: a\n"
            f"  - If wrong: cost {n}\n")


def _note(rows: str, owner: str, route: str = "discovery-only") -> str:
    return HEAD + (rows or "None\n") + f"\n## Owner decisions\n\n{owner}\n## Route\n\n- Deliver: docs\n- Route: {route}\n"


THREE = _note("".join(_row(n, "Owner decision") for n in (1, 2, 3)), "".join(_entry(n) for n in (1, 2, 3)))
READINGS = _note(_row(1, "Findable") + _row(2, "Findable"), "None\n")
MIXED = _note(_row(1, "Findable") + _row(2, "Owner decision"), _entry(2))


# -- the harness: stand-in sessions by the unit of the session key --------------------------------------------------


class Stop(AssertionError):
    """The stand-in ends the run where the test has seen what it needs."""


class Stand:
    """A stand-in executor that writes the given triage note and counts the sessions of each unit."""

    def __init__(self, note: str, *, route: str = "discovery-only", covered: str = "no") -> None:
        self.inner = standin("claude")
        self.name = self.inner.name
        self.note, self.route, self.covered = note, route, covered
        self.lock = threading.Lock()
        self.sessions: list[tuple[str, str, str | None]] = []

    def __getattr__(self, name: str) -> Any:
        return getattr(self.inner, name)

    def count(self, unit: str, kind: str = "step") -> int:
        return sum(1 for k, u, _ in self.sessions if (k, u) == (kind, unit))

    @staticmethod
    def _whose(req: SessionRequest) -> tuple[str, str | None]:
        parts = req.session_key.split(".")
        return parts[0], (parts[1] if parts[0] == "read_gap" and len(parts) > 1 else None)

    def run_step(self, req: SessionRequest, sink: Any) -> SessionResult:
        unit, item = self._whose(req)
        with self.lock:
            self.sessions.append(("step", unit, item))
        work = Path(req.workdir)
        if unit == "triage":
            (work / "docs" / "tasks").mkdir(parents=True, exist_ok=True)
            path = f"docs/tasks/{TASK}.triage.md"
            (work / path).write_text(self.note, encoding="utf-8")
            some = "none" if "None\n\n## Owner" in self.note else "some"
            return answer(f"Triaged.\nARTIFACT triage_note: {path}\nARTIFACT gaps: {some}\nARTIFACT route: {self.route}\n"
                          f"ARTIFACT covered: {self.covered}", session_id="s-triage")
        if unit == "read_gap":
            return answer(f"Read.\nARTIFACT gap_finding: finding of {item}", session_id=f"s-read-{item}")
        if unit == "discovery":
            (work / "docs" / "tasks").mkdir(parents=True, exist_ok=True)
            path = f"docs/tasks/{TASK}.handoff.md"
            (work / path).write_text(f"# Hand-off: {TASK}\n", encoding="utf-8")
            return answer(f"Closed the gaps.\nARTIFACT handoff: {path}", session_id="s-discovery")
        raise Stop(f"{unit} reached")

    def run_judge(self, req: SessionRequest, views: Any, sink: Any) -> SessionResult:
        unit, item = self._whose(req)
        with self.lock:
            self.sessions.append(("judge", unit, item))
        rows = [{"n": i, "status": "MET", "evidence": "stand-in", "defect_in": None, "no_change": False}
                for i in range(1, max(len(SPEC.units[unit].gate.criteria), 1) + 1)]
        text = "Reviewed.\n```json\n" + json.dumps({"criteria": rows, "gap": False, "confidence": 0.9}) + "\n```"
        return answer(text, tools=("Read",), session_id=f"j-{unit}-{item}")


def ready(ctx: Any) -> dict[str, str]:
    return {"setup_ready": "yes"}


def passes(ctx: Any) -> CheckResult:
    return CheckResult(result="PASS", evidence="stand-in")


def _spec() -> Any:
    """The package's spec with `prepare` ready, a passing check on each gate that has one (the answers check of
    `ask_owner` stays as it is) and no outcome gate."""
    units = {}
    for name, u in SPEC.units.items():
        check = CallableRef(module=__name__, qualname="passes", func=passes) if u.gate.check is not None else None
        units[name] = dataclasses.replace(u, gate=dataclasses.replace(u.gate, check=check))
    script = dataclasses.replace(SPEC.units["prepare"].script, run=None,
                                 call=CallableRef(module=__name__, qualname="ready", func=ready))
    units["prepare"] = dataclasses.replace(units["prepare"], script=script)
    return dataclasses.replace(SPEC, units=units, outcome=None)


def _repo(root: Path) -> Path:
    root.mkdir(parents=True, exist_ok=True)

    def git(*args: str) -> None:
        subprocess.run(["git", "-c", "user.name=t", "-c", "user.email=t@example.invalid", *args], cwd=root,
                       check=True, capture_output=True)

    git("init", "-q", "-b", "main")
    (root / "README.md").write_text("scratch\n")
    git("add", "-f", "-A")
    git("commit", "-q", "-m", "start")
    return root


def _registry(ex: Stand) -> Registry:
    reg = Registry()
    reg.register(ex)
    return reg


def _begin(repo: Path, ex: Stand, conversation: str = "blocking", **flags: Any) -> Any:
    settings = RunSettings(sleep=lambda s: None, flags={"code_mode.arm": "single",
                                                        "settings.conversation": conversation, **flags})
    try:
        return start(_spec(), TASK, {"request": "x"}, repo, _registry(ex), settings)
    except Stop:
        return None


def _again(repo: Path, ex: Stand, **kw: Any) -> Any:
    try:
        return resume(_spec(), TASK, repo, _registry(ex), settings=RunSettings(sleep=lambda s: None, **kw))
    except Stop:
        return None


def _records(repo: Path, kind: str) -> list[dict[str, Any]]:
    path = run_dir(state_root_path(repo), NAME, TASK) / "run.jsonl"
    return [r for r in map(json.loads, path.read_text().splitlines()) if r["kind"] == kind]


def _answers_file(repo: Path) -> dict[str, Any]:
    return json.loads(asking.answers_path(run_dir(state_root_path(repo), NAME, TASK), "ask_owner").read_text())


def _expire(repo: Path) -> None:
    """Move the pause's deadline into the past, as a day going by would."""
    db = engine_file.checkpoint_of(state_root_path(repo), NAME, TASK)
    past = (datetime.now(UTC) - timedelta(days=1)).isoformat(timespec="seconds")
    con = sqlite3.connect(db)
    try:
        for table, col in (("writes", "value"), ("checkpoints", "checkpoint")):
            for rowid, blob in con.execute(f"select rowid, {col} from {table}").fetchall():  # noqa: S608
                if isinstance(blob, bytes) and b"deadline_at" in blob:
                    start_at = blob.index(b"deadline_at")
                    at = blob.index(b"20", start_at)
                    con.execute(f"update {table} set {col} = ? where rowid = ?",  # noqa: S608
                                (blob[:at] + past.encode() + blob[at + len(past):], rowid))
        con.commit()
    finally:
        con.close()


def _names(out: Any) -> list[str]:
    return [q["name"] for q in out.payload["questions"]]


# -- OWQ-AC7: what the units declare --------------------------------------------------------------------------------


def test_owq_ac7_the_three_units_are_declared_after_the_reading_and_before_the_writing_session() -> None:  # AC 5
    questions, route, ask = (SPEC.units[n] for n in ("owner_questions", "ask_route", "ask_owner"))
    assert questions.kind == "script" and questions.script is not None and questions.script.call is not None
    assert set(questions.script.produces) == {"question_list", "empty"}
    assert route.kind == "route" and set(SPEC.units["ask_route"].route_targets) == {"ask_owner", "discovery"}
    assert ask.kind == "ask" and ask.ask is not None
    assert ask.ask.questions_from == "question_list" and tuple(ask.ask.context) == ("triage_note",)
    assert (ask.ask.deadline_s, ask.ask.on_deadline) == (86400, "defaults") and ask.ask.check is not None
    for unit in SPEC.units.values():
        assert not unit.gate.approval  # no gate asks for an approval: the one pause is the ask
    order = list(SPEC.order)
    assert order.index("discovery_short") < order.index("read_gap") < order.index("owner_questions")
    assert order.index("owner_questions") < order.index("ask_route") < order.index("ask_owner") < order.index("discovery")
    assert "read_gap" in SPEC.units["triage"].route_targets and "owner_questions" not in SPEC.units["triage"].route_targets


# -- OWQ-AC1, OWQ-AC2: one pause, with the questions of the note ------------------------------------------------------


def test_owq_ac1_a_note_with_three_owner_decisions_pauses_once_with_three_questions(tmp_path: Path) -> None:  # AC 2
    ex = Stand(THREE)
    out = _begin(_repo(tmp_path / "r"), ex)
    assert out is not None and out.exit_code is ExitCode.PAUSED and out.payload["kind"] == "input", out
    assert _names(out) == ["g1", "g2", "g3"] and out.payload["questions"][0]["choices"] == ["a", "b"]
    assert ex.count("read_gap") == 3 and ex.count("discovery") == 0  # the reading is done, nothing is written yet
    assert len(_records(tmp_path / "r", "pause")) == 1


def test_owq_ac1_two_of_three_answers_leave_the_pause_open_for_the_third(tmp_path: Path) -> None:  # AC 2, AC 4
    repo, ex = _repo(tmp_path / "r"), Stand(THREE)
    _begin(repo, ex)
    held = _again(repo, ex, answers={"g1": "b", "g2": "a"})
    assert held is not None and held.exit_code is ExitCode.PAUSED and held.payload["missing"] == ["g3"]
    assert _answers_file(repo)["answers"] == {"g1": "b", "g2": "a"} and ex.count("discovery") == 0
    done = _again(repo, ex, answers={"g3": "b"})
    assert done is not None and done.exit_code is ExitCode.FINISHED, getattr(done, "message", None)
    assert _answers_file(repo)["answers"] == {"g1": "b", "g2": "a", "g3": "b"} and ex.count("discovery") == 1


def test_owq_ac2_always_with_no_owner_decision_and_two_findable_gaps_pauses_once_with_two(tmp_path: Path) -> None:
    # AC 3
    ex = Stand(READINGS)
    out = _begin(_repo(tmp_path / "r"), ex, "always")
    assert out is not None and out.exit_code is ExitCode.PAUSED, out
    assert _names(out) == ["g1", "g2"] and out.payload["questions"][0]["choices"] == ["right", "wrong"]


def test_owq_ac2_blocking_asks_the_decisions_only_and_always_adds_the_readings(tmp_path: Path) -> None:  # AC 3
    blocking = _begin(_repo(tmp_path / "b"), Stand(MIXED), "blocking")
    always = _begin(_repo(tmp_path / "a"), Stand(MIXED), "always")
    assert _names(blocking) == ["g2"] and _names(always) == ["g2", "g1"]


def test_owq_ac2_blocking_with_none_pauses_nowhere_and_reaches_the_reading(tmp_path: Path) -> None:  # AC 2
    ex = Stand(READINGS)
    out = _begin(_repo(tmp_path / "r"), ex, "blocking")
    assert out is not None and out.exit_code is ExitCode.FINISHED, getattr(out, "message", None)
    assert ex.count("read_gap") == 2 and ex.count("discovery") == 1 and _records(tmp_path / "r", "pause") == []


def test_owq_ac2_never_with_owner_decisions_pauses_nowhere(tmp_path: Path) -> None:  # AC 2
    ex = Stand(THREE)
    out = _begin(_repo(tmp_path / "r"), ex, "never")
    assert out is not None and out.exit_code is ExitCode.FINISHED, getattr(out, "message", None)
    assert ex.count("read_gap") == 3 and _records(tmp_path / "r", "pause") == []


def test_owq_ac2_always_with_no_gap_or_only_covered_gaps_pauses_nowhere(tmp_path: Path) -> None:  # AC 3
    none = Stand(_note("", "None\n"))
    out = _begin(_repo(tmp_path / "none"), none, "always")
    assert out is not None and out.exit_code is ExitCode.FINISHED, getattr(out, "message", None)
    assert none.count("discovery") == 1 and _records(tmp_path / "none", "pause") == []
    covered = Stand(_note(_row(1, "Findable", True) + _row(2, "Findable", True), "None\n"))
    out = _begin(_repo(tmp_path / "cov"), covered, "always")
    assert out is not None and out.exit_code is ExitCode.FINISHED, getattr(out, "message", None)
    assert covered.count("read_gap") == 2 and _records(tmp_path / "cov", "pause") == []


def test_owq_ac2_the_other_routes_of_triage_pause_nowhere(tmp_path: Path) -> None:  # AC 2
    short = Stand(THREE, route="discovery", covered="yes")  # the short visit: no owner list, no pause
    _begin(_repo(tmp_path / "short"), short)
    assert short.count("discovery_short") >= 1 and short.count("read_gap") == 0
    assert _records(tmp_path / "short", "pause") == []
    plan = Stand(_note("", "None\n", "plan"), route="plan")
    _begin(_repo(tmp_path / "plan"), plan)
    assert plan.count("plan") >= 1 and _records(tmp_path / "plan", "pause") == []
    quick = Stand(_note("", "None\n", "quick"), route="quick")
    _begin(_repo(tmp_path / "quick"), quick)
    assert quick.count("code") >= 1 and _records(tmp_path / "quick", "pause") == []


# -- OWQ-AC5, OWQ-AC7, OWQ-AC8: a reading called wrong, and the deadline ----------------------------------------------


def _deadline_s(out: Any) -> float:
    return (datetime.fromisoformat(out.payload["deadline_at"]) - datetime.now(UTC)).total_seconds()


def test_owq_ac7_the_pause_shows_a_deadline_of_a_day_or_the_seconds_set(tmp_path: Path) -> None:  # AC 5
    out = _begin(_repo(tmp_path / "day"), Stand(THREE))
    assert out.payload["on_deadline"] == "defaults" and 86400 - 120 < _deadline_s(out) <= 86400
    short = _begin(_repo(tmp_path / "set"), Stand(THREE), **{"ask_owner.deadline_s": 3600})
    assert 3600 - 120 < _deadline_s(short) <= 3600


def test_owq_ac8_applying_the_deadline_before_it_is_refused_with_exit_code_2(tmp_path: Path) -> None:  # AC 5
    repo, ex = _repo(tmp_path / "r"), Stand(THREE)
    _begin(repo, ex)
    early = _again(repo, ex, apply_deadline=True)
    assert early is not None and early.exit_code is ExitCode.USAGE and early.reason == "deadline_not_passed"
    assert ex.count("discovery") == 0


def test_owq_ac8_after_the_deadline_the_run_goes_on_with_the_answers_and_the_defaults(tmp_path: Path) -> None:  # AC 5
    repo, ex = _repo(tmp_path / "r"), Stand(THREE)
    _begin(repo, ex)
    _again(repo, ex, answers={"g2": "b"})
    _expire(repo)
    done = _again(repo, ex, apply_deadline=True)
    assert done is not None and done.exit_code is ExitCode.FINISHED, getattr(done, "message", None)
    file = _answers_file(repo)
    assert file["answers"] == {"g1": "a", "g2": "b", "g3": "a"} and file["defaulted"] == ["g1", "g3"]
    assert ex.count("read_gap") == 3 and ex.count("discovery") == 1


def test_owq_ac5_a_reading_called_wrong_keeps_the_pause_open_also_after_the_deadline(tmp_path: Path) -> None:  # AC 3
    repo, ex = _repo(tmp_path / "r"), Stand(MIXED)
    first = _begin(repo, ex, "always")
    assert _names(first) == ["g2", "g1"]
    held = _again(repo, ex, answers={"g2": "b", "g1": "wrong"})
    assert held is not None and held.exit_code is ExitCode.PAUSED
    assert any("G1" in p for p in held.payload["check_problems"]) and ex.count("discovery") == 0
    _expire(repo)
    late = _again(repo, ex, apply_deadline=True)
    assert late is not None and late.exit_code is ExitCode.PAUSED
    assert any("G1" in p for p in late.payload["check_problems"]) and ex.count("discovery") == 0
    done = _again(repo, ex, answers={"g1": "right"})
    assert done is not None and done.exit_code is ExitCode.FINISHED, getattr(done, "message", None)
    assert _answers_file(repo)["answers"] == {"g2": "b", "g1": "right"}


# -- AC 7: the records agree with the units ---------------------------------------------------------------------------


def test_the_records_agree_with_the_three_units() -> None:  # AC 7
    bp = bpm.read(ROOT / "blueprint.json")
    assert not isinstance(bp, list), bp
    assert compare(bp, SPEC, OUTCOME) == []
    data = json.loads((ROOT / "blueprint.json").read_text(encoding="utf-8"))
    units = {u["name"]: u for u in data["units"]}
    assert units["owner_questions"]["kind"] == "script"
    assert sorted(units["owner_questions"]["produces"]) == ["empty", "question_list"]
    assert units["ask_route"]["kind"] == "route" and units["ask_owner"]["kind"] == "ask"
    assert "answers" in units["ask_owner"]["produces"]
    flow = data["flow"]
    assert "read_gap" in flow["triage"]["route"] and "owner_questions" not in flow["triage"]["route"]
    assert sorted(flow["ask_route"]["route"]) == ["ask_owner", "discovery"]
    decisions = json.loads((ROOT / "authoring.json").read_text(encoding="utf-8"))["decisions"]
    text = json.dumps(decisions)
    for unit in ("owner_questions", "ask_route", "ask_owner"):
        assert unit in text, unit


def test_the_diagram_names_the_three_units() -> None:  # AC 7
    drawn = (ROOT / "diagram" / "workflow.md").read_text(encoding="utf-8")
    for unit in ("owner_questions", "ask_route", "ask_owner"):
        assert unit in drawn, unit
