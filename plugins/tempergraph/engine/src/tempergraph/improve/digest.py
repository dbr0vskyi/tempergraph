"""The session digest: a model-free pass over every session of a segment (SRV-B11, SRV-B12; ADR `session-logs-are-read-model-free-first-and-by-a-model-only-on-a-plan`).

One `sessions/<session_key>/digest.json` per session, names and numbers only: tool names, enums, counts, sizes,
durations and keyed digests of paths and targets. It is built from the activity journal, `meta.json` and the run
log, and reads `raw.jsonl` only for the turn boundaries and per-turn usage the journal lacks. `turns()` is the
shared turn model; the session review (`improve/review.py`) builds its condensed view from the same turns.
"""

from __future__ import annotations

import json
import re
import statistics
from collections.abc import Iterable, Mapping, Sequence
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

from tempergraph import identity
from tempergraph.docs import write_json
from tempergraph.improve import params
from tempergraph.store.layout import run_dir

SCHEMA = 1
KINDS = frozenset({"step", "retry", "judge", "judge_reask", "grouping", "member", "member_reask", "chair"})
STEP_KINDS = frozenset({"step", "retry"})
JUDGE_KINDS = frozenset({"judge", "judge_reask"})
WRITE_CAPS = frozenset({"edit", "write"})
FILE_CAPS = frozenset({"read", "search", "list", "edit", "write"})
OUTSIDE = "<outside workspace>"
SHELL_FOR_FILES = re.compile(r"^\s*(cat|head|tail|less|more|ls|find|grep|rg|sed\s+-n|awk)\b|^\s*echo\b.*>")
CD_BEFORE_GIT = re.compile(r"^\s*cd\s+\S+\s*(&&|;)\s*git\b")
ERROR_CLASSES: tuple[tuple[str, re.Pattern[str]], ...] = (
    ("not_found", re.compile(r"no such file|not found|does not exist|cannot find", re.I)),
    ("permission", re.compile(r"permission denied|not permitted|denied", re.I)),
    ("timeout", re.compile(r"timed? ?out|timeout", re.I)),
    ("syntax", re.compile(r"syntax ?error|parse error|invalid syntax", re.I)),
    ("test_failure", re.compile(r"\bfailed\b|assertion|traceback", re.I)),
    ("exit_nonzero", re.compile(r"exit (code|status) [1-9]|returned non-zero", re.I)),
)


@dataclass(kw_only=True)
class Call:
    call_id: str
    name: str
    capability: str | None
    summary: str | None
    ok: bool | None = None
    error_class: str | None = None
    output_chars: int = 0
    error_tail: str = ""
    subagent: bool = False
    t: float | None = None
    duration_s: float | None = None


@dataclass(kw_only=True)
class Turn:
    n: int
    text: str = ""
    calls: list[Call] = field(default_factory=list)
    context: int = 0
    output_tokens: int = 0
    subagent: bool = False
    t: float | None = None


def error_class(text: str) -> str:
    return next((name for name, rx in ERROR_CLASSES if rx.search(text or "")), "error")


def _jsonl(path: Path) -> list[dict[str, Any]]:
    try:
        lines = path.read_text(encoding="utf-8", errors="replace").splitlines()
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


def _text_of(content: Any) -> str:
    if isinstance(content, str):
        return content
    if isinstance(content, list):
        return "\n".join(str(b.get("text") or "") for b in content if isinstance(b, dict))
    return ""


def turns(session_dir: Path) -> tuple[list[Turn], str]:
    """The session's turns and its capture level: `full` from `raw.jsonl`, else rebuilt from the journal."""
    activity = _jsonl(session_dir / "activity.jsonl")
    started = {str(r.get("call_id")): r for r in activity if r.get("ev") == "tool_started"}
    finished = {str(r.get("call_id")): r for r in activity if r.get("ev") == "tool_finished"}
    raw = _jsonl(session_dir / "raw.jsonl")
    if raw:
        return _from_raw(raw, started, finished), "full"
    if activity:
        return _from_activity(activity, finished), "activity_only"
    return [], "pruned" if (session_dir / "meta.json").exists() else "not_captured"


def _from_raw(raw: Sequence[Mapping[str, Any]], started: Mapping[str, Mapping[str, Any]],
              finished: Mapping[str, Mapping[str, Any]]) -> list[Turn]:
    out: list[Turn] = []
    by_id: dict[str, Call] = {}
    for msg in raw:
        kind = msg.get("type")
        body = msg.get("message") or {}
        if kind == "assistant":
            usage = body.get("usage") or {}
            ctx = sum(int(usage.get(k) or 0) for k in ("input_tokens", "cache_read_input_tokens",
                                                        "cache_creation_input_tokens"))
            turn = Turn(n=len(out) + 1, context=ctx, output_tokens=int(usage.get("output_tokens") or 0),
                        subagent=msg.get("parent_tool_use_id") is not None)
            for block in body.get("content") or []:
                if not isinstance(block, dict):
                    continue
                if block.get("type") == "text":
                    turn.text += str(block.get("text") or "")
                elif block.get("type") == "tool_use":
                    cid = str(block.get("id") or "")
                    s = started.get(cid) or {}
                    call = Call(call_id=cid, name=str(block.get("name") or ""), capability=s.get("capability"),
                                summary=s.get("input_summary"), subagent=turn.subagent, t=s.get("t"),
                                duration_s=(finished.get(cid) or {}).get("duration_s"))
                    by_id[cid] = call
                    turn.calls.append(call)
                    if turn.t is None and call.t is not None:
                        turn.t = float(call.t)
            out.append(turn)
        elif kind == "user":
            content = body.get("content")
            for block in content if isinstance(content, list) else []:
                if isinstance(block, dict) and block.get("type") == "tool_result":
                    hit = by_id.get(str(block.get("tool_use_id") or ""))
                    if hit is None:
                        continue
                    call = hit
                    text = _text_of(block.get("content"))
                    call.ok = not block.get("is_error", False)
                    call.output_chars = len(text)
                    if not call.ok:
                        call.error_class = error_class(text)
                        call.error_tail = text[-400:]
    return out


def _from_activity(activity: Sequence[Mapping[str, Any]], finished: Mapping[str, Mapping[str, Any]]) -> list[Turn]:
    """Without `raw.jsonl`: a turn per text line and per run of tool calls between them (SRV-B9)."""
    out: list[Turn] = []
    cur: Turn | None = None
    for r in activity:
        ev = r.get("ev")
        if ev == "text":
            cur = Turn(n=len(out) + 1, text=str(r.get("last_line") or ""), t=r.get("t"))
            out.append(cur)
        elif ev == "tool_started":
            if cur is None or (cur.calls and cur.calls[-1].ok is not None):
                cur = Turn(n=len(out) + 1, t=r.get("t"))
                out.append(cur)
            cid = str(r.get("call_id") or "")
            f = finished.get(cid) or {}
            cur.calls.append(Call(call_id=cid, name=str(r.get("name") or ""), capability=r.get("capability"),
                                  summary=r.get("input_summary"), ok=f.get("ok"), t=r.get("t"),
                                  duration_s=f.get("duration_s"), subagent=bool(r.get("subagent")),
                                  error_class="error" if f.get("ok") is False else None))
    return out


def parse_key(key: str) -> tuple[str, int, str]:
    parts = str(key).split(".")
    idx = next((i for i, p in enumerate(parts) if p in KINDS), len(parts) - 1)
    attempt = int(parts[idx - 1]) if idx >= 1 and parts[idx - 1].isdigit() else 1
    return parts[0], attempt, parts[idx] if idx < len(parts) else "step"


def _item(key: str) -> str:
    """The map item of a session key `<unit>.<item>.<attempt>.<kind>`: the parts between the unit and the attempt."""
    parts = key.split(".")
    idx = next((i for i, p in enumerate(parts) if p in KINDS), len(parts) - 1)
    return ".".join(parts[1:idx - 1]) if idx >= 3 and parts[idx - 1].isdigit() else ""


def _target(c: Call) -> str | None:
    return identity.request_digest(f"{c.name}|{c.summary or ''}") if c.summary else None


def _repeats(calls: Sequence[tuple[int, Call]], k: int) -> list[dict[str, Any]]:
    out: list[dict[str, Any]] = []
    run: list[tuple[int, Call]] = []

    def close() -> None:
        if len(run) >= k:
            c = run[0][1]
            out.append({"tool": c.name, "target": _target(c), "error_class": c.error_class, "count": len(run),
                        "first_turn": run[0][0], "last_turn": run[-1][0]})

    for n, c in calls:
        key = (c.name, c.summary, c.error_class)
        if run and (run[-1][1].name, run[-1][1].summary, run[-1][1].error_class) == key:
            run.append((n, c))
        else:
            close()
            run = [(n, c)]
    close()
    return out


def _idle(tl: Sequence[Turn], minutes: float) -> list[dict[str, Any]]:
    """Spans of `minutes` or more between workspace writes (or the ends) with tokens spent in them."""
    out: list[dict[str, Any]] = []
    timed = [t for t in tl if t.t is not None]
    if len(timed) < 2:
        return out
    start = timed[0]
    spent = 0
    for t in timed[1:]:
        spent += t.output_tokens
        wrote = any(c.capability in WRITE_CAPS for c in t.calls)
        if wrote or t is timed[-1]:
            if float(t.t or 0) - float(start.t or 0) >= minutes * 60 and spent:
                out.append({"first_turn": start.n, "last_turn": t.n,
                            "minutes": round((float(t.t or 0) - float(start.t or 0)) / 60, 1), "tokens": spent})
            start, spent = t, 0
    return out


def _decl(unit: Mapping[str, Any] | None) -> tuple[set[str], set[str], set[str]]:
    tools = set((unit or {}).get("tools") or ())
    skills = {t.split(":", 2)[2] for t in tools if t.startswith("skill:") and t.count(":") >= 2}
    subagents = set((unit or {}).get("subagent_types") or ())
    return {t for t in tools if not t.startswith("skill:")}, skills, subagents


def build(session_dir: Path, run_rec: Mapping[str, Any], unit_decl: Mapping[str, Any] | None = None,
          prior: Mapping[str, Any] | None = None, changed: Sequence[str] = (), counted: bool = True) -> dict[str, Any]:
    """The digest of one session; `run_rec` is its `agent_run` record, `prior` the previous attempt's digest."""
    key = str(run_rec.get("session_key") or session_dir.name)
    unit, attempt, kind = parse_key(key)
    tl, capture = turns(session_dir)
    meta = {}
    try:
        meta = json.loads((session_dir / "meta.json").read_text(encoding="utf-8"))
    except (OSError, ValueError):
        meta = {}
    calls = [(t.n, c) for t in tl for c in t.calls]
    tools: dict[str, dict[str, Any]] = {}
    for _, c in calls:
        row = tools.setdefault(c.name, {"capability": c.capability, "calls": 0, "failures": 0, "refused": 0,
                                        "duration_s": 0.0})
        row["calls"] += 1
        row["failures"] += 1 if c.ok is False else 0
        row["duration_s"] = round(row["duration_s"] + float(c.duration_s or 0.0), 3)
    for r in _jsonl(session_dir / "activity.jsonl"):
        if r.get("ev") == "denied":
            name = str(r.get("name") or "")
            tools.setdefault(name, {"capability": None, "calls": 0, "failures": 0, "refused": 0,
                                    "duration_s": 0.0})["refused"] += 1
    declared, skills_decl, sub_decl = _decl(unit_decl)
    used_caps = {c.capability for _, c in calls if c.capability}
    skills_used = sorted({str(c.summary) for _, c in calls if c.capability == "skill" and c.summary})
    subagents: dict[str, dict[str, Any]] = {}
    total_tokens = sum(t.output_tokens for t in tl) or 0
    sub_tokens = sum(t.output_tokens for t in tl if t.subagent)
    for _, c in calls:
        if c.capability == "subagent":
            subagents.setdefault(str(c.summary or "subagent"), {"count": 0})["count"] += 1
    for v in subagents.values():
        v["token_share"] = round(sub_tokens / total_tokens, 3) if total_tokens else None
    first_write = next((t.n for t in tl if any(c.capability in WRITE_CAPS for c in t.calls)), None)
    before_write = next((t.context for t in tl if t.n == first_write), None) if first_write else None
    read_paths = [c.summary for _, c in calls if c.capability == "read" and c.summary]
    shell = [str(c.summary or "") for _, c in calls if c.capability == "shell"]
    wrote = {c.summary for _, c in calls if c.capability in WRITE_CAPS and c.summary}
    k = int(params.value("digest.repeat_min"))
    peak = max((t.context for t in tl), default=int((run_rec.get("usage") or {}).get("peak_context_tokens") or 0))
    doc: dict[str, Any] = {
        "schema_version": SCHEMA, "session_key": key, "kind": run_rec.get("session_kind") or kind, "unit": unit,
        "attempt": attempt, "executor": run_rec.get("executor"), "alias": run_rec.get("alias"),
        "model": meta.get("model") or run_rec.get("model"), "capture": capture,
        "turns": len(tl), "peak_context": peak, "turns_over_200k": sum(1 for t in tl if t.context > 200_000),
        "tokens_before_first_write": before_write,
        "files_reread": sum(n - 1 for n in _counts(read_paths).values() if n > 1),
        "tools": tools,
        "declared_unused": sorted((declared - used_caps - {"subagent"}) | (skills_decl - set(skills_used))
                                  | (sub_decl - set(subagents))),
        "undeclared_used": sorted(c for c in used_caps - declared - {"skill", "subagent", "mcp"}
                                  if declared and kind in STEP_KINDS),
        "skills": skills_used, "subagents": subagents,
        "repeats": _repeats(calls, k),
        "idle_spans": _idle(tl, float(params.value("digest.idle_minutes"))),
        "shell_for_files": sum(1 for s in shell if SHELL_FOR_FILES.search(s)),
        "cd_before_git": sum(1 for s in shell if CD_BEFORE_GIT.search(s)),
        "outside_workspace": sum(1 for _, c in calls if OUTSIDE in str(c.summary or "")),
        "end": _end(run_rec, tl),
    }
    if doc["kind"] in JUDGE_KINDS:
        opened = {p for p in read_paths if p}
        doc["reads"] = sorted(filter(None, (identity.request_digest(p) for p in opened)))
        if counted:  # SRV-B38: a null `changed_base` has no count to carry
            doc["changed_total"] = len(changed)
            doc["changed_read"] = sum(1 for p in changed if p in opened)
    doc["_commands"] = sorted({identity.request_digest(s) or "" for s in shell} - {""})
    doc["_wrote"] = sorted({identity.request_digest(str(w)) or "" for w in wrote} - {""})
    if prior is not None and doc["kind"] == "retry":
        a = set(prior.get("_commands") or ()) | set(prior.get("_wrote") or ())
        b = set(doc["_commands"]) | set(doc["_wrote"])
        doc["prior_overlap"] = round(len(a & b) / len(a), 3) if a else 0.0
    return doc


def _counts(xs: Iterable[str]) -> dict[str, int]:
    out: dict[str, int] = {}
    for x in xs:
        out[x] = out.get(x, 0) + 1
    return out


def _end(rec: Mapping[str, Any], tl: Sequence[Turn]) -> dict[str, Any]:
    if rec.get("timed_out"):
        timeout = float(rec.get("timeout_s") or 600)
        calls = [c for t in tl for c in t.calls]
        open_long = any(c.ok is None and float(c.duration_s or 0) > timeout / 2 for c in calls)
        share = float(rec.get("tool_wall_share") or 0)
        if open_long or (calls and calls[-1].ok is None and not rec.get("slow_host")):
            shape = "hung"
        elif rec.get("slow_host") or (share >= 0.6 and len(calls) >= 10):
            shape = "slow_host"
        elif calls and calls[-1].ok is not None:
            shape = "model_silent"
        else:
            shape = "mixed"
        return {"state": "timed_out", "timeout_shape": shape}
    if rec.get("stalled"):
        return {"state": "stalled"}
    return {"state": "ok" if rec.get("ok") else "partial"}


def public(doc: Mapping[str, Any]) -> dict[str, Any]:
    return {k: v for k, v in doc.items() if not k.startswith("_")}


def digest_path(root: Path, workflow: str, task_id: str, key: str) -> Path:
    return run_dir(root, workflow, task_id) / "sessions" / key / "digest.json"


def read(root: Path, workflow: str, task_id: str, key: str) -> dict[str, Any] | None:
    try:
        doc = json.loads(digest_path(root, workflow, task_id, key).read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return None
    return doc if isinstance(doc, dict) else None


def write_segment(root: Path, workflow: str, task_id: str, seg: Sequence[Mapping[str, Any]],
                  units: Mapping[str, Mapping[str, Any]]) -> list[dict[str, Any]]:
    """Digests of every session the segment ran; a failed write leaves that one out (SRV-B1, SRV-B20, SRV-B21, SRV-B22, SRV-B18)."""
    out: list[dict[str, Any]] = []
    last_by_unit: dict[str, dict[str, Any]] = {}
    timeouts: dict[str, Any] = {}
    for r in seg:
        if r.get("kind") == "attempt_start" and r.get("session_key"):
            timeouts[str(r["session_key"])] = r.get("timeout_s")
        if r.get("kind") != "agent_run" or not r.get("session_key"):
            continue
        key = str(r["session_key"])
        r = {**r, "timeout_s": timeouts.get(key)}
        changed = [str(p) for p in r.get("changed_paths") or ()]
        unit, _, kind = parse_key(key)
        sdir = run_dir(root, workflow, task_id) / "sessions" / key
        try:
            doc = build(sdir, r, units.get(unit), last_by_unit.get(unit) if kind == "retry" else None, changed,
                        counted=not ("changed_base" in r and r["changed_base"] is None))
            write_json(sdir / "digest.json", doc)
        except Exception:  # noqa: BLE001 - OVR-B4: findings are derived without this digest
            continue
        if kind in STEP_KINDS:
            last_by_unit[unit] = doc
        out.append(doc)
    return out


def _history(root: Path, workflow: str, version: str | None, unit: str) -> list[dict[str, Any]]:
    """Step digests of the unit over the version's runs on this machine (IMD-B1, local scope)."""
    found: list[dict[str, Any]] = []
    base = root / "runs" / workflow
    for task in sorted(base.iterdir()) if base.is_dir() else ():
        started = next((r for r in _jsonl(task / "run.jsonl") if r.get("kind") == "run_started"), None)
        if started is None or started.get("workflow_version") != version:
            continue
        for d in (task / "sessions").glob(f"{unit}.*/digest.json") if (task / "sessions").is_dir() else ():
            try:
                doc = json.loads(d.read_text(encoding="utf-8"))
            except (OSError, ValueError):
                continue
            if isinstance(doc, dict) and doc.get("kind") in STEP_KINDS:
                found.append(doc | {"_task": task.name})
    return found


def causes(digests: Sequence[Mapping[str, Any]], *, root: Path | None = None, workflow: str = "",
           version: str | None = None, units: Mapping[str, Mapping[str, Any]] | None = None,
           judged: Mapping[str, Mapping[str, Any]] | None = None) -> list[dict[str, Any]]:
    """SRV-B12 cause codes from digest fields only: `{unit, cause, count}`. `judged` carries, per unit, `passed`
    (the last judgement had no blockers) and `gave` (the attempts that got a real judgement, SRV-B12, SRV-B31)."""
    out: dict[tuple[str, str], int] = {}

    def add(unit: str, code: str) -> None:
        out[(unit, code)] = out.get((unit, code), 0) + 1

    for d in digests:
        unit, kind = str(d.get("unit")), str(d.get("kind"))
        step = kind in STEP_KINDS
        if step and any(rp.get("error_class") for rp in d.get("repeats") or ()):  # SRV-B2: failed calls only
            add(unit, "tool_repeat")
        if d.get("idle_spans"):
            add(unit, "idle_burn")
        declared, _, _ = _decl((units or {}).get(unit))
        if step and int(d.get("shell_for_files") or 0) >= 3 and declared & FILE_CAPS:
            add(unit, "shell_for_files")
        bloat = int(d.get("turns_over_200k") or 0) >= 1
        if not bloat and root is not None and step:
            peaks = [int(h.get("peak_context") or 0) for h in _history(root, workflow, version, unit)]
            if len(peaks) >= 10:
                bloat = int(d.get("peak_context") or 0) > statistics.quantiles(peaks, n=10)[-1]
        if step and bloat:
            add(unit, "context_bloat")
        subs = d.get("subagents") or {}
        if any(float(v.get("token_share") or 0) > 0.5 for v in subs.values()):
            add(unit, "subagent_heavy")
        end = d.get("end") or {}
        if end.get("state") == "timed_out":
            add(unit, f"timeout:{end.get('timeout_shape') or 'mixed'}")
        item = _item(str(d.get("session_key") or ""))
        held = judged or {}
        mine = held.get(f"{unit}.{item}") if item else None
        mine = mine if mine is not None else held.get(unit)
        if kind in JUDGE_KINDS and int(d.get("changed_total") or 0) > 0 and int(d.get("changed_read") or 0) == 0:
            j = mine or {}
            if j.get("passed"):
                add(unit, "judge_unread_pass")
        if kind in JUDGE_KINDS and int(d.get("changed_total") or 0) > 0:  # SRV-B31: read some, but under the share
            read, total = int(d.get("changed_read") or 0), int(d.get("changed_total") or 0)
            gave = (mine or {}).get("gave") or ()
            if 1 <= read < float(params.value("digest.judge_read_share")) * total and int(d.get("attempt") or 1) in gave:
                add(unit, "judge_partial_read")
        if kind == "retry" and float(d.get("prior_overlap") or 0) >= float(params.value("digest.retry_overlap")):
            add(unit, "retry_same_path")
    if root is not None:
        for unit in {str(d.get("unit")) for d in digests if d.get("kind") in STEP_KINDS}:
            hist = _history(root, workflow, version, unit)
            runs = {h["_task"] for h in hist}
            if len(runs) >= int(params.value("digest.unused_runs")):
                _, skills, subs = _decl((units or {}).get(unit))
                for name in sorted(skills | subs):
                    if all(name in (h.get("declared_unused") or ()) for h in hist):
                        add(unit, f"declared_unused:{name}")
    return [{"unit": u, "cause": c, "count": n} for (u, c), n in out.items()]
