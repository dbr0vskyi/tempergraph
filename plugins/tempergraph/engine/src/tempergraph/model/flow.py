"""Where each unit can go: the one answer the compiler, validation and the diagram share (CMP §2).

``successors`` lists, per routing token, the target nodes. Node names come from ``node_names``.
"""

from __future__ import annotations

from dataclasses import dataclass, field

from tempergraph.contracts import WorkflowSpec

FINALIZER = "finalizer"
END = "__end__"
OUTCOME_UNIT = "outcome"  # reserved (OUT §2.4, CMP §2.2)

TOKENS = ("PROCEED", "RETRY", "BACK", "ESCALATE", "STOP")


def node_names(unit: str) -> tuple[str, str, str, str]:
    return (f"{unit}.step", f"{unit}.judge", f"{unit}.gate", f"{unit}.human")


def step_node(unit: str) -> str:
    return node_names(unit)[0]


def effective_order(spec: WorkflowSpec) -> tuple[str, ...]:
    """The units in order, with the reserved outcome gate last when the workflow has an outcome."""
    order = tuple(spec.order)
    if spec.outcome is not None and spec.outcome.final and OUTCOME_UNIT not in order:
        order = order + (OUTCOME_UNIT,)
    return order


def target_node(target: str) -> str:
    return FINALIZER if target == FINALIZER else step_node(target)


@dataclass
class SuccessorSet:
    proceed: list[str] = field(default_factory=list)  # target nodes
    retry: list[str] = field(default_factory=list)
    back: list[str] = field(default_factory=list)
    escalate: list[str] = field(default_factory=list)
    stop: list[str] = field(default_factory=list)
    rewind: list[str] = field(default_factory=list)  # human node only (RRN §2.3)

    def by_token(self) -> dict[str, list[str]]:
        return {"PROCEED": self.proceed, "RETRY": self.retry, "BACK": self.back, "ESCALATE": self.escalate,
                "STOP": self.stop}


def next_unit(spec: WorkflowSpec, unit: str) -> str:
    order = effective_order(spec)
    flow = spec.flow.get(unit)
    if flow is not None and flow.next:
        return flow.next
    i = order.index(unit)
    return order[i + 1] if i + 1 < len(order) else FINALIZER


def proceed_targets(spec: WorkflowSpec, unit: str) -> list[str]:
    """Unit names (or `finalizer`) a pass may go to."""
    if unit == OUTCOME_UNIT and unit not in spec.units:
        return [FINALIZER]
    u = spec.units[unit]
    targets: list[str]
    if u.switch is not None:
        targets = list(dict.fromkeys(list(u.switch.arms.values())))
    elif u.route is not None:
        targets = list(dict.fromkeys(u.route_targets))
    else:
        targets = [next_unit(spec, unit)]
    return [_through_outcome(spec, t) for t in targets]


def _through_outcome(spec: WorkflowSpec, target: str) -> str:
    """Every path to the finalizer passes the outcome gate (OUT §2.4)."""
    if target == FINALIZER and OUTCOME_UNIT in effective_order(spec):
        return OUTCOME_UNIT
    return target


def back_targets(spec: WorkflowSpec, unit: str) -> list[str]:
    if unit == OUTCOME_UNIT and unit not in spec.units:
        return outcome_back_targets(spec)
    return list(spec.units[unit].gate.back_targets)


def outcome_back_targets(spec: WorkflowSpec) -> list[str]:
    """Derived from `serves` links: units whose intermediate criteria serve a final criterion (OUT §2.4)."""
    if spec.outcome is None:
        return []
    finals = {c.id for c in spec.outcome.final}
    out = []
    for name in spec.order:
        inter = spec.outcome.intermediate.get(name)
        if inter and any(set(c.serves) & finals for c in inter.criteria):
            out.append(name)
    return out


def successors(spec: WorkflowSpec, unit: str) -> SuccessorSet:
    order = effective_order(spec)
    step, _, _, human = node_names(unit)
    s = SuccessorSet()
    s.proceed = [target_node(t) for t in proceed_targets(spec, unit)]
    s.retry = [step]
    s.back = [step_node(t) for t in back_targets(spec, unit)]
    s.escalate = [human]
    s.stop = [END]
    s.rewind = [step_node(u) for u in order[: order.index(unit)]]
    return s


def human_targets(spec: WorkflowSpec, unit: str) -> list[str]:
    s = successors(spec, unit)
    return list(dict.fromkeys(s.proceed + s.retry + s.back + s.rewind + s.stop))


def gate_targets(spec: WorkflowSpec, unit: str) -> list[str]:
    s = successors(spec, unit)
    return list(dict.fromkeys(s.proceed + s.retry + s.back + s.escalate + s.stop))


def reachable_units(spec: WorkflowSpec) -> set[str]:
    order = effective_order(spec)
    if not order:
        return set()
    seen: set[str] = set()
    todo = [order[0]]
    while todo:
        u = todo.pop()
        if u in seen or u == FINALIZER or u not in order:
            continue
        seen.add(u)
        todo.extend(proceed_targets(spec, u) + back_targets(spec, u))
    return seen


def finalizer_reachable(spec: WorkflowSpec) -> bool:
    return any(FINALIZER in proceed_targets(spec, u) for u in reachable_units(spec))
