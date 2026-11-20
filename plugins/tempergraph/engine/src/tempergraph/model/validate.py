"""Validation before spend (WFM §2.1, §2.2).

One function guards the catalog, a start, a resume, the pre-start check and the upgrade check
(WFM-AC-2). Each refusal has its own finding code (WFM-AC-1). The engine never names a workflow (C8).
"""

from __future__ import annotations

import re
from collections.abc import Mapping
from dataclasses import dataclass
from typing import Literal

from tempergraph.constants import RELEASE
from tempergraph.contracts import (
    READ_ONLY_CAPABILITIES,
    CallableRef,
    Capabilities,
    Criterion,
    UnitSpec,
    ValueKind,
    WorkflowSpec,
    is_capability,
)
from tempergraph.model import flow
from tempergraph.model.text import ENGINE_KEYS, RESERVED_KEYS, TextUnreadable, input_names, load_text
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
    "parallel": 2, "map": 2, "wait": 2, "ask": 2, "council": 3, "contest": 3, "subworkflow": 3,
}
MODEL_KINDS = frozenset({"step"})
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
            self.err("reserved-unit-name", flow.OUTCOME_UNIT, "the unit name 'outcome' is reserved (OUT §2.4)")
        self._release()
        self._settings()
        self._routing()
        for name in s.order:
            self._unit(name, s.units[name])
        self._flow()
        self._finalizer()
        from tempergraph.model.prompt_lint import lint  # LIF: prompt lint is part of validate, as warnings

        self.findings += [Finding(f.code, f.unit, f"{f.where}: {f.message}", "warning") for f in lint(s)]
        if s.package_root is not None:  # PKG §2.3 step 6: then the package rules
            from tempergraph.package.loader import package_findings

            self.findings += package_findings(s)

    # -- release --------------------------------------------------------------------------------
    def _release(self) -> None:
        s = self.spec
        for name, u in s.units.items():
            if u.kind in LATER_KINDS:
                self.err("not_in_release", name,
                         f"unit kind {u.kind!r} is built in release {LATER_KINDS[u.kind]}, not release {RELEASE}")
            if u.step is not None and u.step.self_check:
                self.err("not_in_release", name, "`self_check` is built in release 2, not release 1")
            for sc in (u.step.before + u.step.after) if u.step else ():
                if sc.cache != "off":
                    self.err("not_in_release", name, "the script cache is built in release 2, not release 1")
            if u.script is not None and u.script.cache != "off":
                self.err("not_in_release", name, "the script cache is built in release 2, not release 1")
            g = u.gate
            if g.on_fail == "fallback" or g.on_budget_spent == "fallback" or g.fallback:
                self.err("not_in_release", name, "the fallback target is built in release 2, not release 1")
            if u.extra:
                self.err("not_in_release", name, f"fields {sorted(u.extra)} are not built in release {RELEASE}")
        if s.extra:
            self.err("not_in_release", None, f"workflow fields {sorted(s.extra)} are not built in release {RELEASE}")

    # -- settings and routing ---------------------------------------------------------------------
    def _settings(self) -> None:
        s = self.spec
        if not s.issue_repository or not ISSUE_REPO_RE.match(s.issue_repository):
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
        mechanical = [c for c in g.criteria if c.mechanical]
        if mechanical and g.check is None:
            self.err("mechanical-without-check", name, "a `mechanical` criterion needs a gate check")
        if u.kind == "step":
            self._step(name, u)
        elif u.kind == "script":
            self._script_unit(name, u)
        elif u.kind == "route":
            if u.route is None or not u.route_targets:
                self.err("route-invalid", name, "a route unit needs a select function and targets")
        elif u.kind == "switch":
            sw = u.switch
            if sw is None or not sw.arms or sw.default not in sw.arms:
                self.err("switch-invalid", name, "a switch needs arms and a default arm among them")
        if u.route is not None:
            self._callable(name, u.route, "route")
        if u.switch is not None:
            self._callable(name, u.switch.predicate, "switch predicate")
        for c in g.criteria:
            if c.severity not in ("blocker", "warning"):
                self.err("criterion-invalid", name, f"criterion severity {c.severity!r}")
            if not c.check_method.strip():
                self.warn("criterion-no-check-method", name, f"criterion {c.id or c.text[:30]!r} has no check method")

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
            for alias in _aliases(st.model) + _aliases(s.model_profile.get(name)):
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
        if isinstance(st.model, tuple) and len(st.model) > 8:
            self.err("ladder-too-long", name, "a model ladder holds at most eight aliases")
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
        # The judge moves to a capable executor at preflight (EXI §2.4); refuse only when none exists.
        if caps is not None and not caps.restricts_judge_tools and not any(
            c.restricts_judge_tools for c in self.executors.values()
        ):
                self.err("judge-executor-unrestricted", unit, "no registered executor can restrict judge tools")
        if j.model:
            target = caps or self.executors.get("claude")
            if target is not None:
                self._alias(unit, j.model, target)
        produces = u.step.produces if u.step else {}
        subject = j.subject or tuple(produces)
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
            if f.startswith("settings."):
                if f[len("settings."):] not in self.spec.settings:
                    self.err("template-unknown-field", unit, f"field {{{f}}} names no declared setting")
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
    return keys


def _dominates(spec: WorkflowSpec, a: str, b: str) -> bool:
    """True when every forward path from the first unit to ``b`` passes ``a``."""
    order = list(spec.order)
    start = order[0]
    if a == start:
        return True
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
