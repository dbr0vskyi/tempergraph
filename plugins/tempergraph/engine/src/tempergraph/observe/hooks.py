"""Lifecycle hooks (HOK-B1 to HOK-B6, EVT-B22, EVT-B23, EVT-B24): an operator's command run on a run event.

The registry is `<state root>/config/hooks.json`, written only by `hooks add` and `hooks remove`. When the
run log writes a record that maps to an event with a registered hook, the writer leaves a facts file (ids,
enums and numbers only, never run text) in the thread's `hooks/` folder and a hand-off ticket under the home,
then starts `python -m tempergraph.observe.hooks drain` through the detached child launcher (SEC-B7). The
child re-validates the ticket, takes the argv from the registry, never from the ticket, and runs it with the
facts file's path in its environment. A hook's failure is recorded and never changes the run (OVR-B4).
"""

from __future__ import annotations

import json
import os
import sys
import uuid
from collections.abc import Mapping, Sequence
from pathlib import Path
from typing import Any

from tempergraph.docs import append_jsonl, write_json
from tempergraph.store.layout import home_path, now_iso

RUN_EVENTS = ("started", "unit_entered", "gate_verdict", "paused", "resumed", "stop_requested", "finished",
              "failed", "schedule_paused")  # `schedule_paused`: failures paused a schedule (TCK-B24, SCH-B23)
LATER_EVENTS = ("stalled", "orchestration_attention", "orchestration_finished", "schedule_fired",
                "schedule_missed", "schedule_refused")
FILE = "hooks.json"
MAX_HOOKS, MAX_WORDS, MAX_WORD = 20, 32, 500
TIMEOUT_S = 60.0
# the record fields a facts file may carry, all ids, enums or numbers (SEC-B5, SEC-B6)
FACT_FIELDS = ("seq", "ts", "segment", "unit", "item", "attempt", "token", "verdict", "route_target", "pause_kind",
               "exit_code", "reason", "degraded", "mode", "origin", "visit")
_SLUG_CHARS = frozenset("abcdefghijklmnopqrstuvwxyzABCDEFGHIJKLMNOPQRSTUVWXYZ0123456789._-")


class HookRefused(ValueError):
    """`hooks add` or `hooks remove` cannot do what was asked; nothing is written."""


def config_path(root: Path) -> Path:
    return root / "config" / FILE


def tickets_dir(home: Path) -> Path:
    return home / "hooks" / "tickets"


def load(root: Path) -> list[dict[str, Any]]:
    """The registered hooks; a missing or unreadable file is no hooks."""
    try:
        doc = json.loads(config_path(root).read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return []
    out = []
    for h in (doc.get("hooks") if isinstance(doc, dict) else None) or []:
        if isinstance(h, dict) and h.get("event") in RUN_EVENTS and not argv_problem(h.get("argv")) \
                and isinstance(h.get("id"), str):
            out.append({"id": h["id"], "event": h["event"], "argv": [str(w) for w in h["argv"]]})
    return out


def argv_problem(argv: Any) -> str | None:
    if not isinstance(argv, list | tuple) or not argv:
        return "a hook needs a command after `--`"
    if len(argv) > MAX_WORDS:
        return f"a hook command takes at most {MAX_WORDS} words"
    for w in argv:
        if not isinstance(w, str) or not w or len(w) > MAX_WORD or "\x00" in w or "\n" in w:
            return f"a hook word is 1 to {MAX_WORD} characters on one line"
    return None


def _store(root: Path, hooks: Sequence[Mapping[str, Any]]) -> None:
    path = config_path(root)
    path.parent.mkdir(parents=True, exist_ok=True, mode=0o700)
    write_json(path, {"schema_version": 1, "hooks": [dict(h) for h in hooks]})


def add(root: Path, event: str, argv: Sequence[str]) -> dict[str, Any]:
    if event in LATER_EVENTS:
        raise HookRefused(f"event {event!r} is not in this release; hooks take {', '.join(RUN_EVENTS)}")
    if event not in RUN_EVENTS:
        raise HookRefused(f"unknown event {event!r}; hooks take {', '.join(RUN_EVENTS)}")
    problem = argv_problem(list(argv))
    if problem:
        raise HookRefused(problem)
    hooks = load(root)
    if len(hooks) >= MAX_HOOKS:
        raise HookRefused(f"at most {MAX_HOOKS} hooks are kept; remove one first")
    hook = {"id": uuid.uuid4().hex[:8], "event": event, "argv": list(argv)}
    _store(root, [*hooks, hook])
    return hook


def remove(root: Path, hook_id: str) -> dict[str, Any]:
    hooks = load(root)
    gone = next((h for h in hooks if h["id"] == hook_id), None)
    if gone is None:
        raise HookRefused(f"no hook {hook_id!r}")
    _store(root, [h for h in hooks if h["id"] != hook_id])
    return gone


def event_of(rec: Mapping[str, Any]) -> str | None:
    """The hook event a run-log record stands for, or None."""
    kind = rec.get("kind")
    if kind == "run_started":
        return "resumed" if rec.get("segment") else "started"
    if kind == "run_exit":
        code = rec.get("exit_code")
        return "finished" if code == 0 else None if code == 3 else "failed"  # 3 is a pause, told by `paused`
    return {"unit_entered": "unit_entered", "gate": "gate_verdict", "pause": "paused",
            "stop_requested": "stop_requested"}.get(str(kind))


def facts(event: str, workflow: str, task_id: str, rec: Mapping[str, Any]) -> dict[str, Any]:
    out: dict[str, Any] = {"schema_version": 1, "event": event, "workflow": workflow, "task_id": task_id,
                           "thread_id": f"{workflow}/{task_id}"}
    for k in FACT_FIELDS:
        v = rec.get(k)
        if isinstance(v, bool | int | float) or (isinstance(v, str) and len(v) <= 200) or (v is None and k in rec):
            out[k] = v
    return out


def on_record(log: Path, rec: Mapping[str, Any]) -> bool:
    """Called by the run log's writer; True when a hook child was started. Raises nothing the caller keeps."""
    event = event_of(rec)
    if event is None:
        return False
    root = log.parents[3]
    if not config_path(root).exists():
        return False
    mine = [h for h in load(root) if h["event"] == event]
    if not mine:
        return False
    workflow, task_id, seq = log.parent.parent.name, log.parent.name, int(rec.get("seq") or 0)
    folder = log.parent / "hooks"
    folder.mkdir(parents=True, exist_ok=True, mode=0o700)
    write_json(folder / f"{event}-{seq}.facts.json", facts(event, workflow, task_id, rec))
    home = home_path()
    tickets_dir(home).mkdir(parents=True, exist_ok=True, mode=0o700)
    for h in mine:
        write_json(tickets_dir(home) / f"{uuid.uuid4().hex}.json",
                   {"schema_version": 1, "root": str(root), "workflow": workflow, "task_id": task_id,
                    "event": event, "seq": seq, "hook": h["id"]})
    from tempergraph import detach

    return detach.start("tempergraph.observe.hooks", ("drain",), home)


def on_schedule_event(root: Path, event: str, workflow: str, schedule_id: str, extra: Mapping[str, Any]) -> bool:
    """A schedule-level hook event (`schedule_paused`): the facts file beside the schedule's runs in the target
    repository's state root, a ticket for each hook registered there, then the one drain child. Raises nothing."""
    try:
        mine = [h for h in load(root) if h["event"] == event]
        if not mine:
            return False
        task_id = f"schedule-{schedule_id}"
        folder = root / "runs" / workflow / task_id / "hooks"
        folder.mkdir(parents=True, exist_ok=True, mode=0o700)
        seq = len(list(folder.glob(f"{event}-*.facts.json"))) + 1
        doc: dict[str, Any] = {"schema_version": 1, "event": event, "workflow": workflow, "task_id": task_id,
                               "schedule_id": schedule_id}
        for k in ("cause", "thread", "failures"):
            v = extra.get(k)
            if isinstance(v, bool | int | float) or (isinstance(v, str) and len(v) <= 200):
                doc[k] = v
        write_json(folder / f"{event}-{seq}.facts.json", doc)
        home = home_path()
        tickets_dir(home).mkdir(parents=True, exist_ok=True, mode=0o700)
        for h in mine:
            write_json(tickets_dir(home) / f"{uuid.uuid4().hex}.json",
                       {"schema_version": 1, "root": str(root), "workflow": workflow, "task_id": task_id,
                        "event": event, "seq": seq, "hook": h["id"]})
        from tempergraph import detach

        return detach.start("tempergraph.observe.hooks", ("drain",), home)
    except Exception:  # noqa: BLE001 - a hook never changes a tick (OVR-B4)
        return False


def _slug(text: Any) -> bool:
    return isinstance(text, str) and 0 < len(text) <= 200 and set(text) <= _SLUG_CHARS and ".." not in text


def run_hook(root: Path, hook: Mapping[str, Any], facts_file: Path, out_path: Path) -> dict[str, Any]:
    """One hook's argv, from the registry, with the facts file named in its environment; never raises."""
    from tempergraph.run.commands import ResolvedCommand, run_command

    cmd = ResolvedCommand(argv=tuple(hook["argv"]), prefix=str(hook["argv"][0]), resolver="hook")
    try:
        got = run_command(cmd, root.parent, out_path, TIMEOUT_S,
                          env_extra={"TEMPERGRAPH_HOOK_EVENT": str(hook["event"]),
                                     "TEMPERGRAPH_HOOK_FACTS": str(facts_file)})
        return {"hook": hook["id"], "event": hook["event"], "exit_code": got.exit_code, "timed_out": got.timed_out,
                "duration_s": round(got.duration_s, 3), "error": got.extra.get("error"),
                "ok": got.exit_code == 0 and not got.timed_out, "log": out_path.name}
    except Exception as exc:  # noqa: BLE001 - a hook never changes anything (OVR-B4)
        return {"hook": hook["id"], "event": hook["event"], "exit_code": None, "timed_out": False,
                "duration_s": 0.0, "error": type(exc).__name__, "ok": False, "log": out_path.name}


def process(t: Mapping[str, Any]) -> dict[str, Any]:
    """One ticket, every value checked again: the argv is the registry's, the paths are derived (SEC-B5, SEC-B6)."""
    root = Path(str(t.get("root") or ""))
    event, seq = t.get("event"), t.get("seq")
    if not (root.is_absolute() and config_path(root).is_file() and event in RUN_EVENTS and isinstance(seq, int)
            and _slug(t.get("workflow")) and _slug(t.get("task_id"))):
        return {"error": "ticket_refused"}
    hook = next((h for h in load(root) if h["id"] == t.get("hook") and h["event"] == event), None)
    folder = root / "runs" / str(t["workflow"]) / str(t["task_id"]) / "hooks"
    facts_file = folder / f"{event}-{seq}.facts.json"
    if hook is None or not facts_file.is_file():
        return {"error": "ticket_refused"}
    result = {"ts": now_iso(), "seq": seq, **run_hook(root, hook, facts_file, folder / f"{event}-{seq}.{hook['id']}.log")}
    append_jsonl(folder / "results.jsonl", result)
    return result


def drain(home: Path | None = None) -> list[dict[str, Any]]:
    """Claims and runs every waiting ticket, oldest first; one ticket's failure never stops the next."""
    folder = tickets_dir(home or home_path())
    done: list[dict[str, Any]] = []
    for path in sorted(folder.glob("*.json"), key=lambda p: p.stat().st_mtime) if folder.is_dir() else ():
        claim = path.with_suffix(".claimed")
        try:
            os.replace(path, claim)  # one child per ticket
        except OSError:
            continue
        try:
            done.append(process(json.loads(claim.read_text(encoding="utf-8"))))
        except Exception as exc:  # noqa: BLE001
            done.append({"error": type(exc).__name__})
        finally:
            claim.unlink(missing_ok=True)
    return done


def fixture(event: str) -> dict[str, Any]:
    """The fixture facts `hooks test` runs a hook against: the shape of a real file, with made-up ids."""
    rec: dict[str, Any] = {"seq": 1, "ts": now_iso(), "segment": 0, "unit": "example", "item": None, "attempt": 1}
    extra: dict[str, dict[str, Any]] = {"gate_verdict": {"token": "PROCEED", "verdict": "PASS", "route_target": "next.step"},
                "paused": {"pause_kind": "approval"}, "finished": {"exit_code": 0, "reason": "finished"},
                "failed": {"exit_code": 1, "reason": "failed"}, "stop_requested": {"mode": "graceful"},
                "resumed": {"segment": 1}}
    rec.update(extra.get(event, {}))
    return facts(event, "example", "hook-test", rec)


def test(root: Path, event: str) -> list[dict[str, Any]]:
    """Runs each hook of `event` once, in this process, against the fixture facts; no run is touched."""
    if event not in RUN_EVENTS:
        raise HookRefused(f"unknown event {event!r}; hooks take {', '.join(RUN_EVENTS)}")
    folder = root / "hooks" / "test"
    folder.mkdir(parents=True, exist_ok=True, mode=0o700)
    facts_file = folder / f"{event}.facts.json"
    write_json(facts_file, fixture(event))
    return [run_hook(root, h, facts_file, folder / f"{event}.{h['id']}.log")
            for h in load(root) if h["event"] == event]


def main(argv: Sequence[str]) -> int:
    if list(argv) != ["drain"]:
        return 2
    drain()
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
