"""The public declaration interface (PKG-B19, PKG-B20, ADR-0106): the only engine module a workflow imports.

Each builder produces one CON-B4, CON-B5, CON-B6, CON-B7 type and takes the same field names as keyword arguments; an unknown
argument is a ``TypeError`` at build time. ``name`` and ``version`` come from the package manifests and
are refused as arguments (PKG-B2). Kinds outside the running release build, and are refused at validation
with ``not_in_release`` (ADR-0090).
"""

from __future__ import annotations

import dataclasses
import inspect
from collections.abc import Callable, Iterable, Mapping, Sequence
from typing import Any

from tempergraph import check_helpers as checks  # `tempergraph.api.checks` (SCF-B14 to SCF-B17)
from tempergraph.contracts import (
    AskQuestion,
    AskSpec,
    CallableRef,
    CheckFinding,
    CheckResult,
    ComplexitySpec,
    Criterion,
    EscalationSpec,
    GateSpec,
    InputDeclaration,
    JudgeSpec,
    MapSpec,
    MeasureSpec,
    ProducesKind,
    RearmSpec,
    ResolveResult,
    RiskLevel,
    RiskSpec,
    RiskWhen,
    RouteView,
    RoutingMetadata,
    ScriptSpec,
    SessionOptions,
    SettingDecl,
    StepSpec,
    SwitchSpec,
    TextRef,
    UnitSpec,
    ValueKind,
    WaitSpec,
    WorkflowSpec,
    WorktreeDecl,
)
from tempergraph.contracts import Param as _ParamType
from tempergraph.run.finalize import FinalizerContext, FinalizerResult

__all__ = [
    "CheckFinding", "CheckResult", "Criterion", "FinalizerContext", "FinalizerResult", "Gate", "Input", "Judge", "Param", "ResolveResult", "Route",
    "ComplexitySwitch", "Escalation", "Level", "Measure", "Risk", "When", "stock", "Rearm", "RouteView", "Routing", "Script", "SessionOptions", "Setting", "Step", "Switch", "Value", "Workflow",
    "WorktreeDecl", "checks", "text", "Parallel", "Question", "Map", "Ask", "Wait", "Council", "Contest", "Subworkflow",
]


def callable_ref(func: Callable[..., Any]) -> CallableRef:
    """Record a module-level function as `<module>:<qualname>`; refuse lambdas, nested and bound callables."""
    if isinstance(func, CallableRef):
        return func
    if not inspect.isfunction(func):
        raise TypeError(f"callable-not-importable: {func!r} is not a module-level function")
    qual = func.__qualname__
    if "<lambda>" in qual or "<locals>" in qual:
        raise TypeError(f"callable-not-importable: {func.__module__}:{qual}")
    return CallableRef(module=func.__module__, qualname=qual, func=func)


def _opt_ref(func: Callable[..., Any] | None) -> CallableRef | None:
    return None if func is None else callable_ref(func)


def text(path: str) -> TextRef:
    """A template or brief file inside the package (PKG-B19, PKG-B20)."""
    return TextRef(path=path)


def Value(*, choices: Iterable[str] | None = None, pattern: str | None = None, max_chars: int = 500,
          optional: bool = False) -> ValueKind:
    return ValueKind(choices=tuple(choices) if choices is not None else None, pattern=pattern,
                     max_chars=max_chars, optional=optional)


def Param(*, name: str, meaning: str = "", example: str = "", when_asked: str = "") -> _ParamType:  # noqa: N802
    return _ParamType(name=name, meaning=meaning, example=example, when_asked=when_asked)


def Input(*, kind: str = "text", parameters: Iterable[Any] = (), examples: Iterable[str] = (),  # noqa: N802
          prerequisites: Iterable[str] = (), resolver: Callable[..., Any] | None = None) -> InputDeclaration:
    return InputDeclaration(kind=kind, parameters=tuple(parameters), examples=tuple(examples),  # type: ignore[arg-type]
                            prerequisites=tuple(prerequisites), resolver=_opt_ref(resolver))


def Routing(*, description: str, when_to_use: str = "", task_kind: str = "prompt") -> RoutingMetadata:  # noqa: N802
    return RoutingMetadata(description=description, when_to_use=when_to_use, task_kind=task_kind)  # type: ignore[arg-type]


def Setting(*, kind: str, default: Any, meaning: str = "", choices: Iterable[str] | None = None,  # noqa: N802
            min: float | None = None, max: float | None = None) -> SettingDecl:
    return SettingDecl(kind=kind, default=default, meaning=meaning,  # type: ignore[arg-type]
                       choices=tuple(choices) if choices is not None else None, min=min, max=max)


def Judge(*, file: str | None = None, stance: str = "", brief: str = "",  # noqa: N802
          references: Mapping[str, str] | Iterable[str] = (), subject: Iterable[str] = (),
          executor: str | None = None, model: str | None = None, timeout_s: int | None = None,
          tools: Iterable[str] | None = None, effort: str | None = None,
          session_options: SessionOptions | None = None, sizing: str = "",
          risk: RiskSpec | None = None) -> JudgeSpec:
    """`sizing` is one sentence on why `model` and `effort` fit what this judge must read (SCF-B10)."""
    refs = dict(references) if isinstance(references, Mapping) else {k: "required" for k in references}
    if effort is not None:
        if session_options is not None and session_options.effort is not None:
            raise TypeError("Judge() takes `effort` once: as a field or in `session_options`")
        session_options = dataclasses.replace(session_options or SessionOptions(), effort=effort)  # type: ignore[arg-type]
    return JudgeSpec(file=file, stance=stance, brief=brief, references=refs, subject=tuple(subject),  # type: ignore[arg-type]
                     executor=executor, model=model, timeout_s=timeout_s,
                     tools=tuple(tools) if tools is not None else None, session_options=session_options,
                     sizing=sizing, risk=risk)


def Level(name: str, *, model: str | None = None, effort: str | None = None) -> RiskLevel:  # noqa: N802
    """One level of a judge (JRK-B6). The first level takes no model: it is the gate's own judge."""
    return RiskLevel(name=name, model=model, effort=effort)


def When(level: str, *, paths: Iterable[str] = (), min_paths: int = 1, min_lines: int | None = None,  # noqa: N802
         fact: tuple[str, str] | None = None, min_fact: float | None = None) -> RiskWhen:
    """A stock risk rule: `level` holds when the attempt changed `min_paths` paths under `paths`, `min_lines`
    lines, or a check fact reached `min_fact`. Of the rules that hold, the highest level wins."""
    return RiskWhen(level=level, paths=tuple(paths), min_paths=min_paths, min_lines=min_lines,
                    fact=tuple(fact) if fact else None, min_fact=min_fact)  # type: ignore[arg-type]


def Risk(*, levels: Iterable[RiskLevel], rule: Callable[..., Any] | None = None,  # noqa: N802
         when: Iterable[RiskWhen] = (), mode: str = "route") -> RiskSpec:
    """Raise a gate's judge by model-free facts of the attempt (JRK): a `rule(ctx: RiskContext)` that returns a
    level name (and optional signals), or stock `when` rules. It only ever raises, and a fault takes the last
    level."""
    return RiskSpec(levels=tuple(levels), rule=_opt_ref(rule), when=tuple(when), mode=mode)  # type: ignore[arg-type]


def Gate(*, check: Callable[..., Any] | None = None, check_timeout_s: int = 1800,  # noqa: N802
         judge: JudgeSpec | None = None, criteria: Iterable[Criterion] = (), on_fail: str = "retry",
         on_budget_spent: str = "ask", fallback: str | None = None, approval: bool = False,
         back_targets: Iterable[str] = (), loop_budget: int = 1, retry_budget: int = 2) -> GateSpec:
    return GateSpec(check=_opt_ref(check), check_timeout_s=check_timeout_s, judge=judge, criteria=tuple(criteria),
                    on_fail=on_fail, on_budget_spent=on_budget_spent, fallback=fallback,  # type: ignore[arg-type]
                    approval=approval, back_targets=tuple(back_targets), loop_budget=loop_budget,
                    retry_budget=retry_budget)


def Script(*, run: Iterable[str] | None = None, call: Callable[..., Any] | None = None,  # noqa: N802
           produces: Mapping[str, ProducesKind] | None = None, inputs: Iterable[str] = (),
           side_effects: str = "workspace", timeout_s: int = 600, cache: str = "off",
           environmental_exit_codes: Iterable[int] = (), summary: str = "", gate: GateSpec | None = None,
           name: str = "") -> Any:
    """A script declaration. With ``gate`` it is a script unit; without, a hybrid `before`/`after` script."""
    spec = ScriptSpec(run=tuple(run) if run is not None else None, call=_opt_ref(call), produces=dict(produces or {}),
                      inputs=tuple(inputs), side_effects=side_effects, timeout_s=timeout_s, cache=cache,  # type: ignore[arg-type]
                      environmental_exit_codes=tuple(environmental_exit_codes), summary=summary, name=name)
    if gate is None:
        return spec
    return UnitSpec(kind="script", gate=gate, script=spec)


def Step(*, gate: GateSpec, prompt: str | TextRef = "default", executor: str | None = None,  # noqa: N802
         tools: Iterable[str] = (), commands: Iterable[str] = (), produces: Mapping[str, ProducesKind] | None = None,
         model: str | Iterable[str] | None = None, timeout_s: int | None = None, idle_s: int | None = None,
         session_options: SessionOptions | None = None, before: Iterable[ScriptSpec] = (),
         after: Iterable[ScriptSpec] = (), self_check: bool = False, summary: str = "",
         subagent_model: str | None = None, route: Callable[..., Any] | None = None,
         route_targets: Iterable[str] = (), effort: str | None = None, effort_ladder: Iterable[str] = (),
         escalation: EscalationSpec | None = None, sizing: str = "") -> UnitSpec:
    """`effort` is the fixed effort; `effort_ladder` and `escalation` are the evidence-gated ladder (LAD-B9).
    `sizing` is one sentence on why `model` and the effort fit the step's work (SCF-B10)."""
    m: str | tuple[str, ...] | None = model if model is None or isinstance(model, str) else tuple(model)
    if effort is not None:
        if session_options is not None and session_options.effort is not None:
            raise TypeError("Step() takes `effort` once: as a field or in `session_options`")
        session_options = dataclasses.replace(session_options or SessionOptions(), effort=effort)  # type: ignore[arg-type]
    step = StepSpec(executor=executor, prompt=prompt, tools=tuple(tools), commands=tuple(commands),
                    produces=dict(produces or {}), model=m, timeout_s=timeout_s, idle_s=idle_s,
                    session_options=session_options, before=tuple(before), after=tuple(after),
                    self_check=self_check, summary=summary, subagent_model=subagent_model,
                    effort_ladder=tuple(effort_ladder), escalation=escalation, sizing=sizing)
    return UnitSpec(kind="step", gate=gate, step=step, route=_opt_ref(route), route_targets=tuple(route_targets))


def Route(*, select: Callable[..., Any], targets: Iterable[str], gate: GateSpec | None = None) -> UnitSpec:  # noqa: N802
    """A route unit: a pure function of state picks one static forward target or the finalizer (CMP-B10 to CMP-B16)."""
    return UnitSpec(kind="route", gate=gate or GateSpec(), route=callable_ref(select), route_targets=tuple(targets))


def Rearm(*, from_arm: str, to: str, units: Iterable[str], on: Iterable[str] = ("budget_spent",)) -> RearmSpec:  # noqa: N802
    """SWM-B7: move a run from arm `from_arm` to the entry of arm `to` when a listed unit ends on `on`."""
    return RearmSpec(from_arm=from_arm, to=to, units=tuple(units), on=tuple(on))


def Switch(*, predicate: Callable[..., Any], arms: Mapping[str, str], default: str, sticky: str = "visit",  # noqa: N802
           gate: GateSpec | None = None, mode: str = "route",
           arm_overrides: Mapping[str, Mapping[str, Mapping[str, Any]]] | None = None,
           rearm: Iterable[RearmSpec] = ()) -> UnitSpec:
    """A switch: a pure predicate picks one arm, the default on a fault (CMP-B10 to CMP-B16). `mode="shadow"` records
    the pick and takes the default; `arm_overrides` and `rearm` are SWM-B6, SWM-B7."""
    sw = SwitchSpec(predicate=callable_ref(predicate), arms=dict(arms), default=default, sticky=sticky,  # type: ignore[arg-type]
                    mode=mode,  # type: ignore[arg-type]
                    arm_overrides={a: {u: dict(v) for u, v in units.items()}
                                   for a, units in (arm_overrides or {}).items()},
                    rearm=tuple(rearm))
    return UnitSpec(kind="switch", gate=gate or GateSpec(), switch=sw)


class stock:  # noqa: N801 - a namespace of the stock measures (CXR-B9)
    """Stock measures for `Measure(name, stock.<measure>(...))`."""

    @staticmethod
    def fact(unit: str, key: str) -> tuple[str, ...]:
        return ("fact", unit, key)

    @staticmethod
    def input(name: str) -> tuple[str, ...]:
        return ("input", name)

    @staticmethod
    def setting(name: str) -> tuple[str, ...]:
        return ("setting", name)

    @staticmethod
    def count_items(unit: str, key: str) -> tuple[str, ...]:
        return ("count_items", unit, key)

    @staticmethod
    def count_lines(unit: str, key: str, pattern: str) -> tuple[str, ...]:
        return ("count_lines", unit, key, pattern)

    @staticmethod
    def changed_paths() -> tuple[str, ...]:
        return ("changed_paths",)


def Measure(name: str, source: tuple[str, ...] | Callable[..., Any]) -> MeasureSpec:  # noqa: N802
    """One measure of a complexity switch: a stock measure or a pure, model-free callable (CXR-B7)."""
    if callable(source):
        return MeasureSpec(name=name, call=callable_ref(source))
    return MeasureSpec(name=name, stock=tuple(str(x) for x in source))


def Escalation(*, to: str, stages: Mapping[str, str] | None = None, effort: str | None = None) -> EscalationSpec:  # noqa: N802
    """One attempt on the tier above the step's alias, on a repeated trusted blocker only (LAD-B12)."""
    return EscalationSpec(to=to, stages=dict(stages or {}), effort=effort)


def ComplexitySwitch(*, arms: Mapping[str, str], measures: Iterable[MeasureSpec], joins_at: str,  # noqa: N802
                     rules: str | None = None, size: str | None = None, explore: Mapping[str, Any] | None = None,
                     mode: str = "route", arm_overrides: Mapping[str, Mapping[str, Mapping[str, Any]]] | None = None,
                     rearm: Iterable[RearmSpec] = (), gate: GateSpec | None = None) -> UnitSpec:
    """A complexity switch (CXR): `arms` run from the simplest to the most detailed, which is the safe arm and
    the default. The engine picks the arm from the measures and the rules file; there is no predicate."""
    names = list(arms)
    sw = SwitchSpec(predicate=None, arms=dict(arms), default=names[-1] if names else "", sticky="run",
                    mode=mode,  # type: ignore[arg-type]
                    arm_overrides={a: {u: dict(v) for u, v in units.items()}
                                   for a, units in (arm_overrides or {}).items()},
                    rearm=tuple(rearm),
                    complexity=ComplexitySpec(measures=tuple(measures), joins_at=joins_at, rules=rules, size=size,
                                              explore=dict(explore) if explore else None))
    return UnitSpec(kind="switch", gate=gate or GateSpec(), switch=sw)


def _later(kind: str) -> Callable[..., UnitSpec]:
    def build(*, gate: GateSpec | None = None, **fields: Any) -> UnitSpec:
        return UnitSpec(kind=kind, gate=gate or GateSpec(), extra=dict(fields))  # type: ignore[arg-type]

    build.__name__ = kind.title()
    build.__doc__ = f"A `{kind}` unit; refused with `not_in_release` by this engine release (ADR-0090)."
    return build


def Map(*, items_from: tuple[str, str] | Sequence[str], step: UnitSpec, extract: Callable[..., Any] | None = None,  # noqa: N802
        max_items: int = 20, on_empty: str = "stop", mode: str = "sequential", concurrency: int = 3,
        item_model: Callable[..., Any] | None = None, models: Iterable[str] = ()) -> UnitSpec:
    """A map: `step` (built with `Step`) runs once per item of the list at `items_from` (`(unit, key)`), each
    item gated on its own by the step's gate (MAP-B7). Release 2 builds the sequential mode."""
    if step.kind != "step" or step.step is None:
        raise TypeError("Map(step=...) takes a unit built with Step()")
    if step.route is not None:
        raise TypeError("a map's step takes no route")
    unit, key = tuple(items_from)
    m = MapSpec(items_from=(str(unit), str(key)), extract=_opt_ref(extract), max_items=max_items,
                on_empty=on_empty, mode=mode, concurrency=concurrency,  # type: ignore[arg-type]
                item_model=_opt_ref(item_model), models=tuple(models))
    return UnitSpec(kind="map", gate=step.gate, step=step.step, map=m)


def Question(name: str, text: str, *, kind: str = "text", choices: Iterable[str] = (), required: bool = True,  # noqa: N802
             default: Any = None) -> AskQuestion:
    return AskQuestion(name=name, text=text, kind=kind, choices=tuple(choices), required=required,  # type: ignore[arg-type]
                       default=default)


def Ask(*, questions: Iterable[AskQuestion] = (), questions_from: str | None = None,  # noqa: N802
        context: Iterable[str] = (), check: Callable[..., Any] | None = None, deadline_s: int | None = None,
        on_deadline: str = "escalate", gate: GateSpec | None = None) -> UnitSpec:
    """An ask unit: pauses for a person's typed answers and stores them as the `answers` artifact (ASK-B5 to ASK-B9)."""
    return UnitSpec(kind="ask", gate=gate or GateSpec(), ask=AskSpec(
        questions=tuple(questions), questions_from=questions_from, context=tuple(context), check=_opt_ref(check),
        deadline_s=deadline_s, on_deadline=on_deadline))


def Wait(*, event: str, check: Callable[..., Any], deadline_s: int | None = None,  # noqa: N802
         on_deadline: str = "escalate", gate: GateSpec | None = None) -> UnitSpec:
    """An event wait: passes only on `event:<name>=<value>` that `check(value)` accepts (HUM-B4)."""
    return UnitSpec(kind="wait", gate=gate or GateSpec(), wait=WaitSpec(
        event=event, check=callable_ref(check), deadline_s=deadline_s, on_deadline=on_deadline))


def Parallel(*, branches: Iterable[str], gate: GateSpec | None = None) -> UnitSpec:  # noqa: N802
    """A parallel block's join: `branches` names two or more read-only units that run at once; the unit runs
    nothing itself and passes when every branch has passed (CMP-B10 to CMP-B16)."""
    return UnitSpec(kind="parallel", gate=gate or GateSpec(), branches=tuple(branches))


Council = _later("council")
Contest = _later("contest")
Subworkflow = _later("subworkflow")

_WORKFLOW_FIELDS = {f for f in WorkflowSpec.__dataclass_fields__} - {"name", "version", "package_root", "outcome"}


def Workflow(*, order: Iterable[str], units: Mapping[str, UnitSpec], **fields: Any) -> WorkflowSpec:  # noqa: N802
    """Build a `WorkflowSpec`. `name` and `version` come from the manifests (PKG-B13, PKG-B2)."""
    for banned in ("name", "version"):
        if banned in fields:
            raise TypeError(f"Workflow() got an unexpected keyword argument '{banned}' "
                            f"(it comes from the package manifests)")
    unknown = set(fields) - _WORKFLOW_FIELDS
    if unknown:
        raise TypeError(f"Workflow() got an unexpected keyword argument '{sorted(unknown)[0]}'")
    for key in ("finalizer", "command_resolver"):
        if key in fields and fields[key] is not None:
            fields[key] = callable_ref(fields[key])
    for key in ("finalizer_outcomes", "allow_commands"):
        if key in fields:
            fields[key] = tuple(fields[key])
    return WorkflowSpec(name="", order=tuple(order), units=dict(units), **fields)
