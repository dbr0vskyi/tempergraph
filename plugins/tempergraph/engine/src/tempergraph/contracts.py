"""Shared types of CON (docs/specs/01-contracts.spec.md).

This module is the only definition of a type two or more engine components share (CON-AC-1).
Field names and defaults follow the spec tables; section numbers are given per block.
"""

from __future__ import annotations

import re
from collections.abc import Callable, Mapping
from dataclasses import dataclass, field
from enum import StrEnum
from pathlib import Path
from typing import Any, Literal, Protocol

# ---------------------------------------------------------------------------------------------
# Callable references (PKG §2.4): callables are recorded as `<module>:<qualname>`.


@dataclass(frozen=True, kw_only=True)
class CallableRef:
    module: str
    qualname: str
    func: Callable[..., Any] | None = field(default=None, compare=False, repr=False)

    @property
    def ref(self) -> str:
        return f"{self.module}:{self.qualname}"

    def resolve(self) -> Callable[..., Any]:
        if self.func is not None:
            return self.func
        import importlib

        obj: Any = importlib.import_module(self.module)
        for part in self.qualname.split("."):
            obj = getattr(obj, part)
        return obj


@dataclass(frozen=True, kw_only=True)
class TextRef:
    """A file reference relative to the package root (PKG §2.4 ``text()``)."""

    path: str


TextSource = str | TextRef  # inline text or a file ref; "default" is a literal value

# ---------------------------------------------------------------------------------------------
# §2.1 Workflow specification

UnitKind = Literal[
    "step", "route", "switch", "parallel", "map", "subworkflow", "wait", "script", "council", "contest", "ask"
]
ArtifactKind = Literal["file", "url", "wiki_page", "tracker_issue", "pull_request", "value"]
Severity = Literal["blocker", "warning"]


@dataclass(frozen=True, kw_only=True)
class ValueKind:
    """A `value` artifact with optional `choices` and `pattern` (VAL §2.1)."""

    choices: tuple[str, ...] | None = None
    pattern: str | None = None
    max_chars: int = 500
    optional: bool = False


ProducesKind = ArtifactKind | ValueKind


@dataclass(frozen=True, kw_only=True)
class Criterion:
    text: str
    check_method: str = ""
    severity: Severity = "blocker"
    id: str | None = None
    unverified_system: str | None = None
    no_change_policy: Literal["escalate", "retry"] = "escalate"
    mechanical: bool = False
    # Outcome fields (CON §2.14 OutcomeCriterion); empty for inline criteria.
    verified_by: Literal["check", "judge", "person", "none"] | None = None
    verifier: Mapping[str, Any] | None = None
    source: str | None = None
    serves: tuple[str, ...] = ()


@dataclass(frozen=True, kw_only=True)
class RiskLevel:
    """JRK §2.1: one level of a judge. Level 0 states no model: it is the gate's own judge, resolved as without
    `risk`; a later level names the alias, the effort, or both."""

    name: str
    model: str | None = None
    effort: str | None = None


@dataclass(frozen=True, kw_only=True)
class RiskWhen:
    """A stock risk rule (JRK, open question 1): the level holds when the attempt changed at least `min_paths`
    paths matching `paths`, or at least `min_lines` lines; with a fact, when its number is at least `min_fact`."""

    level: str
    paths: tuple[str, ...] = ()
    min_paths: int = 1
    min_lines: int | None = None
    fact: tuple[str, str] | None = None
    min_fact: float | None = None


@dataclass(frozen=True, kw_only=True)
class RiskSpec:
    """JRK §2.1: a model-free rule that only ever raises the judge. Exactly one of `rule` and `when`."""

    levels: tuple[RiskLevel, ...]
    rule: CallableRef | None = None
    when: tuple[RiskWhen, ...] = ()
    mode: Literal["route", "shadow"] = "route"


@dataclass(frozen=True, kw_only=True)
class RiskContext:
    """What a risk rule reads (JRK §2.2). It holds no step text, artifact content or step value."""

    unit: str
    item: str | None
    visit: int
    attempt: int
    git: Any
    facts: Mapping[str, Mapping[str, Any]]
    request: Mapping[str, Any]
    settings: Mapping[str, Any]
    stage: str
    producer: Mapping[str, Any]


@dataclass(frozen=True, kw_only=True)
class JudgeSpec:
    stance: str = ""
    brief: str = ""
    file: str | None = None  # judges/<unit>.md with two headings (PKG §2.4)
    references: Mapping[str, Literal["required", "optional"]] = field(default_factory=dict)
    subject: tuple[str, ...] = ()
    executor: str | None = None
    model: str | None = None
    timeout_s: int | None = None
    tools: tuple[str, ...] | None = None
    idle_s: int | None = None
    session_options: SessionOptions | None = None
    sizing: str = ""  # why this model and effort fit the judge's reading (SCF §2.1.1)
    risk: RiskSpec | None = None  # JRK: a stronger judge for a riskier attempt


@dataclass(frozen=True, kw_only=True)
class GateSpec:
    check: CallableRef | None = None
    check_timeout_s: int = 1800
    judge: JudgeSpec | None = None
    criteria: tuple[Criterion, ...] = ()
    on_fail: Literal["retry", "stop", "fallback"] = "retry"
    on_budget_spent: Literal["stop", "ask", "fallback"] = "ask"
    fallback: str | None = None
    approval: bool = False
    back_targets: tuple[str, ...] = ()
    loop_budget: int = 1
    retry_budget: int = 2


@dataclass(frozen=True, kw_only=True)
class SessionOptions:
    effort: Literal["low", "medium", "high", "xhigh", "max"] | None = None
    cost_cap_usd: float | None = None
    fallback_alias: str | None = None
    turn_cap: int | None = None

    def set_names(self) -> tuple[str, ...]:
        return tuple(n for n in ("effort", "cost_cap_usd", "fallback_alias", "turn_cap") if getattr(self, n) is not None)


@dataclass(frozen=True, kw_only=True)
class ScriptSpec:
    """SCR §2.1."""

    run: tuple[str, ...] | None = None
    call: CallableRef | None = None
    produces: Mapping[str, ProducesKind] = field(default_factory=dict)
    inputs: tuple[str, ...] = ()
    side_effects: Literal["none", "workspace", "external"] = "workspace"
    timeout_s: int = 600
    cache: Literal["off", "thread"] = "off"
    environmental_exit_codes: tuple[int, ...] = ()
    summary: str = ""
    name: str = ""


@dataclass(frozen=True, kw_only=True)
class StepSpec:
    executor: str | None = None
    prompt: TextSource = "default"
    tools: tuple[str, ...] = ()
    commands: tuple[str, ...] = ()
    produces: Mapping[str, ProducesKind] = field(default_factory=dict)
    model: str | tuple[str, ...] | None = None
    timeout_s: int | None = None
    idle_s: int | None = None
    session_options: SessionOptions | None = None
    before: tuple[ScriptSpec, ...] = ()
    after: tuple[ScriptSpec, ...] = ()
    self_check: bool = False
    summary: str = ""
    subagent_model: str | None = None
    sizing: str = ""  # why this model and effort fit the step's work (SCF §2.1.1)
    effort_ladder: tuple[str, ...] = ()  # LAD §2.1: rung 0 is the effort of a visit's first attempt
    escalation: EscalationSpec | None = None


@dataclass(frozen=True, kw_only=True)
class EscalationSpec:
    """LAD §2.4: one attempt on the next tier up, only on a repeated trusted blocker."""

    to: str
    stages: Mapping[str, str] = field(default_factory=dict)  # stage -> off | offer | auto
    effort: str | None = None


@dataclass(frozen=True, kw_only=True)
class RearmSpec:
    """SWM §2.4: while arm `from_arm` is in force, a listed unit ending on a cause in `on` sends the run to
    the entry of arm `to`."""

    from_arm: str
    to: str
    units: tuple[str, ...]
    on: tuple[str, ...] = ("budget_spent",)


@dataclass(frozen=True, kw_only=True)
class MeasureSpec:
    """CXR §2.1: one named measure, from a stock measure (`stock`: its name and arguments) or a callable."""

    name: str
    stock: tuple[str, ...] = ()
    call: CallableRef | None = None


@dataclass(frozen=True, kw_only=True)
class ComplexitySpec:
    """CXR §2.1: what makes a switch a complexity switch. Its arms run from the simplest to the safe arm."""

    measures: tuple[MeasureSpec, ...]
    joins_at: str
    rules: str | None = None  # a path in the package; `routing/<switch>.json` when None
    size: str | None = None
    explore: Mapping[str, Any] | None = None  # {rate, per_week}


@dataclass(kw_only=True)
class MeasureContext:
    """What a measure callable reads (CXR §2.3). It holds no step value."""

    request: Mapping[str, Any]
    facts: Mapping[str, Mapping[str, str]]
    artifacts: Mapping[str, Mapping[str, str]]
    settings: Mapping[str, Any]
    stage: str
    workdir: Path
    git: Any = None

    def read_text(self, path: str | Path, max_bytes: int = 1_000_000) -> str:
        p = (self.workdir / path).resolve()
        if not p.is_relative_to(self.workdir.resolve()):
            raise ValueError(f"{path} is outside the workspace")
        with open(p, "rb") as fh:
            return fh.read(max_bytes).decode("utf-8", errors="replace")


EFFORTS = ("low", "medium", "high", "xhigh", "max")  # ascending (LAD §2.1)
STAGES = ("local-dev", "local-stable", "pipeline")  # PRO §2.1
ARM_OVERRIDE_KEYS = ("model", "timeout_s", "idle_s", "effort", "effort_ladder", "escalation")
REARM_CAUSES = ("budget_spent", "timeout")


@dataclass(frozen=True, kw_only=True)
class SwitchSpec:
    """CMP §2.2 switch: predicate, arms and a default arm; stickiness per visit or run. SWM §2.1 adds the
    mode, the per-arm overrides and the re-arm entries."""

    predicate: CallableRef | None
    arms: Mapping[str, str]  # arm name -> target unit or "finalizer"
    default: str
    sticky: Literal["visit", "run"] = "visit"
    mode: Literal["route", "shadow"] = "route"
    arm_overrides: Mapping[str, Mapping[str, Mapping[str, Any]]] = field(default_factory=dict)  # arm -> unit -> values
    rearm: tuple[RearmSpec, ...] = ()
    complexity: ComplexitySpec | None = None  # CXR: the engine builds the predicate from measures and rules

    def rearm_units(self) -> frozenset[str]:
        return frozenset(u for r in self.rearm for u in r.units)


@dataclass(frozen=True, kw_only=True)
class MapItem:
    """MAP §2.1: one item of a map's list; `id` names its artifacts, records and pauses."""

    id: str
    text: str = ""


@dataclass(frozen=True, kw_only=True)
class ExtractContext:
    """What a map's `extract` callable reads (MAP §2.1): read-only."""

    artifact: Path
    workdir: Path
    values: Mapping[str, str] = field(default_factory=dict)


@dataclass(frozen=True, kw_only=True)
class MapSpec:
    """MAP §2.1. The step and the gate every item runs are the unit's own `step` and `gate`."""

    items_from: tuple[str, str]  # (unit, key) of the artifact that holds the list
    extract: CallableRef | None = None
    max_items: int = 20
    on_empty: Literal["one_item", "stop", "skip"] = "stop"
    mode: Literal["sequential", "concurrent"] = "sequential"
    concurrency: int = 3
    item_model: CallableRef | None = None
    models: tuple[str, ...] = ()  # the aliases `item_model` may choose among


AnswerKind = Literal["text", "choice", "choices", "number", "bool", "file", "url"]


@dataclass(frozen=True, kw_only=True)
class AskQuestion:
    """ASK §2.1 `Question`: one typed question of an ask unit."""

    name: str
    text: str
    kind: AnswerKind = "text"
    choices: tuple[str, ...] = ()
    required: bool = True
    default: Any = None


@dataclass(frozen=True, kw_only=True)
class AskSpec:
    """ASK §2.1: declared questions, or a list artifact of them written by an earlier step."""

    questions: tuple[AskQuestion, ...] = ()
    questions_from: str | None = None  # the `from` field: an artifact key
    context: tuple[str, ...] = ()
    check: CallableRef | None = None  # pure: answers -> a list of problems, empty when they pass
    deadline_s: int | None = None
    on_deadline: str = "escalate"  # `escalate`, `stop` or a forward unit (FLX §2.3)


@dataclass(frozen=True, kw_only=True)
class WaitSpec:
    """An event wait (CMP §2.2, HUM-B4): passes only on `event:<name>=<value>` the pure check accepts."""

    event: str
    check: CallableRef  # pure: the delivered value -> bool
    deadline_s: int | None = None
    on_deadline: str = "escalate"


@dataclass(frozen=True, kw_only=True)
class UnitSpec:
    kind: UnitKind
    gate: GateSpec
    ask: AskSpec | None = None
    wait: WaitSpec | None = None
    branches: tuple[str, ...] = ()  # a parallel block's branch units; the unit itself is the join (CMP §2.2)
    step: StepSpec | None = None
    map: MapSpec | None = None
    script: ScriptSpec | None = None
    route: CallableRef | None = None  # route unit or a step's route (CMP §2.2)
    route_targets: tuple[str, ...] = ()
    switch: SwitchSpec | None = None
    extra: Mapping[str, Any] = field(default_factory=dict)  # fields of kinds not in this release


@dataclass(frozen=True, kw_only=True)
class FlowSpec:
    """Where a pass goes when it is not the next unit in `order`."""

    next: str | None = None


@dataclass(frozen=True, kw_only=True)
class Param:
    name: str
    meaning: str = ""
    example: str = ""
    when_asked: str = ""


@dataclass(frozen=True, kw_only=True)
class InputDeclaration:
    kind: Literal["any", "tracker_key", "file", "text", "resolver"] = "text"
    parameters: tuple[Param, ...] = ()
    examples: tuple[str, ...] = ()
    prerequisites: tuple[str, ...] = ()
    resolver: CallableRef | None = None


@dataclass(frozen=True, kw_only=True)
class Question:
    name: str
    question: str
    choices: tuple[str, ...] | None = None


@dataclass(frozen=True, kw_only=True)
class ResolveResult:
    status: Literal["ok", "needs", "error"]
    task_id: str = ""
    inputs: Mapping[str, str] = field(default_factory=dict)
    questions: tuple[Question, ...] = ()
    message: str = ""


@dataclass(frozen=True, kw_only=True)
class RoutingMetadata:
    description: str = ""
    when_to_use: str = ""
    task_kind: Literal["ticket", "prompt", "symptom", "repository", "findings"] = "prompt"


@dataclass(frozen=True, kw_only=True)
class SettingDecl:
    kind: Literal["bool", "int", "float", "duration_s", "choice", "text"]
    default: Any
    meaning: str = ""
    choices: tuple[str, ...] | None = None
    min: float | None = None
    max: float | None = None


@dataclass(frozen=True, kw_only=True)
class WorktreeDecl:
    """WTR §2.3."""

    include: tuple[str, ...] = ()  # gitignore-style patterns, at most 50
    setup: tuple[tuple[str, ...], ...] = ()  # argv lists, at most 10, each on the allow-list
    submodules: Literal["auto", "skip"] = "auto"
    setup_timeout_s: int = 600
    base: str | None = None
    cleanup: Literal["never", "on_finish"] | None = None


@dataclass(frozen=True, kw_only=True)
class WorkflowSpec:
    name: str
    order: tuple[str, ...]
    units: Mapping[str, UnitSpec]
    flow: Mapping[str, FlowSpec] = field(default_factory=dict)
    input: InputDeclaration = field(default_factory=InputDeclaration)
    workspace: Literal["auto", "in_place", "worktree"] = "auto"
    worktree: WorktreeDecl | None = None
    finalizer: CallableRef | None = None
    finalizer_outcomes: tuple[str, ...] = ()
    default_executor: str = "claude"
    model_profile: Mapping[str, str | tuple[str, ...]] = field(default_factory=dict)
    issue_repository: str = ""
    routing: RoutingMetadata = field(default_factory=RoutingMetadata)
    improvement_mode: Literal["dev", "stable"] = "dev"
    session_review: Literal["auto", "full", "signals", "off"] = "auto"  # improvement.session_review (SRV §2.3)
    verified_engine: str | None = None
    command_resolver: CallableRef | None = None
    run_cost_cap_usd: float | None = None
    daily_cap_usd: float | None = None  # stable mode's loop budget per UTC day; dev mode has none (SIL §4)
    version: str = "0.0.0"
    requires_engine: str | None = None
    upgrade: Mapping[str, Any] | None = None
    settings: Mapping[str, SettingDecl] = field(default_factory=dict)
    profiles: Mapping[str, Mapping[str, Any]] = field(default_factory=dict)
    outcome: OutcomeSpec | None = None
    allow_commands: tuple[str, ...] = ()  # the workflow-wide command allow-list (WFM §2.1)
    builtin: bool | str = False  # a workflow the engine ships, by its flag, for example `upgrade` (WFM §2, UWF §2.1)
    package_root: Path | None = None
    extra: Mapping[str, Any] = field(default_factory=dict)  # fields outside this release


# ---------------------------------------------------------------------------------------------
# §2.5 Tool capabilities

READ_ONLY_CAPABILITIES = frozenset({"read", "search", "list", "web_fetch", "web_search"})
WRITE_CAPABILITIES = frozenset({"edit", "write", "shell"})
BASE_CAPABILITIES = frozenset(READ_ONLY_CAPABILITIES | WRITE_CAPABILITIES | {"subagent"})
_MCP_RE = re.compile(r"^mcp:[A-Za-z0-9_.-]+/[A-Za-z0-9_.-]+$")
_SKILL_RE = re.compile(r"^skill:[A-Za-z0-9_.-]+:[A-Za-z0-9_.-]+$")


def is_capability(name: str) -> bool:
    return name in BASE_CAPABILITIES or bool(_MCP_RE.match(name)) or bool(_SKILL_RE.match(name))


# ---------------------------------------------------------------------------------------------
# §2.6 Executor protocol types


class InfraCause(StrEnum):
    SPAWN_FAILED = "spawn_failed"
    PROMPT_NOT_DELIVERED = "prompt_not_delivered"
    NO_OUTPUT = "no_output"
    NO_RESULT = "no_result"
    BROKEN_PIPE = "broken_pipe"
    CONNECTION = "connection"
    OUT_OF_MEMORY = "out_of_memory"
    REQUEST_TIMED_OUT = "request_timed_out"
    SLOW_HOST = "slow_host"
    THROTTLED = "throttled"


ErrorKind = Literal["model", "refused", "cap_reached", "turn_cap", "denied", "auth", "unknown"]
SessionKind = Literal["step", "retry", "judge", "judge_reask", "grouping", "member", "member_reask", "chair"]


@dataclass(kw_only=True)
class Usage:
    input_tokens: int | None = None
    output_tokens: int | None = None
    cache_read_tokens: int | None = None
    cache_write_tokens: int | None = None
    thinking_tokens: int | None = None
    reported_cost_usd: float | None = None
    estimated_cost_usd: float | None = None
    by_model: dict[str, dict[str, Any]] = field(default_factory=dict)
    turns: int | None = None
    peak_context_tokens: int | None = None

    def has_tokens(self) -> bool:
        return self.input_tokens is not None or self.output_tokens is not None

    def to_json(self) -> dict[str, Any]:
        return {
            "input_tokens": self.input_tokens,
            "output_tokens": self.output_tokens,
            "cache_read_tokens": self.cache_read_tokens,
            "cache_write_tokens": self.cache_write_tokens,
            "thinking_tokens": self.thinking_tokens,
            "reported_cost_usd": self.reported_cost_usd,
            "estimated_cost_usd": self.estimated_cost_usd,
            "by_model": self.by_model,
            "turns": self.turns,
            "peak_context_tokens": self.peak_context_tokens,
        }


@dataclass(frozen=True, kw_only=True)
class Capabilities:
    name: str
    binds_aliases: frozenset[str]
    families: Mapping[str, str] = field(default_factory=dict)
    prompt_off_argv: bool = False
    streams_events: bool = False
    reports_actions: bool = False
    reports_tokens: bool = False
    reports_cost: bool = False
    enforces_step_tools: bool = False
    restricts_judge_tools: bool = False
    step_allow_rules: bool = False
    judge_mcp: bool = False
    isolates_user_config: bool = False
    fresh_session: bool = False
    hosts_authoring_surface: bool = False
    session_options: frozenset[str] = frozenset()
    efforts: frozenset[str] = frozenset({"low", "medium", "high", "xhigh", "max"})  # efforts it applies
    efforts_uncertain: frozenset[str] = frozenset()  # declared, not yet shown by a live probe (LAD §2.6)
    tool_map: Mapping[str, tuple[str, ...]] = field(default_factory=dict)
    version: str = ""

    def maps(self, capability: str) -> bool:
        if capability in self.tool_map:
            return True
        if capability.startswith("mcp:") and "mcp:*" in self.tool_map:
            return True
        return capability.startswith("skill:") and "skill:*" in self.tool_map

    def knows_tool(self, name: str) -> bool:
        """A tool name the executor reported is in its view catalog (SIL-B4: else `unknown_tool_name`)."""
        if name.startswith("mcp__"):
            return "mcp:*" in self.tool_map
        return any(name in names for names in self.tool_map.values())


@dataclass(frozen=True, kw_only=True)
class SessionRequest:
    kind: SessionKind
    prompt: str
    workdir: Path
    alias: str
    session_key: str
    tools: tuple[str, ...] = ()
    commands: tuple[str, ...] = ()
    timeout_s: int = 600
    idle_s: int | None = None
    options: SessionOptions = field(default_factory=SessionOptions)
    credentials_profile: str | None = None
    session_dir: Path | None = None  # where the launcher writes raw.jsonl, stderr.log (LOS §2.1)
    enforce_tools: bool = False
    in_engine_worktree: bool = False
    plugin_dir: Path | None = None  # PKG §2.6: step sessions only


@dataclass(frozen=True, kw_only=True)
class ToolCall:
    name: str
    ok: bool | None = None
    subagent: bool = False
    call_id: str = ""


@dataclass(kw_only=True)
class SessionResult:
    ok: bool
    text: str = ""
    session_id: str | None = None
    usage: Usage = field(default_factory=Usage)
    tool_calls: list[ToolCall] = field(default_factory=list)
    timed_out: bool = False
    stalled: bool = False
    partial: bool = False
    infra_cause: InfraCause | None = None
    error_kind: ErrorKind | None = None
    applied_options: tuple[str, ...] = ()
    cli_version: str = ""
    model: str | None = None
    denied: tuple[str, ...] = ()
    tools_at_start: tuple[str, ...] = ()
    tool_wall_share: float = 0.0  # share of wall time spent inside tool calls (BUD §2.2 slow_host)
    prompt_gap_s: float | None = None
    duration_s: float | None = None
    argv: tuple[str, ...] = ()  # the launch argv, for records and canary tests


ProbeWord = Literal["ok", "missing", "signed_out", "version_unreadable", "probe_failed"]


@dataclass(frozen=True, kw_only=True)
class ProbeReport:
    """What `Executor.probe()` saw, read-only and model-free (EXI §2.1, ECC §4)."""

    ok: bool
    reason: ProbeWord = "ok"
    version: str = ""
    path: str = ""
    facts: Mapping[str, Any] = field(default_factory=dict)


@dataclass(frozen=True, kw_only=True)
class Deferred:
    """A judge view the executor cannot hold to read-only; its criterion renders as out of reach (GRD)."""

    capability: str
    reason: str


@dataclass(frozen=True, kw_only=True)
class ViewSet:
    """A judge's view set, in the judge executor's own tool names (GRD §2)."""

    tools: tuple[str, ...] = ()
    deferred: tuple[Deferred, ...] = ()
    tool_less: bool = False  # the session reviewer: no tools at all, not the default read-only set (SRV §2.6)


class Executor(Protocol):
    """CON §2.6. Neither run method raises for a session failure; failure is a field of the result."""

    name: str

    def capabilities(self) -> Capabilities: ...
    def probe(self) -> ProbeReport: ...
    def run_step(self, req: SessionRequest, sink: EventSink) -> SessionResult: ...
    def run_judge(self, req: SessionRequest, views: ViewSet, sink: EventSink) -> SessionResult: ...


# ---------------------------------------------------------------------------------------------
# §2.7 Normalized session events


@dataclass(frozen=True, kw_only=True)
class Event:
    kind: Literal[
        "session_started", "model_delta", "tool_started", "tool_finished", "text", "retrying", "denied", "result"
    ]
    data: Mapping[str, Any] = field(default_factory=dict)
    ts: float = 0.0


class EventSink:
    """Receives normalized events; the base sink keeps them in a list."""

    def __init__(self) -> None:
        self.events: list[Event] = []

    def push(self, event: Event) -> None:
        self.events.append(event)


# ---------------------------------------------------------------------------------------------
# §2.8 Judgement, verdict and check results


class Verdict(StrEnum):
    PROCEED = "PROCEED"
    RETRY = "RETRY"
    BACK = "BACK"
    ESCALATE = "ESCALATE"
    STOP = "STOP"


CriterionStatus = Literal["MET", "PARTIAL", "UNMET", "N/A", "UNVERIFIABLE"]


@dataclass(frozen=True, kw_only=True)
class CriterionFinding:
    n: int
    status: CriterionStatus
    id: str | None = None
    evidence: str = ""
    place: str = ""
    fix: str = ""
    defect_in: str | None = None
    no_change: bool = False


@dataclass(frozen=True, kw_only=True)
class Judgement:
    criteria: tuple[CriterionFinding, ...]
    coverage: Mapping[str, int] = field(default_factory=dict)
    gap: bool = False
    confidence: float = 0.0
    summary: str = ""


@dataclass(frozen=True, kw_only=True)
class CheckFinding:
    status: Literal["pass", "maybe", "fail", "n_a"]
    criterion: str | None = None
    place: str = ""
    fix: str = ""
    message: str = ""
    kind: Literal["substance", "output_contract"] | None = None  # LAD §2.2: what the failing finding verified


@dataclass(kw_only=True)
class CheckResult:
    result: Literal["PASS", "MAYBE", "FAIL"]
    evidence: str = ""
    environmental: bool = False
    untracked_only: bool = False
    findings: list[CheckFinding] = field(default_factory=list)
    facts: dict[str, str] = field(default_factory=dict)
    runs: list[dict[str, Any]] = field(default_factory=list)


# ---------------------------------------------------------------------------------------------
# §2.9 Runs, threads and exit codes


class ThreadState(StrEnum):
    NONE = "none"
    RUNNING = "running"
    PAUSED = "paused"
    UNFINISHED = "unfinished"
    STOPPED = "stopped"
    FINISHED = "finished"


_DECISION_RE = re.compile(
    r"^(?:(?P<word>proceed|retry|stop)|(?P<kw>back|rewind):(?P<unit>[A-Za-z0-9_.-]+)"
    r"|(?P<ev>event|answer):(?P<name>[A-Za-z0-9_-]+)=(?P<value>.*))$"
)


@dataclass(frozen=True, kw_only=True)
class Decision:
    word: Literal["proceed", "retry", "back", "rewind", "stop", "event", "answer"]
    unit: str | None = None
    name: str | None = None
    value: str | None = None

    @staticmethod
    def parse(text: str) -> Decision:
        m = _DECISION_RE.match(text.strip())
        if not m:
            raise ValueError(f"not a decision: {text!r}")
        if m.group("word"):
            return Decision(word=m.group("word"))  # type: ignore[arg-type]
        if m.group("kw"):
            return Decision(word=m.group("kw"), unit=m.group("unit"))  # type: ignore[arg-type]
        return Decision(word=m.group("ev"), name=m.group("name"), value=m.group("value"))  # type: ignore[arg-type]

    def __str__(self) -> str:
        if self.word in ("back", "rewind"):
            return f"{self.word}:{self.unit}"
        if self.word in ("event", "answer"):
            return f"{self.word}:{self.name}={self.value}"
        return self.word


def thread_id(workflow: str, task_id: str) -> str:
    return f"{workflow}/{task_id}"


# ---------------------------------------------------------------------------------------------
# §2.12 Run settings, options and feedback; §2.13 callers


CallerKind = Literal["person", "agent", "orchestrator", "scheduler", "pipeline", "engine", "unknown"]


@dataclass(frozen=True, kw_only=True)
class Caller:
    kind: CallerKind
    confidence: Literal["attested", "marked", "observed", "declared", "none"] = "none"
    decided_by: CallerKind | None = None
    relay: Literal["direct", "turn_named", "turn_only", "claimed", "none"] | None = None
    host: str | None = None
    host_session: str | None = None
    caller_app: str | None = None
    evidence: tuple[str, ...] = ()
    call_id: str = ""

    def to_json(self) -> dict[str, Any]:
        return {
            "kind": self.kind,
            "confidence": self.confidence,
            "decided_by": self.decided_by,
            "relay": self.relay,
            "host": self.host,
            "host_session": self.host_session,
            "caller_app": self.caller_app,
            "evidence": list(self.evidence),
            "call_id": self.call_id,
        }


@dataclass(frozen=True, kw_only=True)
class Feedback:
    text_ref: str
    chars: int
    ruling: bool = False
    applies_to: tuple[str, ...] = ()


@dataclass(kw_only=True)
class RunOptions:
    settings: dict[str, dict[str, Any]] = field(default_factory=dict)  # layer -> key -> {value, ref, via?}
    profiles: tuple[str, ...] = ()
    alias: str | None = None
    label: str | None = None
    origin: str = "cli"
    dry_run: bool = False
    caller: Caller | None = None
    rerun_of: dict[str, Any] | None = None


@dataclass(frozen=True, kw_only=True)
class SettingRow:
    key: str
    value: Any
    layer: str
    ref: str
    shadowed: tuple[Mapping[str, str], ...] = ()


@dataclass(frozen=True, kw_only=True)
class ResolvedSettings:
    """RST §2.7: rows for every key set above the engine layer; `values` holds every key the run reads."""

    rows: tuple[SettingRow, ...] = ()
    values: Mapping[str, Any] = field(default_factory=dict)
    digest: str = ""
    profiles: tuple[str, ...] = ()


# ---------------------------------------------------------------------------------------------
# §2.14 Workflow packages and outcomes


@dataclass(frozen=True, kw_only=True)
class PackageManifest:
    schema_version: int
    name: str
    entry: str
    workflow_api: int
    docs: str = "provisional"
    surfaces: Mapping[str, Any] = field(default_factory=dict)
    audit: Mapping[str, Any] = field(default_factory=dict)  # `{ignore: [...]}`, AUD §2.4


@dataclass(frozen=True, kw_only=True)
class RouteView:
    unit: str
    visit: int
    values: Mapping[str, str]
    facts: Mapping[str, Mapping[str, str]]
    artifact_keys: tuple[str, ...]
    settings: Mapping[str, Any]


@dataclass(frozen=True, kw_only=True)
class RawRequest:
    args: tuple[str, ...]
    inputs: Mapping[str, str]
    main_checkout: Path


@dataclass(frozen=True, kw_only=True)
class IntermediateOutcome:
    statement: str
    criteria: tuple[Criterion, ...]


@dataclass(frozen=True, kw_only=True)
class OutcomeSpec:
    schema_version: int
    revision: int
    statement: str
    deliverables: tuple[Mapping[str, str], ...]
    final: tuple[Criterion, ...]
    intermediate: Mapping[str, IntermediateOutcome]
    judge: Mapping[str, Any] | None = None
    check: CallableRef | None = None
    assumptions: tuple[str, ...] = ()
    revisions: tuple[Mapping[str, Any], ...] = ()


Trust = Literal["deterministic", "calibrated", "uncalibrated", "human", "unverified"]
OutcomeVerdict = Literal["met", "met_with_open", "unmet", "needs_person", "not_reached"]
