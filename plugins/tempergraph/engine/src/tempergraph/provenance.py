"""Caller provenance: who made a mutating call, and who decided it (PRV-B11 to PRV-B22; ADR `classify-callers-by-the-strongest-signal`, ADR `a-relayed-decision-counts-as-a-persons-only-with-host-turn-evidence`).

Accounting, not a security boundary: every signal can be forged by a process of the same user. A declaration
only lowers trust, and a refusal built on provenance fails toward the careful side. Read-only verbs never call
this module (OVR-B15).
"""

from __future__ import annotations

import json
import re
import uuid
from collections.abc import Callable, Mapping, Sequence
from datetime import datetime
from pathlib import Path
from typing import Any

CI_SYSTEMS = {"GITHUB_ACTIONS": "github-actions", "GITLAB_CI": "gitlab-ci", "BUILDKITE": "buildkite",
              "CIRCLECI": "circleci", "JENKINS_URL": "jenkins", "TF_BUILD": "azure-pipelines",
              "TEAMCITY_VERSION": "teamcity"}
DECLARABLE = ("person", "agent", "pipeline")
RESERVED = ("orchestrator", "scheduler", "engine")
APP = re.compile(r"^[a-z0-9-]{1,40}$")


class CallerRefused(ValueError):
    def __init__(self, code: str, message: str) -> None:
        super().__init__(message)
        self.code = code


def _set(env: Mapping[str, str], name: str) -> bool:
    return bool(env.get(name))


def _scheduler(env: Mapping[str, str], schedule: str | None,
               entry_for_fire: Callable[[str], Mapping[str, Any] | None] | None) -> dict[str, Any]:
    """TCK-B17: the fire token against the digest of the entry the fire id names, before anything is written."""
    import hashlib
    import hmac

    token = env.get("TEMPERGRAPH_SCHEDULE_TOKEN") or ""
    if schedule and not token:
        raise CallerRefused("schedule_reserved", "--schedule belongs to the scheduler's fires: it needs the fire token")
    entry = entry_for_fire(schedule) if (schedule and entry_for_fire is not None) else None
    wanted = str((entry or {}).get("token_digest") or "")
    if not (schedule and entry and wanted and hmac.compare_digest(hashlib.sha256(token.encode("utf-8")).hexdigest(), wanted)):
        raise CallerRefused("schedule_token_invalid", "no schedule entry on this machine matches the token")
    sid, _, when = str(schedule).partition("@")
    try:
        slot = datetime.strptime(when.removeprefix("manual-"),
                                 "%Y%m%dT%H%M%SZ" if when.startswith("manual-") else "%Y%m%dT%H%MZ")
    except ValueError:
        raise CallerRefused("schedule_token_invalid", "the fire id names no slot") from None
    made = (entry.get("created") or {}).get("caller") or {}
    trace = (env.get("TRACEPARENT") or "").split("-")
    return {"kind": "scheduler", "confidence": "attested", "decided_by": None, "relay": None, "host": "schedule",
            "host_session": None, "caller_app": None, "parent": None,
            "schedule": {"schedule_id": sid, "fire_id": schedule, "slot": slot.strftime("%Y-%m-%dT%H:%M:%SZ"),
                         "created_by": {"kind": made.get("kind"), "decided_by": made.get("decided_by")}},
            "trace_id": trace[1] if len(trace) >= 3 and len(trace[1]) == 32 else None,
            "evidence": [{"signal": "S7", "value": "token_attested"}], "call_id": uuid.uuid4().hex}


def classify(env: Mapping[str, str], tty: bool, *, declared: str | None = None, caller_app: str | None = None,
             schedule: str | None = None, parent: str | None = None,
             entry_for_fire: Callable[[str], Mapping[str, Any] | None] | None = None) -> dict[str, Any]:
    """PRV-B13: the first matching row decides; `evidence` keeps every signal seen."""
    if env.get("TEMPERGRAPH_SESSION_KEY"):
        raise CallerRefused("engine_session_caller", "a step never drives the engine (PRV-B5, PRV-B18, PRV-B17, PRV-B14, PRV-B13, PRV-B19, PRV-B15)")
    if env.get("TEMPERGRAPH_SUPERVISOR_TOKEN") or parent:
        # release 1 has no orchestrations, so no supervisor digest can match (ORC is release 3)
        raise CallerRefused("supervisor_token_invalid", "no orchestration on this machine issued that token")
    if env.get("TEMPERGRAPH_SCHEDULE_TOKEN") or schedule:
        return _scheduler(env, schedule, entry_for_fire)
    declared = declared or env.get("TEMPERGRAPH_CALLER") or None
    caller_app = caller_app or env.get("TEMPERGRAPH_CALLER_APP") or None
    if declared in RESERVED:
        raise CallerRefused("caller_reserved", f"--caller {declared} cannot be declared")
    if declared is not None and declared not in DECLARABLE:
        raise CallerRefused("caller_invalid", f"--caller must be one of {', '.join(DECLARABLE)}")
    if caller_app is not None and not APP.match(caller_app):
        raise CallerRefused("caller_app_invalid", "--caller-app must match [a-z0-9-]{1,40}")
    s2 = env.get("CLAUDE_CODE_CHILD_SESSION") == "1"
    s3 = env.get("CLAUDECODE") == "1" and not s2
    ci = next((sysname for var, sysname in CI_SYSTEMS.items() if _set(env, var)), None)
    s4 = ci is not None or env.get("CI") == "true"
    evidence = [{"signal": "S2", "value": "set" if s2 else "unset"},
                {"signal": "S3", "value": "set" if s3 else "unset"},
                {"signal": "S4", "value": "set" if s4 else "unset", **({"system": ci} if ci else {})},
                {"signal": "S5", "value": "set" if tty else "unset"},
                {"signal": "S6", "value": declared or "unset"}]
    host, session = "unknown", None
    if s2:
        if declared == "person":
            raise CallerRefused("caller_conflict", "a Claude Code tool call cannot declare itself a person; use "
                                                   "--relayed to carry a person's decision (PRV-B5)")
        kind, confidence, host = "agent", "marked", "claude-code"
        session = env.get("CLAUDE_CODE_SESSION_ID") or None
    elif s4 and not tty:
        kind, confidence, host = "pipeline", "marked", f"ci:{ci or 'unknown'}"
    elif declared in ("agent", "pipeline"):
        kind, confidence = declared, "declared"
        host = "messages-api-app" if declared == "agent" and caller_app else "unknown"
    elif tty:
        kind, confidence, host = "person", "observed", "terminal"
    elif declared == "person":
        kind, confidence = "unknown", "declared"
    else:
        kind, confidence = "unknown", "none"
    trace = (env.get("TRACEPARENT") or "").split("-")
    return {"kind": kind, "confidence": confidence, "decided_by": None, "relay": None, "host": host,
            "host_session": session, "caller_app": caller_app, "parent": None, "schedule": None,
            "trace_id": trace[1] if len(trace) >= 3 and len(trace[1]) == 32 else None, "evidence": evidence,
            "call_id": uuid.uuid4().hex}


def journal_path(home: Path, host: str, session: str) -> Path:
    return home / "supervision" / host / f"{session}.jsonl"


def person_turns(home: Path, host: str, session: str | None) -> list[dict[str, Any]] | None:
    """`person_turn` entries of the host session's supervision journal (SCO-B10, SCO-B11); None when unreadable."""
    if not session or not re.match(r"^[A-Za-z0-9_.-]{1,128}$", session):
        return None
    p = journal_path(home, host, session)
    if not p.exists():
        return []
    try:
        lines = p.read_text(encoding="utf-8").splitlines()
    except OSError:
        return None
    out = []
    for ln in lines:
        try:
            e = json.loads(ln)
        except ValueError:
            continue
        if isinstance(e, dict) and e.get("kind", e.get("entry")) == "person_turn":
            out.append(e)
    return out


def _after(at: Any, since: str | None) -> bool:
    if since is None:
        return True
    try:
        return datetime.fromisoformat(str(at)) > datetime.fromisoformat(since)
    except ValueError:
        return False


def decide(block: Mapping[str, Any], *, relayed: bool, words: Sequence[str] = (), since: str | None = None,
           home: Path | None = None) -> dict[str, Any]:
    """PRV-B14: the decider of a deciding call, from the caller and the host's person turns."""
    out = dict(block)
    kind = str(block.get("kind"))
    if kind == "person":
        out.update(decided_by="person", relay="direct")
    elif kind == "agent" and relayed:
        turns = person_turns(home, str(block.get("host")), block.get("host_session")) if home else None
        if turns is None:
            out.update(decided_by="agent", relay="claimed")
            out["evidence"] = [*block.get("evidence", []), {"signal": "journal", "value": "journal_unreadable"}]
        else:
            later = [t for t in turns if _after(t.get("at"), since)]
            named = [t for t in later if set(words) & set(t.get("names") or [])]
            if named:
                out.update(decided_by="person", relay="turn_named", person_turn_at=named[-1].get("at"))
            elif later:
                out.update(decided_by="person", relay="turn_only", person_turn_at=later[-1].get("at"))
            else:
                out.update(decided_by="agent", relay="claimed")
    elif kind == "unknown":
        out.update(decided_by="unknown", relay="claimed" if relayed else "none")
    else:
        out.update(decided_by=kind, relay="none")
    return out


def may_widen(block: Mapping[str, Any]) -> bool:
    """PRV-B21, PRV-B22: a widening needs a person, at a terminal or through a `turn_named` relay."""
    return block.get("decided_by") == "person" and block.get("relay") in ("direct", "turn_named")
