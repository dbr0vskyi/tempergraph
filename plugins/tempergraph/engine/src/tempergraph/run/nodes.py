"""The node bodies the compiler wires into the graph (CMP `UnitNodes`): step, judge, gate, human, finalizer.

The step and judge nodes are the only places a model session starts (OVR-B3); the gate is pure;
the human node's interrupt is the compiler's. Budgets follow BUD-B1, BUD-B11: the cause picks the counter.
"""

from __future__ import annotations

import contextlib
import dataclasses
import fnmatch
import hashlib
import os
import posixpath
import threading
import time
from collections.abc import Callable, Mapping, Sequence
from concurrent.futures import ThreadPoolExecutor
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

from tempergraph import git as gitmod
from tempergraph.compiler.state import Move, RunState, fold, item_view, own_keys, slot_writes
from tempergraph.contracts import (
    CheckResult,
    Executor,
    MapItem,
    MeasureContext,
    ScriptSpec,
    SessionOptions,
    SessionRequest,
    SessionResult,
    SlotSpec,
    StepSpec,
    UnitSpec,
    Verdict,
    ViewSet,
    WorkflowSpec,
)
from tempergraph.executors.launcher import StopRequest
from tempergraph.executors.registry import Registry
from tempergraph.improve import lessons as lessonsmod
from tempergraph.model import flow
from tempergraph.model.text import load_text, split_judge_file
from tempergraph.render.output import parse_output
from tempergraph.render.prompt import AttemptContext, Blocker, render_step
from tempergraph.run import audit as auditmod
from tempergraph.run import checks as checkmod
from tempergraph.run import complexity, mapping, reserve, scriptcache, tool_access
from tempergraph.run import contest as contestmod
from tempergraph.run import gate as gatemod
from tempergraph.run import ladder as laddermod
from tempergraph.run.check_worker import run_in_worker
from tempergraph.run.commands import ResolvedCommand, run_command
from tempergraph.run.commands import expand as expand_commands
from tempergraph.run.guard import guard, view_set
from tempergraph.run.judging import (
    CLAIM_CRITERION_ID,
    JudgeInputs,
    Unparsed,
    brief_digest,
    claim_criterion,
    council_dissent_blocker,
    council_inputs,
    criteria_digest,
    derive,
    judged,
    marked_reading,
    parse_judgement,
    reask_prompt,
    render_judge,
    reread_needed,
    reread_prompt,
)
from tempergraph.run.log import CostTotals, RunLog, cost_so_far, estimate, session_sink
from tempergraph.run.session_record import read_session
from tempergraph.security.scrub import clip, scrub
from tempergraph.settings import Capture
from tempergraph.store.layout import session_dir, session_key
from tempergraph.workspace import WorkspaceRecord, WorkspaceRefused, cut_writers, scan_foreign_worktrees

ATTEMPT_CAP = 15
INFRA_TRIES = 3
BACKOFF_S = (10, 20, 40)
DEFAULT_TIMEOUT_S = 600


def _skip_match(path: str, pattern: str) -> bool:
    """SRV-B42: a whole-path, case-sensitive match; `*` and `**` cross directories."""
    return fnmatch.fnmatchcase(path, posixpath.normpath(pattern))


class Drain(Exception):
    """End this process's segment at a boundary; the thread stays resumable (CMP-B5, RCT-B1, BUD cost cap)."""

    def __init__(self, reason: str) -> None:
        super().__init__(reason)
        self.reason = reason


@dataclass(kw_only=True)
class RunContext:
    spec: WorkflowSpec
    task_id: str
    state_root: Path
    registry: Registry
    log: RunLog
    judges: Mapping[str, str] = field(default_factory=dict)
    enforce_tools: bool = False
    judge_override: str | None = None
    stop: StopRequest = field(default_factory=StopRequest)
    drain_requested: Callable[[], str | None] = lambda: None
    sleep: Callable[[float], None] = time.sleep
    attempt_cap: int = ATTEMPT_CAP
    infra_tries: int = INFRA_TRIES
    backoff_max_s: int = 300
    settings: Mapping[str, Any] = field(default_factory=dict)  # workflow-declared settings (RST-B25)
    capture: Capture = field(default_factory=Capture)  # the operator's capture level (LOS-B17)
    main_checkout: Path | None = None
    attempts_started: int = 0
    counted: dict[tuple[str, str | None], int] = field(default_factory=dict)  # counted attempts by unit and item (CMP-B19)
    started: dict[tuple[str, str | None], int] = field(default_factory=dict)  # every attempt started, counted or not
    trips: dict[str, int] = field(default_factory=dict)  # trips back, by the unit they entered (CMP-B20)
    origin: str = "cli"
    stage: str = "local-dev"  # PRO-B7, PRO-B4
    judge_state: Callable[[str], str] | None = None  # a gate's judge binding state (JCL-B17); None reads it
    escalation_record: Callable[[str], bool] | None = None  # LAD-B13; None reads the ledger
    self_check_limit: int = 3  # CHK-B17
    audit_rate: float = 0.0  # JDG-B7: the chance that a judged gate is audited by a second judge
    audit_executor: str | None = None  # JDG-B7: the executor of the audit judge; None is the gate's judge executor
    audit_seed: int | None = None  # a test hook that fixes the audit draw
    child: str | None = None  # SWF-B8: the sub-workflow unit whose child this context runs; None for the run's own spec
    parent_thread: str = ""  # a child's context keeps the parent's thread
    read_worktreeinclude: bool = True  # `run.worktree.read_worktreeinclude`, for the writer worktrees (WSP-B2)

    def count_attempt(self, unit: str, item: str | None, attempt: int, visit: int) -> None:
        """CMP-B19: an attempt counts against the cap only when its unit, item or slot has attempted before in the
        thread, as a retry or in a visit after a trip back."""
        self.started[(unit, item)] = self.started.get((unit, item), 0) + 1
        if attempt > 1 or visit > 1:
            self.attempts_started += 1
            self.counted[(unit, item)] = self.counted.get((unit, item), 0) + 1

    def report(self) -> dict[str, Any]:
        """CMP-B20: what repeated in this invocation, for the exit at the attempt cap."""
        repeated = [{"unit": u, "item": i, "attempts": self.started.get((u, i), n),
                     "trips_back": self.trips.get(u, 0)} for (u, i), n in self.counted.items()]
        return {"attempts_counted": self.attempts_started, "trips_back": sum(self.trips.values()),
                "repeated": repeated}

    @property
    def thread(self) -> str:
        return self.parent_thread or f"{self.spec.name}/{self.task_id}"

    @property
    def key_prefix(self) -> str:
        """SWF-B8: session keys of a child read `<unit>/<child unit>.<attempt>.<kind>`."""
        return f"{self.child}/" if self.child else ""


def _aliases(v: object) -> list[str]:
    if v is None:
        return []
    return [v] if isinstance(v, str) else [str(x) for x in v]  # type: ignore[attr-defined]


class EngineNodes:
    def __init__(self, ctx: RunContext) -> None:
        self._deferred: list[dict[str, Any]] = []
        self._deferred_lock = threading.Lock()
        self._audits: dict[tuple[str, str | None], dict[str, Any]] = {}  # audit results waiting for their gate record
        self.ledger = reserve.Ledger()  # what each running session of a parallel block holds (BUD-B12)
        self.ctx = ctx

    # -- helpers ---------------------------------------------------------------------------------

    def defer(self, update: Mapping[str, Any]) -> None:
        """A state write the runner could not make before the graph ran, because several nodes are pending
        (branches of a parallel block): the first node to finish carries it."""
        with self._deferred_lock:
            self._deferred.append(dict(update))

    def settle(self, w: dict[str, Any]) -> dict[str, Any]:
        with self._deferred_lock:
            held, self._deferred = self._deferred, []
        for update in held:
            for ch, val in update.items():
                w[ch] = {**val, **w[ch]} if isinstance(val, dict) and isinstance(w.get(ch), dict) else \
                    w.get(ch, val) if ch in w else val
        return w

    def _workdir(self, state: Mapping[str, Any], unit: str | None = None) -> Path:
        """The run's worktree; a writer branch's own worktree for the step, judge, check and script of `unit`
        (WSP-B11, WTR-B25)."""
        child = self._writer_child(state, unit) if unit is not None else None
        if child is not None:
            return Path(str(child["path"]))
        return Path((state.get("workspace") or {}).get("path") or self.ctx.state_root.parent)

    def _writer_child(self, state: Mapping[str, Any], unit: str) -> Mapping[str, Any] | None:
        """The workspace record's child for `unit` when `unit` is a writer branch of a parallel block, or for the item in
        hand when `unit` is a concurrent map whose step writes (its child is addressed by the item's slot and the map's
        visit, WSP-B20; a contest's slot is addressed by the slot and the contest's attempt, WSP-B20; a block's writer
        branch is that of visit 1)."""
        held = mapping.item_in_hand(state)
        if held is not None:  # an item of a writing map or a slot of a writing contest: its child is its slot's
            if flow.writer_map(self.ctx.spec, unit):
                return self._child_of(state, held["slot"], int(mapping.record(state, unit).get("visit", 1)))
            if flow.writer_contest(self.ctx.spec, unit):
                return self._child_of(state, held["slot"], int(mapping.record(state, unit).get("attempt", 1)))
            return None
        block = flow.block_of(self.ctx.spec, unit)
        if block is None or unit not in flow.writer_branches(self.ctx.spec, block):
            return None
        return self._child_of(state, unit)

    @staticmethod
    def _child_of(state: Mapping[str, Any], name: str, visit: int = 1) -> Mapping[str, Any] | None:
        """The child of the workspace record whose unit is `name` and whose visit (none recorded: the first) is `visit`."""
        for child in (state.get("workspace") or {}).get("children") or []:
            if child.get("unit") == name and int(child.get("visit", 1)) == visit:
                return child
        return None

    def _in_worktree(self, state: Mapping[str, Any]) -> bool:
        return (state.get("workspace") or {}).get("mode") == "worktree"

    @staticmethod
    def _workspace_paths(state: Mapping[str, Any]) -> list[str]:
        ws = state.get("workspace") or {}
        return [str(p) for p in (ws.get("path"), *(c.get("path") for c in ws.get("children") or [])) if p]

    def _foreign_worktrees(self, unit: str, iid: str | None, key: str, known: Sequence[str],
                           before: Mapping[str, str]) -> list[str]:
        """WTR-B26, WTR-B13: a worktree that appeared during a step session and is not in the run's record (a
        subagent's, P-WTR-2) is recorded as a `workspace` record `foreign` with its path relative to the
        repository's parent, its branch and the session key. Nothing is removed, merged or read. Returns the
        relative paths."""
        main = self.ctx.main_checkout
        if main is None:
            return []
        out: list[str] = []
        for path, br in scan_foreign_worktrees(main, known).items():
            if path in before:
                continue
            rel = os.path.relpath(path, main.parent)
            out.append(rel)
            self.ctx.log.write("workspace", action="foreign", unit=unit, item=iid, mode="worktree", path=rel,
                               branch=br or None, session_key=key)
        return out

    def fork(self, join: str, state: RunState) -> dict[str, Any]:
        """WSP-B19, WSP-B11: entering a block that has a writer branch commits the run worktree's uncommitted changes on
        the run's branch, then cuts one worktree per writer branch from that commit. A cut that fails ends the segment
        at this boundary (engine_error `workspace_refused`) with nothing left behind."""
        writers = flow.writer_branches(self.ctx.spec, join)
        ws = dict(state.get("workspace") or {})
        try:
            if ws.get("mode") != "worktree":
                raise WorkspaceRefused("needs_worktree", f"writer branch {writers[0]}: the run has no worktree")
            rec = WorkspaceRecord.from_json(ws)
            run_path = Path(rec.path)
            gitmod.commit_all(run_path, f"tempergraph: checkpoint before {join}")
            rec = cut_writers(rec, self.ctx.thread, writers, self.ctx.spec.worktree, self.ctx.state_root,
                              read_include=self.ctx.read_worktreeinclude)
            rec.last_head = gitmod.head(run_path)
        except (WorkspaceRefused, gitmod.GitError) as exc:
            word = exc.word if isinstance(exc, WorkspaceRefused) else "git_failed"
            self.ctx.log.write("engine_error", unit=join, error="workspace_refused", detail=f"{word}: {exc}")
            raise Drain("workspace_refused") from None
        return {"workspace": rec.to_json()}

    def _merge_writers(self, join: str, state: Mapping[str, Any]) -> tuple[dict[str, Any] | None, dict[str, Any]]:
        """WSP-B11, WSP-B12: merge each writer branch into the run branch without fast-forward, in the order the
        parallel unit names them. A conflict (or a merge git refuses) puts the run branch back at the commit it held
        before the first merge. Returns the new workspace record, or None with what the attempt records."""
        return self._merge_children(state, [(u, u, f"Merge writer branch {u} of {join}")
                                            for u in flow.writer_branches(self.ctx.spec, join)])

    def _merge_items(self, unit: str, state: Mapping[str, Any], ids: Sequence[str], visit: int = 1
                     ) -> tuple[dict[str, Any] | None, dict[str, Any]]:
        """WSP-B11, WSP-B12: the same merge for the items of a writing concurrent map, in the order of the list; only the
        children cut for `visit` are merged (WSP-B22)."""
        return self._merge_children(state, [(mapping.slot(unit, i), i, f"Merge map item {i} of {unit}") for i in ids],
                                    visit)

    def _merge_children(self, state: Mapping[str, Any], order: Sequence[tuple[str, str, str]], visit: int = 1
                        ) -> tuple[dict[str, Any] | None, dict[str, Any]]:
        """Merge the children of the workspace record named by `order` (the child's unit, the name it is told by, the
        merge message), one after the other, without fast-forward. A child is matched by its unit and its `visit`."""
        rec = WorkspaceRecord.from_json(dict(state.get("workspace") or {}))
        run_path = Path(rec.path)
        children = {str(c.get("unit")): c for c in rec.children if int(c.get("visit", 1)) == visit}
        before = gitmod.head(run_path)
        for key, label, message in order:
            child = children.get(key)
            if child is None:
                continue
            try:
                gitmod.commit_all(Path(str(child["path"])), f"tempergraph: work of {label}")  # what the session left
                paths = gitmod.merge_no_ff(run_path, str(child["branch"]), message)
                failure = ""
            except gitmod.GitError as exc:
                paths, failure = [], str(exc)
            if paths or failure:
                gitmod.merge_abort(run_path)
                gitmod.reset_hard(run_path, before)
                return None, {"escalate": "merge_conflict", "conflicts": paths, "conflict_branch": label,
                              "merge_error": failure}
        rec.last_head = gitmod.head(run_path)
        return rec.to_json(), {}

    def _boundary(self, state: Mapping[str, Any]) -> None:
        reason = self.ctx.drain_requested()
        if reason:
            raise Drain(reason)
        if self.ctx.attempts_started >= self.ctx.attempt_cap:
            raise Drain("attempt_cap")
        cap = self.ctx.spec.run_cost_cap_usd
        if cap is not None and CostTotals.from_json((state.get("run") or {}).get("cost")).figure() >= cap:
            raise Drain("cost_cap")

    def _council_boundary(self, state: Mapping[str, Any], accrued: float) -> None:
        """The check made before an attempt (BUD-B9), for a council session that runs alone: the chair, once the members have
        spent what this attempt's state does not hold yet."""
        reason = self.ctx.drain_requested()
        if reason:
            raise Drain(reason)
        cap = self.ctx.spec.run_cost_cap_usd
        if cap is not None and CostTotals.from_json((state.get("run") or {}).get("cost")).figure() + accrued >= cap:
            raise Drain("cost_cap")

    def _hold(self, unit: str, state: Mapping[str, Any], width: int | None = None) -> dict[str, Any] | None:
        """What a session of `unit` needs to take a reservation (BUD-B12): a branch of a parallel block, an item of a
        concurrent map, or a member or chair session of a council (its `width` is the members of the round, 1 for a session
        that runs alone), in a run with a cost cap. Other units run one session at a time and keep the BUD-B9 check."""
        spec = self.ctx.spec
        cap = spec.run_cost_cap_usd
        block = flow.block_of(spec, unit)
        held = mapping.item_in_hand(state)
        if cap is None or (block is None and held is None and width is None):
            return None
        if width is None and held is not None and spec.units[unit].contest is not None:  # a slot of a contest: the
            c = spec.units[unit].contest  # slots that may run at once share the cap, the lower of `concurrency` and the
            assert c is not None  # slot count (BUD-B12)
            width = min(c.concurrency, max(len(flow.slot_names(spec, unit)), 1))
        elif width is None and held is not None:  # an item of a concurrent map: the items that may run at once share the cap
            m = spec.units[unit].map
            assert m is not None
            width = min(m.concurrency, max(len(mapping.record(state, unit).get("items") or []), 1))
        elif width is None:
            assert block is not None
            width = len(spec.units[block].branches)
        totals = CostTotals.from_json((state.get("run") or {}).get("cost"))
        return {"cap": float(cap), "width": width, "snapshot": totals.sessions, "spent": totals.figure()}

    def _session(self, ex: Executor, req: SessionRequest, judge_views: Any = None,
                 lessons_digest: str | None = None, extra: Mapping[str, Any] | None = None,
                 hold: Mapping[str, Any] | None = None) -> tuple[SessionResult, list]:
        """One session with infra tries and backoff outside the retry budget (BUD-B1, JDG-B5). With `hold`, each
        try takes a reservation first and gives it back, replaced by its real cost, when it ends (BUD-B12)."""
        results: list[SessionResult] = []
        if req.kind in ("step", "retry"):  # the rendered prompt, kept local for the session review (SRV-B17)
            from tempergraph.improve.record import write_prompt

            write_prompt(self.ctx.state_root, self.ctx.spec.name, self.ctx.task_id, req.session_key, req.prompt)
        key = req.session_key
        started = ""
        if req.kind in ("step", "retry"):  # SIL-B33: the commit the session started from
            with contextlib.suppress(Exception):
                started = gitmod.head(req.workdir)
        for n in range(self.ctx.infra_tries):
            if hold is not None:
                reason = self.ledger.acquire(
                    key, snapshot=hold["snapshot"], spent_usd=hold["spent"], cap_usd=hold["cap"],
                    amount=lambda spent: reserve.session_amount(req.options.cost_cap_usd, hold["cap"], spent,
                                                                hold["width"]),
                    write=lambda action, **fig: self.ctx.log.write("reservation", action=action, session_key=key,
                                                                   **fig),
                    drain=self.ctx.drain_requested)
                if reason:
                    raise Drain(reason)
            try:
                sink = session_sink(self.ctx.log, req, ex.name, tool_inputs=self.ctx.capture.tool_inputs)
                self.ctx.log.write("attempt_start", session_key=req.session_key, kind=req.kind, executor=ex.name,
                                   alias=req.alias, timeout_s=req.timeout_s,
                                   prompt_digest=hashlib.sha256((req.prompt or "").encode()).hexdigest()[:16],
                                   **{k: extra[k] for k in ("sources", "ladder") if extra and k in extra})
                try:
                    if judge_views is None:
                        res = ex.run_step(req, sink)
                    else:
                        res = ex.run_judge(req, judge_views, sink)
                finally:
                    sink.close()
                    if not self.ctx.capture.raw and req.session_dir is not None:  # `observe.raw = off` (LOS-B17)
                        with contextlib.suppress(OSError):
                            (req.session_dir / "raw.jsonl").unlink(missing_ok=True)
                if res.usage.estimated_cost_usd is None:
                    res.usage.estimated_cost_usd = estimate(res.usage, res.model)
                results.append(res)
                self.ctx.log.write("agent_run", session_key=req.session_key, kind=req.kind, executor=ex.name,
                                   alias=req.alias, usage=res.usage, ok=res.ok,
                                   tools=[c.name for c in res.tool_calls],
                                   cli_version=res.cli_version, session_id=res.session_id,
                                   unknown_tools=sorted({c.name for c in res.tool_calls
                                                         if not ex.capabilities().knows_tool(c.name)}),
                                   infra_cause=str(res.infra_cause) if res.infra_cause else None,
                                   error_kind=res.error_kind, timed_out=res.timed_out, stalled=res.stalled,
                                   usage_limit=res.usage_limit, usage_limit_resets_at=res.usage_limit_resets_at,
                                   duration_s=res.duration_s, tool_wall_share=res.tool_wall_share,
                                   slow_host=bool(res.timed_out and res.tool_wall_share >= 0.6),
                                   **({"lessons_digest": lessons_digest} if lessons_digest else {}),
                                   **({"wrote_paths": self._wrote_paths(req, started)}
                                      if req.kind in ("step", "retry") else {}),
                                   **dict(extra or {}))
                if hold is not None:
                    spent = CostTotals()
                    spent.add(res.usage)
                    self.ledger.release(key, snapshot=hold["snapshot"], real_usd=spent.figure())
            finally:
                if hold is not None:
                    self.ledger.release(key, snapshot=hold["snapshot"], real_usd=0.0)  # a no-op once released
            if res.infra_cause is None or n + 1 >= self.ctx.infra_tries or (res.usage_limit and not res.ok):
                break  # a usage-limit refusal is never rerun after a backoff (BUD-B17)
            self.ctx.sleep(min(BACKOFF_S[min(n, len(BACKOFF_S) - 1)], self.ctx.backoff_max_s))
        return results[-1], results

    @staticmethod
    def _wrote_paths(req: SessionRequest, started: str) -> list[str]:
        """SIL-B33: the files that differ from the commit the session started from, committed or not, by any tool or
        command; empty when git cannot say."""
        try:
            return gitmod.changed_paths(req.workdir, started or None)
        except Exception:  # noqa: BLE001 - observability never changes the run (OVR-B4)
            return []

    def _cost(self, state: Mapping[str, Any], results: list[SessionResult]) -> dict[str, Any]:
        totals = CostTotals.from_json((state.get("run") or {}).get("cost"))
        base = dict(totals.to_json()["counters"])  # what this writer read: the reducer adds only its delta
        for r in results:
            totals.add(r.usage)
        return {**totals.to_json(), "_base": base}

    # -- council (CNL-B13 to CNL-B15): the nodes of the subgraph that is a council's step node --------------------

    def council_open(self, unit: str, state: Mapping[str, Any]) -> Any:
        from tempergraph.run import council_run

        return council_run.open_run(self, unit, state)

    def council_member(self, run: Any, name: str, stage: int) -> None:
        run.member(name, stage)

    def council_close(self, run: Any, stage: int) -> int:
        return int(run.close(stage))

    def council_tally(self, run: Any) -> None:
        run.tally_now()

    def council_chair(self, run: Any) -> None:
        run.chair_now()

    def council_finish(self, run: Any) -> dict[str, Any]:
        return dict(run.finish())

    # -- step ------------------------------------------------------------------------------------

    def _skey(self, unit: str, attempt: int, kind: str, item: str | None = None) -> str:
        return self.ctx.key_prefix + session_key(unit, attempt, kind, item=item)

    def step(self, unit: str, state: RunState, config: Any = None) -> dict[str, Any]:
        spec = self.ctx.spec
        u = spec.units[unit]
        self._boundary(state)
        if u.kind == "subworkflow":  # SWF-B1: the child runs as one unit, on a graph and state of its own
            from tempergraph.run import subrun

            return subrun.run_child(self, unit, state, config)
        if u.kind == "script":
            return self._script_unit(unit, state)
        if u.kind in ("route", "switch"):
            return self._flow_unit(unit, state)
        if u.kind in ("ask", "wait"):
            return self._person_unit(unit, state)
        if u.kind == "parallel":
            return self._join_unit(unit, state)
        if u.kind == "contest" and mapping.item_in_hand(state) is None:  # CTS-B6: the slots run from the unit's own node
            return self._contest_step(unit, state)
        if u.extra.get("outcome"):
            return self._outcome_step(unit, state)
        st = u.step
        assert st is not None
        prev = (state.get("attempts") or {}).get(unit) or {}
        visit = int(((state.get("visits") or {}).get(unit) or {}).get("visit", 1))
        counters = (state.get("counters") or {}).get(unit) or {}
        entered = prev.get("visit") != visit
        workdir = self._workdir(state, unit)
        path_units = list(((state.get("run") or {}).get("path") or {}).get("units") or [])
        sent = mapping.item_in_hand(state)  # an item of a concurrent map: the unit's own entry was logged by its step node
        if entered and sent is None:
            fp = gitmod.fingerprint(workdir)
            self.ctx.log.write("unit_entered", unit=unit, visit=visit, head_commit=fp.head, dirty=fp.dirty,
                               entered_from=_entered_from(state, unit))
        item: dict[str, Any] | None = None
        maps: dict[str, Any] = {}
        if (u.map is not None or u.contest is not None) and sent is not None:  # the item or slot the node was sent
            m, item = self._concurrent_item(unit, state, sent["id"])  # its own attempt count
            maps = {unit: m}
        elif u.map is not None:  # the list is read once per visit; the item in hand is the first not passed
            done, m, item = self._map_item(unit, state, visit, workdir, prev, path_units)
            if done is not None:
                return done
            assert item is not None
            maps = {unit: m}
        iid = item["id"] if item else None
        first = entered or prev.get("item") != iid
        entry_head = ""  # SRV-B35: the commit an item's first attempt of the visit started from, carried by its retries
        if u.map is not None:
            if first:
                with contextlib.suppress(Exception):
                    entry_head = gitmod.head(workdir)
            else:
                entry_head = str(prev.get("entry_head") or "")
        attempt = int(item["attempt"]) if item else int(prev.get("attempt", 0)) + 1
        again = prev.get("reuse") if (item is None and prev.get("escalate") == "usage_limit"
                                      and prev.get("usage_limit_stage") == "step" and prev.get("visit") == visit
                                      and isinstance(prev.get("reuse"), Mapping)) else None
        if again is not None:  # DUR-B12: the session the limit ended runs again, as that attempt and with its inputs
            attempt, first = int(prev["attempt"]), bool(again["first"])
        else:
            self.ctx.count_attempt(unit, iid, attempt, visit)
        ov, layer = gatemod.arm_overrides(spec, unit, state)  # below the operator layers (SWM-B6, RST-B22, RST-B23)
        ov = {k: v for k, v in ov.items() if k in ("model", "timeout_s", "idle_s", "effort")
              and k not in (u.extra.get("operator_set") or ())}
        sources = {k: layer for k in ov}
        # one alias per attempt: release 1's retry-count list is retired (LAD-B18) and validation refuses it
        alias = (_aliases(ov.get("model")) or _aliases(st.model) or _aliases(spec.model_profile.get(unit)) or ["inherit"])[0]
        full_ov, _ = gatemod.arm_overrides(spec, unit, state)
        rungs, pinned = laddermod.rungs_of(u, full_ov)
        rung = laddermod.held_rung(counters, visit, iid) if rungs and not pinned else 0
        climb: dict[str, Any] | None = None
        if rungs and not pinned:  # the effort of this attempt is its rung's (LAD-B9); a pin switches it off
            ov["effort"] = rungs[rung]
            sources["effort"] = f"ladder:effort[{rung}]"
        held = counters.get("ladder") or {}
        up = held.get("escalate") if held.get("visit") == visit and held.get("item") == iid and not first else None
        if up:  # LAD-B12: one attempt on the tier above, at the escalation's effort
            alias = str(up["to"])
            sources["model"] = "escalation:+1"
            if up.get("effort"):
                ov["effort"] = up["effort"]
                sources["effort"] = "escalation:+1"
        if item and u.map is not None and u.map.item_model is not None:
            try:
                chosen = str(u.map.item_model.resolve()(MapItem(id=item["id"], text=item["text"])))
            except Exception as exc:  # noqa: BLE001 - a workflow fault, recorded
                chosen = f"<{type(exc).__name__}>"
            if chosen not in u.map.models:  # MAP-B8, MAP-B10, MAP-B9: the attempt fails before launch
                self.ctx.log.write("engine_error", unit=unit, item=iid, error="item_model",
                                   detail=f"{chosen!r} is not one of {list(u.map.models)}")
                record: dict[str, Any] = {
                    "attempt": attempt, "visit": visit, "item": iid, "ok": False, "text": "", "issues": [],
                          "tools": [], "session_id": None, "error_kind": "item_model", "infra_spent": False,
                          "check": None, "escalate": "workflow_fault", "timed_out": False,
                          "entry_head": entry_head}
                return {"attempts": {unit: record}, "maps": maps}
            alias = chosen
        slot_spec = self._slot_spec(unit, iid) if u.contest is not None else None  # CTS-B6: this slot's own overrides
        if slot_spec is not None and slot_spec.model and not up and "model" not in (u.extra.get("operator_set") or ()):
            alias = slot_spec.model
        ex = self.ctx.registry.get((slot_spec.executor if slot_spec is not None else None) or st.executor
                                   or spec.default_executor)
        caps = ex.capabilities()
        fields = self._fields(unit, state, attempt, visit, workdir)
        if item:  # VAL-B8 item keys
            fields.update(item_id=item["id"], item_index=str(item["index"]), item_count=str(item["count"]),
                          item=item["text"])
        failed, env, hybrid = self._scripts(st.before, unit, attempt, "before", state, workdir)
        fields.update(hybrid)  # a `before` script's keys are the session's to read (SCR-B5)
        if failed is not None:
            return self._script_failed(unit, state, attempt, visit, failed, env, path_units, first, hybrid, entry_head)
        judged = (state.get("judgements") or {}).get(unit) or {}
        fb = (state.get("feedback") or {}).get(unit) or {}
        retry = not first and bool(prev)
        prev_unit = self._previous_unit(unit, path_units)
        prev_judged = ((state.get("judgements") or {}).get(prev_unit) or {}) if prev_unit else {}
        notes = tuple(prev_judged.get("notes") or ()) if first else ()
        lessons_text = lessonsmod.block(lessonsmod.load(spec, unit))
        prior_check = prev.get("check") if retry else None  # BUD-B16: the previous attempt's failing check, same visit and item
        # what the attempt's prompt is made from; a refused attempt keeps it, because the judge node overwrites the
        # judgement and the gate clears one-time feedback before the rerun (DUR-B12)
        inputs: dict[str, Any] = dict(again) if again is not None else {
            "first": first, "retry": retry,
            "blockers": [dict(b) for b in (judged.get("blockers") or [])] if retry else [],
            "check_evidence": str(((prev.get("check") or {}).get("evidence")) or "") if retry else "",
            "previous_report": str(prev.get("text") or "") if retry else "",
            "paths_only": retry and bool(prev.get("cut_off")),
            "notes": [*notes, *([str(fb.get("text"))] if fb.get("as") == "notes" else [])],
            "visit_reason": str(((state.get("visits") or {}).get(unit) or {}).get("reason") or "") if first else "",
            "visit_from": str(((state.get("visits") or {}).get(unit) or {}).get("from") or "") if first else "",
            "feedback": str(fb.get("text") or "") if fb.get("as") == "feedback" else "",
            "prior_failing": {"findings": [{k: f.get(k) for k in ("criterion", "place", "message")}
                                           for f in prior_check.get("findings") or [] if f.get("status") == "fail"],
                              "evidence": str(prior_check.get("evidence") or "")}
            if isinstance(prior_check, Mapping) and prior_check.get("result") == "FAIL"
            and not prior_check.get("environmental") else None}
        retry = bool(inputs["retry"])
        ctx = AttemptContext(
            template=load_text(spec, st.prompt), fields=fields, attempt=attempt, retry=retry, lessons=lessons_text,
            blockers=tuple(Blocker(criterion=str(b.get("criterion", "")), place=str(b.get("place", "")),
                                   problem=str(b.get("problem", "")), fix=str(b.get("fix", "")))
                           for b in inputs["blockers"]),
            check_evidence=str(inputs["check_evidence"]), previous_report=str(inputs["previous_report"]),
            paths_only=bool(inputs["paths_only"]), notes=tuple(str(n) for n in inputs["notes"]),
            visit_reason=str(inputs["visit_reason"]), visit_from=str(inputs["visit_from"]),
            feedback=str(inputs["feedback"]),
            rulings=tuple(gatemod.active_rulings(spec, state, unit)),
            upstream_targets=tuple(u.gate.back_targets))
        commands = expand_commands(st.commands, workdir)  # `@repository`: what the repository declares (CHK-B11)
        shown = u if commands == tuple(st.commands) else dataclasses.replace(
            u, step=dataclasses.replace(st, commands=commands))
        ticket: str | None = None
        if st.self_check and u.gate.check is not None:  # CHK-B17: a ticket for this attempt only
            from tempergraph.run import selfcheck

            ticket = selfcheck.issue(
                self.ctx.state_root, u.gate,
                self._check_context(unit, state, {"item": iid, "attempt": attempt, "visit": visit}, workdir,
                                    sub="-preview"), thread=self.ctx.thread, limit=self.ctx.self_check_limit,
                base_branch=str((state.get("workspace") or {}).get("base_branch") or ""))
            ctx = dataclasses.replace(ctx, self_check=selfcheck.command(ticket))
        rendered = render_step(unit, shown, ctx, caps)
        prompt = rendered.text
        if slot_spec is not None and slot_spec.prompt_variant:  # CTS-B6: appended under its fixed heading
            prompt += "\n\n## Approach for this attempt\n" + slot_spec.prompt_variant.strip() + "\n"
        key = self._skey(unit, attempt, "retry" if retry else "step", item=iid)
        req = SessionRequest(
            kind="retry" if retry else "step", prompt=prompt, workdir=workdir, alias=alias, session_key=key,
            tools=tuple(st.tools), commands=(*commands, *([ctx.self_check] if ctx.self_check else [])),
            timeout_s=ov.get("timeout_s") or st.timeout_s or DEFAULT_TIMEOUT_S,
            idle_s=ov.get("idle_s") or st.idle_s,
            options=dataclasses.replace(st.session_options or SessionOptions(),
                                        **({"effort": ov["effort"]} if "effort" in ov else {})),
            session_dir=session_dir(self.ctx.state_root, spec.name, self.ctx.task_id, key),
            enforce_tools=self.ctx.enforce_tools, in_engine_worktree=self._in_worktree(state),
            plugin_dir=spec.package_root)
        if rungs or up or laddermod.escalation_of(u, full_ov) is not None:
            last = (counters.get("ladder") or {}) if not first else {}
            climb = {"rung": rung, "effort": req.options.effort, "alias": alias,
                     "source": "escalation:+1" if up else "operator" if pinned else f"ladder:effort[{rung}]"
                     if rungs else "declared",
                     "evidence": last.get("evidence"), "held_by": last.get("held_by")}
            if up:
                climb["taken_by"] = up.get("taken_by")
        extra: dict[str, Any] = {"sources": sources} if sources else {}
        if climb:
            extra["ladder"] = climb
        before = gitmod.fingerprint(workdir)
        known = self._workspace_paths(state)
        worktrees_before = scan_foreign_worktrees(self.ctx.main_checkout, known) if self.ctx.main_checkout else {}
        try:
            res, results = self._session(ex, req, lessons_digest=lessonsmod.digest(lessons_text),
                                         extra=extra or None, hold=self._hold(unit, state))
        finally:
            if ticket is not None:  # the ticket ends with its attempt; one record a preview (CHK-B17 Record)
                from tempergraph.run import selfcheck

                for call in selfcheck.close(self.ctx.state_root, ticket):
                    self.ctx.log.write("self_check", unit=unit, item=iid, attempt=attempt, result=call.get("result"),
                                       findings=call.get("findings"), duration_s=call.get("duration_s"))
        if res.partial and not res.ok:  # RCT-B11: a session the stop request ended is no failed attempt; none is recorded,
            reason = self.ctx.drain_requested()  # so no retry is charged and a resume runs the attempt again
            if reason:
                raise Drain(reason)
        after = gitmod.fingerprint(workdir)
        foreign = self._foreign_worktrees(unit, iid, key, known, worktrees_before)  # WTR-B26: recorded, never touched
        parsed = parse_output(res.text, st.produces, tuple(u.gate.back_targets))
        after_failed, after_env = None, False
        if res.ok and st.after:
            after_failed, after_env, after_arts = self._scripts(st.after, unit, attempt, "after", state, workdir)
            hybrid.update(after_arts)
        escalate: str | None = None
        reach = tool_access.refused(unit, st, caps, res.denied, res.tools_at_start)
        limited = bool(res.usage_limit and not res.ok)
        if limited:
            escalate = "usage_limit"  # BUD-B17: spends no retry and no infra try, whatever else the result says
        elif res.error_kind in ("auth", "refused"):
            escalate = res.error_kind
        elif reach and (not res.ok or parsed.blocked):
            escalate = "tool_access"  # no retry spent; the pause offers the grants (BUD-B1, BUD-B11, RST-B28, RST-B29, RST-B30)
        elif parsed.blocked:
            escalate = "blocked"
        elif parsed.upstream:
            escalate = "upstream"
        prior_failing = inputs["prior_failing"]
        record = {
            "item": iid, "prior_failing": prior_failing, "session_key": key,  # the check reads this session's journal (CHK-B24)
            "visit_keys": [*([] if first else [str(k) for k in prev.get("visit_keys") or ()]), key],  # VSR-B1
            "attempt": attempt, "visit": visit, "ok": res.ok, "text": clip(scrub(res.text), 8000), "blocked": parsed.blocked, "upstream": parsed.upstream,
            "issues": parsed.issues, "infra_cause": str(res.infra_cause) if res.infra_cause else None,
            "infra_spent": res.infra_cause is not None and not limited, "timed_out": res.timed_out, "stalled": res.stalled,
            "error_kind": res.error_kind, "denied": list(res.denied), "tools": [c.name for c in res.tool_calls],
            "tool_access": reach,
            "session_id": res.session_id, "executor": ex.name, "alias": alias, "model": res.model,
            "changed": before != after, "escalate": escalate, "cut_off": res.partial, "check": None,
            "duration_s": res.duration_s, "tool_wall_share": res.tool_wall_share,
            "slow_host": res.timed_out and res.tool_wall_share >= 0.6, "missing_fields": rendered.missing_fields,
            **({"entry_head": entry_head} if u.map is not None else {}),
        }
        if limited:
            record.update(usage_limit_resets_at=res.usage_limit_resets_at, usage_limit_stage="step", reuse=inputs)
        else:  # the merge deletes a key written as None: nothing of an earlier refusal stays
            record.update(usage_limit_resets_at=None, usage_limit_stage=None, reuse=None)
        esc_spec = laddermod.escalation_of(u, full_ov)
        if up:
            record.update(escalated=True, escalated_to=alias)
        elif esc_spec is not None:  # E6: what this attempt's tokens would cost one tier up (OBS-B10 to OBS-B13 prices)
            priced = estimate(res.usage, laddermod.TIER_FAMILY.get(laddermod.tier(esc_spec.to)))
            usages = [*(prev.get("up_estimates") or [])] if not first else []
            record["up_estimates"] = [*usages, priced][-5:]
        if foreign:
            record.update(foreign_worktrees=foreign, warnings=[f"foreign_worktree: {rel}" for rel in foreign])
        if u.contest is not None:  # the slot's own step cost: the attempt's cost cap and the pick read it (CTS-B6, CTS-B7)
            spent = CostTotals()
            for r in results:
                spent.add(r.usage)
            record["cost_usd"] = spent.figure()
        if record["slow_host"]:
            record.update(infra_cause="slow_host", infra_spent=False)
        if res.ok and before != after and (flow.block_of(spec, unit) or sent is not None) \
                and self._writer_child(state, unit) is None:
            # WSP-B11: a read-only branch or item changes nothing in the run worktree; a writer's fingerprint is its own
            record.update(ok=False, error_kind="branch_changed_the_workspace")
        if after_failed is not None:
            record.update(ok=False, error_kind=f"script_failed:{after_failed}",
                          escalate="environmental" if after_env else record["escalate"])
        run: dict[str, Any] = {"cost": self._cost(state, results),
                               "executors": {**((state.get("run") or {}).get("executors") or {}),
                                             ex.name: res.cli_version}}
        if entered and unit not in path_units:
            run["path"] = {"units": path_units + [unit]}
        arts: dict[str, Any] = {**hybrid, **parsed.artifacts}
        vals: dict[str, Any] = dict(parsed.values)
        seen = {"facts": {unit: {"foreign_worktrees": foreign}}} if foreign else {}  # the check and the judge read it
        if iid:  # an item's keys are kept as `<key>[<item id>]`; the plain key is the item in hand (MAP-B8, MAP-B9, MAP-B10)
            arts.update({mapping.item_key(k, iid): v for k, v in list(arts.items())})
            vals.update({mapping.item_key(k, iid): v for k, v in list(vals.items())})
            return {"attempts": {unit: record}, "artifacts": {unit: arts} if arts else {},
                    "values": {unit: vals} if vals else {}, "run": run, "maps": maps, **seen}
        return {"attempts": {unit: record}, "artifacts": {unit: arts or None},
                "values": {unit: vals or None}, "run": run, **seen}  # feedback is cleared at the gate

    @staticmethod
    def _concurrent_item(unit: str, state: Mapping[str, Any], iid: str) -> tuple[dict[str, Any], dict[str, Any]]:
        """The item a concurrent map's node was sent: its `maps` write (its attempt count, which continues across
        visits so session keys never repeat) and the item with its index and attempt (MAP-B9)."""
        m = mapping.record(state, unit)
        items = m.get("items") or []
        at = next(i for i, it in enumerate(items, start=1) if it["id"] == iid)
        n = int(m.get(f"n:{iid}", 0)) + 1
        return {f"n:{iid}": n}, {**items[at - 1], "index": at, "count": len(items), "attempt": n}

    # -- the contest (CTS-B6 to CTS-B10) ----------------------------------------------------------

    def _slot_spec(self, unit: str, name: str | None) -> SlotSpec | None:
        c = self.ctx.spec.units[unit].contest
        if c is None or isinstance(c.slots, int):
            return None
        return next((s for s in c.slots if s.name == name), None)

    @staticmethod
    def _slot_view(state: Mapping[str, Any], unit: str, name: str) -> Any:
        """The state a slot's step or judge reads: the slot's own record in the place the unit's would be, and a person's
        feedback for the unit, which no slot of its own holds."""
        view = item_view(state, unit, name)
        own = (state.get("feedback") or {}).get(unit)
        if own and unit not in (view.get("feedback") or {}):
            view["feedback"] = {**(view.get("feedback") or {}), unit: own}
        return view

    def _each(self, names: Sequence[str], width: int, work: Callable[[str], None]) -> None:
        """Run `work` for each name, up to `width` at once and the next as one ends; the first failure is raised once every
        started name has ended."""
        with ThreadPoolExecutor(max_workers=max(1, min(width, len(names) or 1)), thread_name_prefix="slot") as pool:
            futures = [pool.submit(work, n) for n in names]
        for f in futures:
            f.result()

    def _contest_step(self, unit: str, state: RunState) -> dict[str, Any]:
        """CTS-B6, CTS-B8: the step node of a contest. Its slots run the unit's step each in the state of its own, up to
        `concurrency` at once, and an unstarted slot is skipped once the attempt's cost has reached `cost_cap_usd`. A
        visit's first entry runs every slot; a retry runs the slots the retry scope names (CTS-B8). The grading and the
        pick are the judge node's."""
        spec = self.ctx.spec
        u = spec.units[unit]
        c = u.contest
        assert c is not None
        names = list(flow.slot_names(spec, unit))
        visit = int(((state.get("visits") or {}).get(unit) or {}).get("visit", 1))
        prev = (state.get("attempts") or {}).get(unit) or {}
        workdir = self._workdir(state)
        path_units = list(((state.get("run") or {}).get("path") or {}).get("units") or [])
        run = {"path": {"units": path_units + [unit]}} if unit not in path_units else {}
        m = mapping.record(state, unit)
        writes: dict[str, Any] = {}
        attempt = int(prev.get("attempt", 0)) + 1  # the unit's attempt in hand: a slot's worktree is cut for it (WSP-B20)
        if m.get("visit") != visit:  # a new visit: every slot runs, nothing of an earlier visit stands
            if prev.get("visit") != visit:
                fp = gitmod.fingerprint(workdir)
                self.ctx.log.write("unit_entered", unit=unit, visit=visit, head_commit=fp.head, dirty=fp.dirty,
                                   entered_from=_entered_from(state, unit))
            stale = {k: None for k in m if k.startswith("st:") or k in ("pick", "single", "round", "skipped")}
            writes["maps"] = {unit: {"visit": visit, "items": [{"id": n, "text": ""} for n in names], "passed": [],
                                     "attempt": attempt, **stale}}
            running = names
        else:  # a retry of this visit (CTS-B8)
            running = contestmod.retry_slots(names, m.get("single"))  # `best` after a retry: one step (CTS-B8, CTS-B4)
            writes["maps"] = {unit: {"attempt": attempt}}
        if flow.writer_contest(spec, unit):  # WSP-B19, WSP-B11, WSP-B20: the checkpoint, then a worktree per slot run
            writes["workspace"] = self._enter_writer_contest(unit, state, running, attempt)
        self._boundary(state)
        start = fold(dict(state), writes)
        cap = c.cost_cap_usd
        lock = threading.Lock()
        done: dict[str, dict[str, Any]] = {}
        skipped: list[str] = []
        spent = 0.0

        def work(name: str) -> None:
            nonlocal spent
            with lock:
                if cap is not None and spent >= cap:  # CTS-B6: the attempt's cost has reached the cap
                    skipped.append(name)
                    return
            body = self.step(unit, self._slot_view(start, unit, name))
            got = (body.get("attempts") or {}).get(unit) or {}
            with lock:
                spent += float(got.get("cost_usd") or 0.0)
                done[name] = slot_writes(body, unit, name)

        self._each(running, c.concurrency, work)
        out: dict[str, Any] = fold({}, writes)
        for name in running:
            if name in done:
                out = fold(out, done[name])
        base = {"attempt": attempt, "visit": visit, "ok": True, "text": "", "issues": [], "tools": [],
                "session_id": None, "escalate": None, "infra_spent": False, "check": None, "item": None,
                "timed_out": False, "contest": True}
        round_ = {"round": running, "skipped": [n for n in running if n in skipped], "attempt": attempt}
        return fold(out, {"attempts": {unit: base}, "run": run, "maps": {unit: round_}})

    def _enter_writer_contest(self, unit: str, state: Mapping[str, Any], names: Sequence[str], attempt: int = 1
                              ) -> dict[str, Any]:
        """WSP-B19, WSP-B11, WSP-B20: an attempt of a writing contest commits the run worktree's uncommitted changes on the
        run's branch, then cuts one worktree and branch per slot it runs (`names`) from that commit, named by the attempt
        (`--s-<slot>` for the first, `--s<attempt>-<slot>` after); the worktrees of earlier attempts are left as they are.
        A cut that fails ends the segment at this boundary (engine_error `workspace_refused`) with nothing left behind."""
        ws = dict(state.get("workspace") or {})
        try:
            if ws.get("mode") != "worktree":
                raise WorkspaceRefused("needs_worktree", f"writing contest {unit}: the run has no worktree")
            rec = WorkspaceRecord.from_json(ws)
            run_path = Path(rec.path)
            gitmod.commit_all(run_path, f"tempergraph: checkpoint before {unit}")
            rec = cut_writers(rec, self.ctx.thread, [mapping.slot(unit, n) for n in names], self.ctx.spec.worktree,
                              self.ctx.state_root, read_include=self.ctx.read_worktreeinclude, kind="s", visit=attempt)
            rec.last_head = gitmod.head(run_path)
        except (WorkspaceRefused, gitmod.GitError) as exc:
            word = exc.word if isinstance(exc, WorkspaceRefused) else "git_failed"
            self.ctx.log.write("engine_error", unit=unit, error="workspace_refused", detail=f"{word}: {exc}")
            raise Drain("workspace_refused") from None
        return rec.to_json()

    def _contest_judge(self, unit: str, state: RunState) -> dict[str, Any]:
        """CTS-B7, CTS-B2, CTS-B3, CTS-B9: the judge node of a contest. Each slot that ran is graded alone, on a view of its
        own: its check first, and a judge session only for a slot whose check passed, holding that slot's artifacts
        only. The slots that were not put out are ordered by the fixed rule (`run/contest.py`); the winner's artifacts
        and verdict become the unit's, and a `contest` record says so."""
        spec = self.ctx.spec
        u = spec.units[unit]
        c = u.contest
        assert c is not None
        names = list(flow.slot_names(spec, unit))
        m = mapping.record(state, unit)
        visit = int(((state.get("visits") or {}).get(unit) or {}).get("visit", 1))
        unit_att = dict((state.get("attempts") or {}).get(unit) or {})
        attempt = int(unit_att.get("attempt", 1))
        skipped = [n for n in names if n in (m.get("skipped") or [])]
        ran = [n for n in names if n in (m.get("round") or []) and n not in skipped]
        before = CostTotals.from_json((state.get("run") or {}).get("cost")).figure()
        lock = threading.Lock()
        bodies: dict[str, dict[str, Any]] = {}

        def grade(name: str) -> None:
            body = self._judge(unit, self._slot_view(state, unit, name))
            with lock:
                bodies[name] = body

        self._each(ran, c.concurrency, grade)
        out: dict[str, Any] = {}
        judged: dict[str, dict[str, Any]] = {}
        atts: dict[str, dict[str, Any]] = {}
        costs: dict[str, float] = {}
        for name in ran:
            body = bodies[name]
            out = fold(out, slot_writes(body, unit, name))
            judged[name] = dict((body.get("judgements") or {}).get(unit) or {})
            held = (state.get("attempts") or {}).get(mapping.slot(unit, name)) or {}
            atts[name] = {**held, **((body.get("attempts") or {}).get(unit) or {})}
            cost = (body.get("run") or {}).get("cost")
            mine = CostTotals.from_json(cost).figure() - before if cost else 0.0
            costs[name] = round(float(atts[name].get("cost_usd") or 0.0) + max(mine, 0.0), 6)
        infra = {n for n in ran if atts[n].get("infra_spent") or judged[n].get("infra_spent")}
        out_for = {n: (n in infra or (atts[n].get("check") or {}).get("result") == "FAIL"
                       or judged[n].get("reason") in ("step_failed", "output_contract")) for n in ran}
        cands = [contestmod.Candidate(slot=n, order=names.index(n), verdict=str(judged[n].get("verdict")),
                                      cost=costs[n], **{k: v for k, v in contestmod.keys_of(judged[n]).items()})
                 for n in ran if not out_for[n]]
        winner = contestmod.pick(cands)
        rows = []
        for n in names:
            if n in skipped:
                rows.append(contestmod.slot_row(names.index(n) + 1, n, skipped=True))
            elif n in ran:
                gone = out_for[n]
                rows.append(contestmod.slot_row(
                    names.index(n) + 1, n, attempt=atts[n].get("attempt"),
                    check=(atts[n].get("check") or {}).get("result"), verdict=None if gone else judged[n].get("verdict"),
                    keys=None if gone else contestmod.keys_of(judged[n]), cost=costs[n]))
        place = names.index(winner.slot) + 1 if winner is not None else None
        self.ctx.log.write("contest", unit=unit, visit=visit, attempt=attempt, winner=place, slots=rows)
        live = [n for n in ran if n not in infra]
        chosen = winner.slot if winner is not None else None
        if chosen is None:  # CTS-B9: every slot was put out; the first slot's FAIL is the unit's check result
            chosen = next((n for n in live if (atts[n].get("check") or {}).get("result") == "FAIL"), None) or (
                live[0] if live else (ran[0] if ran else None))
        verdict_att: dict[str, Any] = {**unit_att, "contest": True, "winner": winner.slot if winner else None,
                                       "item": None, "attempt": attempt, "visit": visit}
        if chosen is None:  # nothing ran: no slot started (cannot happen: the first slot always starts)
            unit_j: dict[str, Any] = {"verdict": str(Verdict.ESCALATE), "reason": "contest_no_slot"}
        elif winner is None and not live:  # CTS-B9: every slot failed on infrastructure
            verdict_att.update({k: v for k, v in atts[chosen].items() if k not in ("item", "attempt", "visit")})
            verdict_att.update(infra_spent=True, ok=False, item=None)
            unit_j = {"verdict": str(Verdict.ESCALATE), "reason": "infra", "confidence": 1.0,
                      "confidence_source": "engine_placeholder"}
        else:
            verdict_att.update({k: v for k, v in atts[chosen].items() if k not in ("item", "attempt", "visit")})
            verdict_att["item"] = None
            unit_j = {**judged[chosen], "winner": winner.slot if winner else None}
        extra: dict[str, Any] = {}
        if flow.writer_contest(spec, unit) and winner is not None:  # CTS-B5, CTS-B7: only the winner's worktree is merged
            merged, found = self._merge_children(state, [(mapping.slot(unit, winner.slot), winner.slot,
                                                          f"Merge contest slot {winner.slot} of {unit}")], attempt)
            verdict_att.update(found)
            if merged is None:  # CTS-B9: a failed winner merge is a writer join conflict, the run branch put back
                unit_j = {"verdict": str(Verdict.ESCALATE), "reason": "merge_conflict", "confidence": 1.0,
                          "confidence_source": "engine_placeholder", "blockers": [
                              {"criterion": "writer-branches", "place": p, "problem": f"conflicting change in {p}",
                               "fix": f"decide which change of contest slot {winner.slot} or the run's branch stays"}
                              for p in found.get("conflicts") or []] or [
                              {"criterion": "writer-branches",
                               "problem": str(found.get("merge_error") or "the merge failed")}]}
            else:  # the attempt's other slots' worktrees are discarded and their records kept; earlier attempts stand (WSP-B21)
                won = mapping.slot(unit, winner.slot)
                merged["children"] = [{**ch, "state": "discarded"} if str(ch.get("unit")).startswith(f"{unit}.")
                                      and ch.get("unit") != won and int(ch.get("visit", 1)) == attempt else ch
                                      for ch in merged.get("children") or []]
                extra["workspace"] = merged
        writes: dict[str, Any] = {**out, **extra}
        writes = fold(writes, {"attempts": {unit: verdict_att}, "judgements": {unit: unit_j},
                               "maps": {unit: {"pick": {"winner": winner.slot if winner else None,
                                                        "verdict": unit_j.get("verdict"),
                                                        "order": [x.slot for x in contestmod.ordered(cands)],
                                                        "attempt": attempt},
                                               "round": None, "skipped": None}}})
        if chosen is not None and winner is not None:  # the plain keys are the winner's (CTS-B7)
            for chan in ("artifacts", "values", "facts"):
                loose: Mapping[str, Any] = state
                was: Mapping[str, Any] = (loose.get(chan) or {}).get(unit) or {}
                now: Mapping[str, Any] = (out.get(chan) or {}).get(unit) or {}
                plain = own_keys({**was, **now}, winner.slot)
                if plain:
                    writes = fold(writes, {chan: {unit: plain}})
        return writes

    def _map_item(self, unit: str, state: Mapping[str, Any], visit: int, workdir: Path, prev: Mapping[str, Any],
                  path_units: list[str]) -> tuple[dict[str, Any] | None, dict[str, Any], dict[str, Any] | None]:
        """Fan-out at the start of a visit, then the item in hand (MAP-B8, MAP-B9, MAP-B10). Returns a finished state write
        when the list stops or skips the map, else the `maps` record and the item with its attempt number."""
        m = mapping.record(state, unit)
        run = {"path": {"units": path_units + [unit]}} if unit not in path_units else {}
        base = {"attempt": int(prev.get("attempt", 0)) + 1, "visit": visit, "ok": True, "text": "", "issues": [],
                "tools": [], "session_id": None, "escalate": None, "infra_spent": False, "check": None,
                "item": None, "timed_out": False}
        if m.get("visit") != visit:
            try:
                items = mapping.read_items(self.ctx.spec, unit, state, workdir)
            except mapping.MapFault as exc:
                self.ctx.log.write("map_items", unit=unit, visit=visit, count=exc.count, ids=[], error=exc.code,
                                   detail=str(exc))
                return ({"attempts": {unit: {**base, "ok": False, "map_fault": f"{unit}: {exc}"}}, "run": run},
                        m, None)
            m = {"visit": visit, "items": [{"id": i.id, "text": i.text} for i in items], "passed": [],
                 "attempts": dict(m.get("attempts") or {})}
            self.ctx.log.write("map_items", unit=unit, visit=visit, count=len(items), ids=[i.id for i in items])
            if not items:  # `on_empty: skip` passes the map with no item
                return {"attempts": {unit: {**base, "map_skip": True}}, "maps": {unit: m}, "run": run}, m, None
        item = mapping.pending(m)
        if item is None:  # every item passed already (a resume at the gate): nothing to run
            return {"attempts": {unit: {**dict(prev), "visit": visit}}, "maps": {unit: m}, "run": run}, m, None
        n = int((m.get("attempts") or {}).get(item["id"], 0)) + 1
        m["attempts"] = {**(m.get("attempts") or {}), item["id"]: n}
        return None, m, {**item, "attempt": n}

    def map_move(self, unit: str, state: RunState) -> Move:
        """MAP-B8 to MAP-B10, MAP-B12, MAP-B13: the step node of a concurrent map. It reads the list once per visit, sends
        the next `concurrency` items that have not started to the item nodes, waits while items run, sends the items
        that wait for a person to their pause once nothing else can run, and when every item has passed merges the
        items of a writing map and runs the map's check once on the result, then goes on to the unit's judge."""
        spec = self.ctx.spec
        u = spec.units[unit]
        assert u.map is not None
        visit = int(((state.get("visits") or {}).get(unit) or {}).get("visit", 1))
        prev = (state.get("attempts") or {}).get(unit) or {}
        judge_node = flow.node_names(unit)[1]
        workdir = self._workdir(state)
        path_units = list(((state.get("run") or {}).get("path") or {}).get("units") or [])
        run = {"path": {"units": path_units + [unit]}} if unit not in path_units else {}
        writes: dict[str, Any] = {}
        m = mapping.record(state, unit)
        if m.get("visit") != visit:  # a new visit: the list is read once, the items are all still to start
            self._boundary(state)
            if prev.get("visit") != visit:
                fp = gitmod.fingerprint(workdir)
                self.ctx.log.write("unit_entered", unit=unit, visit=visit, head_commit=fp.head, dirty=fp.dirty,
                                   entered_from=_entered_from(state, unit))
            base = {"attempt": int(prev.get("attempt", 0)) + 1, "visit": visit, "ok": True, "text": "", "issues": [],
                    "tools": [], "session_id": None, "escalate": None, "infra_spent": False, "check": None,
                    "item": None, "timed_out": False, "map_done": None, "map_skip": None, "map_fault": None}
            try:
                items = mapping.read_items(spec, unit, state, workdir)
            except mapping.MapFault as exc:
                self.ctx.log.write("map_items", unit=unit, visit=visit, count=exc.count, ids=[], error=exc.code,
                                   detail=str(exc))
                return Move({"attempts": {unit: {**base, "ok": False, "map_fault": f"{unit}: {exc}"}},
                                     "run": run}, goto=judge_node)
            self.ctx.log.write("map_items", unit=unit, visit=visit, count=len(items), ids=[i.id for i in items])
            stale = {k: None for k in m if k.startswith("st:") or k == "exit"}  # nothing of an earlier visit stands
            fresh = {"visit": visit, "items": [{"id": i.id, "text": i.text} for i in items], "passed": [],
                     **{k: v for k, v in m.items() if k.startswith("n:")}}  # attempt numbers continue across visits
            writes = {"attempts": {unit: base}, "maps": {unit: {**stale, **fresh}}, "run": run}
            m = {**{k: v for k, v in m.items() if k not in stale}, **fresh}
            if not items:  # `on_empty: skip` passes the map with no item
                writes["attempts"][unit]["map_skip"] = True
                return Move(writes, goto=judge_node)
            if flow.writer_map(spec, unit):  # WSP-B19, WSP-B11: the checkpoint, then one worktree per item
                writes["workspace"] = self._enter_writer_map(unit, state, [i.id for i in items], visit)
        standing = {it["id"]: mapping.item_state(m, it["id"]) for it in m["items"]}
        if "started" in standing.values():  # items that run finish first, whatever the others wait for
            return Move(writes)
        if m.get("exit"):  # an item stopped the map, or a person's rewind or a fallback left it (MAP-B10)
            return Move(writes, goto=str(m["exit"]["node"]))
        fresh_ids = [i for i, s in standing.items() if s is None]
        if fresh_ids:
            self._boundary(state)
            wave = fresh_ids[: u.map.concurrency]
            for iid in wave:
                at = mapping.slot(unit, iid)
                for channel in ("attempts", "judgements", "feedback", "pause"):
                    writes.setdefault(channel, {})[at] = None
                writes.setdefault("counters", {})[at] = {"retries": 0, "infra": 0, "human": 0, "ladder": None,
                                                         "loops": None}
                writes.setdefault("maps", {}).setdefault(unit, {})[f"st:{iid}"] = "started"
            return Move(writes, items=wave)
        parked = [i for i, s in standing.items() if s == "parked"]
        if parked:
            self._boundary(state)
            return Move(writes, items=parked, kind="human")
        return self._map_finish(unit, state, m, writes, prev, visit, judge_node)

    def _enter_writer_map(self, unit: str, state: Mapping[str, Any], ids: Sequence[str], visit: int = 1
                          ) -> dict[str, Any]:
        """WSP-B19, WSP-B11: entering a writing concurrent map commits the run worktree's uncommitted changes on the run's
        branch, then cuts one worktree per item from that commit, named for the map's `visit` (WSP-B20); the worktrees
        of earlier visits stay. A cut that fails ends the segment at this boundary (engine_error `workspace_refused`)
        with nothing left behind."""
        ws = dict(state.get("workspace") or {})
        try:
            if ws.get("mode") != "worktree":
                raise WorkspaceRefused("needs_worktree", f"writing map {unit}: the run has no worktree")
            rec = WorkspaceRecord.from_json(ws)
            run_path = Path(rec.path)
            gitmod.commit_all(run_path, f"tempergraph: checkpoint before {unit}")
            rec = cut_writers(rec, self.ctx.thread, [mapping.slot(unit, i) for i in ids], self.ctx.spec.worktree,
                              self.ctx.state_root, read_include=self.ctx.read_worktreeinclude, kind="i", visit=visit)
            rec.last_head = gitmod.head(run_path)
        except (WorkspaceRefused, gitmod.GitError) as exc:
            word = exc.word if isinstance(exc, WorkspaceRefused) else "git_failed"
            self.ctx.log.write("engine_error", unit=unit, error="workspace_refused", detail=f"{word}: {exc}")
            raise Drain("workspace_refused") from None
        return rec.to_json()

    def _map_finish(self, unit: str, state: Mapping[str, Any], m: Mapping[str, Any], writes: dict[str, Any],
                    prev: Mapping[str, Any], visit: int, judge_node: str) -> Move:
        """Every item has passed (MAP-B10): the plain keys hold the last item of the list, the items of a writing map are
        merged in the order of the list, and the gate's check runs once on the merged worktree (MAP-B12, MAP-B13). No
        model session starts here: a merge conflict or a failing check ends the map blocked, for a person."""
        spec = self.ctx.spec
        u = spec.units[unit]
        ids = [it["id"] for it in m["items"]]
        att: dict[str, Any] = {"attempt": int(prev.get("attempt", 0)) + 1, "visit": visit, "ok": True, "text": "",
                               "issues": [], "tools": [], "session_id": None, "escalate": None, "infra_spent": False,
                               "check": None, "item": None, "timed_out": False, "map_done": True, "conflicts": None,
                               "conflict_branch": None, "merge_error": None, "map_findings": None}
        writes.setdefault("attempts", {})[unit] = {**(writes.get("attempts") or {}).get(unit, {}), **att}
        writes.setdefault("maps", {}).setdefault(unit, {})["passed"] = ids
        last = f"[{ids[-1]}]"
        for channel in ("artifacts", "values", "facts"):  # the plain key holds the last item of the list (MAP-B9)
            held = (state.get(channel) or {}).get(unit) or {}
            plain = {k[: -len(last)]: v for k, v in held.items() if k.endswith(last)}
            if plain:
                writes.setdefault(channel, {})[unit] = plain
        if not flow.writer_map(spec, unit):
            return Move(writes, goto=judge_node)
        merged, found = self._merge_items(unit, state, ids, visit)
        record = writes["attempts"][unit]
        record.update(found)
        if merged is None:  # WSP-B12: the run branch is back where it was; no model session runs
            return Move(writes, goto=judge_node)
        writes["workspace"] = merged
        if u.gate.check is not None:  # MAP-B12: once, on the run's worktree, over the joined result, with no item
            cres, notes = self._check(unit, state, {**record, "item": None}, Path(str(merged["path"])))
            record["check"] = checkmod.to_json(cres)
            self.ctx.log.write("check", unit=unit, item=None, attempt=None, result=cres.result,
                               environmental=cres.environmental, evidence=clip(cres.evidence, 200), notes=notes)
            if cres.facts:
                writes.setdefault("facts", {}).setdefault(unit, {}).update(cres.facts)
            if cres.result == "FAIL":  # MAP-B13: blocked, not retried, the merge kept
                record["escalate"] = "map_check"
                record["map_findings"] = [{"criterion": f.criterion or "check", "place": f.place, "problem": f.message,
                                           "fix": f.fix} for f in cres.findings if f.status == "fail"] or [
                    {"criterion": "check", "problem": "check FAIL"}]
        return Move(writes, goto=judge_node)

    def _script_failed(self, unit: str, state: Mapping[str, Any], attempt: int, visit: int, name: str, env: bool,
                       path_units: list[str], first: bool, arts: dict[str, str], entry_head: str = ""
                       ) -> dict[str, Any]:
        """A failed `before` script fails the attempt with no session (SCR-B7, SCR-B2). An item of a map keeps the
        commit its first attempt started from, for the retry that follows (SRV-B35)."""
        record: dict[str, Any] = {
            "attempt": attempt, "visit": visit, "ok": False, "text": "", "issues": [], "tools": [],
            "session_id": None, "error_kind": f"script_failed:{name}", "infra_spent": False, "check": None,
            "escalate": "environmental" if env else None, "timed_out": False,
            **({"entry_head": entry_head} if entry_head else {})}
        run = {"path": {"units": path_units + [unit]}} if first and unit not in path_units else {}
        return {"attempts": {unit: record}, "artifacts": {unit: arts or None}, "run": run}

    def _previous_unit(self, unit: str, path_units: list[str]) -> str | None:
        before = [p for p in path_units if p != unit]
        return before[-1] if before else None

    def _fields(self, unit: str, state: Mapping[str, Any], attempt: int, visit: int, workdir: Path
                ) -> dict[str, str | None]:
        req = state.get("request") or {}
        out: dict[str, str | None] = {k: str(v) for k, v in (req.get("inputs") or {}).items()}
        ws = state.get("workspace") or {}
        out.update(task_id=self.ctx.task_id, thread_id=self.ctx.thread, workflow=self.ctx.spec.name, unit=unit,
                   attempt=str(attempt), visit=str(visit), branch=ws.get("branch") or gitmod.branch(workdir),
                   base=ws.get("base_branch") or "", workdir=str(workdir), run_label=None)
        for chan in ("artifacts", "values"):
            for owner, vals in (state.get(chan) or {}).items():
                if isinstance(vals, dict):
                    out.update({k: str(v) for k, v in vals.items()})
                    held = self.ctx.spec.units.get(owner)
                    if held is not None and held.kind == "subworkflow":  # SWF-B12: `{<unit>.<key>}`
                        out.update({f"{owner}.{k}": str(v) for k, v in vals.items()})
        out.update(self._map_lines(unit, state))
        return out

    def _map_lines(self, unit: str, state: Mapping[str, Any]) -> dict[str, str]:
        """VAL-B9: a key the step of a map before this unit produces renders one line `<item id>: <value>` for each
        item of the map's list that holds it, in list order, and `none` when no item does. An item's own template
        keeps the plain key."""
        order = list(self.ctx.spec.order)
        if unit not in order:
            return {}
        lines: dict[str, str] = {}
        for owner in order[: order.index(unit)]:
            held = self.ctx.spec.units.get(owner)
            if held is None or held.map is None or held.step is None:
                continue
            items = [str(it["id"]) for it in ((state.get("maps") or {}).get(owner) or {}).get("items") or []]
            for key in held.step.produces:
                found: list[str] = []
                for item in items:
                    for chan in ("artifacts", "values"):
                        got = ((state.get(chan) or {}).get(owner) or {}).get(f"{key}[{item}]")
                        if got is not None:
                            found.append(f"{item}: {got}")
                            break
                lines[key] = "\n".join(found) or "none"
        return lines

    # -- script units (SCR) ------------------------------------------------------------------------

    def _run_script(self, sc: ScriptSpec, unit: str, attempt: int, phase: str, state: Mapping[str, Any],
                    workdir: Path) -> tuple[bool, bool, dict[str, str]]:
        """One script through the command runner or its callable (SCR-B5); returns ok, environmental, artifacts."""
        t0 = time.monotonic()
        artifacts: dict[str, str] = {}
        ok, env, exit_code = True, False, None
        name = sc.name or (sc.run[0] if sc.run else unit)
        cache_key, cache_error = None, None
        folder = self.ctx.state_root / "runs" / self.ctx.spec.name / self.ctx.task_id / "cache"
        if sc.cache == "thread":  # SCR-B9: a hit restores the recorded files and result and runs nothing
            try:
                cache_key = self._script_key(sc, unit, state, workdir)
                hit = scriptcache.lookup(folder, cache_key, workdir)
            except (scriptcache.CacheError, OSError) as exc:  # an unreadable cache is a logged miss
                cache_key, hit, cache_error = None, None, type(exc).__name__
            if hit is not None:
                self.ctx.log.write("script", unit=unit, name=name, phase=phase, exit_code=hit.exit_code,
                                   command_prefix=sc.run[0] if sc.run else None,
                                   duration_s=round(time.monotonic() - t0, 3), environmental=False, cached=True,
                                   cache="hit")
                return True, False, {k: str(v) for k, v in hit.artifacts.items()}
        if sc.run:
            tag = unit if phase == "unit" else f"{unit}.{phase}.{name}"
            out = self.ctx.state_root / "runs" / self.ctx.spec.name / self.ctx.task_id / "scripts" / tag / f"{attempt}.out"
            r = run_command(ResolvedCommand(argv=sc.run, prefix=sc.run[0]), workdir, out, sc.timeout_s,
                            main=self.ctx.main_checkout)
            exit_code = r.exit_code
            ok = r.finished and r.exit_code == 0
            env = r.exit_code in sc.environmental_exit_codes or "error" in r.extra
            artifacts = parse_output(Path(out).read_text(encoding="utf-8", errors="replace") if Path(out).exists()
                                     else "", sc.produces).artifacts
        elif sc.call is not None:
            try:
                got = sc.call.resolve()(checkmod.CheckContext(
                    unit=unit, workdir=workdir, request=state.get("request") or {},
                    artifacts=state.get("artifacts") or {}, values=state.get("values") or {},
                    settings=dict(self.ctx.settings)))  # SCR-B5, RST-B25: what a check is given
                artifacts = {str(k): str(v) for k, v in (got or {}).items()} if isinstance(got, dict) else {}
            except Exception as exc:  # noqa: BLE001
                ok, env = False, True
                self.ctx.log.write("engine_error", unit=unit, error=type(exc).__name__)
        if cache_key is not None and ok and not env and all(k in artifacts for k in sc.produces):
            try:  # only a run that finished and succeeded is recorded
                scriptcache.store(folder, cache_key, scriptcache.Result(
                    exit_code=exit_code, artifacts=artifacts,
                    kinds={k: v if isinstance(v, str) else "value" for k, v in sc.produces.items()}), workdir)
            except scriptcache.CacheError as exc:
                cache_error = str(exc)
        extra: dict[str, Any] = {"cache": "miss"} if sc.cache == "thread" else {}
        if cache_error:
            extra["cache_error"] = cache_error
        self.ctx.log.write("script", unit=unit, name=name, phase=phase, exit_code=exit_code,
                           command_prefix=sc.run[0] if sc.run else None, duration_s=round(time.monotonic() - t0, 3),
                           environmental=env, cached=False, **extra)
        return ok, env, artifacts

    def _script_key(self, sc: ScriptSpec, unit: str, state: Mapping[str, Any], workdir: Path) -> str:
        """SCR-B9: the digest of the argv or callable reference, the workflow's content digest, the arguments and
        each declared input's content digest. The files this unit's earlier visits produced are not part of the
        workspace input: a restore puts them back."""
        from tempergraph.package.loader import full_version

        known: dict[str, str] = {k: str(v) for k, v in ((state.get("request") or {}).get("inputs") or {}).items()}
        for chan in ("artifacts", "values"):
            for vals in (state.get(chan) or {}).values():
                if isinstance(vals, dict):
                    known.update({k: str(v) for k, v in vals.items() if v is not None})
        own = {str(v) for v in ((state.get("artifacts") or {}).get(unit) or {}).values() if v is not None}
        inputs = {n: scriptcache.input_digest(n, workdir, self.ctx.state_root, known, own) for n in sc.inputs}
        return scriptcache.key(argv=(sc.run[0],) if sc.run else (), reference=sc.call.ref if sc.call else None,
                               workflow=full_version(self.ctx.spec), arguments=tuple(sc.run[1:]) if sc.run else (),
                               inputs=inputs)

    def _scripts(self, scripts: tuple[ScriptSpec, ...], unit: str, attempt: int, phase: str,
                 state: Mapping[str, Any], workdir: Path) -> tuple[str | None, bool, dict[str, str]]:
        """Hybrid `before` or `after` scripts in declaration order; the first failure ends the phase."""
        arts: dict[str, str] = {}
        for sc in scripts:
            ok, env, got = self._run_script(sc, unit, attempt, phase, state, workdir)
            arts.update(got)
            if not ok:
                return sc.name or (sc.run[0] if sc.run else phase), env, arts
        return None, False, arts

    def _script_unit(self, unit: str, state: RunState) -> dict[str, Any]:
        sc = self.ctx.spec.units[unit].script
        assert sc is not None
        prev = (state.get("attempts") or {}).get(unit) or {}
        attempt = int(prev.get("attempt", 0)) + 1
        ok, env, artifacts = self._run_script(sc, unit, attempt, "unit", state, self._workdir(state, unit))
        record = {"attempt": attempt, "visit": 1, "ok": ok, "text": "", "escalate": "environmental" if env else None,
                  "infra_spent": False, "check": None, "script": True}
        path_units = list(((state.get("run") or {}).get("path") or {}).get("units") or [])
        run = {"path": {"units": path_units + [unit]}} if unit not in path_units else {}
        return {"attempts": {unit: record}, "artifacts": {unit: artifacts or None}, "run": run}

    def _flow_unit(self, unit: str, state: RunState) -> dict[str, Any]:
        """A route or switch unit runs no session: its pick is made in the gate node (CMP-B10 to CMP-B16)."""
        visit = int(((state.get("visits") or {}).get(unit) or {}).get("visit", 1))
        record: dict[str, Any] = {"attempt": 1, "visit": visit, "ok": True, "text": "", "escalate": None,
                                  "infra_spent": False, "check": None, "flow": True}
        sw = self.ctx.spec.units[unit].switch
        if sw is not None and sw.complexity is not None:
            prev = ((state.get("attempts") or {}).get(unit) or {}).get("complexity")
            record["complexity"] = prev or self._complexity(unit, state)  # once per run (CXR-B7)
        path_units = list(((state.get("run") or {}).get("path") or {}).get("units") or [])
        run = {"path": {"units": path_units + [unit]}} if unit not in path_units else {}
        return {"attempts": {unit: record}, "run": run}

    def _join_unit(self, unit: str, state: RunState) -> dict[str, Any]:
        """A parallel block's join runs nothing: every branch has passed when this node starts (CMP-B4)."""
        visit = int(((state.get("visits") or {}).get(unit) or {}).get("visit", 1))
        prev = (state.get("attempts") or {}).get(unit) or {}
        if prev.get("visit") != visit:
            fp = gitmod.fingerprint(self._workdir(state))
            self.ctx.log.write("unit_entered", unit=unit, visit=visit, head_commit=fp.head, dirty=fp.dirty,
                               entered_from="join", branches=list(self.ctx.spec.units[unit].branches))
        record: dict[str, Any] = {"attempt": int(prev.get("attempt", 0)) + 1, "visit": visit, "ok": True, "text": "",
                                  "escalate": None, "infra_spent": False, "check": None, "join": True}
        path_units = list(((state.get("run") or {}).get("path") or {}).get("units") or [])
        run = {"path": {"units": path_units + [unit]}} if unit not in path_units else {}
        out: dict[str, Any] = {"attempts": {unit: record}, "run": run}
        if flow.writer_branches(self.ctx.spec, unit):  # no model session starts for a join, merged or not
            merged, found = self._merge_writers(unit, state)
            record.update(found)
            if merged is not None:
                out["workspace"] = merged
        return out

    def _person_unit(self, unit: str, state: RunState) -> dict[str, Any]:
        """An ask or a wait runs nothing: its step node records the entry and the human node pauses (CMP-B10 to CMP-B16).
        An ask reads its questions here, once per visit, and starts the visit with no answers (ASK-B2)."""
        from tempergraph.run import asking

        u = self.ctx.spec.units[unit]
        visit = int(((state.get("visits") or {}).get(unit) or {}).get("visit", 1))
        prev = (state.get("attempts") or {}).get(unit) or {}
        workdir = self._workdir(state)
        if prev.get("visit") != visit:
            fp = gitmod.fingerprint(workdir)
            self.ctx.log.write("unit_entered", unit=unit, visit=visit, head_commit=fp.head, dirty=fp.dirty,
                               entered_from=_entered_from(state, unit))
        record: dict[str, Any] = {"attempt": int(prev.get("attempt", 0)) + 1, "visit": visit, "ok": True, "text": "",
                                  "escalate": None, "infra_spent": False, "check": None, u.kind: True}
        if u.ask is not None:
            folder = self.ctx.state_root / "runs" / self.ctx.spec.name / self.ctx.task_id
            with contextlib.suppress(OSError):
                asking.answers_path(folder, unit).unlink()
            try:
                listed = asking.questions(u.ask, state, workdir)
                if u.ask.on_deadline == "defaults" and (gaps := asking.defaults_problems(listed)):  # ASK-B13
                    raise asking.AskFault(gaps[0])
                record["questions"] = [asking.to_json(q) for q in listed]
            except asking.AskFault as exc:
                record.update(ok=False, ask_fault=str(exc))
        path_units = list(((state.get("run") or {}).get("path") or {}).get("units") or [])
        run = {"path": {"units": path_units + [unit]}} if unit not in path_units else {}
        return {"attempts": {unit: record}, "artifacts": {unit: None}, "values": {unit: None}, "run": run}

    def _escalation_facts(self, unit: str, state: Mapping[str, Any], att: Mapping[str, Any],
                          write: Mapping[str, Any]) -> dict[str, Any]:
        """What the gate cannot read from state for E1, E6 and E7 (LAD-B12): the stage, whether the escalation
        record is met, the median estimate of one attempt on the tier above and what the run cost cap leaves."""
        ctx = self.ctx
        met = ctx.escalation_record or (lambda u: laddermod.record_met(ctx.state_root, ctx.spec.name,
                                                                         ctx.spec.version, u))
        try:
            record_met = bool(met(unit))
        except Exception:  # noqa: BLE001 - LAD-B14: a record that cannot be read is not met
            record_met = False
        known = sorted(float(x) for x in att.get("up_estimates") or [] if isinstance(x, int | float))
        estimate_usd = known[len(known) // 2] if known and len(known) == len(att.get("up_estimates") or []) else None
        cap = ctx.spec.run_cost_cap_usd
        cost = (write.get("run") or {}).get("cost") or write["judgements"][unit].get("_cost") or (
            state.get("run") or {}).get("cost")
        left = round(float(cap) - CostTotals.from_json(cost).figure(), 6) if cap is not None else None
        return {"stage": ctx.stage, "record_met": record_met, "estimate_usd": estimate_usd, "cap_left_usd": left}

    def _judge_state(self) -> Callable[[str], str]:
        if self.ctx.judge_state is None:
            from tempergraph.improve import calibration

            self.ctx.judge_state = calibration.state_name_for(self.ctx.spec, self.ctx.state_root,
                                                              child=self.ctx.child)  # SWF-B9: a child's own gates
        return self.ctx.judge_state

    def _complexity(self, unit: str, state: Mapping[str, Any]) -> dict[str, Any]:
        """CXR-B9, CXR-B10, CXR-B1: the measures, the rules in force and the zone, evaluated in the switch's step node."""
        ctx = self.ctx
        workdir = self._workdir(state)
        maps = (dict, Mapping)
        mctx = MeasureContext(
            request=dict(state.get("request") or {}),
            facts={u: dict(f) for u, f in (state.get("facts") or {}).items() if isinstance(f, maps)},
            artifacts={u: dict(a) for u, a in (state.get("artifacts") or {}).items() if isinstance(a, maps)},
            settings=dict(ctx.settings), stage=ctx.stage, workdir=workdir,
            git=checkmod.git_facts(workdir, (state.get("workspace") or {}).get("base_commit") or "",
                                   (state.get("workspace") or {}).get("base_branch") or ""))
        return complexity.evaluate(ctx.spec, unit, state, mctx, state_root=ctx.state_root, thread=ctx.thread,
                                   origin=ctx.origin,
                                   recent=complexity.explored_recent(ctx.state_root, ctx.spec.name, unit))

    # -- judge -----------------------------------------------------------------------------------

    def _outcome_step(self, unit: str, state: RunState) -> dict[str, Any]:
        """OUT-B15, OUT-B16, OUT-B17: no session; the subject is final state, recorded for the judge and the record."""
        prev = (state.get("attempts") or {}).get(unit) or {}
        visit = int(((state.get("visits") or {}).get(unit) or {}).get("visit", 1))
        attempt = int(prev.get("attempt", 0)) + 1
        path_units = list(((state.get("run") or {}).get("path") or {}).get("units") or [])
        if prev.get("visit") != visit:
            fp = gitmod.fingerprint(self._workdir(state))
            self.ctx.log.write("unit_entered", unit=unit, visit=visit, head_commit=fp.head, dirty=fp.dirty,
                               entered_from=_entered_from(state, unit))
        o = self.ctx.spec.outcome
        record = {"attempt": attempt, "visit": visit, "ok": True, "text": "", "issues": [], "tools": [],
                  "session_id": None, "escalate": None, "infra_spent": False, "check": None,
                  "deliverables": [dict(d) for d in (o.deliverables if o else ())]}
        run = {"path": {"units": path_units + [unit]}} if unit not in path_units else {}
        return {"attempts": {unit: record}, "run": run}

    def judge(self, unit: str, state: RunState) -> dict[str, Any]:
        if self.ctx.spec.units[unit].kind == "contest" and mapping.item_in_hand(state) is None:
            return self._contest_judge(unit, state)  # CTS-B7: every slot graded alone, then the pick
        w = self._judge(unit, state)
        if self.ctx.spec.units[unit].extra.get("outcome"):
            w = self._route_outcome(unit, state, w)
        return w

    def _route_outcome(self, unit: str, state: RunState, w: dict[str, Any]) -> dict[str, Any]:
        """A failing outcome gate goes back to the earliest serving unit on the path, else escalates (OUT-B15, OUT-B16, OUT-B17)."""
        from tempergraph.run.outcome import derived_back

        j = dict((w.get("judgements") or {}).get(unit) or {})
        if j.get("verdict") not in (str(Verdict.RETRY), str(Verdict.BACK)):
            return w
        o = self.ctx.spec.outcome
        finals = [str(c.id) for c in (o.final if o else ())]
        failing = [b.get("criterion") for b in j.get("blockers") or [] if b.get("criterion") in finals] or finals
        path = list(((state.get("run") or {}).get("path") or {}).get("units") or [])
        target = derived_back(self.ctx.spec, failing, path)
        if target:
            j.update(verdict=str(Verdict.BACK), back_to=target, reason="outcome_serves")
        else:
            j.update(verdict=str(Verdict.ESCALATE), reason="outcome_no_serving_unit")
        return {**w, "judgements": {**(w.get("judgements") or {}), unit: j}}

    def _judge(self, unit: str, state: RunState) -> dict[str, Any]:
        spec = self.ctx.spec
        u = spec.units[unit]
        g = u.gate
        att = dict((state.get("attempts") or {}).get(unit) or {})
        if att.get("map_fault"):
            return {"judgements": {unit: {"verdict": str(Verdict.ESCALATE), "reason": "map_fault"}}}
        if u.kind in ("ask", "wait"):  # no model and no judge: the person's input is the bar (ASK, WFM-B4)
            return {"judgements": {unit: {"verdict": str(Verdict.ESCALATE), "reason": u.kind}}}
        if att.get("map_skip"):
            return {"judgements": {unit: {"verdict": str(Verdict.PROCEED), "reason": "map_empty"}}}
        if att.get("map_done") and not att.get("escalate"):  # MAP-B10: a concurrent map whose items all passed (and merged)
            return {"judgements": {unit: {"verdict": str(Verdict.PROCEED), "reason": "map_items_passed"}}}
        if u.kind == "subworkflow" and (done := self._child_verdict(unit, att)) is not None:
            return done
        if att.get("council_stop"):  # CNL-B13: no decision with `on_no_decision: stop`; the gate stops the run
            return {"judgements": {unit: {"verdict": str(Verdict.ESCALATE), "reason": "no_decision", "confidence": 1.0,
                                          "confidence_source": "engine_placeholder"}}}
        if (att.get("escalate") == "upstream" and att.get("upstream") and att.get("ok") and g.judge is not None
                and not att.get("infra_spent")):
            return self._judge_claim(unit, state, att)
        if att.get("infra_spent") or att.get("escalate"):
            placeholder: dict[str, Any] = {"verdict": str(Verdict.ESCALATE), "reason": att.get("escalate") or "infra",
                                           "confidence": 1.0, "confidence_source": "engine_placeholder"}
            if att.get("escalate") == "merge_conflict":  # WSP-B12: the pause lists the conflicting paths
                placeholder["blockers"] = [
                    {"criterion": "writer-branches", "place": p, "problem": f"conflicting change in {p}",
                     "fix": f"decide which change of writer branch {att.get('conflict_branch')} or the run's branch stays"}
                    for p in att.get("conflicts") or []] or [
                    {"criterion": "writer-branches", "problem": str(att.get("merge_error") or "the join failed")}]
            if att.get("escalate") == "map_check":  # MAP-B13: the pause lists the joined check's failing findings
                placeholder["blockers"] = list(att.get("map_findings") or [])
            return {"judgements": {unit: placeholder}}
        if not att.get("ok"):
            problem = att.get("error_kind") or ("timed out" if att.get("timed_out") else "the step failed")
            if att.get("written"):  # WSP-B11, CNL-B14: a read-only member wrote to the workspace; its paths are reported
                problem += ": " + ", ".join(str(p) for p in att["written"])
            return {"judgements": {unit: {"verdict": str(Verdict.RETRY), "reason": "step_failed", "blockers": [
                {"criterion": "step", "problem": problem}]}}}
        bad = [i for i in att.get("issues") or [] if i.startswith(("value_missing", "value_invalid"))]
        if bad:
            return {"judgements": {unit: {"verdict": str(Verdict.RETRY), "reason": "output_contract", "blockers": [
                {"criterion": "output", "problem": i} for i in bad]}}}
        if att.get("dissent_missing"):  # CNL-B12: the built-in check; its failure is retryable
            return {"judgements": {unit: {"verdict": str(Verdict.RETRY), "reason": "council_dissent",
                                          "blockers": [council_dissent_blocker(unit)]}}}
        workdir = self._workdir(state, unit)
        cres, notes = self._check(unit, state, att, workdir)
        att["check"] = checkmod.to_json(cres)
        iid = att.get("item")
        facts: dict[str, Any] = dict(cres.facts or {})
        if att.get("foreign_worktrees"):  # WTR-B26: the step's fact outlives the check's own facts
            facts["foreign_worktrees"] = att["foreign_worktrees"]
        if iid:
            facts.update({mapping.item_key(k, str(iid)): v for k, v in list(facts.items())})
        write: dict[str, Any] = {"attempts": {unit: att},
                                 "facts": {unit: facts} if iid and facts else {} if iid else {unit: facts or None}}
        self.ctx.log.write("check", unit=unit, item=iid, attempt=att.get("attempt") if iid else None,  # per item
                           result=cres.result, environmental=cres.environmental,
                           evidence=clip(cres.evidence, 200), notes=notes)
        if cres.result == "FAIL":
            if cres.environmental:
                att["escalate"] = "environmental"
                write["judgements"] = {unit: {"verdict": str(Verdict.ESCALATE), "reason": "environmental"}}
            elif self._repeats(att, cres):  # BUD-B16: the same failure again although files changed: no retry helps
                att["escalate"] = "check_repeat"
                att["repeated"] = checkmod.failing(cres)
                att["repeated_evidence"] = cres.evidence
                write["judgements"] = {unit: {"verdict": str(Verdict.ESCALATE), "reason": "check_repeat"}}
            else:
                blockers = [{"criterion": f.criterion or "check", "place": f.place, "problem": f.message, "fix": f.fix}
                            for f in cres.findings if f.status == "fail"]
                if g.judge is None and g.on_fail == "back" and blockers and len(g.back_targets) == 1:  # HUM-B15
                    write["judgements"] = {unit: {"verdict": str(Verdict.BACK), "back_to": g.back_targets[0],
                                                  "reason": "check_fail", "blockers": blockers}}
                else:
                    write["judgements"] = {unit: {"verdict": str(Verdict.RETRY), "reason": "check_fail",
                                                  "blockers": blockers or [{"criterion": "check",
                                                                            "problem": "check FAIL"}]}}
            return write
        if g.judge is None:  # a script unit gated by its check alone
            write["judgements"] = {unit: {"verdict": str(Verdict.PROCEED), "reason": "check_only"}}
            return write
        write["judgements"] = {unit: self._judge_session(unit, state, att, cres, workdir)}
        if u.step is not None and (u.step.effort_ladder or u.step.escalation is not None or any(
                sw.switch is not None and unit in sw.switch.rearm_units() for sw in spec.units.values())):
            level = (write["judgements"][unit].get("risk") or {}).get("level")  # a level is its own binding
            g_names = [lv.name for lv in g.judge.risk.levels] if g.judge.risk is not None else []
            raised = level in g_names[1:]
            # the gate reads trust from the judgement (LAD-B10)
            state_of = self._judge_state()(f"{unit}@{level}" if raised else unit)
            write["judgements"][unit].update(judge_state=state_of, trusted=laddermod.trusted(state_of, self.ctx.stage))
            if u.step.escalation is not None or gatemod.arm_overrides(spec, unit, state)[0].get("escalation"):
                write["judgements"][unit]["escalation"] = self._escalation_facts(unit, state, att, write)
        if write["judgements"][unit].get("reason") == "usage_limit":  # JDG-B14: the attempt keeps the cause and the instant
            att.update(escalate="usage_limit", usage_limit_stage="judge",
                       usage_limit_resets_at=write["judgements"][unit].get("usage_limit_resets_at"))
        if write["judgements"][unit].get("infra_spent"):
            att["infra_spent"] = True
            att["infra_cause"] = "judge_infra"
        return {**write, "run": {"cost": write["judgements"][unit].pop("_cost")}} if "_cost" in write["judgements"][
            unit] else write

    def _child_verdict(self, unit: str, att: Mapping[str, Any]) -> dict[str, Any] | None:
        """SWF-B5: what the child's end says about the unit's gate, before anything else is checked. An upstream defect
        in a key the unit mapped into `inputs` goes back to the parent unit that made it when it is a back target of
        the gate (the gate's own rule), else asks a person; a child that stopped or ended `unmet` or `needs_person`
        fails the gate with the child's failing final criteria as blockers. None: the child ended well."""
        up = att.get("upstream_child")
        if up:
            blockers = [{"criterion": "upstream", "problem": str(up.get("reason") or "an upstream defect"),
                         "defect_in": up.get("key")}]
            if up.get("unit") in self.ctx.spec.units[unit].gate.back_targets:
                return {"judgements": {unit: {"verdict": str(Verdict.BACK), "back_to": up["unit"], "blockers": blockers,
                                              "reason": "upstream_confirmed", "confidence": 1.0,
                                              "confidence_source": "child_judge"}}}
            return {"judgements": {unit: {"verdict": str(Verdict.ESCALATE), "reason": "upstream", "blockers": blockers,
                                          "confidence": 1.0, "confidence_source": "child_judge"}}}
        failing = att.get("child_failed")
        if failing:
            return {"judgements": {unit: {"verdict": str(Verdict.RETRY), "reason": "child_unmet", "blockers": [
                {"criterion": str(f.get("criterion")), "problem": str(f.get("problem"))} for f in failing]}}}
        return None

    @staticmethod
    def _repeats(att: Mapping[str, Any], cres: CheckResult) -> bool:
        """BUD-B16: this failing check equals the previous attempt's, and this attempt's step changed files."""
        prior = att.get("prior_failing")
        if not prior or not att.get("changed"):
            return False
        return checkmod.repeat_key(prior.get("findings") or [], str(prior.get("evidence") or "")) \
            == checkmod.repeat_key(checkmod.failing(cres), cres.evidence)

    def _judge_claim(self, unit: str, state: RunState, att: dict[str, Any]) -> dict[str, Any]:
        """A step's upstream claim is judged on its own against one criterion: confirmed goes BACK, refuted
        retries, undecided asks a person (BUD-B10, HUM-B7 to HUM-B11). No check runs: the step produced nothing to check."""
        target, defect = (str(x) for x in att["upstream"])
        j = self._judge_session(unit, state, att, None, self._workdir(state, unit), claim=(target, defect))
        cost = j.pop("_cost", None)
        verdict = j.get("verdict")
        if j.get("infra_spent"):
            att["infra_spent"], att["infra_cause"] = True, "judge_infra"
        elif verdict == str(Verdict.PROCEED):  # the one criterion is MET: the defect is there
            j.update(verdict=str(Verdict.BACK), back_to=target, reason="upstream_confirmed",
                     blockers=[{"criterion": CLAIM_CRITERION_ID, "problem": defect}])
            att["escalate"] = None
        elif verdict == str(Verdict.RETRY):
            j.update(reason="upstream_refuted")
            att["escalate"] = None
        else:
            j.update(verdict=str(Verdict.ESCALATE), reason="upstream")
        write: dict[str, Any] = {"attempts": {unit: att}, "judgements": {unit: j}}
        return {**write, "run": {"cost": cost}} if cost is not None else write

    def _check(self, unit: str, state: Mapping[str, Any], att: Mapping[str, Any], workdir: Path
               ) -> tuple[CheckResult, list[str]]:
        u = self.ctx.spec.units[unit]
        ctx = self._check_context(unit, state, att, workdir)
        skey = att.get("session_key")
        if isinstance(skey, str) and skey.rsplit(".", 1)[-1] in ("step", "retry"):  # CHK-B24: no other check has a record
            calls = read_session(session_dir(self.ctx.state_root, self.ctx.spec.name, self.ctx.task_id, skey))
            ctx.session = None if calls is None else tuple(calls)
            if calls is not None:  # VSR-B1, VSR-B2: the attempts of this visit and item, in order; no record adds no call
                held = att.get("visit_keys")
                keys = [k for k in held if isinstance(k, str)] if isinstance(held, list) and held else [skey]
                visit_calls: list[Any] = []
                for k in keys:
                    if k.rsplit(".", 1)[-1] not in ("step", "retry"):
                        continue
                    got_calls = calls if k == skey else read_session(
                        session_dir(self.ctx.state_root, self.ctx.spec.name, self.ctx.task_id, k))
                    visit_calls.extend(got_calls or ())
                ctx.visit_session = tuple(visit_calls)
        got = run_in_worker(u.gate, ctx)
        if not self.ctx.capture.check_output and ctx.out_dir is not None:  # `observe.check_output = off`
            for f in ctx.out_dir.glob("*.out"):
                with contextlib.suppress(OSError):
                    f.unlink()
        return got

    def _check_context(self, unit: str, state: Mapping[str, Any], att: Mapping[str, Any], workdir: Path,
                       sub: str = "") -> checkmod.CheckContext:
        u = self.ctx.spec.units[unit]
        facts = {k: v for k, v in (state.get("facts") or {}).items() if k != unit}
        gfacts = checkmod.git_facts(workdir, (state.get("workspace") or {}).get("base_commit") or "",
                                    (state.get("workspace") or {}).get("base_branch") or "")
        return checkmod.CheckContext(
            changed_paths=checkmod.changed_paths(
                workdir, gfacts, self.ctx.state_root / "runs" / self.ctx.spec.name / self.ctx.task_id / "manifest.json"),
            unit=unit, item=att.get("item"), workdir=workdir, request=state.get("request") or {},
            attempt=int(att.get("attempt", 1)),
            visit=int(att.get("visit", 1)), main_checkout=self.ctx.main_checkout,
            artifacts=state.get("artifacts") or {}, values=state.get("values") or {}, facts=facts,
            git=gfacts,
            criteria=tuple({"id": c.id, "mechanical": c.mechanical} for c in u.gate.criteria),
            allow=tuple(self.ctx.spec.allow_commands),
            out_dir=self.ctx.state_root / "runs" / self.ctx.spec.name / self.ctx.task_id / "checks"
            / (f"{unit}.{att['item']}" if att.get("item") else unit) / (str(att.get("attempt", 1)) + sub),
            settings={**self._check_settings(u), **({"path_units": list(
                ((state.get("run") or {}).get("path") or {}).get("units") or [])} if u.extra.get("outcome") else {})},
            reuse_store=self.ctx.state_root / "runs" / self.ctx.spec.name / self.ctx.task_id / "command_runs.jsonl")

    def _check_settings(self, u: UnitSpec) -> dict[str, Any]:
        o = self.ctx.spec.outcome
        if not u.extra.get("outcome") or o is None:
            return dict(self.ctx.settings)  # the workflow-declared settings a check reads (RST-B25)
        from tempergraph.run.outcome import deliverable_producers

        return {**self.ctx.settings, "deliverables": [dict(d) for d in o.deliverables],
                "deliverable_producers": deliverable_producers(self.ctx.spec),
                "outcome_check": o.check.ref if o.check else None}

    @staticmethod
    def _reachable_views(ex: Any, views: ViewSet, workdir: Path) -> ViewSet:
        """ECC-B15: an MCP view whose server has no working proxy on this executor (not in the operator's
        configuration, defined by a URL, or exits at start) is deferred for the attempt and its tools are dropped from
        the judge's views, so the prompt names the artifact out of reach and no tool of that server is offered."""
        check = getattr(ex, "unreachable_views", None)  # an executor that fronts MCP servers itself has it
        if check is None or not any(t.startswith("mcp__") for t in views.tools):
            return views
        down: Mapping[str, str] = check(views, workdir)
        if not down:
            return views
        from tempergraph.contracts import Deferred
        from tempergraph.executors import mcpconfig

        lost = [Deferred(capability=f"mcp:{server}/{tool}", reason=f"mcp_{down[server]}")
                for server, tools in mcpconfig.viewed_servers(views.tools).items() if server in down for tool in tools]
        keep = tuple(t for t in views.tools if not (t.startswith("mcp__") and t.split("__", 2)[1] in down))
        return dataclasses.replace(views, tools=keep, deferred=(*views.deferred, *lost))

    def _entry_commit(self, unit: str, visit: int) -> str:
        """SRV-B34, SRV-B36: the commit recorded when the unit's visit was entered (EVT-B12), the first record of the
        unit and visit in this run's log; empty when none holds one."""
        from tempergraph.run.events import records
        from tempergraph.run.subrun import root_log

        try:
            for r in records(root_log(self.ctx.log).path):
                if r.get("kind") == "unit_entered" and r.get("unit") == unit and r.get("visit") == visit \
                        and r.get("child") == self.ctx.child:
                    return str(r.get("head_commit") or "")
        except Exception:  # noqa: BLE001 - observability never changes the run (OVR-B4)
            return ""
        return ""

    def _declared_files(self, unit: str, state: Mapping[str, Any], workdir: Path) -> set[str]:
        """SRV-B41: the workspace-relative paths of the file artifacts the units of the run's path (and `unit`) declare
        in `produces`, every item's of a map included; `./x`, `x` and an absolute path inside the workspace name one
        path."""
        spec = self.ctx.spec
        path_units = list(((state.get("run") or {}).get("path") or {}).get("units") or [])
        out: set[str] = set()
        root = os.path.normpath(str(workdir))
        for name in dict.fromkeys([*path_units, unit]):
            u = spec.units.get(name)
            produces = getattr(u.step, "produces", None) if u is not None and u.step is not None else None
            values = (state.get("artifacts") or {}).get(name) or {}
            for key, kind in (produces or {}).items():
                if kind != "file":
                    continue
                # a map keeps each item's value as `<key>[<item id>]`; the plain key is only the item in hand (MAP-B9)
                for held, value in values.items():
                    if held != key and not (held.startswith(f"{key}[") and held.endswith("]")):
                        continue
                    p = os.path.normpath(str(value))
                    if os.path.isabs(p):
                        if not (p == root or p.startswith(root + os.sep)):
                            continue
                        p = os.path.relpath(p, root)
                    out.add(p)
        return out

    def _judge_count(self, unit: str, state: Mapping[str, Any], workdir: Path, base: str, g: Any) -> dict[str, Any]:
        """SRV-B34, SRV-B37 to SRV-B43: the judge's own record fields. The lists of checks, git facts, the session's
        own record and the suites stay unfiltered (`gitmod.changed_paths`)."""
        problem = None
        try:
            problem = gitmod.base_problem(workdir, base)
        except Exception:  # noqa: BLE001 - observability never changes the run (OVR-B4)
            problem = "outside_repository"
        if problem is not None:
            return {"changed_base": None, "changed_base_reason": problem, "changed_left_out": 0}
        try:
            listed = gitmod.judge_changed_paths(workdir, base, 100000)
        except Exception:  # noqa: BLE001
            listed = []
        declared = self._declared_files(unit, state, workdir)
        listed = [p for p in listed if p not in declared]
        patterns = tuple(getattr(g, "judge_may_skip", ()) or ())
        kept = [p for p in listed if not any(_skip_match(p, pat) for pat in patterns)]
        return {"changed_paths": kept[:200], "changed_base": base, "changed_left_out": len(listed) - len(kept)}

    def _judge_session(self, unit: str, state: Mapping[str, Any], att: Mapping[str, Any], cres: CheckResult | None,
                       workdir: Path, claim: tuple[str, str] | None = None) -> dict[str, Any]:
        spec = self.ctx.spec
        u = spec.units[unit]
        g = u.gate
        st = u.step if u.step is not None else StepSpec()  # a sub-workflow unit has no step: its judge reads what `produces` exposes
        assert g.judge is not None
        j = g.judge
        if claim:  # one engine criterion replaces the gate's own; the subject is the claimed unit's output
            g = dataclasses.replace(g, criteria=(claim_criterion(*claim),))
        else:  # OUT-B10, OUT-B12: a judge grades no criterion a person signs or nobody verifies
            g = judged(g)
        step_ex = st.executor or spec.default_executor
        judge_name = self.ctx.judges.get(unit) or self.ctx.registry.judge_executor(step_ex, j.executor,
                                                                                  self.ctx.judge_override)
        ex = self.ctx.registry.get(judge_name)
        caps = ex.capabilities()
        from tempergraph.contracts import ToolCall  # local: keeps the module's import list short

        views = view_set(st, [ToolCall(name=t) for t in att.get("tools") or []], caps, j.tools,
                         granted=tuple(u.extra.get("views_add") or ()))
        views = self._reachable_views(ex, views, workdir)  # ECC-B15: before the prompt names what is out of reach
        stance, brief = j.stance, j.brief
        if j.file:
            from tempergraph.contracts import TextRef

            stance, brief = split_judge_file(load_text(spec, TextRef(path=j.file)))
        subject_unit = claim[0] if claim else unit
        arts = (state.get("artifacts") or {}).get(subject_unit) or {}
        vals = (state.get("values") or {}).get(subject_unit) or {}
        if u.contest is not None and att.get("item"):  # CTS-B3: one candidate's artifacts, no other slot's
            arts, vals = own_keys(arts, str(att["item"])), own_keys(vals, str(att["item"]))
        refs: dict[str, str] = {}
        for ref in j.references:
            for chan in ("artifacts", "values"):
                for vs in (state.get(chan) or {}).values():
                    if isinstance(vs, dict) and ref in vs:
                        refs[ref] = str(vs[ref])
        inputs = (state.get("request") or {}).get("inputs") or {}
        for ref in j.references:  # a reference may name a request input (validation allows it)
            if ref not in refs and ref != "request" and ref in inputs:
                refs[ref] = str(inputs[ref])
        req_text = str(inputs.get("request", ""))
        subject = {**{k: str(v) for k, v in arts.items()}, **{k: str(v) for k, v in vals.items()}}
        if u.kind == "council":  # CNL-B4: the judge grades `decision`, with `positions` among its references
            subject, more = council_inputs(vals)
            for k, v in more.items():
                refs.setdefault(k, v)
        prompt = render_judge(JudgeInputs(
            gate=g, stance=stance, brief=brief, request=req_text, references=refs,
            subject=subject,
            out_of_reach=[d.capability for d in views.deferred], check=cres, step_account=str(att.get("text") or ""),
            workspace_facts={"branch": gitmod.branch(workdir), "changed": len(gitmod.changed_paths(workdir))},
            feedback=str(((state.get("feedback") or {}).get(unit) or {}).get("text") or ""),
            rulings=tuple(gatemod.active_rulings(spec, state, unit)),
            visit_reason=str(((state.get("visits") or {}).get(unit) or {}).get("reason") or "")))
        alias = j.model or "inherit"  # resolved on the judge chain alone (RST-B22, RST-B23, CON-B3)
        attempt = int(att.get("attempt", 1))
        iid = att.get("item")
        jopts = j.session_options or SessionOptions()
        risk = self._risk(unit, state, att, cres, workdir, j) if j.risk is not None else None
        if risk is not None:  # JRK-B8: the level's alias and effort for this attempt; a pin keeps its own
            alias = risk.pop("model") or alias
            effort = risk.pop("effort")
            if effort:
                jopts = dataclasses.replace(jopts, effort=effort)
            self.ctx.log.write("judge_risk", unit=unit, item=iid, attempt=attempt, alias=alias,
                               effort=jopts.effort, **risk)
        key = self._skey(unit, attempt, "judge", item=iid)
        req = SessionRequest(kind="judge", prompt=prompt, workdir=workdir, alias=alias, session_key=key,
                             timeout_s=j.timeout_s or DEFAULT_TIMEOUT_S, idle_s=j.idle_s,
                             options=jopts,
                             session_dir=session_dir(self.ctx.state_root, spec.name, self.ctx.task_id, key))
        before = gitmod.fingerprint(workdir)
        base = str(att.get("entry_head") or "") if u.map is not None else self._entry_commit(
            unit, int(((state.get("visits") or {}).get(unit) or {}).get("visit", 1)))
        counted = self._judge_count(unit, state, workdir, base, g)  # the digest's `changed_read` (SRV-B11, SRV-B34)
        hold = self._hold(unit, state)
        res, results = self._session(ex, req, views, extra=counted, hold=hold)
        all_results = list(results)
        out: dict[str, Any] = {"judge_executor": judge_name, "alias": alias, "views": list(views.tools)}
        if risk is not None:
            out["risk"] = risk
        if not res.ok and res.usage_limit:  # JDG-B14: a refusal derives no verdict and spends nothing
            return self._judge_limited(out, res, state, all_results)
        if res.infra_cause is not None:
            out.update(verdict=str(Verdict.ESCALATE), infra_spent=True, reason="judge_infra")
            out["_cost"] = self._cost(state, all_results)
            return out
        judgement = None
        if not res.timed_out:
            try:
                judgement = parse_judgement(res.text, g)
            except Unparsed:
                rkey = self._skey(unit, attempt, "judge_reask", item=iid)
                rreq = SessionRequest(kind="judge_reask", prompt=reask_prompt(res.text, g), workdir=workdir,
                                      alias=alias, session_key=rkey, timeout_s=req.timeout_s, idle_s=req.idle_s,
                                      options=req.options,
                                      session_dir=session_dir(self.ctx.state_root, spec.name, self.ctx.task_id, rkey))
                res2, r2 = self._session(ex, rreq, views, hold=hold)
                all_results += r2
                if not res2.ok and res2.usage_limit:
                    return self._judge_limited(out, res2, state, all_results)
                try:
                    judgement = parse_judgement(res2.text, g)
                except Unparsed:
                    judgement = None
        after = gitmod.fingerprint(workdir)
        gr = guard(views, res.tool_calls, before, after, workspace_mode=(state.get("workspace") or {}).get(
            "mode", "in_place"), step_session_id=att.get("session_id"), judge_session_id=res.session_id,
            reports_actions=caps.reports_actions)
        if gr.status == "discarded":
            judgement = None
        if judgement is not None and reread_needed(judgement, g, cres):  # JDG-B17: one re-read, never a third session
            mk = marked_reading(judgement, g, cres)
            ckey = self._skey(unit, attempt, "judge_reread", item=iid)
            creq = SessionRequest(kind="judge_reread", prompt=reread_prompt(prompt, judgement, mk.marked, g),
                                  workdir=workdir, alias=alias, session_key=ckey, timeout_s=req.timeout_s,
                                  idle_s=req.idle_s, options=req.options,
                                  session_dir=session_dir(self.ctx.state_root, spec.name, self.ctx.task_id, ckey))
            res3, r3 = self._session(ex, creq, views, hold=hold)
            all_results += r3
            if not res3.ok and res3.usage_limit:
                return self._judge_limited(out, res3, state, all_results)
            judgement = None  # JDG-B19: the verdict comes from the re-read's judgement alone
            if not res3.timed_out:
                try:
                    judgement = parse_judgement(res3.text, g)
                except Unparsed:
                    judgement = None
        back_units: dict[str, str] = {}
        for target in flow.effective_order(spec):
            if target in g.back_targets:
                tu = spec.units[target]
                for k in (tu.step.produces if tu.step else {}):
                    back_units[k] = target
                for b in tu.branches:  # a defect in a branch's output sends the run back to its block
                    bu = spec.units.get(b)
                    for k in (bu.step.produces if bu is not None and bu.step else {}):
                        back_units[k] = target
        outcome = derive(judgement, g, cres, {} if claim else back_units)
        if judgement is None and gr.status == "discarded":
            outcome.reason = f"guard:{gr.reason}"
        self.ctx.log.write("judgement", unit=unit, item=iid, attempt=attempt, statuses=outcome.statuses, blockers=[
            b["criterion"] for b in outcome.blockers], confidence=outcome.confidence,
            confidence_source=outcome.confidence_source, gap=outcome.gap, guard=gr.status, views=list(views.tools),
            judge_executor=judge_name, brief_digest=brief_digest(stance, brief),
            criteria_digest=criteria_digest(g.criteria), **({"claim": claim[0]} if claim else {}),
            **({"deferred": [{"capability": d.capability, "reason": d.reason} for d in views.deferred]}
               if views.deferred else {}),
            **({"level": risk["level"]} if risk is not None else {}))
        self._keep_evidence(unit, att, outcome.blockers)
        out.update(outcome.to_json())
        out["guard"] = gr.status
        out["_cost"] = self._cost(state, all_results)  # the audit judge's cost is in no counter (JDG-B7)
        if claim is None and judgement is not None and self._audit_drawn(unit, iid, attempt):
            self._audit_judgement(unit, iid, attempt, ex, req, views, g, cres, state, att, workdir)
        return out

    def _judge_limited(self, out: dict[str, Any], res: SessionResult, state: Mapping[str, Any],
                       results: list[SessionResult]) -> dict[str, Any]:
        """JDG-B14: the usage limit ended a judge session; the gate gets the ESCALATE placeholder, no `judgement` record."""
        out.update(verdict=str(Verdict.ESCALATE), reason="usage_limit", confidence=1.0,
                   confidence_source="engine_placeholder", usage_limit_resets_at=res.usage_limit_resets_at)
        out["_cost"] = self._cost(state, results)
        return out

    # -- the sampled audit judge (JDG-B7) ---------------------------------------------------------------

    def _audit_drawn(self, unit: str, iid: str | None, attempt: int) -> bool:
        return auditmod.sampled(self.ctx.audit_rate, seed=self.ctx.audit_seed, thread=self.ctx.thread, unit=unit,
                                item=iid, attempt=attempt)

    def _audit_judgement(self, unit: str, iid: str | None, attempt: int, judge_ex: Executor, req: SessionRequest,
                         views: Any, g: Any, cres: CheckResult | None, state: Mapping[str, Any],
                         att: Mapping[str, Any], workdir: Path) -> None:
        """A second judge on the same prompt and views, on the audit executor when one is set, under its own
        session key. The result waits for the gate record of this attempt, which it must follow; no verdict,
        route, counter or budget reads it, and any failure of the audit leaves no trace but its session log."""
        try:
            name = self.ctx.audit_executor or judge_ex.name
            ex = judge_ex if name == judge_ex.name else self.ctx.registry.get(name)
            key = session_key(unit, attempt, "audit", item=iid)
            areq = dataclasses.replace(req, session_key=key, session_dir=session_dir(
                self.ctx.state_root, self.ctx.spec.name, self.ctx.task_id, key))
            caps = ex.capabilities()
            mode = (state.get("workspace") or {}).get("mode", "in_place")

            def session(r: SessionRequest) -> tuple[SessionResult, list[SessionResult]]:
                return self._session(ex, r, views)  # no reservation: an audit holds none of a cap

            before = gitmod.fingerprint(workdir)

            def discarded(res: SessionResult) -> bool:
                return guard(views, res.tool_calls, before, gitmod.fingerprint(workdir), workspace_mode=mode,
                             step_session_id=att.get("session_id"), judge_session_id=res.session_id,
                             reports_actions=caps.reports_actions).status == "discarded"

            found = auditmod.run(session, areq, gate=g, check=cres, executor=name, discarded=discarded)
        except Exception:  # noqa: BLE001 - an audit that cannot run changes nothing
            return
        if found is not None:
            self._audits[(unit, iid)] = {"item": iid, "attempt": attempt, **found.fields()}

    def _risk(self, unit: str, state: Mapping[str, Any], att: Mapping[str, Any], cres: CheckResult | None,
              workdir: Path, j: Any) -> dict[str, Any]:
        """JRK-B7, JRK-B8: the rule on model-free facts of the attempt, then the level that grades it."""
        from tempergraph.contracts import RiskContext
        from tempergraph.run import risk as riskmod

        ctx = self.ctx
        maps = (dict, Mapping)
        facts = {u: dict(f) for u, f in (state.get("facts") or {}).items() if isinstance(f, maps)}
        if cres is not None and cres.facts:
            facts[unit] = {**facts.get(unit, {}), **dict(cres.facts)}
        escalated = bool(att.get("escalated"))
        rctx = RiskContext(
            unit=unit, item=att.get("item"), visit=int(att.get("visit", 1)), attempt=int(att.get("attempt", 1)),
            git=riskmod.git_of(checkmod.git_facts(workdir, (state.get("workspace") or {}).get("base_commit") or "",
                                                  (state.get("workspace") or {}).get("base_branch") or ""),
                               workdir),
            facts=facts, request=dict((state.get("request") or {}).get("inputs") or {}), settings=dict(ctx.settings),
            stage=ctx.stage, producer={"alias": att.get("alias"), "escalated": escalated,
                                       "source": "escalation:+1" if escalated else "declared"})
        opts = j.session_options
        pinned = any(k in (ctx.spec.units[unit].extra.get("judge_operator_set") or ()) for k in riskmod.PIN_KEYS)
        return riskmod.resolve(j.risk, riskmod.run_rule(j.risk, rctx), base_model=j.model,
                               base_effort=opts.effort if opts else None, pinned=pinned,
                               producer_rank=riskmod.rank(att.get("alias")) if escalated else None)

    def _keep_evidence(self, unit: str, att: Mapping[str, Any], blockers: list[dict[str, Any]]) -> None:
        """One judgement's evidence and fix lines per attempt, scrubbed and local only (LOS-B7, LOS-B8, LOS-B9, RDD-B7 to RDD-B11, RDD-B13, RDD-B15)."""
        if not blockers:
            return
        from tempergraph.docs import write_json
        from tempergraph.store.layout import run_dir

        visit, attempt = int(att.get("visit", 1)), int(att.get("attempt", 1))
        path = (run_dir(self.ctx.state_root, self.ctx.spec.name, self.ctx.task_id) / "evidence" / "judgements"
                / (f"{unit}.{att['item']}" if att.get("item") else unit) / f"{visit}.{attempt}.json")
        rows = [{"criterion": b.get("criterion"),
                 "evidence": clip(scrub(str(b.get("evidence") or b.get("problem") or "")), 400),
                 "fix": clip(scrub(str(b.get("fix") or "")), 400)} for b in blockers]
        with contextlib.suppress(OSError):
            path.parent.mkdir(parents=True, exist_ok=True, mode=0o700)
            write_json(path, {"schema_version": 1, "unit": unit, "visit": visit, "attempt": attempt,
                              "blockers": rows}, mode=0o600)

    # -- gate, human, finalizer --------------------------------------------------------------------

    def gate(self, unit: str, state: RunState) -> dict[str, Any]:
        w = gatemod.decide(self.ctx.spec, unit, state, self.ctx.task_id)
        if (state.get("feedback") or {}).get(unit):
            w.setdefault("feedback", {})[unit] = None  # one-time: seen by the attempt and its judge (RRN-B14, RRN-B15)
        r = w["route"][unit]
        so_far = cost_so_far((state.get("run") or {}).get("cost"))
        self.ctx.log.write("gate", unit=unit, item=((state.get("attempts") or {}).get(unit) or {}).get("item"),
                           verdict=((state.get("judgements") or {}).get(unit) or {}).get("verdict"),
                           token=r["token"], route_target=r["node"], cost_so_far=so_far)
        if r["token"] == "BACK":
            to = ((state.get("judgements") or {}).get(unit) or {}).get("back_to") or r["node"]
            self.ctx.trips[to] = self.ctx.trips.get(to, 0) + 1
        done = self._audits.pop((unit, ((state.get("attempts") or {}).get(unit) or {}).get("item")), None)
        if done is not None:  # JDG-B7: the audit record follows the gate of the judgement it audits
            self.ctx.log.write("audit_judge", unit=unit, **done)
        self._budget_records(unit, state, w)
        if r.get("ladder"):  # LAD-B16, LAD-B17: every gate that chose the next attempt's rung
            self.ctx.log.write("ladder_decision", unit=unit, **r["ladder"])
        att = (state.get("attempts") or {}).get(unit) or {}
        if att.get("escalated"):  # LAD-B16, LAD-B17: the escalation record
            laddermod.record_escalation(
                self.ctx.state_root, workflow=self.ctx.spec.name, version=self.ctx.spec.version, unit=unit,
                thread=self.ctx.thread, passed=r["token"] in ("PROCEED", "NEXT"), to=str(att.get("escalated_to")),
                judge_state=((state.get("judgements") or {}).get(unit) or {}).get("judge_state"))
        for name, rr in w["route"].items():  # every pick: predicate, default, operator or re-arm (OBS `route`)
            p = (rr or {}).get("pick")
            if p and (name == unit or p.get("chosen_by") == "rearm"):
                self.ctx.log.write("route", unit=name, arm=p["arm"], target=p["target"], chosen_by=p["chosen_by"],
                                   **{k: p[k] for k in ("shadow", "would_choose", "signals", "signals_clipped",
                                                        "fault", "rearmed_from", "rearm_unit", "rearm_cause",
                                                        *gatemod.COMPLEXITY_FIELDS)
                                      if k in p})
        if unit in (w.get("pause") or {}) and w["pause"][unit]:
            p = w["pause"][unit]
            self.ctx.log.write("pause", unit=unit, item=p.get("item"), pause_kind=p["kind"], decisions=p["decisions"], resume=p["resume"],
                               cost_so_far=so_far, reason=p.get("reason"), escalation=p.get("escalation"),
                               tool_access=[{k: t.get(k) for k in ("name", "capability", "class")}
                                            for t in p.get("tool_access") or []] or None,
                               **({"deadline_at": p["deadline_at"], "on_deadline": p.get("on_deadline")}
                                  if p.get("deadline_at") else {}),
                               **({"usage_limit_resets_at": p["usage_limit_resets_at"]}
                                  if "usage_limit_resets_at" in p else {}),
                               **({"questions": len(p["questions"])} if p.get("questions") is not None else {}))
        return w

    def _budget_records(self, unit: str, state: RunState, w: Mapping[str, Any]) -> None:
        """EVT-B10 to EVT-B16 `budget`: one record per counter this gate charged, with its limit and cause."""
        g = self.ctx.spec.units[unit].gate
        before = (state.get("counters") or {}).get(unit) or {}
        after = (w.get("counters") or {}).get(unit) or {}
        cause = ((state.get("judgements") or {}).get(unit) or {}).get("reason") or "verdict"
        if int(after.get("retries", 0)) > int(before.get("retries", 0)):
            self.ctx.log.write("budget", unit=unit, counter="retries", used=int(after["retries"]),
                               limit=g.retry_budget, cause=cause)
        old_loops = before.get("loops") or {}
        for target, n in (after.get("loops") or {}).items():
            if int(n) > int(old_loops.get(target, 0)):
                self.ctx.log.write("budget", unit=unit, counter=f"loops:{target}", used=int(n), limit=g.loop_budget,
                                   cause=cause)

    def human(self, unit: str, state: RunState, decision: Any) -> dict[str, Any]:
        payload = decision if isinstance(decision, dict) else {"decision": str(decision)}
        w = gatemod.apply_decision(self.ctx.spec, unit, state, payload)
        self.ctx.log.write("human", unit=unit, decision=payload.get("decision"), caller=payload.get("caller"),
                           feedback=bool(payload.get("feedback")) and not payload.get("ruling"))
        if payload.get("council_decision") is not None:  # CNL-B13, EVT-B15: the person's answer is the council's outcome
            held = (state.get("attempts") or {}).get(unit) or {}
            tally = held.get("council", {}).get("tally") or {}
            self.ctx.log.write("council_tally", unit=unit, attempt=held.get("attempt"), mode=tally.get("mode"),
                               rule=tally.get("rule"), counts=tally.get("counts"),
                               outcome=str(payload["council_decision"]), chosen_by="person")
        p = (w.get("pause") or {}).get(unit)
        if p:  # an applied deadline turned the pause into an escalation (FLX-B8)
            self.ctx.log.write("pause", unit=unit, item=p.get("item"), pause_kind=p["kind"], decisions=p["decisions"],
                               resume=p["resume"], reason=p.get("reason"),
                               cost_so_far=cost_so_far((state.get("run") or {}).get("cost")))
        return w

    def finalizer(self, state: RunState) -> dict[str, Any]:
        from tempergraph.run.finalize import run_finalizer

        result = run_finalizer(self.ctx, state)
        self.ctx.log.write("finalize", **result)
        if result.get("manual_steps") or result.get("outcome") == "error":  # FIN-B8: seen, not only logged
            import sys

            reason = str(result.get("reason") or "").replace("\n", " ")
            sys.stderr.write(f"{self.ctx.thread}: finalizer {result.get('outcome')}: {reason}\n")
        return {"finalized": {"done": True, **result}}


def _entered_from(state: Mapping[str, Any], unit: str) -> str:
    """EVT-B10 to EVT-B16 `entered_from`: `start`, `proceed`, `back:<unit>`, `rewind:<unit>` or `resume`."""
    v = (state.get("visits") or {}).get(unit) or {}
    if v.get("entered_from"):
        return str(v["entered_from"])
    if int(v.get("visit", 1)) > 1 and v.get("from"):
        return f"back:{v['from']}"
    path = list(((state.get("run") or {}).get("path") or {}).get("units") or [])
    return "proceed" if path else "start"

