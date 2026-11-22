"""Stable mode's daily cap and the loop's own proposals and trials (SIL-B19, SIL-B20, PRP-B11, PRP-B8; plan T12.8).

The daily cap bounds what the loop child spends without a person: its friction judge, its session review, and,
at autonomy `propose` or `trial`, the proposer and a trial it starts on its own. A day is the UTC date. The spend
of a day is the `loop` ledger rows of the workflow, plus the proposals and trials recorded that day whose
`author` is `loop`. Only stable mode is capped; dev mode is a person watching their own runs.

At autonomy `propose` the child runs the proposer on the top-ranked cluster that this run's findings belong to
and opens a draft pull request without a trial; at `trial` it trials the drafted proposal under the lower of the
trial cap and the day's room, and opens a draft pull request only when the trial is `shown_better` (PRP-B8).
One autonomous proposal per workflow per day; a cluster with a live proposal is skipped. Nothing merges.
"""

from __future__ import annotations

import json
from collections.abc import Mapping
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

from tempergraph.improve import params

LIVE_STATES = frozenset({"drafted", "trialling", "shown_better", "opened"})


def _jsonl(path: Path) -> list[dict[str, Any]]:
    try:
        lines = path.read_text(encoding="utf-8").splitlines()
    except OSError:
        return []
    out = []
    for ln in lines:
        try:
            r = json.loads(ln)
        except ValueError:
            continue
        if isinstance(r, dict):
            out.append(r)
    return out


def _day(now: datetime | None) -> str:
    return (now or datetime.now(UTC)).date().isoformat()


def daily_cap(mode: str, setting: float | None) -> float | None:
    """The run setting `daily_cap_usd` (the workflow's `daily_cap_usd`, a settings file or `--daily-cap`), else
    `stable.daily_cap_usd` ($50); None in dev mode, which has no daily limit (SIL-B19, SIL-B20)."""
    if mode != "stable":
        return None
    return float(setting) if isinstance(setting, (int, float)) and setting >= 0 \
        else float(params.value("stable.daily_cap_usd"))


def _records(folder: Path) -> list[dict[str, Any]]:
    out = []
    for p in sorted(folder.glob("*.json")) if folder.is_dir() else ():
        try:
            doc = json.loads(p.read_text(encoding="utf-8"))
        except (OSError, ValueError):
            continue
        if isinstance(doc, dict):
            out.append(doc)
    return out


def _spend_of(doc: Mapping[str, Any]) -> float:
    s = doc.get("spend") or {}
    if isinstance(s.get("total"), (int, float)):
        return float(s["total"])
    return float(s.get("reported") or 0) + float(s.get("estimated") or 0)


def day_spend(root: Path, workflow: str, now: datetime | None = None) -> float:
    """What the loop spent on its own for one workflow today: loop rows, its own proposals and trials."""
    day = _day(now)
    total = 0.0
    for r in _jsonl(root / "ledger.jsonl"):
        if r.get("kind") == "loop" and r.get("workflow") == workflow and str(r.get("ts") or "")[:10] == day:
            c = r.get("cost") or {}
            total += float(c.get("reported") or 0) + float(c.get("estimated_only") or 0)
    for folder in (root / "improve" / "proposals", root / "improve" / "trials"):
        for doc in _records(folder):
            if doc.get("workflow") == workflow and doc.get("author") == "loop" and str(doc.get("at") or "")[:10] == day:
                total += _spend_of(doc)
    return round(total, 6)


def room(t: Mapping[str, Any], root: Path, now: datetime | None = None) -> float | None:
    """The day's remaining loop budget for the ticket's workflow; None when the mode is not capped (dev)."""
    if str(t.get("mode") or "dev") != "stable":
        return None
    got = t.get("daily_cap_usd")
    cap = float(got) if isinstance(got, (int, float)) else float(params.value("stable.daily_cap_usd"))
    return round(cap - day_spend(root, str(t["workflow"]), now), 6)


def _proposed_today(root: Path, workflow: str, now: datetime | None) -> bool:
    day = _day(now)
    return any(d.get("workflow") == workflow and d.get("author") == "loop" and str(d.get("at") or "")[:10] == day
               for d in _records(root / "improve" / "proposals"))


def pick(root: Path, workflow: str, fingerprints: set[str]) -> dict[str, Any] | None:
    """The top-ranked workflow-side cluster this run's findings belong to, with no live proposal."""
    from tempergraph.improve import proposals as prp

    live = {str((d.get("cluster") or {}).get("cluster_id")) for d in _records(prp.proposals_dir(root))
            if d.get("state") in LIVE_STATES}
    for c in prp.clusters(root, workflow):
        if c.get("side") != "workflow" or c["cluster_id"] in live:
            continue
        if fingerprints & set(c.get("findings") or ()):
            return c
    return None


def act(t: Mapping[str, Any], registry: Any, host: Any, log: Any, now: datetime | None = None) -> dict[str, Any]:
    """After filing: the loop's own proposal, and trial, at autonomy `propose` or `trial` in stable mode."""
    from tempergraph.docs import append_jsonl
    from tempergraph.store.layout import now_iso

    root = Path(str(t["state_root"]))
    wf = str(t["workflow"])
    level = str(t.get("autonomy") or "file")
    out: dict[str, Any] = {"level": level, "proposal": None, "trial": None, "pull_request": None}

    def note(kind: str, **kw: Any) -> None:
        append_jsonl(log, {"ts": now_iso(), "kind": kind, **kw})

    if level not in ("propose", "trial") or str(t.get("mode")) != "stable":
        return out
    if t.get("dry_run") or not t.get("package_root"):
        note("loop_skipped", step="propose", reason="dry_run" if t.get("dry_run") else "no_package")
        return out
    left = room(t, root, now)
    if left is not None and left < float(params.value("autonomy.min_room_usd")):
        note("loop_skipped", step="propose", reason="daily_cap")
        return out
    if _proposed_today(root, wf, now):
        note("loop_skipped", step="propose", reason="one_per_day")
        return out
    cl = pick(root, wf, {str(f) for f in t.get("fingerprints") or ()})
    if cl is None:
        note("loop_skipped", step="propose", reason="no_cluster")
        return out
    from tempergraph.improve import proposals as prp
    from tempergraph.improve import trials as trl
    from tempergraph.package.loader import load

    spec = load(Path(str(t["package_root"])))
    ex = registry.get(str(t.get("executor") or spec.default_executor))
    rec = prp.propose(root, spec, cl, ex, alias=str(t.get("alias") or "medium"),
                      effort=str(t.get("effort") or "max"))
    rec["author"] = "loop"
    prp.save(root, rec)
    out["proposal"] = rec.get("proposal_id")
    note("loop_proposed", proposal=rec.get("proposal_id"), cluster=cl["cluster_id"], state=rec.get("state"),
         refusal=rec.get("refusal"))
    if rec.get("state") != "drafted":
        return out
    if level == "propose":
        opened = prp.open_pr(root, spec, str(rec["proposal_id"]), host)
        out["pull_request"] = opened.get("pull_request")
        note("loop_opened", proposal=rec.get("proposal_id"), pull_request=opened.get("pull_request"),
             error=opened.get("open_error"))
        return out
    left = room(t, root, now)
    per, _monthly = trl.caps(spec, None)
    cap = min(per, left) if left is not None else per
    try:
        judge = ex if rec.get("side") == "grader" else None
        tr = trl.trial(root, spec, str(rec["proposal_id"]), trl.ChildRuns(repo=root.parent, registry=registry),
                       cap_usd=cap, judge_executor=judge)
    except trl.TrialRefused as exc:
        note("loop_skipped", step="trial", reason="refused", detail=str(exc)[:200])
        return out
    tr["author"] = "loop"
    trl.save(root, tr)
    out["trial"] = tr.get("trial_id")
    note("loop_trialled", trial=tr.get("trial_id"), decision=tr.get("decision"), reason=tr.get("reason"))
    if tr.get("decision") == "shown_better":  # PRP-B8: a draft pull request, never a merge
        opened = prp.open_pr(root, spec, str(rec["proposal_id"]), host)
        out["pull_request"] = opened.get("pull_request")
        note("loop_opened", proposal=rec.get("proposal_id"), pull_request=opened.get("pull_request"),
             error=opened.get("open_error"))
    return out
