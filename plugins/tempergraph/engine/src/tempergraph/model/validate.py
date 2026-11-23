"""Validation before spend (WFM-B8, WFM-B9, WFM-B10, WFM-B11, WFM-B12).

One function guards the catalog, a start, a resume, the pre-start check and the upgrade check
(WFM-AC2). Each refusal has its own finding code (WFM-AC1). The engine never names a workflow (OVR-B10).
"""

from __future__ import annotations

import contextlib
import re
from collections.abc import Mapping
from dataclasses import dataclass
from typing import Any, Literal

from tempergraph.constants import RELEASE
from tempergraph.contracts import (
    ARM_OVERRIDE_KEYS,
    EFFORTS,
    READ_ONLY_CAPABILITIES,
    REARM_CAUSES,
    STAGES,
    CallableRef,
    Capabilities,
    Criterion,
    StepSpec,
    SwitchSpec,
    UnitSpec,
    ValueKind,
    WorkflowSpec,
    is_capability,
)
from tempergraph.improve import lessons
from tempergraph.model import flow
from tempergraph.model.text import (
    ENGINE_KEYS,
    ITEM_KEYS,
    RESERVED_KEYS,
    TextUnreadable,
    input_names,
    load_text,
)
from tempergraph.render.template import TemplateError, fields
from tempergraph.security.launch import has_shell_metacharacter


@dataclass(frozen=True)
class Finding:
    code: str
    unit: str | None
    message: str
    severity: Literal["error", "warning"] = "error"


# Kinds, primitives and fields this release does not build, with the release that adds them (ADR-0090).
LATER_KINDS: dict[str, int] = {
    "contest": 3,
}
# The artifacts a council produces, keyed by the unit (CNL-B10); the judge reads `decision` and `positions` (CNL-B4).
COUNCIL_ARTIFACTS = ("decision", "positions", "tally")
COUNCIL_MODES = ("synthesize", "vote", "rank")
COUNCIL_RULES = ("majority", "supermajority", "unanimous", "plurality")
STANCE_MAX = 400
MODEL_KINDS = frozenset({"step"})
# Keys the settings resolution writes into a unit's `extra` (RST `effective_spec`), never a workflow's own field.
RESOLVED_EXTRA = frozenset({"operator_set", "arm", "judge_operator_set", "session_cost_cap_usd"})
ISSUE_REPO_RE = re.compile(r"^[A-Za-z0-9_.-]+/[A-Za-z0-9_.-]+$")
SLUG_RE = re.compile(r"^[a-z0-9][a-z0-9_-]{0,63}$")
READ_VIEW_KINDS = frozenset({"file", "url", "value"})  # what a claude judge can read without MCP views


def validate(spec: WorkflowSpec, executors: Mapping[str, Capabilities]) -> list[Finding]:
    v = _Validator(spec, executors)
    v.run()
    return v.findings


def errors(findings: list[Finding]) -> list[Finding]:
    return [f for f in findings if f.severity == "error"]


class _Validator:
    def __init__(self, spec: WorkflowSpec, executors: Mapping[str, Capabilities]) -> None:
        self.spec = spec
        self.executors = executors
        self.findings: list[Finding] = []
        self._children: dict[str, Any] = {}

    def _child(self, name: str) -> Any:
        """A child read once per validation, by the one reader (SWF-B6, SWF-B12); loaded only when a unit names one."""
        if name not in self._children:
            from tempergraph.model import subworkflow

            self._children[name] = subworkflow.read_child(name)
        return self._children[name]

    def err(self, code: str, unit: str | None, message: str) -> None:
        self.findings.append(Finding(code, unit, message, "error"))

    def warn(self, code: str, unit: str | None, message: str) -> None:
        self.findings.append(Finding(code, unit, message, "warning"))

    def run(self) -> None:
        s = self.spec
        if not s.order:
            self.err("order-empty", None, "the workflow's order is empty")
            return
        for name in s.order:
            if name not in s.units:
                self.err("order-unknown-unit", name, f"order names {name!r}, which is not a unit")
        if any(f.code == "order-unknown-unit" for f in self.findings):
            return
        if flow.OUTCOME_UNIT in s.units:
            self.err("reserved-unit-name", flow.OUTCOME_UNIT, "the unit name 'outcome' is reserved (OUT-B15, OUT-B16, OUT-B17)")
        self._release()
        self._settings()
        self._routing()
        for name in s.order:
            self._unit(name, s.units[name])
        self._flow()
        self._finalizer()
        for code, unit, msg in lessons.validate(s):  # LSN-B6, LSN-B7
            self.err(code, unit, msg)
        from tempergraph.model.prompt_lint import lint  # LIF: prompt lint is part of validate, as warnings

        self.findings += [Finding(f.code, f.unit, f"{f.where}: {f.message}", "warning") for f in lint(s)]
        if s.package_root is not None and (s.package_root / "tempergraph.json").is_file():  # PKG-B15, PKG-B16, PKG-B17 step 6
            from tempergraph.package.loader import package_findings

            self.findings += package_findings(s)

    # -- release --------------------------------------------------------------------------------
    def _release(self) -> None:
        s = self.spec
        for name, u in s.units.items():
            if u.kind in LATER_KINDS:
                self.err("not_in_release", name,
                         f"unit kind {u.kind!r} is built in release {LATER_KINDS[u.kind]}, not release {RELEASE}")
            if u.step is not None and u.step.self_check and u.gate.check is None:
                self.err("self-check-without-check", name, "`self_check` needs a gate check to preview (CHK-B15, CHK-B14, CHK-B10, CHK-B17)")
            later = sorted(k for k in u.extra if k not in RESOLVED_EXTRA)
            if later:
                self.err("not_in_release", name, f"fields {later} are not built in release {RELEASE}")
        if s.extra:
            self.err("not_in_release", None, f"workflow fields {sorted(s.extra)} are not built in release {RELEASE}")

    # -- settings and routing ---------------------------------------------------------------------
    def _settings(self) -> None:
        s = self.spec
        if s.builtin and not s.issue_repository:
            pass  # a workflow the engine ships files nothing: it has no repository of its own (UWF-B6, UWF-B5, UWF-B7)
        elif not s.issue_repository or not ISSUE_REPO_RE.match(s.issue_repository):
            self.err("issue-repository-invalid", None, "`issue_repository` must be `owner/name`")
        if s.run_cost_cap_usd is not None and not s.run_cost_cap_usd > 0:
            self.err("cost-cap-invalid", None, "`run_cost_cap_usd` must be positive")
        for name, decl in s.settings.items():
            if not _setting_ok(decl.kind, decl.default, decl.choices, decl.min, decl.max):
                self.err("setting-default-invalid", None, f"setting {name!r}: default outside its kind or range")
        for pname, bundle in s.profiles.items():
            for key, value in bundle.items():
                if key.startswith("settings."):
                    found = s.settings.get(key[len("settings."):])
                    if found is None:
                        self.err("profile-key-unknown", None, f"profile {pname!r} names unknown setting {key!r}")
                    elif not _setting_ok(found.kind, value, found.choices, found.min, found.max):
                        self.err("profile-value-invalid", None, f"profile {pname!r}: {key} outside its range")

    # -- person units and flow extensions (ASK, HUM-B4, FLX-B11) -------------------------------------
    def _forward(self, name: str, target: str, *, finalizer: bool) -> bool:
        order = list(self.spec.order)
        if target == flow.FINALIZER:
            return finalizer
        return target in order and name in order and order.index(target) > order.index(name)

    def _deadline(self, name: str, deadline_s: int | None, on_deadline: str) -> None:
        if deadline_s is None:
            return
        if not isinstance(deadline_s, int) or deadline_s <= 0:
            self.err("deadline-invalid", name, "`deadline_s` must be a positive integer")
        if on_deadline not in ("escalate", "stop", "defaults") and not self._forward(name, on_deadline,
                                                                                    finalizer=True):
            self.err("deadline-target-not-forward", name,
                     f"`on_deadline` is `escalate`, `stop`, `defaults` (an ask only) or a unit after {name!r}, "
                     f"not {on_deadline!r}")

    def _person_gate(self, name: str, u: UnitSpec) -> None:
        g = u.gate
        if g.judge is not None or g.criteria:
            self.err("person-unit-judge", name, f"a `{u.kind}` unit has no judge and no criteria: the person's "
                                                "input, checked by rule, is the bar")
        if g.approval or g.back_targets:
            self.err("person-unit-gate", name, f"a `{u.kind}` unit takes no approval and no back target")

    def _ask(self, name: str, u: UnitSpec) -> None:
        from tempergraph.run import asking

        a = u.ask
        if a is None:
            self.err("ask-invalid", name, "an ask unit needs questions or `questions_from`")
            return
        self._person_gate(name, u)
        if bool(a.questions) == bool(a.questions_from):
            self.err("ask-invalid", name, "an ask takes exactly one of `questions` and `questions_from`")
        for problem in asking.question_problems(a.questions) if a.questions else ():
            self.err("ask-question-invalid", name, problem)
        if a.questions_from and a.questions_from not in self._keys_before(name):
            self.err("ask-from-unknown", name, f"`questions_from` names {a.questions_from!r}, which no earlier "
                                               "unit produces")
        for key in a.context:
            if key not in self._keys_before(name):
                self.err("ask-context-unknown", name, f"context names {key!r}, which no earlier unit produces")
        if a.check is not None:
            self._callable(name, a.check, "check")
        self._deadline(name, a.deadline_s, a.on_deadline)
        if a.on_deadline == "defaults" and a.questions:  # FLX-B11: with or without `deadline_s`
            for problem in asking.defaults_problems(a.questions):
                self.err("deadline-defaults-incomplete", name, problem)

    def _wait(self, name: str, u: UnitSpec) -> None:
        w = u.wait
        if w is None:
            self.err("wait-invalid", name, "a wait unit needs an event name and a check")
            return
        self._person_gate(name, u)
        if not SLUG_RE.match(w.event.replace("_", "-")):
            self.err("wait-invalid", name, f"event name {w.event!r} is not a slug")
        self._callable(name, w.check, "check")
        self._deadline(name, w.deadline_s, w.on_deadline)
        if w.on_deadline == "defaults":
            self.err("deadline-defaults-not-ask", name, "`on_deadline: defaults` fills an ask's questions; a wait "
                                                        "has none")

    def _keys_before(self, name: str) -> set[str]:
        return self._earlier_keys(name)["any"]

    def _parallel(self, name: str, u: UnitSpec) -> None:
        """CMP-B10 to CMP-B16, WFM-B7, WFM-B8: two or more branches directly before their join; a branch that declares
        `write` or `edit` works in its own worktree, which `workspace: in_place` has none of."""
        order = list(self.spec.order)
        if len(u.branches) < 2 or len(set(u.branches)) != len(u.branches):
            self.err("parallel-branches", name, "a parallel block needs two or more distinct branches")
            return
        at = order.index(name)
        for b in u.branches:
            bu = self.spec.units.get(b)
            if bu is None or b not in order:
                self.err("parallel-branch-unknown", name, f"branch {b!r} is not a unit in `order`")
                continue
            if order.index(b) > at:
                self.err("parallel-join-before-branch", name, f"the join {name!r} comes before its branch {b!r}")
            if bu.kind not in ("step", "script"):
                self.err("parallel-branch-kind", b, f"a branch is a step or a script unit, not a `{bu.kind}`")
            if bu.gate.back_targets or bu.gate.fallback or bu.route is not None or b in self.spec.flow:
                self.err("parallel-branch-flow", b, "a branch takes no back target, fallback, route or `next`: "
                                                    "its pass goes to the join")
            others = [n for n, o in self.spec.units.items() if n != name and o.kind == "parallel" and b in o.branches]
            if others:
                self.err("parallel-branch-shared", b, f"{b!r} is a branch of {name!r} and of {others[0]!r}")
        placed = [order.index(b) for b in u.branches if b in order]
        if placed and sorted(placed) != list(range(at - len(placed), at)):
            self.err("parallel-branches-not-adjacent", name, "a block's branches are the units directly before "
                                                             "its join in `order`")
        writers = flow.writer_branches(self.spec, name)
        if writers and self.spec.workspace == "in_place":  # WFM-B8: a writer branch has its own worktree
            self.err("parallel-writer-in-place", writers[0], f"{writers[0]!r} declares `write` or `edit`, which needs its "
                     "own worktree; a workflow that declares `workspace: in_place` has none (WSP-B11)")
        if u.gate.judge is not None or u.gate.criteria or u.gate.check is not None or u.gate.approval:
            self.err("parallel-join-gate", name, "the join is engine-owned in this release: it takes no check, "
                                                 "judge, criteria or approval")

    def _subworkflow(self, name: str, u: UnitSpec) -> None:
        """SWF-B6: the refusals of one sub-workflow unit, from the one reader of a child, with no spend."""
        if u.subworkflow is None:
            return
        from tempergraph.model import subworkflow

        for code, unit, message in subworkflow.unit_problems(self.spec, name, read=self._child):
            self.err(code, unit, message)
        child = self._child(u.subworkflow.workflow)
        if isinstance(child, subworkflow.Child) and child.spec.finalizer is not None:  # SWF-B8, SWF-B10
            self.warn("subworkflow-finalizer-skipped", name,
                      f"unit {name!r}: child {child.name!r} declares a finalizer, which never runs from a parent; the "
                      "parent's own finalizer can call the same code")

    def _council(self, name: str, u: UnitSpec) -> None:
        """CNL-B9, CNL-B16: the refusals of one council unit, each with its own finding code, and its three warnings."""
        s = self.spec
        c = u.council
        if c is None:
            self.err("council-missing", name, "a council unit needs its council fields")
            return
        block = flow.block_of(s, name)
        if block is not None and flow.writer_branches(s, block):  # WSP-B11: a branch of a writer block works in a worktree of its own
            self.err("council-in-writer-block", name, f"{name!r} is a branch of {block!r}, a block with a writer branch")
        if not 2 <= len(c.members) <= 7:
            self.err("council-members-count", name, f"a council has 2 to 7 members, not {len(c.members)}")
        names = [m.name for m in c.members]
        for dup in sorted({n for n in names if names.count(n) > 1}):
            self.err("council-member-duplicate", name, f"two members are named {dup!r}")
        for m in c.members:
            if not SLUG_RE.match(m.name):
                self.err("council-member-name-invalid", name, f"member name {m.name!r} is not a slug")
            if len(m.stance) > STANCE_MAX:
                self.err("council-stance-too-long", name, f"member {m.name!r}: a stance holds at most {STANCE_MAX} characters")
            for label, val in (("timeout_s", m.timeout_s), ("idle_s", m.idle_s)):
                if val is not None and (isinstance(val, bool) or not isinstance(val, int) or val <= 0):
                    self.err("timeout-invalid", name, f"member {m.name!r}: `{label}` must be a positive integer")
            for tool in m.tools:  # GRD: the engine's catalog holds no MCP tool read-only, so any MCP tool is refused
                if tool not in READ_ONLY_CAPABILITIES:
                    self.err("council-member-tool-not-read-only", name,
                             f"member {m.name!r}: tool {tool!r} is outside the read-only catalog")
        self._council_options(name, c)
        if not isinstance(c.rounds, int) or isinstance(c.rounds, bool) or not 0 <= c.rounds <= 3:
            self.err("council-rounds-invalid", name, "`rounds` is an integer from 0 to 3")
        if c.quorum is not None and (isinstance(c.quorum, bool) or not isinstance(c.quorum, int)
                                     or not 1 <= c.quorum <= max(len(c.members), 1)):
            self.err("council-quorum-invalid", name, "`quorum` is an integer from 1 to the member count")
        if c.on_no_decision not in ("escalate", "retry", "stop"):
            self.err("council-no-decision-invalid", name, "`on_no_decision` is escalate, retry or stop")
        if c.retry_scope not in ("all", "chair"):
            self.err("council-retry-scope-invalid", name, "`retry_scope` is all or chair")
        elif c.retry_scope == "chair" and c.mode == "vote":
            self.err("council-retry-scope-vote", name, "`retry_scope: chair` keeps final positions for `synthesize` and `rank`, not `vote`")
        if c.cost_cap_usd is not None and not c.cost_cap_usd > 0:
            self.err("cost-cap-invalid", name, "`cost_cap_usd` must be positive")
        if c.mode == "synthesize" and c.chair is None:
            self.err("council-chair-missing", name, "a `synthesize` council needs a chair")
        if u.gate.judge is None:  # OVR-B6: a council is a step; its gate has the one independent judge
            self.err("council-judge-missing", name, "a council's gate needs a judge")
        if not u.gate.criteria:
            self.err("criteria-missing", name, "a judged gate needs at least one criterion")
        self._template(name, c.question)
        self._council_sessions(name, u, c)
        if u.gate.judge is not None:
            self._judge(name, u, s.default_executor)
        if c.mode == "vote" and (c.rule or "majority") == "majority" and len(c.members) % 2 == 0:
            self.warn("council-even-majority", name, f"{name!r}: `rule: majority` with {len(c.members)} members can tie")
        if c.rounds > 0 and not c.anonymize:
            self.warn("council-anonymize-off", name, f"{name!r}: deliberation rounds with `anonymize: false` name the authors")

    def _council_options(self, name: str, c: Any) -> None:
        if c.mode not in COUNCIL_MODES:
            self.err("council-mode-invalid", name, f"`mode` is one of {list(COUNCIL_MODES)}")
        if c.mode != "vote":
            if c.rule is not None:
                self.err("council-rule-outside-vote", name, "`rule` belongs to a `vote` council")
            if c.options is not None:
                self.err("council-options-outside-vote", name, "`options` belongs to a `vote` council")
            return
        if c.rule is not None and c.rule not in COUNCIL_RULES:
            self.err("council-rule-invalid", name, f"`rule` is one of {list(COUNCIL_RULES)}")
        opts = c.options
        if opts is None or (not isinstance(opts, str) and len(opts) < 2):
            self.err("council-options-missing", name, "a `vote` council needs `options`: 2 to 10 slugs or a list artifact")
        elif isinstance(opts, str):
            if opts not in self._keys_before(name):
                self.err("council-options-unknown", name, f"`options` names {opts!r}, which no earlier unit produces")
        elif len(opts) > 10 or len(set(opts)) != len(opts) or not all(SLUG_RE.match(str(o)) for o in opts):
            self.err("council-options-invalid", name, "`options` are 2 to 10 distinct slugs")

    def _council_sessions(self, name: str, u: UnitSpec, c: Any) -> None:
        """The executor, alias and tools of each member and of the chair, and the one-family warning (CNL-B16, ARC-B15)."""
        s = self.spec
        families: list[str | None] = []
        for who, ex_name, alias, tools in [(f"member {m.name!r}", m.executor, m.model, m.tools) for m in c.members] + (
                [("the chair", c.chair.executor, c.chair.model, ())] if c.chair is not None else []):
            executor = ex_name or s.default_executor
            caps = self.executors.get(executor)
            if caps is None:
                self.err("executor-unknown", name, f"{who}: unknown executor {executor!r}")
                families.append(None)
                continue
            if alias:
                self._alias(name, alias, caps)
            for tool in tools:
                if tool in READ_ONLY_CAPABILITIES and not caps.maps(tool):
                    self.err("tool-unmapped", name, f"{who}: executor {executor!r} maps no tool for {tool!r}")
            if who != "the chair":
                families.append(caps.families.get(alias or "inherit"))
        if len(families) >= 2 and None not in families and len(set(families)) == 1:
            self.warn("council-one-family", name, f"{name!r}: every member runs on the {families[0]!r} model family")

    def _exposed(self, unit: str, owner: str, key: str) -> bool:
        """SWF-B12: `{<owner>.<key>}` read by `unit` names a key a sub-workflow unit earlier in the order exposes."""
        from tempergraph.model import subworkflow

        s = self.spec
        order = list(s.order)
        o = s.units.get(owner)
        if o is None or o.subworkflow is None or owner not in order or unit not in order \
                or order.index(owner) >= order.index(unit):
            return False
        child = self._child(o.subworkflow.workflow)
        if not isinstance(child, subworkflow.Child):  # a child that cannot be read exposes nothing
            return False
        return key in subworkflow.exposed_keys(o, child)

    def _fallback(self, name: str, u: UnitSpec) -> None:
        g = u.gate
        if (g.on_fail == "fallback" or g.on_budget_spent == "fallback") and not g.fallback:
            self.err("fallback-missing", name, "`on_fail: fallback` or `on_budget_spent: fallback` needs `fallback`")
        if g.fallback and not self._forward(name, g.fallback, finalizer=True):
            self.err("fallback-not-forward", name, f"`fallback` names {g.fallback!r}, which is not a unit after "
                                                   f"{name!r} or the finalizer")
        if g.fallback and g.on_fail != "fallback" and g.on_budget_spent != "fallback":
            self.warn("fallback-unused", name, "`fallback` is set but neither `on_fail` nor `on_budget_spent` "
                                               "uses it")

    def _routing(self) -> None:
        if not self.spec.routing.description.strip():
            self.err("routing-description-missing", None, "routing metadata needs a one-line description")

    # -- units ----------------------------------------------------------------------------------
    def _unit(self, name: str, u: UnitSpec) -> None:
        if name in RESERVED_KEYS:
            self.err("reserved-key", name, f"unit name {name!r} is a reserved template key")
        g = u.gate
        for label, n in (("retry_budget", g.retry_budget), ("loop_budget", g.loop_budget)):
            if not isinstance(n, int) or n < 0:
                self.err("budget-invalid", name, f"`{label}` must be an integer ≥ 0")
        if not isinstance(g.check_timeout_s, int) or g.check_timeout_s <= 0:
            self.err("timeout-invalid", name, "`check_timeout_s` must be a positive integer")
        if g.check is not None:
            self._callable(name, g.check, "check")
        self._fallback(name, u)
        if u.kind not in ("ask", "wait"):
            for label, d in (("ask", u.ask), ("wait", u.wait)):
                if d is not None:
                    self.err("deadline-misplaced", name, f"`{label}` fields, deadlines included, go on a "
                                                         f"`{label}` unit, not a `{u.kind}`")
        if u.council is not None and u.kind == "map":  # CNL-B16: a map item runs one session, never a council
            self.err("council-in-map-item", name, f"{name!r} is a map whose item would be a council")
        elif u.council is not None and u.kind != "council":
            self.err("council-misplaced", name, f"`council` fields go on a `council` unit, not a `{u.kind}`")
        mechanical = [c for c in g.criteria if c.mechanical]
        if mechanical and g.check is None:
            self.err("mechanical-without-check", name, "a `mechanical` criterion needs a gate check")
        if u.kind == "step":
            self._step(name, u)
        elif u.kind == "map":
            self._step(name, u)
            self._map(name, u)
        elif u.kind == "script":
            self._script_unit(name, u)
        elif u.kind == "parallel":
            self._parallel(name, u)
        elif u.kind == "subworkflow":
            self._subworkflow(name, u)
        elif u.kind == "council":
            self._council(name, u)
        elif u.kind == "ask":
            self._ask(name, u)
        elif u.kind == "wait":
            self._wait(name, u)
        elif u.kind == "route":
            if u.route is None or not u.route_targets:
                self.err("route-invalid", name, "a route unit needs a select function and targets")
        elif u.kind == "switch":
            sw = u.switch
            if sw is None or not sw.arms or sw.default not in sw.arms:
                self.err("switch-invalid", name, "a switch needs arms and a default arm among them")
            else:
                self._measured_switch(name, sw)
        if u.route is not None:
            self._callable(name, u.route, "route")
        if u.switch is not None and u.switch.complexity is not None:
            self._complexity(name, u.switch)
        elif u.switch is not None and u.switch.predicate is None:
            self.err("switch-invalid", name, "a switch needs a predicate")
        elif u.switch is not None:
            self._callable(name, u.switch.predicate, "switch predicate")  # type: ignore[arg-type]
        for c in g.criteria:
            if c.severity not in ("blocker", "warning"):
                self.err("criterion-invalid", name, f"criterion severity {c.severity!r}")
            if not c.check_method.strip():
                self.warn("criterion-no-check-method", name, f"criterion {c.id or c.text[:30]!r} has no check method")

    def _map(self, name: str, u: UnitSpec) -> None:
        """MAP-B11 and the limits of MAP-B7: the mode, `concurrency` of a concurrent map, and a concurrent map whose
        step writes in a workflow that has no worktrees."""
        m = u.map
        s = self.spec
        if m is None:
            self.err("map-invalid", name, "a map unit needs its map fields")
            return
        if m.mode not in ("sequential", "concurrent"):
            self.err("map-invalid", name, f"map mode {m.mode!r} is not sequential or concurrent")
        elif m.mode == "concurrent":
            if isinstance(m.concurrency, bool) or not isinstance(m.concurrency, int) or not 1 <= m.concurrency <= 10:
                self.err("map-invalid", name, "`concurrency` must be an integer from 1 to 10")
            if flow.writer_map(s, name) and s.workspace == "in_place":  # MAP-B11, WFM-B8, WSP-B11
                self.err("map-writer-in-place", name, f"{name!r} is a concurrent map whose step declares `write` or "
                         "`edit`, which needs a worktree for each item; a workflow that declares `workspace: "
                         "in_place` has none (WSP-B11)")
        if m.on_empty not in ("one_item", "stop", "skip"):
            self.err("map-invalid", name, f"on_empty {m.on_empty!r} is not one_item, stop or skip")
        if isinstance(m.max_items, bool) or not isinstance(m.max_items, int) or not 1 <= m.max_items <= 50:
            self.err("map-invalid", name, "`max_items` must be an integer from 1 to 50")
        if u.gate.back_targets:
            self.err("map-back-target", name, "a map's gate takes no back targets: a defect across items is found "
                                              "at the join (MAP-B11)")
        if u.route is not None or u.switch is not None:
            self.err("map-invalid", name, "a map takes no route")
        src, key = m.items_from
        order = list(s.order)
        if src not in s.units or src not in order or name not in order or order.index(src) >= order.index(name):
            self.err("map-items-unknown", name, f"items_from names {src!r}, which does not precede the map")
        elif key not in _produced(s.units[src]):
            self.err("map-items-unknown", name, f"{src!r} produces no {key!r}")
        elif key not in self._earlier_keys(name)["all"]:
            self.err("map-items-unknown", name, f"{key!r} is not produced on every path into the map")
        for ref, what in ((m.extract, "map extract"), (m.item_model, "map item_model")):
            if ref is not None:
                self._callable(name, ref, what)
        if m.item_model is not None and not 1 <= len(m.models) <= 8:
            self.err("map-invalid", name, "`item_model` needs one to eight declared `models`")
        caps = self.executors.get((u.step.executor if u.step else None) or s.default_executor)
        if caps is not None:
            for alias in m.models:
                self._alias(name, alias, caps)

    def _measured_switch(self, name: str, sw: SwitchSpec) -> None:
        """SWM-B4, SWM-B5: the mode, every arm override and every re-arm entry."""
        s = self.spec
        order = list(s.order)
        if sw.mode not in ("route", "shadow"):
            self.err("switch-invalid", name, f"switch mode {sw.mode!r} is not route or shadow")
        if any(t != flow.FINALIZER and t not in s.units for t in sw.arms.values()):
            return  # reported as target-unknown by the flow pass
        for arm, units in sw.arm_overrides.items():
            if arm not in sw.arms:
                self.err("switch-arm-unknown", name, f"arm_overrides names arm {arm!r}, which the switch lacks")
                continue
            reach = flow.arm_units(s, sw.arms[arm])
            for unit, values in units.items():
                target = s.units.get(unit)
                if unit not in reach or target is None or target.step is None:
                    self.err("switch-override-unreachable", name,
                             f"arm {arm!r} overrides {unit!r}, which is not a step on that arm's path")
                    continue
                for key, value in values.items():
                    self._override_value(name, arm, unit, target, key, value)
        for r in sw.rearm:
            if r.from_arm not in sw.arms or r.to not in sw.arms:
                self.err("switch-arm-unknown", name, f"rearm names an arm the switch lacks ({r.from_arm} -> {r.to})")
                continue
            entry = sw.arms[r.to]
            if not r.units or not r.on or any(c not in REARM_CAUSES for c in r.on):
                self.err("switch-rearm-invalid", name, f"rearm needs units and causes among {list(REARM_CAUSES)}")
            if r.from_arm == r.to or entry == flow.FINALIZER:
                self.err("switch-rearm-invalid", name, "rearm needs two different arms and a unit as the entry of `to`")
                continue
            for unit in r.units:
                if unit not in order or unit not in flow.arm_units(s, sw.arms[r.from_arm]):
                    self.err("switch-rearm-invalid", name, f"rearm unit {unit!r} is not on the path of arm {r.from_arm!r}")
                elif order.index(entry) >= order.index(unit):
                    self.err("switch-rearm-invalid", name,
                             f"the entry of arm {r.to!r} ({entry}) does not precede {unit!r}")

    def _ladder(self, name: str, st: StepSpec, caps: Capabilities | None, executor: str) -> None:
        """LAD-B9, LAD-B14: the shape of an effort ladder and whether the executor applies each rung."""
        from tempergraph.run.ladder import ascending

        rungs = tuple(st.effort_ladder)
        esc = st.escalation
        if esc is not None:  # LAD-B9: one tier above a plain tier alias, never from `large`, `inherit` or an item
            from tempergraph.run.ladder import MODES, TIER_UP, stages_ok

            model = st.model if isinstance(st.model, str) else None
            m = self.spec.units[name].map
            if model not in TIER_UP or TIER_UP[model] != esc.to or (m is not None and m.item_model is not None):
                self.err("escalation-invalid", name,
                         f"`escalation.to` must be exactly one tier above a `small` or `medium` step ({model!r} -> {esc.to!r})")
            elif caps is not None:
                self._alias(name, esc.to, caps)
            if not stages_ok(esc) or (esc.effort is not None and esc.effort not in EFFORTS):
                self.err("escalation-invalid", name, f"`escalation` takes stages {list(STAGES)} as {list(MODES)} and an effort")
            if dict(esc.stages).get("pipeline") == "offer":
                self.err("escalation-invalid", name, "a pipeline never waits on an offer: use `off` or `auto`")
        if not rungs:
            return
        if not 2 <= len(rungs) <= 4 or not ascending(rungs):
            self.err("ladder-invalid", name, f"`effort_ladder` holds 2 to 4 efforts of {list(EFFORTS)}, strictly ascending")
            return
        pinned = "effort" in (self.spec.units[name].extra.get("operator_set") or ())  # an operator's pin is no field
        if st.session_options is not None and st.session_options.effort is not None and not pinned:
            self.err("ladder-invalid", name, "`effort_ladder` excludes a fixed `effort`")
        if caps is None:
            return
        for rung in rungs:
            if "effort" not in caps.session_options or rung not in caps.efforts:
                self.err("effort-rung-unsupported", name,
                         f"step {name!r}: executor {executor!r} cannot apply effort {rung!r}; a climb would be silent")
            elif rung in caps.efforts_uncertain:
                self.warn("effort-rung-uncertain", name,
                          f"step {name!r}: effort {rung!r} on {executor!r} is not yet shown by a live probe")

    def _complexity(self, name: str, sw: SwitchSpec) -> None:
        """CXR-B7, CXR-B4, CXR-B10: the declaration, the rules file, the direction of re-arms and the arm contract."""
        from tempergraph.run import complexity as cx

        s = self.spec
        comp = sw.complexity
        assert comp is not None
        arms = list(sw.arms)
        if sw.predicate is not None:
            self.err("complexity-predicate", name, "a complexity switch takes no predicate; the engine reads the rules")
        names = [m.name for m in comp.measures]
        if not 2 <= len(arms) <= 3 or sw.default != (arms[-1] if arms else None) or sw.sticky != "run":
            self.err("complexity-invalid", name,
                     "a complexity switch has 2 or 3 arms, the last one as its default, and is sticky for the run")
        if not names or len(set(names)) != len(names) or any(not SLUG_RE.match(n) for n in names):
            self.err("complexity-invalid", name, "measures need unique slug names, at least one")
        for m in comp.measures:
            if m.call is not None:
                self._callable(name, m.call, f"measure {m.name}")
            elif not m.stock or cx.STOCK_ARITY.get(m.stock[0]) != len(m.stock) - 1:
                self.err("complexity-invalid", name, f"measure {m.name!r} is not a stock measure with its arguments")
            elif m.stock[0] in ("fact", "count_items", "count_lines") and m.stock[1] not in s.units:
                self.err("complexity-invalid", name, f"measure {m.name!r} names unknown unit {m.stock[1]!r}")
        if comp.size is not None and comp.size not in names:
            self.err("complexity-invalid", name, f"`size` names {comp.size!r}, which is not a measure")
        ex = comp.explore
        if ex is not None:
            rate, per_week = cx._num(ex.get("rate")), cx._num(ex.get("per_week"))
            if rate is None or per_week is None or not 0 < rate <= cx.EXPLORE_MAX_RATE \
                    or not 0 < per_week <= cx.EXPLORE_MAX_PER_WEEK or set(ex) - {"rate", "per_week"}:
                self.err("complexity-explore", name,
                         f"explore takes rate up to {cx.EXPLORE_MAX_RATE} and per_week up to {cx.EXPLORE_MAX_PER_WEEK}")
        for r in sw.rearm:
            if r.from_arm in arms and r.to in arms and arms.index(r.to) <= arms.index(r.from_arm):
                self.err("complexity-rearm", name, f"rearm {r.from_arm} -> {r.to} goes toward a simpler arm")
        if s.package_root is not None and len(set(names)) == len(names):
            loaded = cx.load_rules(s, name, None)
            if loaded["error"]:
                self.err("complexity-rules", name, f"rules file: {loaded['error']}")
        if any(t != flow.FINALIZER and t not in s.units for t in sw.arms.values()):
            return  # reported as target-unknown by the flow pass
        join = comp.joins_at
        if join not in s.units or join in sw.arms.values():
            self.err("complexity-joins", name, f"`joins_at` {join!r} is not a unit after every arm's entry")
            return
        after = flow.arm_units(s, join)
        paths: dict[str, set[str]] = {}
        for arm, entry in sw.arms.items():
            reach = flow.arm_units(s, entry) if entry != flow.FINALIZER else set()
            if join not in reach:
                self.err("complexity-joins", name, f"arm {arm!r} does not reach `joins_at` {join!r}")
                return
            paths[arm] = reach - after
            if flow.OUTCOME_UNIT in paths[arm]:
                self.err("complexity-joins", name, f"arm {arm!r} holds the final outcome gate")
            if any(s.units[u].switch is not None and s.units[u].switch.complexity is not None  # type: ignore[union-attr]
                   for u in paths[arm]):
                self.err("complexity-invalid", name, f"arm {arm!r} holds another complexity switch")
        made = {arm: set().union(*[_produced(s.units[u]) for u in units]) for arm, units in paths.items()}
        on_arms = set().union(*made.values())
        for reader in [u for u in s.order if u in after]:
            for key in sorted(self._reads(reader) & on_arms):
                for arm in arms:
                    if key not in made[arm]:
                        self.err("arm-contract", name,
                                 f"arm {arm!r} does not produce {key!r}, which {reader!r} reads after `joins_at`")

    def _reads(self, unit: str) -> set[str]:
        """Artifact keys a unit's prompt, judge references and map list name."""
        u = self.spec.units[unit]
        keys: set[str] = set()
        if u.step is not None:
            with contextlib.suppress(TextUnreadable, TemplateError):
                keys |= set(fields(load_text(self.spec, u.step.prompt)))
        if u.gate.judge is not None:
            keys |= set(u.gate.judge.references)
        if u.map is not None:
            keys.add(u.map.items_from[1])
        return keys

    def _override_value(self, name: str, arm: str, unit: str, target: UnitSpec, key: str, value: object) -> None:
        where = f"arm_overrides.{arm}.{unit}.{key}"
        if key not in ARM_OVERRIDE_KEYS:
            self.err("switch-override-invalid", name, f"{where}: an arm overrides only {', '.join(ARM_OVERRIDE_KEYS)}")
        elif key == "model":
            st = target.step
            caps = self.executors.get((st.executor if st else None) or self.spec.default_executor)
            aliases = [value] if isinstance(value, str) else list(value) if isinstance(value, (list, tuple)) else []
            if not aliases or not all(isinstance(a, str) for a in aliases):
                self.err("switch-override-invalid", name, f"{where}: not a model alias")
            elif caps is not None:
                for a in aliases:
                    self._alias(name, str(a), caps)
        elif key in ("timeout_s", "idle_s"):
            if isinstance(value, bool) or not isinstance(value, int) or value <= 0:
                self.err("switch-override-invalid", name, f"{where} must be a positive integer")
        elif key == "effort" and value not in EFFORTS:
            self.err("switch-override-invalid", name, f"{where}: {value!r} is not one of {', '.join(EFFORTS)}")

    def _step(self, name: str, u: UnitSpec) -> None:
        s = self.spec
        st = u.step
        if st is None:
            self.err("step-missing", name, "a step unit needs its step fields")
            return
        g = u.gate
        if g.judge is None:
            self.err("judge-missing", name, "a model step's gate needs a judge")
        if not g.criteria:
            self.err("criteria-missing", name, "a judged gate needs at least one criterion")
        executor = st.executor or s.default_executor
        caps = self.executors.get(executor)
        if caps is None:
            self.err("executor-unknown", name, f"unknown executor {executor!r}")
        else:
            for alias in _aliases(st.model)[:1] + _aliases(s.model_profile.get(name))[:1]:
                self._alias(name, alias, caps)
            for tool in st.tools:
                if not is_capability(tool):
                    self.err("tool-unknown", name, f"{tool!r} is not a tool capability")
                elif not caps.maps(tool):
                    self.err("tool-unmapped", name, f"executor {executor!r} maps no tool for {tool!r}")
            if st.session_options is not None:
                for opt in st.session_options.set_names():
                    if opt not in caps.session_options:
                        if opt == "effort":
                            self.warn("effort-unsupported", name, f"{executor!r} cannot apply `effort`")
                        else:
                            self.err("option-unsupported", name, f"{executor!r} does not support {opt!r}")
        self._ladder(name, st, caps, executor)
        from tempergraph.model import retire

        for where, got in retire.detect(s).items():  # LAD-B14: a release 1 model list, with its rewrite (LAD-B18)
            if where in (f"units.{name}.model", f"model_profile.{name}"):
                self.err("model-ladder-retired", name,
                         f"`{where}` is a list of models, retired in release 2; write {retire.describe(got)}")
        for label, val in (("timeout_s", st.timeout_s), ("idle_s", st.idle_s)):
            if val is not None and (not isinstance(val, int) or val <= 0):
                self.err("timeout-invalid", name, f"`{label}` must be a positive integer")
        self._commands(name, st.commands, "shell" in st.tools)
        for tool in st.tools:
            if tool.startswith("skill:"):
                self._skill(name, tool)
        self._produces(name, st.produces)
        self._judge(name, u, executor)
        self._template(name, st.prompt)
        for sc in st.before + st.after:
            self._script(name, sc, hybrid="before" if sc in st.before else "after")
        if g.approval is False and any(sc.side_effects == "external" for sc in st.after):
            self.warn("external-after-without-approval", name, "an `after` script with external side effects on a gate with no approval")

    def _alias(self, unit: str, alias: str, caps: Capabilities) -> None:
        if ":" in alias:
            ex, _ = alias.split(":", 1)
            if ex != caps.name:
                self.err("alias-unbound", unit, f"alias {alias!r} is qualified for another executor")
            else:
                self.warn("alias-qualified", unit, f"executor-qualified alias {alias!r} where a tier would do")
        elif alias not in caps.binds_aliases:
            self.err("alias-unbound", unit, f"{caps.name!r} binds no alias {alias!r}")

    def _commands(self, unit: str, commands: tuple[str, ...], has_shell: bool) -> None:
        allow = self.spec.allow_commands
        for cmd in commands:
            if has_shell_metacharacter(cmd):
                self.err("command-metacharacter", unit, f"command {cmd!r} holds a shell metacharacter")
            elif not any(cmd == a or cmd.startswith(a + " ") for a in allow):
                self.err("command-not-allowed", unit, f"command {cmd!r} is outside the workflow allow-list")
            if not has_shell:
                self.err("command-without-shell", unit, f"command {cmd!r} on a step that does not declare `shell`")

    def _skill(self, unit: str, tool: str) -> None:
        _, plugin, skill = tool.split(":", 2)
        root = self.spec.package_root
        if root is None or not (root / "skills" / skill / "SKILL.md").exists():
            self.err("skill-not-installed", unit, f"{tool!r}: skills/{skill}/SKILL.md is not in the package")

    def _produces(self, unit: str, produces: Mapping[str, object]) -> None:
        for key, kind in produces.items():
            if key in RESERVED_KEYS:
                self.err("reserved-key", unit, f"artifact key {key!r} is a reserved template key")
            if isinstance(kind, ValueKind):
                if kind.choices is not None and kind.pattern is not None:
                    self.err("value-choices-and-pattern", unit, f"value {key!r} sets both `choices` and `pattern`")
                if kind.pattern is not None:
                    try:
                        re.compile(kind.pattern)
                    except re.error:
                        self.err("value-pattern-invalid", unit, f"value {key!r} has an invalid pattern")
            elif kind not in ("file", "url", "wiki_page", "tracker_issue", "pull_request", "value"):
                self.err("artifact-kind-unknown", unit, f"artifact {key!r} has unknown kind {kind!r}")

    def _judge(self, unit: str, u: UnitSpec, step_executor: str) -> None:
        g = u.gate
        j = g.judge
        if j is None:
            return
        if j.tools is not None:
            for t in j.tools:
                if t not in READ_ONLY_CAPABILITIES:
                    self.err("judge-tool-not-read-only", unit, f"judge tool {t!r} is outside the read-only catalog")
        judge_ex = j.executor or step_executor
        caps = self.executors.get(judge_ex)
        # The judge moves to a capable executor at preflight (EXI-B24); refuse only when none exists.
        if caps is not None and not caps.restricts_judge_tools and not any(
            c.restricts_judge_tools for c in self.executors.values()
        ):
                self.err("judge-executor-unrestricted", unit, "no registered executor can restrict judge tools")
        if j.model:
            target = caps or self.executors.get("claude")
            if target is not None:
                self._alias(unit, j.model, target)
        if j.risk is not None:  # JRK-B6, JRK-B7, JRK-B2
            from tempergraph.run import risk as riskmod

            base = j.model or (u.step.model if u.step is not None and isinstance(u.step.model, str) else None)
            opts = j.session_options
            for problem in riskmod.problems(j.risk, base, opts.effort if opts else None):
                self.err("risk-invalid", unit, f"judge `risk`: {problem}")
            target = caps or self.executors.get("claude")
            for lv in j.risk.levels[1:]:
                if lv.model and target is not None:
                    self._alias(unit, lv.model, target)
            if j.risk.rule is not None:
                self._callable(unit, j.risk.rule, "risk rule")
        produces: Mapping[str, Any] = u.step.produces if u.step else (
            {k: "value" for k in COUNCIL_ARTIFACTS} if u.kind == "council" else {})
        subject = j.subject or (("decision",) if u.kind == "council" else tuple(produces))  # CNL-B4
        unverified = any(c.unverified_system for c in g.criteria)
        judge_caps = caps if (caps is not None and caps.restricts_judge_tools) else self.executors.get("claude")
        for key in subject:
            kind = produces.get(key)
            if isinstance(kind, ValueKind) or kind is None:
                continue
            if kind not in READ_VIEW_KINDS and not (judge_caps and judge_caps.judge_mcp) and not unverified:
                self.err("judge-view-unavailable", unit,
                         f"the judge cannot read artifact {key!r} of kind {kind!r}; mark the system unverified")
        earlier = self._earlier_keys(unit)
        for ref, need in j.references.items():
            if ref in ("request",) or ref in input_names(self.spec):
                continue
            if ref not in earlier["any"] and ref not in produces:
                self.err("reference-unknown", unit, f"judge reference {ref!r} is produced by no earlier unit")
            elif need == "required" and ref not in earlier["all"] and ref not in produces:
                self.err("reference-not-on-every-path", unit,
                         f"required judge reference {ref!r} is not produced on every path into {unit!r}")

    def _template(self, unit: str, source: object) -> None:
        try:
            text = load_text(self.spec, source)  # type: ignore[arg-type]
        except TextUnreadable as exc:
            self.err("template-unreadable", unit, str(exc))
            return
        try:
            names = fields(text)
        except TemplateError as exc:
            self.err("template-invalid", unit, str(exc))
            return
        inputs = input_names(self.spec)
        earlier = self._earlier_keys(unit)
        for f in names:
            if f in ENGINE_KEYS or f in inputs:
                continue
            if f in ITEM_KEYS and self.spec.units[unit].kind == "map":
                continue
            if f.startswith("settings."):
                if f[len("settings."):] not in self.spec.settings:
                    self.err("template-unknown-field", unit, f"field {{{f}}} names no declared setting")
                continue
            if "." in f:  # `<unit>.<key>` (CON-B8, SWF-B12)
                owner, key = f.split(".", 1)
                if not self._exposed(unit, owner, key):
                    self.err("template-unknown-field", unit,
                             f"field {{{f}}} is not a key an earlier sub-workflow unit {owner!r} exposes")
                continue
            if f in earlier["any"]:
                if f not in earlier["all"]:
                    self.warn("template-key-not-on-every-path", unit, f"field {{{f}}} is not produced on every path")
                continue
            self.err("template-unknown-field", unit, f"field {{{f}}} is neither an engine key, an input nor an earlier artifact")

    def _earlier_keys(self, unit: str) -> dict[str, set[str]]:
        """Artifact keys produced before ``unit``: on any path, and on every path from the start."""
        s = self.spec
        order = list(s.order)
        if unit not in order:
            return {"any": set(), "all": set()}
        idx = order.index(unit)
        any_keys: set[str] = set()
        for name in order[:idx]:
            any_keys |= _produced(s.units[name])
        # every path: keys of units that dominate `unit` (all paths from the first unit pass them)
        all_keys: set[str] = set()
        for name in order[:idx]:
            if _dominates(s, name, unit):
                all_keys |= _produced(s.units[name])
        return {"any": any_keys, "all": all_keys}

    def _script_unit(self, name: str, u: UnitSpec) -> None:
        if u.script is None:
            self.err("script-missing", name, "a script unit needs its script fields")
            return
        self._script(name, u.script, hybrid=None)
        if u.gate.judge is not None and not any(
            k in READ_VIEW_KINDS or isinstance(k, ValueKind) for k in u.script.produces.values()
        ):
            self.err("script-judge-nothing-to-read", name, "a judged script unit must produce a readable artifact")

    def _script(self, unit: str, sc: object, hybrid: str | None) -> None:
        from tempergraph.contracts import ScriptSpec

        assert isinstance(sc, ScriptSpec)
        if (sc.run is None) == (sc.call is None):
            self.err("script-run-or-call", unit, "a script needs exactly one of `run` and `call`")
        if sc.run is not None:
            if not sc.run:
                self.err("script-run-or-call", unit, "an empty `run`")
            else:
                for part in sc.run:
                    if part.startswith("{") and part.endswith("}") and "{" not in part[1:-1]:
                        continue
                    if has_shell_metacharacter(part):
                        self.err("script-part-invalid", unit, f"script part {part!r} is neither a constant nor one field")
                prefix = sc.run[0]
                if not any(prefix == a or prefix == a.split(" ")[0] for a in self.spec.allow_commands):
                    self.err("command-not-allowed", unit, f"script program {prefix!r} is outside the allow-list")
        if sc.call is not None:
            self._callable(unit, sc.call, "script")
        if sc.cache == "thread" and (sc.side_effects != "none" or not sc.inputs):
            self.err("script-cache-side-effects", unit, "a cached script must have no side effects and declare inputs")
        if hybrid == "before" and sc.side_effects == "external":
            self.err("script-before-external", unit, "a `before` script may not have external side effects")
        if not isinstance(sc.timeout_s, int) or sc.timeout_s <= 0:
            self.err("timeout-invalid", unit, "a script `timeout_s` must be a positive integer")
        self._produces(unit, sc.produces)

    def _callable(self, unit: str, ref: CallableRef, what: str) -> None:
        if "<locals>" in ref.qualname or "<lambda>" in ref.qualname:
            self.err("callable-not-importable", unit, f"{what} {ref.ref} is not module-level")
            return
        try:
            ref.resolve()
        except Exception as exc:  # noqa: BLE001 - any import failure is a finding
            self.err("callable-not-importable", unit, f"{what} {ref.ref}: {type(exc).__name__}")

    # -- flow -----------------------------------------------------------------------------------
    def _flow(self) -> None:
        s = self.spec
        order = list(s.order)
        for name in order:
            u = s.units[name]
            idx = order.index(name)
            targets: list[str] = []
            if u.route is not None:
                targets = list(u.route_targets)
            if u.switch is not None:
                targets = list(u.switch.arms.values())
            if name in s.flow and s.flow[name].next:
                targets.append(s.flow[name].next or "")
            for t in targets:
                if t == flow.FINALIZER:
                    continue
                if t not in order:
                    self.err("target-unknown", name, f"target {t!r} is outside order")
                elif order.index(t) <= idx:
                    self.err("target-not-forward", name, f"route target {t!r} is not a forward unit")
            for t in u.gate.back_targets:
                if t not in order:
                    self.err("target-unknown", name, f"back target {t!r} is outside order")
                elif order.index(t) >= idx:
                    self.err("back-target-not-earlier", name, f"back target {t!r} is not an earlier unit")
        if any(f.code.startswith("target-") or f.code == "back-target-not-earlier" for f in self.findings):
            return
        reach = flow.reachable_units(s)
        for name in order:
            if name not in reach:
                self.err("unreachable", name, f"unit {name!r} is unreachable")
        if not flow.finalizer_reachable(s):
            self.err("finalizer-unreachable", None, "no path reaches the finalizer")

    def _finalizer(self) -> None:
        s = self.spec
        if s.finalizer is not None:
            self._callable(None, s.finalizer, "finalizer")  # type: ignore[arg-type]
            if not s.finalizer_outcomes:
                self.err("finalizer-outcomes-missing", None, "a finalizer needs `finalizer_outcomes`")
            for o in s.finalizer_outcomes:
                if not SLUG_RE.match(o):
                    self.err("finalizer-outcomes-invalid", None, f"finalizer outcome {o!r} is not a slug")


def _aliases(model: str | tuple[str, ...] | None) -> list[str]:
    if model is None:
        return []
    if isinstance(model, str):
        return [model]
    return [m for m in model if isinstance(m, str)]


def _produced(u: UnitSpec) -> set[str]:
    keys: set[str] = set()
    if u.step is not None:
        keys |= set(u.step.produces)
        for sc in u.step.before + u.step.after:
            keys |= set(sc.produces)
    if u.script is not None:
        keys |= set(u.script.produces)
    if u.kind == "ask":
        keys.add("answers")  # ASK-B5, ASK-B6: the unit's one artifact
    if u.kind == "council":
        keys |= set(COUNCIL_ARTIFACTS)  # CNL-B10
    return keys


def _dominates(spec: WorkflowSpec, a: str, b: str) -> bool:
    """True when every forward path from the first unit to ``b`` passes ``a``."""
    order = list(spec.order)
    start = order[0]
    if a == start:
        return True
    join = flow.block_of(spec, a)
    if join is not None and join != b:  # CMP-B10 to CMP-B16: a join runs only once every branch has passed
        return _dominates(spec, join, b)
    seen: set[str] = set()
    todo = [start]
    while todo:
        u = todo.pop()
        if u == b:
            return False
        if u in seen or u == a or u == flow.FINALIZER or u not in spec.units:
            continue
        seen.add(u)
        todo.extend(flow.proceed_targets(spec, u))
    return True


def _setting_ok(kind: str, value: object, choices: tuple[str, ...] | None, lo: float | None, hi: float | None) -> bool:
    if kind == "bool":
        return isinstance(value, bool)
    if kind in ("int", "float"):
        if isinstance(value, bool) or not isinstance(value, (int, float)):
            return False
        if kind == "int" and not isinstance(value, int):
            return False
        return (lo is None or value >= lo) and (hi is None or value <= hi)
    if kind == "choice":
        return choices is not None and value in choices
    return isinstance(value, str)


def criteria_texts(criteria: tuple[Criterion, ...]) -> list[str]:
    return [c.text for c in criteria]
