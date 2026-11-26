"""Where each unit can go: the one answer the compiler, validation and the diagram share (CMP-B8).

``successors`` lists, per routing token, the target nodes. Node names come from ``node_names``.
"""

from __future__ import annotations

from dataclasses import dataclass, field

from tempergraph.contracts import WorkflowSpec

FINALIZER = "finalizer"
END = "__end__"
OUTCOME_UNIT = "outcome"  # reserved (OUT-B15, OUT-B16, OUT-B17, CMP-B10 to CMP-B16)

TOKENS = ("PROCEED", "RETRY", "BACK", "ESCALATE", "STOP")


def node_names(unit: str) -> tuple[str, str, str, str]:
    return (f"{unit}.step", f"{unit}.judge", f"{unit}.gate", f"{unit}.human")


def step_node(unit: str) -> str:
    return node_names(unit)[0]


ITEM_KINDS = ("step", "judge", "gate", "human")


def item_node(unit: str, kind: str) -> str:
    """The node every item of a concurrent map passes through for `kind` (MAP-B9): one static node per kind, an item
    reaching it by a `Send` that carries its id."""
    return f"{unit}.item_{kind}"


def effective_order(spec: WorkflowSpec) -> tuple[str, ...]:
    """The units in order, with the reserved outcome gate last when the workflow has an outcome."""
    order = tuple(spec.order)
    if spec.outcome is not None and spec.outcome.final and OUTCOME_UNIT not in order:
        order = order + (OUTCOME_UNIT,)
    return order


def target_node(target: str) -> str:
    return FINALIZER if target == FINALIZER else step_node(target)


def fork_node(join: str) -> str:
    return f"{join}.fork"


def done_node(branch: str) -> str:
    return f"{branch}.done"


def block_of(spec: WorkflowSpec, unit: str) -> str | None:
    """The parallel block (its join unit) that `unit` is a branch of, if any (CMP-B10 to CMP-B16)."""
    for name, u in spec.units.items():
        if u.kind == "parallel" and unit in u.branches:
            return name
    return None


WRITER_TOOLS = frozenset({"write", "edit"})  # `shell` alone makes no writer branch (WSP-B11)


def writer_branches(spec: WorkflowSpec, block: str) -> tuple[str, ...]:
    """The branches of the parallel block `block` that declare `write` or `edit`, in the order its parallel unit names
    them (WSP-B11); empty for a block of read-only branches or a unit that is no block."""
    u = spec.units.get(block)
    if u is None or u.kind != "parallel":
        return ()
    return tuple(b for b in u.branches
                 if (bu := spec.units.get(b)) is not None and bu.step is not None and WRITER_TOOLS & set(bu.step.tools))


def has_writer_branch(spec: WorkflowSpec) -> bool:
    return any(writer_branches(spec, name) for name in spec.units)


def concurrent_map(spec: WorkflowSpec, unit: str) -> bool:
    """`unit` is a map of `mode: concurrent` (MAP-B7, MAP-B9)."""
    u = spec.units.get(unit)
    return u is not None and u.kind == "map" and u.map is not None and u.map.mode == "concurrent"


def writer_map(spec: WorkflowSpec, unit: str) -> bool:
    """`unit` is a concurrent map whose step declares `write` or `edit`: each item works in its own worktree and the
    items are merged when all have passed (WSP-B11, MAP-B12)."""
    u = spec.units.get(unit)
    return concurrent_map(spec, unit) and u is not None and u.step is not None and bool(WRITER_TOOLS & set(u.step.tools))


def has_writer_map(spec: WorkflowSpec) -> bool:
    return any(writer_map(spec, name) for name in spec.units)


def is_contest(spec: WorkflowSpec, unit: str) -> bool:
    """`unit` is a contest: its slots are items that run the unit's step (CTS-B6)."""
    u = spec.units.get(unit)
    return u is not None and u.kind == "contest" and u.contest is not None


def writer_contest(spec: WorkflowSpec, unit: str) -> bool:
    """`unit` is a contest of `writes: true`: each slot works in its own worktree and only the winner is merged (CTS-B5,
    CTS-B7, WSP-B11)."""
    u = spec.units.get(unit)
    return is_contest(spec, unit) and u is not None and u.contest is not None and bool(u.contest.writes)


def has_writer_contest(spec: WorkflowSpec) -> bool:
    return any(writer_contest(spec, name) for name in spec.units)


def slot_names(spec: WorkflowSpec, unit: str) -> tuple[str, ...]:
    """The slot names of a contest, in declared order: `s1` to `sN` for a count (CTS-B6); empty for a unit that is none."""
    u = spec.units.get(unit)
    if u is None or u.contest is None:
        return ()
    slots = u.contest.slots
    if isinstance(slots, tuple | list):
        return tuple(s.name for s in slots)
    return tuple(f"s{n}" for n in range(1, slots + 1)) if isinstance(slots, int) and slots > 0 else ()


def in_map_item(spec: WorkflowSpec, unit: str) -> bool:
    """A contest that sits in a map item: the unit is a map whose item step is a contest (CTS-B10)."""
    u = spec.units.get(unit)
    return u is not None and u.contest is not None and (u.kind == "map" or u.map is not None)


def in_branch(spec: WorkflowSpec, unit: str) -> bool:
    """`unit` is a branch of a parallel block (CTS-B10 refuses a contest there)."""
    return block_of(spec, unit) is not None


def entry_node(spec: WorkflowSpec, target: str) -> str:
    """The node that enters `target`: a parallel block, named by its join or by a branch, is entered at its
    fork, which starts every branch."""
    if target == FINALIZER:
        return FINALIZER
    u = spec.units.get(target)
    if u is not None and u.kind == "parallel":
        return fork_node(target)
    block = block_of(spec, target)
    return fork_node(block) if block else step_node(target)


def entry_unit(node: str) -> str | None:
    """The unit a target node belongs to; None for the finalizer and the end."""
    return node.rsplit(".", 1)[0] if "." in node else None


@dataclass
class SuccessorSet:
    proceed: list[str] = field(default_factory=list)  # target nodes
    retry: list[str] = field(default_factory=list)
    back: list[str] = field(default_factory=list)
    escalate: list[str] = field(default_factory=list)
    stop: list[str] = field(default_factory=list)
    rewind: list[str] = field(default_factory=list)  # human node only (RRN-B16)

    def by_token(self) -> dict[str, list[str]]:
        return {"PROCEED": self.proceed, "RETRY": self.retry, "BACK": self.back, "ESCALATE": self.escalate,
                "STOP": self.stop}


def next_unit(spec: WorkflowSpec, unit: str) -> str:
    order = effective_order(spec)
    flow = spec.flow.get(unit)
    if flow is not None and flow.next:
        return flow.next
    block = block_of(spec, unit)
    if block is not None:
        return block  # a branch's pass goes to its block's join
    i = order.index(unit)
    return order[i + 1] if i + 1 < len(order) else FINALIZER


def proceed_targets(spec: WorkflowSpec, unit: str) -> list[str]:
    """Unit names (or `finalizer`) a pass may go to."""
    if unit == OUTCOME_UNIT and (unit not in spec.units or spec.units[unit].extra.get("outcome")):
        return [FINALIZER]
    u = spec.units[unit]
    targets: list[str]
    if u.switch is not None:
        targets = list(dict.fromkeys(list(u.switch.arms.values())))
    elif u.route is not None:
        targets = list(dict.fromkeys(u.route_targets))
    else:
        targets = [next_unit(spec, unit)]
    return [through_outcome(spec, t) for t in targets]


def through_outcome(spec: WorkflowSpec, target: str) -> str:
    """Every path to the finalizer passes the outcome gate (OUT-B15, OUT-B16, OUT-B17)."""
    if target == FINALIZER and OUTCOME_UNIT in effective_order(spec):
        return OUTCOME_UNIT
    return target


def back_targets(spec: WorkflowSpec, unit: str) -> list[str]:
    if unit == OUTCOME_UNIT and unit not in spec.units:
        return outcome_back_targets(spec)
    return list(spec.units[unit].gate.back_targets)


def outcome_back_targets(spec: WorkflowSpec) -> list[str]:
    """Derived from `serves` links: units whose intermediate criteria serve a final criterion (OUT-B15, OUT-B16, OUT-B17)."""
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
    if block_of(spec, unit) is not None:
        s.proceed = [done_node(unit)]  # the join fires when every branch's `done` has (CMP-B4)
    else:
        s.proceed = [entry_node(spec, t) for t in proceed_targets(spec, unit)]
    s.retry = [step]
    s.back = [entry_node(spec, t) for t in back_targets(spec, unit)]
    s.escalate = [human]
    s.stop = [END]
    own = block_of(spec, unit) or unit
    before = [u for u in order[: order.index(unit)] if block_of(spec, u) != block_of(spec, unit) or
              block_of(spec, u) is None]
    s.rewind = list(dict.fromkeys(entry_node(spec, u) for u in before if u != own))
    return s


def human_targets(spec: WorkflowSpec, unit: str) -> list[str]:
    s = successors(spec, unit)
    extra: list[str] = [node_names(unit)[1]]  # a usage-limit pause reruns the judge session the limit ended (DUR-B12)
    if deadline_of(spec, unit) is not None:  # an applied deadline re-enters the human node, or goes forward
        extra += [node_names(unit)[3]] + ([n] if (n := deadline_node(spec, unit)) else [])
    return list(dict.fromkeys(s.proceed + s.retry + s.back + s.rewind + s.stop + extra))


def rearm_targets(spec: WorkflowSpec, unit: str) -> list[str]:
    """Entry nodes a re-arm can send `unit`'s gate to: the entry of arm `to` of every entry listing it (SWM-B7)."""
    out: list[str] = []
    for u in spec.units.values():
        sw = u.switch
        for r in (sw.rearm if sw is not None else ()):
            entry = sw.arms.get(r.to) if sw is not None else None
            if unit in r.units and entry and entry != FINALIZER and entry in spec.units:
                out.append(entry_node(spec, entry))
    return list(dict.fromkeys(out))


def arm_units(spec: WorkflowSpec, entry: str) -> set[str]:
    """Units a pass can reach from an arm's entry, the entry included."""
    seen: set[str] = set()
    todo = [entry]
    while todo:
        u = todo.pop()
        if u in seen or u == FINALIZER or u not in spec.units:
            continue
        seen.add(u)
        todo.extend(proceed_targets(spec, u))
    return seen


def fallback_node(spec: WorkflowSpec, unit: str) -> str | None:
    """The node a gate's fallback target leads to (FLX-B9); the finalizer is reached through the outcome gate."""
    fb = spec.units[unit].gate.fallback if unit in spec.units else None
    return entry_node(spec, through_outcome(spec, fb)) if fb else None


def deadline_of(spec: WorkflowSpec, unit: str) -> tuple[int, str] | None:
    """`(deadline_s, on_deadline)` of a wait or an ask that declares a deadline (FLX-B8)."""
    u = spec.units.get(unit)
    d = (u.ask or u.wait) if u is not None else None
    return (int(d.deadline_s), str(d.on_deadline)) if d is not None and d.deadline_s else None


def deadline_node(spec: WorkflowSpec, unit: str) -> str | None:
    """The forward unit's node when `on_deadline` names one; `escalate`, `stop` and `defaults` are words."""
    d = deadline_of(spec, unit)
    if d is None or d[1] in ("escalate", "stop", "defaults"):
        return None
    return entry_node(spec, through_outcome(spec, d[1]))


def gate_targets(spec: WorkflowSpec, unit: str) -> list[str]:
    s = successors(spec, unit)
    fb = fallback_node(spec, unit)
    return list(dict.fromkeys(s.proceed + s.retry + s.back + s.escalate + s.stop + rearm_targets(spec, unit)
                              + ([fb] if fb else [])))


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
        for t in list(proceed_targets(spec, u)):  # entering a block reaches each of its branches
            tu = spec.units.get(t)
            todo.extend(tu.branches if tu is not None and tu.kind == "parallel" else
                        spec.units[b].branches if (b := block_of(spec, t)) else ())
        fb = spec.units[u].gate.fallback if u in spec.units else None
        dl = deadline_of(spec, u)
        todo.extend(proceed_targets(spec, u) + back_targets(spec, u) + ([fb] if fb else [])
                    + ([dl[1]] if dl and dl[1] not in ("escalate", "stop", "defaults") else []))
    return seen


def finalizer_reachable(spec: WorkflowSpec) -> bool:
    return any(FINALIZER in proceed_targets(spec, u) for u in reachable_units(spec))
