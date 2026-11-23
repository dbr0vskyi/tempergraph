"""A council runs: its sessions, keys, barrier and crash resume (CNL-B13 to CNL-B15, CNL-AC4; task AC 4)."""

from __future__ import annotations

import dataclasses
import json
import threading
import time
from collections import Counter
from collections.abc import Callable
from pathlib import Path
from typing import Any

import pytest

from tempergraph.api import Chair, Council, Gate, Judge, Member, Routing, Workflow
from tempergraph.constants import ExitCode
from tempergraph.contracts import SessionRequest, SessionResult
from tempergraph.executors.standins import answer, standin
from tempergraph.run.runner import RunSettings, resume, start
from tempergraph.store.layout import run_dir, state_root_path

from .fixtures.workflows import crit, named
from .test_run import MET, registry

NO_SLEEP = RunSettings(sleep=lambda s: None)
UNIT = "decide"


def blk(position: str = "queue", *, choice: str | None = None, ranking: list[str] | None = None,
        confidence: float = 0.7, round: int = 0, changed: bool = False, dissent: str = "") -> str:
    """An answer with its fenced JSON block (CNL-B11)."""
    doc: dict[str, Any] = {"position": position, "confidence": confidence}
    if choice is not None:
        doc["choice"] = choice
    if ranking is not None:
        doc["ranking"] = ranking
    if round >= 1:
        doc.update(changed=changed, why_changed="because" if changed else "held", dissent=dissent)
    return f"My view on {position}.\n```json\n{json.dumps(doc)}\n```\n"


def chair_text(dissent: str = "A and B differ on cost") -> str:
    return f"Synthesis.\n```json\n{json.dumps({'dissent': dissent})}\n```\n"


Reply = str | SessionResult | Callable[[SessionRequest], SessionResult | str]


class Crew:
    """A stand-in that answers by session key: a member by `(name, round)`, the chair, and the judge. The sessions of one
    round run at once, so each reply is found by the key and never by the order of the calls. `script` holds, per
    `(member, round)`, a list of replies consumed one per session of that key's member and round (a re-ask takes the
    next)."""

    scripted = True

    def __init__(self, script: dict[tuple[str, int], list[Reply]] | None = None, *, chair: Reply | list[Reply] | None = None,
                 judges: list[str] | None = None, default: Callable[[str, int], str] | None = None,
                 hold_s: float = 0.0, cost: float = 0.01) -> None:
        self.inner = standin("claude")
        self.name = self.inner.name
        self.script = {k: list(v) for k, v in (script or {}).items()}
        self.chairs: list[Reply] = list(chair) if isinstance(chair, list) else [chair if chair is not None else chair_text()]
        self.views: dict[str, Any] = {}  # the views each judge session was given, by session key
        self.judges = list(judges or [])
        self.default = default or (lambda name, rnd: blk(f"{name}-view", round=rnd))
        self.hold_s = hold_s
        self.cost = cost
        self.lock = threading.Lock()
        self.requests: list[SessionRequest] = []
        self.sessions: Counter[str] = Counter()
        self.events: list[tuple[str, str]] = []  # ("start" | "end", session key), in the order they happened
        self.open = 0
        self.peak = 0

    def __getattr__(self, name: str) -> Any:
        return getattr(self.inner, name)

    def _reply(self, req: SessionRequest) -> SessionResult:
        parts = req.session_key.split(".")
        if req.kind == "chair":
            with self.lock:
                got: Reply = self.chairs.pop(0) if len(self.chairs) > 1 else self.chairs[0]
        elif req.kind == "step":  # a plain step after the council (a unit that routes on its outcome)
            got = "Done."
        else:
            name, rnd = parts[3], int(parts[4])
            with self.lock:
                queue = self.script.get((name, rnd))
                got = queue.pop(0) if queue else self.default(name, rnd)
        if callable(got):
            got = got(req)
        return got if isinstance(got, SessionResult) else answer(got, session_id=f"s-{req.session_key}", cost=self.cost)

    def run_step(self, req: SessionRequest, sink: Any) -> SessionResult:
        with self.lock:
            self.requests.append(req)
            self.sessions[req.session_key] += 1
            self.events.append(("start", req.session_key))
            self.open += 1
            self.peak = max(self.peak, self.open)
        try:
            if self.hold_s:
                time.sleep(self.hold_s)
            return self._reply(req)
        finally:
            with self.lock:
                self.open -= 1
                self.events.append(("end", req.session_key))

    def run_judge(self, req: SessionRequest, views: Any, sink: Any) -> SessionResult:
        with self.lock:
            self.requests.append(req)
            self.sessions[req.session_key] += 1
            self.views[req.session_key] = views
            text = self.judges.pop(0) if self.judges else MET
        return answer(text, tools=("Read",), session_id=f"j-{req.session_key}", cost=self.cost)

    def of(self, kind: str) -> list[str]:
        return sorted(r.session_key for r in self.requests if r.kind == kind)


def council_wf(names: tuple[str, ...] = ("a", "b", "c"), **fields: Any) -> Any:
    mode = fields.get("mode", "synthesize")
    base: dict[str, Any] = {
        "question": "Which store for {request}?", "members": [Member(name=n, stance=f"Lens {n}") for n in names],
        "chair": Chair() if mode != "rank" else None,
        "gate": Gate(judge=Judge(stance="Verify.", references=["positions"]), criteria=[crit("c-dec")])}
    base.update(fields)
    return named(Workflow(order=[UNIT], units={UNIT: Council(**base)}, issue_repository="acme/x",
                          routing=Routing(description="Decide a store")))


def go(repo: Path, spec: Any, ex: Any, task: str = "C-1", **kw: Any) -> Any:
    return start(spec, task, {"request": "the jobs"}, repo, registry(ex), dataclasses.replace(NO_SLEEP, **kw))


def recs(repo: Path, kind: str, task: str = "C-1") -> list[dict[str, Any]]:
    p = run_dir(state_root_path(repo), "demo", task) / "run.jsonl"
    return [r for r in map(json.loads, p.read_text().splitlines()) if r["kind"] == kind]


def test_cnl_ac4_a_council_runs_its_rounds_with_the_kinds_and_keys_of_cnl_b14(repo: Path) -> None:  # CNL-AC4 (CNL-B14)
    ex = Crew()
    out = go(repo, council_wf(rounds=1), ex)
    assert out.exit_code is ExitCode.FINISHED, out.message
    members = [f"{UNIT}.1.member.{n}.{r}" for r in (0, 1) for n in "abc"]
    assert ex.of("member") == sorted(members)
    assert ex.of("chair") == [f"{UNIT}.1.chair"] and ex.of("judge") == [f"{UNIT}.1.judge"]
    assert not ex.of("member_reask")
    assert all(n == 1 for n in ex.sessions.values())  # every session ran once
    kinds = {r["session_key"]: r["session_kind"] for r in recs(repo, "attempt_start")}
    assert kinds[f"{UNIT}.1.member.a.0"] == "member" and kinds[f"{UNIT}.1.chair"] == "chair"


def test_a_member_session_is_read_only_in_the_runs_worktree_and_resolved_on_the_step_layer(repo: Path) -> None:  # CNL-B14
    ex = Crew()
    spec = council_wf(members=[Member(name="a", tools=["read", "search"], model="large", timeout_s=90),
                               Member(name="b"), Member(name="c")])
    assert go(repo, spec, ex).exit_code is ExitCode.FINISHED
    a = next(r for r in ex.requests if r.session_key == f"{UNIT}.1.member.a.0")
    b = next(r for r in ex.requests if r.session_key == f"{UNIT}.1.member.b.0")
    assert a.tools == ("read", "search") and a.alias == "large" and a.timeout_s == 90
    assert b.tools == () and b.alias == "inherit"  # a member that declares none takes the step layer's
    assert a.workdir == b.workdir and Path(a.workdir).exists()  # one worktree, read-only members


def test_the_barrier_waits_for_every_member_before_the_next_round(repo: Path) -> None:  # CNL-AC4 (CNL-B14)
    ex = Crew(hold_s=0.1)
    assert go(repo, council_wf(rounds=1), ex).exit_code is ExitCode.FINISHED
    order = [(what, key.split(".")[-1]) for what, key in ex.events if ".member." in key and "reask" not in key]
    last_round0_end = max(i for i, (w, r) in enumerate(order) if w == "end" and r == "0")
    first_round1_start = min(i for i, (w, r) in enumerate(order) if w == "start" and r == "1")
    assert last_round0_end < first_round1_start
    assert ex.peak >= 2  # the members of a round run at once


def test_a_member_whose_block_does_not_parse_is_asked_once_more(repo: Path) -> None:  # CNL-AC4 (CNL-B11)
    ex = Crew(script={("a", 0): ["no block here", blk("fixed")]})
    out = go(repo, council_wf(), ex)
    assert out.exit_code is ExitCode.FINISHED, out.message
    assert ex.of("member_reask") == [f"{UNIT}.1.member_reask.a.0"]
    assert recs(repo, "council_round")[0]["answered"] == 3 and recs(repo, "council_round")[0]["spoiled"] == 0


def test_a_member_that_changed_the_workspace_fails_the_attempt_with_the_written_paths(repo: Path) -> None:  # CNL-AC4 (CNL-B14)
    def writes(req: SessionRequest) -> str:
        (Path(req.workdir) / "leak.txt").write_text("a member wrote this\n")
        return blk("sneaky")

    ex = Crew(script={("b", 0): [writes]})
    spec = council_wf()
    units = dict(spec.units)
    units[UNIT] = dataclasses.replace(units[UNIT], gate=dataclasses.replace(units[UNIT].gate, retry_budget=0))
    out = go(repo, dataclasses.replace(spec, units=units), ex)
    assert out.exit_code is ExitCode.PAUSED and out.payload["kind"] == "budget", out.message
    problem = out.payload["blockers"][0]["problem"]
    assert "member_changed_the_workspace" in problem and "leak.txt" in problem
    assert not ex.of("chair")  # a failed attempt asks no chair


class CrashingCrew(Crew):
    """`Crew` whose member `victim` waits for the others of round 0 to end and then cuts the process."""

    def __init__(self, victim: str, others: set[str], **kw: Any) -> None:
        super().__init__(**kw)
        self.victim, self.others = victim, others

    def _reply(self, req: SessionRequest) -> SessionResult:
        if req.kind == "member" and req.session_key == f"{UNIT}.1.member.{self.victim}.0":
            end = time.monotonic() + 10
            while time.monotonic() < end:
                with self.lock:
                    done = {k.split(".")[3] for w, k in self.events if w == "end" and ".member." in k}
                if self.others <= done:
                    break
                time.sleep(0.01)
            raise KeyboardInterrupt  # the process dies mid-round
        return super()._reply(req)


def test_cnl_ac4_a_crash_after_two_of_three_members_resumes_with_one_member_session(repo: Path) -> None:  # CNL-AC4 (CNL-B14)
    first = CrashingCrew("c", {"a", "b"})
    with pytest.raises(KeyboardInterrupt):
        go(repo, council_wf(), first)
    assert sorted(k for k in first.sessions if ".member." in k) == [f"{UNIT}.1.member.{n}.0" for n in "abc"]
    second = Crew()
    out = resume(council_wf(), "C-1", repo, registry(second), settings=NO_SLEEP)
    assert out.exit_code is ExitCode.FINISHED, out.message
    assert [k for k in second.sessions if ".member." in k] == [f"{UNIT}.1.member.c.0"]  # one, not three
    assert second.sessions[f"{UNIT}.1.chair"] == 1
    rows = recs(repo, "council_round")
    assert rows[-1]["answered"] == 3


def test_the_cost_of_the_sessions_that_ended_before_a_crash_is_counted_once(repo: Path) -> None:  # CNL-AC4 (CNL-B14)
    first = CrashingCrew("c", {"a", "b"}, cost=0.1)
    with pytest.raises(KeyboardInterrupt):
        go(repo, council_wf(), first)
    second = Crew(cost=0.1)
    assert resume(council_wf(), "C-1", repo, registry(second), settings=NO_SLEEP).exit_code is ExitCode.FINISHED
    (exit_rec,) = recs(repo, "run_exit")
    sessions = exit_rec["cost"]["counters"]["sessions"]
    assert sessions == 3 + 1 + 1  # three members, the chair and the judge, each paid for once


def test_every_council_session_is_written_in_the_run_log(repo: Path) -> None:  # CNL-AC4, EVT-B13, EVT-B15
    ex = Crew()
    assert go(repo, council_wf(), ex).exit_code is ExitCode.FINISHED
    rounds = recs(repo, "council_round")
    assert [(r["round"], r["answered"], r["spoiled"], r["missing"], r["changed"]) for r in rounds] == [(0, 3, 0, 0, 0)]
    assert sorted(rounds[0]["labels"]) == ["a", "b", "c"]
    (tally,) = recs(repo, "council_tally")
    assert tally["mode"] == "synthesize" and tally["outcome"] == "synthesized" and tally["chosen_by"] == "engine"
