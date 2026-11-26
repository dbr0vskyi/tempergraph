"""A council attempt, session by session (CNL-B1, CNL-B2, CNL-B11 to CNL-B15, ADR `new-node-kinds-keep-the-gated-unit`, ADR `council-is-a-gated-step-with-engine-tallied-outcomes`).

`compiler.graph` builds the unit's step node as a small subgraph (one member dispatch per round and member, a barrier,
a tally node and the chair node) and calls the methods of `CouncilRun` from its nodes. This module owns what the nodes
do: the member, re-ask and chair sessions with their keys, the fingerprints around each member, the caps, and the
state write the step node hands back. What a council decides without a session lives in `run.council`.

Each member session is kept on its own, under its session key, as soon as it ends (`council_result.json` in its
folder). The step node's own state write is made once, at the end, so a crash or a drain in the middle of a round
leaves the state as it was and the rerun of the attempt finds the sessions that ended and runs only the others.
"""

from __future__ import annotations

import contextlib
import hashlib
import json
import threading
from collections.abc import Mapping, Sequence
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

from tempergraph import git as gitmod
from tempergraph.compiler.state import council_answers
from tempergraph.contracts import (
    CouncilSpec,
    SessionOptions,
    SessionRequest,
    SessionResult,
    ToolCall,
    Usage,
)
from tempergraph.docs import write_json
from tempergraph.model.text import load_text
from tempergraph.render.template import render
from tempergraph.run import council as cn
from tempergraph.run.log import CostTotals
from tempergraph.security.scrub import clip, scrub
from tempergraph.store.layout import session_dir

RESULT_FILE = "council_result.json"
DEFAULT_TIMEOUT_S = 600


# -- sessions kept on their own ---------------------------------------------------------------------------------


def dump_result(res: SessionResult) -> dict[str, Any]:
    return {"ok": res.ok, "text": res.text, "session_id": res.session_id, "usage": res.usage.to_json(),
            "tools": [c.name for c in res.tool_calls], "timed_out": res.timed_out, "stalled": res.stalled,
            "partial": res.partial, "error_kind": res.error_kind, "cli_version": res.cli_version, "model": res.model,
            "duration_s": res.duration_s, "tool_wall_share": res.tool_wall_share, "denied": list(res.denied),
            "tools_at_start": list(res.tools_at_start)}


def load_result(d: Mapping[str, Any]) -> SessionResult:
    return SessionResult(
        ok=bool(d["ok"]), text=str(d.get("text") or ""), session_id=d.get("session_id"),
        usage=Usage(**dict(d.get("usage") or {})), tool_calls=[ToolCall(name=str(n)) for n in d.get("tools") or []],
        timed_out=bool(d.get("timed_out")), stalled=bool(d.get("stalled")), partial=bool(d.get("partial")),
        error_kind=d.get("error_kind"), cli_version=str(d.get("cli_version") or ""), model=d.get("model"),
        duration_s=d.get("duration_s"), tool_wall_share=float(d.get("tool_wall_share") or 0.0),
        denied=tuple(d.get("denied") or ()), tools_at_start=tuple(d.get("tools_at_start") or ()))


def _digest(text: str) -> str:
    return hashlib.sha256(text.encode()).hexdigest()[:16]


@dataclass(kw_only=True)
class CouncilRun:
    """One attempt of one council unit, shared by the nodes of its subgraph (never checkpointed itself)."""

    engine: Any  # EngineNodes
    unit: str
    council: CouncilSpec
    state: Mapping[str, Any]
    attempt: int
    visit: int
    entered: bool
    workdir: Path
    question: str
    options: tuple[str, ...]
    labels: dict[str, str]
    names: list[str]
    chair_only: bool = False
    notes: tuple[str, ...] = ()
    prior: Mapping[str, Any] = field(default_factory=dict)
    stages: list[dict[str, cn.Answer]] = field(default_factory=list)
    ranks: dict[str, cn.Answer] = field(default_factory=dict)
    results: list[SessionResult] = field(default_factory=list)
    executors: dict[str, str] = field(default_factory=dict)
    infra_stage: dict[int, set[str]] = field(default_factory=dict)
    infra_all: bool = False
    capped: bool = False
    stopped_early: bool = False  # a round missed its quorum: no later round is asked
    written: list[str] = field(default_factory=list)
    tally: cn.Tally | None = None
    decision: str = ""
    chair_text: str | None = None
    chair_failed: str | None = None
    chair_infra: bool = False
    limited: tuple[float | None] | None = None  # the usage limit ended a session: its reset instant (BUD-B17)
    rounds_log: list[dict[str, Any]] = field(default_factory=list)
    lock: threading.Lock = field(default_factory=threading.Lock)

    # -- the shape of the attempt -----------------------------------------------------------------------------

    @property
    def spec(self) -> Any:
        return self.engine.ctx.spec

    @property
    def rounds(self) -> int:
        return self.council.rounds

    @property
    def last_stage(self) -> int:
        """The last stage a member is asked in: the final round, or the ranking pass of a `rank` council."""
        return self.rounds + (1 if self.council.mode == "rank" else 0)

    def dispatch(self, stage: int) -> list[str] | None:
        """The members asked in `stage`, or None when no member is (the attempt is past its last stage, a chair-only
        retry, a stop at a boundary, or an attempt that has already failed)."""
        if (self.chair_only or self.infra_all or self.capped or self.stopped_early or self.written
                or self.limited is not None):
            return None
        return list(self.names) if stage <= self.last_stage else None

    def key(self, kind: str, name: str | None = None, stage: int | None = None) -> str:
        """`<unit>.<attempt>.member.<name>.<round>`, the same with `member_reask`, and `<unit>.<attempt>.chair` (CNL-B14)."""
        what = kind if name is None else f"{kind}.{name}.{stage}"
        return self.engine._skey(self.unit, self.attempt, what)

    def accrued(self) -> float:
        """What this attempt's sessions cost so far, as the run line counts it."""
        t = CostTotals()
        with self.lock:
            for r in self.results:
                t.add(r.usage)
        return t.figure()

    # -- one session ------------------------------------------------------------------------------------------

    def _request(self, kind: str, key: str, prompt: str, *, executor: str | None, alias: str | None, tools: Sequence[str],
                 timeout_s: int | None, idle_s: int | None) -> tuple[Any, SessionRequest]:
        eng = self.engine
        ex = eng.ctx.registry.get(executor or self.spec.default_executor)
        cap = (eng.ctx.spec.units[self.unit].extra or {}).get("session_cost_cap_usd")
        req = SessionRequest(
            kind=kind, prompt=prompt, workdir=self.workdir, alias=alias or "inherit", session_key=key,  # type: ignore[arg-type]
            tools=tuple(tools), timeout_s=timeout_s or DEFAULT_TIMEOUT_S, idle_s=idle_s,
            options=SessionOptions(cost_cap_usd=float(cap)) if cap is not None else SessionOptions(),
            session_dir=session_dir(eng.ctx.state_root, self.spec.name, eng.ctx.task_id, key),
            enforce_tools=eng.ctx.enforce_tools, in_engine_worktree=eng._in_worktree(self.state),
            plugin_dir=self.spec.package_root)
        return ex, req

    def _kept(self, req: SessionRequest) -> SessionResult | None:
        path = (req.session_dir or Path()) / RESULT_FILE
        try:
            doc = json.loads(path.read_text(encoding="utf-8"))
            if doc.get("key") == req.session_key and doc.get("digest") == _digest(req.prompt):
                return load_result(doc["result"])
        except (OSError, ValueError, KeyError, TypeError):
            return None
        return None

    def _keep(self, req: SessionRequest, res: SessionResult) -> None:
        if req.session_dir is None or res.infra_cause is not None or not res.ok:
            return
        with contextlib.suppress(OSError):
            req.session_dir.mkdir(parents=True, exist_ok=True, mode=0o700)
            write_json(req.session_dir / RESULT_FILE, {"key": req.session_key, "digest": _digest(req.prompt),
                                                       "result": dump_result(res)}, mode=0o600)

    def session(self, ex: Any, req: SessionRequest, *, width: int, gated: bool = True) -> SessionResult | None:
        """Run one session, or take the one that already ended under this key. None: the council's own cost cap stopped
        it before it started (CNL-B8). The reservation of a run with a cost cap is taken per try (BUD-B12)."""
        eng = self.engine
        kept = self._kept(req)
        if kept is not None:
            with self.lock:
                self.results.append(kept)
                self.executors[ex.name] = kept.cli_version or self.executors.get(ex.name, "")
            hold = self._hold(width)
            if hold is not None:  # it was paid before this process: it counts as spent for the sessions that follow
                paid = CostTotals()
                paid.add(kept.usage)
                eng.ledger.add_ended(int(hold["snapshot"]), paid.figure())
            return kept
        cap = self.council.cost_cap_usd
        if cap is not None and self.accrued() >= cap:  # no new session; the running ones finish (CNL-B8)
            with self.lock:
                self.capped = True
            return None
        res, tries = eng._session(ex, req, hold=self._hold(width) if gated else None)
        with self.lock:
            self.results.extend(tries)
            self.executors[ex.name] = res.cli_version or self.executors.get(ex.name, "")
        self._keep(req, res)
        return res

    def _hold(self, width: int) -> dict[str, Any] | None:
        return self.engine._hold(self.unit, self.state, width=width)

    def _workspace_guard(self, before: gitmod.Fingerprint, after: gitmod.Fingerprint) -> list[str]:
        """WSP-B11: the paths a read-only session left written in the run's worktree."""
        if before == after:
            return []
        old = set(before.status.splitlines())
        return sorted({ln[3:] for ln in after.status.splitlines() if ln not in old and len(ln) > 3}) or ["(the workspace)"]

    # -- a member's stage -------------------------------------------------------------------------------------

    def _peers(self, name: str, stage: int) -> list[tuple[str, str]]:
        """The others' answers of the stage before, under their labels in the attempt's order (or their names)."""
        prev = self.stages[stage - 1] if 0 < stage <= len(self.stages) else {}
        order = sorted((n for n in self.names if n != name), key=lambda n: self.labels[n])
        if not self.council.anonymize:
            order = [n for n in self.names if n != name]
        return [((self.labels[n] if self.council.anonymize else n), prev[n].text)
                for n in order if n in prev and prev[n].status == "ok"]

    def member(self, name: str, stage: int) -> None:
        """One member answers once in `stage` (CNL-B1, CNL-B2, CNL-B11); a read-only session in the run's worktree."""
        c = self.council
        m = next(x for x in c.members if x.name == name)
        ranking = stage > self.rounds
        prev = self.stages[stage - 1] if 0 < stage <= len(self.stages) else {}
        own = prev[name].text if name in prev and prev[name].status == "ok" else ""
        if ranking:
            final = self.stages[self.rounds] if self.rounds < len(self.stages) else {}
            peers = [(self.labels[n], final[n].text) for n in sorted(self.names, key=lambda x: self.labels[x])
                     if n != name and n in final and final[n].status == "ok"]
            prompt = cn.ranking_prompt(question=self.question, peers=peers,
                                       own_previous=final[name].text if name in final else "")
            asked = tuple(lab for lab, _ in peers)
            read_round = 0
        else:
            prompt = cn.member_prompt(question=self.question, stance=m.stance, round=stage, mode=c.mode,
                                      options=self.options, peers=self._peers(name, stage), anonymize=c.anonymize,
                                      own_previous=own)
            asked, read_round = (), stage
        ex, req = self._request("member", self.key("member", name, stage), prompt, executor=m.executor, alias=m.model,
                                tools=m.tools, timeout_s=m.timeout_s, idle_s=m.idle_s)
        width = len(self.names)
        before = gitmod.fingerprint(self.workdir)
        res = self.session(ex, req, width=width)
        answer = self._read(name, stage, ex, req, res, ranking, asked, read_round, width)
        written = self._workspace_guard(before, gitmod.fingerprint(self.workdir)) if res is not None and res.ok else []
        with self.lock:
            if written:
                self.written.extend(p for p in written if p not in self.written)
                answer = cn.missing()
            self._put(stage, name, answer, res)

    def _read(self, name: str, stage: int, ex: Any, req: SessionRequest, res: SessionResult | None, ranking: bool,
              asked: tuple[str, ...], read_round: int, width: int) -> cn.Answer:
        c = self.council
        if res is not None and res.usage_limit and not res.ok:
            self._limit(res)  # not a missing answer: the attempt pauses and nothing is spent (BUD-B17)
            return cn.missing()
        if res is None or res.infra_cause is not None or not res.ok:
            return cn.missing()  # no session ended with an answer (CNL-B15)
        try:
            return cn.parse_answer(res.text, mode=c.mode, options=self.options, round=read_round, peers=asked)
        except cn.Unparsed as exc:
            problem = str(exc)
        again = cn.reask_prompt(res.text, problem, mode=c.mode, options=self.options, round=read_round,
                                ranking=ranking)
        ex2, req2 = self._request("member_reask", self.key("member_reask", name, stage), again,
                                  executor=next(x for x in c.members if x.name == name).executor,
                                  alias=req.alias, tools=req.tools, timeout_s=req.timeout_s, idle_s=req.idle_s)
        res2 = self.session(ex2, req2, width=width)
        if res2 is not None and res2.usage_limit and not res2.ok:
            self._limit(res2)
            return cn.missing()
        if res2 is None or res2.infra_cause is not None or not res2.ok:
            return cn.spoiled(res.text)
        try:
            return cn.parse_answer(res2.text, mode=c.mode, options=self.options, round=read_round, peers=asked)
        except cn.Unparsed:
            return cn.spoiled(res2.text)  # a second failure counts against the quorum (CNL-B11)

    def _limit(self, res: SessionResult) -> None:
        with self.lock:
            if self.limited is None or (res.usage_limit_resets_at or 0) > (self.limited[0] or 0):
                self.limited = (res.usage_limit_resets_at,)

    def _put(self, stage: int, name: str, answer: cn.Answer, res: SessionResult | None) -> None:
        while len(self.stages) <= min(stage, self.rounds):
            self.stages.append({})
        if stage > self.rounds:
            self.ranks[name] = answer
        else:
            self.stages[stage][name] = answer
        if res is not None and res.infra_cause is not None:
            self.infra_stage.setdefault(stage, set()).add(name)

    # -- the barrier --------------------------------------------------------------------------------------------

    def close(self, stage: int) -> int:
        """The round barrier: every member has answered, failed or spoiled. Writes the `council_round` record, applies
        the stops, and names the next stage (CNL-B14, CNL-B15, EVT-B13)."""
        c = self.council
        if stage <= self.rounds:
            got = self.stages[stage] if stage < len(self.stages) else {}
            counts = cn.round_counts(got, self.names)
            self.rounds_log.append({"round": stage, **counts})
            self.engine.ctx.log.write("council_round", unit=self.unit, attempt=self.attempt, round=stage,
                                      labels=sorted(self.names, key=lambda n: self.labels[n]), **counts)
            need = c.quorum or len(self.names)
            if counts["answered"] < need:
                self.stopped_early = True  # a round below quorum ends the deliberation (CNL-B13)
        failed = self.infra_stage.get(stage, set())
        if failed and len(failed) >= len(self.names):
            self.infra_all = True  # every member failed on infrastructure: an infra failure, never a pause (CNL-B15)
        return stage + 1

    # -- the tally and the chair --------------------------------------------------------------------------------

    def _restore(self) -> None:
        """A chair-only retry reuses the members' recorded positions (CNL-B7)."""
        held = council_answers(self.state, self.unit)
        self.stages = [{n: cn.Answer.from_json(a) for n, a in dict(stage).items()} for stage in held.get("stages") or []]
        self.ranks = {n: cn.Answer.from_json(a) for n, a in dict(held.get("ranks") or {}).items()}

    def tally_now(self) -> None:
        """The pure tally node: the outcome by rule, no model reading the ballots (CNL-B3, CNL-B12)."""
        c = self.council
        if self.chair_only:
            self._restore()
        if self.infra_all or self.capped or self.written or self.limited is not None:
            return
        final =self.stages[min(len(self.stages), self.rounds + 1) - 1] if self.stages else {}
        n = len(self.names)
        if c.mode == "vote":
            self.tally = cn.tally_vote(final, options=self.options, rule=c.rule, quorum=c.quorum, members=n)
        elif c.mode == "rank":
            conf = {nm: _mean_confidence(self.stages, nm) for nm in self.names}
            have_all = len(self.stages) == self.rounds + 1 and not self.stopped_early
            self.tally = cn.borda(self.ranks if have_all else {}, labels=self.labels, confidences=conf,
                                  quorum=c.quorum)
        else:
            self.tally = cn.synthesis_tally(final, quorum=c.quorum, members=n)
        if not self.chair_only:
            self.engine.ctx.log.write("council_tally", unit=self.unit, attempt=self.attempt, mode=c.mode,
                                      rule=self.tally.rule, counts=dict(self.tally.counts), outcome=self.tally.outcome,
                                      chosen_by="engine")

    def final_answers(self) -> dict[str, cn.Answer]:
        return self.stages[min(len(self.stages), self.rounds + 1) - 1] if self.stages else {}

    def chair_now(self) -> None:
        """The chair node: the synthesis of a `synthesize` council, the rationale of a `vote` or `rank` that has a chair.
        It does not run when there is no decision, or the attempt has already failed (CNL-B12, CNL-B13)."""
        c = self.council
        t = self.tally
        if t is None or t.outcome == cn.NO_DECISION or c.chair is None:
            self.decision = cn.decision_text(c.mode, t, None) if t is not None else ""
            return
        final = self.final_answers()
        positions = [(self.labels[n], final[n].position, final[n].text) for n in
                     sorted(self.names, key=lambda x: self.labels[x]) if n in final and final[n].status == "ok"]
        prompt = cn.chair_prompt(question=self.question, positions=positions, mode=c.mode,
                                 outcome=None if c.mode == "synthesize" else t.outcome, notes=self.notes,
                                 custom=c.chair.prompt)
        eng = self.engine
        eng._council_boundary(self.state, self.accrued())  # the chair runs alone: it meets the check of an attempt
        ex, req = self._request("chair", self.key("chair"), prompt, executor=c.chair.executor, alias=c.chair.model,
                                tools=(), timeout_s=None, idle_s=None)
        before = gitmod.fingerprint(self.workdir)
        res = self.session(ex, req, width=1)
        if res is None:
            return
        written = self._workspace_guard(before, gitmod.fingerprint(self.workdir)) if res.ok else []
        if res.usage_limit and not res.ok:
            self._limit(res)
            return
        if written:
            self.written.extend(written)
        elif res.infra_cause is not None:
            self.chair_infra = True
        elif not res.ok:
            self.chair_failed = res.error_kind or ("timed out" if res.timed_out else "the chair's session failed")
        else:
            self.chair_text = res.text
        self.decision = cn.decision_text(c.mode, t, self.chair_text)

    # -- what the step node writes -------------------------------------------------------------------------------

    def finish(self) -> dict[str, Any]:
        """The state write of the step node: the attempt record, the three artifacts and the cost (CNL-B10)."""
        eng = self.engine
        c = self.council
        state = self.state
        t = self.tally
        final = self.final_answers()
        outcome = t.outcome if t is not None else None
        positions = cn.positions_json(self.stages, self.labels, self.ranks or None) if self.stages else {}
        dissent = cn.chair_dissent(self.chair_text or "") if self.chair_text is not None else ""
        differs = cn.positions_differ(final) if final else False
        council: dict[str, Any] = {
            "mode": c.mode, "labels": dict(self.labels),
            "order": sorted(self.names, key=lambda n: self.labels[n]), "rounds": list(self.rounds_log),
            "outcome": outcome, "tally": cn.tally_json(t) if t is not None else None,
            "chair_only": self.chair_only, "dissent": dissent, "positions_differ": differs,
            "options": list(self.options)}
        rec: dict[str, Any] = {
            "attempt": self.attempt, "visit": self.visit, "ok": True, "text": clip(scrub(self.decision), 8000),
            "issues": [], "tools": [], "session_id": None, "escalate": None, "infra_spent": False, "check": None,
            "item": None, "timed_out": False, "changed": False, "council": council, "error_kind": None,
            "council_stop": None, "dissent_missing": None, "written": None, "infra_cause": None}
        if self.limited is not None:  # BUD-B17: nothing is spent and the attempt keeps no artifacts
            rec.update(ok=False, escalate="usage_limit", usage_limit_resets_at=self.limited[0],
                       usage_limit_stage="step", reuse={"notes": list(self.notes)})
        elif self.infra_all or self.chair_infra:
            rec.update(ok=False, infra_spent=True, infra_cause="member_infra" if self.infra_all else "chair_infra")
        elif self.written:
            rec.update(ok=False, error_kind="member_changed_the_workspace", written=list(self.written))
        elif self.capped:
            rec.update(ok=False, error_kind="cap_reached")
        elif self.chair_failed:
            rec.update(ok=False, error_kind=self.chair_failed)
        elif outcome == cn.NO_DECISION:
            how = c.on_no_decision
            if how == "escalate":
                rec["escalate"] = "no_decision"
            elif how == "retry":
                rec.update(ok=False, error_kind="no_decision")
            else:
                rec["council_stop"] = True
        elif c.mode == "synthesize" and differs and not dissent:  # a retryable built-in check (CNL-B12)
            rec["dissent_missing"] = True
        failed = not rec["ok"] and rec["error_kind"] != "no_decision" or bool(rec["infra_spent"])
        arts: dict[str, Any] | None = None
        if t is not None and not failed:
            arts = {"decision": self.decision, "positions": json.dumps(positions, sort_keys=True),
                    "tally": json.dumps(cn.tally_json(t), sort_keys=True), "tally.outcome": str(outcome)}
        run: dict[str, Any] = {"cost": eng._cost(state, self.results),
                               "executors": {**((state.get("run") or {}).get("executors") or {}), **self.executors}}
        path_units = list(((state.get("run") or {}).get("path") or {}).get("units") or [])
        if self.entered and self.unit not in path_units:
            run["path"] = {"units": path_units + [self.unit]}
        kept = {"attempt": self.attempt, "labels": dict(self.labels),
                "stages": [{n: a.to_json() for n, a in s.items()} for s in self.stages],
                "ranks": {n: a.to_json() for n, a in self.ranks.items()}} if self.stages and not failed else None
        return {"attempts": {self.unit: rec}, "values": {self.unit: arts}, "council": {self.unit: kept}, "run": run}


def _mean_confidence(stages: Sequence[Mapping[str, cn.Answer]], name: str) -> float | None:
    got = [s[name].confidence for s in stages if name in s and s[name].confidence is not None]
    return sum(got) / len(got) if got else None  # type: ignore[arg-type]


# -- the entry the subgraph's first node calls ---------------------------------------------------------------------


def open_run(engine: Any, unit: str, state: Mapping[str, Any]) -> CouncilRun:
    """The first node: what this attempt is (its number, its labels, the question) and whether it is a chair-only
    retry (CNL-B7). The unit's entry is logged once per visit, as a step's is."""
    spec = engine.ctx.spec
    c = spec.units[unit].council
    assert c is not None
    engine._boundary(state)
    prev = (state.get("attempts") or {}).get(unit) or {}
    visit = int(((state.get("visits") or {}).get(unit) or {}).get("visit", 1))
    entered = prev.get("visit") != visit
    workdir = engine._workdir(state, unit)
    if entered:
        from tempergraph.run.nodes import _entered_from

        fp = gitmod.fingerprint(workdir)
        engine.ctx.log.write("unit_entered", unit=unit, visit=visit, head_commit=fp.head, dirty=fp.dirty,
                             entered_from=_entered_from(state, unit))
    again = prev.get("escalate") == "usage_limit" and not entered  # DUR-B12: the refused attempt runs again
    attempt = int(prev["attempt"]) if again else int(prev.get("attempt", 0)) + 1
    if not again:
        engine.ctx.count_attempt(unit, None, attempt, visit)
    names = [m.name for m in c.members]
    seed = f"{engine.ctx.thread}/{unit}/{attempt}"
    fields = engine._fields(unit, state, attempt, visit, workdir)
    question = render(load_text(spec, c.question), fields)[0]
    held = prev.get("council") or {}
    judged = (state.get("judgements") or {}).get(unit) or {}
    retry = not entered and bool(prev)
    scoped = ((state.get("route") or {}).get(unit) or {}).get("scope") == "chair"  # the gate said so (CNL-B7)
    chair_only = (scoped and retry and bool(council_answers(state, unit).get("stages")) and bool(held.get("labels"))
                  and c.chair is not None)
    notes: tuple[str, ...] = ()
    if again:  # the judgement is the placeholder now: the refused attempt kept what its chair prompt reads
        notes = tuple(str(n) for n in (prev.get("reuse") or {}).get("notes") or ())
    elif retry:
        notes =tuple(str(b.get("problem") or b.get("evidence") or "") for b in judged.get("blockers") or []
                      if b.get("problem") or b.get("evidence"))
    labels = dict(held["labels"]) if chair_only else cn.label_map(names, seed)
    return CouncilRun(engine=engine, unit=unit, council=c, state=state, attempt=attempt, visit=visit, entered=entered,
                      workdir=workdir, question=question, options=options_of(c, state, workdir), labels=labels,
                      names=names, chair_only=chair_only, notes=notes, prior=held,
                      rounds_log=[dict(r) for r in held.get("rounds") or []] if chair_only else [])


def options_of(c: CouncilSpec, state: Mapping[str, Any], workdir: Path) -> tuple[str, ...]:
    """A `vote`'s options: its slugs, or the list an earlier unit produced under the key `options` names (CNL-B9)."""
    if c.options is None:
        return ()
    if not isinstance(c.options, str):
        return tuple(c.options)
    raw = ""
    for chan in ("values", "artifacts"):
        for vals in (state.get(chan) or {}).values():
            if isinstance(vals, dict) and c.options in vals:
                raw = str(vals[c.options])
    if raw and "\n" not in raw and not raw.lstrip().startswith(("[", "-")):
        with contextlib.suppress(OSError):
            p = (workdir / raw).resolve()
            if p.is_relative_to(workdir.resolve()) and p.is_file():
                raw = p.read_text(encoding="utf-8", errors="replace")
    try:
        data = json.loads(raw)
        if isinstance(data, list):
            return tuple(str(x) for x in data)
    except ValueError:
        pass
    return tuple(ln.strip().lstrip("-* ").strip() for ln in raw.splitlines() if ln.strip().lstrip("-* ").strip())
