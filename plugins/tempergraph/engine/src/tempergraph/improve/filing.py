"""Filing findings to the repository that owns the fault (SIL-B2, B3, B6, B7, SIL-B19, SIL-B20; T12.2).

Publishing code: it reads findings (metadata) only and never imports or opens the evidence file. An issue's
title and body are built from cause codes, counts, ids and the cause's fixed remedy text; no request text.
"""

from __future__ import annotations

import json
from collections.abc import Iterable, Mapping, Sequence
from dataclasses import dataclass, field
from datetime import UTC, datetime, timedelta
from pathlib import Path
from typing import Any

from tempergraph.improve import params
from tempergraph.improve.codehost import CodeHost, CodeHostError

ENGINE_REPOSITORY = "dbr0vskyi/tempergraph"  # engine and executor findings (SIL-B11)
LOOP_LABEL = "tempergraph-loop"
DEFAULT_LABELS = [LOOP_LABEL, "needs-triage"]  # ISS-B1: the engine's own `issue_labels`


def marker(fp: str) -> str:
    return f"tempergraph:fp={fp}"


def _marker_line(fp: str) -> str:
    return f"<!-- {marker(fp)} -->"


@dataclass(kw_only=True)
class Candidate:
    """A finding the loop's judge has seen: its lens, confidence, attribution and calibration."""

    finding: Mapping[str, Any]
    lens: str = "friction"  # friction | outcome
    confidence: float | None = None
    attributed: bool = False  # the judge attributed the fault to this side
    calibrated: bool = False  # the outcome judge has a calibration score for this gate
    request_digest: str | None = None
    issue_labels: Sequence[str] | None = None  # the workflow's `improvement.issue_labels` (ISS-B1)
    review_categories: frozenset[str] = frozenset()  # the review catalog's category codes, so a body names only those


@dataclass(kw_only=True)
class Decision:
    action: str  # file | record
    reason: str
    candidate: Candidate
    repo: str | None = None
    counts: dict[str, int] = field(default_factory=dict)


def repository(finding: Mapping[str, Any], issue_repository: str) -> str | None:
    side = str(finding.get("side") or "")
    if side == "host":
        return None  # host findings are recorded only
    if side == "engine" or side.startswith("executor:"):
        return ENGINE_REPOSITORY
    if finding.get("child"):  # SWF-B9: a finding about a child's unit files to the child's own repository, never the parent's
        return str(finding.get("issue_repository") or "") or None
    return issue_repository or None


def decide(c: Candidate, history: Iterable[Mapping[str, Any]], issue_repository: str,
           now: datetime | None = None) -> Decision:
    """Whether a candidate files, or is only recorded, and why (SIL-B12 to SIL-B16, B3, B7)."""
    f = c.finding
    repo = repository(f, issue_repository)
    if f.get("class") != "fault":
        return Decision(action="record", reason=str(f.get("class")), candidate=c)
    if repo is None:
        return Decision(action="record", reason="host" if f.get("side") == "host" else "no_repository", candidate=c)
    if c.lens == "outcome" and not c.calibrated:
        return Decision(action="record", reason="uncalibrated", candidate=c)  # SIL-B7
    if c.lens == "friction" and (c.confidence is None
                                 or c.confidence < params.value("friction.file_confidence") or not c.attributed):
        return Decision(action="record", reason="not_judged" if c.confidence is None else "below_floor", candidate=c)
    if c.lens == "outcome" and f.get("side") == "workflow":  # SIL-B3; one clear engine fault is enough
        now = now or datetime.now(UTC)
        since = (now - timedelta(days=int(params.value("pattern_rule.window_days")))).isoformat()
        same = [h for h in history if h.get("fingerprint") == f.get("fingerprint") and str(h.get("at") or "") >= since]
        runs = {str(h.get("thread")) for h in same} | {str(f.get("thread"))}
        reqs = {str(h.get("request_digest")) for h in same if h.get("request_digest")}
        if c.request_digest:
            reqs.add(c.request_digest)
        counts = {"runs": len(runs), "requests": len(reqs),
                  "machines": len({str(h.get("machine")) for h in same} | {str(f.get("machine"))})}
        if len(runs) < params.value("pattern_rule.min_runs") or len(reqs) < params.value(
                "pattern_rule.min_distinct_requests"):
            return Decision(action="record", reason="pattern_not_met", candidate=c, repo=repo,
                            counts={**counts, "scope_local": 1})
        return Decision(action="file", reason="pattern_met", candidate=c, repo=repo, counts=counts)
    return Decision(action="file", reason="fault", candidate=c, repo=repo)


def title(f: Mapping[str, Any]) -> str:
    where = f" at {f['unit']}" if f.get("unit") else ""
    return f"[loop] {f.get('workflow')}: {f.get('cause')}{where}"[:200]


def body(d: Decision, regression_of: int | None = None) -> str:
    """ISS-B2: the hidden line, then Summary, Evidence, Fingerprint and Suggested remedy; ISS-B4: a closed issue
    the finding may be a regression of is named in the Summary."""
    f = d.candidate.finding
    fp = str(f.get("fingerprint"))
    summary = [f"**Cause** `{f.get('cause')}` ({f.get('class')}, side `{f.get('side')}`), lens {d.candidate.lens}.",
               f"**Workflow** `{f.get('workflow')}`; unit `{f.get('unit') or '-'}`."]
    category = str(f.get("review") or "").removeprefix("review:")
    if category and category in d.candidate.review_categories:  # SRV-B7: the category code only, never a note
        summary.append(f"A session review kept `review:{category}` on this unit in this run.")
    if f.get("child") and f.get("parent"):  # SWF-B9
        summary.append(f"**Parent** `{f.get('parent')}` ran this workflow as its sub-workflow unit `{f.get('child')}`.")
    if regression_of is not None:
        summary.append(f"Possible regression of #{int(regression_of)}: that issue was closed as completed and this "
                       "cause came back. A person decides.")
    figures = [f"Workflow version `{f.get('workflow_version')}`; count {f.get('count')}."
               + (f" Executor CLI `{f['executor_version']}`." if f.get("executor_version") else "")]
    if d.counts:
        figures.append("**Pattern** " + ", ".join(f"{k} {v}" for k, v in sorted(d.counts.items())) + ".")
    rows = [_marker_line(fp), "", "## Summary", *summary, "", "## Evidence", *figures, "", "## Fingerprint",
            f"`{fp}`", "", "## Suggested remedy", f"{f.get('remedy')}", "",
            "An issue is evidence, not an order: a person decides (SIL-B8)."]
    return "\n".join(rows)


def _names(value: Any) -> list[str] | None:
    """A declared label list, or none when it is not a non-empty list of names (ISS-B1)."""
    if isinstance(value, list | tuple) and value and all(isinstance(v, str) and v.strip() for v in value):
        return [v.strip() for v in value]
    return None


def _labels(f: Mapping[str, Any], declared: Any = None) -> list[str]:
    """ISS-B1: the list of `issue_labels` (the workflow's for its own workflow-side finding, the child's for a
    child's, else the default), `tempergraph-loop` when it omits it, and the side label."""
    side = str(f.get("side") or "")
    base: list[str] | None = None
    if side == "workflow":
        base = _names(f.get("issue_labels")) if f.get("child") else _names(declared)
    out: list[str] = []
    for name in [*(base or DEFAULT_LABELS), LOOP_LABEL, side if side.startswith("executor:") else f"side:{side}"]:
        if name not in out:
            out.append(name)
    return out


@dataclass(kw_only=True)
class Outbox:
    """Payloads a code host did not take, redelivered by the next filing (SIL-B19, SIL-B20)."""

    path: Path

    @classmethod
    def at(cls, root: Path) -> Outbox:
        return cls(path=root / "filing-outbox.jsonl")  # LOS-B7, LOS-B8, LOS-B9

    def add(self, payload: Mapping[str, Any]) -> None:
        self.path.parent.mkdir(parents=True, exist_ok=True, mode=0o700)
        with open(self.path, "a", encoding="utf-8") as fh:
            fh.write(json.dumps(dict(payload)) + "\n")

    def take(self) -> list[dict[str, Any]]:
        try:
            lines = self.path.read_text(encoding="utf-8").splitlines()
        except OSError:
            return []
        self.path.unlink(missing_ok=True)
        return [json.loads(ln) for ln in lines if ln.strip()]


def _deliver(host: CodeHost, p: Mapping[str, Any]) -> str:
    if p["op"] == "comment":
        return host.comment(p["repo"], int(p["number"]), p["body"])
    return host.create(p["repo"], p["title"], p["body"], list(p.get("labels") or []))


def _closed_at(issue: Mapping[str, Any]) -> datetime:
    try:
        at = datetime.fromisoformat(str(issue.get("closed_at") or "").replace("Z", "+00:00"))
    except ValueError:
        return datetime.min.replace(tzinfo=UTC)  # an unreadable time sorts oldest and never mutes
    return at if at.tzinfo else at.replace(tzinfo=UTC)


def _latest_close(host: CodeHost, repo: str, fp: str) -> tuple[Mapping[str, Any] | None, bool]:
    """ISS-B3 to ISS-B6: the closed issue of the fingerprint that closed most recently, read with one retry; the
    flag says the read failed twice."""
    for attempt in (1, 2):
        try:
            hits = host.closed(repo, marker(fp))
        except CodeHostError:
            if attempt == 2:
                return None, True
            continue
        mine = [h for h in hits if _marker_line(fp) in str(h.get("body") or "").splitlines()]
        return (max(mine, key=_closed_at) if mine else None), False
    return None, True


def file(decisions: Sequence[Decision], host: CodeHost, outbox: Outbox, *, dry_run: bool = False,
         now: datetime | None = None) -> list[dict[str, Any]]:
    """SIL-B2: comment on an open match of the fingerprint, else read the latest close (ISS-B3 to ISS-B6: not
    planned mutes, completed links a possible regression) and file; a dry run makes no call (SIL-B6)."""
    results: list[dict[str, Any]] = []
    now = now or datetime.now(UTC)
    if not dry_run:
        for p in outbox.take():
            try:
                results.append({"op": "redelivered", "url": _deliver(host, p), "fingerprint": p.get("fingerprint")})
            except CodeHostError:
                outbox.add(p)
    for d in decisions:
        f = d.candidate.finding
        fp = str(f.get("fingerprint"))
        if d.action != "file" or d.repo is None:
            results.append({"op": "recorded", "reason": d.reason, "fingerprint": fp})
            continue
        if dry_run:
            results.append({"op": "would_file", "repo": d.repo, "title": title(f), "fingerprint": fp})
            continue
        note = None
        match = None
        searched = False
        for attempt in (1, 2):
            try:
                hits = host.search(d.repo, marker(fp))
                match = next((h for h in hits if _marker_line(fp) in str(h.get("body") or "").splitlines()), None)
                searched = True
                break
            except CodeHostError:
                if attempt == 2:
                    note = "search_failed"  # retried once, then files anyway and says why
        regression: int | None = None
        if match is None and searched:  # an open issue always wins; only then do closed ones count
            last, failed = _latest_close(host, d.repo, fp)
            if failed:
                note = "closed_search_failed"  # files with no link and no mute (ISS-B6)
            elif last is not None:
                reason = str(last.get("state_reason") or "")
                days = float(params.value("mute.days"))
                if reason == "not_planned" and now - _closed_at(last) < timedelta(days=days):
                    results.append({"op": "muted", "url": last.get("url"), "fingerprint": fp})  # ISS-B3
                    continue
                if reason == "completed" and last.get("number") is not None:
                    regression = int(last["number"])  # ISS-B4
        if match is not None:
            p = {"op": "comment", "repo": d.repo, "number": int(match["number"]), "fingerprint": fp,
                 "body": f"Seen again: `{f.get('cause')}`, count {f.get('count')}."
                         + (" Pattern: " + ", ".join(f"{k} {v}" for k, v in sorted(d.counts.items())) + "."
                            if d.counts else "")}
        else:
            p = {"op": "create", "repo": d.repo, "title": title(f), "body": body(d, regression), "labels": _labels(f, d.candidate.issue_labels),
                 "fingerprint": fp}
        try:
            url = _deliver(host, p)
            results.append({"op": "commented" if p["op"] == "comment" else "filed", "url": url, "fingerprint": fp,
                            **({"note": note} if note else {})})
        except CodeHostError:
            outbox.add(p)
            results.append({"op": "queued", "fingerprint": fp})
    return results
