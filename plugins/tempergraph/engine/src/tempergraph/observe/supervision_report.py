"""`report --supervision` (SUP §2.4): touches, levels, waits and supervision cost per workflow, read-only.

Read from each thread's last `supervision` record (SUP §2.2, written before every `run_exit` for the thread so
far) and, for `--by unit`, from the ledger's intervention rows. A run is a thread. Runs whose origin or caller
app is `evals` are left out of every figure (SUP-AC-4). A figure over fewer than 5 runs is marked `thin`.
Supervision cost, its share and observations come from SCO's closed ledger lines (T7.6): until a thread's
supervision closes, it counts as not measured, never as zero (SUP-AC-5). `promote-check` will read :func:`aggregate` too (SUP-AC-3).
"""

from __future__ import annotations

import json
import math
import statistics
from collections import defaultdict
from collections.abc import Iterable
from dataclasses import dataclass, field
from datetime import datetime
from pathlib import Path
from typing import Any

from tempergraph.run.events import records

THIN = 5
LEVELS = ("observer", "approver", "consultant", "collaborator", "operator")
BY = ("workflow", "version", "unit", "host", "level")


@dataclass
class Run:
    thread_id: str
    workflow: str
    version: str | None
    record: dict[str, Any]
    ended_at: str | None
    hosts: list[str] = field(default_factory=list)


def _ts(text: Any) -> datetime | None:
    try:
        return datetime.fromisoformat(str(text).replace("Z", "+00:00"))
    except ValueError:
        return None


def runs(root: Path, since: datetime | None = None) -> list[Run]:
    """Each thread's last supervision record, eval runs left out."""
    from tempergraph.observe.supervision_cost import closed_for

    out: list[Run] = []
    base = root / "runs"
    closed = closed_for(root)
    for log in sorted(base.glob("*/*/run.jsonl")) if base.is_dir() else []:
        rec: dict[str, Any] | None = None
        version = None
        ended = None
        evals = False
        est: float | None = None
        for r in records(log):
            k = r.get("kind")
            if k == "agent_run":
                ec = (r.get("usage") or {}).get("estimated_cost_usd")
                est = (est or 0.0) + float(ec) if isinstance(ec, int | float) else est
            elif k == "run_started":
                version = r.get("workflow_version") or version
                caller = r.get("caller") or {}
                evals = evals or r.get("origin") == "evals" or caller.get("caller_app") == "evals"
            elif k == "supervision":
                rec = dict(r)
            elif k == "run_exit":
                ended = r.get("ts")
        if rec is None or evals:
            continue
        t = _ts(ended)
        if since is not None and (t is None or t < since):
            continue
        wf, task = log.parent.parent.name, log.parent.name
        _join(rec, closed.get(f"{wf}/{task}"), est)
        hosts = list((rec.get("supervisors") or {}).get("hosts") or [])
        out.append(Run(thread_id=f"{wf}/{task}", workflow=wf, version=version, record=rec, ended_at=ended,
                       hosts=hosts))
    return out


def _join(rec: dict[str, Any], line: dict[str, Any] | None, run_usd: float | None) -> None:
    """SCO's closed figures on the thread's record (SUP §2.2): cost, share and observations; absent stays null."""
    if line is None:
        return
    rec["supervision_cost"] = {k: line.get(k) for k in ("marginal", "turn", "completeness")}
    marginal = ((line.get("marginal") or {}).get("total") or {}).get("estimated_usd")
    if isinstance(marginal, int | float) and run_usd is not None and run_usd + marginal > 0:
        rec["supervision_share"] = round(marginal / (run_usd + marginal), 4)
    if line.get("observations") is not None:
        rec["observations"] = line["observations"]


def wilson(k: int, n: int, z: float = 1.96) -> list[float] | None:
    """The 95% Wilson score interval of k successes in n."""
    if n == 0:
        return None
    p = k / n
    d = 1 + z * z / n
    c = (p + z * z / (2 * n)) / d
    h = z * math.sqrt(p * (1 - p) / n + z * z / (4 * n * n)) / d
    return [round(max(0.0, c - h), 4), round(min(1.0, c + h), 4)]


def _pct(xs: list[float], q: float) -> float | None:
    if not xs:
        return None
    s = sorted(xs)
    return round(s[min(len(s) - 1, max(0, math.ceil(q * len(s)) - 1))], 4)


def _undesigned_by(rec: dict[str, Any]) -> dict[str, int]:
    t = rec.get("touches") or {}
    out: dict[str, int] = defaultdict(int)
    for cls in ("rescue", "steer"):
        for d, n in (t.get(cls) or {}).items():
            if isinstance(n, int) and n:
                out[d] += n
    return dict(out)


def _cost(rec: dict[str, Any]) -> float | None:
    c = rec.get("supervision_cost")
    if isinstance(c, int | float):
        return float(c)
    if isinstance(c, dict):
        m = c.get("marginal")
        v = ((m.get("total") or m).get("estimated_usd")) if isinstance(m, dict) else c.get("marginal_usd")
        return float(v) if isinstance(v, int | float) else None
    return None


def aggregate(rs: list[Run]) -> dict[str, Any]:
    """Every §2.4 figure over one group of runs."""
    n = len(rs)
    by_level: dict[str, int] = defaultdict(int)
    by_level_by: dict[str, int] = defaultdict(int)
    by_class = {"rescue": 0, "steer": 0}
    by_decider: dict[str, int] = defaultdict(int)
    rescues = own = 0
    relays: dict[str, int] = defaultdict(int)
    waits: list[float] = []
    costs: list[float] = []
    shares: list[float] = []
    obs: list[float] = []
    known = 0
    for r in rs:
        rec = r.record
        by_level[str(rec.get("level"))] += 1
        by_level_by[str(rec.get("level_by"))] += 1
        touches = rec.get("touches") or {}
        for cls in by_class:
            by_class[cls] += sum(v for v in (touches.get(cls) or {}).values() if isinstance(v, int))
        for d, c in _undesigned_by(rec).items():
            by_decider[d] += c
        rescues += sum(v for v in (touches.get("rescue") or {}).values() if isinstance(v, int))
        own += int(rec.get("agent_own_rescues") or 0)
        for k, v in (rec.get("relayed") or {}).items():
            relays[k] += int(v or 0)
        if isinstance(rec.get("person_wait_s"), int | float):
            waits.append(float(rec["person_wait_s"]))
        cost = _cost(rec)
        if cost is not None:
            costs.append(cost)
        if isinstance(rec.get("supervision_share"), int | float):
            shares.append(float(rec["supervision_share"]))
        if isinstance(rec.get("observations"), int | float):
            obs.append(float(rec["observations"]))
        known += 1 if not rec.get("callers_unknown") else 0
    unattended = by_level.get("observer", 0) + by_level.get("approver", 0)
    relayed_total = sum(relays.values())
    return {
        "runs": n, "thin": n < THIN,
        "by_level": {lv: {"runs": by_level[lv], "share": round(by_level[lv] / n, 4) if n else None}
                     for lv in LEVELS if by_level.get(lv)},
        "by_level_by": dict(sorted(by_level_by.items())),
        "unattended_rate": round(unattended / n, 4) if n else None, "unattended_interval": wilson(unattended, n),
        "undesigned_per_run": round((by_class["rescue"] + by_class["steer"]) / n, 4) if n else None,
        "undesigned_per_run_by_class": {k: round(v / n, 4) for k, v in by_class.items()} if n else {},
        "undesigned_per_run_by_decider": {k: round(v / n, 4) for k, v in sorted(by_decider.items())} if n else {},
        "agent_own_rescue_share": round(own / rescues, 4) if rescues else None,
        "relay_quality": {k: round(v / relayed_total, 4) for k, v in sorted(relays.items())} if relayed_total else None,
        "person_wait_s": {"p50": _pct(waits, 0.5), "p90": _pct(waits, 0.9)},
        "person_wait_by_pause_kind": None,  # the record keeps waits per decider, not per pause kind (release 1)
        "supervision_cost_per_run": {"p50": _pct(costs, 0.5), "p90": _pct(costs, 0.9),
                                     "measured": len(costs), "of": n},
        "supervision_share": {"median": round(statistics.median(shares), 4) if shares else None,
                              "p90": _pct(shares, 0.9), "measured": len(shares)},
        "observations_per_run": round(statistics.median(obs), 2) if obs else None,
        "data_quality": {"callers_known": round(known / n, 4) if n else None,
                         "cost_measured": round(len(costs) / n, 4) if n else None},
    }


def _units(root: Path, rs: list[Run]) -> dict[str, dict[str, Any]]:
    """Touches per (workflow, unit) from the ledger's intervention rows of the threads in the window."""
    wanted = {r.thread_id for r in rs}
    out: dict[str, dict[str, Any]] = {}
    try:
        lines = (root / "ledger.jsonl").read_text(encoding="utf-8").splitlines()
    except OSError:
        lines = []
    for ln in lines:
        try:
            row = json.loads(ln)
        except ValueError:
            continue
        if not isinstance(row, dict) or row.get("kind") != "intervention" or row.get("thread_id") not in wanted:
            continue
        key = f"{str(row['thread_id']).partition('/')[0]}.{row.get('unit') or '-'}"
        g = out.setdefault(key, {"touches": {}, "by_decider": {}, "threads": set()})
        by = str((row.get("caller") or {}).get("decided_by") or "unknown")
        g["threads"].add(row["thread_id"])
        for t in row.get("touches") or []:
            cls = str(t.get("class"))
            g["touches"][cls] = g["touches"].get(cls, 0) + 1
            g["by_decider"][by] = g["by_decider"].get(by, 0) + 1
    return {k: {"runs": len(v["threads"]), "thin": len(v["threads"]) < THIN, "touches": v["touches"],
                "by_decider": v["by_decider"]} for k, v in sorted(out.items())}


def _groups(rs: Iterable[Run], by: str) -> dict[str, list[Run]]:
    out: dict[str, list[Run]] = defaultdict(list)
    for r in rs:
        if by == "version":
            out[f"{r.workflow}@{r.version or '?'}"].append(r)
        elif by == "host":
            for h in r.hosts or ["none"]:
                out[h].append(r)
        elif by == "level":
            out[str(r.record.get("level"))].append(r)
        else:
            out[r.workflow].append(r)
    return dict(sorted(out.items()))


def report(root: Path, since: datetime | None = None, by: str = "workflow") -> dict[str, Any]:
    rs = runs(root, since)
    doc: dict[str, Any] = {"schema_version": 1, "since": since.isoformat() if since else None, "by": by,
                           "total": aggregate(rs)}
    if by == "unit":
        doc["groups"] = _units(root, rs)
    else:
        doc["groups"] = {k: aggregate(v) for k, v in _groups(rs, by).items()}
    return doc


def text(doc: dict[str, Any]) -> str:
    def line(name: str, a: dict[str, Any]) -> str:
        if "by_level" not in a:  # a unit group
            return f"  {name}: {a['runs']} runs{' (thin)' if a['thin'] else ''} · touches " + \
                ", ".join(f"{k} {v}" for k, v in sorted(a["touches"].items()))
        n = f"n = {a['runs']}{', thin' if a['thin'] else ''}"
        levels = ", ".join(f"{k} {v['runs']}" for k, v in a["by_level"].items()) or "none"
        un = a["unattended_rate"]
        iv = a["unattended_interval"]
        cost = a["supervision_cost_per_run"]
        measured = "not measured" if not cost["measured"] else \
            f"p50 ${cost['p50']:.2f} est · measured {cost['measured']} of {cost['of']}"
        return (f"  {name} ({n}): {levels} · unattended "
                f"{'—' if un is None else f'{un:.0%}'}{f' [{iv[0]:.0%}, {iv[1]:.0%}]' if iv else ''}"
                f" · undesigned/run {a['undesigned_per_run'] if a['undesigned_per_run'] is not None else '—'}"
                f" · supervision cost {measured}")
    out = [f"supervision since {doc['since'] or 'the start'}", line("all", doc["total"])]
    out += [line(k, v) for k, v in doc["groups"].items()]
    return "\n".join(out) + "\n"
