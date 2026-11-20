"""The public declaration interface (PKG §2.4, ADR-0106): the only engine module a workflow imports.

Each builder produces one CON §2.1 type and takes the same field names as keyword arguments; an unknown
argument is a ``TypeError`` at build time. ``name`` and ``version`` come from the package manifests and
are refused as arguments (PKG-B2). Kinds outside the running release build, and are refused at validation
with ``not_in_release`` (ADR-0090).
"""

from __future__ import annotations

import inspect
from collections.abc import Callable, Iterable, Mapping
from typing import Any

from tempergraph.contracts import (
    CallableRef,
    CheckFinding,
    CheckResult,
    Criterion,
    GateSpec,
    InputDeclaration,
    JudgeSpec,
    ProducesKind,
    ResolveResult,
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
    WorkflowSpec,
    WorktreeDecl,
)
from tempergraph.contracts import Param as _ParamType
from tempergraph.run.finalize import FinalizerContext, FinalizerResult

__all__ = [
    "CheckFinding", "CheckResult", "Criterion", "FinalizerContext", "FinalizerResult", "Gate", "Input", "Judge", "Param", "ResolveResult", "Route",
    "RouteView", "Routing", "Script", "SessionOptions", "Setting", "Step", "Switch", "Value", "Workflow",
    "WorktreeDecl", "text", "Parallel", "Map", "Ask", "Wait", "Council", "Contest", "Subworkflow",
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
    """A template or brief file inside the package (PKG §2.4)."""
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
          tools: Iterable[str] | None = None) -> JudgeSpec:
    refs = dict(references) if isinstance(references, Mapping) else {k: "required" for k in references}
    return JudgeSpec(file=file, stance=stance, brief=brief, references=refs, subject=tuple(subject),  # type: ignore[arg-type]
                     executor=executor, model=model, timeout_s=timeout_s,
                     tools=tuple(tools) if tools is not None else None)


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
         route_targets: Iterable[str] = ()) -> UnitSpec:
    m: str | tuple[str, ...] | None = model if model is None or isinstance(model, str) else tuple(model)
    step = StepSpec(executor=executor, prompt=prompt, tools=tuple(tools), commands=tuple(commands),
                    produces=dict(produces or {}), model=m, timeout_s=timeout_s, idle_s=idle_s,
                    session_options=session_options, before=tuple(before), after=tuple(after),
                    self_check=self_check, summary=summary, subagent_model=subagent_model)
    return UnitSpec(kind="step", gate=gate, step=step, route=_opt_ref(route), route_targets=tuple(route_targets))


def Route(*, select: Callable[..., Any], targets: Iterable[str], gate: GateSpec | None = None) -> UnitSpec:  # noqa: N802
    """A route unit: a pure function of state picks one static forward target or the finalizer (CMP §2.2)."""
    return UnitSpec(kind="route", gate=gate or GateSpec(), route=callable_ref(select), route_targets=tuple(targets))


def Switch(*, predicate: Callable[..., Any], arms: Mapping[str, str], default: str, sticky: str = "visit",  # noqa: N802
           gate: GateSpec | None = None) -> UnitSpec:
    sw = SwitchSpec(predicate=callable_ref(predicate), arms=dict(arms), default=default, sticky=sticky)  # type: ignore[arg-type]
    return UnitSpec(kind="switch", gate=gate or GateSpec(), switch=sw)


def _later(kind: str) -> Callable[..., UnitSpec]:
    def build(*, gate: GateSpec | None = None, **fields: Any) -> UnitSpec:
        return UnitSpec(kind=kind, gate=gate or GateSpec(), extra=dict(fields))  # type: ignore[arg-type]

    build.__name__ = kind.title()
    build.__doc__ = f"A `{kind}` unit; refused with `not_in_release` by this engine release (ADR-0090)."
    return build


Parallel = _later("parallel")
Map = _later("map")
Ask = _later("ask")
Wait = _later("wait")
Council = _later("council")
Contest = _later("contest")
Subworkflow = _later("subworkflow")

_WORKFLOW_FIELDS = {f for f in WorkflowSpec.__dataclass_fields__} - {"name", "version", "package_root", "outcome"}


def Workflow(*, order: Iterable[str], units: Mapping[str, UnitSpec], **fields: Any) -> WorkflowSpec:  # noqa: N802
    """Build a `WorkflowSpec`. `name` and `version` come from the manifests (PKG §2.2, PKG-B2)."""
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
