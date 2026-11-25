"""Filing findings to the repository that owns the fault (SIL-B2, B3, B6, B7, SIL-B19, SIL-B20, ISS-B7 to B10).

Publishing code: it reads findings (metadata) and the context the loop child built from the run log's ids, enums
and numbers (`issue_context`), and never imports or opens the evidence file. An issue's title and body are built
from cause codes, counts, ids, versions and the cause's fixed remedy text; no request text.
"""

from __future__ import annotations

import hashlib
import json
from collections.abc import Iterable, Mapping, Sequence
from dataclasses import dataclass, field
from datetime import UTC, datetime, timedelta
from pathlib import Path
from typing import Any

from tempergraph.improve import params
from tempergraph.improve.codehost import LOOP_LABEL, CodeHost, CodeHostError

ENGINE_REPOSITORY = "dbr0vskyi/tempergraph"  # engine and executor findings (SIL-B11)
DEFAULT_LABELS = [LOOP_LABEL, "needs-triage"]  # ISS-B1: the engine's own `issue_labels`


def marker(fp: str) -> str:
    return f"tempergraph:fp={fp}"


def _marker_line(fp: str) -> str:
    return f"<!-- {marker(fp)} -->"


def cause_key(f: Mapping[str, Any]) -> str:
    """ISS-B7: the finding's side, workflow and cause, without the unit: one issue holds a cause at every unit."""
    return hashlib.sha256(f"{f.get('side')}|{f.get('workflow')}|{f.get('cause')}".encode()).hexdigest()[:16]


def _cause_line(key: str) -> str:
    return f"<!-- tempergraph:cause={key} -->"


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
    records: Sequence[Mapping[str, Any]] = ()  # the run log's records, read for ISS-B8 to ISS-B10 through issue_context
    mode: str | None = None  # the workflow's improvement mode (ISS-B8)
    judge_executor: str | None = None  # the loop's judge executor (ISS-B8)


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
    escape = str(f.get("cause") or "").split(":", 1)[0] == "outcome_escape"  # SIL-B34: the pattern rule alone
    if c.lens == "outcome" and not c.calibrated and not escape:
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
    """ISS-B7: the cause, not the unit: the issue holds the cause at every unit, listed in its body."""
    return f"[loop] {f.get('workflow')}: {f.get('cause')}"[:200]


def _unit(f: Mapping[str, Any]) -> str:
    return f"{f['child']}/{f.get('unit') or '-'}" if f.get("child") else str(f.get("unit") or "-")


def _context(ds: Sequence[Decision]) -> dict[str, Any]:
    from tempergraph.improve import issue_context

    c = ds[0].candidate
    return issue_context.build(c.records, [d.candidate.finding for d in ds], mode=c.mode,
                               judge_executor=c.judge_executor)


def _fmt(v: Any) -> str:
    if isinstance(v, list):
        return ", ".join(f"`{x}`" for x in v)
    if isinstance(v, dict):
        return ", ".join(f"`{k}` {x}" for k, x in v.items())
    return f"`{v}`"


ENV_NAMES = (("engine_version", "Engine version (run)"), ("loop_engine_version", "Engine version (loop)"),
             ("workflow_version", "Workflow version"), ("parent_version", "Parent workflow version"), ("executors", "Executor"), ("executor_cli", "Executor CLI"),
             ("models", "Models"), ("aliases", "Model aliases"), ("efforts", "Effort"),
             ("judge_executor", "Loop judge executor"), ("improvement_mode", "Improvement mode"),
             ("python", "Python"), ("os", "OS"), ("arch", "Architecture"))
RUN_NAMES = (("thread", "Run"), ("started", "Segment started (UTC)"), ("exit_code", "Exit code"),
             ("exit_reason", "Exit reason"), ("run_cost_usd", "Run cost so far (USD)"),
             ("unit_cost_usd", "Cost of these units' sessions (USD)"), ("attempts", "Attempts per unit"),
             ("request_digest", "Request digest"), ("rerun_of", "Rerun of"), ("machine", "Machine id"))


def _env_rows(ctx: Mapping[str, Any], f: Mapping[str, Any]) -> list[str]:
    env = dict(ctx.get("environment") or {})
    if f.get("workflow_version"):  # the finding's own workflow: a sub-workflow child's version, not its parent's
        if f.get("child") and env.get("workflow_version") not in (None, f["workflow_version"]):
            env["parent_version"] = env["workflow_version"]
        env["workflow_version"] = f["workflow_version"]
    if f.get("executor_version"):
        env["executor_cli"] = sorted({*(env.get("executor_cli") or []), str(f["executor_version"])})
    return [f"- {name}: {_fmt(env[k])}" for k, name in ENV_NAMES if env.get(k) not in (None, "", [])]


def _run_rows(ctx: Mapping[str, Any]) -> list[str]:
    run = ctx.get("run") or {}
    return [f"- {name}: {_fmt(run[k])}" for k, name in RUN_NAMES if run.get(k) not in (None, "", {}, [])]


def _steps(ds: Sequence[Decision]) -> list[str]:
    """ISS-B8: what a person runs, on the machine that made the run, to see and repeat it."""
    f = ds[0].candidate.finding
    thread = str(f.get("thread") or "")
    wf = str(f.get("parent") or f.get("workflow") or "")
    unit = str(f.get("unit") or "")
    rows = ["On the machine that ran it (machine id above), in the repository the run worked in:", "",
            f"1. `tempergraph status {thread} --detail" + (f" --unit {unit}`" if unit else "`") + ": the run and the unit.",
            f"2. `tempergraph logs {thread} --kind run`: the run log the excerpt below comes from; "
            "`--kind raw --session <session_key>` shows one session's own output.",
            f"3. `tempergraph rerun {wf} {thread} --from {unit or 'start'} --check`, then without `--check`: the same "
            "request again from this unit."]
    rows += ["", "The request, outputs and session logs stay on that machine (under the run's folder in the "
             "repository's `.tempergraph` state root); this issue holds ids, enums, numbers and versions only."]
    return rows


def _log_rows(ctx: Mapping[str, Any]) -> list[str]:
    lines = list(ctx.get("log") or [])
    if not lines:
        return ["No run-log records of these units were found when the loop ran."]
    head = [f"{ctx['log_left_out']} earlier records left out."] if ctx.get("log_left_out") else []
    return [*head, "```text", *lines, "```"]


def _summary(ds: Sequence[Decision], regression_of: int | None) -> list[str]:
    d = ds[0]
    f = d.candidate.finding
    units = list(dict.fromkeys(_unit(x.candidate.finding) for x in ds))
    summary = [f"**Cause** `{f.get('cause')}` ({f.get('class')}, side `{f.get('side')}`), lens {d.candidate.lens}.",
               f"**Workflow** `{f.get('workflow')}`; " + ("unit " if len(units) == 1 else "units ")
               + ", ".join(f"`{u}`" for u in units) + "."]
    for x in ds:
        category = str(x.candidate.finding.get("review") or "").removeprefix("review:")
        if category and category in x.candidate.review_categories:  # SRV-B7: the category code only, never a note
            summary.append(f"A session review kept `review:{category}` on unit `{_unit(x.candidate.finding)}` "
                           "in this run.")
    if f.get("child") and f.get("parent"):  # SWF-B9
        summary.append(f"**Parent** `{f.get('parent')}` ran this workflow as its sub-workflow unit `{f.get('child')}`.")
    if regression_of is not None:
        summary.append(f"Possible regression of #{int(regression_of)}: that issue was closed as completed and this "
                       "cause came back. A person decides.")
    return summary


def _figures(ds: Sequence[Decision]) -> list[str]:
    rows = []
    for x in ds:
        f = x.candidate.finding
        row = f"- `{_unit(f)}`: count {f.get('count')}, fingerprint `{f.get('fingerprint')}`"
        if x.counts:
            row += "; pattern " + ", ".join(f"{k} {v}" for k, v in sorted(x.counts.items()))
        rows.append(row + ".")
    return rows


def body(d: Decision | Sequence[Decision], regression_of: int | None = None) -> str:
    """ISS-B2: the hidden lines, then Summary, Environment, Run, Steps to reproduce, Run log, Evidence, Fingerprint
    and Suggested remedy; ISS-B4: a closed issue the finding may be a regression of is named in the Summary; ISS-B7:
    one body for every unit of the cause in this filing."""
    ds = [d] if isinstance(d, Decision) else list(d)
    f = ds[0].candidate.finding
    ctx = _context(ds)
    fps = list(dict.fromkeys(str(x.candidate.finding.get("fingerprint")) for x in ds))
    hidden = [_marker_line(fps[0]), _cause_line(cause_key(f)), *(_marker_line(fp) for fp in fps[1:])]
    rows = [*hidden, "", "## Summary", *_summary(ds, regression_of), "", "## Environment", *_env_rows(ctx, f), "",
            "## Run", *(_run_rows(ctx) or ["- No run record was found when the loop ran."]), "",
            "## Steps to reproduce", *_steps(ds), "", "## Run log", *_log_rows(ctx), "", "## Evidence",
            *_figures(ds), "", "## Fingerprint", *(f"`{fp}`" for fp in fps), f"Cause key `{cause_key(f)}`.", "",
            "## Suggested remedy", f"{f.get('remedy')}", "",
            "An issue is evidence, not an order: a person decides (SIL-B8)."]
    return "\n".join(rows)


def comment_body(ds: Sequence[Decision]) -> str:
    """SIL-B2, ISS-B7: a "seen again" comment with the same context as a new issue (ISS-B8 to ISS-B10)."""
    f = ds[0].candidate.finding
    ctx = _context(ds)
    units = ", ".join(f"`{_unit(x.candidate.finding)}`" for x in ds)
    fps = list(dict.fromkeys(str(x.candidate.finding.get("fingerprint")) for x in ds))
    rows = [*(_marker_line(fp) for fp in fps), "",
            f"**Seen again**: `{f.get('cause')}` at {units}.", "", "## Environment", *_env_rows(ctx, f), "",
            "## Run", *(_run_rows(ctx) or ["- No run record was found when the loop ran."]), "",
            "## Steps to reproduce", *_steps(ds), "", "## Run log", *_log_rows(ctx), "", "## Evidence",
            *_figures(ds)]
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
    if p["op"] == "reopen":  # PRP-B29: a regression's reopen the host could not take
        host.reopen(p["repo"], int(p["number"]))
        return ""
    return host.create(p["repo"], p["title"], p["body"], list(p.get("labels") or []))


def _closed_at(issue: Mapping[str, Any]) -> datetime:
    try:
        at = datetime.fromisoformat(str(issue.get("closed_at") or "").replace("Z", "+00:00"))
    except ValueError:
        return datetime.min.replace(tzinfo=UTC)  # an unreadable time sorts oldest and never mutes
    return at if at.tzinfo else at.replace(tzinfo=UTC)


def _holds(issue: Mapping[str, Any], lines: Sequence[str]) -> bool:
    got = str(issue.get("body") or "").splitlines()
    return any(ln in got for ln in lines)


def _read(host: CodeHost, repo: str, state: str) -> tuple[list[dict[str, Any]] | None, bool]:
    """ISS-B9: the repository's loop issues in `state`, read with one retry; the flag says the read failed twice."""
    for attempt in (1, 2):
        try:
            return list(host.loop_issues(repo, state)), False
        except CodeHostError:
            if attempt == 2:
                return None, True
    return None, True


def _match_open(issues: Sequence[Mapping[str, Any]], fps: Sequence[str], key: str) -> Mapping[str, Any] | None:
    """SIL-B2, ISS-B7: the oldest open issue holding one of the fingerprints' lines, else one holding the cause
    key's line."""
    order = sorted(issues, key=lambda i: int(i.get("number") or 0))
    by_fp = [i for i in order if _holds(i, [_marker_line(fp) for fp in fps])]
    if by_fp:
        return by_fp[0]
    return next((i for i in order if _holds(i, [_cause_line(key)])), None)


def file(decisions: Sequence[Decision], host: CodeHost, outbox: Outbox, *, dry_run: bool = False,
         now: datetime | None = None) -> list[dict[str, Any]]:
    """SIL-B2, ISS-B7: the findings of one cause key go to one issue: a comment on the open issue that holds one of
    their fingerprints or the cause key, else (ISS-B3 to ISS-B6: not planned mutes, completed links a possible
    regression) one new issue for all of them; ISS-B9: issues are read from the label list, once per repository and
    state; a dry run makes no call (SIL-B6)."""
    results: list[dict[str, Any]] = []
    now = now or datetime.now(UTC)
    if not dry_run:
        for p in outbox.take():
            try:
                results.append({"op": "redelivered", "url": _deliver(host, p), "fingerprint": p.get("fingerprint")})
            except CodeHostError:
                outbox.add(p)
    groups: dict[tuple[str, str], list[Decision]] = {}
    for d in decisions:
        f = d.candidate.finding
        fp = str(f.get("fingerprint"))
        if d.action != "file" or d.repo is None:
            results.append({"op": "recorded", "reason": d.reason, "fingerprint": fp})
            continue
        if dry_run:
            results.append({"op": "would_file", "repo": d.repo, "title": title(f), "fingerprint": fp})
            continue
        groups.setdefault((d.repo, cause_key(f)), []).append(d)
    listed: dict[tuple[str, str], tuple[list[dict[str, Any]] | None, bool]] = {}
    for (repo, key), ds in groups.items():
        fps = list(dict.fromkeys(str(x.candidate.finding.get("fingerprint")) for x in ds))
        note = None
        if (repo, "open") not in listed:
            listed[(repo, "open")] = _read(host, repo, "open")
        opened, failed = listed[(repo, "open")]
        if failed:
            note = "search_failed"  # retried once, then files anyway and says why
        match = _match_open(opened or [], fps, key)
        regression: int | None = None
        if match is None and not failed:  # an open issue always wins; only then do closed ones count
            if (repo, "closed") not in listed:
                listed[(repo, "closed")] = _read(host, repo, "closed")
            closed, cfailed = listed[(repo, "closed")]
            mine = [i for i in closed or [] if _holds(i, [*(_marker_line(fp) for fp in fps), _cause_line(key)])]
            last = max(mine, key=_closed_at) if mine else None
            if cfailed:
                note = "closed_search_failed"  # files with no link and no mute (ISS-B6)
            elif last is not None:
                reason = str(last.get("state_reason") or "")
                days = float(params.value("mute.days"))
                if reason == "not_planned" and now - _closed_at(last) < timedelta(days=days):
                    results += [{"op": "muted", "url": last.get("url"), "fingerprint": fp} for fp in fps]  # ISS-B3
                    continue
                if reason == "completed" and last.get("number") is not None:
                    regression = int(last["number"])  # ISS-B4
        f = ds[0].candidate.finding
        if match is not None:
            p = {"op": "comment", "repo": repo, "number": int(match["number"]), "fingerprint": fps[0],
                 "body": comment_body(ds)}
        else:
            p = {"op": "create", "repo": repo, "title": title(f), "body": body(ds, regression),
                 "labels": _labels(f, ds[0].candidate.issue_labels), "fingerprint": fps[0]}
        try:
            url = _deliver(host, p)
        except CodeHostError:
            outbox.add(p)
            results += [{"op": "queued", "fingerprint": fp} for fp in fps]
            continue
        op = "commented" if p["op"] == "comment" else "filed"
        results.append({"op": op, "url": url, "fingerprint": fps[0], **({"note": note} if note else {})})
        results += [{"op": "grouped", "url": url, "fingerprint": fp, "with": fps[0]} for fp in fps[1:]]
    return results
