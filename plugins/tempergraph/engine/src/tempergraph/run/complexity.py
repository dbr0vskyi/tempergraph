"""Complexity switches: measures, the rules file and zones (CXR §2.3 to §2.6). Model-free.

The switch's own step node evaluates once per run and keeps the result on its attempt record; the gate's pick
reads it there, so the gate stays a pure function of state.
"""

from __future__ import annotations

import concurrent.futures
import hashlib
import json
import re
from collections.abc import Mapping
from datetime import UTC, datetime, timedelta
from pathlib import Path
from typing import Any

from tempergraph.contracts import ComplexitySpec, MeasureContext, MeasureSpec, SwitchSpec, WorkflowSpec

STOCK_ARITY = {"fact": 2, "input": 1, "setting": 1, "count_items": 2, "count_lines": 3, "changed_paths": 0}
MEASURE_TIMEOUT_S = 1.0
EXPLORE_MAX_RATE, EXPLORE_MAX_PER_WEEK = 0.25, 5
NO_EXPLORE_ORIGINS = frozenset({"schedule", "trial"})
FAULT = "fault"


class MeasureFault(Exception):
    pass


def default_rules_path(switch: str) -> str:
    return f"routing/{switch}.json"


def override_path(state_root: Path, workflow: str, switch: str) -> Path:
    """A repository's whole-file override of a switch's rules (CXR §2.4)."""
    return state_root / "routing" / workflow / f"{switch}.json"


def check_rules(rules: Any, sw: SwitchSpec) -> list[str]:
    """Why a rules document cannot be used: the schema, an undeclared arm or measure, a bound of no kind."""
    comp = sw.complexity
    assert comp is not None
    names = {m.name for m in comp.measures}
    arms = list(sw.arms)
    out: list[str] = []
    if not isinstance(rules, Mapping) or rules.get("schema_version") != 1:
        return ["not a schema_version 1 object"]
    by_arm = rules.get("arms")
    if not isinstance(by_arm, Mapping) or not by_arm:
        return ["`arms` is missing"]
    for arm, body in by_arm.items():
        if arm not in arms:
            out.append(f"arm {arm!r} is not declared")
            continue
        if arm == arms[-1]:
            out.append(f"the safe arm {arm!r} takes no bounds")
        when = body.get("when") if isinstance(body, Mapping) else None
        if not isinstance(when, Mapping) or not when:
            out.append(f"arm {arm!r} needs `when`")
            continue
        for measure, bound in when.items():
            if measure not in names:
                out.append(f"measure {measure!r} is not declared")
            if not isinstance(bound, Mapping) or not set(bound) or set(bound) - {"max", "min", "in"}:
                out.append(f"bound of {arm}.{measure} takes max, min or in")
    margin = rules.get("margin") or {}
    if not isinstance(margin, Mapping):
        return out + ["`margin` is not an object"]
    for measure, band in margin.items():
        if measure not in names:
            out.append(f"margin measure {measure!r} is not declared")
        if not (isinstance(band, Mapping) and _num(band.get("from")) is not None and _num(band.get("to")) is not None):
            out.append(f"margin of {measure} needs numbers `from` and `to`")
    return out


def load_rules(spec: WorkflowSpec, switch: str, state_root: Path | None) -> dict[str, Any]:
    """The rules in force: the repository's override when present, else the package's. Returns
    `{rules, digest, source, error}`; `rules` is None on any error (zone `fault` at run time)."""
    sw = spec.units[switch].switch
    assert sw is not None and sw.complexity is not None
    path: Path | None = None
    source = "package"
    if state_root is not None and override_path(state_root, spec.name, switch).is_file():
        path, source = override_path(state_root, spec.name, switch), "repository"
    elif spec.package_root is not None:
        path = spec.package_root / (sw.complexity.rules or default_rules_path(switch))
    if path is None or not path.is_file():
        return {"rules": None, "digest": None, "source": source, "error": "the rules file is missing"}
    raw = path.read_bytes()
    digest = hashlib.sha256(raw).hexdigest()[:16]
    try:
        rules = json.loads(raw.decode("utf-8"))
    except ValueError:
        return {"rules": None, "digest": digest, "source": source, "error": "the rules file is not JSON"}
    problems = check_rules(rules, sw)
    if problems:
        return {"rules": None, "digest": digest, "source": source, "error": "; ".join(problems)}
    return {"rules": rules, "digest": digest, "source": source, "error": None}


def _num(v: Any) -> float | None:
    if isinstance(v, bool):
        return None
    if isinstance(v, (int, float)):
        return float(v)
    if isinstance(v, str):
        try:
            return float(v.strip())
        except ValueError:
            return None
    return None


def _shown(v: Any) -> Any:
    n = _num(v)
    if n is None:
        return str(v)[:60]
    return int(n) if n.is_integer() else n


def _stock(m: MeasureSpec, mctx: MeasureContext, spec: WorkflowSpec, state: Mapping[str, Any]) -> Any:
    kind, args = m.stock[0], m.stock[1:]
    if kind == "fact":
        v = (mctx.facts.get(args[0]) or {}).get(args[1])
        if v is None:
            raise MeasureFault(f"no fact {args[0]}.{args[1]}")
        return v
    if kind == "input":
        v = (mctx.request.get("inputs") or {}).get(args[0])
        if v is None:
            raise MeasureFault(f"no input {args[0]}")
        return v
    if kind == "setting":
        if args[0] not in mctx.settings:
            raise MeasureFault(f"no setting {args[0]}")
        return mctx.settings[args[0]]
    if kind == "changed_paths":
        return len(tuple(getattr(mctx.git, "changed_paths", ()) or ()))
    pointer = (mctx.artifacts.get(args[0]) or {}).get(args[1])
    if not pointer:
        raise MeasureFault(f"no artifact {args[0]}.{args[1]}")
    if kind == "count_lines":
        pattern = re.compile(args[2])
        return sum(1 for ln in mctx.read_text(str(pointer)).splitlines() if pattern.search(ln))
    if kind == "count_items":
        from tempergraph.run import mapping

        for name, u in spec.units.items():
            if u.map is not None and tuple(u.map.items_from) == (args[0], args[1]):
                try:
                    return len(mapping.read_items(spec, name, state, mctx.workdir))
                except mapping.MapFault as exc:
                    if exc.code == "map_empty":
                        return 0
                    raise MeasureFault(str(exc)) from None
        got = json.loads(mctx.read_text(str(pointer)))
        if not isinstance(got, list):
            raise MeasureFault("not a list")
        return len(got)
    raise MeasureFault(f"unknown stock measure {kind}")


def measure(m: MeasureSpec, mctx: MeasureContext, spec: WorkflowSpec, state: Mapping[str, Any]) -> Any:
    """One measure's value, or `FAULT` when it raises, runs over a second or returns another type (CXR §2.3)."""
    def run() -> Any:
        if m.call is not None:
            return m.call.resolve()(mctx)
        return _stock(m, mctx, spec, state)

    pool = concurrent.futures.ThreadPoolExecutor(max_workers=1)
    try:
        got = pool.submit(run).result(timeout=MEASURE_TIMEOUT_S)
    except Exception:  # noqa: BLE001 - any raise, and a timeout, is a fault
        return FAULT
    finally:
        pool.shutdown(wait=False)
    if isinstance(got, bool) or not isinstance(got, (int, float, str)):
        return FAULT
    return _shown(got)


def _holds(value: Any, bound: Mapping[str, Any]) -> bool:
    n = _num(value)
    if "in" in bound and str(value) not in [str(x) for x in bound["in"]] and value not in list(bound["in"]):
        return False
    if "max" in bound and (n is None or n > float(bound["max"])):
        return False
    return not ("min" in bound and (n is None or n < float(bound["min"])))


def _in_band(value: Any, band: Mapping[str, Any]) -> bool:
    n = _num(value)
    return n is not None and float(band["from"]) <= n <= float(band["to"])


def explores(comp: ComplexitySpec, thread: str, switch: str, stage: str, origin: str, explored_recent: int) -> bool:
    """CXR §2.6: a deterministic draw on the thread, a weekly limit, and never in a pipeline, a scheduled
    fire or a trial."""
    ex = comp.explore
    if not ex or stage == "pipeline" or origin in NO_EXPLORE_ORIGINS:
        return False
    rate = min(float(ex.get("rate") or 0), EXPLORE_MAX_RATE)
    per_week = min(int(ex.get("per_week") or 0), EXPLORE_MAX_PER_WEEK)
    draw = int(hashlib.sha256(f"{thread}\0{switch}".encode()).hexdigest(), 16) % 1000
    return draw < rate * 1000 and explored_recent < per_week


def explored_recent(state_root: Path, workflow: str, switch: str, now: datetime | None = None) -> int:
    """Explored runs of the workflow that started in the last 7 days, read from the run logs."""
    since = (now or datetime.now(UTC)) - timedelta(days=7)
    n = 0
    for log in (state_root / "runs" / workflow).glob("*/run.jsonl"):
        try:
            lines = log.read_text(encoding="utf-8").splitlines()
        except OSError:
            continue
        for ln in lines:
            if '"explore"' not in ln:
                continue
            try:
                r = json.loads(ln)
                at = datetime.fromisoformat(str(r.get("ts")).replace("Z", "+00:00"))
            except ValueError:
                continue
            if r.get("kind") == "route" and r.get("unit") == switch and r.get("zone") == "explore" and at >= since:
                n += 1
                break
    return n


def evaluate(spec: WorkflowSpec, switch: str, state: Mapping[str, Any], mctx: MeasureContext, *,
             state_root: Path | None, thread: str, origin: str = "cli", recent: int = 0) -> dict[str, Any]:
    """The zone and the arm it gives (CXR §2.4), with every measure's value, for the `route` record."""
    sw = spec.units[switch].switch
    assert sw is not None and sw.complexity is not None
    comp = sw.complexity
    arms = list(sw.arms)
    safe = arms[-1]
    loaded = load_rules(spec, switch, state_root)
    values = {m.name: measure(m, mctx, spec, state) for m in comp.measures}
    out: dict[str, Any] = {"measures": values, "rules_digest": loaded["digest"], "rules_source": loaded["source"]}
    rules = loaded["rules"]
    if rules is None or FAULT in values.values():
        if loaded["error"]:
            out["rules_error"] = loaded["error"]
        return {**out, "zone": "fault", "arm": safe}
    margin = rules.get("margin") or {}
    in_margin = {name for name, band in margin.items() if _in_band(values.get(name), band)}

    def eligible(lenient: bool) -> str | None:
        for arm in arms[:-1]:
            when = (rules["arms"].get(arm) or {}).get("when")
            if when and all((lenient and name in in_margin) or _holds(values.get(name), bound)
                            for name, bound in when.items()):
                return arm
        return None

    if in_margin:
        arm = eligible(lenient=True)
        if arm is not None and explores(comp, thread, switch, mctx.stage, origin, recent):
            return {**out, "zone": "explore", "arm": arm}
        return {**out, "zone": "margin", "arm": safe}
    arm = eligible(lenient=False)
    if arm is not None:
        return {**out, "zone": "simple", "arm": arm}
    return {**out, "zone": "complex", "arm": safe}
