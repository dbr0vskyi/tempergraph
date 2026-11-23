"""A contest runs on stand-in executors: slots in their own state, each check before its judge, one-candidate judges and
the pick by the fixed rule (CTS-AC2, CTS-AC3; CTS-B1, CTS-B2, CTS-B3, CTS-B6, CTS-B7, EVT-B15)."""

from __future__ import annotations

import dataclasses
import json
import threading
import time
from pathlib import Path
from typing import Any

from tempergraph.api import CheckResult, Contest, Gate, Judge, Routing, Slot, Step, Value, Workflow
from tempergraph.constants import ExitCode
from tempergraph.contracts import CheckFinding, InfraCause, SessionRequest, SessionResult, Usage, WorkflowSpec
from tempergraph.executors.standins import answer, standin
from tempergraph.run.runner import RunSettings, start
from tempergraph.store.layout import run_dir, state_root_path

from .fixtures.workflows import crit, named
from .test_run import registry

NO_SLEEP = RunSettings(sleep=lambda s: None)


def block(*statuses: str, confidence: float = 0.8) -> str:
    """A judge's answer grading the criteria in order: `MET`, `UNMET` and the other statuses."""
    rows = [{"n": i, "status": s, "evidence": "note.md:1 shows it" if s == "MET" else "missing", "defect_in": None,
             "no_change": False} for i, s in enumerate(statuses, 1)]
    return "Reviewed.\n```json\n" + json.dumps({"criteria": rows, "gap": False, "confidence": confidence}) + "\n```"


BOTH_MET = block("MET", "MET")
ONE_WARNING = block("MET", "UNMET")  # the warning criterion unmet: PROCEED with one unmet warning
BLOCKED = block("UNMET", "MET")  # the blocker unmet: RETRY


def fails_s2(ctx: Any) -> CheckResult:
    """The gate's check: slot `s2` fails it, every other slot passes."""
    if ctx.item == "s2":
        return CheckResult(result="FAIL", evidence="s2 is wrong", findings=[
            CheckFinding(status="fail", criterion="c-main", message="not there")])
    return CheckResult(result="PASS", evidence="ok", facts={"seen": str(ctx.item)})


def fails_all(ctx: Any) -> CheckResult:
    return CheckResult(result="FAIL", evidence=f"{ctx.item} is wrong", findings=[
        CheckFinding(status="fail", criterion="c-main", message=f"{ctx.item} not there")])


class BySlot:
    """A stand-in that answers by slot: a step writes `<slot>-done` as its `note`, a judge takes its slot's next answer
    from `judges` (every slot's judge has `BOTH_MET` otherwise), each session costs what `costs` says (`step_cost`
    otherwise), a session may be held for a moment so that sessions overlap, and the sessions open at once are counted."""

    def __init__(self, *, hold_s: float = 0.0, judges: dict[str, list[str]] | None = None,
                 costs: dict[str, float] | None = None, step_cost: float = 0.01, judge_cost: float = 0.01,
                 touch: dict[str, str] | None = None, infra: set[str] | None = None) -> None:
        self.inner = standin("claude")
        self.name = self.inner.name
        self.hold_s = hold_s
        self.judges = {k: list(v) for k, v in (judges or {}).items()}
        self.costs, self.step_cost, self.judge_cost = costs or {}, step_cost, judge_cost
        self.touch = touch or {}  # slot -> a file its step writes in its working directory
        self.infra = infra or set()  # slots whose step sessions fail on infrastructure
        self.lock = threading.Lock()
        self.open = 0
        self.peak = 0
        self.timeline: list[tuple[str, str, str, float]] = []  # (event, kind, slot, time)
        self.requests: list[SessionRequest] = []
        self.sessions: dict[str, int] = {}

    def __getattr__(self, name: str) -> Any:
        return getattr(self.inner, name)

    @staticmethod
    def whose(req: SessionRequest) -> str:
        """The slot of a contest's session (`pick.s1.1.step`), else the unit's own name (`plan.1.step`)."""
        parts = req.session_key.split(".")
        return parts[1] if len(parts) >= 4 else parts[0]

    def _enter(self, kind: str, req: SessionRequest) -> str:
        slot = self.whose(req)
        with self.lock:
            self.open += 1
            self.peak = max(self.peak, self.open)
            self.requests.append(req)
            self.timeline.append(("start", kind, slot, time.monotonic()))
            self.sessions[f"{kind}.{slot}"] = self.sessions.get(f"{kind}.{slot}", 0) + 1
        return slot

    def _leave(self, kind: str, slot: str) -> None:
        with self.lock:
            self.open -= 1
            self.timeline.append(("end", kind, slot, time.monotonic()))

    def run_step(self, req: SessionRequest, sink: Any) -> SessionResult:
        slot = self._enter("step", req)
        try:
            if self.hold_s:
                time.sleep(self.hold_s)
            name = self.touch.get(slot)
            if name:
                (Path(req.workdir) / name).write_text(f"written by {slot}\n")
            if slot in self.infra:
                return SessionResult(ok=False, infra_cause=InfraCause.BROKEN_PIPE, usage=Usage())
            if self.whose(req) == "plan":
                return answer("Planned.\nARTIFACT doc: the-plan", session_id="s-plan")
            return answer(f"Did {slot}.\nARTIFACT note: {slot}-done", session_id=f"s-{slot}",
                          cost=self.costs.get(slot, self.step_cost))
        finally:
            self._leave("step", slot)

    def run_judge(self, req: SessionRequest, views: Any, sink: Any) -> SessionResult:
        slot = self._enter("judge", req)
        try:
            with self.lock:
                queue = self.judges.get(slot) or []
                text = queue.pop(0) if queue else BOTH_MET
            return answer(text, tools=("Read",), session_id=f"j-{slot}", cost=self.judge_cost)
        finally:
            self._leave("judge", slot)

    def kinds(self, slot: str) -> list[str]:
        return [k for e, k, s, _ in self.timeline if e == "start" and s == slot]


def contest_spec(*, slots: Any = 3, check: Any = None, retry_budget: int = 2, then: bool = True,
                 run_cost_cap_usd: float | None = None, plan: bool = False, gate: dict[str, Any] | None = None,
                 **fields: Any) -> WorkflowSpec:
    """A contest of `slots` whose gate has a blocker and a warning criterion, followed by a step that reads its `note`;
    with `plan`, a step `plan` producing `doc` comes first and the contest's gate may send a defect back to it."""
    step = Step(prompt="Draft {request}", tools=["read"], produces={"note": Value()},
                gate=Gate(check=check, judge=Judge(stance="V."),
                          criteria=[crit("c-main"), crit("c-style", severity="warning")], retry_budget=retry_budget,
                          **(gate or {})))
    units: dict[str, Any] = {}
    if plan:
        units["plan"] = Step(prompt="Plan {request}", tools=["read"], produces={"doc": Value()},
                             gate=Gate(judge=Judge(stance="V."), criteria=[crit("c-plan")]))
    units["pick"] = Contest(step=step, slots=slots, **fields)
    if then:
        units["after"] = Step(prompt="Summarise {note}", tools=["read"], gate=Gate(
            judge=Judge(stance="V."), criteria=[crit("c-after")]))
    spec = named(Workflow(order=list(units), units=units, issue_repository="acme/x",
                          routing=Routing(description="Best of n")))
    return dataclasses.replace(spec, run_cost_cap_usd=run_cost_cap_usd)


def go(repo: Path, spec: WorkflowSpec, ex: Any, task: str = "C-1", **kw: Any) -> Any:
    return start(spec, task, {"request": "the task"}, repo, registry(ex), dataclasses.replace(NO_SLEEP, **kw))


def recs(repo: Path, kind: str, task: str = "C-1") -> list[dict[str, Any]]:
    p = run_dir(state_root_path(repo), "demo", task) / "run.jsonl"
    return [r for r in map(json.loads, p.read_text().splitlines()) if r["kind"] == kind]


def test_three_slots_run_each_graded_by_its_own_judge_and_the_pick_is_the_rule_s(repo: Path) -> None:  # CTS-AC2 (CTS-B1, CTS-B7)
    ex = BySlot(judges={"s1": [BLOCKED], "s2": [ONE_WARNING], "s3": [BOTH_MET]}, costs={"s1": 0.1, "s2": 0.2, "s3": 0.3})
    out = go(repo, contest_spec(), ex)
    assert out.exit_code is ExitCode.FINISHED, out.message
    starts = sorted(r.session_key for r in ex.requests)
    assert {k for k in starts if k.startswith("pick.")} == {f"pick.s{n}.1.{kind}" for n in (1, 2, 3)
                                                             for kind in ("step", "judge")}  # slots s1 to s3 (CTS-B6)
    (rec,) = recs(repo, "contest")
    assert (rec["unit"], rec["winner"]) == ("pick", 3)  # PROCEED with no unmet warning beats the one with a warning
    by = {s["name"]: s for s in rec["slots"]}
    assert [s["slot"] for s in rec["slots"]] == [1, 2, 3] and all(isinstance(s["slot"], int) for s in rec["slots"])
    assert (by["s1"]["verdict"], by["s2"]["verdict"], by["s3"]["verdict"]) == ("RETRY", "PROCEED", "PROCEED")
    assert by["s2"]["keys"] == {"unmet_warnings": 1, "met": 1, "confidence": 0.8}
    assert by["s3"]["keys"] == {"unmet_warnings": 0, "met": 2, "confidence": 0.8}
    assert by["s1"]["check"] == "PASS" or by["s1"]["check"] is None  # no check declared: none ran
    assert round(by["s3"]["cost"], 6) == 0.31 and round(by["s1"]["cost"], 6) == 0.11  # the slot's step and its judge
    gate = [g for g in recs(repo, "gate") if g["unit"] == "pick"]
    assert [(g["verdict"], g["token"]) for g in gate] == [("PROCEED", "PROCEED")]  # the winner's verdict is the unit's
    nxt = next(r for r in ex.requests if r.session_key == "after.1.step")
    assert "s3-done" in nxt.prompt and "s1-done" not in nxt.prompt and "s2-done" not in nxt.prompt  # the winner's artifacts


def test_every_slot_runs_in_its_own_state_with_its_own_keys(repo: Path) -> None:  # CTS-AC2 (CTS-B6)
    ex = BySlot()
    out = go(repo, contest_spec(slots=[Slot("fast", model="small"), Slot("deep", model="large")]), ex)
    assert out.exit_code is ExitCode.FINISHED, out.message
    keys = sorted(r.session_key for r in ex.requests if r.session_key.startswith("pick."))
    assert keys == ["pick.deep.1.judge", "pick.deep.1.step", "pick.fast.1.judge", "pick.fast.1.step"]
    assert {r.session_key: r.alias for r in ex.requests if r.session_key.endswith(".step") and r.session_key.startswith(
        "pick.")} == {"pick.fast.1.step": "small", "pick.deep.1.step": "large"}  # each slot's own model
    (rec,) = recs(repo, "contest")
    assert [s["name"] for s in rec["slots"]] == ["fast", "deep"] and rec["winner"] == 1  # a tie goes to the earlier slot


def test_a_slot_prompt_variant_is_appended_under_its_heading(repo: Path) -> None:  # CTS-AC2 (CTS-B6)
    ex = BySlot()
    spec = contest_spec(slots=[Slot("a"), Slot("b", prompt_variant="Start from the failing test.")])
    assert go(repo, spec, ex).exit_code is ExitCode.FINISHED
    prompts = {r.session_key: r.prompt for r in ex.requests}
    assert "Approach for this attempt" in prompts["pick.b.1.step"] and "Start from the failing test." in prompts[
        "pick.b.1.step"]
    assert "Approach for this attempt" not in prompts["pick.a.1.step"]


def test_a_slot_whose_check_fails_gets_no_judge_session(repo: Path) -> None:  # CTS-AC2 (CTS-B2)
    ex = BySlot(judges={"s1": [ONE_WARNING], "s3": [BOTH_MET]})
    out = go(repo, contest_spec(check=fails_s2), ex)
    assert out.exit_code is ExitCode.FINISHED, out.message
    assert ex.kinds("s2") == ["step"]  # the check ran after its step, and no judge session started for it
    assert ex.kinds("s1") == ["step", "judge"] and ex.kinds("s3") == ["step", "judge"]
    checks = {c["item"]: c["result"] for c in recs(repo, "check") if c["unit"] == "pick"}
    assert checks == {"s1": "PASS", "s2": "FAIL", "s3": "PASS"}
    (rec,) = recs(repo, "contest")
    by = {s["name"]: s for s in rec["slots"]}
    assert (by["s2"]["check"], by["s2"]["verdict"], by["s2"]["keys"]) == ("FAIL", None, None)
    assert rec["winner"] == 3  # the one with no unmet warning among the two that passed their check
    ends = {(k, s): t for e, k, s, t in ex.timeline if e == "end"}
    started = {(k, s): t for e, k, s, t in ex.timeline if e == "start"}
    assert ends[("step", "s1")] <= started[("judge", "s1")]  # a slot's step ends before its judge starts


def test_the_judge_of_one_slot_sees_that_slot_only_CTS_AC3(repo: Path) -> None:  # CTS-AC3 (CTS-B3)
    ex = BySlot(judges={"s1": [BOTH_MET], "s2": [BOTH_MET], "s3": [BOTH_MET]}, costs={"s1": 0.31, "s2": 0.32, "s3": 0.33})
    out = go(repo, contest_spec(), ex)
    assert out.exit_code is ExitCode.FINISHED, out.message
    prompts = {BySlot.whose(r): r.prompt for r in ex.requests if r.session_key.endswith(".judge") and r.session_key.startswith(
        "pick.")}
    assert set(prompts) == {"s1", "s2", "s3"}
    for mine, text in prompts.items():
        assert f"{mine}-done" in text and f"Did {mine}." in text  # its own artifact and its own account
        for other in set(prompts) - {mine}:
            assert f"{other}-done" not in text and f"Did {other}." not in text, (mine, other)  # no other slot's text
            assert f"0.3{other[1]}" not in text  # and no other slot's score or cost


def test_the_judge_of_the_second_slot_holds_nothing_of_the_first_CTS_AC3(repo: Path) -> None:  # CTS-AC3 (CTS-B3)
    ex = BySlot()
    assert go(repo, contest_spec(slots=2), ex).exit_code is ExitCode.FINISHED
    judge_of = {BySlot.whose(r): r.prompt for r in ex.requests if r.session_key.endswith(".judge") and
                r.session_key.startswith("pick.")}
    assert "s1-done" not in judge_of["s2"] and "Did s1." not in judge_of["s2"]  # the reverse of the first test
    assert "s2-done" not in judge_of["s1"] and "Did s2." not in judge_of["s1"]


def test_the_contest_run_record_holds_every_slot_and_the_winner_EVT_B15(repo: Path) -> None:  # CTS-AC2 (CTS-B7, EVT-B15)
    ex = BySlot(judges={"s1": [BLOCKED]}, costs={"s1": 0.5})
    assert go(repo, contest_spec(slots=2), ex).exit_code is ExitCode.FINISHED
    (rec,) = recs(repo, "contest")
    assert set(rec) >= {"unit", "visit", "attempt", "winner", "slots"}
    assert rec["winner"] == 2 and [s["slot"] for s in rec["slots"]] == [1, 2]
    assert set(rec["slots"][0]) >= {"slot", "name", "check", "verdict", "keys", "cost"}
