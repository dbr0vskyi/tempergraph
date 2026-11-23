"""The `os` trigger adapter: one per-user autostart entry that runs the shim's absolute path (TCK-B14, TCK-B15; SEC-B7).

The entry holds the shim's path and the verb `schedule loop` (`schedule tick` every 5 minutes for the crontab fallback),
nothing else: no shell, no person-typed value, no environment value. It is written as a file (a LaunchAgent, a systemd user
unit with its `default.target.wants` link, a Task Scheduler definition, a crontab line); this module starts no process, so
the OS picks the entry up at the next login (macOS, Linux) or when the person imports it (Windows, crontab), as `install`
says. `install` is idempotent and rewrites an entry whose shim path changed; `status` calls an entry whose shim is missing
`broken`; `remove` deletes what `install` wrote.
"""

from __future__ import annotations

import os
import shutil
import sys
from collections.abc import Callable
from dataclasses import dataclass
from pathlib import Path
from typing import Any
from xml.sax.saxutils import escape

from tempergraph.install import shim as shimmod

LABEL = "dev.tempergraph.schedule"
UNIT = "tempergraph-schedule.service"
MARKER = "tempergraph-schedule"
CRON_EVERY = "*/5 * * * *"
PLATFORM = sys.platform  # tests replace it: the one place the platform is read
KINDS = ("launchagent", "systemd", "taskscheduler", "crontab")
SAFE = frozenset("abcdefghijklmnopqrstuvwxyzABCDEFGHIJKLMNOPQRSTUVWXYZ0123456789_./:-+@\\")


class NoOsScheduler(Exception):
    """No per-user scheduler is usable (TCK-B14): `no_os_scheduler`; `loop` and `external` still work."""


class UnsafePath(Exception):
    """The shim's path holds a character a crontab line cannot carry without a shell."""


@dataclass
class Entry:
    kind: str
    path: Path
    text: str


def shim_for(home: Path, platform: str) -> Path:
    path = shimmod.shim_path(home)
    return path.with_name(path.name + ".cmd") if platform.startswith("win") else path


def detect(platform: str, user_home: Path, which: Callable[[str], str | None] | None = None) -> str | None:
    """The entry kind this machine takes, or None (`no_os_scheduler`)."""
    which = which or shutil.which
    if platform == "darwin":
        return "launchagent"
    if platform.startswith("win"):
        return "taskscheduler"
    if platform.startswith("linux") and which("systemctl"):
        return "systemd"
    return "crontab" if which("crontab") else None


def render(kind: str, shim: Path) -> str:
    """The entry text of one kind: the shim's absolute path and the verb only."""
    p = str(shim)
    if kind == "launchagent":
        return ('<?xml version="1.0" encoding="UTF-8"?>\n'
                '<!DOCTYPE plist PUBLIC "-//Apple//DTD PLIST 1.0//EN" "http://www.apple.com/DTDs/PropertyList-1.0.dtd">\n'
                '<plist version="1.0">\n<dict>\n'
                f"  <key>Label</key>\n  <string>{LABEL}</string>\n"
                "  <key>ProgramArguments</key>\n  <array>\n"
                f"    <string>{escape(p)}</string>\n    <string>schedule</string>\n    <string>loop</string>\n  </array>\n"
                "  <key>RunAtLoad</key>\n  <true/>\n  <key>KeepAlive</key>\n  <true/>\n</dict>\n</plist>\n")
    if kind == "systemd":
        quoted = '"' + p.replace("\\", "\\\\").replace('"', '\\"').replace("%", "%%") + '"'
        return ("[Unit]\nDescription=tempergraph schedule loop\n\n[Service]\n"
                f"ExecStart={quoted} schedule loop\nRestart=on-failure\n\n[Install]\nWantedBy=default.target\n")
    if kind == "taskscheduler":
        return ('<?xml version="1.0" encoding="UTF-8"?>\n'
                '<Task version="1.2" xmlns="http://schemas.microsoft.com/windows/2004/02/mit/task">\n'
                "  <Triggers>\n    <LogonTrigger>\n      <Enabled>true</Enabled>\n    </LogonTrigger>\n  </Triggers>\n"
                "  <Settings>\n    <MultipleInstancesPolicy>IgnoreNew</MultipleInstancesPolicy>\n"
                "    <ExecutionTimeLimit>PT0S</ExecutionTimeLimit>\n    <RestartOnFailure>\n"
                "      <Interval>PT1M</Interval>\n      <Count>999</Count>\n    </RestartOnFailure>\n  </Settings>\n"
                f"  <Actions>\n    <Exec>\n      <Command>{escape(p)}</Command>\n"
                "      <Arguments>schedule loop</Arguments>\n    </Exec>\n  </Actions>\n</Task>\n")
    if kind == "crontab":
        if not set(p) <= SAFE:
            raise UnsafePath(p)
        return f"{CRON_EVERY} {p} schedule tick  # {MARKER}\n"
    raise ValueError(kind)


def entry_path(kind: str, home: Path, user_home: Path) -> Path:
    if kind == "launchagent":
        return user_home / "Library" / "LaunchAgents" / f"{LABEL}.plist"
    if kind == "systemd":
        return user_home / ".config" / "systemd" / "user" / UNIT
    return home / "triggers" / ("tempergraph-schedule.task.xml" if kind == "taskscheduler" else "tempergraph-schedule.crontab")


def _wants(user_home: Path) -> Path:
    return user_home / ".config" / "systemd" / "user" / "default.target.wants" / UNIT


def _kinds_present(home: Path, user_home: Path) -> list[Entry]:
    out = []
    for kind in KINDS:
        p = entry_path(kind, home, user_home)
        if p.is_file():
            out.append(Entry(kind, p, p.read_text(encoding="utf-8", errors="replace")))
    return out


def entries_present(home: Path, user_home: Path | None = None) -> bool:
    """An `os` entry exists (read-only): a live trigger for `schedule add` (TCK-B15)."""
    return bool(_kinds_present(home, user_home or Path.home()))


def install(home: Path, *, platform: str | None = None, user_home: Path | None = None,
            which: Callable[[str], str | None] | None = None) -> dict[str, Any]:
    """Write the entry (idempotent: the same text is left alone, a changed shim path is rewritten) and the shim it names.
    Raises `NoOsScheduler`."""
    platform, user_home = platform or PLATFORM, user_home or Path.home()
    kind = detect(platform, user_home, which or shutil.which)
    if kind is None:
        raise NoOsScheduler("no per-user scheduler is usable here; `schedule loop --detach` and an external `schedule tick` still work")
    text = render(kind, shim_for(home, platform))
    if not platform.startswith("win"):
        shimmod.write_shim(home)  # an entry that points at a missing shim is mended with it
    path = entry_path(kind, home, user_home)
    same = path.is_file() and path.read_text(encoding="utf-8") == text
    if not same:
        path.parent.mkdir(parents=True, exist_ok=True)
        tmp = path.with_name(path.name + ".tmp")
        tmp.write_text(text, encoding="utf-8")
        os.replace(tmp, path)
    if kind == "systemd":
        link = _wants(user_home)
        link.parent.mkdir(parents=True, exist_ok=True)
        if not link.is_symlink() or Path(os.readlink(link)) != path:
            link.unlink(missing_ok=True)
            link.symlink_to(path)  # what `systemctl --user enable` does: nothing to launch
    return {"kind": kind, "path": str(path), "written": not same,
            "activate": {"launchagent": "it starts at your next login", "systemd": "it starts at your next login "
                         "(`systemctl --user enable --now tempergraph-schedule` starts it now)",
                         "taskscheduler": f"import it with: schtasks /create /tn tempergraph-schedule /xml \"{path}\"",
                         "crontab": f"add its line to your crontab with `crontab -e`: {path}"}[kind]}


def _shim_of(entry: Entry) -> str | None:
    for line in entry.text.splitlines():
        s = line.strip()
        if s.startswith("<string>/") or s.startswith("<string>"):
            inner = s.removeprefix("<string>").removesuffix("</string>")
            if inner not in ("schedule", "loop", LABEL):
                return inner.replace("&amp;", "&").replace("&lt;", "<").replace("&gt;", ">")
        if s.startswith("ExecStart="):
            return s.removeprefix("ExecStart=").rsplit(" schedule loop", 1)[0].strip('"').replace("%%", "%")
        if s.startswith("<Command>"):
            return s.removeprefix("<Command>").removesuffix("</Command>")
        if s.startswith(CRON_EVERY):
            return s.removeprefix(CRON_EVERY).split(" schedule tick", 1)[0].strip()
    return None


def status(home: Path, *, platform: str | None = None, user_home: Path | None = None) -> list[dict[str, Any]]:
    """Every `os` entry seen, with its state: `installed`, `outdated` (a shim path that moved) or `broken` (a missing shim)."""
    platform, user_home = platform or PLATFORM, user_home or Path.home()
    out = []
    for e in _kinds_present(home, user_home):
        wanted = shim_for(home, platform)
        named = _shim_of(e)
        state = "broken" if not named or not Path(named).is_file() else "installed" if named == str(wanted) else "outdated"
        out.append({"trigger": f"os:{e.kind}", "state": state, "path": str(e.path), "shim": named})
    return out


def refresh(home: Path, *, platform: str | None = None, user_home: Path | None = None) -> list[str]:
    """After an `update` moved the shim: rewrite an entry whose shim path changed (TCK-B8); nothing when none exists."""
    platform, user_home = platform or PLATFORM, user_home or Path.home()
    done = []
    for e in _kinds_present(home, user_home):
        try:
            if e.text != render(e.kind, shim_for(home, platform)):
                e.path.write_text(render(e.kind, shim_for(home, platform)), encoding="utf-8")
                done.append(e.kind)
        except (OSError, UnsafePath):
            continue
    return done


def remove(home: Path, *, user_home: Path | None = None) -> list[str]:
    """Delete what `install` wrote and leave no trace (the empty folders it made go too)."""
    user_home = user_home or Path.home()
    gone = []
    for e in _kinds_present(home, user_home):
        e.path.unlink(missing_ok=True)
        gone.append(str(e.path))
        starts = [e.path.parent]
        if e.kind == "systemd":
            _wants(user_home).unlink(missing_ok=True)
            starts.append(_wants(user_home).parent)
        for parent in starts:  # the folders `install` made, while they are empty
            while parent not in (user_home, home) and parent.is_dir() and not any(parent.iterdir()):
                parent.rmdir()
                parent = parent.parent
    return gone
