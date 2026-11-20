"""Supervision cost (SCO): the journal hosts write, attribution of a supervising session's spend to threads,
closing a thread's figures, and the `supervision hook|log|close|show` verbs.

The journal is `~/.tempergraph/supervision/<host>/<host_session>.jsonl`: numbers, names from fixed lists, ids and
times only (SCO §2.2, §2.7). It is written by the plugin's Claude Code hooks through `supervision hook <event>`
and by `supervision log`; read-only verbs never write it (contract C13, ADR-0087). A hook never changes, delays
past 2 s or refuses the host call it observed (C2), and writes nothing inside the engine's own sessions
(`TEMPERGRAPH_SESSION_KEY`, SCO-B6). Two figures per thread, never summed: marginal and turn (ADR-0088). Unmeasured
is never zero.
"""

from __future__ import annotations

import contextlib
import json
import math
import os
import re
import shlex
import time
import uuid
from collections import defaultdict
from collections.abc import Iterable, Mapping
from dataclasses import dataclass, field
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

from tempergraph.contracts import Usage
from tempergraph.run.log import estimate
from tempergraph.store.layout import home_path, now_iso

HOSTS = ("claude-code", "agent-sdk", "messages-api", "antigravity", "unknown")
ID = re.compile(r"^[A-Za-z0-9_.:@-]{1,128}$")
TARGET = re.compile(r"^(?:[A-Za-z0-9_][A-Za-z0-9_.-]*/[A-Za-z0-9_][A-Za-z0-9_.:~-]*|workflow:[A-Za-z0-9_.-]{1,64}|orchestration:[A-Za-z0-9_.-]{1,64})$")
MODEL = re.compile(r"^[A-Za-z0-9_.:@/\[\]-]{1,80}$")
SHIM = ("tempergraph", "tempergraph.exe", "tempergraph.cmd")
WAKE_IDLE_S = 300.0
CLOSE_AFTER_S = 24 * 3600.0
TOKENS = ("input_tokens", "output_tokens", "cache_read_tokens", "cache_write_tokens")
CATEGORY = {
    "run": "start", "run --check": "start", "rerun": "start", "batch": "start", "orchestrate start": "start",
    "status": "watch", "events": "watch", "facts": "watch", "wait": "watch", "attention": "watch",
    "orchestrate status": "watch", "orchestrate wait": "watch",
    "logs": "diagnose", "status --detail": "diagnose", "audit": "diagnose", "report": "diagnose",
    "executors": "diagnose", "supervision show": "diagnose",
    "resume": "decide", "orchestrate answer": "decide", "label": "decide",
    "stop": "steer", "rerun --check": "steer", "config": "steer", "orchestrate edit": "steer",
    "resume --settings": "steer",
}
VERBS = (*CATEGORY, "stats", "self-check", "list", "validate", "store", "other")
CATEGORIES = ("start", "watch", "diagnose", "decide", "steer", "relay", "rewake")
MUTATING = {"run", "rerun", "batch", "resume", "resume --settings", "label", "stop", "orchestrate start",
            "orchestrate answer", "orchestrate edit"}
SELECTOR_VERBS = {"status", "status --detail", "events", "facts", "wait", "logs", "stop", "label", "audit"}
FIELDS: dict[str, dict[str, str]] = {
    "session": {"at": "time", "host": "host", "host_session": "id", "host_version": "id?", "model": "model?",
                "caller_app": "id?"},
    "engine_call": {"at": "time", "tool_use_id": "id?", "agent_id": "id?", "verb": "verb", "targets": "targets",
                    "mutating": "bool", "background": "bool", "exit_code": "int?", "duration_s": "num?",
                    "output_bytes": "int?", "call_id": "id?"},
    "person_turn": {"at": "time", "prompt_id": "id?", "names": "words"},
    "usage": {"at": "time", "message_id": "id?", "agent_id": "id?", "model": "model?", "input_tokens": "int?",
              "output_tokens": "int?", "cache_read_tokens": "int?", "cache_write_tokens": "int?",
              "tool_use_ids": "ids", "skipped_lines": "int?"},
    "reported": {"at": "time", "reported_cost_usd": "num", "source": "source"},
    "end": {"at": "time", "reason": "word?"},
}


class EntryRefused(ValueError):
    pass


# -- journal ---------------------------------------------------------------------------------------------------


def journal_path(home: Path, host: str, session: str) -> Path:
    from tempergraph.provenance import journal_path as jp

    return jp(home, host, session)


def _time(v: Any) -> bool:
    try:
        datetime.fromisoformat(str(v).replace("Z", "+00:00"))
        return True
    except ValueError:
        return False


def _check(kind: str, value: Any, rule: str) -> bool:
    optional = rule.endswith("?")
    rule = rule.rstrip("?")
    if value is None:
        return optional or rule in ("ids", "words", "targets")
    if rule == "time":
        return isinstance(value, str) and _time(value)
    if rule == "id":
        return isinstance(value, str) and bool(ID.match(value))
    if rule == "host":
        return value in HOSTS
    if rule == "model":
        return isinstance(value, str) and bool(MODEL.match(value))
    if rule == "verb":
        return value in VERBS
    if rule == "targets":
        return isinstance(value, list) and len(value) <= 64 and all(isinstance(t, str) and TARGET.match(t) for t in value)
    if rule == "ids":
        return isinstance(value, list) and len(value) <= 256 and all(isinstance(t, str) and ID.match(t) for t in value)
    if rule == "words":
        return isinstance(value, list) and len(value) <= 32 and all(
            isinstance(t, str) and re.match(r"^[a-z0-9_:-]{1,40}$", t) for t in value)
    if rule == "bool":
        return isinstance(value, bool)
    if rule == "int":
        return isinstance(value, int) and not isinstance(value, bool) and 0 <= value < 10**12
    if rule == "num":
        return isinstance(value, int | float) and not isinstance(value, bool) and 0 <= value < 10**9
    if rule == "source":
        return value in ("statusline", "sdk_result")
    if rule == "word":
        return isinstance(value, str) and bool(re.match(r"^[a-z0-9_-]{1,40}$", value))
    return False


def validate(entry: Mapping[str, Any]) -> dict[str, Any]:
    """Fixed fields, numbers in range, no free text beyond ids (SCO §2.6, §4); raises EntryRefused."""
    kind = entry.get("entry")
    if kind not in FIELDS:
        raise EntryRefused(f"unknown entry {kind!r}")
    extra = set(entry) - set(FIELDS[str(kind)]) - {"entry"}
    if extra:
        raise EntryRefused(f"{kind}: fields outside the schema: {', '.join(sorted(extra))}")
    for name, rule in FIELDS[str(kind)].items():
        if not _check(str(kind), entry.get(name), rule):
            raise EntryRefused(f"{kind}.{name}: not a {rule.rstrip('?')}")
    return {"entry": kind, **{k: entry.get(k) for k in FIELDS[str(kind)] if k in entry}}


def disabled(env: Mapping[str, str] | None = None) -> bool:
    """SCO-B6 and `observe.supervision = off` (the user config's defaults, RST)."""
    env = os.environ if env is None else env
    if env.get("TEMPERGRAPH_SESSION_KEY"):
        return True
    try:
        doc = json.loads((home_path() / "config" / "settings.json").read_text(encoding="utf-8"))
        return (doc.get("defaults") or {}).get("observe.supervision") == "off"
    except (OSError, ValueError, AttributeError):
        return False


def append(home: Path, host: str, session: str, entries: Iterable[Mapping[str, Any]]) -> int:
    """Checks every entry first and appends all or nothing; owner-only, append-only."""
    from tempergraph.docs import append_jsonl

    if host not in HOSTS or not ID.match(session):
        raise EntryRefused("host or session is not an id")
    checked = [validate(e) for e in entries]
    path = journal_path(home, host, session)
    if checked and not path.exists() and checked[0]["entry"] != "session":
        checked.insert(0, {"entry": "session", "at": checked[0]["at"], "host": host, "host_session": session})
    for e in checked:
        append_jsonl(path, e)
    return len(checked)


def read(path: Path) -> list[dict[str, Any]]:
    out: list[dict[str, Any]] = []
    try:
        lines = path.read_text(encoding="utf-8").splitlines()
    except OSError:
        return out
    for ln in lines:
        with contextlib.suppress(ValueError):
            e = json.loads(ln)
            if isinstance(e, dict):
                out.append(e)
    return out


def last_record(log: Path, kind: str) -> dict[str, Any] | None:
    from tempergraph.run.events import records

    return next((r for r in reversed(records(log)) if r.get("kind") == kind), None)


def journals(home: Path) -> list[tuple[str, str, Path]]:
    base = home / "supervision"
    if not base.is_dir():
        return []
    return [(p.parent.name, p.stem, p) for p in sorted(base.glob("*/*.jsonl"))]


# -- the Claude Code hooks (SHL §2.2) --------------------------------------------------------------------------


def _verb(words: list[str]) -> str:
    if not words:
        return "other"
    head = words[0]
    if head == "orchestrate" and len(words) > 1:
        v = f"orchestrate {words[1]}"
        return v if v in VERBS else "other"
    if head == "supervision" and len(words) > 1 and words[1] == "show":
        return "supervision show"
    if head in ("run", "rerun") and "--check" in words:
        return f"{head} --check"
    if head == "status" and "--detail" in words:
        return "status --detail"
    if head == "resume" and not any(w.startswith(("--decision", "--feedback", "--answer")) for w in words) \
            and any(w.startswith(("--set", "--unset", "--profile", "--reload-settings")) for w in words):
        return "resume --settings"
    return head if head in VERBS else "other"


def _positionals(words: list[str]) -> list[str]:
    out, skip = [], False
    for w in words[1:]:
        if skip:
            skip = False
            continue
        if w.startswith("--"):
            skip = "=" not in w and w not in ("--json", "--check", "--detail", "--follow", "--relayed", "--now",
                                              "--all-roots", "--no-live", "--as-agent", "--background")
            continue
        out.append(w)
    return out


def targets(words: list[str], cwd: Path | None, printed: str = "") -> list[str]:
    """The threads a command is about, resolved as the verbs resolve a selector (an alias through the state
    root's aliases); a run's new thread id comes from what the engine printed (read, never stored)."""
    out: list[str] = []
    verb = _verb(words)
    pos = _positionals(words)
    root = _root(cwd)

    def sel(v: str) -> None:
        if "/" in v and TARGET.match(v):
            out.append(v)
        elif root is not None:
            from tempergraph.durability.alias import resolve

            tid = resolve(root, v, lambda _t: True)
            out.append(tid if tid and TARGET.match(tid) else f"workflow:{v}" if re.match(r"^[A-Za-z0-9_.-]{1,64}$", v) else "")
    if verb in SELECTOR_VERBS and pos:
        sel(pos[0])
    elif verb.startswith(("resume", "rerun")) and len(pos) >= 2:
        sel(f"{pos[0]}/{pos[1].split('/')[-1]}")
    elif verb.startswith("run") and pos:
        task = next((words[i + 1] for i, w in enumerate(words[:-1]) if w == "--task-id"), None)
        if task:
            sel(f"{pos[0]}/{task}")
    for m in re.finditer(r'"thread_id":\s*"([^"\\]{1,200})"', printed or ""):
        if TARGET.match(m.group(1)):
            out.append(m.group(1))
    return sorted({t for t in out if t})


def _root(cwd: Path | None) -> Path | None:
    if cwd is None:
        return None
    from tempergraph.store.layout import state_root_path

    try:
        root = state_root_path(cwd)
    except Exception:  # noqa: BLE001
        return None
    return root if root.is_dir() else None


def _engine_words(command: str) -> list[str] | None:
    """The engine's argv when the Bash command starts with the shim name; None for any other command."""
    try:
        words = shlex.split(command, posix=True)
    except ValueError:
        return None
    if not words:
        return None
    first = words[0].rsplit("/", 1)[-1]
    return words[1:] if first in SHIM else None


def _names(prompt: str, root: Path | None) -> list[str]:
    """PRV §2.4.1: the decision words of open pauses that occur as whole words in the prompt; no text kept."""
    if root is None or not prompt:
        return []
    words: set[str] = set()
    runs = root / "runs"
    for log in sorted(runs.glob("*/*/run.jsonl")) if runs.is_dir() else []:
        with contextlib.suppress(Exception):
            exit_ = json.loads((log.parent / "exit.json").read_text(encoding="utf-8"))
            if exit_.get("exit_code") != 3:
                continue
            p = last_record(log, "pause") or {}
            for d in p.get("decisions") or []:
                words.add(str(d).split(":")[0])
    found = {w for w in words if re.search(rf"(?<![\w-]){re.escape(w)}(?![\w-])", prompt.lower())}
    return sorted(w for w in found if re.match(r"^[a-z0-9_:-]{1,40}$", w))


def _transcript_usage(path: Path, offset: int) -> tuple[list[dict[str, Any]], int, int]:
    """Usage entries of assistant lines past `offset`: numbers and ids only; returns (entries, offset, skipped)."""
    out: list[dict[str, Any]] = []
    skipped = 0
    try:
        size = path.stat().st_size
        if size < offset:
            offset = 0
        with open(path, "rb") as fh:
            fh.seek(offset)
            data = fh.read(min(size - offset, 64 * 1024 * 1024))
    except OSError:
        return out, offset, 0
    cut = data.rfind(b"\n") + 1
    seen: set[str] = set()
    for raw in data[:cut].splitlines():
        try:
            line = json.loads(raw)
        except ValueError:
            skipped += 1
            continue
        msg = line.get("message") if isinstance(line, dict) else None
        if not isinstance(msg, dict) or line.get("type") != "assistant" or not isinstance(msg.get("usage"), dict):
            continue
        mid = str(msg.get("id") or "")
        u = msg["usage"]
        tools = [str(b.get("id")) for b in msg.get("content") or [] if isinstance(b, dict) and b.get("type") == "tool_use"
                 and ID.match(str(b.get("id") or ""))]
        if mid in seen:  # one message streamed as several lines: keep its last usage and every tool use
            prev = next(e for e in out if e["message_id"] == mid)
            prev["tool_use_ids"] = sorted(set(prev["tool_use_ids"]) | set(tools))
            for k, src in (("input_tokens", "input_tokens"), ("output_tokens", "output_tokens"),
                           ("cache_read_tokens", "cache_read_input_tokens"),
                           ("cache_write_tokens", "cache_creation_input_tokens")):
                if isinstance(u.get(src), int):
                    prev[k] = u[src]
            continue
        seen.add(mid)
        model = str(msg.get("model") or "")
        agent = line.get("agentId") if isinstance(line.get("agentId"), str) and ID.match(line["agentId"]) else None
        at = str(line.get("timestamp") or now_iso())
        out.append({"entry": "usage", "at": at if _time(at) else now_iso(),
                    "message_id": mid if ID.match(mid) else None, "agent_id": agent,
                    "model": model if MODEL.match(model) else None,
                    "input_tokens": u.get("input_tokens") if isinstance(u.get("input_tokens"), int) else None,
                    "output_tokens": u.get("output_tokens") if isinstance(u.get("output_tokens"), int) else None,
                    "cache_read_tokens": u.get("cache_read_input_tokens")
                    if isinstance(u.get("cache_read_input_tokens"), int) else None,
                    "cache_write_tokens": u.get("cache_creation_input_tokens")
                    if isinstance(u.get("cache_creation_input_tokens"), int) else None,
                    "tool_use_ids": tools})
    if out and skipped:
        out[0]["skipped_lines"] = skipped
    return out, offset + cut, skipped


def hook(event: str, payload: Mapping[str, Any], env: Mapping[str, str] | None = None,
         home: Path | None = None) -> int:
    """One Claude Code hook event; returns the entries written. Never raises (C2)."""
    try:
        return _hook(event, payload, env, home)
    except Exception:  # noqa: BLE001 - the host call is never changed by the journal
        return 0


def _hook(event: str, payload: Mapping[str, Any], env: Mapping[str, str] | None, home: Path | None) -> int:
    if disabled(env):
        return 0
    session = str(payload.get("session_id") or "")
    if not ID.match(session):
        return 0
    from tempergraph.store.layout import ensure_home

    home = home or ensure_home()
    cwd = Path(str(payload["cwd"])) if payload.get("cwd") else None
    at = now_iso()
    entries: list[dict[str, Any]] = []
    event = event.lower().replace("_", "-")
    if event in ("sessionstart", "session-start"):
        model = payload.get("model")
        model = model.get("id") if isinstance(model, dict) else model
        entries.append({"entry": "session", "at": at, "host": "claude-code", "host_session": session,
                        "model": model if isinstance(model, str) and MODEL.match(model) else None})
    elif event in ("userpromptsubmit", "user-prompt-submit"):
        pid = payload.get("prompt_id")
        entries.append({"entry": "person_turn", "at": at, "prompt_id": pid if isinstance(pid, str) and ID.match(pid)
                        else None, "names": _names(str(payload.get("prompt") or ""), _root(cwd))})
    elif event in ("posttooluse", "post-tool-use"):
        if payload.get("tool_name") != "Bash":
            return 0
        tin = payload.get("tool_input") or {}
        words = _engine_words(str(tin.get("command") or ""))
        if words is None:
            return 0
        res = payload.get("tool_response") or {}
        res = res if isinstance(res, dict) else {"stdout": str(res)}
        printed = str(res.get("stdout") or "")
        verb = _verb(words)
        code = res.get("exit_code", res.get("exitCode"))
        call = re.search(r'"call_id":\s*"([0-9a-f]{32})"', printed)
        tuid, agent = payload.get("tool_use_id"), payload.get("agent_id")
        entries.append({"entry": "engine_call", "at": at,
                        "tool_use_id": tuid if isinstance(tuid, str) and ID.match(tuid) else None,
                        "agent_id": agent if isinstance(agent, str) and ID.match(agent) else None,
                        "verb": verb, "targets": targets(words, cwd, printed), "mutating": verb in MUTATING,
                        "background": bool(tin.get("run_in_background")),
                        "exit_code": code if isinstance(code, int) and 0 <= code < 256 else None,
                        "duration_s": None,
                        "output_bytes": len(printed.encode()) + len(str(res.get("stderr") or "").encode()),
                        "call_id": call.group(1) if call else None})
    elif event in ("stop", "subagentstop", "subagent-stop"):
        tp = payload.get("agent_transcript_path") or payload.get("transcript_path")
        if not tp:
            return 0
        tpath = Path(str(tp))
        state = journal_path(home, "claude-code", session).with_suffix(".offsets.json")
        offsets: dict[str, int] = {}
        with contextlib.suppress(OSError, ValueError):
            offsets = dict(json.loads(state.read_text(encoding="utf-8")))
        found, offsets[str(tpath)], _ = _transcript_usage(tpath, int(offsets.get(str(tpath)) or 0))
        entries += found
        from tempergraph.docs import write_json

        write_json(state, offsets)
    elif event in ("sessionend", "session-end"):
        reason = str(payload.get("reason") or "other").lower().replace(" ", "_")
        entries.append({"entry": "end", "at": at, "reason": reason if re.match(r"^[a-z0-9_-]{1,40}$", reason) else "other"})
    else:
        return 0
    n = append(home, "claude-code", session, entries)
    if event in ("sessionend", "session-end"):
        with contextlib.suppress(Exception):
            close(home, session=session)
    return n


# -- attribution (SCO §2.4) ------------------------------------------------------------------------------------


def _ts(v: Any) -> float:
    try:
        return datetime.fromisoformat(str(v).replace("Z", "+00:00")).timestamp()
    except ValueError:
        return 0.0


@dataclass
class Figure:
    tokens: dict[str, int] = field(default_factory=lambda: dict.fromkeys(TOKENS, 0))
    usd: float = 0.0
    priced: bool = True

    def add(self, u: Mapping[str, Any], model: str | None, part: Mapping[str, int] | None = None) -> None:
        got = {k: int((part if part is not None else u).get(k) or 0) for k in TOKENS}
        for k, v in got.items():
            self.tokens[k] += v
        if not any(got.values()):
            return
        cost = estimate(Usage(input_tokens=got["input_tokens"], output_tokens=got["output_tokens"],
                              cache_read_tokens=got["cache_read_tokens"], cache_write_tokens=got["cache_write_tokens"]),
                        model)
        if cost is None:
            self.priced = False
        else:
            self.usd += cost

    def to_json(self) -> dict[str, Any]:
        return {"tokens": dict(self.tokens), "estimated_usd": round(self.usd, 6) if self.priced else None}


@dataclass
class ThreadCost:
    marginal: dict[str, Figure] = field(default_factory=lambda: defaultdict(Figure))
    turn: dict[str, Figure] = field(default_factory=lambda: defaultdict(Figure))
    calls: dict[str, int] = field(default_factory=lambda: defaultdict(int))
    sessions: set[tuple[str, str]] = field(default_factory=set)
    counted: set[tuple[tuple[str, str], str]] = field(default_factory=set)  # (session, message) once per thread
    estimated: bool = False
    unmeasured: bool = False
    last_call_at: float = 0.0

    def total(self, which: dict[str, Figure]) -> dict[str, Any]:
        f = Figure()
        for x in which.values():
            for k, v in x.tokens.items():
                f.tokens[k] += v
            f.usd += x.usd
            f.priced = f.priced and x.priced
        return f.to_json()


def attribute(sessions: Mapping[tuple[str, str], list[dict[str, Any]]], wake_idle_s: float = WAKE_IDLE_S
              ) -> tuple[dict[str, ThreadCost], dict[tuple[str, str], dict[str, Any]]]:
    """The one attribution function (SCO-AC-1): per thread its categories and figures, per session its `other`."""
    threads: dict[str, ThreadCost] = defaultdict(ThreadCost)
    per_session: dict[tuple[str, str], dict[str, Any]] = {}
    for key, entries in sessions.items():
        msgs = sorted((e for e in entries if e.get("entry") == "usage"), key=lambda e: _ts(e.get("at")))
        calls = sorted((e for e in entries if e.get("entry") == "engine_call"), key=lambda e: _ts(e.get("at")))
        turns = [e for e in entries if e.get("entry") == "person_turn"]
        model = next((e.get("model") for e in entries if e.get("entry") == "session" and e.get("model")), None)
        used: set[str] = set()
        reported = [e for e in entries if e.get("entry") == "reported"]
        skipped = any(e.get("skipped_lines") for e in msgs)

        def mkey(m: dict[str, Any]) -> str:
            return str(m.get("message_id") or f"@{m.get('at')}")

        for c in calls:
            cat = CATEGORY.get(str(c.get("verb")))
            tids = [t for t in c.get("targets") or [] if "/" in t and not t.startswith(("workflow:", "orchestration:"))]
            if cat is None or not tids:
                continue
            at = _ts(c.get("at"))
            issuer = next((m for m in msgs if c.get("tool_use_id") and c["tool_use_id"] in (m.get("tool_use_ids") or [])),
                          None)
            nxt = next((m for m in msgs if _ts(m.get("at")) >= at and m.get("agent_id") == c.get("agent_id")
                        and m is not issuer), None)
            share = 1.0 / len(tids)
            for tid in tids:
                tc = threads[tid]
                tc.sessions.add(key)
                tc.calls[cat] += 1
                tc.last_call_at = max(tc.last_call_at, at)
                if skipped:
                    tc.estimated = True
                if not msgs:
                    tc.unmeasured = True
                    continue
                out_part = 0
                if issuer is not None:
                    n_calls = max(1, len(issuer.get("tool_use_ids") or []))
                    out_part = int(math.floor((issuer.get("output_tokens") or 0) / n_calls * share))
                in_part = 0
                if nxt is not None:
                    in_part = min(int(math.ceil((c.get("output_bytes") or 0) / 4 * share)), int(nxt.get("input_tokens") or 0))
                    if not c.get("output_bytes"):
                        tc.estimated = True
                tc.marginal[cat].add({}, model, {"output_tokens": out_part, "input_tokens": in_part})
                for m in (issuer, nxt):
                    if m is not None and (key, mkey(m)) not in tc.counted:
                        tc.counted.add((key, mkey(m)))
                        tc.turn[cat].add(m, m.get("model") or model)
                        used.add(mkey(m))
                if c.get("agent_id"):  # SCO-B8: the helper's whole usage is on the thread's turn figure
                    for m in msgs:
                        if m.get("agent_id") == c["agent_id"] and (key, mkey(m)) not in tc.counted:
                            tc.counted.add((key, mkey(m)))
                            tc.turn[cat].add(m, m.get("model") or model)
                            used.add(mkey(m))
        # rewake: the first message after an idle gap that follows a background call's end (SCO §2.4)
        bg = [c for c in calls if c.get("background")]
        for prev, m in zip(msgs, msgs[1:], strict=False):
            gap = _ts(m.get("at")) - _ts(prev.get("at"))
            if gap < wake_idle_s:
                continue
            woke = [c for c in bg if _ts(prev.get("at")) <= _ts(c.get("at")) <= _ts(m.get("at"))] or \
                [c for c in bg if _ts(c.get("at")) <= _ts(m.get("at"))][-1:]
            for c in woke:
                for tid in [t for t in c.get("targets") or [] if "/" in t]:
                    tc = threads[tid]
                    tc.marginal["rewake"].add({}, m.get("model") or model, {"cache_write_tokens": int(m.get("cache_write_tokens") or 0)})
                    used.add(mkey(m))
        # relay: messages between a read of the thread and the decide call that answered, with a person turn between
        for c in calls:
            if CATEGORY.get(str(c.get("verb"))) != "decide":
                continue
            for tid in [t for t in c.get("targets") or [] if "/" in t]:
                before = [x for x in calls if x is not c and tid in (x.get("targets") or []) and _ts(x.get("at")) < _ts(c.get("at"))
                          and CATEGORY.get(str(x.get("verb"))) != "decide"]
                if not before:
                    continue
                start, end = _ts(before[-1].get("at")), _ts(c.get("at"))
                if not any(start < _ts(t.get("at")) < end for t in turns):
                    continue
                tc = threads[tid]
                for m in msgs:
                    if start < _ts(m.get("at")) < end and (key, mkey(m)) not in tc.counted:
                        tc.counted.add((key, mkey(m)))
                        tc.turn["relay"].add(m, m.get("model") or model)
                        tc.calls["relay"] += 1
                        used.add(mkey(m))
        other = Figure()
        for m in msgs:
            if mkey(m) not in used:
                other.add(m, m.get("model") or model)
        per_session[key] = {"host": key[0], "messages": len(msgs), "calls": len(calls), "person_turns": len(turns),
                            "other": other.to_json(),
                            "reported_cost_usd": reported[-1].get("reported_cost_usd") if reported else None,
                            "ended": any(e.get("entry") == "end" for e in entries),
                            "last_at": max((_ts(e.get("at")) for e in entries), default=0.0)}
    return threads, per_session


def _hash(text: str) -> str:
    import hashlib

    return hashlib.sha256(text.encode()).hexdigest()[:16]


def figures(tc: ThreadCost | None, sessions: Mapping[tuple[str, str], dict[str, Any]]) -> dict[str, Any]:
    """SCO §2.5's cost fields of one thread."""
    if tc is None or not tc.sessions:
        return {"marginal": None, "turn": None, "sessions": [], "completeness": "none_known", "calls": {},
                "observations": None}
    complete = "incomplete" if tc.unmeasured else "estimated" if tc.estimated else "complete"
    return {
        "marginal": {"by_category": {k: v.to_json() for k, v in sorted(tc.marginal.items())},
                     "total": tc.total(tc.marginal)} if not tc.unmeasured else None,
        "turn": {"by_category": {k: v.to_json() for k, v in sorted(tc.turn.items())},
                 "total": tc.total(tc.turn)} if not tc.unmeasured else None,
        "sessions": [{"host": h, "session_hash": _hash(f"{h}:{s}"),
                      "reported_cost_usd": (sessions.get((h, s)) or {}).get("reported_cost_usd")}
                     for h, s in sorted(tc.sessions)],
        "completeness": complete, "calls": dict(sorted(tc.calls.items())),
        "observations": tc.calls.get("watch", 0) + tc.calls.get("diagnose", 0),
    }


def load(home: Path, session: str | None = None) -> dict[tuple[str, str], list[dict[str, Any]]]:
    return {(h, s): read(p) for h, s, p in journals(home) if session is None or s == session}


# -- closing (SCO §2.5) ----------------------------------------------------------------------------------------


def _find_thread(home: Path, tid: str) -> Path | None:
    from tempergraph.observe.rows import read_index

    wf, _, task = tid.partition("/")
    for entry in read_index(home):
        root = Path(str(entry.get("path")))
        if (root / "runs" / wf / task / "run.jsonl").exists():
            return root
    return None


def _closed(root: Path) -> dict[str, dict[str, Any]]:
    out: dict[str, dict[str, Any]] = {}
    try:
        lines = (root / "ledger.jsonl").read_text(encoding="utf-8").splitlines()
    except OSError:
        return out
    for ln in lines:
        with contextlib.suppress(ValueError):
            r = json.loads(ln)
            if isinstance(r, dict) and r.get("kind") == "supervision" and r.get("thread_id"):
                out[str(r["thread_id"])] = r
    return out


def close(home: Path | None = None, *, session: str | None = None, now: float | None = None) -> dict[str, Any]:
    """Closes every thread whose supervising sessions have ended or been quiet 24 h after its last exit."""
    from tempergraph.docs import append_jsonl
    from tempergraph.durability.lock import is_held
    from tempergraph.store.layout import lock_path, run_dir

    home = home or home_path()
    now = time.time() if now is None else now
    sessions = load(home)
    threads, per = attribute(sessions)
    closed: list[str] = []
    for tid, tc in sorted(threads.items()):
        if session is not None and not any(s == session for _, s in tc.sessions):
            continue
        root = _find_thread(home, tid)
        if root is None:  # SCO §4: kept, attributed if the thread appears later
            continue
        wf, _, task = tid.partition("/")
        if is_held(lock_path(root, wf, task)):
            continue
        exit_ = last_record(run_dir(root, wf, task) / "run.jsonl", "run_exit")
        if exit_ is None:
            continue
        quiet = all((per.get(k) or {}).get("ended") or now - tc.last_call_at >= CLOSE_AFTER_S for k in tc.sessions)
        if not quiet:
            continue
        prev = _closed(root).get(tid)
        if prev and _ts(prev.get("last_call_at")) >= tc.last_call_at:
            continue
        line = {"kind": "supervision", "schema_version": 1, "id": uuid.uuid4().hex, "thread_id": tid,
                "workflow": wf, "closed_at": now_iso(),
                "last_call_at": datetime.fromtimestamp(tc.last_call_at, UTC).isoformat(),
                **({"replaces": prev.get("id")} if prev else {}), **figures(tc, per)}
        append_jsonl(root / "ledger.jsonl", line)
        _enqueue(home, root, line)
        closed.append(tid)
    return {"schema_version": 1, "closed": closed}


def _enqueue(home: Path, root: Path, line: dict[str, Any]) -> None:
    """The `supervision` row for each sink that takes it (CST §2.2): kept locally, referenced from the outbox."""
    from tempergraph.docs import append_jsonl
    from tempergraph.observe import sinks

    month = str(line["closed_at"])[:7]
    row = {k: line.get(k) for k in ("id", "thread_id", "workflow", "closed_at", "marginal", "turn", "completeness")}
    row["sessions"] = [{k: s.get(k) for k in ("host", "session_hash", "reported_cost_usd")} for s in line.get("sessions") or []]
    row["row_id"] = line["id"]
    row["kind"] = "supervision"
    row["schema_version"] = 1
    row["state_root"] = str(root)
    row["machine_id"] = sinks._machine(home).get("machine_id")
    append_jsonl(home / "supervision" / "rows" / f"{month}.jsonl", row)
    with contextlib.suppress(sinks.SinkConfigError):
        for s in sinks.load(home, root):
            if s.takes("supervision"):
                append_jsonl(sinks.outbox(home, s.name), {"row_id": row["row_id"], "kind": "supervision",
                                                          "month": month, "state_root": str(root)})


def closed_for(root: Path) -> dict[str, dict[str, Any]]:
    """The latest closed figures per thread, for `report --supervision` and the detail document."""
    return _closed(root)


# -- show (SCO §2.6) -------------------------------------------------------------------------------------------


def show(home: Path, *, thread: str | None = None, session: str | None = None) -> dict[str, Any]:
    sessions = load(home, session)
    threads, per = attribute(sessions)
    if thread is not None:
        tc = threads.get(thread)
        return {"schema_version": 1, "thread_id": thread, "open": bool(tc and not all(
            (per.get(k) or {}).get("ended") for k in tc.sessions)), **figures(tc, per)}
    listed = [{"host": k[0], "session": k[1], **v} for k, v in sorted(per.items())]
    by_thread = {tid: figures(tc, per) for tid, tc in sorted(threads.items())}
    out: dict[str, Any] = {"schema_version": 1, "session": session, "sessions": listed, "threads": by_thread}
    pairs: dict[str, set[str]] = defaultdict(set)
    for h, s in sessions:
        pairs[s].add(h)
    out["shared_session_ids"] = sorted(s for s, hs in pairs.items() if len(hs) > 1)  # SCO §4
    return out


def _fig(f: Mapping[str, Any] | None) -> str:
    if not f:
        return "not measured"
    t = f["total"]
    usd = "unpriced" if t.get("estimated_usd") is None else f"${t['estimated_usd']:.2f} est"
    return f"{sum(t['tokens'].values()):,} tokens · {usd}"


def text(doc: Mapping[str, Any]) -> str:
    def block(name: str, f: Mapping[str, Any]) -> list[str]:
        out = [f"{name}: {f['completeness']} · marginal {_fig(f.get('marginal'))} · turn {_fig(f.get('turn'))}"]
        cats = sorted(set((f.get("marginal") or {}).get("by_category") or {}) | set(f.get("calls") or {}))
        for c in cats:
            m = ((f.get("marginal") or {}).get("by_category") or {}).get(c)
            out.append(f"  {c}: {(f.get('calls') or {}).get(c, 0)} calls"
                       + (f" · marginal {sum(m['tokens'].values()):,} tokens" if m else ""))
        return out

    if "thread_id" in doc:
        lines = block(str(doc["thread_id"]) + (" (open)" if doc.get("open") else ""), doc)
    else:
        lines = [f"session {s['host']}/{s['session']}: {s['messages']} messages, {s['calls']} engine calls, "
                 f"{s['person_turns']} person turns · other "
                 f"{sum(s['other']['tokens'].values()):,} tokens" for s in doc.get("sessions") or []]
        for tid, f in (doc.get("threads") or {}).items():
            lines += block(tid, f)
        lines = lines or ["no supervision journal entries"]
    return "\n".join(lines) + "\n"
